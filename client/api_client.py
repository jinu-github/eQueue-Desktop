"""Thin HTTP client wrapper the PyQt UI uses to talk to the FastAPI server."""
import requests

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from shared.constants import DEFAULT_SERVER_URL

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
    def __init__(self, base_url: str = DEFAULT_SERVER_URL):
        self.base_url = base_url.rstrip("/")

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

    def login(self, username: str, password: str) -> dict:
        return self._request("POST", "/users/login", json={"username": username, "password": password})

    def list_departments(self) -> list:
        return self._request("GET", "/departments/")

    def list_queue(self, department_id: int = None) -> list:
        params = {"department_id": department_id} if department_id else {}
        return self._request("GET", "/queue/", params=params)

    def create_patient(self, patient_data: dict) -> dict:
        return self._request("POST", "/patients/", json=patient_data)

    def create_queue_entry(self, queue_data: dict) -> dict:
        return self._request("POST", "/queue/", json=queue_data)

    def update_status(self, entry_id: int, status: str, staff_id: int = None, expected_status: str = None) -> dict:
        payload = {"status": status}
        if staff_id:
            payload["staff_id"] = staff_id
        if expected_status:
            payload["expected_status"] = expected_status
        return self._request("PATCH", f"/queue/{entry_id}/status", json=payload)
