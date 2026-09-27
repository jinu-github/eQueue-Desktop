from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from typing import Optional
import hashlib

from db.database import get_db
from db import models
from audit import log_action

router = APIRouter(prefix="/users", tags=["users"])


def hash_password(raw: str) -> str:
    # NOTE: for a real deployment use bcrypt/argon2 (e.g. passlib) instead.
    return hashlib.sha256(raw.encode()).hexdigest()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str
    department_id: Optional[int] = None
    created_by_id: Optional[int] = None  # who's creating this account, for the audit log


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.username == payload.username).first()
    except SQLAlchemyError:
        # DB unreachable / connection refused / table missing, etc. Distinct from
        # "wrong credentials" so the client can show an accurate message.
        raise HTTPException(503, "Database unavailable")

    if not user or user.password_hash != hash_password(payload.password) or not user.active:
        raise HTTPException(401, "Invalid username or password")
    
    log_action(db, user.id, "Logged in", target=user.username)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "department_id": user.department_id,
    }


@router.post("/")
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(400, "Username already taken")
    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        department_id=payload.department_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, payload.created_by_id, "Created account", target=f"{user.username} ({user.role})")
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/")
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()