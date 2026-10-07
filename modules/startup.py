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

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QSplashScreen

from . import settings, theme
from .theme import CARD_BG, MUTED, TEXT

# relative to this file rather than the working directory, so it still
# resolves when the exe is launched from a shortcut (frozen, both files
# sit in _internal/)
ICON_PATH = Path(__file__).parent.parent / "icon.ico"
_IMAGES = Path(__file__).parent.parent / "images" / "images"
# the StrikeWorks logo: the version outlined for white pages in the
# University of Hull theme, the original on the dark theme
LOGO_PATH = _IMAGES / ("PyDracula_vertical_white.png" if theme.NAME == "hull"
                       else "PyDracula_vertical.png")
# the University's Primary Brandmark, Ink Blue (positive) version: for white
# or light backgrounds only, never recoloured, at least 60 px wide
BRANDMARK_PATH = _IMAGES / "uoh_brandmark.svg"
# the University logo, black on transparent; white (its reverse) on a dark
# background
UOH_LOGO_PATH = _IMAGES / "UOH_logo.png"


def build_splash():
    """The loading splash shown while MainWindow builds its pages: the
    logo and tagline centred above a "Loading application..." message."""
    pix = QPixmap(420, 480)
    pix.fill(QColor(CARD_BG))
    painter = QPainter(pix)

    logo = QPixmap(str(LOGO_PATH)) if LOGO_PATH.exists() else QPixmap()
    if not logo.isNull():
        logo = logo.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation)

    font = QFont()
    font.setPointSize(13)
    font.setItalic(True)
    painter.setFont(font)
    tagline = "Deploy. Process. Predict."
    tagline_h = painter.fontMetrics().height()

    usable_h = pix.height() - 60      # room for the loading message
    spacing = 20
    logo_h = 0 if logo.isNull() else logo.height()
    block_h = logo_h + (spacing if logo_h else 0) + tagline_h
    top = max(20, (usable_h - block_h) // 2)
    if logo_h:
        painter.drawPixmap((pix.width() - logo.width()) // 2, top, logo)
        top += logo_h + spacing

    painter.setPen(QColor(TEXT))
    painter.drawText(0, top, pix.width(), tagline_h,
                     int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                     tagline)
    painter.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.showMessage(
        "Loading application...",
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
        QColor(MUTED))
    return splash


def brandmark(width=120):
    """A QLabel showing the University brandmark `width` px wide (60 px
    at least), or None if the file is missing."""
    renderer = QSvgRenderer(str(BRANDMARK_PATH))
    if not renderer.isValid():
        return None
    width = max(60, width)
    size = renderer.defaultSize()
    pix = QPixmap(QSize(width, round(width * size.height() / size.width())))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    label = QLabel()
    label.setPixmap(pix)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


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


def uoh_logo_pixmap(width, reverse=False):
    """The University of Hull logo `width` px wide, its transparent margin
    trimmed: black, or white with `reverse` for a dark background. A null
    pixmap if the file is missing."""
    image = QImage(str(UOH_LOGO_PATH))
    if image.isNull():
        return QPixmap()
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    # trim to the opaque part (the file has a wide transparent border)
    alpha = image.createAlphaMask()
    left, top = image.width(), image.height()
    right = bottom = -1
    step = max(1, image.width() // 400)
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            if alpha.pixelIndex(x, y):
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    if right >= left:
        image = image.copy(QRect(left, top, right - left + step,
                                 bottom - top + step))
    pix = QPixmap.fromImage(image).scaledToWidth(
        width, Qt.TransformationMode.SmoothTransformation)
    if reverse:
        painter = QPainter(pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pix.rect(), QColor("white"))
        painter.end()
    return pix


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
