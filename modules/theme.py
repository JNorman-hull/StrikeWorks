# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Colours and sizes shared by every page (the app's dark theme),
plus small helpers for the recurring muted label and accent button.
"""
from PySide6.QtWidgets import QLabel

# theme colours (match the PyDracula palette used by the app)
CARD_BG = "#21252b"          # rgb(33,37,43)
BORDER  = "#2c313a"          # rgb(44,49,58)
TEXT    = "#dddddd"
MUTED   = "#8a95aa"
ACCENT  = "#bd93f9"          # purple
PINK    = "#ff79c6"
OK      = "#22c55e"
WARN    = "#f59e0b"
BAD     = "#ef4444"
INFO    = "#568af2"
EMPTY   = "#3a4150"

# category palette for ring segments / stacked bars
PALETTE = [INFO, PINK, WARN, OK, ACCENT, "#00bcd4"]

# Minimum widths only - every card expands to share the row, so a page
# never forces a horizontal scrollbar at a sensible window size.
CARD_W, CARD_H   = 205, 124
CARD_W2, CARD_H2 = 112, 112

# the filled purple button each page uses for its main action
ACCENT_BUTTON = (
    f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
    "border-radius:5px;padding:4px 14px;font-weight:bold;}"
    f"QPushButton:disabled{{background-color:{EMPTY};color:{MUTED};}}")


# the read-only log boxes (processing, training, dataset build)
CONSOLE_STYLE = (
    "QPlainTextEdit{background:#1b1e23;color:#d4d4d4;"
    f"border:1px solid {BORDER};border-radius:4px;"
    "font-family:Consolas,monospace;font-size:9pt;}")


def muted_label(text, wrap=False):
    """A QLabel in the muted (secondary) text colour."""
    lab = QLabel(text)
    lab.setStyleSheet(f"color:{MUTED};")
    lab.setWordWrap(wrap)
    return lab
