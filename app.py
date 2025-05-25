from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)

# 간단한 사용자 인증 정보
USER_CREDENTIALS = {
    "admin": "1234",  # 아이디: 비밀번호
}

# 루트 경로: 로그인 페이지
@app.route("/")
def login():
    return render_template("login.html")

# 로그인 처리
@app.route("/login", methods=["POST"])
def handle_login():
    username = request.form.get("username")
    password = request.form.get("password")

    # 사용자 인증 확인
    if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
        # 로그인 성공 시 학습 플래너 페이지로 이동
        return redirect(url_for("plan"))
    else:
        # 로그인 실패 시 로그인 페이지로 돌아가기
        return render_template("login.html", error="아이디 또는 비밀번호가 잘못되었습니다.")

# 학습 플래너 페이지
@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
        try:
            # 총 학습 시간
            total_hours = float(request.form.get("total_hours"))

            # 과목명 리스트
            names = request.form.getlist("name")

            # 중요도 리스트
            weights = request.form.getlist("weight")

            # 중요도 리스트를 float로 변환
            weights = list(map(float, weights))

            # 유효성 검사
            if len(names) == 0 or len(weights) == 0 or sum(weights) == 0:
                return "입력 데이터가 잘못되었습니다. 다시 시도해주세요."

            # 중요도 합
            total_weight = sum(weights)

            # 각 과목에 배분된 학습 시간을 계산
            results = [(name, round((weight / total_weight) * total_hours, 2)) for name, weight in zip(names, weights)]

            # 결과 페이지 렌더링
            return render_template("result.html", results=results)
        except Exception as e:
            return f"오류가 발생했습니다: {e}"

    # GET 요청일 경우 학습 플래너 페이지 렌더링
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)