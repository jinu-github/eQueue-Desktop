from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QComboBox, QFormLayout, QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.constants import STATUS_COLORS, STATUS_LABELS, ROLE_ACCENT_COLORS, Role
from api_client import ApiClient


class QueueCard(QFrame):
    """A single glanceable queue entry card."""
    def __init__(self, entry: dict):
        super().__init__()
        status = entry.get("status", "waiting")
        color = STATUS_COLORS.get(status, "#94a3b8")

        self.setStyleSheet(f"""
            QFrame {{
                background-color: #1e293b;
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        number = QLabel(f"#{entry.get('queue_number', '?')}")
        number.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        number.setStyleSheet("color: #f8fafc;")
        number.setFixedWidth(60)

        info = QVBoxLayout()
        name = QLabel(f"Patient #{entry.get('patient_id')}")
        name.setStyleSheet("color: #f8fafc; font-weight: 600;")
        badge = QLabel(STATUS_LABELS.get(status, status))
        badge.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
        info.addWidget(name)
        info.addWidget(badge)

        layout.addWidget(number)
        layout.addLayout(info)
        layout.addStretch()


class ReceptionDashboard(QWidget):
    def __init__(self, user: dict):
        super().__init__()
        self.user = user
        self.api = ApiClient()
        self.setWindowTitle("eQueue — Reception")
        self.resize(980, 640)
        self.setStyleSheet("background-color: #0f172a;")
        self.departments = []
        self._build_ui()
        self._load_departments()
        self._refresh_queue()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background-color: {ROLE_ACCENT_COLORS[Role.RECEPTIONIST]};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(20, 24, 20, 20)
        brand = QLabel("eQueue")
        brand.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        brand.setStyleSheet("color: white;")
        role_label = QLabel(f"Reception\n{self.user.get('full_name', '')}")
        role_label.setStyleSheet("color: #dbeafe; margin-top: 4px;")
        side_layout.addWidget(brand)
        side_layout.addWidget(role_label)
        side_layout.addStretch()
        root.addWidget(sidebar)

        # Main content
        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 24)
        content.setSpacing(20)

        # Registration form
        form_frame = QFrame()
        form_frame.setStyleSheet("QFrame { background-color: #1e293b; border-radius: 12px; }")
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(24, 20, 24, 20)
        form_layout.setSpacing(10)

        title = QLabel("Register Patient")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #f8fafc;")
        form_layout.addRow(title)

        input_style = """
            QLineEdit, QComboBox {
                background-color: #0f172a; color: #f8fafc;
                border: 1px solid #334155; border-radius: 6px; padding: 8px;
            }
        """
        self.first_name = QLineEdit(); self.first_name.setStyleSheet(input_style)
        self.last_name = QLineEdit(); self.last_name.setStyleSheet(input_style)
        self.contact = QLineEdit(); self.contact.setPlaceholderText("63XXXXXXXXXX")
        self.contact.setStyleSheet(input_style)
        self.department_combo = QComboBox(); self.department_combo.setStyleSheet(input_style)
        self.reason = QLineEdit(); self.reason.setStyleSheet(input_style)

        for label, widget in [
            ("First name", self.first_name),
            ("Last name", self.last_name),
            ("Contact number", self.contact),
            ("Department", self.department_combo),
            ("Reason for visit", self.reason),
        ]:
            lbl = QLabel(label); lbl.setStyleSheet("color: #94a3b8;")
            form_layout.addRow(lbl, widget)

        register_btn = QPushButton("Register & Assign Queue Number")
        register_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        register_btn.setStyleSheet("""
            QPushButton { background-color: #2563eb; color: white; border-radius: 6px; padding: 10px; font-weight: 600; }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        register_btn.clicked.connect(self._register_patient)
        form_layout.addRow(register_btn)

        content.addWidget(form_frame)

        # Live queue list
        queue_title = QLabel("Today's Queue")
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

    def _load_departments(self):
        try:
            self.departments = self.api.list_departments()
            self.department_combo.clear()
            for dept in self.departments:
                self.department_combo.addItem(dept["name"], dept["id"])
        except Exception:
            pass  # server not reachable yet; handled on submit

    def _register_patient(self):
        if not self.first_name.text() or not self.last_name.text() or not self.contact.text():
            QMessageBox.warning(self, "Missing info", "First name, last name, and contact number are required.")
            return
        try:
            patient = self.api.create_patient({
                "first_name": self.first_name.text(),
                "last_name": self.last_name.text(),
                "contact_number": self.contact.text(),
            })
            dept_id = self.department_combo.currentData()
            entry = self.api.create_queue_entry({
                "patient_id": patient["id"],
                "department_id": dept_id,
                "reason_for_visit": self.reason.text(),
            })
            QMessageBox.information(self, "Registered", f"Queue number assigned: #{entry['queue_number']}")
            self.first_name.clear(); self.last_name.clear()
            self.contact.clear(); self.reason.clear()
            self._refresh_queue()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not register patient.\n{e}")

    def _refresh_queue(self):
        # Clear existing cards
        while self.queue_layout.count() > 1:
            item = self.queue_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            entries = self.api.list_queue()
            for entry in entries:
                card = QueueCard(entry)
                self.queue_layout.insertWidget(self.queue_layout.count() - 1, card)
        except Exception:
            pass
