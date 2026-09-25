import sys
from PyQt6.QtWidgets import QApplication

from ui.login_window import LoginWindow
from ui.reception_dashboard import ReceptionDashboard

# NOTE: staff_dashboard.py and admin_dashboard.py follow the same pattern
# as reception_dashboard.py — sidebar + role-colored accent + live queue.
# Scaffold those next once the reception flow is confirmed to work end to end.


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
            self.window = ReceptionDashboard(user)
        elif role == "staff":
            # from ui.staff_dashboard import StaffDashboard
            # self.window = StaffDashboard(user)
            self.window = ReceptionDashboard(user)  # placeholder until staff view is built
        elif role == "admin":
            # from ui.admin_dashboard import AdminDashboard
            # self.window = AdminDashboard(user)
            self.window = ReceptionDashboard(user)  # placeholder until admin view is built
        self.window.show()


def main():
    app = QApplication(sys.argv)
    controller = AppController()
    controller.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
