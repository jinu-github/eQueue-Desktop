"""Shared enums/constants used by both the server and the PyQt client."""

class Role:
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    STAFF = "staff"

ALL_ROLES = [Role.ADMIN, Role.RECEPTIONIST, Role.STAFF]


class QueueStatus:
    WAITING = "waiting"
    IN_CONSULTATION = "in_consultation"
    DONE = "done"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

STATUS_COLORS = {
    QueueStatus.WAITING: "#f59e0b",         # amber
    QueueStatus.IN_CONSULTATION: "#3b82f6", # blue
    QueueStatus.DONE: "#22c55e",            # green
    QueueStatus.CANCELLED: "#94a3b8",       # slate
    QueueStatus.NO_SHOW: "#ef4444",         # red
}

STATUS_LABELS = {
    QueueStatus.WAITING: "Waiting",
    QueueStatus.IN_CONSULTATION: "In Consultation",
    QueueStatus.DONE: "Done",
    QueueStatus.CANCELLED: "Cancelled",
    QueueStatus.NO_SHOW: "No Show",
}

ROLE_ACCENT_COLORS = {
    Role.ADMIN: "#334155",         # slate
    Role.RECEPTIONIST: "#2563eb",  # blue
    Role.STAFF: "#16a34a",         # green
}

DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_WS_URL = "ws://localhost:8000/ws"
