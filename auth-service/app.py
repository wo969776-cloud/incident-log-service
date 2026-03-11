"""
AUTH SERVICE
- 담당: 회원가입 / 로그인 / 토큰 발급 / 토큰 검증
- DB: users 테이블만 소유
- Port: 8001
- 외부 의존: 없음 (다른 서비스들이 이 서비스를 호출)
"""
import os
import jwt
import datetime
from flask import Flask, request, jsonify
from extensions import db
from models import User

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///auth.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

JWT_SECRET = os.environ.get("JWT_SECRET", "jwt_dev_secret_change_me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = int(os.environ.get("JWT_EXP_HOURS", "24"))

db.init_app(app)

with app.app_context():
    db.create_all()


def _make_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Health ──────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "auth"})


# ── 회원가입 ─────────────────────────────────────────────
@app.post("/auth/register")
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not email or not password:
        return jsonify({"error": "username, email, password 모두 필요합니다"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "이미 존재하는 아이디입니다"}), 409

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "이미 사용 중인 이메일입니다"}), 409

    user = User(username=username, email=email, role="user")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"id": user.id, "username": user.username}), 201


# ── 로그인 → JWT 발급 ────────────────────────────────────
@app.post("/auth/login")
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "아이디와 비밀번호를 입력하세요"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "회원이 아닙니다"}), 404

    if not user.verify_password(password):
        return jsonify({"error": "비밀번호가 틀렸습니다"}), 401

    token = _make_token(user)
    return jsonify({
        "token": token,
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    })


# ── 토큰 검증 (API Gateway / 다른 서비스에서 호출) ───────
@app.post("/auth/verify")
def verify():
    """
    Header: Authorization: Bearer <token>
    반환: {user_id, username, role} or 401
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "토큰이 없습니다"}), 401

    token = auth_header[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return jsonify({
            "user_id":  payload["sub"],
            "username": payload["username"],
            "role":     payload["role"],
        })
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "토큰이 만료됐습니다"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "유효하지 않은 토큰입니다"}), 401


# ── 사용자 정보 조회 (프로필용) ──────────────────────────
@app.get("/auth/users/<int:user_id>")
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        "id":       user.id,
        "username": user.username,
        "email":    user.email,
        "role":     user.role,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
