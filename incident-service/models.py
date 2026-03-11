from datetime import datetime
from extensions import db


class Incident(db.Model):
    __tablename__ = "incidents"

    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(200), nullable=False)
    severity   = db.Column(db.String(20),  nullable=False, default="MEDIUM")
    status     = db.Column(db.String(20),  nullable=False, default="OPEN")
    created_at = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)

    logs = db.relationship("IncidentLog", backref="incident", cascade="all, delete-orphan")


class IncidentLog(db.Model):
    __tablename__ = "incident_logs"

    id          = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incidents.id"), nullable=False)
    action      = db.Column(db.Text,    nullable=False)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
