"""
Create (or update) a user — needed until the Admin Dashboard's user
management screen exists. Useful right now mainly for creating a staff
account to log into the Staff Dashboard with.

Usage:
    cd server
    python create_user.py <username> <password> <full_name> <role> [department_id]

    role is one of: admin | receptionist | staff
    department_id is required for staff (it decides which queue they see).
    Run `python list_departments.py` first if you don't know the IDs
    (or just check departments via GET /departments/ while the server runs).

Examples:
    python create_user.py nurse1 nurse123 "Nurse Joy" staff 1
    python create_user.py frontdesk front123 "Reception Desk" receptionist

If the username already exists, this updates their password/name/role/
department instead of failing, so you can also use it to fix a user.
"""
import sys

from db.database import Base, engine, SessionLocal
from db import models
from routers.users import hash_password

VALID_ROLES = {"admin", "receptionist", "staff"}


def _ensure_departments_seeded(db):
    """If this DB has never been touched by the actual server (so its
    startup seeding never ran), seed the same default departments here
    too, so this script works standalone."""
    if db.query(models.Department).count() == 0:
        db.add_all([
            models.Department(name="Laboratory", avg_consultation_minutes=20),
            models.Department(name="Radiology", avg_consultation_minutes=25),
            models.Department(name="TB DOTS Unit", avg_consultation_minutes=10),
            models.Department(name="Outpatient Department (OPD)", avg_consultation_minutes=15),
        ])
        db.commit()


def create_user(username, password, full_name, role, department_id=None):
    if role not in VALID_ROLES:
        print(f"Role must be one of {sorted(VALID_ROLES)}, got '{role}'")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_departments_seeded(db)

        if department_id is not None:
            dept = db.get(models.Department, int(department_id))
            if not dept:
                depts = db.query(models.Department).all()
                print(f"No department with id={department_id}. Available departments:")
                for d in depts:
                    print(f"  {d.id}: {d.name}")
                return

        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            user.password_hash = hash_password(password)
            user.full_name = full_name
            user.role = role
            user.department_id = int(department_id) if department_id is not None else None
            user.active = True
            db.commit()
            print(f"Updated existing user '{username}' (id={user.id}).")
        else:
            user = models.User(
                username=username,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
                department_id=int(department_id) if department_id is not None else None,
            )
            db.add(user)
            db.commit()
            print(f"Created user '{username}'.")

        print(f"Login with username '{username}' and password '{password}'.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    username, password, full_name, role = sys.argv[1:5]
    department_id = sys.argv[5] if len(sys.argv) > 5 else None
    create_user(username, password, full_name, role, department_id)