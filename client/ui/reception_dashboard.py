from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QComboBox, QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.constants import STATUS_COLORS, STATUS_LABELS
from api_client import ApiClient
from async_worker import run_async
from theme import Color, INPUT_STYLE, PRIMARY_BTN_STYLE, SIDEBAR_STYLE, LOGOUT_BTN_STYLE, role_badge_style
from ws_client import QueueWebSocketClient


# Statuses that should render with the "done" pill treatment (check icon,
# green tint) vs. everything else, which gets a neutral/in-progress dot.
DONE_STATUSES = {"done", "completed", "served"}


class LogoMark(QWidget):
    """Blue rounded-square brand mark with a plus-cross, drawn directly
    instead of relying on an emoji glyph (which fonts render inconsistently
    or not at all, e.g. showing empty boxes on some Windows setups)."""
    def __init__(self, size: int = 34):
        super().__init__()
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1f6feb"))
        painter.drawRoundedRect(rect, 9, 9)

        pen = QPen(QColor("#ffffff"))
        pen.setWidth(max(2, rect.width() // 12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx, cy = rect.center().x(), rect.center().y()
        arm = int(rect.width() * 0.22)
        painter.drawLine(cx - arm, cy, cx + arm, cy)
        painter.drawLine(cx, cy - arm, cx, cy + arm)

class QueueCard(QFrame):
    """Compact queue entry card matching the dashboard theme."""

    def __init__(self, entry: dict, department_name: str = None):
        super().__init__()

        status = entry.get("status", "waiting")
        color = STATUS_COLORS.get(status, "#8fa3b0")
        is_done = status in DONE_STATUSES

        self.setObjectName("queueCard")

        # More compact than the previous version
        self.setFixedHeight(70)

        self.setStyleSheet(f"""
            QFrame#queueCard {{
                background-color: {Color.PANEL_BG};
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 12px;
            }}

            QFrame#queueCard:hover {{
                background-color: rgba(255, 255, 255, 5);
                border: 1px solid rgba(255, 255, 255, 28);
            }}
        """)

        # Main layout
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 8, 18, 8)
        outer.setSpacing(14)

        # ---------------------------------------------------------
        # Queue number
        # ---------------------------------------------------------
        badge = QLabel(f"#{entry.get('queue_number', '?')}")
        badge.setFixedSize(42, 42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        badge.setStyleSheet("""
            QLabel {
                color: #f1f3f5;
                background-color: rgba(255, 255, 255, 8);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 21px;
            }
        """)

        outer.addWidget(badge)

        # ---------------------------------------------------------
        # Patient information
        # ---------------------------------------------------------
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)

        name = QLabel(
            f"Patient #{entry.get('patient_id', '?')}"
        )
        name.setFont(
            QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        )
        name.setStyleSheet(f"""
            QLabel {{
                color: {Color.TEXT_PRIMARY};
                background: transparent;
            }}
        """)

        info.addWidget(name)

        if department_name:
            subtitle = QLabel(department_name)
            subtitle.setFont(
                QFont("Segoe UI", 9)
            )
            subtitle.setStyleSheet(f"""
                QLabel {{
                    color: {Color.TEXT_SECONDARY};
                    background: transparent;
                }}
            """)
            info.addWidget(subtitle)

        outer.addLayout(info)

        # Push status to right
        outer.addStretch()

        # ---------------------------------------------------------
        # Status
        # ---------------------------------------------------------
        if is_done:
            status_text = "✓ Done"

            pill = QLabel(status_text)
            pill.setFixedSize(82, 48)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setFont(
                QFont("Segoe UI", 9, QFont.Weight.DemiBold)
            )

            pill.setStyleSheet("""
                QLabel {
                    color: #20d878;
                    background-color: rgba(32, 216, 120, 32);
                    border: none;
                    border-radius: 15px;
                }
            """)

        else:
            status_text = "● " + STATUS_LABELS.get(
                status, status
            )

            pill = QLabel(status_text)
            pill.setFixedSize(82, 48)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setFont(
                QFont("Segoe UI", 9, QFont.Weight.DemiBold)
            )

            rgb = self._hex_to_rgb(color)

            pill.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    background-color: rgba{(*rgb, 25)};
                    border: 1px solid rgba{(*rgb, 70)};
                    border-radius: 15px;
                }}
            """)

        outer.addWidget(pill)

    @staticmethod
    def _hex_to_rgb(hex_color: str):
        hex_color = hex_color.lstrip("#")

        if len(hex_color) != 6:
            return (143, 163, 176)

        return tuple(
            int(hex_color[i:i + 2], 16)
            for i in (0, 2, 4)
        )


class ReceptionDashboard(QWidget):
    def __init__(self, user: dict, on_logout=None):
        super().__init__()
        self.user = user
        self.on_logout = on_logout
        self.api = ApiClient()
        self.setWindowTitle("eQueue — Reception")
        self.resize(980, 640)
        self.setStyleSheet(f"background-color: {Color.WINDOW_BG};")
        self.departments = []
        self._build_ui()
        self._load_departments()
        self._refresh_queue()

        self._ws = QueueWebSocketClient(self.api.base_url)
        self._ws.message_received.connect(self._on_ws_message)
        self._ws.start()

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

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo_mark = LogoMark(34)
        brand_row.addWidget(logo_mark)
        brand = QLabel("eQueue")
        brand.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        side_layout.addLayout(brand_row)
        side_layout.addSpacing(18)

        role_badge = QLabel("RECEPTION")
        role_badge.setStyleSheet(role_badge_style("receptionist"))
        badge_row = QHBoxLayout()
        badge_row.addWidget(role_badge)
        badge_row.addStretch()
        side_layout.addLayout(badge_row)

        name_label = QLabel(self.user.get("full_name", ""))
        name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        name_label.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; margin-top: 8px;")
        side_layout.addWidget(name_label)

        role_label = QLabel(self.user.get("role_title", "Front Desk"))
        role_label.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 11px;")
        side_layout.addWidget(role_label)
        side_layout.addStretch()

        logout_btn = QPushButton("↪  Log Out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(LOGOUT_BTN_STYLE)
        logout_btn.clicked.connect(self._logout)
        side_layout.addWidget(logout_btn)

        root.addWidget(sidebar)

        # Main content
        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 24)
        content.setSpacing(20)

        page_title = QLabel("Reception Dashboard")
        page_title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        page_title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        content.addWidget(page_title)

        page_subtitle = QLabel("Register patients and manage today's queue")
        page_subtitle.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        content.addWidget(page_subtitle)

        # Registration form
        form_frame = QFrame()
        form_frame.setStyleSheet(f"QFrame {{ background-color: {Color.PANEL_BG}; border-radius: 12px; }}")
        form_outer = QVBoxLayout(form_frame)
        form_outer.setContentsMargins(24, 20, 24, 20)
        form_outer.setSpacing(16)

        title = QLabel("Register Patient")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        form_outer.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(4)

        def field_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 12px;")
            return lbl

        self.first_name = QLineEdit(); self.first_name.setStyleSheet(INPUT_STYLE)
        self.last_name = QLineEdit(); self.last_name.setStyleSheet(INPUT_STYLE)
        self.contact = QLineEdit(); self.contact.setPlaceholderText("0917 000 0000")
        self.contact.setStyleSheet(INPUT_STYLE)
        self.department_combo = QComboBox(); self.department_combo.setStyleSheet(INPUT_STYLE)
        self.reason = QLineEdit(); self.reason.setPlaceholderText("Short description")
        self.reason.setStyleSheet(INPUT_STYLE)

        # Row 1: first name / last name / contact number (3 columns)
        grid.addWidget(field_label("First name"), 0, 0)
        grid.addWidget(field_label("Last name"), 0, 1)
        grid.addWidget(field_label("Contact number"), 0, 2)
        grid.addWidget(self.first_name, 1, 0)
        grid.addWidget(self.last_name, 1, 1)
        grid.addWidget(self.contact, 1, 2)

        # Row 2: department / reason for visit (department narrower)
        grid.addWidget(field_label("Department"), 2, 0)
        grid.addWidget(field_label("Reason for visit"), 2, 1, 1, 2)
        grid.addWidget(self.department_combo, 3, 0)
        grid.addWidget(self.reason, 3, 1, 1, 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        form_outer.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.register_btn = QPushButton("Register && Assign Queue Number")
        self.register_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self.register_btn.clicked.connect(self._register_patient)
        btn_row.addWidget(self.register_btn)
        form_outer.addLayout(btn_row)

        content.addWidget(form_frame)

        # Live queue list
        queue_header = QHBoxLayout()
        queue_title = QLabel("Today's Queue")
        queue_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        queue_title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        self.entries_label = QLabel("0 entries")
        self.entries_label.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 12px;")
        queue_header.addWidget(self.entries_label)
        content.addLayout(queue_header)

        self.queue_scroll = QScrollArea()
        self.queue_scroll.setWidgetResizable(True)
        self.queue_scroll.setStyleSheet("border: none;")
        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setSpacing(10)
        self.queue_layout.setContentsMargins(0, 0, 0, 10)       
        self.queue_layout.addStretch()
        self.queue_scroll.setWidget(self.queue_container)
        content.addWidget(self.queue_scroll, stretch=1)

        root.addLayout(content, stretch=1)

    def _logout(self):
        self._ws.stop()
        if self.on_logout:
            self.on_logout()

    def closeEvent(self, event):
        self._ws.stop()
        super().closeEvent(event)

    def _on_ws_message(self, data: dict):
        if data.get("event") in ("queue_created", "queue_updated"):
            self._refresh_queue()

    def _load_departments(self):
        self._dept_worker = run_async(
            self.api.list_departments,
            on_success=self._on_departments_loaded,
            on_error=lambda e: None,  # server not reachable yet; handled on submit
        )

    def _on_departments_loaded(self, departments):
        self.departments = departments
        self.department_combo.clear()
        self.department_combo.addItem("Select department", None)
        for dept in self.departments:
            self.department_combo.addItem(dept["name"], dept["id"])
        # Departments may finish loading after the queue already rendered
        # without department names - refresh once more now that we have them.
        self._refresh_queue()

    def _register_patient(self):
        if not self.first_name.text() or not self.last_name.text() or not self.contact.text():
            QMessageBox.warning(self, "Missing info", "First name, last name, and contact number are required.")
            return

        first_name, last_name, contact, reason = (
            self.first_name.text(), self.last_name.text(), self.contact.text(), self.reason.text()
        )
        dept_id = self.department_combo.currentData()

        def do_register():
            patient = self.api.create_patient({
                "first_name": first_name, "last_name": last_name, "contact_number": contact,
            })
            return self.api.create_queue_entry({
                "patient_id": patient["id"], "department_id": dept_id, "reason_for_visit": reason,
                "registered_by_id": self.user["id"],
            })
        self.register_btn.setEnabled(False)
        self._register_worker = run_async(
            do_register,
            on_success=self._on_registered,
            on_error=self._on_register_error,
        )

    def _on_registered(self, entry):
        self.register_btn.setEnabled(True)
        QMessageBox.information(self, "Registered", f"Queue number assigned: #{entry['queue_number']}")
        self.first_name.clear(); self.last_name.clear()
        self.contact.clear(); self.reason.clear()
        self._refresh_queue()

    def _on_register_error(self, error):
        self.register_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Could not register patient.\n{error}")

    def _refresh_queue(self):
        self._queue_worker = run_async(
            self.api.list_queue,
            on_success=self._render_queue,
            on_error=lambda e: None,
        )

    def _render_queue(self, entries):
        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.entries_label.setText(f"{len(entries)} entries")

        dept_names = {d["id"]: d["name"] for d in self.departments}
        for entry in entries:
            card = QueueCard(entry, department_name=dept_names.get(entry.get("department_id")))
            self.queue_layout.insertWidget(self.queue_layout.count() - 1, card)