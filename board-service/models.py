"""
Post 모델
- user_id: auth-service 의 users.id (FK 없음 - 서비스 간 DB 분리)
- username: 작성 시점의 username을 비정규화하여 저장
  → auth-service 호출 없이 목록/상세 표시 가능
"""
from datetime import datetime
from extensions import db


class Post(db.Model):
    __tablename__ = "posts"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=False)          # auth-service users.id (논리적 참조)
    username   = db.Column(db.String(80), nullable=False)        # 비정규화: 목록 표시용
    title      = db.Column(db.String(200), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True,  onupdate=datetime.utcnow)
