"""Window helpers for both windows: sizing a window to the screen's work
area, opening a folder in Explorer, and the taskbar button fix.
"""
import platform
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

# Windows' title bar and borders around a window's client area, until the
# window has been shown and its own can be measured
_FRAME_W, _FRAME_H = 16, 39

# set while the demos run, so their reports don't open Explorer windows
suppress_open_folder = False


def fit_to_screen(window, width, height):
    """Give `window` a `width` x `height` client area - less where that
    wouldn't fit, title bar and borders included, inside the screen's work
    area (the screen without the taskbar) - and centre it there."""
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        window.resize(width, height)
        return
    area = screen.availableGeometry()
    if window.isVisible():
        frame_w = window.frameGeometry().width() - window.width()
        frame_h = window.frameGeometry().height() - window.height()
    else:
        frame_w, frame_h = _FRAME_W, _FRAME_H
    w = min(width, area.width() - frame_w)
    h = min(height, area.height() - frame_h)
    # a minimum larger than the screen would push the window past it
    window.setMinimumSize(min(window.minimumWidth(), w),
                          min(window.minimumHeight(), h))
    window.resize(w, h)
    window.move(area.x() + (area.width() - w - frame_w) // 2,
                area.y() + (area.height() - h - frame_h) // 2)


def open_folder(path):
    """Show the folder `path` is (or is in) in Explorer - after a report is
    saved. Not while the demos run, or off-screen (the tests)."""
    if suppress_open_folder or QGuiApplication.platformName() == "offscreen":
        return
    folder = Path(path)
    if folder.is_file():
        folder = folder.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def ensure_taskbar_button(widget):
    """Give `widget` a taskbar button (Windows only).

    Windows gives no automatic taskbar button to a dialog whose owner is
    hidden (StrikeWorks, while MainWindow waits), nor to a frameless
    window (MainWindow with the custom title bar), so set WS_EX_APPWINDOW
    explicitly. Call before the widget is first shown: Windows decides on
    the button at first show, and changing the style later doesn't make it
    reconsider. winId() creates the native window without showing it."""
    if platform.system() != "Windows":
        return
    import ctypes
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    try:
        hwnd = int(widget.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass
