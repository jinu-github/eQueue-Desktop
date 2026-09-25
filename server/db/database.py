"""
Database connection setup.

For a LAN-shared deployment, point DATABASE_URL at your MySQL/Postgres
server, e.g.:
    postgresql+psycopg2://equeue_user:password@192.168.1.10:5432/equeue
    mysql+pymysql://equeue_user:password@192.168.1.10:3306/equeue

For local single-machine testing, SQLite works out of the box.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("EQUEUE_DATABASE_URL", "sqlite:///./equeue.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
