"""
INCIDENT SERVICE
- 담당: Incident CRUD + IncidentLog CRUD (JSON API)
- DB: incidents, incident_logs 테이블만 소유
- Port: 8002
- 인증: API Gateway가 JWT 검증 후 X-User-* 헤더로 사용자 정보 전달
"""
import os
from flask import Flask, request, jsonify
from extensions import db
from models import Incident, IncidentLog

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///incident.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

ALLOWED_SEVERITY = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ALLOWED_STATUS   = {"OPEN", "IN_PROGRESS", "CLOSED"}


# ── 헬퍼 ─────────────────────────────────────────────────
def _get_caller() -> dict:
    """
    API Gateway가 주입한 헤더에서 사용자 정보를 꺼냄.
    X-User-Id / X-User-Role
    """
    return {
        "user_id": request.headers.get("X-User-Id"),
        "role":    request.headers.get("X-User-Role", "user"),
    }

def _validate_enum(field: str, value: str, allowed: set):
    if value and value not in allowed:
        return jsonify({"error": f"invalid {field}", "allowed": sorted(allowed), "got": value}), 400
    return None

def _add_log(incident_id: int, action: str):
    db.session.add(IncidentLog(incident_id=incident_id, action=action))


# ── Health ──────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "incident"})


# ── Incident CRUD ────────────────────────────────────────
@app.get("/incidents")
def list_incidents():
    q        = request.args.get("q", "").strip()
    status   = request.args.get("status")
    severity = request.args.get("severity")

    if status:
        v = _validate_enum("status", status, ALLOWED_STATUS)
        if v: return v
    if severity:
        v = _validate_enum("severity", severity, ALLOWED_SEVERITY)
        if v: return v

    query = Incident.query
    if status:   query = query.filter(Incident.status == status)
    if severity: query = query.filter(Incident.severity == severity)
    if q:        query = query.filter(Incident.title.like(f"%{q}%"))

    items = query.order_by(Incident.id.desc()).all()
    return jsonify([{
        "id":         i.id,
        "title":      i.title,
        "severity":   i.severity,
        "status":     i.status,
        "created_at": i.created_at.isoformat(),
    } for i in items])


@app.post("/incidents")
def create_incident():
    caller = _get_caller()
    if caller["role"] != "admin":
        return jsonify({"error": "관리자만 생성 가능합니다"}), 403

    data     = request.get_json(force=True)
    title    = (data.get("title") or "").strip()
    severity = data.get("severity", "MEDIUM")
    status   = data.get("status",   "OPEN")

    if not title:
        return jsonify({"error": "title is required"}), 400

    v = _validate_enum("severity", severity, ALLOWED_SEVERITY)
    if v: return v
    v = _validate_enum("status", status, ALLOWED_STATUS)
    if v: return v

    inc = Incident(title=title, severity=severity, status=status)
    db.session.add(inc)
    db.session.flush()
    _add_log(inc.id, f"incident created (severity={severity}, status={status})")
    db.session.commit()

    return jsonify({"id": inc.id}), 201


@app.get("/incidents/<int:incident_id>")
def get_incident(incident_id):
    inc = Incident.query.get_or_404(incident_id)
    return jsonify({
        "id":         inc.id,
        "title":      inc.title,
        "severity":   inc.severity,
        "status":     inc.status,
        "created_at": inc.created_at.isoformat(),
    })


@app.patch("/incidents/<int:incident_id>")
def update_incident(incident_id):
    caller = _get_caller()
    if caller["role"] != "admin":
        return jsonify({"error": "관리자만 수정 가능합니다"}), 403

    inc  = Incident.query.get_or_404(incident_id)
    data = request.get_json(force=True)
    before = {"title": inc.title, "severity": inc.severity, "status": inc.status}

    if "title" in data:
        t = (data["title"] or "").strip()
        if not t:
            return jsonify({"error": "title cannot be empty"}), 400
        inc.title = t

    if "severity" in data:
        v = _validate_enum("severity", data["severity"], ALLOWED_SEVERITY)
        if v: return v
        inc.severity = data["severity"]

    if "status" in data:
        v = _validate_enum("status", data["status"], ALLOWED_STATUS)
        if v: return v
        inc.status = data["status"]

    changes = []
    for k in ("title", "severity", "status"):
        after = getattr(inc, k)
        if after != before[k]:
            changes.append(f"{k}: '{before[k]}' -> '{after}'")

    if changes:
        _add_log(inc.id, "updated: " + ", ".join(changes))

    db.session.commit()
    return jsonify({"ok": True, "changed": changes})


@app.delete("/incidents/<int:incident_id>")
def delete_incident(incident_id):
    caller = _get_caller()
    if caller["role"] != "admin":
        return jsonify({"error": "관리자만 삭제 가능합니다"}), 403

    inc = Incident.query.get_or_404(incident_id)
    db.session.delete(inc)
    db.session.commit()
    return jsonify({"ok": True})


# ── Incident Logs ────────────────────────────────────────
@app.get("/incidents/<int:incident_id>/logs")
def list_logs(incident_id):
    Incident.query.get_or_404(incident_id)
    logs = (IncidentLog.query
            .filter_by(incident_id=incident_id)
            .order_by(IncidentLog.id.asc())
            .all())
    return jsonify([{
        "id":          l.id,
        "incident_id": l.incident_id,
        "action":      l.action,
        "created_at":  l.created_at.isoformat(),
    } for l in logs])


@app.post("/incidents/<int:incident_id>/logs")
def add_log(incident_id):
    caller = _get_caller()
    if caller["role"] != "admin":
        return jsonify({"error": "관리자만 로그를 추가할 수 있습니다"}), 403

    Incident.query.get_or_404(incident_id)
    data   = request.get_json(force=True)
    action = (data.get("action") or "").strip()

    if not action:
        return jsonify({"error": "action is required"}), 400

    _add_log(incident_id, action)
    db.session.commit()
    return jsonify({"ok": True}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=True)
