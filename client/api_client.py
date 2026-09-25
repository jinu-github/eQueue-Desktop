"""Thin HTTP client wrapper the PyQt UI uses to talk to the FastAPI server."""
import requests

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from shared.constants import DEFAULT_SERVER_URL


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_SERVER_URL):
        self.base_url = base_url.rstrip("/")

    def login(self, username: str, password: str) -> dict:
        r = requests.post(f"{self.base_url}/users/login", json={
            "username": username, "password": password
        })
        r.raise_for_status()
        return r.json()

    def list_departments(self) -> list:
        r = requests.get(f"{self.base_url}/departments/")
        r.raise_for_status()
        return r.json()

    def list_queue(self, department_id: int = None) -> list:
        params = {"department_id": department_id} if department_id else {}
        r = requests.get(f"{self.base_url}/queue/", params=params)
        r.raise_for_status()
        return r.json()

    def create_patient(self, patient_data: dict) -> dict:
        r = requests.post(f"{self.base_url}/patients/", json=patient_data)
        r.raise_for_status()
        return r.json()

    def create_queue_entry(self, queue_data: dict) -> dict:
        r = requests.post(f"{self.base_url}/queue/", json=queue_data)
        r.raise_for_status()
        return r.json()

    def update_status(self, entry_id: int, status: str, staff_id: int = None) -> dict:
        payload = {"status": status}
        if staff_id:
            payload["staff_id"] = staff_id
        r = requests.patch(f"{self.base_url}/queue/{entry_id}/status", json=payload)
        r.raise_for_status()
        return r.json()
