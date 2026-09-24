# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Windows-taskbar quirks shared by every top-level window the app can
show as its *first* visible window - originally just MainWindow
(main.py), now also SimpleModeDialog (page_simple_mode.py) once it became
the default landing experience shown ahead of (and instead of) MainWindow.
A standalone module rather than a MainWindow method so both can import it
without main.py <-> page_simple_mode.py becoming circular (main.py already
imports SimpleModeDialog at module level).
"""
import platform


def ensure_taskbar_button(widget):
    """Windows-only. `Qt.FramelessWindowHint` (MainWindow, via
    ui_functions.py's uiDefinitions) makes Windows create that window as
    WS_POPUP rather than a normal WS_OVERLAPPED top-level window -
    confirmed via GetWindowLong on a real build: exStyle carried no
    WS_EX_APPWINDOW at all. Unlike a normal window, WS_POPUP does NOT get
    an automatic taskbar button, so the running app was simply missing
    from the taskbar entirely (not just showing the wrong icon).

    SimpleModeDialog itself isn't frameless, but it's a QDialog owned by
    MainWindow - since MainWindow now stays hidden until Simple mode is
    dismissed (main.py's __main__), there is no *visible* owner for
    Windows to group the dialog's taskbar entry under, and it was
    similarly missing a button of its own at launch. Same fix, same
    reason: force WS_EX_APPWINDOW explicitly rather than rely on Windows
    inferring one.

    Must run BEFORE the widget's first show(), not after: Windows decides
    whether to create a taskbar button when a window is first made
    visible, and toggling WS_EX_APPWINDOW afterwards (even paired with a
    hide()/show() cycle) does not reliably force it to reconsider -
    confirmed by testing exactly that ordering on MainWindow, which left
    it not just missing its button but transiently minimized (DWM
    re-evaluating a frameless/layered top-level window mid-flight is not
    something to provoke twice). Calling winId() forces the native handle
    to exist without showing anything, so the style bit is already
    correct by the time show()/exec() runs for the first time."""
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
