from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

from db.database import get_db
from db import models
from websocket_manager import manager
from notifications import notify, notify_next_in_line
from audit import log_action

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueCreate(BaseModel):
    patient_id: int
    department_id: int
    staff_id: Optional[int] = None
    reason_for_visit: Optional[str] = None
    blood_pressure: Optional[str] = None
    temperature: Optional[str] = None
    registered_by_id: Optional[int] = None  # for the audit log


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


def _serialize(entry: models.QueueEntry) -> dict:
    patient = entry.patient
    return {
        "id": entry.id,
        "patient_id": entry.patient_id,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "department_id": entry.department_id,
        "staff_id": entry.staff_id,
        "queue_number": entry.queue_number,
        "status": entry.status,
        "reason_for_visit": entry.reason_for_visit,
        "blood_pressure": entry.blood_pressure,
        "temperature": entry.temperature,
        "check_in_time": entry.check_in_time.isoformat() if entry.check_in_time else None,
        "started_at": entry.started_at.isoformat() if entry.started_at else None,
        "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
    }


@router.get("/")
def list_queue(department_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.QueueEntry)
    if department_id:
        q = q.filter(models.QueueEntry.department_id == department_id)
    entries = q.order_by(models.QueueEntry.queue_number.asc()).all()
    return [_serialize(e) for e in entries]


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

    patient = entry.patient
    dept = db.query(models.Department).get(payload.department_id)
    log_action(
        db, payload.registered_by_id, "Registered patient",
        target=f"{patient.first_name} {patient.last_name} -> {dept.name if dept else '?'} (#{entry.queue_number})"
    )

    notify(db, entry, "welcome")
    await manager.broadcast("queue_created", {"id": entry.id, "department_id": entry.department_id})
    return _serialize(entry)


class StatusUpdate(BaseModel):
    status: str  # waiting | in_consultation | done | cancelled | no_show
    staff_id: Optional[int] = None
    expected_status: Optional[str] = None  # optimistic-concurrency guard


@router.patch("/{entry_id}/status")
async def update_status(entry_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    entry = db.query(models.QueueEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Queue entry not found")

    if payload.expected_status is not None and entry.status != payload.expected_status:
        raise HTTPException(
            409,
            f"This entry was already changed to '{entry.status}' by someone else.",
        )

    if payload.status == "in_consultation":
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

    log_action(
        db, payload.staff_id, f"Changed queue status to '{payload.status}'",
        target=f"#{entry.queue_number} ({entry.patient.first_name} {entry.patient.last_name})" if entry.patient else f"#{entry.queue_number}"
    )

    if payload.status == "in_consultation":
        notify(db, entry, "your_turn")
    elif payload.status == "no_show":
        notify(db, entry, "missed")

    if payload.status in ("in_consultation", "done", "cancelled", "no_show"):
        notify_next_in_line(db, entry.department_id, entry.id)

    await manager.broadcast(
        "queue_updated",
        {"id": entry.id, "status": entry.status, "department_id": entry.department_id},
    )
    return _serialize(entry)