from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.constants import STATUS_COLORS
from api_client import ApiClient, ApiError, ConflictError
from async_worker import run_async
from theme import Color, PRIMARY_BTN_STYLE, SECONDARY_BTN_STYLE, DANGER_SOLID_BTN_STYLE, SIDEBAR_STYLE, LOGOUT_BTN_STYLE, role_badge_style
from ws_client import QueueWebSocketClient

# How often the dashboard polls the server for queue changes.
REFRESH_MS = 3000


def _fmt_time(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return str(value)


class WaitingCard(QFrame):
    """A waiting patient's queue card with staff action buttons."""

    def __init__(self, entry: dict, on_start, on_no_show, on_cancel, start_enabled: bool):
        super().__init__()
        color = STATUS_COLORS.get(entry["status"], "#8fa3b0")
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Color.PANEL_BG};
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        number = QLabel(f"#{entry['queue_number']}")
        number.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        number.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        number.setFixedWidth(56)

        info = QVBoxLayout()
        name = QLabel(entry.get("patient_name") or f"Patient #{entry['patient_id']}")
        name.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; font-weight: 600; font-size: 14px;")
        reason = QLabel(entry.get("reason_for_visit") or "No reason given")
        reason.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 12px;")
        checked_in = QLabel(f"Checked in {_fmt_time(entry.get('check_in_time'))}")
        checked_in.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 11px;")
        info.addWidget(name)
        info.addWidget(reason)
        info.addWidget(checked_in)

        layout.addWidget(number)
        layout.addLayout(info)
        layout.addStretch()

        # "Start" is a primary action — same blue as every other primary
        # button in the app, not a status color.
        start_btn = QPushButton("Start")
        start_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        start_btn.setEnabled(start_enabled)
        start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        start_btn.clicked.connect(lambda: on_start(entry))

        no_show_btn = QPushButton("No-show")
        no_show_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        no_show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        no_show_btn.clicked.connect(lambda: on_no_show(entry))

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(DANGER_SOLID_BTN_STYLE)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(lambda: on_cancel(entry))

        for b in (start_btn, no_show_btn, cancel_btn):
            layout.addWidget(b)


class CurrentlyServingPanel(QFrame):
    """Shows the patient this staff member currently has in consultation,
    or a 'call next' prompt if they're free."""

    def __init__(self, on_call_next, on_complete):
        super().__init__()
        self.on_call_next = on_call_next
        self.on_complete = on_complete
        self.setStyleSheet(f"QFrame {{ background-color: {Color.PANEL_BG}; border-radius: 12px; }}")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(10)
        self.set_entry(None)

    def _clear(self):
        while self.layout_.count():
            item = self.layout_.takeAt(0)

            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())


    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)

            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def set_entry(self, entry):
        self._clear()

        title = QLabel("Currently Serving")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        self.layout_.addWidget(title)

        if entry is None:
            empty = QLabel("You're not seeing anyone right now.")
            empty.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
            self.layout_.addWidget(empty)

            call_btn = QPushButton("Call Next Patient")
            call_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            call_btn.setMinimumHeight(42)
            call_btn.setStyleSheet(PRIMARY_BTN_STYLE)
            call_btn.clicked.connect(self.on_call_next)
            self.layout_.addWidget(call_btn)
            return

        row = QHBoxLayout()
        number = QLabel(f"#{entry['queue_number']}")
        number.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        number.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        number.setFixedWidth(90)
        row.addWidget(number)

        info = QVBoxLayout()
        name = QLabel(entry.get("patient_name") or f"Patient #{entry['patient_id']}")
        name.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        reason = QLabel(f"Reason: {entry.get('reason_for_visit') or '—'}")
        reason.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        vitals_bits = []
        if entry.get("blood_pressure"):
            vitals_bits.append(f"BP {entry['blood_pressure']}")
        if entry.get("temperature"):
            vitals_bits.append(f"Temp {entry['temperature']}")
        vitals = QLabel(" · ".join(vitals_bits) if vitals_bits else "No vitals recorded")
        vitals.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 12px;")
        started = QLabel(f"Started {_fmt_time(entry.get('started_at'))}")
        started.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 12px;")

        info.addWidget(name)
        info.addWidget(reason)
        info.addWidget(vitals)
        info.addWidget(started)
        row.addLayout(info)
        row.addStretch()
        self.layout_.addLayout(row)

        complete_btn = QPushButton("Complete Consultation")
        complete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        complete_btn.setMinimumHeight(42)
        complete_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        complete_btn.clicked.connect(lambda: self.on_complete(entry))
        self.layout_.addWidget(complete_btn)


class StaffDashboard(QWidget):
    def __init__(self, user: dict, on_logout=None):
        super().__init__()
        self.user = user
        self.on_logout = on_logout
        self.api = ApiClient()
        self.department_id = user.get("department_id")

        self.setWindowTitle("eQueue — Staff")
        self.resize(980, 680)
        self.setStyleSheet(f"background-color: {Color.WINDOW_BG};")

        self.department_name = "Loading…"
        self._build_ui()
        self._lookup_department_name()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._silent_refresh)
        self.timer.start(REFRESH_MS)

        self._ws = QueueWebSocketClient(self.api.base_url)
        self._ws.message_received.connect(self._on_ws_message)
        self._ws.start()

        self._refresh_queue(show_errors=True)

    # ---------- setup ----------

    def _lookup_department_name(self):
        if not self.department_id:
            self.department_name = "No department assigned"
            return
        self._dept_lookup_worker = run_async(
            self.api.list_departments,
            on_success=self._on_departments_for_lookup,
            on_error=lambda e: None,
        )

    def _on_departments_for_lookup(self, departments):
        for d in departments:
            if d["id"] == self.department_id:
                self.department_name = d["name"]
                self._update_sidebar_label()
                return
        self.department_name = f"Department #{self.department_id}"
        self._update_sidebar_label()

    def _update_sidebar_label(self):
        self.role_label.setText(f"{self.user.get('full_name', '')}\n{self.department_name}")

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar — same neutral tone across every role; the role itself
        # is shown as a small badge rather than a full-color background.
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(SIDEBAR_STYLE)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(20, 24, 20, 20)
        side_layout.setSpacing(6)
        brand = QLabel("eQueue")
        brand.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        side_layout.addWidget(brand)
        side_layout.addSpacing(14)

        role_badge = QLabel("STAFF")
        role_badge.setStyleSheet(role_badge_style("staff"))
        badge_row = QHBoxLayout()
        badge_row.addWidget(role_badge)
        badge_row.addStretch()
        side_layout.addLayout(badge_row)

        self.role_label = QLabel(f"{self.user.get('full_name', '')}\n{self.department_name}")
        self.role_label.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; margin-top: 4px;")
        side_layout.addWidget(self.role_label)
        side_layout.addStretch()

        logout_btn = QPushButton("Log Out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(LOGOUT_BTN_STYLE)
        logout_btn.clicked.connect(self._logout)
        side_layout.addWidget(logout_btn)

        root.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 24)
        content.setSpacing(16)

        self.status_banner = QLabel("")
        self.status_banner.setStyleSheet(f"color: {Color.RED_TEXT_SUBTLE}; font-size: 12px;")
        self.status_banner.setVisible(False)
        content.addWidget(self.status_banner)

        self.serving_panel = CurrentlyServingPanel(self._call_next, self._complete)
        content.addWidget(self.serving_panel)

        queue_title = QLabel("Waiting Queue")
        queue_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        queue_title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        content.addWidget(queue_title)

        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setStyleSheet("border: none;")
        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setSpacing(8)
        self.queue_layout.addStretch()
        self.queue_scroll.setWidget(self.queue_container)
        content.addWidget(self.queue_scroll, stretch=1)

        root.addLayout(content, stretch=1)

    def _logout(self):
        self.timer.stop()
        self._ws.stop()
        if self.on_logout:
            self.on_logout()

    def closeEvent(self, event):
        self.timer.stop()
        self._ws.stop()
        super().closeEvent(event)

    def _on_ws_message(self, data: dict):
        if data.get("event") not in ("queue_created", "queue_updated"):
            return
        # Only re-fetch if the change was actually in this staff member's
        # department - no point refreshing on every other department's traffic.
        if data.get("data", {}).get("department_id") == self.department_id:
            self._silent_refresh()

    # ---------- data ----------

    def _fetch_department_entries(self):
        if not self.department_id:
            return []
        return self.api.list_queue(department_id=self.department_id)

    def _refresh_queue(self, show_errors=False):
        self._queue_worker = run_async(
            self._fetch_department_entries,
            on_success=self._on_queue_loaded,
            on_error=lambda e: self._on_queue_error(e, show_errors),
        )

    def _silent_refresh(self):
        self._refresh_queue(show_errors=False)

    def _on_queue_loaded(self, entries):
        self._show_banner(None)
        self._render(entries)

    def _on_queue_error(self, error, show_errors):
        if show_errors:
            QMessageBox.critical(self, "Couldn't load queue", str(error))
        self._show_banner(f"Live updates paused — {error}")

    def _show_banner(self, text):
        if text:
            self.status_banner.setText(text)
            self.status_banner.setVisible(True)
        else:
            self.status_banner.setVisible(False)

    def _render(self, entries):
        serving = next(
            (e for e in entries
             if e["status"] == "in_consultation" and e.get("staff_id") == self.user.get("id")),
            None,
        )
        self.serving_panel.set_entry(serving)

        waiting = sorted(
            (e for e in entries if e["status"] == "waiting"),
            key=lambda e: e["queue_number"],
        )

        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not waiting:
            empty = QLabel("No one waiting right now.")
            empty.setStyleSheet(f"color: {Color.TEXT_MUTED}; padding: 8px; border: 1px dashed {Color.BORDER}; border-radius: 8px;")
            self.queue_layout.insertWidget(0, empty)

        for entry in waiting:
            card = WaitingCard(
                entry,
                on_start=self._start,
                on_no_show=self._no_show,
                on_cancel=self._cancel,
                start_enabled=(serving is None),
            )
            self.queue_layout.insertWidget(self.queue_layout.count() - 1, card)

    # ---------- actions ----------

    def _update(self, entry_id, status, expected_status):
        self._action_worker = run_async(
            lambda: self.api.update_status(
                entry_id, status, staff_id=self.user.get("id"), expected_status=expected_status
            ),
            on_success=lambda result: self._refresh_queue(show_errors=False),
            on_error=self._on_update_error,
        )

    def _on_update_error(self, error):
        if isinstance(error, ConflictError):
            QMessageBox.warning(self, "Already updated", str(error))
        else:
            QMessageBox.critical(self, "Action failed", str(error))
        self._refresh_queue(show_errors=False)

    def _call_next(self):
        self._call_next_worker = run_async(
            self._fetch_department_entries,
            on_success=self._on_call_next_entries,
            on_error=lambda e: QMessageBox.critical(self, "Couldn't load queue", str(e)),
        )

    def _on_call_next_entries(self, entries):
        waiting = sorted((e for e in entries if e["status"] == "waiting"), key=lambda e: e["queue_number"])
        if not waiting:
            QMessageBox.information(self, "Queue empty", "No patients are waiting.")
            return
        self._update(waiting[0]["id"], "in_consultation", expected_status="waiting")

    def _start(self, entry):
        self._update(entry["id"], "in_consultation", expected_status="waiting")

    def _complete(self, entry):
        self._update(entry["id"], "done", expected_status="in_consultation")

    def _no_show(self, entry):
        self._update(entry["id"], "no_show", expected_status="waiting")

    def _cancel(self, entry):
        reply = QMessageBox.question(
            self, "Cancel entry",
            f"Cancel queue #{entry['queue_number']} ({entry.get('patient_name', 'this patient')})?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._update(entry["id"], "cancelled", expected_status="waiting")