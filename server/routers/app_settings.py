from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from db import models
from audit import log_action

router = APIRouter(prefix="/app-settings", tags=["app-settings"])


@router.get("/")
def get_settings(db: Session = Depends(get_db)):
    row = db.query(models.AppSettings).get(1)
    if not row:
        row = models.AppSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"staff_poll_seconds": row.staff_poll_seconds}


class AppSettingsUpdate(BaseModel):
    staff_poll_seconds: int
    actor_id: Optional[int] = None


@router.patch("/")
def update_settings(payload: AppSettingsUpdate, db: Session = Depends(get_db)):
    row = db.query(models.AppSettings).get(1)
    if not row:
        row = models.AppSettings(id=1)
        db.add(row)

    row.staff_poll_seconds = payload.staff_poll_seconds
    db.commit()
    db.refresh(row)

    log_action(db, payload.actor_id, "Updated app settings", target=f"staff_poll_seconds={row.staff_poll_seconds}")
    return {"staff_poll_seconds": row.staff_poll_seconds}