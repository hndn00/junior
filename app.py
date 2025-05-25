from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)

# 루트(/) 경로에서 로그인 페이지 렌더링
@app.route("/")
def root():
    return render_template("login.html")

# 로그인 기능 처리
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        # 간단한 로그인 검증 예제 (실제 사용 시 데이터베이스 검증 필요)
        if username == "admin" and password == "1234":
            # 로그인 성공 시 학습 플랜 경로로 리디렉션
            return redirect(url_for("plan"))
        else:
            # 실패 시 다시 로그인 페이지로 이동
            return redirect(url_for("root"))
    
    # GET 요청일 경우 로그인 페이지 렌더링
    return render_template("login.html")

# 학습 플랜 페이지
@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
        total_hours = float(request.form.get("total_hours"))
        names = request.form.getlist("name")
        weights = list(map(float, request.form.getlist("weight")))

        total_weight = sum(weights)
        if total_weight == 0:
            return "중요도 총합이 0입니다. 다시 입력해주세요."

        results = [(name, round((w / total_weight) * total_hours, 2)) for name, w in zip(names, weights)]
        return render_template("result.html", results=results)
    
    # GET 요청 시 학습 플랜 입력 폼 렌더링
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)