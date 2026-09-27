from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QComboBox, QFormLayout, QMessageBox, QScrollArea, QTabWidget,
    QSpinBox, QTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.constants import ALL_ROLES, STATUS_COLORS, STATUS_LABELS
from api_client import ApiClient
from local_settings import load_settings, save_settings
from ws_client import QueueWebSocketClient
from async_worker import run_async
from theme import (
    Color, INPUT_STYLE, PANEL_STYLE, PRIMARY_BTN_STYLE, DANGER_BTN_STYLE,
    SIDEBAR_STYLE, LOGOUT_BTN_STYLE, ROW_STYLE, role_badge_style,
)

SMS_TEMPLATE_TYPES = ["welcome", "proximity", "your_turn", "missed"]
SMS_TEMPLATE_LABELS = {
    "welcome": "Welcome / registered",
    "proximity": "Almost your turn",
    "your_turn": "Your turn now",
    "missed": "Missed / no-show",
}


class UserRow(QFrame):
    def __init__(self, user: dict):
        super().__init__()
        self.setStyleSheet(ROW_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        name = QLabel(user.get("full_name", user.get("username", "?")))
        name.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; font-weight: 600;")
        name.setFixedWidth(200)

        role = QLabel(user.get("role", ""))
        role.setStyleSheet(role_badge_style(user.get("role", "")))

        username = QLabel(f"@{user.get('username', '')}")
        username.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")

        layout.addWidget(name)
        layout.addWidget(role)
        layout.addStretch()
        layout.addWidget(username)


class AdminDashboard(QWidget):
    def __init__(self, user: dict, on_logout=None):
        super().__init__()
        self.user = user
        self.on_logout = on_logout
        self.api = ApiClient()
        self.setWindowTitle("eQueue — Admin")
        self.resize(1000, 660)
        self.setStyleSheet(f"background-color: {Color.WINDOW_BG};")
        self.departments = []
        self._build_ui()
        self._load_departments()
        self._refresh_users()
        self._refresh_overview()
        self._load_settings_tab()

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
        brand = QLabel("eQueue")
        brand.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        side_layout.addWidget(brand)
        side_layout.addSpacing(14)

        role_badge = QLabel("ADMIN")
        role_badge.setStyleSheet(role_badge_style("admin"))
        badge_row = QHBoxLayout()
        badge_row.addWidget(role_badge)
        badge_row.addStretch()
        side_layout.addLayout(badge_row)

        role_label = QLabel(self.user.get("full_name", ""))
        role_label.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; margin-top: 4px;")
        side_layout.addWidget(role_label)
        side_layout.addStretch()

        logout_btn = QPushButton("Log Out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(LOGOUT_BTN_STYLE)
        logout_btn.clicked.connect(self._logout)
        side_layout.addWidget(logout_btn)

        root.addWidget(sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(24, 20, 24, 20)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: {Color.PANEL_BG}; color: {Color.TEXT_SECONDARY}; padding: 10px 18px;
                border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 4px;
            }}
            QTabBar::tab:selected {{ background: {Color.BLUE}; color: white; }}
        """)
        tabs.addTab(self._build_users_tab(), "Users")
        tabs.addTab(self._build_departments_tab(), "Departments")
        tabs.addTab(self._build_sms_tab(), "SMS Templates")
        tabs.addTab(self._build_overview_tab(), "Queue Overview")
        tabs.addTab(self._build_settings_tab(), "Settings")
        tabs.addTab(self._build_sms_settings_tab(), "SMS Settings")
        tabs.addTab(self._build_reports_tab(), "Reports")
        tabs.addTab(self._build_audit_log_tab(), "Audit Log")

        content.addWidget(tabs)
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
            self._refresh_overview()

    # --- Users tab ---------------------------------------------------

    def _build_users_tab(self):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(20)

        form_frame = QFrame()
        form_frame.setStyleSheet(PANEL_STYLE)
        form_frame.setFixedWidth(320)
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(20, 18, 20, 18)
        form_layout.setSpacing(10)

        title = QLabel("Add Staff Account")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        form_layout.addRow(title)

        self.new_full_name = QLineEdit(); self.new_full_name.setStyleSheet(INPUT_STYLE)
        self.new_username = QLineEdit(); self.new_username.setStyleSheet(INPUT_STYLE)
        self.new_password = QLineEdit(); self.new_password.setStyleSheet(INPUT_STYLE)
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_role = QComboBox(); self.new_role.setStyleSheet(INPUT_STYLE)
        self.new_role.addItems(ALL_ROLES)
        self.new_department = QComboBox(); self.new_department.setStyleSheet(INPUT_STYLE)

        for label, widget in [
            ("Full name", self.new_full_name),
            ("Username", self.new_username),
            ("Password", self.new_password),
            ("Role", self.new_role),
            ("Department", self.new_department),
        ]:
            lbl = QLabel(label); lbl.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
            form_layout.addRow(lbl, widget)

        self.create_user_btn = QPushButton("Create Account")
        self.create_user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_user_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self.create_user_btn.clicked.connect(self._create_user)
        form_layout.addRow(self.create_user_btn)

        layout.addWidget(form_frame)

        list_wrapper = QVBoxLayout()
        list_title = QLabel("All Accounts")
        list_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        list_title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        list_wrapper.addWidget(list_title)

        self.users_scroll = QScrollArea()
        self.users_scroll.setWidgetResizable(True)
        self.users_scroll.setStyleSheet("border: none;")
        self.users_container = QWidget()
        self.users_layout = QVBoxLayout(self.users_container)
        self.users_layout.setSpacing(8)
        self.users_layout.addStretch()
        self.users_scroll.setWidget(self.users_container)
        list_wrapper.addWidget(self.users_scroll)

        layout.addLayout(list_wrapper, stretch=1)
        return wrapper

    def _create_user(self):
        if not all([self.new_full_name.text(), self.new_username.text(), self.new_password.text()]):
            QMessageBox.warning(self, "Missing info", "Full name, username, and password are required.")
            return

        payload = {
            "full_name": self.new_full_name.text(),
            "username": self.new_username.text(),
            "password": self.new_password.text(),
            "role": self.new_role.currentText(),
            "department_id": self.new_department.currentData(),
            "created_by_id": self.user["id"],
        }
        self.create_user_btn.setEnabled(False)
        self._create_user_worker = run_async(
            lambda: self.api.create_user(payload),
            on_success=self._on_user_created,
            on_error=self._on_user_create_error,
        )

    def _on_user_created(self, result):
        self.create_user_btn.setEnabled(True)
        self.new_full_name.clear(); self.new_username.clear(); self.new_password.clear()
        self._refresh_users()

    def _on_user_create_error(self, error):
        self.create_user_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Could not create account.\n{error}")

    def _refresh_users(self):
        self._users_worker = run_async(
            self.api.list_users,
            on_success=self._render_users,
            on_error=lambda e: None,
        )

    def _render_users(self, users: list):
        while self.users_layout.count() > 1:
            item = self.users_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for u in users:
            self.users_layout.insertWidget(self.users_layout.count() - 1, UserRow(u))

    # --- Departments tab -----------------------------------------------

    def _build_departments_tab(self):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(20)

        form_frame = QFrame()
        form_frame.setStyleSheet(PANEL_STYLE)
        form_frame.setFixedWidth(320)
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(20, 18, 20, 18)
        form_layout.setSpacing(10)

        title = QLabel("Add Department")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        form_layout.addRow(title)

        self.dept_name_input = QLineEdit(); self.dept_name_input.setStyleSheet(INPUT_STYLE)
        self.dept_minutes_input = QSpinBox(); self.dept_minutes_input.setStyleSheet(INPUT_STYLE)
        self.dept_minutes_input.setRange(1, 240)
        self.dept_minutes_input.setValue(15)
        self.dept_minutes_input.setSuffix(" min")

        lbl1 = QLabel("Name"); lbl1.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        lbl2 = QLabel("Avg. consultation time"); lbl2.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        form_layout.addRow(lbl1, self.dept_name_input)
        form_layout.addRow(lbl2, self.dept_minutes_input)

        self.add_dept_btn = QPushButton("Add Department")
        self.add_dept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_dept_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self.add_dept_btn.clicked.connect(self._create_department)
        form_layout.addRow(self.add_dept_btn)

        layout.addWidget(form_frame)

        list_wrapper = QVBoxLayout()
        list_title = QLabel("All Departments")
        list_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        list_title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        list_wrapper.addWidget(list_title)

        self.dept_scroll = QScrollArea()
        self.dept_scroll.setWidgetResizable(True)
        self.dept_scroll.setStyleSheet("border: none;")
        self.dept_container = QWidget()
        self.dept_list_layout = QVBoxLayout(self.dept_container)
        self.dept_list_layout.setSpacing(8)
        self.dept_list_layout.addStretch()
        self.dept_scroll.setWidget(self.dept_container)
        list_wrapper.addWidget(self.dept_scroll)

        layout.addLayout(list_wrapper, stretch=1)
        return wrapper

    def _create_department(self):
        name = self.dept_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing info", "Department name is required.")
            return

        minutes = self.dept_minutes_input.value()
        self.add_dept_btn.setEnabled(False)
        self._create_dept_worker = run_async(
            lambda: self.api.create_department(name, minutes, actor_id=self.user["id"]),
            on_success=self._on_department_created,
            on_error=self._on_department_create_error,
        )

    def _on_department_created(self, result):
        self.add_dept_btn.setEnabled(True)
        self.dept_name_input.clear()
        self.dept_minutes_input.setValue(15)
        self._load_departments()

    def _on_department_create_error(self, error):
        self.add_dept_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Could not create department.\n{error}")

    def _render_department_list(self):
        while self.dept_list_layout.count() > 1:
            item = self.dept_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for dept in self.departments:
            row = QFrame()
            row.setStyleSheet(ROW_STYLE)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)

            name = QLabel(dept["name"])
            name.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; font-weight: 600;")
            minutes = QLabel(f"~{dept['avg_consultation_minutes']} min / patient")
            minutes.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")

            del_btn = QPushButton("Delete")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(DANGER_BTN_STYLE)
            del_btn.clicked.connect(lambda checked, d=dept: self._delete_department(d))

            row_layout.addWidget(name)
            row_layout.addStretch()
            row_layout.addWidget(minutes)
            row_layout.addWidget(del_btn)
            self.dept_list_layout.insertWidget(self.dept_list_layout.count() - 1, row)

    def _delete_department(self, dept: dict):
        confirm = QMessageBox.question(
            self, "Delete department",
            f"Delete '{dept['name']}'? This only works if it has no queue history."
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._delete_dept_worker = run_async(
            lambda: self.api.delete_department(dept["id"], actor_id=self.user["id"]),
            on_success=lambda result: self._load_departments(),
            on_error=lambda error: QMessageBox.critical(self, "Can't delete", str(error)),
        )

    # --- SMS Templates tab ----------------------------------------------

    def _build_sms_tab(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)

        picker_row = QHBoxLayout()
        lbl = QLabel("Department:")
        lbl.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        self.sms_department = QComboBox()
        self.sms_department.setStyleSheet(INPUT_STYLE)
        self.sms_department.currentIndexChanged.connect(self._refresh_sms_templates)
        picker_row.addWidget(lbl)
        picker_row.addWidget(self.sms_department)
        picker_row.addStretch()
        layout.addLayout(picker_row)

        self.sms_scroll = QScrollArea()
        self.sms_scroll.setWidgetResizable(True)
        self.sms_scroll.setStyleSheet("border: none;")
        self.sms_container = QWidget()
        self.sms_list_layout = QVBoxLayout(self.sms_container)
        self.sms_list_layout.setSpacing(10)
        self.sms_list_layout.addStretch()
        self.sms_scroll.setWidget(self.sms_container)
        layout.addWidget(self.sms_scroll, stretch=1)

        return wrapper

    def _refresh_sms_templates(self):
        dept_id = self.sms_department.currentData()
        if not dept_id:
            return
        self._sms_templates_worker = run_async(
            lambda: self.api.list_sms_templates(department_id=dept_id),
            on_success=self._render_sms_templates,
            on_error=lambda e: self._render_sms_templates([]),
        )

    def _render_sms_templates(self, templates: list):
        while self.sms_list_layout.count() > 1:
            item = self.sms_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        by_type = {t["template_type"]: t for t in templates}

        for ttype in SMS_TEMPLATE_TYPES:
            existing = by_type.get(ttype)
            panel = QFrame()
            panel.setStyleSheet(PANEL_STYLE)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(18, 14, 18, 14)
            panel_layout.setSpacing(8)

            header = QLabel(SMS_TEMPLATE_LABELS[ttype])
            header.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; font-weight: 600;")
            panel_layout.addWidget(header)

            text_edit = QTextEdit()
            text_edit.setStyleSheet(INPUT_STYLE)
            text_edit.setFixedHeight(70)
            text_edit.setPlainText(existing["content"] if existing else "")
            panel_layout.addWidget(text_edit)

            save_btn = QPushButton("Save")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(PRIMARY_BTN_STYLE)
            save_btn.clicked.connect(
                lambda checked, t=ttype, e=text_edit, ex=existing, b=save_btn: self._save_sms_template(t, e, ex, b)
            )
            panel_layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignRight)

            self.sms_list_layout.insertWidget(self.sms_list_layout.count() - 1, panel)

    def _save_sms_template(self, template_type: str, text_edit: QTextEdit, existing: dict, save_btn: QPushButton):
        content = text_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Empty template", "Template content can't be empty.")
            return
        dept_id = self.sms_department.currentData()

        def do_save():
            if existing:
                return self.api.update_sms_template(existing["id"], content, actor_id=self.user["id"])
            return self.api.create_sms_template(dept_id, template_type, content, actor_id=self.user["id"])

        save_btn.setEnabled(False)
        self._save_template_worker = run_async(
            do_save,
            on_success=lambda result: self._on_template_saved(save_btn),
            on_error=lambda error: self._on_template_save_error(save_btn, error),
        )

    def _on_template_saved(self, save_btn: QPushButton):
        save_btn.setEnabled(True)
        QMessageBox.information(self, "Saved", "Template saved.")
        self._refresh_sms_templates()

    def _on_template_save_error(self, save_btn: QPushButton, error):
        save_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Could not save template.\n{error}")

    # --- Settings tab -----------------------------------------------------

    def _build_settings_tab(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        panel = QFrame()
        panel.setStyleSheet(PANEL_STYLE)
        panel.setFixedWidth(420)
        form = QFormLayout(panel)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)

        title = QLabel("This Machine's Settings")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        form.addRow(title)

        note = QLabel("These apply only to this computer, not the shared server.")
        note.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 12px;")
        note.setWordWrap(True)
        form.addRow(note)

        self.settings_server_url = QLineEdit()
        self.settings_server_url.setStyleSheet(INPUT_STYLE)
        lbl1 = QLabel("Server URL"); lbl1.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        form.addRow(lbl1, self.settings_server_url)

        self.settings_poll_seconds = QSpinBox()
        self.settings_poll_seconds.setStyleSheet(INPUT_STYLE)
        self.settings_poll_seconds.setRange(1, 60)
        self.settings_poll_seconds.setSuffix(" sec")
        lbl2 = QLabel("Staff dashboard refresh"); lbl2.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        form.addRow(lbl2, self.settings_poll_seconds)

        save_btn = QPushButton("Save Settings")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        save_btn.clicked.connect(self._save_local_settings)
        form.addRow(save_btn)

        restart_note = QLabel("Restart the app for changes to take effect.")
        restart_note.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 11px;")
        form.addRow(restart_note)

        layout.addWidget(panel)
        layout.addStretch()
        return wrapper

    def _load_settings_tab(self):
        # Purely local file I/O, not a network call - no threading needed.
        settings = load_settings()
        self.settings_server_url.setText(settings["server_url"])
        self.settings_poll_seconds.setValue(settings["staff_poll_seconds"])

    def _save_local_settings(self):
        url = self.settings_server_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing info", "Server URL can't be empty.")
            return
        save_settings({
            "server_url": url,
            "staff_poll_seconds": self.settings_poll_seconds.value(),
        })
        QMessageBox.information(self, "Saved", "Settings saved. Restart the app for them to take effect.")

    # --- SMS Settings tab (provider config) -----------------------------

    def _build_sms_settings_tab(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        panel = QFrame()
        panel.setStyleSheet(PANEL_STYLE)
        panel.setFixedWidth(420)
        form = QFormLayout(panel)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)

        title = QLabel("SMS Provider")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        form.addRow(title)

        note = QLabel("Controls how the server sends patient notifications. Takes effect immediately, no restart needed.")
        note.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 12px;")
        note.setWordWrap(True)
        form.addRow(note)

        self.sms_provider_combo = QComboBox()
        self.sms_provider_combo.setStyleSheet(INPUT_STYLE)
        self.sms_provider_combo.addItems(["console", "semaphore", "iprog"])
        lbl1 = QLabel("Provider"); lbl1.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        form.addRow(lbl1, self.sms_provider_combo)

        self.sms_api_key_input = QLineEdit()
        self.sms_api_key_input.setStyleSheet(INPUT_STYLE)
        self.sms_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.sms_api_key_input.setPlaceholderText("Leave blank to keep the current key")
        lbl2 = QLabel("API Key"); lbl2.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        form.addRow(lbl2, self.sms_api_key_input)

        self.sms_current_key_label = QLabel("")
        self.sms_current_key_label.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 11px;")
        form.addRow(QLabel(""), self.sms_current_key_label)

        self.sms_sender_input = QLineEdit()
        self.sms_sender_input.setStyleSheet(INPUT_STYLE)
        lbl3 = QLabel("Sender Name"); lbl3.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        form.addRow(lbl3, self.sms_sender_input)

        self.save_sms_settings_btn = QPushButton("Save SMS Settings")
        self.save_sms_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_sms_settings_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self.save_sms_settings_btn.clicked.connect(self._save_sms_settings)
        form.addRow(self.save_sms_settings_btn)

        layout.addWidget(panel)

        # Test send panel
        test_panel = QFrame()
        test_panel.setStyleSheet(PANEL_STYLE)
        test_panel.setFixedWidth(420)
        test_form = QFormLayout(test_panel)
        test_form.setContentsMargins(24, 20, 24, 20)
        test_form.setSpacing(12)

        test_title = QLabel("Send Test Message")
        test_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        test_title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        test_form.addRow(test_title)

        self.sms_test_number = QLineEdit()
        self.sms_test_number.setStyleSheet(INPUT_STYLE)
        self.sms_test_number.setPlaceholderText("63XXXXXXXXXX")
        lbl4 = QLabel("Phone Number"); lbl4.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")
        test_form.addRow(lbl4, self.sms_test_number)

        self.test_sms_btn = QPushButton("Send Test SMS")
        self.test_sms_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_sms_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self.test_sms_btn.clicked.connect(self._send_test_sms)
        test_form.addRow(self.test_sms_btn)

        layout.addWidget(test_panel)
        layout.addStretch()

        self._load_sms_settings()
        return wrapper

    def _load_sms_settings(self):
        self._sms_settings_worker = run_async(
            self.api.get_sms_settings,
            on_success=self._render_sms_settings,
            on_error=lambda e: None,
        )

    def _render_sms_settings(self, settings: dict):
        idx = self.sms_provider_combo.findText(settings["provider"])
        if idx >= 0:
            self.sms_provider_combo.setCurrentIndex(idx)
        self.sms_sender_input.setText(settings["sender_name"])
        masked = settings["api_key_masked"]
        self.sms_current_key_label.setText(f"Current key: {masked}" if masked else "No key set yet")

    def _save_sms_settings(self):
        provider = self.sms_provider_combo.currentText()
        api_key = self.sms_api_key_input.text().strip()
        sender_name = self.sms_sender_input.text().strip()

        self.save_sms_settings_btn.setEnabled(False)
        self._save_sms_settings_worker = run_async(
            lambda: self.api.update_sms_settings(
                provider, api_key=api_key or None, sender_name=sender_name, actor_id=self.user["id"]
            ),
            on_success=self._on_sms_settings_saved,
            on_error=self._on_sms_settings_save_error,
        )

    def _on_sms_settings_saved(self, result):
        self.save_sms_settings_btn.setEnabled(True)
        self.sms_api_key_input.clear()
        QMessageBox.information(self, "Saved", "SMS settings updated. Takes effect immediately.")
        self._load_sms_settings()

    def _on_sms_settings_save_error(self, error):
        self.save_sms_settings_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Could not save SMS settings.\n{error}")

    def _send_test_sms(self):
        number = self.sms_test_number.text().strip()
        if not number:
            QMessageBox.warning(self, "Missing number", "Enter a phone number to test.")
            return

        self.test_sms_btn.setEnabled(False)
        self._test_sms_worker = run_async(
            lambda: self.api.send_test_sms(number),
            on_success=self._on_test_sms_sent,
            on_error=self._on_test_sms_error,
        )

    def _on_test_sms_sent(self, result):
        self.test_sms_btn.setEnabled(True)
        QMessageBox.information(self, "Sent", f"Test SMS sent via {result['provider']}.")

    def _on_test_sms_error(self, error):
        self.test_sms_btn.setEnabled(True)
        QMessageBox.critical(self, "Test failed", f"Could not send test SMS.\n{error}")

    # --- Queue overview tab -------------------------------------------

    def _build_overview_tab(self):
        wrapper = QWidget()
        self.overview_layout = QVBoxLayout(wrapper)
        self.overview_layout.setContentsMargins(0, 16, 0, 0)
        self.overview_layout.setSpacing(10)
        return wrapper

    def _load_departments(self):
        self._dept_worker = run_async(
            self.api.list_departments,
            on_success=self._on_departments_loaded,
            on_error=lambda e: None,
        )

    def _on_departments_loaded(self, departments: list):
        self.departments = departments

        self.new_department.clear()
        for dept in self.departments:
            self.new_department.addItem(dept["name"], dept["id"])

        if hasattr(self, "sms_department"):
            current = self.sms_department.currentData()
            self.sms_department.clear()
            for dept in self.departments:
                self.sms_department.addItem(dept["name"], dept["id"])
            if current:
                idx = self.sms_department.findData(current)
                if idx >= 0:
                    self.sms_department.setCurrentIndex(idx)

        self._render_department_list()
        self._refresh_overview()

    def _refresh_overview(self):
        self._overview_worker = run_async(
            self.api.list_queue,
            on_success=self._render_overview,
            on_error=lambda e: None,
        )

    def _render_overview(self, entries: list):
        while self.overview_layout.count():
            item = self.overview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for dept in self.departments:
            dept_entries = [e for e in entries if e["department_id"] == dept["id"]]
            counts = {}
            for status in STATUS_LABELS:
                counts[status] = len([e for e in dept_entries if e["status"] == status])

            row = QFrame()
            row.setStyleSheet(PANEL_STYLE)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(18, 12, 18, 12)

            name = QLabel(dept["name"])
            name.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; font-weight: 600;")
            name.setFixedWidth(240)
            row_layout.addWidget(name)

            for status, count in counts.items():
                color = STATUS_COLORS.get(status, "#8fa3b0")
                chip = QLabel(f"{STATUS_LABELS[status]}: {count}")
                chip.setStyleSheet(f"color: {color}; font-weight: 600; margin-right: 16px;")
                row_layout.addWidget(chip)

            row_layout.addStretch()
            self.overview_layout.addWidget(row)

        self.overview_layout.addStretch()

    # --- Reports tab -----------------------------------------------------

    def _build_reports_tab(self):
        wrapper = QWidget()
        self.reports_layout = QVBoxLayout(wrapper)
        self.reports_layout.setContentsMargins(0, 16, 0, 0)
        self.reports_layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Today's Summary")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        header_row.addWidget(title)
        header_row.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        refresh_btn.clicked.connect(self._load_reports)
        header_row.addWidget(refresh_btn)
        self.reports_layout.addLayout(header_row)

        self.reports_rows_container = QVBoxLayout()
        self.reports_layout.addLayout(self.reports_rows_container)
        self.reports_layout.addStretch()

        self._load_reports()
        return wrapper

    def _load_reports(self):
        self._reports_worker = run_async(
            self.api.get_daily_summary,
            on_success=self._render_reports,
            on_error=lambda error: QMessageBox.critical(self, "Error", f"Could not load report.\n{error}"),
        )

    def _render_reports(self, summary: dict):
        while self.reports_rows_container.count():
            item = self.reports_rows_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for dept in summary.get("departments", []):
            row = QFrame()
            row.setStyleSheet(PANEL_STYLE)
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(18, 14, 18, 14)
            row_layout.setSpacing(6)

            name = QLabel(dept["department_name"])
            name.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            name.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
            row_layout.addWidget(name)

            stats_row = QHBoxLayout()
            stats = [
                ("Registered", dept["total_registered"]),
                ("Done", dept["done"]),
                ("Waiting", dept["waiting"]),
                ("In Consultation", dept["in_consultation"]),
                ("No Show", dept["no_show"]),
                ("Cancelled", dept["cancelled"]),
            ]
            for label, value in stats:
                chip = QLabel(f"{label}: {value}")
                chip.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; font-size: 12px;")
                stats_row.addWidget(chip)
            stats_row.addStretch()
            row_layout.addLayout(stats_row)

            timing_row = QHBoxLayout()
            avg_wait = dept["avg_wait_minutes"]
            avg_consult = dept["avg_consultation_minutes"]
            wait_label = QLabel(f"Avg wait: {avg_wait} min" if avg_wait is not None else "Avg wait: —")
            wait_label.setStyleSheet(f"color: {Color.AMBER_TEXT}; font-size: 12px; font-weight: 600;")
            consult_label = QLabel(f"Avg consultation: {avg_consult} min" if avg_consult is not None else "Avg consultation: —")
            consult_label.setStyleSheet(f"color: {Color.BLUE_TEXT}; font-size: 12px; font-weight: 600; margin-left: 16px;")
            timing_row.addWidget(wait_label)
            timing_row.addWidget(consult_label)
            timing_row.addStretch()
            row_layout.addLayout(timing_row)

            self.reports_rows_container.addWidget(row)

    # --- Audit Log tab -----------------------------------------------------

    def _build_audit_log_tab(self):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Recent Activity")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        header_row.addWidget(title)
        header_row.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        refresh_btn.clicked.connect(self._load_audit_log)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        self.audit_scroll = QScrollArea()
        self.audit_scroll.setWidgetResizable(True)
        self.audit_scroll.setStyleSheet("border: none;")
        self.audit_container = QWidget()
        self.audit_layout = QVBoxLayout(self.audit_container)
        self.audit_layout.setSpacing(6)
        self.audit_layout.addStretch()
        self.audit_scroll.setWidget(self.audit_container)
        layout.addWidget(self.audit_scroll, stretch=1)

        self._load_audit_log()
        return wrapper

    def _load_audit_log(self):
        self._audit_worker = run_async(
            lambda: self.api.list_audit_logs(limit=100),
            on_success=self._render_audit_log,
            on_error=lambda error: QMessageBox.critical(self, "Error", f"Could not load audit log.\n{error}"),
        )

    def _render_audit_log(self, logs: list):
        while self.audit_layout.count() > 1:
            item = self.audit_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for log in logs:
            row = QFrame()
            row.setStyleSheet(ROW_STYLE)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 8, 14, 8)

            action = QLabel(log["action"])
            action.setStyleSheet(f"color: {Color.TEXT_PRIMARY}; font-weight: 600;")
            action.setFixedWidth(220)

            target = QLabel(log.get("target") or "—")
            target.setStyleSheet(f"color: {Color.TEXT_SECONDARY};")

            meta = QLabel(f"{log.get('user_name', 'System')} · {self._format_timestamp(log.get('timestamp'))}")
            meta.setStyleSheet(f"color: {Color.TEXT_MUTED}; font-size: 11px;")

            row_layout.addWidget(action)
            row_layout.addWidget(target, stretch=1)
            row_layout.addWidget(meta)

            self.audit_layout.insertWidget(self.audit_layout.count() - 1, row)

    @staticmethod
    def _format_timestamp(ts: str) -> str:
        if not ts:
            return "—"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")
        except (ValueError, TypeError):
            return ts