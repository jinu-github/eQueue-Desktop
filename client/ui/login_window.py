from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from api_client import (
    ApiClient,
    ServerUnreachableError,
    ServerTimeoutError,
    InvalidCredentialsError,
    ServiceUnavailableError,
    ServerError,
)
from async_worker import run_async
from theme import Color, PRIMARY_BTN_STYLE


class LoginWindow(QWidget):
    def __init__(self, on_login_success):
        super().__init__()
        self.api = ApiClient()
        self.on_login_success = on_login_success
        self.setWindowTitle("eQueue — Sign in")
        self.setFixedSize(420, 480)
        self.setStyleSheet(f"background-color: {Color.WINDOW_BG};")
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 60, 40, 40)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{ background-color: {Color.PANEL_BG}; border-radius: 16px; }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(14)

        title = QLabel("eQueue")
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Color.TEXT_PRIMARY};")
        subtitle = QLabel("Queue management, reimagined")
        subtitle.setStyleSheet(f"color: {Color.TEXT_SECONDARY}; margin-bottom: 16px;")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        for field in (self.username_input, self.password_input):
            field.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {Color.WINDOW_BG};
                    color: {Color.TEXT_PRIMARY};
                    border: 1px solid {Color.BORDER};
                    border-radius: 8px;
                    padding: 10px 12px;
                    font-size: 14px;
                }}
                QLineEdit:focus {{ border: 1px solid {Color.BLUE}; }}
            """)
            field.setMinimumHeight(40)

        self.login_btn = QPushButton("Sign in")
        self.login_btn.setMinimumHeight(42)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setStyleSheet(PRIMARY_BTN_STYLE)
        self.login_btn.clicked.connect(self._handle_login)
        self.password_input.returnPressed.connect(self._handle_login)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addWidget(self.username_input)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(8)
        card_layout.addWidget(self.login_btn)

        outer.addWidget(card)

    def _handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Missing info", "Enter both username and password.")
            return

        self._set_loading(True)
        self._login_worker = run_async(
            lambda: self.api.login(username, password),
            on_success=self._on_login_success,
            on_error=self._on_login_error,
        )

    def _set_loading(self, loading: bool):
        self.username_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.login_btn.setEnabled(not loading)
        self.login_btn.setText("Signing in…" if loading else "Sign in")

    def _on_login_success(self, user: dict):
        self._set_loading(False)
        self.on_login_success(user)

    def _on_login_error(self, error: Exception):
        self._set_loading(False)
        if isinstance(error, InvalidCredentialsError):
            QMessageBox.critical(self, "Login failed", "Invalid username or password.")
        elif isinstance(error, ServerUnreachableError):
            QMessageBox.critical(
                self, "Server unavailable",
                f"Can't reach the eQueue server at {self.api.base_url}.\n\n"
                "Make sure the server is running, or check the server URL."
            )
        elif isinstance(error, ServerTimeoutError):
            QMessageBox.critical(
                self, "Connection timed out",
                "The server didn't respond in time. It may be overloaded or unreachable."
            )
        elif isinstance(error, ServiceUnavailableError):
            QMessageBox.critical(
                self, "Database unavailable",
                f"The server is running but can't reach its database.\n\n{error}"
            )
        elif isinstance(error, ServerError):
            QMessageBox.critical(self, "Unexpected server error", str(error))
        else:
            QMessageBox.critical(self, "Unexpected error", str(error))