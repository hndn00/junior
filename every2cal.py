import everytime

__author__ = "Hoseong Son <me@sookcha.com>"

import argparse
import os

from convert import Convert


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, help="Everytime timetable id", required=False)
    parser.add_argument("--xml", type=str, help="Location of timetable xml file", required=False)
    parser.add_argument("--begin", type=str, help="Semester beginning date", required=True)
    parser.add_argument("--end", type=str, help="Semester ending date", required=True)
    parser.add_argument("--output", type=str, help="Output file path", required=False)
    parser.add_argument("--hide-details", action="store_true", help="Hide subject name", required=False)
    args = parser.parse_args()

    xml_input = "" # Renamed to avoid conflict with the module name
    if (args.xml):
        xml_input = args.xml
    else:
        path = args.id if (args.id) else input('Everytime 시간표 공유 URL의 ID를 입력하세요 (예: https://everytime.kr/@ABCDEF -> ABCDEF): ')
        
        e = everytime.Everytime(path)
        xml_input = e.get_timetable()
        if not xml_input:
            print("시간표 XML 데이터를 가져오는데 실패했습니다. ID를 확인해주세요.")
            return

    c = Convert(xml_input)
    subjects = c.get_subjects()

    # --- 기존 시간표 정보 출력 코드 ---
    print("\n--- 변환된 시간표 정보 ---")
    if not subjects:
        print("처리할 과목 정보가 없습니다.")
    else:
        day_map = {
            "0": "월요일", "1": "화요일", "2": "수요일", "3": "목요일",
            "4": "금요일", "5": "토요일", "6": "일요일"
        }
        for subject in subjects:
            subject_name = subject.get("name", "이름 없음")
            professor_name = subject.get("professor", "교수 정보 없음")
            print(f"\n과목: {subject_name} (교수: {professor_name})")
            if not subject.get("info"):
                print("  이 과목에 대한 시간 정보가 없습니다.")
                continue
            for session_info in subject["info"]:
                day_numeric = session_info.get("day", "요일 정보 없음")
                day_str = day_map.get(day_numeric, f"알 수 없는 요일 코드({day_numeric})")
                start_time = session_info.get("startAt", "시작 시간 없음")
                end_time = session_info.get("endAt", "종료 시간 없음")
                place = session_info.get("place", "장소 정보 없음")
                print(f"  - 요일: {day_str}")
                print(f"    시작 시간: {start_time}")
                print(f"    종료 시간: {end_time}")
                print(f"    장소: {place}")
    print("--- 시간표 정보 출력 완료 ---\n")

    # --- 공강 시간 계산 및 출력 코드 시작 ---
    print("\n--- 일일 공강 시간 (오전 9시 - 오후 9시) ---")

    def time_to_minutes(time_str):
        """HH:MM 형식의 시간 문자열을 자정으로부터의 분으로 변환합니다."""
        if not time_str or ':' not in time_str:
            return None
        try:
            h, m = map(int, time_str.split(':'))
            return h * 60 + m
        except ValueError:
            return None

    def minutes_to_time_str(minutes):
        """자정으로부터의 분을 HH:MM 형식의 시간 문자열로 변환합니다."""
        if minutes is None or minutes < 0: # 음수 분 처리 추가
            return "N/A"
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"

    daily_schedule = {} # key: day_numeric (str), value: list of (start_minutes, end_minutes)

    if subjects:
        for subject in subjects:
            if not subject.get("info"):
                continue
            for session_info in subject["info"]:
                day_numeric = session_info.get("day")
                start_time_str = session_info.get("startAt")
                end_time_str = session_info.get("endAt")

                if not day_numeric or not start_time_str or not end_time_str:
                    continue 

                start_minutes = time_to_minutes(start_time_str)
                end_minutes = time_to_minutes(end_time_str)

                if start_minutes is None or end_minutes is None or start_minutes >= end_minutes: # 종료 시간이 시작 시간보다 빠르거나 같은 경우 제외
                    # day_map은 이전에 정의되었으므로 여기서 직접 사용 가능
                    print(f"  경고: 과목 '{subject.get('name', 'N/A')}'의 '{day_map.get(day_numeric, day_numeric)}' 시간 형식 또는 순서 오류 ('{start_time_str}' ~ '{end_time_str}')")
                    continue

                if day_numeric not in daily_schedule:
                    daily_schedule[day_numeric] = []
                daily_schedule[day_numeric].append((start_minutes, end_minutes))
    
    # day_map은 이미 위에서 정의됨.

    for day_numeric_str in sorted(day_map.keys()): # "0" (월요일) 부터 "6" (일요일) 까지 순회
        day_name = day_map.get(day_numeric_str, f"알 수 없는 요일 코드({day_numeric_str})")
        print(f"\n--- {day_name} ---")

        # 기준 시간 설정 (오전 9시 ~ 오후 9시)
        overall_day_start_minutes = time_to_minutes("09:00")
        overall_day_end_minutes = time_to_minutes("21:00")
        
        # 현재까지 처리된 마지막 시간 (공강 시작점 계산용)
        # 초기값은 오전 9시로 설정
        last_class_end_processed_minutes = overall_day_start_minutes
        free_slots_printed_this_day = False

        todays_relevant_classes = []
        if day_numeric_str in daily_schedule:
            for s_mins, e_mins in daily_schedule[day_numeric_str]:
                # 현재 고려 중인 09:00-21:00 시간대와 겹치는 수업만 필터링
                if e_mins > overall_day_start_minutes and s_mins < overall_day_end_minutes:
                    todays_relevant_classes.append((s_mins, e_mins))
            todays_relevant_classes.sort(key=lambda x: x[0]) # 시작 시간 기준으로 정렬

        if not todays_relevant_classes:
            # 해당 요일에 09:00-21:00 사이와 겹치는 수업이 없는 경우
            if overall_day_end_minutes > overall_day_start_minutes:
                start_str = minutes_to_time_str(overall_day_start_minutes)
                end_str = minutes_to_time_str(overall_day_end_minutes)
                print(f"  공강: {start_str} ~ {end_str}")
                free_slots_printed_this_day = True
        else:
            for class_start_minutes, class_end_minutes in todays_relevant_classes:
                # 현재 수업 시작 전까지의 공강 시간 계산
                # 공강 시작은 max(오전 9시, 이전 수업 종료 시간)
                # 공강 종료는 min(현재 수업 시작 시간, 오후 9시)
                effective_free_slot_start = last_class_end_processed_minutes
                effective_free_slot_end = min(class_start_minutes, overall_day_end_minutes)

                if effective_free_slot_end > effective_free_slot_start:
                    start_str = minutes_to_time_str(effective_free_slot_start)
                    end_str = minutes_to_time_str(effective_free_slot_end)
                    print(f"  공강: {start_str} ~ {end_str}")
                    free_slots_printed_this_day = True
                
                # 다음 공강 계산을 위해 마지막 처리 시간 업데이트
                # (현재 수업 종료 시간과 이전 마지막 처리 시간 중 더 늦은 시간, 하지만 오후 9시를 넘지 않도록)
                last_class_end_processed_minutes = min(max(last_class_end_processed_minutes, class_end_minutes), overall_day_end_minutes)

                # 이미 오후 9시를 넘었으면 더 이상 공강 없음
                if last_class_end_processed_minutes >= overall_day_end_minutes:
                    break
            
            # 모든 수업 처리 후, 마지막 수업 종료 시간부터 오후 9시까지의 공강 시간 계산
            if last_class_end_processed_minutes < overall_day_end_minutes:
                start_str = minutes_to_time_str(last_class_end_processed_minutes)
                end_str = minutes_to_time_str(overall_day_end_minutes)
                print(f"  공강: {start_str} ~ {end_str}")
                free_slots_printed_this_day = True

        if not free_slots_printed_this_day:
            # 09:00-21:00 사이에 공강이 하나도 출력되지 않은 경우
            # (수업으로 꽉 찼거나, 모든 수업이 해당 범위 밖인 경우는 위에서 처리됨)
            print(f"  오전 9시부터 오후 9시까지 공강 시간 없음 (수업으로 채워짐).")

    print("--- 공강 시간 계산 완료 ---\n")
    # --- 공강 시간 계산 및 출력 코드 종료 ---

    cal = c.get_calendar(subjects, args.begin, args.end, args.hide_details)
    output_path = args.output if (args.output) else os.path.join('', 'calendar.ics')
    
    try:
        c.export_calender_as_ics(cal, output_path)
        print(f"'{output_path}' 파일로 성공적으로 내보냈습니다! 🙌")
    except Exception as e:
        print(f"ICS 파일 생성 중 오류 발생: {e}")


if __name__ == '__main__':
    main()
