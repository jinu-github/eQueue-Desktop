import math
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QSizePolicy
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from api_client import ApiClient, ApiError
from async_worker import run_async
from ws_client import QueueWebSocketClient

REFRESH_MS = 5000  # public display doesn't need to be as snappy as staff view
CALLED_HIGHLIGHT_MS = 8000
COLUMNS = 2

FONT_FAMILIES = ["IBM Plex Sans", "Segoe UI", "Arial"]

# Ticket prefixes shown before the queue number (e.g. LAB-023).
# A department dict can also provide "prefix" or "code"; otherwise this table is
# used, and if nothing matches the number is shown as plain "#23".
PREFIXES = {
    "laboratory": "LAB",
    "radiology": "RAD",
    "tb dots unit": "TB",
    "outpatient department (opd)": "OPD",
    "opd": "OPD",
}


# Shorter names shown on the panel instead of the full department name.
DISPLAY_NAMES = {
    "outpatient department (opd)": "OPD",
}


class Palette:
    HEADER_BG = "#0d1b2e"
    HEADER_TEXT = "#ffffff"
    GRID_LINE = "#cfd6df"
    PANEL_BG = "#ffffff"
    CALLED_BG = "#e6eff9"
    TEXT_PRIMARY = "#0d1b2e"
    TEXT_MUTED = "#586577"
    TEXT_IDLE = "#9aa5b4"
    ACCENT = "#1f5fa8"
    ACCENT_FADED = "rgba(31, 95, 168, 70)"


def make_font(px, weight=QFont.Weight.Normal, spacing=0.0):
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(max(1, int(px)))
    font.setWeight(weight)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px * spacing)
    return font


def format_number(department: dict, number) -> str:
    prefix = department.get("prefix") or department.get("code") or PREFIXES.get(department["name"].strip().lower())
    if prefix:
        return f"{prefix}-{str(number).zfill(3)}"
    return f"#{number}"


class DepartmentPanel(QFrame):
    def __init__(self, department: dict):
        super().__init__()
        self.setObjectName("panel")
        self.department = department
        self.department_id = department["id"]

        self._w, self._h = 1920, 1080
        self._has_serving = False
        self._prev_serving = None
        self._first_update = True
        self._called = False
        self._pulse_on = True

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._toggle_pulse)
        self._called_timer = QTimer(self)
        self._called_timer.setSingleShot(True)
        self._called_timer.timeout.connect(lambda: self._set_called(False))

        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        # Top row: department name on the left, NOW SERVING indicator on the right
        self.top = QHBoxLayout()
        full_name = department["name"]
        self.name = QLabel(DISPLAY_NAMES.get(full_name.strip().lower(), full_name).upper())
        self.name.setWordWrap(True)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.dot = QLabel()
        self.label = QLabel("NOW SERVING")
        self.top.addWidget(self.name, stretch=1)
        self.top.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.top.addWidget(self.label)
        layout.addLayout(self.top)

        # Centre: the queue number (or the empty state)
        self.number = QLabel("")
        self.number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.number.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.number, stretch=1)

        # Bottom: divider + NEXT number
        self.divider = QFrame()
        self.divider.setFixedHeight(1)
        self.divider.setStyleSheet(f"background-color: {Palette.GRID_LINE};")
        layout.addWidget(self.divider)

        self.bottom = QHBoxLayout()
        self.next_label = QLabel("")
        self.next_label.setTextFormat(Qt.TextFormat.RichText)
        self.bottom.addWidget(self.next_label)
        self.bottom.addStretch()
        layout.addLayout(self.bottom)

        self._render_number(None)
        self._render_next(None)
        self.apply_scale(self._w, self._h)

    # ---- data -------------------------------------------------------------

    def update_from_entries(self, entries: list):
        serving = next((e for e in entries if e["status"] == "in_consultation"), None)
        serving_number = serving["queue_number"] if serving else None
        self._render_number(serving_number)

        waiting = sorted((e for e in entries if e["status"] == "waiting"), key=lambda e: e["queue_number"])
        self._render_next(waiting[0]["queue_number"] if waiting else None)

        # Highlight the panel when a new number is called (not on the first load)
        if not self._first_update and serving_number is not None and serving_number != self._prev_serving:
            self._set_called(True)
        elif serving_number is None:
            self._set_called(False)
        self._prev_serving = serving_number
        self._first_update = False

    def _render_number(self, number):
        self._has_serving = number is not None
        if self._has_serving:
            self.number.setText(format_number(self.department, number))
        else:
            self.number.setText("NO PATIENT BEING SERVED")
        self._style_number()

    def _render_next(self, number):
        text = format_number(self.department, number) if number is not None else "—"
        self.next_label.setText(
            f'<span style="color:{Palette.TEXT_MUTED}; font-weight:500;">NEXT:</span> '
            f'<span style="color:{Palette.TEXT_PRIMARY};">{text}</span>'
        )

    # ---- calling state ----------------------------------------------------

    def _set_called(self, on: bool):
        self._called = on
        if on:
            self._pulse_on = True
            self._pulse_timer.start(900)
            self._called_timer.start(CALLED_HIGHLIGHT_MS)
        else:
            self._pulse_timer.stop()
            self._called_timer.stop()
        self._restyle()

    def _toggle_pulse(self):
        self._pulse_on = not self._pulse_on
        self._restyle()

    # ---- styling / scaling ------------------------------------------------

    def apply_scale(self, w: int, h: int):
        """Sizes are relative to the window, so the layout fills any 16:9 screen."""
        self._w, self._h = w, h
        side = int(0.022 * w)
        self.layout().setContentsMargins(side, int(0.024 * h), side, int(0.022 * h))
        self.top.setSpacing(int(0.006 * w))
        self.bottom.setContentsMargins(0, int(0.016 * h), 0, 0)

        self.name.setFont(make_font(min(0.021 * w, 0.043 * h), QFont.Weight.Bold, 0.06))
        self.label.setFont(make_font(min(0.0115 * w, 0.023 * h), QFont.Weight.Medium, 0.14))
        self.next_label.setFont(make_font(min(0.021 * w, 0.042 * h), QFont.Weight.DemiBold))

        dot = max(6, int(0.012 * h))
        self.dot.setFixedSize(dot, dot)
        self._style_number()
        self._restyle()

    def _style_number(self):
        if self._has_serving:
            self.number.setFont(make_font(min(0.086 * self._w, 0.19 * self._h), QFont.Weight.Bold))
            color = Palette.TEXT_PRIMARY
        else:
            self.number.setFont(make_font(min(0.021 * self._w, 0.043 * self._h), QFont.Weight.DemiBold, 0.06))
            color = Palette.TEXT_IDLE
        self.number.setStyleSheet(f"color: {color};")

    def _restyle(self):
        border = max(3, int(0.009 * self._h))
        if self._called:
            bg, top_color = Palette.CALLED_BG, Palette.ACCENT
            dot_color = Palette.ACCENT if self._pulse_on else Palette.ACCENT_FADED
            label_color = Palette.ACCENT
        else:
            bg, top_color = Palette.PANEL_BG, Palette.GRID_LINE
            dot_color = Palette.TEXT_IDLE
            label_color = Palette.TEXT_MUTED

        self.setStyleSheet(
            f"#panel {{ background-color: {bg}; border-top: {border}px solid {top_color}; }}"
            "#panel QLabel { background: transparent; }"
        )
        self.name.setStyleSheet(f"color: {Palette.TEXT_PRIMARY};")
        self.label.setStyleSheet(f"color: {label_color};")
        d = self.dot.width()
        self.dot.setStyleSheet(f"background-color: {dot_color}; border-radius: {d // 2}px;")


class DisplayWindow(QWidget):
    """Public, read-only queue display — no login. Meant for a TV/monitor
    in the waiting room. Launch via client/display.py."""

    def __init__(self):
        super().__init__()
        self.api = ApiClient()
        self.setWindowTitle("eQueue — Now Serving")
        self.setObjectName("displayRoot")
        self.setStyleSheet(f"#displayRoot {{ background-color: {Palette.GRID_LINE}; }}")

        self.departments = []
        self.panels = {}
        self._build_ui()
        self._update_clock()
        self._load_departments()
        self.showFullScreen()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(REFRESH_MS)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

        self._ws = QueueWebSocketClient(self.api.base_url)
        self._ws.message_received.connect(self._on_ws_message)
        self._ws.start()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setObjectName("header")
        self.header.setStyleSheet(f"#header {{ background-color: {Palette.HEADER_BG}; }}")
        self.header_layout = QHBoxLayout(self.header)
        self.title = QLabel("HOSPITAL QUEUE DISPLAY")
        self.title.setStyleSheet(f"color: {Palette.HEADER_TEXT};")
        self.time_label = QLabel("")
        self.time_label.setStyleSheet(f"color: {Palette.HEADER_TEXT};")
        self.date_label = QLabel("")
        self.date_label.setStyleSheet("color: rgba(255, 255, 255, 215);")
        self.header_layout.addWidget(self.title)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.time_label, alignment=Qt.AlignmentFlag.AlignBaseline)
        self.header_layout.addWidget(self.date_label, alignment=Qt.AlignmentFlag.AlignBaseline)
        outer.addWidget(self.header)

        # 2 x 2 grid (thin lines between panels come from the grid background)
        self.grid_container = QWidget()
        self.grid_container.setObjectName("gridContainer")
        self.grid_container.setStyleSheet(f"#gridContainer {{ background-color: {Palette.GRID_LINE}; }}")
        self.grid = QGridLayout(self.grid_container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(2)
        outer.addWidget(self.grid_container, stretch=1)

        # Footer
        self.footer = QLabel("Please wait for your queue number to be called.")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.footer)

        self._apply_scale()

    def _apply_scale(self):
        w, h = max(self.width(), 640), max(self.height(), 360)
        self.header_layout.setContentsMargins(int(0.02 * w), int(0.014 * h), int(0.02 * w), int(0.014 * h))
        self.header_layout.setSpacing(int(0.02 * w))
        self.title.setFont(make_font(min(0.022 * w, 0.04 * h), QFont.Weight.DemiBold, 0.08))
        self.time_label.setFont(make_font(min(0.026 * w, 0.048 * h), QFont.Weight.DemiBold))
        self.date_label.setFont(make_font(min(0.015 * w, 0.028 * h)))

        pad = max(4, int(0.009 * h))
        self.footer.setFont(make_font(min(0.011 * w, 0.02 * h)))
        self.footer.setStyleSheet(
            f"background-color: {Palette.PANEL_BG}; color: {Palette.TEXT_MUTED};"
            f"border-top: 1px solid {Palette.GRID_LINE}; padding: {pad}px 0px;"
        )
        for panel in self.panels.values():
            panel.apply_scale(w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scale()

    def _update_clock(self):
        now = datetime.now()
        self.time_label.setText(now.strftime("%I:%M %p").lstrip("0"))
        self.date_label.setText(f"{now:%A, %B} {now.day}, {now.year}")

    def _load_departments(self):
        self._dept_worker = run_async(
            self.api.list_departments,
            on_success=self._on_departments_loaded,
            on_error=lambda e: None,
        )

    def _on_departments_loaded(self, departments):
        self.departments = departments

        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.panels = {}

        rows = max(1, math.ceil(len(self.departments) / COLUMNS))
        for c in range(COLUMNS):
            self.grid.setColumnStretch(c, 1)
        for r in range(rows):
            self.grid.setRowStretch(r, 1)

        for index, dept in enumerate(self.departments):
            panel = DepartmentPanel(dept)
            self.panels[dept["id"]] = panel
            self.grid.addWidget(panel, index // COLUMNS, index % COLUMNS)

        self._apply_scale()
        self._refresh()

    def _refresh(self):
        if not self.departments:
            self._load_departments()
            return
        self._refresh_worker = run_async(
            self.api.list_queue,
            on_success=self._on_queue_loaded,
            on_error=lambda e: None,  # keep showing last known state
        )

    def _on_queue_loaded(self, entries):
        for dept in self.departments:
            dept_entries = [e for e in entries if e["department_id"] == dept["id"]]
            panel = self.panels.get(dept["id"])
            if panel:
                panel.update_from_entries(dept_entries)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        self.clock_timer.stop()
        self._ws.stop()
        super().closeEvent(event)

    def _on_ws_message(self, data: dict):
        if data.get("event") in ("queue_created", "queue_updated"):
            self._refresh()