from flask import Flask, request, render_template, redirect, url_for, session, jsonify
import torch
from planner_model import model  # 네가 따로 정의한 모델 파일
from utils import weekly_schedule_to_tensor, assign_subjects_with_breaks, parse_schedule_json

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # 실제 배포 시 변경

# 간단한 사용자 인증 정보
USER_CREDENTIALS = {

    "admin": "helloai",
}

# 첫 화면: main.html
@app.route("/")
def main():
    return render_template("main.html")

# 로그아웃 처리
@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for("login"))

# 로그인 처리
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

# 과목별 중요도 기반 학습시간 분배
@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
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

# ✅ 딥러닝 기반 학습 플래너 (공강 + 중요도 + 전공)
@app.route("/deepplan", methods=["POST"])
def deepplan():
    try:
        data = request.json
        # data 구조: {schedule: {...}, importance: [...], major: [...], max_hours: 6}
        schedule_dict = parse_schedule_json(data["schedule"])
        importance = torch.tensor([data["importance"]])
        major = torch.tensor([data["major"]])
        max_hours = int(data["max_hours"])

        free_time = weekly_schedule_to_tensor(schedule_dict)
        subject_ratios = model(free_time, importance, major)
        final_schedule = assign_subjects_with_breaks(free_time, subject_ratios, max_daily_hours=max_hours)

        return jsonify({"schedule": final_schedule})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(debug=True)
