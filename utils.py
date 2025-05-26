import torch
import numpy as np

def weekly_schedule_to_tensor(schedule_dict):
    tensor = torch.zeros(336)
    day_index = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

    for day, intervals in schedule_dict.items():
        base = day_index[day] * 48
        for start, end in intervals:
            start_slot = int((start - 9) * 2)
            end_slot = int((end - 9) * 2)
            for s in range(max(0, start_slot), min(48, end_slot)):
                tensor[base + s] = 1.0
    return tensor.unsqueeze(0)

def assign_subjects_with_breaks(free_time_tensor, subject_ratios, max_daily_hours=6):
    free_time = free_time_tensor.squeeze().numpy()
    subject_ratios = subject_ratios.squeeze().detach().numpy()
    subject_count = len(subject_ratios)
    max_daily_slots = max_daily_hours * 2

    schedule = [-1] * 336
    for day in range(7):
        base = day * 48
        day_free_indices = [i for i in range(base, base + 48) if free_time[i] == 1]
        day_slots = day_free_indices[:max_daily_slots]
        if not day_slots:
            continue
        total_week_slots = int(np.sum(free_time))
        subject_total = (subject_ratios * total_week_slots).astype(int)
        subject_daily = (subject_total / 7).astype(int)
        cursor = 0
        for subject_idx, count in enumerate(subject_daily):
            inserted = 0
            while inserted < count and cursor < len(day_slots):
                for _ in range(2):
                    if inserted >= count or cursor >= len(day_slots): break
                    schedule[day_slots[cursor]] = subject_idx
                    cursor += 1
                    inserted += 1
                if cursor < len(day_slots):
                    schedule[day_slots[cursor]] = -2  # 휴식
                    cursor += 1
    return schedule
