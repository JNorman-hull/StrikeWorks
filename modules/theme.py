# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The app's themes: one palette per theme, the app stylesheet built from
it (themes/app.qss), and the colours the code draws with directly (list
items, plots, figures).

The theme is chosen in Settings and read once, at start-up; a change
applies the next time the app starts.

Widgets get their look from the stylesheet, not from colours of their
own: `style(widget, role=..., tone=...)` tags a widget with a role (a kind
of text or button - see the list in app.qss) and/or a tone (a status
colour: ok, warn, bad, accent, info, highlight, muted).
"""
import gc
import re
from pathlib import Path

from PySide6.QtWidgets import QLabel

from . import settings

_QSS = Path(__file__).parent.parent / "themes" / "app.qss"

# the dark theme's two blues (in place of its original purple and pink):
# navy fills what sits behind white text (headers, pressed and primary
# buttons, selections, scrollbar handles), light blue is anything drawn on
# the dark background (markers, accent and link text, rings, the spinner)
NAVY, LIGHT_BLUE = "#0d1446", "#81daf4"
# its data series (charts, rings, figures), from the same brand strip:
# first green, then lime, then orange ...
GREEN, LIME, ORANGE, PINK_S, LAVENDER = (
    "#75dfb8", "#d6f677", "#f2bb6b", "#f0afdd", "#ab9df3")
SERIES = [GREEN, LIME, ORANGE, LIGHT_BLUE, PINK_S, LAVENDER]

STRIKEWORKS = {
    "label": "StrikeWorks (dark)",
    # content
    "bg": "#282c34", "border": "#2c313a", "card": "#21252b", "grid": "#2c313c",
    "text": "#dddddd", "muted": "#8a95aa", "disabled_text": "#717e95",
    "placeholder": "#15181d", "empty": "#3a4150", "session_box": "#ffffff",
    # sidebar, section panel, title and status bars
    "sidebar": "#21252b", "sidebar_text": "#dddddd", "sidebar_subtle": "#717e95",
    "sidebar_caption": LIGHT_BLUE, "sidebar_hover": "#282c34",
    "sidebar_selected": "#282c34", "sidebar_panel": "#2c313a",
    "sidebar_line": "#2c313a", "sidebar_toggle": "#252930",
    "titlebar": "#21252b", "titlebar_hover": "#2c3139", "titlebar_pressed": "#171a1e",
    "statusbar": "#2c313a",
    # accents
    "accent": NAVY, "accent_hover": "#1c2a73", "accent_pressed": "#080d2e",
    "on_accent": "#ffffff", "accent_text": LIGHT_BLUE,
    "highlight": LIGHT_BLUE, "on_highlight": NAVY, "highlight_text": LIGHT_BLUE,
    "selection": NAVY, "on_selection": "#ffffff", "link": LIGHT_BLUE,
    "tooltip_bg": "rgba(33, 37, 43, 180)", "tooltip_text": "#ffffff",
    # inputs
    "input": "#21252b", "input_border": "#21252b", "input_hover": "#404758",
    "input_focus": "#5b657c", "field": "#1b1d23",
    "combo_divider": "rgba(39, 44, 54, 150)", "combo_button": "transparent",
    "popup": "#21252b", "popup_text": LIGHT_BLUE, "popup_selection": "#272c36",
    "track": "#343b48", "track_end": "#373f4d", "track_hover": "#373e4c",
    "handle": NAVY,
    "indicator": "#2c313c", "indicator_border": "#343b48",
    "indicator_hover": "#3a4251", "indicator_checked": "#343b48",
    "radio_checked": "#5e6a82",
    # buttons
    "button": "#343b48", "button_text": "#dddddd", "button_hover": "#394150",
    "button_hover_border": "#3d4656", "button_pressed": "#232831",
    "button_pressed_border": "#2b323d",
    "primary": NAVY, "on_primary": "#ffffff", "primary_hover": "#1c2a73",
    "alternative": "#ef4444", "on_alternative": "#ffffff",
    "console": "#1b1e23", "console_text": "#d4d4d4",
    # status
    "ok": "#22c55e", "warn": "#f59e0b", "bad": "#ef4444", "info": "#568af2",
    # drawing: ring segments, figures, signal plots
    "palette": SERIES,
    "figure_palette": SERIES,
    # plots sit on the page's own background
    "screen_bg": "#282c34", "screen_axes": "#282c34", "screen_fg": "#c8cdd6",
    "screen_grid": "#3a4150", "plot_fg": "#c8cdd6",
    "trace": "#dddddd", "trace2": "#ff5555", "nadir": "#ffdc00",
    "region_fill": (120, 170, 255, 35), "region_edge": (120, 170, 255, 90),
    "dark": True,
}

# one theme for now; Settings > Appearance lists whatever is here, and a
# light one would set "dark": False (white plots - and it would need a
# navy logo: startup.logo_path)
THEMES = {"strikeworks": STRIKEWORKS}
NAME = settings.get_theme() if settings.get_theme() in THEMES else "strikeworks"
P = THEMES[NAME]

# the colours code draws with directly
CARD_BG = P["card"]
BORDER = P["border"]
TEXT = P["text"]
MUTED = P["muted"]
ACCENT = P["accent_text"]          # drawn on the page: text, rings, list items
PINK = P["highlight_text"]
OK = P["ok"]
WARN = P["warn"]
BAD = P["bad"]
INFO = P["info"]
EMPTY = P["empty"]
PALETTE = list(P["palette"])      # ring segments / stacked bars

# the live signal plots (pyqtgraph)
TRACE = P["trace"]                # the main channel
TRACE2 = P["trace2"]              # the second channel, on the right axis
NADIR = P["nadir"]                # the nadir line
REGION_FILL = P["region_fill"]    # the ROI / sync window
REGION_EDGE = P["region_edge"]

# Minimum widths only - every card expands to share the row, so a page
# never forces a horizontal scrollbar at a sensible window size.
CARD_W, CARD_H   = 205, 124
CARD_W2, CARD_H2 = 112, 112


def stylesheet():
    """The app stylesheet, with every @token filled from the palette."""
    def token(m):
        value = P[m.group(1)]
        return value if isinstance(value, str) else f"rgba{tuple(value)}"
    return re.sub(r"@([a-z_0-9]+)", token, _QSS.read_text(encoding="utf-8"))


def apply(app):
    # a stylesheet change re-polishes every widget, running Python event
    # handlers as it goes; garbage collected in one of those (a widget
    # whose wrapper sits in a reference cycle, deleted mid-iteration) is
    # an access violation - so collect it first
    gc.collect()
    app.setStyleSheet(stylesheet())


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def style(widget, role=None, tone=None):
    """Set `widget`'s role and tone (None clears either) - like replacing
    its stylesheet, the previous look is dropped."""
    widget.setProperty("role", role or "")
    widget.setProperty("tone", tone or "")
    _repolish(widget)
    return widget


def set_flag(widget, name, on):
    """A true/false property the stylesheet selects on (the sidebar's
    "selected" and "boxOwner")."""
    widget.setProperty(name, bool(on))
    _repolish(widget)


def muted_label(text, wrap=False):
    """A QLabel in the muted (secondary) text colour."""
    lab = QLabel(text)
    style(lab, role="muted")
    lab.setWordWrap(wrap)
    return lab
