import torch
import torch.nn as nn
from torch.utils.data import Dataset

# 시간 문자열(HH:MM) → 자정부터의 분
def time_to_minutes(time_str):
    if not time_str or ':' not in time_str:
        return 0
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

class TimetableDataset(Dataset):
    """
    slots: [("수업" or "공강", subject_name, day_name, start_str, end_str), ...]
    subject_list: ["회로이론", "미적분", ...]
    subject_weights: [0.8, 0.6, ...]  (same order as subject_list)
    """
    def __init__(self, slots, subject_list, subject_weights):
        # 과목명 → 인덱스 맵
        self.subj2idx = {name: idx for idx, name in enumerate(subject_list)}

        # weight 정규화용 최대값 (비어있으면 1.0)
        max_w = max(subject_weights) if subject_weights else 1.0

        feats = []
        targets = []
        # 요일 맵
        day_to_idx = {
            "월요일":0, "화요일":1, "수요일":2,
            "목요일":3, "금요일":4, "토요일":5, "일요일":6
        }

        for kind, name, day, st, ed in slots:
            # 1) 요일 one-hot (7)
            day_idx = day_to_idx.get(day, 0)
            day_oh = [1.0 if i == day_idx else 0.0 for i in range(7)]

            # 2) 시간 정규화 (start, end) → [0,1]
            s_norm = time_to_minutes(st) / (24*60)
            e_norm = time_to_minutes(ed) / (24*60)

            # 3) 수업 여부 flag
            is_class = 1.0 if kind == "수업" else 0.0

            # 4) 과목 중요도 가중치 (subject_weights 정규화)
            if name in self.subj2idx:
                idx = self.subj2idx[name]
                # **안전장치: idx가 벗어나면 0.0 사용**
                if 0 <= idx < len(subject_weights):
                    w = subject_weights[idx] / max_w
                else:
                    w = 0.0
            else:
                w = 0.0

            # 합쳐서 10차원 feature
            feat = day_oh + [s_norm, e_norm, is_class, w]
            feats.append(feat)

            # 타깃: 과목 인덱스 (없으면 -1)
            targets.append(self.subj2idx.get(name, -1))

        # 텐서로 변환
        self.inputs  = torch.tensor(feats, dtype=torch.float32)
        self.targets = torch.tensor(targets, dtype=torch.long)

    def __len__(self):
        return len(self.inputs)

    def __getitem__(self, idx):
        return self.inputs[idx], self.targets[idx]


class TimetableNet(nn.Module):
    """
    단순 MLP: input_dim=10 → hidden → hidden/2 → num_subjects
    """
    def __init__(self, input_dim: int, hidden_dim: int, num_subjects: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim // 2, num_subjects)
        )

    def forward(self, x):
        return self.net(x)
