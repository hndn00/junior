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
        weights = [float(w) if w else 1.0 for w in raw_ws]
        majors = [1.0 if v=="on" else 0.0 for v in request.form.getlist("major")]
        majors += [0.0] * (len(weights)-len(majors))

        valid = [i for i,n in enumerate(names) if n.strip()]
        if not valid:
            return render_template("result.html", error_message="유효한 과목명이 필요합니다.")

        names = [names[i] for i in valid]
        weights = [weights[i] for i in valid]
        majors = [majors[i] for i in valid]

        # 과목 데이터 준비
        subjects_data = []
        for n, w, m in zip(names, weights, majors):
            subjects_data.append({
                "name": n,
                "weight": w,
                "major": m
            })

        # 시간표 슬롯 데이터 준비 (신경망용)
        slots_for_dataset = [(s[0], s[1], s[2], s[3], s[4]) for s in timetable_slots_full]

        try:
            # 학습 계획 생성 (신경망 사용)
            print("AI 학습 계획 생성 중...")
            study_plan_result = create_study_plan(subjects_data, slots_for_dataset)

            # 결과 데이터 준비
            priorities = study_plan_result['priorities']
            weekly_schedule = study_plan_result['weekly_schedule']
            summary = study_plan_result['summary']

            # 학습 시간 통계 계산
            total_study_hours = 0
            daily_study_hours = {}

            for day, schedule in weekly_schedule.items():
                daily_hours = sum(item['duration'] for item in schedule)
                daily_study_hours[day] = daily_hours
                total_study_hours += daily_hours

            # 과목별 주간 학습 시간 계산
            subject_weekly_hours = {}
            for day_schedule in weekly_schedule.values():
                for item in day_schedule:
                    subject = item['subject']
                    if subject not in subject_weekly_hours:
                        subject_weekly_hours[subject] = 0
                    subject_weekly_hours[subject] += item['duration']

            # 결과 렌더링
            return render_template("result.html",
                                   priorities=priorities,
                                   weekly_schedule=weekly_schedule,
                                   summary=summary,
                                   total_study_hours=round(total_study_hours, 1),
                                   daily_study_hours=daily_study_hours,
                                   subject_weekly_hours=subject_weekly_hours,
                                   timetable_slots=timetable_slots_full)

        except Exception as e:
            return render_template("result.html", error_message=f"AI 학습 계획 생성 중 오류: {str(e)}")

    return render_template("index.html", timetable_slots="")

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