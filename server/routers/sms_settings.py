from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from db import models
from sms_provider import send_sms, SmsSendError
from notifications import get_sms_config
from audit import log_action

router = APIRouter(prefix="/sms-settings", tags=["sms-settings"])

PROVIDERS = ["console", "semaphore", "iprog"]


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


@router.get("/")
def get_settings(db: Session = Depends(get_db)):
    row = db.query(models.SmsSettings).get(1)
    if not row:
        row = models.SmsSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return {
        "provider": row.provider,
        "api_key_masked": _mask(row.api_key),
        "sender_name": row.sender_name,
    }


class SmsSettingsUpdate(BaseModel):
    provider: str
    api_key: Optional[str] = None
    sender_name: Optional[str] = None
    actor_id: Optional[int] = None


@router.patch("/")
def update_settings(payload: SmsSettingsUpdate, db: Session = Depends(get_db)):
    if payload.provider not in PROVIDERS:
        raise HTTPException(400, f"provider must be one of {PROVIDERS}")

    row = db.query(models.SmsSettings).get(1)
    if not row:
        row = models.SmsSettings(id=1)
        db.add(row)

    row.provider = payload.provider
    if payload.api_key:
        row.api_key = payload.api_key
    if payload.sender_name is not None:
        row.sender_name = payload.sender_name

    db.commit()
    db.refresh(row)

    log_action(db, payload.actor_id, "Updated SMS settings", target=f"provider={row.provider}")
    return {
        "provider": row.provider,
        "api_key_masked": _mask(row.api_key),
        "sender_name": row.sender_name,
    }

class TestSmsRequest(BaseModel):
    phone_number: str


@router.post("/test")
def send_test_sms(payload: TestSmsRequest, db: Session = Depends(get_db)):
    config = get_sms_config(db)
    message = "This is a test message from eQueue. If you received this, SMS is working."
    try:
        send_sms(payload.phone_number, message, config)
    except SmsSendError as e:
        raise HTTPException(502, f"Test SMS failed: {e}")
    return {"sent": True, "provider": config["provider"]}