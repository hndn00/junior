import os
import json
import torch
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from flask import (
    Flask, request, render_template,
    redirect, url_for, session, jsonify
)

from models.timetable_nn import TimetableDataset, TimetableNet
from everytime import Everytime
from convert import Convert

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# 간단 로그인 정보
USER_CREDENTIALS = {
    "admin": "helloai",
}

# 모델 파일 위치
BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "model.pt")


def time_to_minutes(time_str):
    """HH:MM → 자정부터 분."""
    if not time_str or ':' not in time_str:
        return None
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def minutes_to_time_str(minutes):
    """분 → HH:MM."""
    if minutes is None or minutes < 0:
        return "N/A"
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


@app.route("/")
def main():
    return render_template("main.html")


@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == p:
            session['username'] = u
            return redirect(url_for("plan"))
        return render_template("login.html", error="Incorrect username or password.", username=u)
    return render_template("login.html", error=None, username="")


@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
        # 1) 숨은 필드에서 slots JSON 불러오기
        slots_json = request.form.get("timetable_slots", "")
        if not slots_json:
            return "시간표 정보가 없습니다. 먼저 Load Timetable 해주세요.", 400
        try:
            timetable_slots = json.loads(slots_json)
        except json.JSONDecodeError:
            return "시간표 데이터 파싱 실패", 400

        # 2) 과목명, 중요도, 전공 여부 읽기
        names      = request.form.getlist("name")
        weights    = list(map(float, request.form.getlist("weight")))
        majors_raw = request.form.getlist("major")  # 체크박스 name="major"
        major_flags = [1.0 if v == "on" else 0.0 for v in majors_raw]
        # padding
        if len(major_flags) < len(weights):
            major_flags += [0.0] * (len(weights) - len(major_flags))

        if not names or not weights or sum(weights) == 0:
            return "입력 데이터가 올바르지 않습니다.", 400

        # 전공 과목 +50% 가중치
        adjusted_weights = [
            w * (1.0 + mf * 0.5)
            for w, mf in zip(weights, major_flags)
        ]

        # 3) 체크포인트 로드 → 저장된 num_subjects 추출
        checkpoint = torch.load(MODEL_PATH, map_location="cpu")
        num_subjects_saved = checkpoint['net.4.weight'].size(0)

        # 4) Dataset 생성 & input_dim 결정
        dataset = TimetableDataset(timetable_slots, names, adjusted_weights)
        input_dim = dataset.inputs.shape[1]

        # 5) 모델 초기화 및 가중치 로드
        model = TimetableNet(input_dim=input_dim,
                             hidden_dim=64,
                             num_subjects=num_subjects_saved)
        model.load_state_dict(checkpoint)
        model.eval()

        # 6) 추론
        with torch.no_grad():
            logits = model(dataset.inputs)
            preds  = torch.argmax(logits, dim=1).tolist()

        # 7) “공강” 구간별 추천 스케줄 생성
        schedule_entries = []
        for slot, p in zip(timetable_slots, preds):
            kind, _, day, st, ed = slot
            if kind == "공강" and 0 <= p < len(names):
                schedule_entries.append({
                    "day": day,
                    "start": st,
                    "end": ed,
                    "subject": names[p]
                })

        return render_template("schedule.html",
                               schedule_entries=schedule_entries)

    # GET
    return render_template("index.html")


@app.route("/process_timetable", methods=["POST"])
def process_timetable():
    timetable_url = request.form.get("new_url")
    if not timetable_url:
        return jsonify({"error": "URL이 필요합니다."}), 400

    try:
        parsed = urlparse(timetable_url)
        if parsed.netloc == "everytime.kr" and parsed.path.startswith("/@"):
            timetable_id = parsed.path.split("/@")[-1]
        elif not parsed.scheme and not parsed.netloc:
            timetable_id = timetable_url
        else:
            return jsonify({"error": "유효하지 않은 URL 또는 ID"}), 400

        # 1) XML 가져오기
        e = Everytime(timetable_id)
        xml_data = e.get_timetable()
        if not xml_data or "<error>" in xml_data.lower() or "<code>-1</code>" in xml_data.lower():
            return jsonify({"error": "시간표 XML을 가져오지 못했습니다."}), 400

        # 2) XML → subjects
        c = Convert(xml_data)
        subjects = c.get_subjects()
        if not subjects:
            return jsonify({
                "timetable_slots": [],
                "message": "과목 정보를 찾을 수 없습니다."
            })

        # 3) 수업/공강 슬롯 계산
        day_map = {
            "0": "월요일", "1": "화요일", "2": "수요일",
            "3": "목요일", "4": "금요일", "5": "토요일", "6": "일요일"
        }
        free_start = time_to_minutes("09:00")
        free_end   = time_to_minutes("21:00")
        timetable_results = []

        # 수업 슬롯
        for subj in subjects:
            name = subj.get("name", "N/A")
            for info in subj.get("info", []):
                d, s, e = info.get("day"), info.get("startAt"), info.get("endAt")
                if d in day_map and s and e:
                    if time_to_minutes(s) is not None and time_to_minutes(e) is not None:
                        timetable_results.append((
                            "수업", name, day_map[d], s, e
                        ))

        # 공강 슬롯
        for d in sorted(day_map.keys()):
            day_name = day_map[d]
            day_classes = []
            for subj in subjects:
                for info in subj.get("info", []):
                    if info.get("day") == d:
                        s = time_to_minutes(info.get("startAt"))
                        e = time_to_minutes(info.get("endAt"))
                        if s is not None and e is not None and s < e:
                            if e > free_start and s < free_end:
                                day_classes.append((s, e))
            day_classes.sort(key=lambda x: x[0])

            last_end = free_start
            if not day_classes:
                if free_end > free_start:
                    timetable_results.append((
                        "공강", "", day_name,
                        minutes_to_time_str(free_start),
                        minutes_to_time_str(free_end)
                    ))
            else:
                for s, e in day_classes:
                    seg_s = max(s, free_start)
                    seg_e = min(e, free_end)
                    if seg_s > last_end:
                        timetable_results.append((
                            "공강", "", day_name,
                            minutes_to_time_str(last_end),
                            minutes_to_time_str(seg_s)
                        ))
                    last_end = max(last_end, seg_e)
                if last_end < free_end:
                    timetable_results.append((
                        "공강", "", day_name,
                        minutes_to_time_str(last_end),
                        minutes_to_time_str(free_end)
                    ))

        # 정렬
        def sort_key(item):
            typ, _, day_nm, s, _ = item
            order = {
                "월요일": 0, "화요일": 1, "수요일": 2,
                "목요일": 3, "금요일": 4, "토요일": 5, "일요일": 6
            }
            s_min = time_to_minutes(s) or float('inf')
            return (order.get(day_nm, 7), s_min, 0 if typ == "공강" else 1)

        timetable_results.sort(key=sort_key)
        response = {"timetable_slots": timetable_results}
        print("Responding with:", response)
        return jsonify(response)

    except ET.ParseError:
        return jsonify({"error": "XML 파싱 오류"}), 500
    except requests.RequestException as e:
        return jsonify({"error": f"네트워크 오류: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"예기치 못한 오류: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
