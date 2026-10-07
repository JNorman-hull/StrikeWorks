# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Start-up helpers for main.py: the app icon, the logos, the loading
splash, the default data folders and the Windows taskbar identity.
"""
import platform
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QSizePolicy, QSplashScreen, QWidget

from . import settings, theme
from .theme import CARD_BG, MUTED

# relative to this file rather than the working directory, so it still
# resolves when the exe is launched from a shortcut (frozen, both files
# sit in _internal/)
ICON_PATH = Path(__file__).parent.parent / "icon.ico"
_IMAGES = Path(__file__).parent.parent / "images" / "images"
# the StrikeWorks logo: the version outlined for white pages in the
# University of Hull theme, the original on the dark theme
LOGO_PATH = _IMAGES / ("PyDracula_vertical_white.png" if theme.NAME == "hull"
                       else "PyDracula_vertical.png")
# the University's Primary Brandmark - the one University logo the app
# shows: Ink Blue (positive) on light backgrounds, white (negative) on dark,
# at least 60 px wide
BRANDMARK_PATH = _IMAGES / "uoh_brandmark.svg"


def build_splash():
    """The loading splash shown while MainWindow builds its pages: the
    StrikeWorks logo, the University brandmark under it, and room for the
    "Loading application..." message - no bigger than they need."""
    logo_w, mark_w, pad, gap, message_h = 200, 70, 22, 16, 36
    logo = QPixmap(str(LOGO_PATH)) if LOGO_PATH.exists() else QPixmap()
    if not logo.isNull():
        logo = logo.scaledToWidth(logo_w, Qt.TransformationMode.SmoothTransformation)
    mark = brandmark_pixmap(mark_w, reverse=theme.P["dark"])
    width = max(logo.width(), mark.width()) + 2 * pad
    height = (pad + logo.height() + (gap if not logo.isNull() else 0)
              + mark.height() + message_h)
    pix = QPixmap(width, height)
    pix.fill(QColor(CARD_BG))
    painter = QPainter(pix)
    top = pad
    if not logo.isNull():
        painter.drawPixmap((width - logo.width()) // 2, top, logo)
        top += logo.height() + gap
    if not mark.isNull():
        painter.drawPixmap((width - mark.width()) // 2, top, mark)
    painter.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    font = QFont()
    font.setPointSize(9)
    splash.setFont(font)
    splash.showMessage(
        "Loading application...",
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
        QColor(MUTED))
    return splash


def logo_label(width):
    """A QLabel showing the StrikeWorks logo (the theme's version) `width`
    px wide, centred; None if the file is missing."""
    pix = QPixmap(str(LOGO_PATH))
    if pix.isNull():
        return None
    label = QLabel()
    label.setPixmap(pix.scaledToWidth(
        width, Qt.TransformationMode.SmoothTransformation))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _brandmark_ratio(renderer):
    size = renderer.defaultSize()
    return size.height() / size.width()


def brandmark_pixmap(width, reverse=False):
    """The University brandmark `width` px wide: Ink Blue, or with
    `reverse` its white (negative) version, for a dark background. A null
    pixmap if the file is missing."""
    renderer = QSvgRenderer(str(BRANDMARK_PATH))
    if not renderer.isValid():
        return QPixmap()
    pix = QPixmap(QSize(width, round(width * _brandmark_ratio(renderer))))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    if reverse:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pix.rect(), QColor("white"))
    painter.end()
    return pix


def brandmark(width=120, reverse=None):
    """A QLabel showing the University brandmark `width` px wide (60 px at
    least), or None if the file is missing. White on the dark theme unless
    `reverse` says otherwise."""
    if reverse is None:
        reverse = theme.P["dark"]
    pix = brandmark_pixmap(max(60, width), reverse)
    if pix.isNull():
        return None
    label = QLabel()
    label.setPixmap(pix)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setToolTip("University of Hull")
    return label


class Brandmark(QWidget):
    """The University brandmark at up to `max_width`, scaled down to fit a
    narrower space (the sidebar collapsed to its icon strip) - never below
    the brand's 60 px; narrower than that it isn't drawn."""

    def __init__(self, max_width, reverse=False):
        super().__init__()
        renderer = QSvgRenderer(str(BRANDMARK_PATH))
        self._valid = renderer.isValid()
        self._ratio = _brandmark_ratio(renderer) if self._valid else 1.0
        self._max = max_width
        self._reverse = reverse
        self._pix = QPixmap()
        self.setFixedHeight(round(max_width * self._ratio))
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setToolTip("University of Hull")

    def paintEvent(self, _event):
        width = min(self._max, self.width())
        if not self._valid or width < 60:
            return
        if self._pix.width() != width:
            self._pix = brandmark_pixmap(width, self._reverse)
        painter = QPainter(self)
        painter.drawPixmap((self.width() - self._pix.width()) // 2,
                           (self.height() - self._pix.height()) // 2,
                           self._pix)
        painter.end()


def ensure_default_folders():
    """Create the libraries, models, output and input folders if missing,
    so a fresh install shows them straight away."""
    for getter in (settings.get_libraries_dir, settings.get_models_dir,
                   settings.get_output_dir, settings.get_input_data_dir):
        try:
            getter().mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Could not create {getter.__name__[4:]}: {e}")


def set_windows_app_id():
    """Give the process its own AppUserModelID, so Windows shows the
    StrikeWorks icon on the taskbar rather than grouping it under Python.
    No-op off Windows."""
    if platform.system() != "Windows":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "StrikeWorks.App")
    except (AttributeError, OSError):
        pass
