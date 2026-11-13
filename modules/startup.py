"""Start-up helpers for main.py: the app icon, the logos, the loading
splash, the default data folders, the Windows taskbar identity and which
edition is running.
"""
import os
import platform
from pathlib import Path

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QSplashScreen, QWidget

from . import settings
from .theme import CARD_BG, MUTED


def simple_only() -> bool:
    """True in the Simple edition: StrikeWorks only, the Development
    toolkit locked. `build.py --simple` compiles in a start-up hook
    (tools/simple_edition_hook.py) that sets STRIKEWORKS_EDITION=simple;
    set the variable to try it from source."""
    return os.environ.get("STRIKEWORKS_EDITION", "").strip().lower() == "simple"


# relative to this file rather than the working directory, so it still
# resolves when the exe is launched from a shortcut (frozen, both files
# sit in _internal/)
ICON_PATH = Path(__file__).parent.parent / "icon.ico"   # built from icon.png
# StrikeWorks | University of Hull logo, white for the dark theme: 300 dpi
# for the large copies (Home, Finished, splash, About), 96 dpi for the
# small ones (StrikeWorks's bottom bar, the toolkit's sidebar)
_LOGOS = Path(__file__).parent.parent / "images"


def logo_path(large=True):
    return _LOGOS / f"strikeworks_uoh_{300 if large else 96}.png"


def _drawn_rect(pix):
    """The part of `pix` with anything drawn on it - the logo files carry a
    transparent margin, which would otherwise shrink and offset them."""
    img = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    rows = np.frombuffer(img.constBits(), np.uint8).reshape(
        img.height(), img.bytesPerLine())
    alpha = rows[:, 3:img.width() * 4:4]          # B, G, R, A per pixel
    ys, xs = np.nonzero(alpha > 8)
    if not len(xs):
        return pix.rect()
    return QRect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
                 int(ys.max() - ys.min() + 1))


def logo_pixmap(width=None, height=None, large=True):
    """The logo cropped to its drawing, scaled to `width` or `height` px;
    a null pixmap if the file is missing."""
    pix = QPixmap(str(logo_path(large)))
    if pix.isNull():
        return pix
    pix = pix.copy(_drawn_rect(pix))
    smooth = Qt.TransformationMode.SmoothTransformation
    if width:
        return pix.scaledToWidth(width, smooth)
    if height:
        return pix.scaledToHeight(height, smooth)
    return pix


def icon_pixmap(size):
    """The app icon (images/icon.png - the same picture as icon.ico),
    cropped to its drawing and fitted into `size` x `size` px; a null
    pixmap if the file is missing."""
    pix = QPixmap(str(_LOGOS / "icon.png"))
    if pix.isNull():
        return pix
    return pix.copy(_drawn_rect(pix)).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation)


def logo_label(width=None, height=None, large=True):
    """A QLabel showing the logo (`logo_pixmap`), centred; None if the file
    is missing."""
    pix = logo_pixmap(width, height, large)
    if pix.isNull():
        return None
    label = QLabel()
    label.setPixmap(pix)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def build_splash():
    """The loading splash shown while MainWindow builds its pages: the
    logo and room for the "Loading application..." message - no bigger
    than they need."""
    logo_w, pad, message_h = 340, 22, 36
    logo = logo_pixmap(width=logo_w)
    width = (logo.width() if not logo.isNull() else logo_w) + 2 * pad
    height = pad + (logo.height() if not logo.isNull() else 0) + message_h
    pix = QPixmap(width, height)
    pix.fill(QColor(CARD_BG))
    if not logo.isNull():
        painter = QPainter(pix)
        painter.drawPixmap(pad, pad, logo)
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


class ScaledLogo(QWidget):
    """The small (96 dpi) logo at up to `max_width`, scaled down to fit a
    narrower space - the toolkit's sidebar - and not drawn at all once
    narrower than `min_width` (the sidebar collapsed to its icon strip)."""

    def __init__(self, max_width, min_width=120):
        super().__init__()
        self._source = logo_pixmap(large=False)
        self._max, self._min = max_width, min_width
        self._pix = QPixmap()
        ratio = (self._source.height() / self._source.width()
                 if not self._source.isNull() else 0.35)
        self.setFixedHeight(round(max_width * ratio))
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event):
        width = min(self._max, self.width())
        if self._source.isNull() or width < self._min:
            return
        if self._pix.width() != width:
            self._pix = self._source.scaledToWidth(
                width, Qt.TransformationMode.SmoothTransformation)
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
