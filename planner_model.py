# planner_model.py

import torch
import torch.nn as nn
import torch.nn.functional as F

class WeeklyStudyPlanner(nn.Module):
    def __init__(self, subject_count=5, day_slots=48, days=7):
        super().__init__()
        self.subject_count = subject_count
        input_size = days * day_slots + subject_count * 2
        self.fc1 = nn.Linear(input_size, 256)
        self.fc2 = nn.Linear(256, 128)
        self.fc3 = nn.Linear(128, subject_count)

    def forward(self, free_time, importance, major):
        weighted_importance = importance + 0.2 * major
        x = torch.cat([free_time, weighted_importance, major], dim=1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return F.softmax(self.fc3(x), dim=1)

# 모델 초기화
model = WeeklyStudyPlanner(subject_count=5)
model.eval()  # 학습 안 함
