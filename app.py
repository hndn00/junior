from flask import Flask, request, render_template
import os

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/plan", methods=["POST"])
def plan():
    total_hours = float(request.form.get("total_hours"))
    names = request.form.getlist("name")
    weights = list(map(float, request.form.getlist("weight")))

    total_weight = sum(weights)
    if total_weight == 0:
        return "중요도 총합이 0입니다. 다시 입력해주세요."

    results = [(name, round((w / total_weight) * total_hours, 2)) for name, w in zip(names, weights)]
    return render_template("result.html", results=results)

if __name__ == "__main__":
    app.run(debug=True)
