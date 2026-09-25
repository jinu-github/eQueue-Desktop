from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

from db.database import get_db
from db import models
from websocket_manager import manager

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueCreate(BaseModel):
    patient_id: int
    department_id: int
    staff_id: Optional[int] = None
    reason_for_visit: Optional[str] = None
    blood_pressure: Optional[str] = None
    temperature: Optional[str] = None


def _next_queue_number(db: Session, department_id: int) -> int:
    """Daily queue number per department, resetting each day."""
    today_start = datetime.combine(date.today(), datetime.min.time())
    count = (
        db.query(func.count(models.QueueEntry.id))
        .filter(
            models.QueueEntry.department_id == department_id,
            models.QueueEntry.check_in_time >= today_start,
        )
        .scalar()
    )
    return count + 1


@router.get("/")
def list_queue(department_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.QueueEntry)
    if department_id:
        q = q.filter(models.QueueEntry.department_id == department_id)
    return q.order_by(models.QueueEntry.queue_number.asc()).all()


@router.post("/")
async def create_queue_entry(payload: QueueCreate, db: Session = Depends(get_db)):
    entry = models.QueueEntry(
        patient_id=payload.patient_id,
        department_id=payload.department_id,
        staff_id=payload.staff_id,
        reason_for_visit=payload.reason_for_visit,
        blood_pressure=payload.blood_pressure,
        temperature=payload.temperature,
        queue_number=_next_queue_number(db, payload.department_id),
        status="waiting",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    await manager.broadcast("queue_created", {"id": entry.id, "department_id": entry.department_id})
    return entry


class StatusUpdate(BaseModel):
    status: str  # waiting | in_consultation | done | cancelled | no_show
    staff_id: Optional[int] = None


@router.patch("/{entry_id}/status")
async def update_status(entry_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    entry = db.query(models.QueueEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Queue entry not found")

    if payload.status == "in_consultation":
        # enforce: only one patient "in_consultation" per staff at a time
        staff_id = payload.staff_id or entry.staff_id
        if staff_id:
            busy = (
                db.query(models.QueueEntry)
                .filter(
                    models.QueueEntry.staff_id == staff_id,
                    models.QueueEntry.status == "in_consultation",
                    models.QueueEntry.id != entry_id,
                )
                .first()
            )
            if busy:
                raise HTTPException(400, "This staff member already has a patient in consultation")
        entry.started_at = datetime.utcnow()

    if payload.status == "done":
        entry.completed_at = datetime.utcnow()

    entry.status = payload.status
    if payload.staff_id:
        entry.staff_id = payload.staff_id

    db.commit()
    db.refresh(entry)

    await manager.broadcast(
        "queue_updated",
        {"id": entry.id, "status": entry.status, "department_id": entry.department_id},
    )
    return entry
