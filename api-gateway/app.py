"""
API GATEWAY
- 역할: 단일 진입점 (클라이언트 → 게이트웨이 → 각 서비스)
- JWT 검증 후 X-User-* 헤더 주입
- Port: 8000
- 라우팅 규칙:
    /api/auth/*       → AUTH SERVICE     (8001) [인증 불필요]
    /api/incidents/*  → INCIDENT SERVICE (8002) [JWT 필요]
    /api/posts/*      → BOARD SERVICE    (8003) [JWT 필요]
    /ui/*             → FRONTEND SERVICE (8004) [세션 쿠키 기반]
"""
import os
import jwt
import requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

JWT_SECRET    = os.environ.get("JWT_SECRET", "jwt_dev_secret_change_me")
JWT_ALGORITHM = "HS256"

AUTH_SERVICE     = os.environ.get("AUTH_SERVICE_URL",     "http://auth-service:8001")
INCIDENT_SERVICE = os.environ.get("INCIDENT_SERVICE_URL", "http://incident-service:8002")
BOARD_SERVICE    = os.environ.get("BOARD_SERVICE_URL",    "http://board-service:8003")
FRONTEND_SERVICE = os.environ.get("FRONTEND_SERVICE_URL", "http://frontend-service:8004")

# 인증이 필요 없는 경로 prefix
PUBLIC_PATHS = ("/api/auth/",)


def _verify_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def _proxy(target_url: str, extra_headers: dict = None) -> Response:
    """요청을 target_url로 그대로 프록시."""
    headers = {k: v for k, v in request.headers if k.lower() != "host"}
    if extra_headers:
        headers.update(extra_headers)

    resp = requests.request(
        method  = request.method,
        url     = target_url,
        headers = headers,
        data    = request.get_data(),
        params  = request.args,
        timeout = 10,
        allow_redirects = False,
    )

    excluded = {"content-encoding", "transfer-encoding", "connection"}
    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}

    return Response(resp.content, status=resp.status_code, headers=resp_headers)


# ── Health ──────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "gateway"})


# ── 모든 요청 처리 ────────────────────────────────────────
@app.route("/api/<path:path>", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
def gateway(path: str):
    full_path = f"/api/{path}"

    # ── 공개 경로: JWT 검증 없이 통과 ──
    is_public = any(full_path.startswith(p) for p in PUBLIC_PATHS)

    user_headers = {}

    if not is_public:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "인증 토큰이 필요합니다"}), 401

        payload = _verify_jwt(auth_header[7:])
        if payload is None:
            return jsonify({"error": "유효하지 않거나 만료된 토큰입니다"}), 401

        # 검증된 사용자 정보를 헤더로 주입
        user_headers = {
            "X-User-Id":   str(payload["sub"]),
            "X-User-Name": payload["username"],
            "X-User-Role": payload["role"],
        }

    # ── 라우팅 ──────────────────────────────────────────
    if path.startswith("auth/"):
        stripped = path[len("auth/"):]
        return _proxy(f"{AUTH_SERVICE}/{stripped}", user_headers)

    if path.startswith("incidents"):
        return _proxy(f"{INCIDENT_SERVICE}/{path}", user_headers)

    if path.startswith("posts"):
        return _proxy(f"{BOARD_SERVICE}/{path}", user_headers)

    return jsonify({"error": f"알 수 없는 경로: /api/{path}"}), 404


# ── UI 요청: Frontend Service로 프록시 ─────────────────
@app.route("/ui/<path:path>", methods=["GET", "POST"])
@app.route("/ui/", methods=["GET"])
def ui_proxy(path=""):
    return _proxy(f"{FRONTEND_SERVICE}/ui/{path}")


# ── 루트 ────────────────────────────────────────────────
@app.get("/")
def root():
    return jsonify({
        "service": "api-gateway",
        "routes": {
            "/api/auth/*":      "auth-service:8001",
            "/api/incidents/*": "incident-service:8002",
            "/api/posts/*":     "board-service:8003",
            "/ui/*":            "frontend-service:8004",
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
