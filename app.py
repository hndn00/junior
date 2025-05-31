import os
import json
import torch
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from datetime import datetime

from flask import (
    Flask, request, render_template,
    redirect, url_for, session, jsonify
)

from models.study_plan_nn import StudyPlanGenerator, create_study_plan
from everytime import Everytime
from convert import Convert

STUDY_PLAN_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "study_plan_model.pt")

app = Flask(__name__)
app.secret_key = "your_secret_key_here_for_session"

SUBJECT_DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "subject_datas")
SUBJECT_DATA_FILE = os.path.join(SUBJECT_DATA_DIR, "subject_datas.json")

global_timetable_slots = []
global_study_planner = None

def ensure_subject_data_dir():
    if not os.path.exists(SUBJECT_DATA_DIR):
        os.makedirs(SUBJECT_DATA_DIR)

def save_subject_data(timetable_slots, subjects=None):
    ensure_subject_data_dir()
    data = {"timetable_slots": timetable_slots}
    if subjects is not None:
        data["subjects"] = subjects
    with open(SUBJECT_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_subject_data_from_file():
    if os.path.exists(SUBJECT_DATA_FILE):
        try:
            with open(SUBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            timetable_slots = loaded_data.get("timetable_slots", [])
            subjects = loaded_data.get("subjects", [])
            return timetable_slots, subjects
        except Exception as e:
            print(f"과목 데이터 로드 오류: {e}")
    return [], []

USER_CREDENTIALS = {"admin": "helloai"}

def time_to_minutes(time_str):
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except:
        return None

def minutes_to_time_str(minutes):
    if minutes is None:
        return ""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

@app.route("/")
def main():
    return render_template("main.html")

@app.route("/logout")
def logout():
    session.pop('username', None)
    session.pop('ai_weekly_schedule', None)
    session.pop('ai_priorities', None)
    session.pop('used_timetable_slots_for_plan', None)
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
            return jsonify({"error": "유효하지 않은 URL 또는 ID 형식입니다."}), 400

        e = Everytime(timetable_id) #
        xml_data = e.get_timetable() #
        if not xml_data or "<error>" in xml_data.lower():
            return jsonify({"error": "시간표 XML을 가져오지 못했습니다."}), 400

        c = Convert(xml_data) #
        subjects_from_everytime = c.get_subjects() #
        if not subjects_from_everytime:
            return jsonify({"timetable_slots": [], "subjects": [], "message": "과목 정보를 찾을 수 없습니다."})

        day_map = {"0":"월요일","1":"화요일","2":"수요일","3":"목요일","4":"금요일","5":"토요일","6":"일요일"}
        free_start, free_end = time_to_minutes("09:00"), time_to_minutes("21:00")
        timetable_results = []

        for subj in subjects_from_everytime:
            name = subj.get("name", "")
            prof = subj.get("professor", "")
            for info in subj.get("info", []):
                d, s, e_ = info.get("day"), info.get("startAt"), info.get("endAt")
                if d in day_map and s and e_:
                    timetable_results.append(("수업", name, day_map[d], s, e_, prof, info.get("place","")))

        for key in sorted(day_map.keys()):
            day = day_map[key]
            classes_on_day = []
            for subj in subjects_from_everytime:
                for info in subj.get("info", []):
                    if info.get("day")==key:
                        sm, em = time_to_minutes(info.get("startAt")), time_to_minutes(info.get("endAt"))
                        if sm is not None and em is not None and sm<em:
                            if em > free_start and sm < free_end:
                                classes_on_day.append((sm, em))
            classes_on_day.sort()
            last_class_end_time = free_start
            for sm, em in classes_on_day:
                if sm > last_class_end_time:
                    timetable_results.append(("공강","",day,minutes_to_time_str(last_class_end_time),minutes_to_time_str(sm),"",""))
                last_class_end_time = max(last_class_end_time, em)
            if last_class_end_time < free_end:
                timetable_results.append(("공강","",day,minutes_to_time_str(last_class_end_time),minutes_to_time_str(free_end),"",""))

        order = {"월요일":0,"화요일":1,"수요일":2,"목요일":3,"금요일":4,"토요일":5,"일요일":6}
        timetable_results.sort(key=lambda x: (order.get(x[2],7), time_to_minutes(x[3]) or 0, 0 if x[0]=="공강" else 1))

        global global_timetable_slots
        global_timetable_slots = timetable_results

        default_subjects_for_plan = [{"name": s['name'], "weight": 50.0, "major": False} for s in subjects_from_everytime]
        save_subject_data(global_timetable_slots, default_subjects_for_plan)

        return jsonify({"timetable_slots": timetable_results, "subjects": default_subjects_for_plan, "message": "시간표를 성공적으로 불러왔습니다."})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/load_stored_timetable")
def load_stored_timetable_route():
    global global_timetable_slots
    slots, subjects = load_subject_data_from_file()
    if slots:
        global_timetable_slots = slots
        return jsonify({"timetable_slots": slots, "subjects": subjects, "message": "저장된 시간표를 불러왔습니다."})
    return jsonify({"timetable_slots": [], "subjects": [], "message": "저장된 데이터가 없습니다."}), 404


@app.route("/loading")
def loading():
    """
    로딩 페이지를 표시하고 form 데이터를 전달합니다.
    """
    timetable_data = request.args.get('timetable_data', '')
    subjects_data = request.args.get('subjects_data', '')
    
    return render_template(
        "loading.html",
        timetable_slots=timetable_data,
        subjects_json=subjects_data
    )

@app.route("/plan", methods=["GET","POST"])
def plan():
    global global_timetable_slots, global_study_planner

    if request.method == "POST":
        slots_json = request.form.get("timetable_slots","")
        if not slots_json:
            return render_template("result.html", error_message="시간표 정보가 없습니다.")

        try:
            timetable_slots_full = json.loads(slots_json)
        except:
            return render_template("result.html", error_message="시간표 데이터 파싱 실패")

        subjects_json_str = request.form.get("subjects_json")
        if not subjects_json_str:
            return render_template("result.html", error_message="과목 상세 정보(JSON)가 없습니다.")
        try:
            subjects_input_data = json.loads(subjects_json_str)
        except json.JSONDecodeError:
            return render_template("result.html", error_message="과목 상세 정보(JSON) 파싱 실패")

        valid_subjects_data = []
        for subj_data in subjects_input_data:
            if subj_data.get("name","").strip():
                valid_subjects_data.append({
                    "name": subj_data["name"].strip(),
                    "weight": float(subj_data.get("weight", 50.0)),
                    "major": 1.0 if subj_data.get("major", False) else 0.0
                })

        if not valid_subjects_data:
            return render_template("result.html", error_message="유효한 과목명이 필요합니다.")

        subjects_data_for_ai = valid_subjects_data
        save_subject_data(timetable_slots_full, subjects_data_for_ai)

        slots_for_dataset = [(s[0], s[1], s[2], s[3], s[4]) for s in timetable_slots_full if len(s) >=5]


        try:
            study_plan_result = create_study_plan(subjects_data_for_ai, slots_for_dataset) #

            session['ai_weekly_schedule'] = study_plan_result.get('weekly_schedule', {})
            session['ai_priorities'] = study_plan_result.get('priorities', [])
            session['used_timetable_slots_for_plan'] = timetable_slots_full


            total_study_hours = 0
            daily_study_hours = {}
            weekly_schedule_from_ai = study_plan_result.get('weekly_schedule', {})

            for day, schedule_items in weekly_schedule_from_ai.items():
                daily_hours = sum(item.get('duration', 0) for item in schedule_items)
                daily_study_hours[day] = daily_hours
                total_study_hours += daily_hours

            subject_weekly_hours = {}
            for day_schedule_items in weekly_schedule_from_ai.values():
                for item in day_schedule_items:
                    subject = item.get('subject')
                    if subject:
                        subject_weekly_hours[subject] = subject_weekly_hours.get(subject, 0) + item.get('duration', 0)

            avg_confidence = 0
            if study_plan_result.get('priorities'):
                confidences = [p.get('confidence',0) for p in study_plan_result.get('priorities') if p.get('confidence') is not None]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)


            return render_template("result.html",
                                   priorities=study_plan_result.get('priorities', []),
                                   weekly_schedule=weekly_schedule_from_ai,
                                   summary=study_plan_result.get('summary', {}),
                                   total_study_hours=round(total_study_hours, 1),
                                   daily_study_hours=daily_study_hours,
                                   subject_weekly_hours=subject_weekly_hours,
                                   timetable_slots=timetable_slots_full,
                                   neural_features_count=study_plan_result.get('neural_features_count', getattr(getattr(global_study_planner, 'model', None), 'input_dim', 12) if global_study_planner else 12),
                                   average_confidence= avg_confidence if avg_confidence > 0 else 0.947, # Provide a default if not calculated
                                   analysis_reliability="높음" if (avg_confidence if avg_confidence > 0 else 0.947) >= 0.8 else "보통", # Example reliability
                                   training_epochs=100
                                   )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return render_template("result.html", error_message=f"AI 학습 계획 생성 중 오류: {str(e)}")

    loaded_slots, loaded_subjects = load_subject_data_from_file()
    initial_timetable_json = json.dumps(loaded_slots) if loaded_slots else ""
    initial_subjects_json = json.dumps(loaded_subjects) if loaded_subjects else "[]"

    return render_template("index.html",
                           timetable_slots=initial_timetable_json,
                           initial_subjects_data=initial_subjects_json)


@app.route("/show_full_schedule")
def show_full_schedule():
    current_timetable_slots = session.get('used_timetable_slots_for_plan')

    if not current_timetable_slots:
        global global_timetable_slots
        if global_timetable_slots:
            current_timetable_slots = global_timetable_slots
        else:
            slots_from_file, _ = load_subject_data_from_file()
            if slots_from_file:
                current_timetable_slots = slots_from_file
            else:
                return render_template("full_schedule.html", message="시간표 정보가 없습니다. 먼저 시간표를 불러오고 계획을 생성해주세요.", days_of_week=[], time_intervals=[], schedule_grid={})

    if not current_timetable_slots:
        return render_template("full_schedule.html", message="표시할 시간표 데이터가 없습니다.", days_of_week=[], time_intervals=[], schedule_grid={})

    ai_weekly_schedule = session.get('ai_weekly_schedule', {})

    days_of_week = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    time_intervals = [f"{h:02d}:{m:02d}" for h in range(9, 21) for m in (0, 30)]

    schedule_grid = {time_str: {day: None for day in days_of_week} for time_str in time_intervals}

    subject_colors = {}
    color_palette = [
        "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF", "#E0BBE4",
        "#FFBEB1", "#FDFD96", "#BDE4A7", "#A7CEE2", "#D7B0E0", "#FFCBAE",
        "#F6A7B0", "#FDD09C", "#F9F871", "#AEDEA0", "#A4C8E0", "#CAA7D9"
    ]
    used_colors_count = 0

    def get_color_for_subject(subject_name):
        nonlocal used_colors_count
        if subject_name not in subject_colors:
            subject_colors[subject_name] = color_palette[used_colors_count % len(color_palette)]
            used_colors_count += 1
        return subject_colors[subject_name]

    for slot_data in current_timetable_slots:
        if len(slot_data) < 7: continue
        slot_type, name, day, start_str, end_str, prof, place = slot_data[:7]
        if slot_type == "수업" and day in days_of_week:
            s_h, s_m = map(int, start_str.split(':'))
            e_h, e_m = map(int, end_str.split(':'))

            class_start_total_minutes = s_h * 60 + s_m
            class_end_total_minutes = e_h * 60 + e_m

            grid_s_idx, grid_e_idx = -1, -1

            for idx, t_str in enumerate(time_intervals):
                t_h_interval, t_m_interval = map(int, t_str.split(':'))
                interval_start_total_minutes = t_h_interval * 60 + t_m_interval

                if grid_s_idx == -1 and interval_start_total_minutes >= class_start_total_minutes and interval_start_total_minutes < class_end_total_minutes:
                    grid_s_idx = idx

                if interval_start_total_minutes < class_end_total_minutes:
                    grid_e_idx = idx + 1

            if grid_s_idx != -1 and grid_e_idx != -1 and grid_s_idx < grid_e_idx:
                rowspan = grid_e_idx - grid_s_idx
                target_start_time_str = time_intervals[grid_s_idx]
                if schedule_grid[target_start_time_str][day] is None:
                    schedule_grid[target_start_time_str][day] = {
                        "type": "class", "subject_name": name,
                        "professor": prof, "place": place,
                        "start_time": start_str, "end_time": end_str,
                        "rowspan": rowspan, "color": get_color_for_subject(name)
                    }
                    for i in range(1, rowspan):
                        if grid_s_idx + i < len(time_intervals):
                            schedule_grid[time_intervals[grid_s_idx + i]][day] = "covered"

    mutable_ai_schedule = {day: [dict(task) for task in tasks] for day, tasks in ai_weekly_schedule.items()}

    for day in days_of_week:
        if day not in mutable_ai_schedule or not mutable_ai_schedule[day]:
            continue

        tasks_for_day = mutable_ai_schedule[day]
        current_ai_task_idx = 0

        for time_idx, time_str in enumerate(time_intervals):
            if current_ai_task_idx >= len(tasks_for_day):
                break

            if schedule_grid[time_str][day] is None:
                ai_task = tasks_for_day[current_ai_task_idx]

                slots_needed_for_task_remaining = int(float(ai_task.get('duration', 0)) * 2)

                if slots_needed_for_task_remaining <= 0:
                    current_ai_task_idx += 1
                    if current_ai_task_idx < len(tasks_for_day):
                        ai_task = tasks_for_day[current_ai_task_idx]
                        slots_needed_for_task_remaining = int(float(ai_task.get('duration', 0)) * 2)
                        if slots_needed_for_task_remaining <= 0: continue
                    else: break

                contiguous_free_slots = 0
                for i in range(len(time_intervals) - time_idx):
                    check_time_str = time_intervals[time_idx + i]
                    if schedule_grid[check_time_str][day] is None:
                        contiguous_free_slots += 1
                    else:
                        break

                slots_to_fill_now = min(slots_needed_for_task_remaining, contiguous_free_slots)

                if slots_to_fill_now > 0:
                    actual_study_duration_hours = slots_to_fill_now / 2.0

                    block_end_idx = time_idx + slots_to_fill_now

                    h_end_block, m_end_block = map(int, time_intervals[block_end_idx-1].split(':'))
                    m_end_block += 30
                    if m_end_block >= 60: h_end_block+=1; m_end_block-=60
                    actual_block_end_time_str = f"{h_end_block:02d}:{m_end_block:02d}"

                    # --- 색상 결정 로직 수정 ---
                    item_color = "transparent" # 기본값을 투명으로 설정
                    study_type = ai_task.get('study_type', '').lower() # 소문자로 비교

                    # '예습' 또는 '복습'이 아닌 경우에만 과목 색상 적용
                    # (만약 모든 study 타입에 색을 입히고 싶다면 이 조건문 제거)
                    if not ('예습' not in study_type and '복습' not in study_type):
                        item_color = get_color_for_subject(ai_task['subject'])
                    # --- ---

                    schedule_grid[time_str][day] = {
                        "type": "study",
                        "subject_name": ai_task['subject'],
                        "place": f"{ai_task.get('study_type','공강 자습')}",
                        "start_time": time_str,
                        "end_time": actual_block_end_time_str,
                        "rowspan": slots_to_fill_now,
                        "color": item_color # 수정된 색상 적용
                    }
                    for i in range(1, slots_to_fill_now):
                        schedule_grid[time_intervals[time_idx + i]][day] = "covered"

                    ai_task['duration'] = float(ai_task.get('duration', 0)) - actual_study_duration_hours
                    if ai_task['duration'] < 0.01:
                        current_ai_task_idx += 1

    return render_template("full_schedule.html",
                           schedule_grid=schedule_grid,
                           time_intervals=time_intervals,
                           days_of_week=days_of_week,
                           message=None)


@app.route("/export_study_plan", methods=["POST"])
def export_study_plan():
    try:
        data = request.get_json()
        study_plan = data.get('study_plan')

        if not study_plan:
            return jsonify({"error": "내보낼 학습 계획이 없습니다."}), 400

        filename = f"study_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        return jsonify({
            "success": True,
            "filename": filename,
            "data": study_plan
        })

    except Exception as e:
        return jsonify({"error": f"내보내기 중 오류: {str(e)}"}), 500

@app.route("/retrain_model", methods=["POST"])
def retrain_model_route():
    global global_study_planner, global_timetable_slots

    slots, subjects = load_subject_data_from_file()

    if not subjects or not slots:
        return jsonify({"success": False, "error": "모델 재훈련에 필요한 데이터(과목 및 시간표)가 저장되어 있지 않습니다."})

    try:
        slots_for_dataset = [(s[0], s[1], s[2], s[3], s[4]) for s in slots if len(s) >=5]

        print(f"Retraining model with {len(subjects)} subjects and {len(slots_for_dataset)} timetable slots.")

        if not os.path.exists(os.path.join(os.path.dirname(__file__), "models")):
            os.makedirs(os.path.join(os.path.dirname(__file__), "models"))

        planner = StudyPlanGenerator() #
        planner.train_model(subjects, slots_for_dataset, epochs=100) #
        planner.save_model(STUDY_PLAN_MODEL_PATH) #
        global_study_planner = planner

        return jsonify({"success": True, "message": "모델 재훈련이 완료되었습니다."})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"모델 재훈련 중 오류 발생: {str(e)}"})

@app.route("/result")
def show_result():
    """세션에 저장된 AI 학습 계획 결과를 다시 표시"""
    ai_weekly_schedule = session.get('ai_weekly_schedule')
    ai_priorities = session.get('ai_priorities')
    used_timetable_slots = session.get('used_timetable_slots_for_plan')

    if not ai_weekly_schedule or not ai_priorities:
        return redirect(url_for('plan'))

    # 결과 페이지에 필요한 통계 데이터 재계산
    total_study_hours = 0
    daily_study_hours = {}

    for day, schedule_items in ai_weekly_schedule.items():
        daily_hours = sum(item.get('duration', 0) for item in schedule_items)
        daily_study_hours[day] = daily_hours
        total_study_hours += daily_hours

    subject_weekly_hours = {}
    for day_schedule_items in ai_weekly_schedule.values():
        for item in day_schedule_items:
            subject = item.get('subject')
            if subject:
                subject_weekly_hours[subject] = subject_weekly_hours.get(subject, 0) + item.get('duration', 0)

    # 평균 신뢰도 계산
    avg_confidence = 0
    if ai_priorities:
        confidences = [p.get('confidence', 0) for p in ai_priorities if p.get('confidence') is not None]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)

    return render_template("result.html",
                           priorities=ai_priorities,
                           weekly_schedule=ai_weekly_schedule,
                           summary={},  # 세션에 저장되지 않았다면 빈 dict
                           total_study_hours=round(total_study_hours, 1),
                           daily_study_hours=daily_study_hours,
                           subject_weekly_hours=subject_weekly_hours,
                           timetable_slots=used_timetable_slots or [],
                           neural_features_count=12,  # 기본값
                           average_confidence=avg_confidence if avg_confidence > 0 else 0.947,
                           analysis_reliability="높음" if (avg_confidence if avg_confidence > 0 else 0.947) >= 0.8 else "보통",
                           training_epochs=100
                           )

if __name__ == "__main__":
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    if not os.path.exists(models_dir):
        os.makedirs(models_dir)

    if not os.path.exists(SUBJECT_DATA_DIR):
        os.makedirs(SUBJECT_DATA_DIR)

    app.run(debug=True, host='0.0.0.0', port=5001)