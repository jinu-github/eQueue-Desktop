"""
Reset the 'admin' account's password back to a known value without
touching any other data (patients, queue history, other users, etc).

Use this if the default admin/admin123 login stops working — it usually
means a local equeue.db already has an 'admin' row from an earlier run
whose password doesn't match what you'd expect, and the normal startup
seeding won't touch an admin account that already exists.

Usage:
    cd server
    python reset_admin.py                  # resets to admin123
    python reset_admin.py MyNewPassword     # resets to a password you choose

If no 'admin' user exists yet, this creates one (same as the normal
startup seed would).
"""
import sys

from db.database import Base, engine, SessionLocal
from db import models
from routers.users import hash_password


def reset_admin(new_password: str = "admin123") -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if admin:
            admin.password_hash = hash_password(new_password)
            admin.active = True
            db.commit()
            print(f"Updated existing 'admin' user (id={admin.id}). Password reset.")
        else:
            admin = models.User(
                username="admin",
                password_hash=hash_password(new_password),
                full_name="System Administrator",
                role="admin",
            )
            db.add(admin)
            db.commit()
            print("No 'admin' user existed — created one.")
        print(f"Login with username 'admin' and password '{new_password}'.")
    finally:
        db.close()


if __name__ == "__main__":
    pw = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    reset_admin(pw)