# train_model.py

import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from models.timetable_nn import TimetableDataset, TimetableNet

def load_dummy_data(num_samples=100):
    """
    더미 데이터를 생성합니다.
    - slots_list: 각 샘플의 timetable_slots (list of tuples)
    - subject_lists: 각 샘플의 과목명 리스트
    - weight_lists: 각 샘플의 과목 가중치 리스트
    """
    slots_list = []
    subject_lists = []
    weight_lists = []
    for _ in range(num_samples):
        # 예시: 매번 월요일 09:00-10:00 공강 슬롯만
        slots = [("공강", "", "월요일", "09:00", "10:00")]
        names = ["A", "B", "C"]            # 더미 과목명
        weights = [1.0, 0.5, 0.2]          # 더미 중요도
        slots_list.append(slots)
        subject_lists.append(names)
        weight_lists.append(weights)
    return slots_list, subject_lists, weight_lists

def train():
    # 하이퍼파라미터
    hidden_dim = 64
    batch_size = 16
    epochs     = 20
    lr         = 1e-3

    # 1) 데이터 준비
    slots_list, subject_lists, weight_lists = load_dummy_data(200)
    # 각 샘플마다 TimetableDataset을 만들고 input/target을 모은 뒤,
    all_inputs = []
    all_targets = []
    for slots, names, weights in zip(slots_list, subject_lists, weight_lists):
        ds = TimetableDataset(slots, names, weights)
        all_inputs.append(ds.inputs)
        all_targets.append(ds.targets)

    full_inputs  = torch.cat(all_inputs, dim=0)
    full_targets = torch.cat(all_targets, dim=0)
    full_ds = TensorDataset(full_inputs, full_targets)
    loader  = DataLoader(full_ds, batch_size=batch_size, shuffle=True)

    # 2) 모델 초기화
    input_dim    = full_inputs.shape[1]     # 예: 11
    num_subjects = len(subject_lists[0])    # 예: 3 (A, B, C)
    model = TimetableNet(input_dim=input_dim,
                         hidden_dim=hidden_dim,
                         num_subjects=num_subjects)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn   = nn.CrossEntropyLoss(ignore_index=-1)

    # 3) 학습 루프
    model.train()
    for epoch in range(1, epochs+1):
        total_loss = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            logits = model(xb)
            loss   = loss_fn(logits, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * xb.size(0)
        avg_loss = total_loss / len(full_ds)
        print(f"Epoch {epoch:02d}/{epochs}  loss = {avg_loss:.4f}")

    # 4) 가중치 저장
    os.makedirs("models", exist_ok=True)
    torch.save(model.state_dict(), "models/model.pt")
    print("✅ 학습 완료 — models/model.pt에 state_dict 저장됨")

if __name__ == "__main__":
    train()
