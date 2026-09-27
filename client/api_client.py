"""Thin HTTP client wrapper the PyQt UI uses to talk to the FastAPI server."""
import requests

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from shared.constants import DEFAULT_SERVER_URL
from local_settings import load_settings

# Every request gets this timeout so the UI never just hangs when the
# server is up but not responding (as opposed to refusing the connection
# outright, which raises immediately).
REQUEST_TIMEOUT = 5


class ApiError(Exception):
    """Base class for errors ApiClient raises, so UI code can catch this
    alone if it doesn't care about the distinction."""


class ServerUnreachableError(ApiError):
    """Could not connect to the server at all (wrong host/port, server
    not running, firewall, etc.)."""


class ServerTimeoutError(ApiError):
    """Connected, but the server didn't respond in time."""


class InvalidCredentialsError(ApiError):
    """Server responded 401: username/password combination is wrong."""


class ServiceUnavailableError(ApiError):
    """Server responded 503: e.g. its database is unreachable."""


class ConflictError(ApiError):
    """Server responded 409: the resource changed since the client last
    saw it (e.g. another staff member already claimed this queue entry)."""


class ServerError(ApiError):
    """Server reached but returned an unexpected error (4xx/5xx other
    than the above, or a malformed response)."""


class ApiClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or load_settings()["server_url"]).rstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Shared request path: consistent timeout + typed exceptions for
        every endpoint, not just login."""
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        try:
            r = requests.request(method, f"{self.base_url}{path}", **kwargs)
        except requests.exceptions.Timeout:
            raise ServerTimeoutError(f"No response from {self.base_url} within {REQUEST_TIMEOUT}s")
        except requests.exceptions.ConnectionError as e:
            raise ServerUnreachableError(f"Could not reach {self.base_url}: {e}")

        if r.status_code == 401:
            raise InvalidCredentialsError(r.json().get("detail", "Invalid username or password"))
        if r.status_code == 409:
            raise ConflictError(r.json().get("detail", "Conflict: this record was changed by someone else"))
        if r.status_code == 503:
            raise ServiceUnavailableError(r.json().get("detail", "Service unavailable"))
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            detail = r.json().get("detail", str(e)) if r.content else str(e)
            raise ServerError(f"Unexpected server error ({r.status_code}): {detail}")

        return r.json() if r.content else {}

    # --- auth ---------------------------------------------------------

    def login(self, username: str, password: str) -> dict:
        return self._request("POST", "/users/login", json={"username": username, "password": password})

    # --- patients / queue ----------------------------------------------

    def create_patient(self, patient_data: dict) -> dict:
        return self._request("POST", "/patients/", json=patient_data)

    def list_queue(self, department_id: int = None) -> list:
        params = {"department_id": department_id} if department_id else {}
        return self._request("GET", "/queue/", params=params)

    def create_queue_entry(self, queue_data: dict) -> dict:
        return self._request("POST", "/queue/", json=queue_data)

    def update_status(self, entry_id: int, status: str, staff_id: int = None, expected_status: str = None) -> dict:
        payload = {"status": status}
        if staff_id:
            payload["staff_id"] = staff_id
        if expected_status is not None:
            payload["expected_status"] = expected_status
        return self._request("PATCH", f"/queue/{entry_id}/status", json=payload)

    # --- users ----------------------------------------------------------

    def create_user(self, user_data: dict) -> dict:
        return self._request("POST", "/users/", json=user_data)

    def list_users(self) -> list:
        return self._request("GET", "/users/")

    # --- departments ------------------------------------------------------

    def list_departments(self) -> list:
        return self._request("GET", "/departments/")

    def create_department(self, name: str, avg_consultation_minutes: int = 15, actor_id: int = None) -> dict:
        payload = {"name": name, "avg_consultation_minutes": avg_consultation_minutes}
        if actor_id is not None:
            payload["actor_id"] = actor_id
        return self._request("POST", "/departments/", json=payload)

    def update_department(self, department_id: int, actor_id: int = None, **fields) -> dict:
        if actor_id is not None:
            fields["actor_id"] = actor_id
        return self._request("PATCH", f"/departments/{department_id}", json=fields)

    def delete_department(self, department_id: int, actor_id: int = None) -> dict:
        params = {"actor_id": actor_id} if actor_id is not None else {}
        return self._request("DELETE", f"/departments/{department_id}", params=params)

    # --- SMS templates ------------------------------------------------------

    def list_sms_templates(self, department_id: int = None) -> list:
        params = {"department_id": department_id} if department_id else {}
        return self._request("GET", "/sms-templates/", params=params)

    def create_sms_template(self, department_id: int, template_type: str, content: str, actor_id: int = None) -> dict:
        payload = {"department_id": department_id, "template_type": template_type, "content": content}
        if actor_id is not None:
            payload["actor_id"] = actor_id
        return self._request("POST", "/sms-templates/", json=payload)

    def update_sms_template(self, template_id: int, content: str, actor_id: int = None) -> dict:
        payload = {"content": content}
        if actor_id is not None:
            payload["actor_id"] = actor_id
        return self._request("PATCH", f"/sms-templates/{template_id}", json=payload)

    def delete_sms_template(self, template_id: int, actor_id: int = None) -> dict:
        params = {"actor_id": actor_id} if actor_id is not None else {}
        return self._request("DELETE", f"/sms-templates/{template_id}", params=params)

    # --- SMS provider settings ------------------------------------------

    def get_sms_settings(self) -> dict:
        return self._request("GET", "/sms-settings/")

    def update_sms_settings(self, provider: str, api_key: str = None, sender_name: str = None, actor_id: int = None) -> dict:
        payload = {"provider": provider}
        if api_key:
            payload["api_key"] = api_key
        if sender_name is not None:
            payload["sender_name"] = sender_name
        if actor_id is not None:
            payload["actor_id"] = actor_id
        return self._request("PATCH", "/sms-settings/", json=payload)

    def send_test_sms(self, phone_number: str) -> dict:
        return self._request("POST", "/sms-settings/test", json={"phone_number": phone_number})

    # --- reports & audit -------------------------------------------------

    def get_daily_summary(self, report_date: str = None) -> dict:
        params = {"report_date": report_date} if report_date else {}
        return self._request("GET", "/reports/daily-summary", params=params)

    def list_audit_logs(self, limit: int = 100) -> list:
        return self._request("GET", "/audit-logs/", params={"limit": limit})