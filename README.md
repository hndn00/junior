# GongGang Genie


## Requirements Installation
```python

pip install BeautifulSoup4 requests bs4 python-dateutil icalendar flask 
pip install flask
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
py train_model.py


```

## Run Application

```python

flask run
or
py app.py

```

# About…

## **Timetable Loading and Free Time Calculation (`/process_timetable`)**

- The `/process_timetable` endpoint calls the Everytime API to retrieve the timetable XML. (`everytime.py`)
- The received XML is parsed by the `Convert` object to extract class information by subject. (`convert.py`)
- "Class" slots and "Free time" slots are calculated in minutes between 9:00 AM and 9:00 PM, sorted, and returned as JSON. (`app.py`)

## **Study Time Allocation and Result Rendering (`/plan`)**

- The client sends the total available study time, subject names, weight (importance level), and whether it's a major subject via POST. It also includes the hidden field `timetable_slots` to submit both free/class slot information. (`index.html`)
- The server loads a pre-trained PyTorch MLP model (`TimetableNet`) to predict which subject to study in each free time slot. (`timetable_nn.py`)
- The prediction results are used to generate:
    - `results_for_pie_chart`: for pie chart rendering
    - `full_schedule_raw_data`: for modal and full timetable view.
    - These are passed to the template for rendering. (`app.py`)



## **Full Timetable Visualization (`/show_full_schedule`)**

- In a separate route, original data stored in the session is retrieved.
- Using the same logic, class and free time slots are recombined and rendered into an HTML `<table>` based on 30-minute grid intervals. (`full_schedule.html`)

---

# Advantages

- **Modularity**: Parsing (`convert.py`), API calls (`everytime.py`), machine learning (`timetable_nn.py`), and training scripts (`train_model.py`) are separated, making the codebase easy to extend and maintain.

- **Full-Stack Coverage**: It spans the entire stack—from backend (Flask) → frontend (index.html + JS) → machine learning (PyTorch) → calendar export (ICS) → static visualization (full_schedule.html).

