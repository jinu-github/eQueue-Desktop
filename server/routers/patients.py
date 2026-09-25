from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from db.database import get_db
from db import models

router = APIRouter(prefix="/patients", tags=["patients"])


class PatientCreate(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    birthdate: Optional[datetime] = None
    gender: Optional[str] = None
    civil_status: Optional[str] = None
    contact_number: str
    address: Optional[str] = None
    guardian_name: Optional[str] = None


@router.get("/")
def list_patients(db: Session = Depends(get_db)):
    return db.query(models.Patient).order_by(models.Patient.id.desc()).all()


@router.get("/{patient_id}")
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.Patient).get(patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    return patient


@router.post("/")
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    patient = models.Patient(**payload.dict())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient
