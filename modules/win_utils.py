# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Windows taskbar fix for the app's first visible window (MainWindow or
Simple mode). Its own module so main.py and page_simple_mode.py can both
use it without importing each other.
"""
import platform


def ensure_taskbar_button(widget):
    """Give `widget` a taskbar button (Windows only).

    Windows gives no automatic taskbar button to a frameless window
    (MainWindow is created as WS_POPUP) or to a dialog whose owner is
    hidden (Simple mode, while MainWindow waits), so set WS_EX_APPWINDOW
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
