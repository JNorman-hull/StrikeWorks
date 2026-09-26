# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Start-up helpers for main.py: the app icon, the loading splash, the
default data folders and the Windows taskbar identity.
"""
import platform
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from . import settings
from .theme import CARD_BG, MUTED, TEXT

# relative to this file rather than the working directory, so it still
# resolves when the exe is launched from a shortcut (frozen, both files
# sit in _internal/)
ICON_PATH = Path(__file__).parent.parent / "icon.ico"
_LOGO_PATH = Path(__file__).parent.parent / "images" / "images" / "PyDracula_vertical.png"


def build_splash():
    """The loading splash shown while MainWindow builds its pages: the
    logo and tagline centred above a "Loading application..." message."""
    pix = QPixmap(420, 480)
    pix.fill(QColor(CARD_BG))
    painter = QPainter(pix)

    logo = QPixmap(str(_LOGO_PATH)) if _LOGO_PATH.exists() else QPixmap()
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
