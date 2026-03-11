"""
BOARD SERVICE
- 담당: 커뮤니티 게시판 CRUD (JSON API)
- DB: posts 테이블만 소유
- Port: 8003
- 인증: API Gateway → X-User-Id / X-User-Role 헤더 주입
"""
import os
from flask import Flask, request, jsonify
from extensions import db
from models import Post

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///board.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


def _caller():
    return {
        "user_id": int(request.headers.get("X-User-Id", 0)),
        "role":    request.headers.get("X-User-Role", "user"),
        "username": request.headers.get("X-User-Name", "unknown"),
    }

def _can_edit(post: Post, caller: dict) -> bool:
    return caller["role"] == "admin" or caller["user_id"] == post.user_id


# ── Health ──────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "board"})


# ── 게시글 목록 ──────────────────────────────────────────
@app.get("/posts")
def list_posts():
    posts = Post.query.order_by(Post.id.desc()).all()
    return jsonify([{
        "id":         p.id,
        "user_id":    p.user_id,
        "username":   p.username,
        "title":      p.title,
        "content":    p.content,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    } for p in posts])


# ── 게시글 생성 ──────────────────────────────────────────
@app.post("/posts")
def create_post():
    caller = _caller()
    data   = request.get_json(force=True)

    title   = (data.get("title")   or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"error": "title과 content 모두 필요합니다"}), 400

    post = Post(
        user_id=caller["user_id"],
        username=caller["username"],
        title=title,
        content=content,
    )
    db.session.add(post)
    db.session.commit()

    return jsonify({"id": post.id}), 201


# ── 게시글 상세 ──────────────────────────────────────────
@app.get("/posts/<int:post_id>")
def get_post(post_id):
    p = Post.query.get_or_404(post_id)
    return jsonify({
        "id":         p.id,
        "user_id":    p.user_id,
        "username":   p.username,
        "title":      p.title,
        "content":    p.content,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    })


# ── 게시글 수정 ──────────────────────────────────────────
@app.patch("/posts/<int:post_id>")
def update_post(post_id):
    caller = _caller()
    p      = Post.query.get_or_404(post_id)

    if not _can_edit(p, caller):
        return jsonify({"error": "작성자(또는 관리자)만 수정할 수 있습니다"}), 403

    data    = request.get_json(force=True)
    title   = (data.get("title")   or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"error": "title과 content 모두 필요합니다"}), 400

    p.title   = title
    p.content = content
    db.session.commit()

    return jsonify({"ok": True})


# ── 게시글 삭제 ──────────────────────────────────────────
@app.delete("/posts/<int:post_id>")
def delete_post(post_id):
    caller = _caller()
    p      = Post.query.get_or_404(post_id)

    if not _can_edit(p, caller):
        return jsonify({"error": "작성자(또는 관리자)만 삭제할 수 있습니다"}), 403

    db.session.delete(p)
    db.session.commit()

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003, debug=True)
