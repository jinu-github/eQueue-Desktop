from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from db.database import get_db
from db import models
from audit import log_action

router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentCreate(BaseModel):
    name: str
    avg_consultation_minutes: int = 15
    actor_id: Optional[int] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    avg_consultation_minutes: Optional[int] = None
    actor_id: Optional[int] = None


@router.get("/")
def list_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).all()


@router.post("/")
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Department).filter(models.Department.name == payload.name).first()
    if existing:
        raise HTTPException(400, "A department with this name already exists")
    dept = models.Department(name=payload.name, avg_consultation_minutes=payload.avg_consultation_minutes)
    db.add(dept)
    db.commit()
    db.refresh(dept)

    log_action(db, payload.actor_id, "Created department", target=dept.name)
    return dept


@router.patch("/{department_id}")
def update_department(department_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db)):
    dept = db.query(models.Department).get(department_id)
    if not dept:
        raise HTTPException(404, "Department not found")
    for field, value in payload.dict(exclude_unset=True, exclude={"actor_id"}).items():
        setattr(dept, field, value)
    db.commit()
    db.refresh(dept)

    log_action(db, payload.actor_id, "Updated department", target=dept.name)
    return dept


@router.delete("/{department_id}")
def delete_department(department_id: int, actor_id: Optional[int] = None, db: Session = Depends(get_db)):
    dept = db.query(models.Department).get(department_id)
    if not dept:
        raise HTTPException(404, "Department not found")
    in_use = db.query(models.QueueEntry).filter(models.QueueEntry.department_id == department_id).first()
    if in_use:
        raise HTTPException(400, "Can't delete a department that has queue history. Consider renaming it instead.")
    name = dept.name
    db.delete(dept)
    db.commit()

    log_action(db, actor_id, "Deleted department", target=name)
    return {"deleted": True}