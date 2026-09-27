from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, date as date_cls
from typing import Optional

from db.database import get_db
from db import models

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_date(date_str: Optional[str]) -> date_cls:
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    return date_cls.today()


@router.get("/daily-summary")
def daily_summary(report_date: Optional[str] = None, db: Session = Depends(get_db)):
    """report_date as YYYY-MM-DD; defaults to today. Per department:
    how many patients registered, their outcomes, and average wait time
    (check-in -> consultation start) and average consultation length
    (start -> complete), in minutes."""
    day = _parse_date(report_date)
    day_start = datetime.combine(day, datetime.min.time())
    day_end = datetime.combine(day, datetime.max.time())

    departments = db.query(models.Department).all()
    results = []
    for dept in departments:
        entries = (
            db.query(models.QueueEntry)
            .filter(
                models.QueueEntry.department_id == dept.id,
                models.QueueEntry.check_in_time >= day_start,
                models.QueueEntry.check_in_time <= day_end,
            )
            .all()
        )

        wait_times = [
            (e.started_at - e.check_in_time).total_seconds() / 60
            for e in entries if e.started_at and e.check_in_time
        ]
        consult_times = [
            (e.completed_at - e.started_at).total_seconds() / 60
            for e in entries if e.completed_at and e.started_at
        ]

        results.append({
            "department_id": dept.id,
            "department_name": dept.name,
            "total_registered": len(entries),
            "done": len([e for e in entries if e.status == "done"]),
            "no_show": len([e for e in entries if e.status == "no_show"]),
            "cancelled": len([e for e in entries if e.status == "cancelled"]),
            "waiting": len([e for e in entries if e.status == "waiting"]),
            "in_consultation": len([e for e in entries if e.status == "in_consultation"]),
            "avg_wait_minutes": round(sum(wait_times) / len(wait_times), 1) if wait_times else None,
            "avg_consultation_minutes": round(sum(consult_times) / len(consult_times), 1) if consult_times else None,
        })

    return {"date": day.isoformat(), "departments": results}