"""Launch the public queue display: `python display.py` from the client
folder. Meant to run full-screen on a TV/monitor in the waiting room —
no login, read-only, auto-refreshing."""
import sys
from PyQt6.QtWidgets import QApplication

from ui.display_window import DisplayWindow


def main():
    app = QApplication(sys.argv)
    window = DisplayWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()