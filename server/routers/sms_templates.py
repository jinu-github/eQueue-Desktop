from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from db import models
from audit import log_action

router = APIRouter(prefix="/sms-templates", tags=["sms-templates"])

# Matches the original system's notification points.
TEMPLATE_TYPES = ["welcome", "proximity", "your_turn", "missed"]


class SmsTemplateCreate(BaseModel):
    department_id: int
    template_type: str
    content: str
    actor_id: Optional[int] = None


class SmsTemplateUpdate(BaseModel):
    content: Optional[str] = None
    actor_id: Optional[int] = None


@router.get("/")
def list_templates(department_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.SmsTemplate)
    if department_id:
        q = q.filter(models.SmsTemplate.department_id == department_id)
    return q.all()


@router.post("/")
def create_template(payload: SmsTemplateCreate, db: Session = Depends(get_db)):
    if payload.template_type not in TEMPLATE_TYPES:
        raise HTTPException(400, f"template_type must be one of {TEMPLATE_TYPES}")
    existing = (
        db.query(models.SmsTemplate)
        .filter(
            models.SmsTemplate.department_id == payload.department_id,
            models.SmsTemplate.template_type == payload.template_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(400, "A template of this type already exists for this department. Edit it instead.")
    template = models.SmsTemplate(
        department_id=payload.department_id,
        template_type=payload.template_type,
        content=payload.content,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    dept = db.query(models.Department).get(payload.department_id)
    log_action(db, payload.actor_id, "Created SMS template",
               target=f"{payload.template_type} ({dept.name if dept else payload.department_id})")
    return template


@router.patch("/{template_id}")
def update_template(template_id: int, payload: SmsTemplateUpdate, db: Session = Depends(get_db)):
    template = db.query(models.SmsTemplate).get(template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    if payload.content is not None:
        template.content = payload.content
    db.commit()
    db.refresh(template)

    dept = db.query(models.Department).get(template.department_id)
    log_action(db, payload.actor_id, "Updated SMS template",
               target=f"{template.template_type} ({dept.name if dept else template.department_id})")
    return template


@router.delete("/{template_id}")
def delete_template(template_id: int, actor_id: Optional[int] = None, db: Session = Depends(get_db)):
    template = db.query(models.SmsTemplate).get(template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    ttype = template.template_type
    dept = db.query(models.Department).get(template.department_id)
    db.delete(template)
    db.commit()

    log_action(db, actor_id, "Deleted SMS template", target=f"{ttype} ({dept.name if dept else '?'})")
    return {"deleted": True}