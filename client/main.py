import sys
from PyQt6.QtWidgets import QApplication

from ui.login_window import LoginWindow
from ui.reception_dashboard import ReceptionDashboard
from ui.staff_dashboard import StaffDashboard
from ui.admin_dashboard import AdminDashboard


class AppController:
    def __init__(self):
        self.window = None

    def start(self):
        self.show_login()

    def show_login(self):
        self.window = LoginWindow(self.handle_login)
        self.window.show()

    def handle_login(self, user: dict):
        self.window.close()
        role = user.get("role")
        if role == "receptionist":
            self.window = ReceptionDashboard(user, on_logout=self.logout)
        elif role == "staff":
            self.window = StaffDashboard(user, on_logout=self.logout)
        elif role == "admin":
            self.window = AdminDashboard(user, on_logout=self.logout)
        self.window.show()

    def logout(self):
        self.window.close()
        self.show_login()


def main():
    app = QApplication(sys.argv)
    controller = AppController()
    controller.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()