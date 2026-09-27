from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from db.database import get_db
from db import models

router = APIRouter(prefix="/sms-logs", tags=["sms-logs"])


@router.get("/")
def list_sms_logs(patient_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(models.SmsLog)
    if patient_id:
        q = q.filter(models.SmsLog.patient_id == patient_id)
    return q.order_by(models.SmsLog.sent_at.desc()).limit(limit).all()