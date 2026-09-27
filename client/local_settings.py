"""
Per-machine settings that live outside the shared database — e.g. which
server this client points at. Stored in the user's home directory so each
reception/staff/admin machine can point at the LAN server independently.
"""
import json
import os

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from shared.constants import DEFAULT_SERVER_URL

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".equeue_client_settings.json")

DEFAULTS = {
    "server_url": DEFAULT_SERVER_URL,
    "staff_poll_seconds": 4,
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)