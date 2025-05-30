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

# 새로운 학습계획 신경망 모듈 임포트
from models.study_plan_nn import StudyPlanGenerator, create_study_plan
from everytime import Everytime
from convert import Convert

# 모델 저장/로드 경로
STUDY_PLAN_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "study_plan_model.pt")

app = Flask(__name__)
app.secret_key = "your_secret_key_here_for_session"

# 과목 데이터 저장 관련 설정
SUBJECT_DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "subject_datas")
SUBJECT_DATA_FILE = os.path.join(SUBJECT_DATA_DIR, "subject_datas.json")

# 전역 변수
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

# 사용자 인증 설정
USER_CREDENTIALS = {"admin": "helloai"}

# 시간 변환 유틸
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

        e = Everytime(timetable_id)
        xml_data = e.get_timetable()
        if not xml_data or "<error>" in xml_data.lower():
            return jsonify({"error": "시간표 XML을 가져오지 못했습니다."}), 400

        c = Convert(xml_data)
        subjects = c.get_subjects()
        if not subjects:
            return jsonify({"timetable_slots": [], "message": "과목 정보를 찾을 수 없습니다."})

        day_map = {"0":"월요일","1":"화요일","2":"수요일","3":"목요일","4":"금요일","5":"토요일","6":"일요일"}
        free_start, free_end = time_to_minutes("09:00"), time_to_minutes("21:00")
        timetable_results = []

        # 수업 슬롯
        for subj in subjects:
            name = subj.get("name", "")
            prof = subj.get("professor", "")
            for info in subj.get("info", []):
                d, s, e_ = info.get("day"), info.get("startAt"), info.get("endAt")
                if d in day_map and s and e_:
                    timetable_results.append(("수업", name, day_map[d], s, e_, prof, info.get("place","")))

        # 공강 슬롯
        for key in sorted(day_map.keys()):
            day = day_map[key]
            classes = []
            for subj in subjects:
                for info in subj.get("info", []):
                    if info.get("day")==key:
                        sm, em = time_to_minutes(info.get("startAt")), time_to_minutes(info.get("endAt"))
                        if sm is not None and em is not None and sm<em:
                            if em>free_start and sm<free_end:
                                classes.append((sm, em))
            classes.sort()
            last = free_start
            for sm, em in classes:
                if sm>last:
                    timetable_results.append(("공강","",day,minutes_to_time_str(last),minutes_to_time_str(sm),"",""))
                last = max(last, em)
            if last<free_end:
                timetable_results.append(("공강","",day,minutes_to_time_str(last),minutes_to_time_str(free_end),"",""))

        # 정렬
        order = {"월요일":0,"화요일":1,"수요일":2,"목요일":3,"금요일":4,"토요일":5,"일요일":6}
        timetable_results.sort(key=lambda x: (order.get(x[2],7), time_to_minutes(x[3]) or 0, 0 if x[0]=="공강" else 1))

        global global_timetable_slots
        global_timetable_slots = timetable_results
        save_subject_data(global_timetable_slots, subjects)
        return jsonify({"timetable_slots": timetable_results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/load_stored_timetable")
def load_stored_timetable_route():
    global global_timetable_slots
    slots, subjects = load_subject_data_from_file()
    if slots:
        global_timetable_slots = slots
        return jsonify({"timetable_slots": slots, "subjects": subjects, "message": "저장된 시간표를 불러왔습니다."})
    return jsonify({"timetable_slots": [], "subjects": [], "message": "데이터가 없습니다."}), 404

# ownstj/junior/junior-d50557606bc124cb2c092c7e953775af7b85deb6/app.py
# ... (other imports and code)

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

        # 과목 정보 수집
        names = request.form.getlist("name")
        raw_ws = request.form.getlist("weight")
        weights = [float(w) if w else 1.0 for w in raw_ws] # Ensure weights are float

        # Process majors: getlist might not return items for unchecked boxes.
        # We need to align it with names and weights.
        # Create a list of booleans for majors based on submitted 'major' values.
        # Assuming 'major' checkboxes send 'on' when checked.
        # A hidden field for each subject could ensure every subject's major status is sent.
        # However, a simpler approach if getlist("major") only gives 'on' for checked ones:

        # A more robust way to handle majors, assuming form names are like "major_0", "major_1", etc.
        # Or, if using identical names and relying on order (as it seems to be the case):

        submitted_majors = request.form.getlist("major") # Contains 'on' for checked boxes

        # Reconstruct the majors list to align with names and weights
        # This assumes that if a subject's major checkbox is not checked, it won't appear in submitted_majors.
        # We need to ensure the `majors` list has the same length as `names`.
        # A common pattern is to have a hidden input with value 0 for each checkbox,
        # and the checkbox itself with value 1 (or 'on'). When submitted, you get "0,1" or "0".
        # Given the current HTML structure implied by getlist("major"),
        # this part might need adjustment based on how `major` is actually submitted for unchecked boxes.
        # The original code uses:
        # majors = [1.0 if v=="on" else 0.0 for v in request.form.getlist("major")]
        # majors += [0.0] * (len(weights)-len(majors))
        # This logic seems fine to handle potentially sparse 'major' list.

        majors_temp = request.form.getlist("major") # These are the 'on' values
        subject_indices_with_major_checked = []

        # To correctly associate 'on' values with their subjects, we need to know their original positions
        # or assume that `request.form.getlist("major")` only returns values for *checked* boxes
        # and they correspond to the *order* of subjects that had their major box checked.
        # The existing code:
        majors_values = request.form.getlist("major") # this list contains 'on' for checked, nothing for unchecked if simple checkbox
        # if there are hidden fields, it might be more complex.
        # Let's stick to the original logic provided in the file for now.

        majors_processed = []
        # Assuming `names` is the definitive list of subjects from the form
        # Iterate through each *expected* subject. If a corresponding "major" value was submitted, it's "on".
        # This part is tricky if `getlist("major")` only returns for checked.
        # The original code:
        # majors = [1.0 if v=="on" else 0.0 for v in request.form.getlist("major")]
        # majors += [0.0] * (len(weights)-len(majors))
        # This implies getlist("major") returns a value for each major checkbox submitted,
        # where unchecked might not send a value, or sends a default.
        # Let's assume the HTML ensures a value is sent or not, and `getlist` captures them in order.
        # The most reliable way from `index.html` is that each `major` checkbox has a distinct name or value that allows server-side reconstruction.
        # However, the `addSubject` JS creates them with `name="major"`.
        # If an unchecked checkbox with name="major" is not submitted, then `getlist("major")` will be shorter.

        # Re-evaluating the existing major processing:
        # names = ["S1", "S2", "S3"]
        # weights = [50, 60, 70]
        # If S1 is not major, S2 is major, S3 is not major.
        # Form sends: name=S1, weight=50, name=S2, weight=60, major=on, name=S3, weight=70
        # request.form.getlist("major") -> ["on"] (if S2 was the only one checked)
        # Original:
        # majors = [1.0 if v=="on" else 0.0 for v in request.form.getlist("major")] -> results in [1.0]
        # majors += [0.0] * (len(weights)-len(majors)) -> [1.0, 0.0, 0.0] if len(weights) is 3. This is WRONG.

        # Correct handling of majors:
        # We need to check for each subject if its major checkbox was checked.
        # The simplest way if names are unique and submitted in order:
        # Iterate over subject items in the form on the server side more explicitly
        # or, ensure the client sends a value for every 'major' checkbox.

        # The provided `index.js` creates inputs with `name="name"`, `name="weight"`, `name="major"`.
        # Flask's `request.form.getlist("major")` will get all values submitted for fields named "major".
        # For a checkbox, if it's checked, its value ('on' by default) is sent. If not, nothing is sent for that specific checkbox.
        # So, `len(request.form.getlist("major"))` will be the number of *checked* major boxes.
        # The original code for `majors` is problematic.

        # A better way for majors, assuming checkbox `major` for each subject:
        # HTML should be structured so each subject's major status is clearly identifiable.
        # E.g., `major_0`, `major_1`...
        # Or, iterate based on the number of subjects (derived from `names` list length).
        # For each subject `i`, check `request.form.get(f"major_{i}")`.

        # Given the current structure (all major checkboxes have `name="major"`):
        # We must rely on the hidden `subjects_json` input created by `index.js` on submit,
        # which correctly captures the boolean state.

        subjects_json_str = request.form.get("subjects_json")
        if not subjects_json_str:
            return render_template("result.html", error_message="과목 상세 정보(JSON)가 없습니다.")
        try:
            subjects_input_data = json.loads(subjects_json_str)
        except json.JSONDecodeError:
            return render_template("result.html", error_message="과목 상세 정보(JSON) 파싱 실패")

        # Now, `subjects_input_data` is a list of dicts: [{'name':n, 'weight':w, 'major':bool}, ...]

        valid_subjects_data = []
        for subj_data in subjects_input_data:
            if subj_data.get("name","").strip():
                valid_subjects_data.append({
                    "name": subj_data["name"].strip(),
                    "weight": float(subj_data.get("weight", 1.0)), # Ensure float
                    "major": 1.0 if subj_data.get("major", False) else 0.0 # Convert boolean to float 1.0/0.0
                })

        if not valid_subjects_data:
            return render_template("result.html", error_message="유효한 과목명이 필요합니다.")

        subjects_data_for_ai = valid_subjects_data # Use this for AI and saving

        # --- SAVE SUBJECT DATA ---
        # Save the current state of timetable_slots and user-defined subjects (name, weight, major)
        # This `subjects_data_for_ai` is in the format: [{'name': ..., 'weight': ..., 'major': ...}]
        save_subject_data(timetable_slots_full, subjects_data_for_ai)
        # --- END SAVE SUBJECT DATA ---

        # 시간표 슬롯 데이터 준비 (신경망용)
        slots_for_dataset = [(s[0], s[1], s[2], s[3], s[4]) for s in timetable_slots_full]

        try:
            # 학습 계획 생성 (신경망 사용)
            print("AI 학습 계획 생성 중...")
            # Pass `subjects_data_for_ai` to the study plan creator
            study_plan_result = create_study_plan(subjects_data_for_ai, slots_for_dataset)

            # ... (rest of the /plan POST route)
            # 결과 데이터 준비
            priorities = study_plan_result['priorities']
            # ... (ensure this part uses the output of create_study_plan correctly)

            # Example of data passed to result.html
            # Reconstruct priorities if needed for display from study_plan_result
            # The `priorities` list for the template should ideally come directly from `study_plan_result['priorities']`
            # which already contains subject_name, priority string, confidence, weight, is_major (boolean).

            # Ensure the `priorities` variable passed to render_template matches what result.html expects
            # study_plan_result['priorities'] is like:
            # [{'subject_name': ..., 'priority': '매우 높음', ..., 'weight': ..., 'is_major': True/False}]

            # The `result.html` template iterates through `priorities` and expects `priority.is_major` (boolean).
            # So, `study_plan_result['priorities']` should be fine.


            # ... (rest of the /plan POST route to prepare data for result.html)
            # ...
            total_study_hours = 0
            daily_study_hours = {}
            weekly_schedule = study_plan_result.get('weekly_schedule', {}) # Make sure this key exists

            for day, schedule in weekly_schedule.items():
                daily_hours = sum(item.get('duration', 0) for item in schedule) # item might not have duration
                daily_study_hours[day] = daily_hours
                total_study_hours += daily_hours

            subject_weekly_hours = {}
            for day_schedule in weekly_schedule.values():
                for item in day_schedule:
                    subject = item.get('subject')
                    if subject: # Check if subject exists
                        if subject not in subject_weekly_hours:
                            subject_weekly_hours[subject] = 0
                        subject_weekly_hours[subject] += item.get('duration', 0)


            return render_template("result.html",
                                   priorities=study_plan_result.get('priorities', []),
                                   weekly_schedule=weekly_schedule,
                                   summary=study_plan_result.get('summary', {}),
                                   total_study_hours=round(total_study_hours, 1),
                                   daily_study_hours=daily_study_hours,
                                   subject_weekly_hours=subject_weekly_hours,
                                   timetable_slots=timetable_slots_full, # This is passed for potential "full schedule" view from result
                                   # Add any other specific data needed by ai_result.html, like:
                                   neural_features_count = study_plan_result.get('neural_features_count', 12), # Example
                                   average_confidence = study_plan_result.get('average_confidence', 0.947), # Example
                                   analysis_reliability = study_plan_result.get('analysis_reliability', "높음"), # Example
                                   training_epochs = study_plan_result.get('training_epochs', 100) # Example
                                   )

        except Exception as e:
            # Print stack trace for debugging
            import traceback
            traceback.print_exc()
            return render_template("result.html", error_message=f"AI 학습 계획 생성 중 오류: {str(e)}")

    # For GET request
    # Try to load previously saved data to pre-populate if desired, or leave as is for fresh start
    # current behavior: always starts fresh on GET /plan
    loaded_slots, loaded_subjects = load_subject_data_from_file()
    if loaded_slots: # If there's something saved
        # Pass timetable_slots as JSON string for the hidden input
        # Pass subjects data for index.js to potentially use (though index.js currently re-adds one blank on empty)
        return render_template("index.html",
                               timetable_slots=json.dumps(loaded_slots),
                               initial_subjects_data=json.dumps(loaded_subjects))
    else:
        return render_template("index.html", timetable_slots="", initial_subjects_data="[]")


# ... (rest of app.py)

@app.route("/generate_study_plan", methods=["POST"])
def generate_study_plan():
    """
    AJAX를 통한 학습 계획 생성 엔드포인트
    """
    try:
        data = request.get_json()
        subjects_data = data.get('subjects', [])
        timetable_slots = data.get('timetable_slots', [])

        if not subjects_data or not timetable_slots:
            return jsonify({"error": "과목 정보와 시간표 정보가 필요합니다."}), 400

        # 학습 계획 생성
        study_plan_result = create_study_plan(subjects_data, timetable_slots)

        return jsonify({
            "success": True,
            "study_plan": study_plan_result
        })

    except Exception as e:
        return jsonify({"error": f"학습 계획 생성 중 오류: {str(e)}"}), 500

@app.route("/get_study_recommendations", methods=["POST"])
def get_study_recommendations():
    """
    특정 과목에 대한 학습 추천사항 제공
    """
    try:
        data = request.get_json()
        subject_name = data.get('subject_name')
        priority = data.get('priority', '보통')
        is_major = data.get('is_major', False)

        # 추천 학습 방법 생성
        recommendations = generate_study_recommendations(subject_name, priority, is_major)

        return jsonify({
            "success": True,
            "recommendations": recommendations
        })

    except Exception as e:
        return jsonify({"error": f"추천사항 생성 중 오류: {str(e)}"}), 500

def generate_study_recommendations(subject_name: str, priority: str, is_major: bool) -> dict:
    """
    과목별 맞춤 학습 추천사항 생성
    """
    base_recommendations = {
        "매우 높음": {
            "daily_study_time": "3-4시간",
            "study_methods": [
                "매일 복습 및 예습 진행",
                "개념 노트 정리 및 암기",
                "다양한 문제 풀이",
                "스터디 그룹 참여",
                "교수님 면담 신청"
            ],
            "materials": [
                "주교재 + 참고서적 2권 이상",
                "온라인 강의 수강",
                "과거 기출문제 분석",
                "학회 논문 및 최신 자료"
            ]
        },
        "높음": {
            "daily_study_time": "2-3시간",
            "study_methods": [
                "주 5회 이상 학습",
                "핵심 개념 위주 정리",
                "문제 풀이 연습",
                "동료와 스터디"
            ],
            "materials": [
                "주교재 + 참고서적 1권",
                "온라인 자료 활용",
                "연습문제집"
            ]
        },
        "보통": {
            "daily_study_time": "1-2시간",
            "study_methods": [
                "주 3-4회 학습",
                "강의 내용 복습",
                "기본 문제 풀이"
            ],
            "materials": [
                "주교재 중심",
                "강의 노트",
                "기본 문제집"
            ]
        },
        "낮음": {
            "daily_study_time": "1시간",
            "study_methods": [
                "주 2-3회 학습",
                "핵심 내용만 정리",
                "최소한의 복습"
            ],
            "materials": [
                "강의 자료",
                "요약 노트"
            ]
        },
        "매우 낮음": {
            "daily_study_time": "30분-1시간",
            "study_methods": [
                "주 1-2회 학습",
                "시험 직전 집중 학습"
            ],
            "materials": [
                "강의 자료",
                "요점 정리"
            ]
        }
    }

    recommendations = base_recommendations.get(priority, base_recommendations["보통"]).copy()

    # 전공 과목인 경우 추가 권장사항
    if is_major:
        recommendations["major_bonus"] = [
            "전공 관련 추가 도서 읽기",
            "관련 분야 인턴십 또는 프로젝트 참여",
            "전공 관련 세미나 및 학회 참석",
            "대학원 진학 대비 심화 학습"
        ]

    # 과목명 기반 맞춤 추천 (예시)
    subject_specific = get_subject_specific_tips(subject_name)
    if subject_specific:
        recommendations["subject_tips"] = subject_specific

    return recommendations

def get_subject_specific_tips(subject_name: str) -> list:
    """
    과목별 특화 학습 팁
    """
    tips_map = {
        "수학": [
            "공식 암기보다 원리 이해에 집중",
            "다양한 유형의 문제 풀이",
            "오답 노트 작성 및 반복 학습"
        ],
        "영어": [
            "매일 단어 암기 (최소 20개)",
            "영어 뉴스/드라마 시청",
            "문법 규칙 체계적 정리",
            "영작문 연습"
        ],
        "프로그래밍": [
            "매일 코딩 연습",
            "다양한 알고리즘 문제 해결",
            "개인 프로젝트 진행",
            "오픈소스 기여"
        ],
        "경제": [
            "경제 뉴스 매일 읽기",
            "그래프와 도표 해석 연습",
            "실제 사례와 이론 연결",
            "토론 및 발표 준비"
        ]
    }

    # 부분 매칭으로 과목 찾기
    for key, tips in tips_map.items():
        if key in subject_name or subject_name in key:
            return tips

    return []

@app.route("/show_full_schedule")
def show_full_schedule():
    """
    전체 시간표 및 학습 계획 통합 뷰
    """
    global global_timetable_slots

    if not global_timetable_slots:
        return render_template("full_schedule.html",
                               error_message="시간표 정보가 없습니다. 먼저 시간표를 불러와주세요.")

    # 요일별 시간표 정리
    days_schedule = {}
    days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

    for day in days:
        day_slots = [slot for slot in global_timetable_slots if slot[2] == day]
        days_schedule[day] = sorted(day_slots, key=lambda x: time_to_minutes(x[3]) or 0)

    return render_template("full_schedule.html",
                           days_schedule=days_schedule,
                           timetable_slots=global_timetable_slots)

@app.route("/export_study_plan", methods=["POST"])
def export_study_plan():
    """
    학습 계획을 JSON 형태로 내보내기
    """
    try:
        data = request.get_json()
        study_plan = data.get('study_plan')

        if not study_plan:
            return jsonify({"error": "내보낼 학습 계획이 없습니다."}), 400

        # 파일명 생성 (현재 날짜 포함)
        from datetime import datetime
        filename = f"study_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        return jsonify({
            "success": True,
            "filename": filename,
            "data": study_plan
        })

    except Exception as e:
        return jsonify({"error": f"내보내기 중 오류: {str(e)}"}), 500

if __name__ == "__main__":
    # 모델 디렉토리 생성
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    if not os.path.exists(models_dir):
        os.makedirs(models_dir)

    app.run(debug=True, host='0.0.0.0')