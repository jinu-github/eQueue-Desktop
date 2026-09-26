import sys
from PyQt6.QtWidgets import QApplication

from ui.login_window import LoginWindow
from ui.reception_dashboard import ReceptionDashboard
from ui.staff_dashboard import StaffDashboard

# NOTE: admin_dashboard.py still follows the same pattern as the other
# dashboards — sidebar + role-colored accent + live queue. Scaffold it
# next once the staff flow is confirmed to work end to end.


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
            self.window = StaffDashboard(user)
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
