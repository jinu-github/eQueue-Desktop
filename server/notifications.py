"""Formats SMS templates with patient/queue context, sends them, and logs
the result — used by routers/queue.py at each lifecycle point."""
from sqlalchemy.orm import Session
from datetime import datetime

from db import models
from sms_provider import send_sms, SmsSendError, ENV_DEFAULTS


def get_sms_config(db: Session) -> dict:
    """Live SMS config from the DB (editable via the admin dashboard),
    falling back to .env defaults if the settings row doesn't exist yet
    for some reason."""
    row = db.query(models.SmsSettings).get(1)
    if not row:
        return dict(ENV_DEFAULTS)
    return {"provider": row.provider, "api_key": row.api_key, "sender_name": row.sender_name}


def _format_message(template_content: str, patient, entry, department) -> str:
    return template_content.format(
        name=patient.first_name,
        full_name=f"{patient.first_name} {patient.last_name}",
        queue_number=entry.queue_number,
        department=department.name,
    )


def notify(db: Session, entry: "models.QueueEntry", template_type: str):
    """Looks up the department's template for this event type and sends it
    to the patient, if a template exists. Silently no-ops if there isn't
    one configured yet, so this is always safe to call."""
    template = (
        db.query(models.SmsTemplate)
        .filter(
            models.SmsTemplate.department_id == entry.department_id,
            models.SmsTemplate.template_type == template_type,
        )
        .first()
    )
    if not template:
        return

    patient = db.query(models.Patient).get(entry.patient_id)
    department = db.query(models.Department).get(entry.department_id)
    if not patient or not department:
        return

    try:
        message = _format_message(template.content, patient, entry, department)
    except (KeyError, IndexError):
        # Template has a placeholder we don't support (e.g. {typo}) — log
        # as failed rather than crashing the request that triggered this.
        db.add(models.SmsLog(
            patient_id=patient.id, message=template.content, status="failed",
            sent_at=datetime.utcnow(),
        ))
        db.commit()
        return

    try:
        send_sms(patient.contact_number, message, get_sms_config(db))
        status = "sent"
    except SmsSendError:
        status = "failed"

    db.add(models.SmsLog(
        patient_id=patient.id, message=message, status=status, sent_at=datetime.utcnow(),
    ))
    db.commit()


def notify_next_in_line(db: Session, department_id: int, just_completed_entry_id: int):
    """After an entry finishes (done/cancelled/no_show), send the 'almost
    your turn' notice to whoever is now first in that department's queue."""
    next_entry = (
        db.query(models.QueueEntry)
        .filter(
            models.QueueEntry.department_id == department_id,
            models.QueueEntry.status == "waiting",
            models.QueueEntry.id != just_completed_entry_id,
        )
        .order_by(models.QueueEntry.queue_number.asc())
        .first()
    )
    if next_entry:
        notify(db, next_entry, "proximity")