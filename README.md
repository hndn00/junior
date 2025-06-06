# GongGang AI Planner

This project generates a personalized study plan using your university timetable. You can fetch schedules from Everytime or upload XML files, analyze free periods, and use a neural network model to suggest weekly study priorities. A web interface lets you visualize and adjust the plan.

## Features

- **Timetable import**: `everytime.py` fetches an XML timetable from an Everytime share URL or loads a local file.
- **Timetable → Calendar**: `every2cal.py` lists free time slots and exports an `.ics` calendar.
- **Study plan generation**: `models/study_plan_nn.py` assigns priorities based on subject importance, major relevance, and free time.
- **Web interface**: `app.py` is a Flask server to input timetable data, view schedules, and retrain the model if needed.

## Getting Started

1. Install Python 3.8+ and required packages:
   ```bash
   pip install flask torch requests icalendar python-dateutil
   ```
2. Launch the web server:
   ```bash
   python app.py
   ```
3. Visit `http://localhost:5001` in your browser to load a timetable and generate a study plan.

Convert a timetable directly to an `.ics` file:
```bash
python every2cal.py --id <EVERYTIME_ID> --begin 2024-03-02 --end 2024-06-20
```

## Directory Overview

- `app.py` – Flask application entry point
- `every2cal.py` – Converts timetable XML to `.ics`
- `convert.py` – Parses XML and performs iCalendar conversion
- `models/` – Neural network (`study_plan_nn.py`) and saved model files
- `templates/`, `static/` – Web page templates and static resources
- `subject_datas/` – User-provided subject data storage

## License

This project is released under the MIT License unless noted otherwise.
