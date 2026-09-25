from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from db import models

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("/")
def list_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).all()
