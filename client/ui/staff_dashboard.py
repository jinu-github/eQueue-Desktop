from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.constants import STATUS_COLORS, ROLE_ACCENT_COLORS, Role
from api_client import ApiClient, ApiError, ConflictError

# How often the dashboard polls the server for queue changes. A real push
# channel (the server already broadcasts over /ws) would be a nice later
# upgrade, but wiring asyncio websockets into a Qt event loop is its own
# chunk of work — polling is simple, robust, and fast enough for a queue
# that changes on the order of minutes, not milliseconds.
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
        color = STATUS_COLORS.get(entry["status"], "#94a3b8")
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1e293b;
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        number = QLabel(f"#{entry['queue_number']}")
        number.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        number.setStyleSheet("color: #f8fafc;")
        number.setFixedWidth(56)

        info = QVBoxLayout()
        name = QLabel(entry.get("patient_name") or f"Patient #{entry['patient_id']}")
        name.setStyleSheet("color: #f8fafc; font-weight: 600; font-size: 14px;")
        reason = QLabel(entry.get("reason_for_visit") or "No reason given")
        reason.setStyleSheet("color: #94a3b8; font-size: 12px;")
        checked_in = QLabel(f"Checked in {_fmt_time(entry.get('check_in_time'))}")
        checked_in.setStyleSheet("color: #64748b; font-size: 11px;")
        info.addWidget(name)
        info.addWidget(reason)
        info.addWidget(checked_in)

        layout.addWidget(number)
        layout.addLayout(info)
        layout.addStretch()

        start_btn = QPushButton("Start")
        start_btn.setStyleSheet("""
            QPushButton { background-color: #16a34a; color: white; border-radius: 6px; padding: 8px 14px; font-weight: 600; }
            QPushButton:hover { background-color: #15803d; }
            QPushButton:disabled { background-color: #334155; color: #64748b; }
        """)
        start_btn.setEnabled(start_enabled)
        start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        start_btn.clicked.connect(lambda: on_start(entry))

        no_show_btn = QPushButton("No-show")
        no_show_btn.setStyleSheet("""
            QPushButton { background-color: #334155; color: #e2e8f0; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background-color: #475569; }
        """)
        no_show_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        no_show_btn.clicked.connect(lambda: on_no_show(entry))

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton { background-color: #7f1d1d; color: #fecaca; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background-color: #991b1b; }
        """)
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
        self.setStyleSheet("QFrame { background-color: #1e293b; border-radius: 12px; }")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(10)
        self.set_entry(None)

    def _clear(self):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_entry(self, entry):
        self._clear()

        title = QLabel("Currently Serving")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #f8fafc;")
        self.layout_.addWidget(title)

        if entry is None:
            empty = QLabel("You're not seeing anyone right now.")
            empty.setStyleSheet("color: #94a3b8;")
            self.layout_.addWidget(empty)

            call_btn = QPushButton("Call Next Patient")
            call_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            call_btn.setMinimumHeight(42)
            call_btn.setStyleSheet("""
                QPushButton { background-color: #16a34a; color: white; border-radius: 8px; font-weight: 600; font-size: 14px; }
                QPushButton:hover { background-color: #15803d; }
            """)
            call_btn.clicked.connect(self.on_call_next)
            self.layout_.addWidget(call_btn)
            return

        row = QHBoxLayout()
        number = QLabel(f"#{entry['queue_number']}")
        number.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        number.setStyleSheet("color: #f8fafc;")
        number.setFixedWidth(90)
        row.addWidget(number)

        info = QVBoxLayout()
        name = QLabel(entry.get("patient_name") or f"Patient #{entry['patient_id']}")
        name.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        name.setStyleSheet("color: #f8fafc;")
        reason = QLabel(f"Reason: {entry.get('reason_for_visit') or '—'}")
        reason.setStyleSheet("color: #94a3b8;")
        vitals_bits = []
        if entry.get("blood_pressure"):
            vitals_bits.append(f"BP {entry['blood_pressure']}")
        if entry.get("temperature"):
            vitals_bits.append(f"Temp {entry['temperature']}")
        vitals = QLabel(" · ".join(vitals_bits) if vitals_bits else "No vitals recorded")
        vitals.setStyleSheet("color: #64748b; font-size: 12px;")
        started = QLabel(f"Started {_fmt_time(entry.get('started_at'))}")
        started.setStyleSheet("color: #64748b; font-size: 12px;")

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
        complete_btn.setStyleSheet("""
            QPushButton { background-color: #2563eb; color: white; border-radius: 8px; font-weight: 600; font-size: 14px; }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        complete_btn.clicked.connect(lambda: self.on_complete(entry))
        self.layout_.addWidget(complete_btn)


class StaffDashboard(QWidget):
    def __init__(self, user: dict):
        super().__init__()
        self.user = user
        self.api = ApiClient()
        self.department_id = user.get("department_id")

        self.setWindowTitle("eQueue — Staff")
        self.resize(980, 680)
        self.setStyleSheet("background-color: #0f172a;")

        self.department_name = self._lookup_department_name()
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._silent_refresh)
        self.timer.start(REFRESH_MS)

        self._refresh_queue(show_errors=True)

    # ---------- setup ----------

    def _lookup_department_name(self):
        if not self.department_id:
            return "No department assigned"
        try:
            for d in self.api.list_departments():
                if d["id"] == self.department_id:
                    return d["name"]
        except ApiError:
            pass
        return f"Department #{self.department_id}"

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background-color: {ROLE_ACCENT_COLORS[Role.STAFF]};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(20, 24, 20, 20)
        brand = QLabel("eQueue")
        brand.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        brand.setStyleSheet("color: white;")
        role_label = QLabel(f"Staff\n{self.user.get('full_name', '')}\n{self.department_name}")
        role_label.setStyleSheet("color: #dcfce7; margin-top: 4px;")
        side_layout.addWidget(brand)
        side_layout.addWidget(role_label)
        side_layout.addStretch()
        root.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 24)
        content.setSpacing(16)

        self.status_banner = QLabel("")
        self.status_banner.setStyleSheet("color: #fca5a5; font-size: 12px;")
        self.status_banner.setVisible(False)
        content.addWidget(self.status_banner)

        self.serving_panel = CurrentlyServingPanel(self._call_next, self._complete)
        content.addWidget(self.serving_panel)

        queue_title = QLabel("Waiting Queue")
        queue_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        queue_title.setStyleSheet("color: #f8fafc;")
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

    # ---------- data ----------

    def _fetch_department_entries(self):
        if not self.department_id:
            return []
        return self.api.list_queue(department_id=self.department_id)

    def _refresh_queue(self, show_errors=False):
        try:
            entries = self._fetch_department_entries()
        except ApiError as e:
            if show_errors:
                QMessageBox.critical(self, "Couldn't load queue", str(e))
            self._show_banner(f"Live updates paused — {e}")
            return
        self._show_banner(None)
        self._render(entries)

    def _silent_refresh(self):
        # Background poll: never pop a dialog for this, just surface a
        # small banner if the server becomes unreachable, and clear it
        # automatically once a poll succeeds again.
        self._refresh_queue(show_errors=False)

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
            empty.setStyleSheet("color: #64748b; padding: 8px;")
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
        try:
            self.api.update_status(
                entry_id, status,
                staff_id=self.user.get("id"),
                expected_status=expected_status,
            )
        except ConflictError as e:
            # Someone else (another staff member) changed this entry first —
            # this is the "two staff can't take the same patient" guard
            # firing. Tell the user plainly rather than silently overwriting.
            QMessageBox.warning(self, "Already updated", str(e))
        except ApiError as e:
            QMessageBox.critical(self, "Action failed", str(e))
        finally:
            self._refresh_queue(show_errors=False)

    def _call_next(self):
        try:
            entries = self._fetch_department_entries()
        except ApiError as e:
            QMessageBox.critical(self, "Couldn't load queue", str(e))
            return
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
