from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)

# 간단한 사용자 인증 정보
USER_CREDENTIALS = {
    "admin": "helloai",  # 아이디: 비밀번호
}

# 첫 화면: main.html
@app.route("/")
def main():
    return render_template("main.html")

# 로그인 처리 페이지
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # 사용자 인증 확인
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            return redirect(url_for("plan"))
        else:
            return render_template("login.html", error="아이디 또는 비밀번호가 잘못되었습니다.")

    # GET 요청: 로그인 페이지 렌더링
    return render_template("login.html", error=None)

# 학습 플래너 페이지
@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
        try:
            total_hours = float(request.form.get("total_hours"))
            names = request.form.getlist("name")
            weights = list(map(float, request.form.getlist("weight")))

            if len(names) == 0 or len(weights) == 0 or sum(weights) == 0:
                return "입력 데이터가 잘못되었습니다. 다시 시도해주세요."

            total_weight = sum(weights)
            results = [(name, round((weight / total_weight) * total_hours, 2)) for name, weight in zip(names, weights)]
            return render_template("result.html", results=results)
        except Exception as e:
            return f"오류가 발생했습니다: {e}"

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)