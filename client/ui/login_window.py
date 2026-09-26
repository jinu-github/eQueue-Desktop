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


class LoginWindow(QWidget):
    def __init__(self, on_login_success):
        super().__init__()
        self.api = ApiClient()
        self.on_login_success = on_login_success
        self.setWindowTitle("eQueue — Sign in")
        self.setFixedSize(420, 480)
        self.setStyleSheet("background-color: #0f172a;")
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 60, 40, 40)

        card = QFrame()
        card.setStyleSheet("""
            QFrame { background-color: #1e293b; border-radius: 16px; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(14)

        title = QLabel("eQueue")
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        title.setStyleSheet("color: #f8fafc;")
        subtitle = QLabel("Queue management, reimagined")
        subtitle.setStyleSheet("color: #94a3b8; margin-bottom: 16px;")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        for field in (self.username_input, self.password_input):
            field.setStyleSheet("""
                QLineEdit {
                    background-color: #0f172a;
                    color: #f8fafc;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 10px 12px;
                    font-size: 14px;
                }
                QLineEdit:focus { border: 1px solid #3b82f6; }
            """)
            field.setMinimumHeight(40)

        login_btn = QPushButton("Sign in")
        login_btn.setMinimumHeight(42)
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border-radius: 8px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        login_btn.clicked.connect(self._handle_login)
        self.password_input.returnPressed.connect(self._handle_login)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addWidget(self.username_input)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(8)
        card_layout.addWidget(login_btn)

        outer.addWidget(card)

    def _handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Missing info", "Enter both username and password.")
            return
        try:
            user = self.api.login(username, password)
        except InvalidCredentialsError:
            QMessageBox.critical(self, "Login failed", "Invalid username or password.")
            return
        except ServerUnreachableError:
            QMessageBox.critical(
                self, "Server unavailable",
                f"Can't reach the eQueue server at {self.api.base_url}.\n\n"
                "Make sure the server is running, or check the server URL."
            )
            return
        except ServerTimeoutError:
            QMessageBox.critical(
                self, "Connection timed out",
                "The server didn't respond in time. It may be overloaded or unreachable."
            )
            return
        except ServiceUnavailableError as e:
            QMessageBox.critical(
                self, "Database unavailable",
                f"The server is running but can't reach its database.\n\n{e}"
            )
            return
        except ServerError as e:
            QMessageBox.critical(self, "Unexpected server error", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Unexpected error", str(e))
            return
        self.on_login_success(user)