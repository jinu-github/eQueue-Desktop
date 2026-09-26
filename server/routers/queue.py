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


def _serialize_entry(entry: models.QueueEntry) -> dict:
    """Include display-friendly names alongside the raw FKs so the UI
    doesn't need a round trip per card to show who a queue entry is for."""
    return {
        "id": entry.id,
        "patient_id": entry.patient_id,
        "patient_name": f"{entry.patient.first_name} {entry.patient.last_name}" if entry.patient else None,
        "department_id": entry.department_id,
        "department_name": entry.department.name if entry.department else None,
        "staff_id": entry.staff_id,
        "staff_name": entry.staff.full_name if entry.staff else None,
        "queue_number": entry.queue_number,
        "status": entry.status,
        "reason_for_visit": entry.reason_for_visit,
        "blood_pressure": entry.blood_pressure,
        "temperature": entry.temperature,
        "check_in_time": entry.check_in_time,
        "started_at": entry.started_at,
        "completed_at": entry.completed_at,
    }


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
    entries = q.order_by(models.QueueEntry.queue_number.asc()).all()
    return [_serialize_entry(e) for e in entries]


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
    return _serialize_entry(entry)


class StatusUpdate(BaseModel):
    status: str  # waiting | in_consultation | done | cancelled | no_show
    staff_id: Optional[int] = None
    # Optional optimistic-concurrency guard: the status the client believes
    # the entry is currently in. If another staff member changed it first
    # (e.g. two people both hit "Start" on the same waiting patient), this
    # will no longer match and the request is rejected with 409 instead of
    # silently overwriting whatever the other person just did.
    expected_status: Optional[str] = None


@router.patch("/{entry_id}/status")
async def update_status(entry_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    entry = db.query(models.QueueEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Queue entry not found")

    if payload.expected_status is not None and entry.status != payload.expected_status:
        raise HTTPException(
            409,
            f"This entry is already '{entry.status}' (expected '{payload.expected_status}'). "
            "Someone else may have just updated it — refresh and try again.",
        )

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
    return _serialize_entry(entry)
