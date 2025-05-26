from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from urllib.parse import urlparse
import xml.etree.ElementTree as ElementTree
import requests
import json
import os

# everytime.py와 convert.py가 같은 디렉토리에 있다고 가정합니다.
from everytime import Everytime
from convert import Convert

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # 실제 사용 시 복잡한 키로 변경하세요

# 과목 데이터 저장 파일 경로
SUBJECT_DATA_FILE = 'subject_data.json'

# 간단한 사용자 인증 정보
USER_CREDENTIALS = {
    "admin": "helloai",  # 아이디: 비밀번호
}

# every2cal.py의 HH:MM을 분으로 변환하는 헬퍼 함수
def time_to_minutes(time_str):
    """HH:MM 형식의 시간 문자열을 자정으로부터의 분으로 변환합니다."""
    if not time_str or ':' not in time_str:
        return None
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except ValueError:
        return None

# every2cal.py의 분을 HH:MM으로 변환하는 헬퍼 함수
def minutes_to_time_str(minutes):
    """자정으로부터의 분을 HH:MM 형식의 시간 문자열로 변환합니다."""
    if minutes is None or minutes < 0:
        return "N/A"
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

# 첫 화면: main.html
@app.route("/")
def main():
    return render_template("main.html")

# 로그아웃 처리
@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for("login"))

# 로그인 처리 페이지
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            session['username'] = username
            return redirect(url_for("plan"))
        else:
            return render_template("login.html", error="Incorrect username or password.", username=username)
    return render_template("login.html", error=None, username="")

# 학습 플래너 페이지
@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
        # 기존 학습 플래너 계산 로직은 그대로 유지합니다.
        try:
            total_hours = float(request.form.get("total_hours"))
            names = request.form.getlist("name")
            weights = list(map(float, request.form.getlist("weight")))

            if len(names) == 0 or len(weights) == 0 or sum(weights) == 0:
                return "The input data is invalid. Please try again."

            total_weight = sum(weights)

            def convert_to_hours_minutes(decimal_hours):
                hours = int(decimal_hours)
                minutes = int((decimal_hours - hours) * 60)
                return hours, minutes

            results = []
            for name, weight in zip(names, weights):
                decimal_hours = (weight / total_weight) * total_hours
                hours, minutes = convert_to_hours_minutes(decimal_hours)
                results.append((name, hours, minutes))

            return render_template("result.html", results=results)
        except Exception as e:
            return f"An error has occurred: {e}"

    return render_template("index.html")


@app.route("/process_timetable", methods=["POST"])
def process_timetable():
    timetable_url = request.form.get("new_url")
    if not timetable_url:
        error_response = {"error": "URL이 필요합니다."}
        print("Responding with error:", error_response) # 콘솔 로그 추가
        return error_response, 400

    timetable_id = ""
    xml_data = "" # xml_data를 try 블록 외부에서 초기화
    try:
        parsed_url = urlparse(timetable_url)
        if parsed_url.netloc == "everytime.kr" and parsed_url.path and parsed_url.path.startswith("/@"):
            timetable_id = parsed_url.path.split('/@')[-1]
        elif not parsed_url.scheme and not parsed_url.netloc and timetable_url: # 아마도 raw ID일 경우
            timetable_id = timetable_url

        if not timetable_id:
            error_response = {"error": "유효하지 않은 에브리타임 URL 또는 ID 형식입니다."}
            print("Responding with error:", error_response) # 콘솔 로그 추가
            return error_response, 400

        # 1. 에브리타임에서 XML 데이터 가져오기
        e = Everytime(timetable_id)
        xml_data = e.get_timetable()

        if not xml_data or "<error>" in xml_data.lower() or "<code>-1</code>" in xml_data.lower():
            app.logger.warning(f"ID {timetable_id}에 대한 유효한 시간표 XML을 가져오지 못했습니다. 응답: {xml_data[:200]}")
            error_response = {"error": "시간표 XML을 가져오지 못했습니다. ID가 잘못되었거나 시간표가 비공개 또는 비어있을 수 있습니다."}
            print("Responding with error:", error_response) # 콘솔 로그 추가
            return error_response, 400


        # 2. Convert 클래스를 사용하여 과목 가져오기
        c = Convert(xml_data)
        subjects = c.get_subjects()

        if not subjects:
            response_data = {"timetable_slots": [], "message": "시간표에서 과목 정보를 찾을 수 없습니다."}
            print("Responding with:", response_data) # 콘솔 로그 추가
            return response_data

        # 3. 수업 시간 및 공강 시간 계산
        day_map = {
            "0": "월요일", "1": "화요일", "2": "수요일", "3": "목요일",
            "4": "금요일", "5": "토요일", "6": "일요일"
        }
        free_slot_calc_start_minutes = time_to_minutes("09:00")
        free_slot_calc_end_minutes = time_to_minutes("21:00")

        timetable_results = []

        for subject in subjects:
            subject_name = subject.get("name", "N/A")
            for session_info in subject.get("info", []):
                day_numeric = session_info.get("day")
                start_time_str = session_info.get("startAt")
                end_time_str = session_info.get("endAt")

                if day_numeric in day_map and start_time_str and end_time_str:
                    if time_to_minutes(start_time_str) is not None and time_to_minutes(end_time_str) is not None:
                        timetable_results.append(
                            ("수업", subject_name, day_map[day_numeric], start_time_str, end_time_str)
                        )

        for day_numeric_str in sorted(day_map.keys()):
            day_name = day_map[day_numeric_str]

            todays_relevant_classes = []
            for subject_details in subjects:
                for session_info in subject_details.get("info", []):
                    if session_info.get("day") == day_numeric_str:
                        s_mins = time_to_minutes(session_info.get("startAt"))
                        e_mins = time_to_minutes(session_info.get("endAt"))
                        if s_mins is not None and e_mins is not None and s_mins < e_mins:
                            if e_mins > free_slot_calc_start_minutes and s_mins < free_slot_calc_end_minutes:
                                todays_relevant_classes.append((s_mins, e_mins))

            todays_relevant_classes.sort(key=lambda x: x[0])

            last_class_end_processed_minutes = free_slot_calc_start_minutes

            if not todays_relevant_classes:
                if free_slot_calc_end_minutes > free_slot_calc_start_minutes:
                    start_str = minutes_to_time_str(free_slot_calc_start_minutes)
                    end_str = minutes_to_time_str(free_slot_calc_end_minutes)
                    timetable_results.append(("공강", "", day_name, start_str, end_str))
            else:
                for class_start_minutes, class_end_minutes in todays_relevant_classes:
                    effective_class_segment_start = max(class_start_minutes, free_slot_calc_start_minutes)
                    effective_class_segment_end = min(class_end_minutes, free_slot_calc_end_minutes)

                    if effective_class_segment_start > last_class_end_processed_minutes:
                        start_str = minutes_to_time_str(last_class_end_processed_minutes)
                        end_str = minutes_to_time_str(effective_class_segment_start)
                        timetable_results.append(("공강", "", day_name, start_str, end_str))

                    last_class_end_processed_minutes = max(last_class_end_processed_minutes, effective_class_segment_end)

                if last_class_end_processed_minutes < free_slot_calc_end_minutes:
                    start_str = minutes_to_time_str(last_class_end_processed_minutes)
                    end_str = minutes_to_time_str(free_slot_calc_end_minutes)
                    timetable_results.append(("공강", "", day_name, start_str, end_str))

        def sort_key_final(item_tuple):
            type_val, name_val, day_name_val, start_str_val, end_str_val = item_tuple
            day_order = {"월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4, "토요일": 5, "일요일": 6}
            day_idx = day_order.get(day_name_val, 7)
            start_minutes_val = time_to_minutes(start_str_val)
            if start_minutes_val is None: start_minutes_val = float('inf')
            type_order = 0 if type_val == "공강" else 1
            return (day_idx, start_minutes_val, type_order)

        timetable_results.sort(key=sort_key_final)

        response_data = {"timetable_slots": timetable_results}
        print("Responding with:", response_data) # 콘솔 로그 추가
        return response_data

    except ElementTree.ParseError as e_xml:
        app.logger.error(f"ID {timetable_id}에 대한 XML 파싱 오류: {e_xml}\nXML 데이터: {xml_data[:500]}")
        error_response = {"error": "에브리타임의 XML 데이터가 유효하지 않습니다. 시간표가 비어 있거나 형식이 잘못되었을 수 있습니다."}
        print("Responding with error:", error_response) # 콘솔 로그 추가
        return error_response, 500
    except requests.exceptions.RequestException as e_req:
        app.logger.error(f"ID {timetable_id} 시간표 가져오기 네트워크 오류: {e_req}")
        error_response = {"error": f"시간표 가져오기 네트워크 오류: {str(e_req)}"}
        print("Responding with error:", error_response) # 콘솔 로그 추가
        return error_response, 500
    except Exception as e_generic:
        app.logger.error(f"ID {timetable_id} 시간표 처리 중 오류 발생: {e_generic}", exc_info=True)
        error_response = {"error": f"예상치 못한 오류가 발생했습니다: {str(e_generic)}"}
        print("Responding with error:", error_response) # 콘솔 로그 추가
        return error_response, 500


# 과목 데이터 저장 엔드포인트
@app.route("/save_subject_data", methods=["POST"])
def save_subject_data():
    try:
        data = request.get_json()
        
        # 로그인한 사용자 확인
        username = session.get('username')
        if not username:
            return jsonify({"error": "로그인이 필요합니다."}), 401
        
        # 데이터 검증 - 이제 데이터는 {subjects: [...], totalHours: "..."}와 같은 형태
        if not isinstance(data, dict) or not isinstance(data.get('subjects', []), list):
            return jsonify({"error": "잘못된 데이터 형식입니다."}), 400
        
        # 기존 데이터 파일 읽기
        all_data = {}
        if os.path.exists(SUBJECT_DATA_FILE):
            try:
                with open(SUBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
            except json.JSONDecodeError:
                all_data = {}
        
        # 현재 사용자의 데이터 업데이트
        all_data[username] = data
        
        # 파일에 저장
        with open(SUBJECT_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True, "message": "과목 데이터가 성공적으로 저장되었습니다."})
    
    except Exception as e:
        app.logger.error(f"과목 데이터 저장 중 오류 발생: {str(e)}", exc_info=True)
        return jsonify({"error": f"데이터 저장 중 오류가 발생했습니다: {str(e)}"}), 500

# 과목 데이터 불러오기 엔드포인트
@app.route("/load_subject_data", methods=["GET"])
def load_subject_data():
    try:
        # 로그인한 사용자 확인
        username = session.get('username')
        if not username:
            return jsonify({"error": "로그인이 필요합니다."}), 401
        
        # 데이터 파일이 없는 경우 빈 배열 반환
        if not os.path.exists(SUBJECT_DATA_FILE):
            return jsonify({"data": []})
        
        # 데이터 파일 읽기
        try:
            with open(SUBJECT_DATA_FILE, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
                user_data = all_data.get(username, [])
                return jsonify({"data": user_data})
        except json.JSONDecodeError:
            return jsonify({"error": "데이터 파일이 손상되었습니다."}), 500
    
    except Exception as e:
        app.logger.error(f"과목 데이터 불러오기 중 오류 발생: {str(e)}", exc_info=True)
        return jsonify({"error": f"데이터 불러오기 중 오류가 발생했습니다: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)