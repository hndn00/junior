from flask import Flask, request, render_template

app = Flask(__name__)

# 루트(/) 경로에서 로그인 페이지 렌더링
@app.route("/")
def root():
    # 로그인 페이지로 바로 연결
    return render_template("login.html")

# 로그인 기능 처리
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        # 사용자 인증 처리 (예: 간단한 확인 로직)
        if username == "admin" and password == "1234":
            return f"환영합니다, {username}님!"
        else:
            return "아이디 또는 비밀번호가 올바르지 않습니다."
    
    # GET 요청 시 로그인 페이지 렌더링
    return render_template("login.html")

if __name__ == "__main__":
    app.run(debug=True)