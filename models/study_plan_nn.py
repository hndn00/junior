import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

class StudyPlanNet(nn.Module):
    """
    학습 계획을 생성하는 인공신경망
    """
    def __init__(self, input_dim: int, hidden_dim: int = 128, output_dim: int = 5):
        super(StudyPlanNet, self).__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim  # 학습 시간 분배 (매우 높음, 높음, 보통, 낮음, 매우 낮음)

        # 네트워크 구조
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim // 2)
        self.fc3 = nn.Linear(hidden_dim // 2, hidden_dim // 4)
        self.fc4 = nn.Linear(hidden_dim // 4, output_dim)

        self.dropout = nn.Dropout(0.3)
        self.relu = nn.ReLU()
        self.softmax = nn.Softmax(dim=1)

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.relu(self.fc3(x))
        x = self.fc4(x)
        return self.softmax(x)

class StudyPlanDataset:
    """
    학습 계획 데이터셋 클래스
    """
    def __init__(self, subjects: List[Dict], timetable_slots: List[Tuple]):
        self.subjects = subjects
        self.timetable_slots = timetable_slots
        self.features = self._extract_features()
        self.labels = self._generate_labels()

    def _extract_features(self) -> torch.Tensor:
        """
        과목별 특성 벡터 추출
        """
        features = []

        for subject in self.subjects:
            feature_vector = []

            # 1. 과목 중요도 (정규화)
            weight = subject.get('weight', 1.0)
            normalized_weight = min(weight / 10.0, 1.0)  # 0-1 범위로 정규화
            feature_vector.append(normalized_weight)

            # 2. 전공 여부 (0 또는 1)
            is_major = subject.get('major', 0.0)
            feature_vector.append(is_major)

            # 3. 수업 시간 분석
            class_hours = self._calculate_class_hours(subject['name'])
            feature_vector.append(class_hours / 10.0)  # 정규화

            # 4. 공강 시간 분석
            free_hours = self._calculate_free_hours_around_class(subject['name'])
            feature_vector.append(free_hours / 20.0)  # 정규화

            # 5. 요일별 분포 (월-금)
            day_distribution = self._get_day_distribution(subject['name'])
            feature_vector.extend(day_distribution)

            # 6. 시간대별 분포 (오전, 오후, 저녁)
            time_distribution = self._get_time_distribution(subject['name'])
            feature_vector.extend(time_distribution)

            # 7. 연속성 지수 (연속된 수업인지)
            continuity = self._calculate_continuity(subject['name'])
            feature_vector.append(continuity)

            features.append(feature_vector)

        return torch.FloatTensor(features)

    def _calculate_class_hours(self, subject_name: str) -> float:
        """수업 시간 계산"""
        total_hours = 0
        for slot in self.timetable_slots:
            if slot[0] == "수업" and slot[1] == subject_name:
                start_time = self._time_to_minutes(slot[3])
                end_time = self._time_to_minutes(slot[4])
                total_hours += (end_time - start_time) / 60.0
        return total_hours

    def _calculate_free_hours_around_class(self, subject_name: str) -> float:
        """수업 전후 공강시간 계산"""
        free_hours = 0
        subject_slots = []

        # 해당 과목의 수업시간 찾기
        for slot in self.timetable_slots:
            if slot[0] == "수업" and slot[1] == subject_name:
                subject_slots.append((slot[2], self._time_to_minutes(slot[3]), self._time_to_minutes(slot[4])))

        # 각 수업 전후 공강시간 계산
        for day, start, end in subject_slots:
            for slot in self.timetable_slots:
                if slot[0] == "공강" and slot[2] == day:
                    free_start = self._time_to_minutes(slot[3])
                    free_end = self._time_to_minutes(slot[4])

                    # 수업 직전/직후 2시간 이내의 공강시간
                    if abs(free_end - start) <= 120 or abs(free_start - end) <= 120:
                        free_hours += (free_end - free_start) / 60.0

        return free_hours

    def _get_day_distribution(self, subject_name: str) -> List[float]:
        """요일별 분포 (월-금)"""
        days = ["월요일", "화요일", "수요일", "목요일", "금요일"]
        distribution = [0.0] * 5

        for slot in self.timetable_slots:
            if slot[0] == "수업" and slot[1] == subject_name:
                if slot[2] in days:
                    distribution[days.index(slot[2])] = 1.0

        return distribution

    def _get_time_distribution(self, subject_name: str) -> List[float]:
        """시간대별 분포 (오전, 오후, 저녁)"""
        morning = afternoon = evening = 0

        for slot in self.timetable_slots:
            if slot[0] == "수업" and slot[1] == subject_name:
                start_minutes = self._time_to_minutes(slot[3])

                if start_minutes < 720:  # 12:00 이전 (오전)
                    morning = 1
                elif start_minutes < 1080:  # 18:00 이전 (오후)
                    afternoon = 1
                else:  # 저녁
                    evening = 1

        return [float(morning), float(afternoon), float(evening)]

    def _calculate_continuity(self, subject_name: str) -> float:
        """수업의 연속성 계산"""
        subject_times = []

        for slot in self.timetable_slots:
            if slot[0] == "수업" and slot[1] == subject_name:
                day = slot[2]
                start = self._time_to_minutes(slot[3])
                end = self._time_to_minutes(slot[4])
                subject_times.append((day, start, end))

        # 같은 날 연속된 수업인지 확인
        continuity_score = 0
        for i, (day1, start1, end1) in enumerate(subject_times):
            for j, (day2, start2, end2) in enumerate(subject_times):
                if i != j and day1 == day2:
                    if abs(end1 - start2) <= 30 or abs(end2 - start1) <= 30:  # 30분 이내
                        continuity_score += 1

        return min(continuity_score / len(subject_times) if subject_times else 0, 1.0)

    def _time_to_minutes(self, time_str: str) -> int:
        """시간 문자열을 분으로 변환"""
        try:
            h, m = map(int, time_str.split(':'))
            return h * 60 + m
        except:
            return 0

    def _generate_labels(self) -> torch.Tensor:
        """
        학습 우선순위 라벨 생성
        """
        labels = []

        for subject in self.subjects:
            weight = subject.get('weight', 1.0)
            is_major = subject.get('major', 0.0)

            # 가중치 계산 (전공 과목에 보너스)
            adjusted_weight = weight * (1.0 + 0.5 * is_major)

            # 5단계 우선순위로 분류
            if adjusted_weight >= 9.0:
                label = 0  # 매우 높음
            elif adjusted_weight >= 7.0:
                label = 1  # 높음
            elif adjusted_weight >= 5.0:
                label = 2  # 보통
            elif adjusted_weight >= 3.0:
                label = 3  # 낮음
            else:
                label = 4  # 매우 낮음

            labels.append(label)

        return torch.LongTensor(labels)

class StudyPlanGenerator:
    """
    학습 계획 생성기
    """
    def __init__(self, model_path: str = None):
        self.model = None
        self.subjects = []
        self.timetable_slots = []

        if model_path:
            self.load_model(model_path)

    def train_model(self, subjects: List[Dict], timetable_slots: List[Tuple],
                    epochs: int = 100, lr: float = 0.001):
        """
        모델 훈련
        """
        self.subjects = subjects
        self.timetable_slots = timetable_slots

        # 데이터셋 준비
        dataset = StudyPlanDataset(subjects, timetable_slots)

        # 모델 초기화
        input_dim = dataset.features.shape[1]
        self.model = StudyPlanNet(input_dim=input_dim)

        # 손실 함수와 옵티마이저
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=lr)

        # 훈련
        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()

            outputs = self.model(dataset.features)
            loss = criterion(outputs, dataset.labels)

            loss.backward()
            optimizer.step()

            if (epoch + 1) % 20 == 0:
                print(f'Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}')

    def predict_study_priorities(self) -> List[Dict]:
        """
        학습 우선순위 예측
        """
        if not self.model:
            raise ValueError("모델이 훈련되지 않았습니다.")

        dataset = StudyPlanDataset(self.subjects, self.timetable_slots)

        self.model.eval()
        with torch.no_grad():
            outputs = self.model(dataset.features)
            priorities = torch.argmax(outputs, dim=1).tolist()
            confidence_scores = torch.max(outputs, dim=1)[0].tolist()

        priority_names = ["매우 높음", "높음", "보통", "낮음", "매우 낮음"]

        results = []
        for i, subject in enumerate(self.subjects):
            results.append({
                'subject_name': subject['name'],
                'priority': priority_names[priorities[i]],
                'priority_score': priorities[i],
                'confidence': confidence_scores[i],
                'weight': subject.get('weight', 1.0),
                'is_major': bool(subject.get('major', 0.0))
            })

        # 우선순위 순으로 정렬
        results.sort(key=lambda x: x['priority_score'])

        return results

    def generate_weekly_schedule(self) -> Dict:
        """
        주간 학습 계획 생성
        """
        priorities = self.predict_study_priorities()

        # 시간대별 학습 시간 분배
        time_allocation = {
            "매우 높음": 3.0,  # 시간
            "높음": 2.5,
            "보통": 2.0,
            "낮음": 1.5,
            "매우 낮음": 1.0
        }

        weekly_schedule = {}
        days = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

        for day in days:
            daily_schedule = []

            # 해당 요일의 공강시간 찾기
            free_slots = []
            for slot in self.timetable_slots:
                if slot[0] == "공강" and slot[2] == day:
                    start_minutes = self._time_to_minutes(slot[3])
                    end_minutes = self._time_to_minutes(slot[4])
                    duration = (end_minutes - start_minutes) / 60.0

                    if duration >= 1.0:  # 1시간 이상의 공강시간만
                        free_slots.append({
                            'start_time': slot[3],
                            'end_time': slot[4],
                            'duration': duration
                        })

            # 우선순위별로 학습시간 배정
            allocated_time = 0
            for priority_info in priorities:
                subject_name = priority_info['subject_name']
                priority = priority_info['priority']
                study_time_needed = time_allocation[priority]

                # 해당 과목의 수업이 있는 날인지 확인
                has_class_today = any(
                    slot[0] == "수업" and slot[1] == subject_name and slot[2] == day
                    for slot in self.timetable_slots
                )

                # 수업이 있는 날은 복습 시간 추가, 없는 날은 예습 시간
                study_type = "복습" if has_class_today else "예습"

                # 남은 공강시간에서 학습시간 할당
                remaining_time = sum(slot['duration'] for slot in free_slots) - allocated_time
                actual_study_time = min(study_time_needed, remaining_time)

                if actual_study_time > 0:
                    daily_schedule.append({
                        'subject': subject_name,
                        'study_type': study_type,
                        'duration': actual_study_time,
                        'priority': priority,
                        'recommended_materials': self._get_study_materials(subject_name, study_type)
                    })
                    allocated_time += actual_study_time

            weekly_schedule[day] = daily_schedule

        return weekly_schedule

    def _time_to_minutes(self, time_str: str) -> int:
        """시간 문자열을 분으로 변환"""
        try:
            h, m = map(int, time_str.split(':'))
            return h * 60 + m
        except:
            return 0

    def _get_study_materials(self, subject_name: str, study_type: str) -> List[str]:
        """과목별 추천 학습 자료"""
        materials = {
            "예습": [
                "교재 해당 챕터 읽기",
                "강의 노트 미리 정리",
                "관련 개념 사전 학습",
                "예제 문제 풀어보기"
            ],
            "복습": [
                "강의 내용 요약 정리",
                "연습 문제 풀이",
                "개념 암기 및 이해 점검",
                "모르는 부분 질문 준비"
            ]
        }
        return materials.get(study_type, [])

    def save_model(self, path: str):
        """모델 저장"""
        if not self.model:
            raise ValueError("저장할 모델이 없습니다.")

        torch.save({
            'model_state_dict': self.model.state_dict(),
            'input_dim': self.model.input_dim,
            'hidden_dim': self.model.hidden_dim,
            'output_dim': self.model.output_dim,
            'subjects': self.subjects,
            'timetable_slots': self.timetable_slots
        }, path)

    def load_model(self, path: str):
        """모델 로드"""
        checkpoint = torch.load(path, map_location='cpu')

        self.model = StudyPlanNet(
            input_dim=checkpoint['input_dim'],
            hidden_dim=checkpoint['hidden_dim'],
            output_dim=checkpoint['output_dim']
        )
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.subjects = checkpoint['subjects']
        self.timetable_slots = checkpoint['timetable_slots']

# 사용 예시 함수
def create_study_plan(subjects_data: List[Dict], timetable_slots: List[Tuple]) -> Dict:
    """
    학습 계획 생성 메인 함수

    Args:
        subjects_data: [{'name': '과목명', 'weight': 중요도(1-10), 'major': 전공여부(0/1)}]
        timetable_slots: [(타입, 과목명, 요일, 시작시간, 종료시간, 교수명, 강의실)]

    Returns:
        학습 계획 딕셔너리
    """
    # 학습 계획 생성기 초기화
    planner = StudyPlanGenerator()

    # 모델 훈련
    print("인공신경망 모델 훈련 중...")
    planner.train_model(subjects_data, timetable_slots, epochs=100)

    # 학습 우선순위 예측
    print("학습 우선순위 분석 중...")
    priorities = planner.predict_study_priorities()

    # 주간 학습 계획 생성
    print("주간 학습 계획 생성 중...")
    weekly_schedule = planner.generate_weekly_schedule()

    return {
        'priorities': priorities,
        'weekly_schedule': weekly_schedule,
        'summary': {
            'total_subjects': len(subjects_data),
            'major_subjects': sum(1 for s in subjects_data if s.get('major', 0)),
            'high_priority_subjects': sum(1 for p in priorities if p['priority'] in ['매우 높음', '높음'])
        }
    }

# Flask 앱과의 통합을 위한 함수
def train_model_for_web(subjects_data: List[Dict], timetable_slots: List[Tuple],
                        model_path: str = "models/study_plan_model.pt") -> StudyPlanGenerator:
    """
    웹 앱용 모델 훈련 함수
    """
    planner = StudyPlanGenerator()
    planner.train_model(subjects_data, timetable_slots)
    planner.save_model(model_path)
    return planner