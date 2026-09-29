"""
Pluggable SMS sending.

Config (provider / api key / sender name) is stored in the sms_settings
table, editable live from the admin dashboard -> SMS Settings tab. On
first startup that table is seeded from these env vars, which then just
serve as the initial defaults / fallback if the table is ever empty:

  EQUEUE_SMS_PROVIDER   console | semaphore | iprog  (default: console)
  EQUEUE_SMS_API_KEY
  EQUEUE_SMS_SENDER_NAME  (Semaphore only)

"console" doesn't call any API, just prints the message - lets you
develop/test the whole notification flow with no SMS account.
"""
import os
import requests

ENV_DEFAULTS = {
    "provider": os.environ.get("EQUEUE_SMS_PROVIDER", "console"),
    "api_key": os.environ.get("EQUEUE_SMS_API_KEY", ""),
    "sender_name": os.environ.get("EQUEUE_SMS_SENDER_NAME", "eQueue"),
}


class SmsSendError(Exception):
    pass


def _send_console(number: str, message: str, config: dict):
    print(f"[SMS:console] to {number}: {message}")


def _send_semaphore(number: str, message: str, config: dict):
    r = requests.post("https://api.semaphore.co/api/v4/messages", data={
        "apikey": config["api_key"],
        "number": number,
        "message": message,
        "sendername": config["sender_name"],
    }, timeout=10)
    if r.status_code >= 300:
        raise SmsSendError(f"Semaphore error {r.status_code}: {r.text}")


def _send_iprog(number: str, message: str, config: dict):
    r = requests.post("https://sms.iprogtech.com/api/v1/sms_messages", data={
        "api_token": config["api_key"],
        "phone_number": number,
        "message": message,
        "sms_provider": 0,  # IPROG's documented default; 1 may route through
                             # a provider your account isn't set up for
    }, timeout=10)

    if r.status_code >= 300:
        raise SmsSendError(f"IPROG HTTP error {r.status_code}: {r.text}")

    # IPROG returns HTTP 200 even on failure - the real result is in the
    # JSON body, e.g. {"status": 500, "message": "Invalid Token"} or
    # {"status": "error", ...}. A real success looks like {"status": 200, ...}.
    try:
        body = r.json()
    except ValueError:
        raise SmsSendError(f"IPROG returned a non-JSON response: {r.text}")

    status = body.get("status")
    if status not in (200, "success"):
        raise SmsSendError(f"IPROG rejected the message: {body.get('message', body)}")


_PROVIDERS = {
    "console": _send_console,
    "semaphore": _send_semaphore,
    "iprog": _send_iprog,
}


def send_sms(number: str, message: str, config: dict):
    """config is a dict with "provider", "api_key", "sender_name" - get it
    from get_sms_config(db) in notifications.py. Raises SmsSendError on
    failure; caller decides how to log/handle it."""
    sender = _PROVIDERS.get(config["provider"])
    if not sender:
        raise SmsSendError(f"Unknown SMS provider '{config['provider']}'")
    sender(number, message, config)