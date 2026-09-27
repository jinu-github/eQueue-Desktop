"""Single place to write audit log entries. Call this from a router right
after a state-changing action succeeds. user_id may be None for actions
where we don't yet have an authenticated actor (the app has no session/
token system - the client just tells us who's acting)."""
from sqlalchemy.orm import Session
from db import models


def log_action(db: Session, user_id, action: str, target: str = None):
    db.add(models.AuditLog(user_id=user_id, action=action, target=target))
    db.commit()