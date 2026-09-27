from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from .database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    avg_consultation_minutes = Column(Integer, default=15)

    users = relationship("User", back_populates="department")
    queue_entries = relationship("QueueEntry", back_populates="department")
    sms_templates = relationship("SmsTemplate", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(20), nullable=False)  # admin | receptionist | staff
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="users")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=False)
    birthdate = Column(DateTime, nullable=True)
    gender = Column(String(20), nullable=True)
    civil_status = Column(String(30), nullable=True)
    contact_number = Column(String(20), nullable=False)
    address = Column(Text, nullable=True)
    guardian_name = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    queue_entries = relationship("QueueEntry", back_populates="patient")


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    staff_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    queue_number = Column(Integer, nullable=False)
    status = Column(String(20), default="waiting")
    reason_for_visit = Column(Text, nullable=True)

    blood_pressure = Column(String(20), nullable=True)
    temperature = Column(String(20), nullable=True)

    check_in_time = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="queue_entries")
    department = relationship("Department", back_populates="queue_entries")
    staff = relationship("User")


class SmsTemplate(Base):
    __tablename__ = "sms_templates"

    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    template_type = Column(String(30), nullable=False)  # welcome | proximity | your_turn | missed
    content = Column(Text, nullable=False)

    department = relationship("Department", back_populates="sms_templates")


class SmsLog(Base):
    __tablename__ = "sms_logs"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="sent")  # sent | failed
    sent_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    target = Column(String(200), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class SmsSettings(Base):
    """Single-row table (id is always 1) holding the live SMS provider
    config, editable from the admin dashboard without touching the server
    machine. Seeded from .env on first startup; after that, this table is
    the source of truth."""
    __tablename__ = "sms_settings"

    id = Column(Integer, primary_key=True, default=1)
    provider = Column(String(20), default="console")  # console | semaphore | iprog
    api_key = Column(String(255), default="")
    sender_name = Column(String(50), default="eQueue")
