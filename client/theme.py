"""
Shared visual theme for the eQueue desktop app.

Single source of truth for colors and common Qt stylesheet snippets, so
Admin, Reception, Staff, and the public Display window all read as one
product instead of four differently-themed windows. Import from here
instead of hardcoding hex values in a dashboard file.

    from theme import Color, PANEL_STYLE, INPUT_STYLE, PRIMARY_BTN_STYLE

Palette notes:
- One blue (Color.BLUE) is used for every primary action across every
  screen — "Create Account", "Register & Assign Queue Number",
  "Call Next Patient", "Complete Consultation", "Sign in" all share it.
- Green / amber / red are reserved for *status only* (queue states,
  now-serving indicators) — never used decoratively or as a button color.
- Sidebars are a single neutral dark tone across all three roles; the
  role is shown with a small badge (see role_badge_style) instead of a
  full-color background.
"""


class Color:
    # Backdrops
    WINDOW_BG = "#0f1b24"
    PANEL_BG = "#16242e"
    PANEL_BG_ALT = "#1b2b37"
    BORDER = "#26394a"

    # Text
    TEXT_PRIMARY = "#eaf1f6"
    TEXT_SECONDARY = "#8fa3b0"
    TEXT_MUTED = "#6b8394"

    # Brand — the one accent used for every primary action
    BLUE = "#2d74aa"
    BLUE_HOVER = "#245f89"
    BLUE_TEXT = "#6ba9d6"

    # Status colors — state only, never decoration
    GREEN = "#3fb37f"
    GREEN_TEXT = "#6fcb9a"
    AMBER = "#d99a4e"
    AMBER_TEXT = "#e2a85b"
    RED = "#d1554f"
    RED_HOVER = "#b8443f"
    RED_BG_SUBTLE = "#3a2220"
    RED_BG_SUBTLE_HOVER = "#4a2b28"
    RED_TEXT_SUBTLE = "#e8bdba"

    DISABLED_BG = "#26394a"
    DISABLED_TEXT = "#6b8394"

    SIDEBAR_BG = "#111c24"
    SIDEBAR_BORDER = "#1e2e3a"
    SIDEBAR_TEXT = "#c3d2db"


# Small pill shown under the "eQueue" wordmark in every sidebar, replacing
# the old full-color background as the way a user tells which role they're in.
ROLE_BADGE_COLORS = {
    "admin": Color.BLUE_TEXT,
    "staff": Color.GREEN_TEXT,
    "receptionist": Color.AMBER_TEXT,
}


PANEL_STYLE = f"QFrame {{ background-color: {Color.PANEL_BG}; border-radius: 12px; }}"

ROW_STYLE = f"QFrame {{ background-color: {Color.PANEL_BG}; border-radius: 8px; }}"

INPUT_STYLE = f"""
    QLineEdit, QComboBox, QSpinBox, QTextEdit {{
        background-color: {Color.WINDOW_BG}; color: {Color.TEXT_PRIMARY};
        border: 1px solid {Color.BORDER}; border-radius: 6px; padding: 8px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {Color.BLUE};
    }}
"""

PRIMARY_BTN_STYLE = f"""
    QPushButton {{
        background-color: {Color.BLUE}; color: white;
        border-radius: 6px; padding: 10px; font-weight: 600;
    }}
    QPushButton:hover {{ background-color: {Color.BLUE_HOVER}; }}
    QPushButton:disabled {{ background-color: {Color.DISABLED_BG}; color: {Color.DISABLED_TEXT}; }}
"""

SECONDARY_BTN_STYLE = f"""
    QPushButton {{
        background-color: {Color.PANEL_BG_ALT}; color: {Color.TEXT_PRIMARY};
        border: 1px solid {Color.BORDER}; border-radius: 6px; padding: 8px 12px;
    }}
    QPushButton:hover {{ background-color: {Color.BORDER}; }}
"""

DANGER_BTN_STYLE = f"""
    QPushButton {{
        background-color: transparent; color: {Color.RED};
        border: 1px solid {Color.RED}; border-radius: 6px;
        padding: 6px 10px; font-weight: 600; font-size: 12px;
    }}
    QPushButton:hover {{ background-color: {Color.RED}; color: white; }}
"""

DANGER_SOLID_BTN_STYLE = f"""
    QPushButton {{
        background-color: {Color.RED_BG_SUBTLE}; color: {Color.RED_TEXT_SUBTLE};
        border-radius: 6px; padding: 8px 12px;
    }}
    QPushButton:hover {{ background-color: {Color.RED_BG_SUBTLE_HOVER}; }}
"""

SIDEBAR_STYLE = f"QFrame {{ background-color: {Color.SIDEBAR_BG}; border-right: 1px solid {Color.SIDEBAR_BORDER}; }}"

LOGOUT_BTN_STYLE = f"""
    QPushButton {{
        background-color: transparent; color: {Color.SIDEBAR_TEXT};
        border: 1px solid {Color.SIDEBAR_BORDER}; border-radius: 6px; padding: 8px;
    }}
    QPushButton:hover {{ background-color: rgba(255,255,255,0.06); }}
"""


def role_badge_style(role_key: str) -> str:
    """QSS for the small role pill in a sidebar (replaces a full-color sidebar bg)."""
    color = ROLE_BADGE_COLORS.get(role_key, Color.TEXT_SECONDARY)
    return (
        f"color: {color}; font-weight: 600; font-size: 12px; "
        f"background-color: rgba(255,255,255,0.06); border-radius: 6px; "
        f"padding: 4px 10px;"
    )
