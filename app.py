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
app.secret_key = "your_secret_key_here_for_session" #

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
def load_subject_data_from_file(): # 함수 이름 변경 (혼동 방지)
    # global global_timetable_slots # 이 함수는 전역 변수를 직접 수정하지 않음
    if os.path.exists(SUBJECT_DATA_FILE):
        try:
            with open(SUBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            return loaded_data
        except Exception as e:
            print(f"과목 데이터 로드 오류: {e}")
    return []

# 앱 시작 시 저장된 데이터 로드 (이 부분은 제거하거나 주석 처리하여 자동 로드를 막습니다)
# load_subject_data()
# -> 사용자의 요청은 'Load JSON' 버튼을 눌렀을 때만 불러오는 것이므로 앱 시작 시 로드는 불필요.

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
    # (이전과 동일한 로직)
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

        # ProcessTimetable 결과를 global_timetable_slots 에 저장하고 파일에도 저장
        global global_timetable_slots
        global_timetable_slots = timetable_results
        save_subject_data(global_timetable_slots)

        response = {"timetable_slots": timetable_results} #
        return jsonify(response) #

    except ET.ParseError: #
        return jsonify({"error": "시간표 XML 파싱 중 오류가 발생했습니다."}), 500 #
    except requests.RequestException: #
        return jsonify({"error": "Everytime 서버와 통신 중 네트워크 오류가 발생했습니다."}), 500 #
    except Exception as e: #
        return jsonify({"error": f"시간표 처리 중 예기치 못한 오류가 발생했습니다: {str(e)}"}), 500 #

# JSON 파일에서 시간표 데이터를 로드하는 새 라우트
@app.route("/load_stored_timetable", methods=["GET"])
def load_stored_timetable_route():
    global global_timetable_slots
    loaded_data = load_subject_data_from_file()
    if loaded_data:
        global_timetable_slots = loaded_data
        return jsonify({"timetable_slots": global_timetable_slots, "message": "저장된 시간표를 불러왔습니다."})
    else:
        return jsonify({"timetable_slots": [], "message": "저장된 시간표 데이터가 없거나 불러오는데 실패했습니다."}), 404

@app.route("/plan", methods=["GET", "POST"])
def plan():
    global global_timetable_slots

    if request.method == "POST":
        # ... (POST 요청 로직은 이전 답변과 동일하게 유지) ...
        # POST 요청 시에는 global_timetable_slots을 현재 form에서 받은 데이터로 업데이트하고 저장
        slots_json = request.form.get("timetable_slots", "")
        if not slots_json:
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="시간표 정보가 없습니다.")
        try:
            timetable_slots_full = json.loads(slots_json)
        except json.JSONDecodeError:
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="시간표 데이터 파싱 실패")

        # ===== POST 로직 시작 (이전 답변 내용과 거의 동일) =====
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

        if not os.path.exists(MODEL_PATH):
            return render_template("result.html", results_for_pie_chart=[], full_schedule_raw_data={}, error_message="학습된 모델 파일(model.pt)을 찾을 수 없습니다.")

        checkpoint = torch.load(MODEL_PATH, map_location="cpu")
        num_subjects_saved = checkpoint['net.4.weight'].size(0)

        # filtered_names의 수가 모델이 학습된 num_subjects_saved와 다를 경우 에러 처리 또는 조정 필요
        # 여기서는 TimetableDataset이 subject_list를 받아서 처리하므로,
        # TimetableNet의 출력 뉴런 수(num_subjects_saved)와 filtered_names 길이가 일치해야 함.
        # 만약 num_subjects_saved가 filtered_names의 실제 길이보다 크면 preds 인덱싱은 문제 없으나,
        # 작으면 preds 에서 에러 발생 가능.
        # 여기서는 train_model.py 에서 num_subjects를 동적으로 결정하고,
        # TimetableNet도 그에 맞춰 생성된다고 가정.
        # 하지만, 실제 사용 시에는 저장된 모델의 num_subjects와 현재 입력 과목 수가 다를 수 있음을 인지해야함.
        # 가장 안전한 방법은 TimetableNet의 마지막 레이어를 현재 filtered_names 길이에 맞게 동적으로 바꾸거나,
        # 예측 시 num_subjects_saved와 filtered_names.length 중 작은 값으로 preds를 제한하는 것.
        # 여기서는 TimetableDataset이 알아서 처리한다고 가정하고 진행.
        # (TimetableNet은 num_subjects_saved 만큼의 출력을 생성)

        dataset = TimetableDataset(slots_for_dataset, filtered_names, adjusted_weights)
        input_dim = dataset.inputs.shape[1]

        model = TimetableNet(input_dim=input_dim, hidden_dim=64, num_subjects=num_subjects_saved)
        model.load_state_dict(checkpoint)
        model.eval()

        with torch.no_grad():
            logits = model(dataset.inputs) # logits.shape: (num_slots, num_subjects_saved)
            preds = torch.argmax(logits, dim=1).tolist()

        schedule_entries_for_pie = []
        for i, slot_data in enumerate(timetable_slots_full):
            kind = slot_data[0]
            if kind == "공강":
                p_idx = preds[i]
                # p_idx는 0부터 num_subjects_saved-1 사이의 값. filtered_names의 인덱스로 사용하려면 len(filtered_names) 보다 작아야 함.
                if 0 <= p_idx < len(filtered_names): # 이 조건 중요!
                    schedule_entries_for_pie.append({
                        "start": slot_data[3],
                        "end": slot_data[4],
                        "subject": filtered_names[p_idx]
                    })
                # else: p_idx가 filtered_names 범위를 벗어나는 경우 (모델이 더 많은 과목으로 학습된 경우 등) 이 공강은 할당되지 않음

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

        all_schedule_items_for_modal = []
        temp_subject_names_for_colors = set()

        for i, slot_data in enumerate(timetable_slots_full):
            kind = slot_data[0]
            original_subject_name = slot_data[1]
            day = slot_data[2]
            start_time = slot_data[3]
            end_time = slot_data[4]
            professor = slot_data[5] if len(slot_data) > 5 else ""
            place = slot_data[6] if len(slot_data) > 6 else ""

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
                if 0 <= p_idx < len(filtered_names): # 이 조건 중요!
                    predicted_subject_name = filtered_names[p_idx]
                    item_details['subject_name'] = predicted_subject_name
                    item_details['type'] = 'study'
                    item_details['professor'] = ""
                    item_details['place'] = "공강 자습"
                    all_schedule_items_for_modal.append(item_details)
                # else: 할당되지 않은 공강은 all_schedule_items_for_modal에 추가되지 않음

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
            else:
                item['color'] = 'transparent'

        full_schedule_raw_data_for_js = {
            'all_schedule_items': all_schedule_items_for_modal
        }

        global_timetable_slots = timetable_slots_full # 현재 사용된 시간표를 global에 반영
        save_subject_data(global_timetable_slots) # 파일에도 저장

        return render_template("result.html",
                               results_for_pie_chart=results_for_pie_chart,
                               full_schedule_raw_data=full_schedule_raw_data_for_js)
        # ===== POST 로직 종료 =====

    # GET 요청 시:
    # 항상 빈 timetable_slots를 전달하여 페이지가 초기 상태로 로드되도록 함.
    # global_timetable_slots은 서버에 유지되지만, GET 요청 시 자동으로 화면에 로드되지 않음.
    # 사용자가 "Load JSON" 버튼을 눌러야 서버의 global_timetable_slots (또는 파일) 데이터가 로드됨.
    return render_template("index.html", timetable_slots="") # 빈 문자열 전달


@app.route("/show_full_schedule")
def show_full_schedule():
    # 이 라우트는 result.html에서 모달로 대체되었으므로,
    # 세션 방식 대신 global_timetable_slots 와 예측 결과를 사용하도록 수정하거나,
    # result.html에서 직접 JS로 full_schedule_raw_data를 사용하므로 불필요해질 수 있습니다.
    # 현재는 global_timetable_slots에 저장된 데이터를 기반으로 시간표를 생성하는 로직이 필요합니다.
    # (단, 예측 결과 preds 와 filtered_names 가 필요하므로, 이들을 어떻게 가져올지 결정해야 합니다.
    #  가장 간단한 방법은 /plan POST에서 이를 global 변수나 세션에 저장하는 것이지만,
    #  사용자 요청은 result.html에서 모달로 보는 것이므로 이 라우트가 계속 필요할지 검토 필요)

    # 임시로, 만약 global_timetable_slots만 사용해서 표시해야 한다면,
    # 예측 없이 '수업'과 '공강'만 표시하거나,
    # 또는 /plan POST 시 `preds`와 `filtered_names`도 `global_` 변수에 저장해야 합니다.
    # 여기서는 단순화를 위해 `global_timetable_slots` (수업/공강 정보만 있는)를 기반으로
    # 시간표를 그리는 예시를 보입니다. ML 예측 결과는 반영되지 않습니다.
    # 제대로 된 전체 시간표를 보려면 ML 예측결과가 필요합니다.

    current_timetable_slots = global_timetable_slots # 또는 파일에서 다시 로드
    if not current_timetable_slots:
        return render_template("full_schedule.html", message="표시할 시간표 데이터가 없습니다. 먼저 시간표를 로드하거나 계획을 생성해주세요.")

    all_schedule_items = []
    temp_subject_names_for_colors = set()

    for slot_data in current_timetable_slots:
        kind = slot_data[0]
        original_subject_name = slot_data[1]
        day = slot_data[2]
        start_time = slot_data[3]
        end_time = slot_data[4]
        professor = slot_data[5] if len(slot_data) > 5 else ""
        place = slot_data[6] if len(slot_data) > 6 else ""

        item_details = {
            'day': day,
            'start_time': start_time,
            'end_time': end_time,
            'professor': professor,
            'place': place,
            'subject_name': original_subject_name, # 공강이면 비어있을 수 있음
            'type': 'class' if kind == "수업" else 'free', # 'study' 대신 'free'로 임시 구분
        }
        all_schedule_items.append(item_details)
        if kind == "수업":
            temp_subject_names_for_colors.add(original_subject_name)

    subject_colors = {}
    color_palette = [
        "#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF",
        "#A0C4FF", "#BDB2FF", "#FFC6FF", "#FFC8DD", "#E0BBE4"
    ]
    idx = 0
    sorted_class_subject_names = sorted(list(temp_subject_names_for_colors))
    for subj_name in sorted_class_subject_names:
        subject_colors[subj_name] = color_palette[idx % len(color_palette)]
        idx += 1

    for item in all_schedule_items:
        if item['type'] == 'class':
            item['color'] = subject_colors.get(item['subject_name'], '#E0E0E0')
        else: # 'free' (공강)
            item['color'] = 'transparent'


    DAYS_ORDER = ["월요일", "화요일", "수요일", "목요일", "금요일"]
    time_intervals_display = []
    time_intervals_minutes = []
    current_display_time_min = time_to_minutes("09:00")
    max_display_time_min = time_to_minutes("18:00") # full_schedule.html 과 동일하게
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

        item['rowspan'] = max(1, duration_min // interval_duration_min)


        start_interval_index = -1
        # 정확히 일치하는 시작 시간 또는 가장 가까운 이전 시간 간격을 찾습니다.
        for i_idx, t_min in enumerate(time_intervals_minutes):
            if item_start_min >= t_min and (i_idx + 1 == len(time_intervals_minutes) or item_start_min < time_intervals_minutes[i_idx+1]):
                # 만약 item_start_min이 t_min과 정확히 일치하지 않으면, 가장 가까운 t_min에 스냅합니다.
                # 이는 그리드에 맞추기 위함입니다. 정확한 시작/종료는 아이템 내부에 표시됩니다.
                # 또는, item_start_min이 그리드 간격과 정확히 일치한다고 가정합니다. 여기서는 후자를 따릅니다.
                if item_start_min == t_min:
                    start_interval_index = i_idx
                    break

                    # 만약 정확한 시간대를 찾지 못했지만, 범위 내에 있다면 첫 번째 가능한 슬롯에 배치 (간단화)
        if start_interval_index == -1:
            if item_start_min < time_intervals_minutes[0] and item_end_min > time_intervals_minutes[0]:
                start_interval_index = 0 # 9시 이전 시작이면 9시에 걸침
            # else: continue # 범위 밖이면 무시 (또는 다른 처리)

        if start_interval_index != -1 and start_interval_index < len(time_intervals_display):
            start_time_str = time_intervals_display[start_interval_index]
            if schedule_grid.get(start_time_str, {}).get(day) is None: # 해당 슬롯이 비어있는 경우에만
                schedule_grid[start_time_str][day] = item
                for r_idx in range(1, item['rowspan']):
                    covered_interval_index = start_interval_index + r_idx
                    if covered_interval_index < len(time_intervals_display):
                        covered_time_str = time_intervals_display[covered_interval_index]
                        if day in schedule_grid[covered_time_str]:
                            schedule_grid[covered_time_str][day] = "covered"

    return render_template("full_schedule.html",
                           schedule_grid=schedule_grid,
                           time_intervals=time_intervals_display,
                           days_of_week=DAYS_ORDER)


if __name__ == "__main__": #
    app.run(debug=True) #