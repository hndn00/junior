from flask import Flask, request, render_template, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # 실제 사용 시 복잡한 키로 변경하세요

# 간단한 사용자 인증 정보
USER_CREDENTIALS = {
    "admin": "helloai",  # 아이디: 비밀번호
}

# 첫 화면: main.html
@app.route("/")
def main():
    # 세션 확인을 위해 명시적으로 세션 접근
    # 이렇게 하면 세션이 유효한지 확인할 수 있음
    username = session.get('username', None)
    # main.html 템플릿에는 이미 {% if session.username %} 조건문이 있음
    # 추가적인 서버 측 세션 검증은 필요하지 않으며
    # 첫 페이지는 로그인 여부와 상관없이 접근 가능
    return render_template("main.html")

# 로그아웃 처리
@app.route("/logout")
def logout():
    # 세션에서 사용자 정보 제거
    session.pop('username', None)
    # 로그인 페이지로 리다이렉트
    return redirect(url_for("login"))

# 로그인 처리 페이지
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # 사용자 인증 확인
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            # 세션에 사용자 이름 저장
            session['username'] = username
            return redirect(url_for("plan"))
        else:
            return render_template("login.html", error="아이디 또는 비밀번호가 잘못되었습니다.", username=username)

    # GET 요청: 로그인 페이지 렌더링
    return render_template("login.html", error=None, username="")

# 학습 플래너 페이지
@app.route("/plan", methods=["GET", "POST"])
def plan():
    # 로그인 상태 확인
    if 'username' not in session:
        # 로그인되지 않은 경우 로그인 페이지로 리다이렉트
        return redirect(url_for("login"))
        
    if request.method == "POST":
        try:
            total_hours = float(request.form.get("total_hours"))
            names = request.form.getlist("name")
            weights = list(map(float, request.form.getlist("weight")))

            if len(names) == 0 or len(weights) == 0 or sum(weights) == 0:
                return "입력 데이터가 잘못되었습니다. 다시 시도해주세요."

            total_weight = sum(weights)
            
            # 소수점 시간을 시간과 분으로 변환하는 함수
            def convert_to_hours_minutes(decimal_hours):
                hours = int(decimal_hours)  # 정수 부분 (시간)
                minutes = int((decimal_hours - hours) * 60)  # 소수점 부분을 분으로 변환
                return hours, minutes
            
            # 결과 계산 및 시간 형식 변환
            results = []
            for name, weight in zip(names, weights):
                decimal_hours = (weight / total_weight) * total_hours
                hours, minutes = convert_to_hours_minutes(decimal_hours)
                results.append((name, hours, minutes))
            
            return render_template("result.html", results=results)
        except Exception as e:
            return f"오류가 발생했습니다: {e}"

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
