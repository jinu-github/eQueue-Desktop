from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from db.database import get_db
from db import models

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/")
def list_audit_logs(user_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(models.AuditLog)
    if user_id:
        q = q.filter(models.AuditLog.user_id == user_id)
    logs = q.order_by(models.AuditLog.timestamp.desc()).limit(limit).all()

    result = []
    for log in logs:
        user = db.query(models.User).get(log.user_id) if log.user_id else None
        result.append({
            "id": log.id,
            "user_id": log.user_id,
            "user_name": user.full_name if user else "System",
            "action": log.action,
            "target": log.target,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        })
    return result