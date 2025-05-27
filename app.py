import os
import json
import torch
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import random

from flask import (
    Flask, request, render_template,
    redirect, url_for, session, jsonify
)

from models.timetable_nn import TimetableDataset, TimetableNet #
from everytime import Everytime #
from convert import Convert #

app = Flask(__name__) #
app.secret_key = "your_secret_key_here_for_session" # 세션 사용을 위해 secret_key 필수

# 과목 데이터 저장 관련 설정
SUBJECT_DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "subject_datas")
SUBJECT_DATA_FILE = os.path.join(SUBJECT_DATA_DIR, "subject_datas.json")

# 전역 변수로 시간표 슬롯 데이터 저장
global_timetable_slots = []

# 디렉토리 생성 함수
def ensure_subject_data_dir():
    if not os.path.exists(SUBJECT_DATA_DIR):
        os.makedirs(SUBJECT_DATA_DIR)

# 과목 데이터 저장 함수
def save_subject_data(timetable_slots):
    ensure_subject_data_dir()
    with open(SUBJECT_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(timetable_slots, f, ensure_ascii=False, indent=2)

# 과목 데이터 로드 함수
def load_subject_data():
    global global_timetable_slots
    if os.path.exists(SUBJECT_DATA_FILE):
        try:
            with open(SUBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
                global_timetable_slots = json.load(f)
            return global_timetable_slots
        except Exception as e:
            print(f"과목 데이터 로드 오류: {e}")
    return []

# 앱 시작 시 저장된 데이터 로드
load_subject_data()

# --- (기존 USER_CREDENTIALS, MODEL_PATH, 유틸리티 함수들은 동일) ---
USER_CREDENTIALS = {
    "admin": "helloai",
}

BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "model.pt") #


def time_to_minutes(time_str):
    if not time_str or ':' not in time_str:
        return None
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except ValueError:
        return None


def minutes_to_time_str(minutes):
    if minutes is None or minutes < 0:
        return "N/A"
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

# --- (기존 / , /logout, /login 라우트는 동일) ---
@app.route("/")
def main():
    return render_template("main.html") #


@app.route("/logout")
def logout():
    session.pop('username', None) #
    return redirect(url_for("login")) #


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == p: #
            session['username'] = u #
            return redirect(url_for("plan")) #
        return render_template("login.html", error="Incorrect username or password.", username=u) #
    return render_template("login.html", error=None, username="") #


@app.route("/process_timetable", methods=["POST"]) #
def process_timetable():
    # 이전 답변의 /process_timetable 로직과 동일하게 유지
    # (교수명, 강의실 정보 포함하여 timetable_results 생성하는 부분 확인)
    timetable_url = request.form.get("new_url") #
    if not timetable_url: #
        return jsonify({"error": "URL이 필요합니다."}), 400 #

    try:
        parsed = urlparse(timetable_url) #
        if parsed.netloc == "everytime.kr" and parsed.path.startswith("/@"): #
            timetable_id = parsed.path.split("/@")[-1] #
        elif not parsed.scheme and not parsed.netloc: # ID만 입력된 경우
            timetable_id = timetable_url #
        else:
            return jsonify({"error": "유효하지 않은 URL 또는 ID 형식입니다."}), 400

        e = Everytime(timetable_id) #
        xml_data = e.get_timetable() #
        if not xml_data or "<error>" in xml_data.lower() or "<code>-1</code>" in xml_data.lower(): #
            return jsonify({"error": "시간표 XML을 가져오지 못했습니다. ID를 확인하거나 잠시 후 다시 시도해주세요."}), 400 #

        c = Convert(xml_data) #
        subjects = c.get_subjects() #
        if not subjects: #
            return jsonify({ #
                "timetable_slots": [], #
                "message": "과목 정보를 찾을 수 없습니다." #
            })

        day_map = {
            "0": "월요일", "1": "화요일", "2": "수요일",
            "3": "목요일", "4": "금요일", "5": "토요일", "6": "일요일"
        } #
        free_start = time_to_minutes("09:00") #
        free_end   = time_to_minutes("21:00") #
        timetable_results = [] #

        for subj in subjects: #
            name = subj.get("name", "N/A") #
            professor = subj.get("professor", "")
            for info in subj.get("info", []): #
                d, s, e = info.get("day"), info.get("startAt"), info.get("endAt") #
                place = info.get("place", "")
                if d in day_map and s and e: #
                    if time_to_minutes(s) is not None and time_to_minutes(e) is not None: #
                        timetable_results.append(( #
                            "수업", name, day_map[d], s, e, professor, place
                        ))

        for d_key in sorted(day_map.keys()): #
            day_name = day_map[d_key] #
            day_classes = [] #
            for subj_inner in subjects:
                for info in subj_inner.get("info", []): #
                    if info.get("day") == d_key: #
                        s_mins = time_to_minutes(info.get("startAt")) #
                        e_mins = time_to_minutes(info.get("endAt")) #
                        if s_mins is not None and e_mins is not None and s_mins < e_mins: #
                            if e_mins > free_start and s_mins < free_end: #
                                day_classes.append((s_mins, e_mins)) #
            day_classes.sort(key=lambda x: x[0]) #

            last_end = free_start #
            if not day_classes: #
                if free_end > free_start: #
                    timetable_results.append(( #
                        "공강", "", day_name, #
                        minutes_to_time_str(free_start), #
                        minutes_to_time_str(free_end), #
                        "", ""
                    ))
            else:
                for s_class, e_class in day_classes: #
                    effective_free_slot_start = max(free_start, last_end)
                    effective_free_slot_end = min(s_class, free_end)

                    if effective_free_slot_end > effective_free_slot_start:
                        timetable_results.append(( #
                            "공강", "", day_name, #
                            minutes_to_time_str(effective_free_slot_start),
                            minutes_to_time_str(effective_free_slot_end),
                            "", ""
                        ))
                    last_end = max(last_end, e_class) #

                if last_end < free_end: #
                    timetable_results.append(( #
                        "공강", "", day_name, #
                        minutes_to_time_str(last_end), #
                        minutes_to_time_str(free_end), #
                        "", ""
                    ))

        def sort_key(item): #
            if len(item) < 7:
                return (7, float('inf'), 1)
            typ, _, day_nm, s, _1, _2, _3 = item
            order = { "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4, "토요일": 5, "일요일": 6 } #
            s_min = time_to_minutes(s) or float('inf') #
            return (order.get(day_nm, 7), s_min, 0 if typ == "공강" else 1) #

        timetable_results.sort(key=sort_key) #
        response = {"timetable_slots": timetable_results} #
        return jsonify(response) #

    except ET.ParseError: #
        return jsonify({"error": "시간표 XML 파싱 중 오류가 발생했습니다."}), 500 #
    except requests.RequestException: #
        return jsonify({"error": "Everytime 서버와 통신 중 네트워크 오류가 발생했습니다."}), 500 #
    except Exception as e: #
        return jsonify({"error": f"시간표 처리 중 예기치 못한 오류가 발생했습니다: {str(e)}"}), 500 #

# app.py (/plan 라우트 수정)

@app.route("/plan", methods=["GET", "POST"])
def plan():
    global global_timetable_slots
    
    if request.method == "POST":
        # ... (기존의 slots_json, names, weights, model prediction 등 로직은 동일) ...
        # --- (이전 답변의 filtered_names, adjusted_weights, preds 등 계산 부분은 동일하게 유지) ---
        slots_json = request.form.get("timetable_slots", "")
        if not slots_json:
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="시간표 정보가 없습니다.")
        try:
            timetable_slots_full = json.loads(slots_json)
        except json.JSONDecodeError:
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="시간표 데이터 파싱 실패")

        names = request.form.getlist("name")
        weights = []
        raw_weights = request.form.getlist("weight")
        for w in raw_weights:
            try: weights.append(float(w))
            except ValueError: weights.append(0.0)

        majors_raw = request.form.getlist("major")
        major_flags = [1.0 if v == "on" else 0.0 for v in majors_raw]
        if len(major_flags) < len(weights):
            major_flags += [0.0] * (len(weights) - len(major_flags))

        valid_subject_indices = [i for i, name in enumerate(names) if name.strip()]
        if not valid_subject_indices:
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="유효한 과목명이 하나 이상 필요합니다.")

        filtered_names = [names[i] for i in valid_subject_indices]
        filtered_weights = [weights[i] for i in valid_subject_indices]
        filtered_major_flags = [major_flags[i] for i in valid_subject_indices]

        if not filtered_names or sum(filtered_weights) == 0:
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="과목 정보가 없거나 모든 과목의 가중치가 0입니다.")

        adjusted_weights = [w * (1.0 + mf * 0.5) for w, mf in zip(filtered_weights, filtered_major_flags)]
        slots_for_dataset = [(s[0], s[1], s[2], s[3], s[4]) for s in timetable_slots_full]

        checkpoint = torch.load(MODEL_PATH, map_location="cpu")
        num_subjects_saved = checkpoint['net.4.weight'].size(0)

        dataset = TimetableDataset(slots_for_dataset, filtered_names, adjusted_weights)
        input_dim = dataset.inputs.shape[1]

        model = TimetableNet(input_dim=input_dim, hidden_dim=64, num_subjects=num_subjects_saved)
        model.load_state_dict(checkpoint)
        model.eval()

        with torch.no_grad():
            logits = model(dataset.inputs)
            preds = torch.argmax(logits, dim=1).tolist()

        # --- 파이 차트 데이터 준비 (results_for_pie_chart) ---
        schedule_entries_for_pie = []
        for i, slot_data in enumerate(timetable_slots_full): # timetable_slots_full 사용
            kind = slot_data[0]
            if kind == "공강":
                p_idx = preds[i] # preds는 timetable_slots_full (및 slots_for_dataset)과 인덱스 정렬됨
                if 0 <= p_idx < len(filtered_names):
                    schedule_entries_for_pie.append({
                        "start": slot_data[3],
                        "end": slot_data[4],
                        "subject": filtered_names[p_idx]
                    })

        subject_total_minutes = {}
        for entry in schedule_entries_for_pie:
            subject_name = entry["subject"]
            start_m = time_to_minutes(entry["start"])
            end_m = time_to_minutes(entry["end"])
            if start_m is not None and end_m is not None and end_m > start_m:
                duration = end_m - start_m
                subject_total_minutes[subject_name] = subject_total_minutes.get(subject_name, 0) + duration

        results_for_pie_chart = []
        for name, total_mins in subject_total_minutes.items():
            if total_mins > 0:
                hours = total_mins // 60
                minutes_val = total_mins % 60
                results_for_pie_chart.append((name, hours, minutes_val))
        results_for_pie_chart.sort(key=lambda x: x[0])

        # --- 전체 시간표 구성용 데이터 준비 (all_schedule_items) ---
        all_schedule_items_for_modal = []
        temp_subject_names_for_colors = set() # 실제 수업 과목만 색상 지정을 위해

        for i, slot_data in enumerate(timetable_slots_full):
            kind = slot_data[0]
            original_subject_name = slot_data[1]
            day = slot_data[2]
            start_time = slot_data[3]
            end_time = slot_data[4]
            professor = slot_data[5]
            place = slot_data[6]

            item_details = {
                'day': day, 'start_time': start_time, 'end_time': end_time,
                'professor': professor, 'place': place,
            }

            if kind == "수업":
                item_details['subject_name'] = original_subject_name
                item_details['type'] = 'class'
                all_schedule_items_for_modal.append(item_details)
                temp_subject_names_for_colors.add(original_subject_name)
            elif kind == "공강":
                p_idx = preds[i]
                if 0 <= p_idx < len(filtered_names):
                    predicted_subject_name = filtered_names[p_idx]
                    item_details['subject_name'] = predicted_subject_name
                    item_details['type'] = 'study'
                    item_details['professor'] = ""
                    item_details['place'] = "공강 자습" # 여기에 "공강 자습" 텍스트
                    all_schedule_items_for_modal.append(item_details)
                    # 학습 과목은 temp_subject_names_for_colors에 추가하지 않음 (별도 색상X 또는 다른 방식)

        subject_colors = {}
        color_palette = [
            "#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF",
            "#A0C4FF", "#BDB2FF", "#FFC6FF", "#FFC8DD", "#E0BBE4",
            "#D4F0F0", "#F9E2AE", "#F7CAC9", "#B2E2F2", "#D8BFD8"
        ]
        idx = 0
        sorted_class_subject_names = sorted(list(temp_subject_names_for_colors))
        for subj_name in sorted_class_subject_names:
            subject_colors[subj_name] = color_palette[idx % len(color_palette)]
            idx += 1

        for item in all_schedule_items_for_modal:
            if item['type'] == 'class':
                item['color'] = subject_colors.get(item['subject_name'], '#E0E0E0')
            else: # 'study' 타입 (공강 자습)
                item['color'] = 'transparent' # 또는 특정 연한 회색 등 기본색

        full_schedule_raw_data_for_js = {
            'all_schedule_items': all_schedule_items_for_modal
            # 필요하다면 DAYS_ORDER, time_intervals_display 등도 여기서 미리 생성해서 전달 가능
        }

        # 현재 데이터를 전역 변수와 파일에 저장
        global_timetable_slots = timetable_slots_full
        save_subject_data(timetable_slots_full)

        # 세션 사용 대신 직접 템플릿으로 모든 데이터 전달
        return render_template("result.html",
                               results_for_pie_chart=results_for_pie_chart,
                               full_schedule_raw_data=full_schedule_raw_data_for_js)

    # GET 요청 시 저장된 데이터 불러오기
    if not global_timetable_slots:
        global_timetable_slots = load_subject_data()
    
    # 저장된 데이터가 있으면 index.html에 시간표 데이터 전달
    return render_template("index.html", timetable_slots=json.dumps(global_timetable_slots) if global_timetable_slots else "")

# `/show_full_schedule` 라우트는 이제 사용하지 않으므로 삭제하거나 주석 처리합니다.
# @app.route("/show_full_schedule")
# def show_full_schedule():
#    ...

@app.route("/show_full_schedule")
def show_full_schedule():
    schedule_data = session.get('full_schedule_data')
    if not schedule_data:
        return redirect(url_for('plan'))

    timetable_slots_full = schedule_data['timetable_slots_full']
    preds = schedule_data['preds']
    filtered_names = schedule_data['filtered_names']

    all_schedule_items = []
    temp_subject_names_for_colors = set() # 실제 수업 과목만 색상 지정을 위해 사용

    for i, slot_data in enumerate(timetable_slots_full):
        kind = slot_data[0]
        original_subject_name = slot_data[1]
        day = slot_data[2]
        start_time = slot_data[3]
        end_time = slot_data[4]
        professor = slot_data[5]
        place = slot_data[6]

        item_details = {
            'day': day,
            'start_time': start_time,
            'end_time': end_time,
            'professor': professor,
            'place': place, # 수업의 경우 원래 장소
        }

        if kind == "수업":
            item_details['subject_name'] = original_subject_name
            item_details['type'] = 'class'
            all_schedule_items.append(item_details)
            temp_subject_names_for_colors.add(original_subject_name)
        elif kind == "공강":
            p_idx = preds[i]
            if 0 <= p_idx < len(filtered_names):
                predicted_subject_name = filtered_names[p_idx]
                item_details['subject_name'] = predicted_subject_name
                item_details['type'] = 'study'
                item_details['professor'] = "" # 자습에는 교수 정보 없음
                item_details['place'] = "공강 자습" # 요청하신 텍스트
                # temp_subject_names_for_colors 에 study 과목은 추가하지 않음 (색상 X)
                all_schedule_items.append(item_details)

    # 수업 과목에 대해서만 색상 지정
    subject_colors = {}
    color_palette = [
        "#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF",
        "#A0C4FF", "#BDB2FF", "#FFC6FF", "#FFC8DD", "#E0BBE4",
        "#D4F0F0", "#F9E2AE", "#F7CAC9", "#B2E2F2", "#D8BFD8"
    ]
    idx = 0
    # 실제 수업 과목들에 대해서만 색상을 할당
    sorted_class_subject_names = sorted(list(temp_subject_names_for_colors))
    for subj_name in sorted_class_subject_names:
        subject_colors[subj_name] = color_palette[idx % len(color_palette)]
        idx += 1

    for item in all_schedule_items:
        if item['type'] == 'class':
            item['color'] = subject_colors.get(item['subject_name'], '#E0E0E0') # 수업은 색상 지정
        else: # 'study' 타입 (공강 자습)
            item['color'] = 'transparent' # 또는 '#FFFFFF' (흰색 배경) 또는 아예 지정 안함

    # --- (이하 schedule_grid 생성 로직은 이전과 동일) ---
    DAYS_ORDER = ["월요일", "화요일", "수요일", "목요일", "금요일"]
    time_intervals_display = []
    time_intervals_minutes = []
    current_display_time_min = time_to_minutes("09:00")
    max_display_time_min = time_to_minutes("18:00")
    interval_duration_min = 30

    while current_display_time_min < max_display_time_min:
        time_intervals_display.append(minutes_to_time_str(current_display_time_min))
        time_intervals_minutes.append(current_display_time_min)
        current_display_time_min += interval_duration_min

    schedule_grid = {time_str: {day: None for day in DAYS_ORDER} for time_str in time_intervals_display}

    for item in all_schedule_items:
        item_start_min = time_to_minutes(item['start_time'])
        item_end_min = time_to_minutes(item['end_time'])
        day = item['day']

        if day not in DAYS_ORDER or item_start_min is None or item_end_min is None:
            continue

        duration_min = item_end_min - item_start_min
        if duration_min <= 0 : continue

        item['rowspan'] = duration_min // interval_duration_min
        if item['rowspan'] == 0 and duration_min > 0 : item['rowspan'] = 1

        start_interval_index = -1
        for i_idx, t_min in enumerate(time_intervals_minutes):
            if item_start_min == t_min :
                start_interval_index = i_idx
                break

        if start_interval_index != -1 and start_interval_index < len(time_intervals_display):
            start_time_str = time_intervals_display[start_interval_index]
            if schedule_grid.get(start_time_str, {}).get(day) is None:
                schedule_grid[start_time_str][day] = item
                for r_idx in range(1, item['rowspan']):
                    covered_interval_index = start_interval_index + r_idx
                    if covered_interval_index < len(time_intervals_display):
                        covered_time_str = time_intervals_display[covered_interval_index]
                        if day in schedule_grid[covered_time_str]: # Ensure day exists
                            schedule_grid[covered_time_str][day] = "covered"

    return render_template("full_schedule.html",
                           schedule_grid=schedule_grid,
                           time_intervals=time_intervals_display,
                           days_of_week=DAYS_ORDER)

if __name__ == "__main__": #
    app.run(debug=True) #