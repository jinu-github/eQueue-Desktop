from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QGridLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from api_client import ApiClient, ApiError
from async_worker import run_async
from theme import Color
from ws_client import QueueWebSocketClient

REFRESH_MS = 5000  # public display doesn't need to be as snappy as staff view


class DepartmentPanel(QFrame):
    def __init__(self, department: dict):
        super().__init__()
        self.department_id = department["id"]
        self.setStyleSheet(f"QFrame {{ background-color: {Color.PANEL_BG}; border-radius: 16px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        name = QLabel(department["name"])
        name.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        name.setWordWrap(True)
        layout.addWidget(name)

        now_serving_label = QLabel("NOW SERVING")
        now_serving_label.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 13px; letter-spacing: 2px; margin-top: 8px;")
        layout.addWidget(now_serving_label)

        self.now_serving_number = QLabel("—")
        self.now_serving_number.setFont(QFont("IBM Plex Mono", 64, QFont.Weight.Bold))
        self.now_serving_number.setStyleSheet(f"color: {Color.BLUE_TEXT};")
        self.now_serving_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.now_serving_number)

        next_label = QLabel("NEXT UP")
        next_label.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 12px; letter-spacing: 2px; margin-top: 12px;")
        layout.addWidget(next_label)

        self.next_numbers = QLabel("—")
        self.next_numbers.setFont(QFont("IBM Plex Mono", 20, QFont.Weight.Bold))
        self.next_numbers.setStyleSheet(f"color: {Color.AMBER_TEXT};")
        self.next_numbers.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_numbers.setWordWrap(True)
        layout.addWidget(self.next_numbers)

    def update_from_entries(self, entries: list):
        serving = next((e for e in entries if e["status"] == "in_consultation"), None)
        self.now_serving_number.setText(f"#{serving['queue_number']}" if serving else "—")

        waiting = sorted((e for e in entries if e["status"] == "waiting"), key=lambda e: e["queue_number"])
        if waiting:
            self.next_numbers.setText("   ".join(f"#{e['queue_number']}" for e in waiting[:5]))
        else:
            self.next_numbers.setText("No one waiting")


class DisplayWindow(QWidget):
    """Public, read-only queue display — no login. Meant for a TV/monitor
    in the waiting room. Launch via client/display.py."""

    def __init__(self):
        super().__init__()
        self.api = ApiClient()
        self.setWindowTitle("eQueue — Now Serving")
        self.setStyleSheet(f"background-color: {Color.WINDOW_BG};")
        self.showMaximized()

        self.departments = []
        self.panels = {}
        self._build_ui()
        self._load_departments()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(REFRESH_MS)

        self._ws = QueueWebSocketClient(self.api.base_url)
        self._ws.message_received.connect(self._on_ws_message)
        self._ws.start()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 32)
        outer.setSpacing(20)

        header = QLabel("eQueue — Now Serving")
        header.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        outer.addWidget(header)

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(20)
        outer.addWidget(self.grid_container, stretch=1)

    def _load_departments(self):
        self._dept_worker = run_async(
            self.api.list_departments,
            on_success=self._on_departments_loaded,
            on_error=lambda e: None,
        )

    def _on_departments_loaded(self, departments):
        self.departments = departments

        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.panels = {}

        columns = 3
        for index, dept in enumerate(self.departments):
            panel = DepartmentPanel(dept)
            self.panels[dept["id"]] = panel
            self.grid.addWidget(panel, index // columns, index % columns)

        self._refresh()

    def _refresh(self):
        if not self.departments:
            self._load_departments()
            return
        self._refresh_worker = run_async(
            self.api.list_queue,
            on_success=self._on_queue_loaded,
            on_error=lambda e: None,  # keep showing last known state
        )

    def _on_queue_loaded(self, entries):
        for dept in self.departments:
            dept_entries = [e for e in entries if e["department_id"] == dept["id"]]
            panel = self.panels.get(dept["id"])
            if panel:
                panel.update_from_entries(dept_entries)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        self._ws.stop()
        super().closeEvent(event)

    def _on_ws_message(self, data: dict):
        if data.get("event") in ("queue_created", "queue_updated"):
            self._refresh()