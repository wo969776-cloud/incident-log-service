"""
FRONTEND SERVICE
- 역할: Jinja2 템플릿 렌더링 (기존 HTML UI 유지)
- 세션 쿠키로 JWT 저장, 각 API 서비스 호출
- Port: 8004
- 백엔드 통신: requests 로 API Gateway 경유 or 직접 서비스 호출
"""
import os
import requests as req
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")

# 내부 서비스 URL (K8s Service DNS 사용)
AUTH_URL     = os.environ.get("AUTH_SERVICE_URL",     "http://auth-service:8001")
INCIDENT_URL = os.environ.get("INCIDENT_SERVICE_URL", "http://incident-service:8002")
BOARD_URL    = os.environ.get("BOARD_SERVICE_URL",    "http://board-service:8003")


# ── 헬퍼 ─────────────────────────────────────────────────
def _auth_header() -> dict:
    token = session.get("token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}

def _require_login():
    if not session.get("logged_in"):
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("login_form"))
    return None

def _require_admin():
    guard = _require_login()
    if guard: return guard
    if session.get("role") != "admin":
        flash("관리자 전용 기능입니다.", "error")
        return redirect(url_for("home"))
    return None


# ── Health ──────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "frontend"})

# ── Root Redirect (Ingress 대응) ─────────────────────────
@app.get("/")
def root():
    if session.get("logged_in"):
        return redirect(url_for("home"))
    return redirect(url_for("login_form"))

# ── Auth UI ──────────────────────────────────────────────
@app.get("/ui/login")
def login_form():
    return render_template("login.html")


@app.post("/ui/login")
def login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        flash("아이디와 비밀번호를 모두 입력하세요.", "error")
        return redirect(url_for("login_form"))

    try:
        resp = req.post(f"{AUTH_URL}/auth/login",
                        json={"username": username, "password": password}, timeout=5)
    except req.exceptions.ConnectionError:
        flash("인증 서버에 연결할 수 없습니다.", "error")
        return redirect(url_for("login_form"))

    if resp.status_code == 200:
        data = resp.json()
        session["logged_in"] = True
        session["token"]     = data["token"]
        session["user_id"]   = data["user_id"]
        session["username"]  = data["username"]
        session["role"]      = data["role"]
        flash(f"{data['username']}님 환영합니다!", "success")
        return redirect(url_for("home"))

    flash(resp.json().get("error", "로그인 실패"), "error")
    return redirect(url_for("login_form"))


@app.get("/ui/register")
def register_form():
    return render_template("register.html")


@app.post("/ui/register")
def register_submit():
    username = request.form.get("username", "").strip()
    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "").strip()

    if not username or not email or not password:
        flash("아이디/이메일/비밀번호를 모두 입력하세요.", "error")
        return redirect(url_for("register_form"))

    resp = req.post(f"{AUTH_URL}/auth/register",
                    json={"username": username, "email": email, "password": password}, timeout=5)

    if resp.status_code == 201:
        flash("회원가입 완료. 로그인해주세요.", "success")
        return redirect(url_for("login_form"))

    flash(resp.json().get("error", "회원가입 실패"), "error")
    return redirect(url_for("register_form"))


@app.get("/ui/logout")
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("login_form"))


# ── Home ─────────────────────────────────────────────────
@app.get("/ui/home")
@app.get("/ui/")
def home():
    guard = _require_login()
    if guard: return guard
    return render_template("home.html", username=session.get("username"))


# ── Profile ──────────────────────────────────────────────
@app.get("/ui/profile")
def profile():
    guard = _require_login()
    if guard: return guard

    resp = req.get(f"{AUTH_URL}/auth/users/{session['user_id']}", timeout=5)
    user = resp.json() if resp.status_code == 200 else {}

    return render_template("profile.html", user=user,
                           username=session.get("username"),
                           is_admin=(session.get("role") == "admin"))


# ── Incident UI ──────────────────────────────────────────
@app.get("/ui/incidents")
def ui_incident_list():
    guard = _require_admin()
    if guard: return guard

    resp  = req.get(f"{INCIDENT_URL}/incidents", headers=_auth_header(), timeout=5)
    items = resp.json() if resp.status_code == 200 else []
    return render_template("incidents_list.html", items=items,
                           is_admin=True, username=session.get("username"))


@app.post("/ui/incidents/create")
def ui_incident_create():
    guard = _require_admin()
    if guard: return guard

    payload = {
        "title":    request.form.get("title", "").strip(),
        "severity": request.form.get("severity", "MEDIUM"),
        "status":   request.form.get("status",   "OPEN"),
    }
    resp = req.post(f"{INCIDENT_URL}/incidents", json=payload,
                    headers=_auth_header(), timeout=5)

    if resp.status_code == 201:
        flash("Incident가 생성되었습니다.", "success")
        return redirect(url_for("ui_incident_detail", incident_id=resp.json()["id"]))

    flash(resp.json().get("error", "생성 실패"), "error")
    return redirect(url_for("ui_incident_list"))


@app.get("/ui/incidents/<int:incident_id>")
def ui_incident_detail(incident_id):
    guard = _require_admin()
    if guard: return guard

    inc_resp  = req.get(f"{INCIDENT_URL}/incidents/{incident_id}",
                        headers=_auth_header(), timeout=5)
    logs_resp = req.get(f"{INCIDENT_URL}/incidents/{incident_id}/logs",
                        headers=_auth_header(), timeout=5)

    if inc_resp.status_code == 404:
        flash("존재하지 않는 Incident입니다.", "error")
        return redirect(url_for("ui_incident_list"))

    return render_template("incident_detail.html",
                           inc=type("Inc", (), inc_resp.json())(),
                           logs=[type("Log", (), l)() for l in (logs_resp.json() if logs_resp.ok else [])],
                           is_admin=True,
                           username=session.get("username"))


@app.post("/ui/incidents/<int:incident_id>/edit")
def ui_incident_edit(incident_id):
    guard = _require_admin()
    if guard: return guard

    payload = {k: request.form.get(k, "").strip()
               for k in ("title", "severity", "status") if request.form.get(k)}

    req.patch(f"{INCIDENT_URL}/incidents/{incident_id}", json=payload,
              headers=_auth_header(), timeout=5)

    flash("수정 완료", "success")
    return redirect(url_for("ui_incident_detail", incident_id=incident_id))


@app.post("/ui/incidents/<int:incident_id>/delete")
def ui_incident_delete(incident_id):
    guard = _require_admin()
    if guard: return guard

    req.delete(f"{INCIDENT_URL}/incidents/{incident_id}",
               headers=_auth_header(), timeout=5)

    flash("삭제 완료", "success")
    return redirect(url_for("ui_incident_list"))


@app.post("/ui/incidents/<int:incident_id>/logs")
def ui_add_log(incident_id):
    guard = _require_admin()
    if guard: return guard

    action = request.form.get("action", "").strip()
    if not action:
        flash("로그 내용을 입력하세요.", "error")
        return redirect(url_for("ui_incident_detail", incident_id=incident_id))

    req.post(f"{INCIDENT_URL}/incidents/{incident_id}/logs",
             json={"action": action}, headers=_auth_header(), timeout=5)

    flash("로그가 추가되었습니다.", "success")
    return redirect(url_for("ui_incident_detail", incident_id=incident_id))


# ── Board UI ─────────────────────────────────────────────
@app.get("/ui/public-board")
def board_list():
    guard = _require_login()
    if guard: return guard

    resp  = req.get(f"{BOARD_URL}/posts", headers=_auth_header(), timeout=5)
    posts_data = resp.json() if resp.ok else []
    # dict → 간단 객체 변환 (템플릿 호환)
    posts = [type("Post", (), p)() for p in posts_data]
    return render_template("board_list.html", posts=posts,
                           username=session.get("username"),
                           is_admin=(session.get("role") == "admin"))


@app.get("/ui/public-board/new")
def board_new_form():
    guard = _require_login()
    if guard: return guard
    return render_template("board_form.html", mode="new", post=None)


@app.post("/ui/public-board/new")
def board_new_submit():
    guard = _require_login()
    if guard: return guard

    payload = {
        "title":   request.form.get("title",   "").strip(),
        "content": request.form.get("content", "").strip(),
    }
    resp = req.post(f"{BOARD_URL}/posts", json=payload,
                    headers=_auth_header(), timeout=5)

    if resp.status_code == 201:
        flash("게시글이 등록되었습니다.", "success")
        return redirect(url_for("board_detail", post_id=resp.json()["id"]))

    flash(resp.json().get("error", "등록 실패"), "error")
    return redirect(url_for("board_new_form"))


@app.get("/ui/public-board/<int:post_id>")
def board_detail(post_id):
    guard = _require_login()
    if guard: return guard

    resp = req.get(f"{BOARD_URL}/posts/{post_id}", headers=_auth_header(), timeout=5)
    if resp.status_code == 404:
        flash("존재하지 않는 게시글입니다.", "error")
        return redirect(url_for("board_list"))

    p        = type("Post", (), resp.json())()
    can_edit = (session.get("role") == "admin" or session.get("user_id") == p.user_id)
    return render_template("board_detail.html", post=p, can_edit=can_edit,
                           username=session.get("username"))


@app.get("/ui/public-board/<int:post_id>/edit")
def board_edit_form(post_id):
    guard = _require_login()
    if guard: return guard

    resp = req.get(f"{BOARD_URL}/posts/{post_id}", headers=_auth_header(), timeout=5)
    p    = type("Post", (), resp.json())()
    return render_template("board_form.html", mode="edit", post=p)


@app.post("/ui/public-board/<int:post_id>/edit")
def board_edit_submit(post_id):
    guard = _require_login()
    if guard: return guard

    payload = {
        "title":   request.form.get("title",   "").strip(),
        "content": request.form.get("content", "").strip(),
    }
    req.patch(f"{BOARD_URL}/posts/{post_id}", json=payload,
              headers=_auth_header(), timeout=5)

    flash("수정되었습니다.", "success")
    return redirect(url_for("board_detail", post_id=post_id))


@app.post("/ui/public-board/<int:post_id>/delete")
def board_delete(post_id):
    guard = _require_login()
    if guard: return guard

    req.delete(f"{BOARD_URL}/posts/{post_id}", headers=_auth_header(), timeout=5)

    flash("삭제되었습니다.", "success")
    return redirect(url_for("board_list"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8004, debug=True)
