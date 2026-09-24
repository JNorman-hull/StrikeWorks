# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Dev mode - a pop-out console window that mirrors everything the app
prints (every page's status handler already does `print(f"[status] ...")`,
plus worker/subprocess chatter) so a manual walkthrough - like an
advanced-mode dummy run - has a live scrollback log to watch instead of
whatever terminal happened to launch the app, or nothing at all for a
built .exe.

Toggled from Adjustments ("Dev mode"); the toggle is persisted
(settings.get_dev_mode/set_dev_mode) so it comes back on at the next
launch. Installing/uninstalling only swaps sys.stdout/sys.stderr for a
tee that also still writes to the original stream - nothing else in the
app needs to know dev mode exists.
"""
import sys
from datetime import datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from .ml_widgets import MUTED, TEXT


class _StreamTee(QObject):
    """Wraps a real stream (stdout/stderr): writes still reach it
    unchanged, and each write also emits a signal - Qt auto-queues the
    connected slot onto the GUI thread when the write comes from a
    worker QThread, so this is safe to install while pages are running."""
    written = Signal(str)

    def __init__(self, real_stream):
        super().__init__()
        self.real = real_stream

    def write(self, text):
        self.real.write(text)
        if text.strip():
            self.written.emit(text)

    def flush(self):
        self.real.flush()

    def isatty(self):
        return False


class DevConsole(QDialog):
    """Non-modal pop-out log window. One instance, held by MainWindow
    (`self.dev_console`) and reused every time Dev mode toggles back on
    rather than rebuilt - but deliberately built with NO Qt parent
    (`super().__init__(None)`), not `DevConsole(window)`.

    A window-modal dialog (Adjustments - page_adjustments.py) blocks more
    than just its own direct parent on Windows in practice: anything else
    sharing that parent's window group gets blocked too, and a QDialog
    parented to MainWindow is exactly that - a sibling of Adjustments
    itself, not just of MainWindow. Confirmed directly: with a parent
    here, the console sat behind Adjustments and refused all input
    (including its own Close button) until Adjustments was closed first -
    exactly backwards from "stays interactive with Adjustments open",
    which is the entire reason Adjustments uses WindowModal instead of
    the exec()-default applicationModal in the first place (see its own
    docstring). No parent takes it out of that group entirely."""

    def __init__(self, window=None):
        super().__init__(window)
        self.setWindowTitle("Dev console")
        self.setMinimumSize(700, 400)
        self.setModal(False)
        self._out_tee = None
        self._err_tee = None
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        title = QLabel("Dev console")
        title.setStyleSheet(f"color:{TEXT};font-size:14px;font-weight:bold;")
        v.addWidget(title)
        subtitle = QLabel(
            "Live app output - every status message plus worker/"
            "prediction subprocess chatter, while Dev mode is on.")
        subtitle.setStyleSheet(f"color:{MUTED};font-size:11px;")
        subtitle.setWordWrap(True)
        v.addWidget(subtitle)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(QFont("Consolas", 9))
        v.addWidget(self.log, stretch=1)

        row = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.log.clear)
        row.addWidget(btn_clear)
        btn_save = QPushButton("Save log...")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.hide)
        row.addWidget(btn_close)
        v.addLayout(row)

    def _append(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        for line in text.rstrip("\n").split("\n"):
            if line:
                self.log.appendPlainText(f"[{ts}] {line}")

    def set_enabled(self, enabled: bool):
        """Install/uninstall the stdout+stderr tee and show/hide the
        window. Safe to call repeatedly with the same value."""
        if enabled and self._out_tee is None:
            self._out_tee = _StreamTee(sys.stdout)
            self._err_tee = _StreamTee(sys.stderr)
            self._out_tee.written.connect(self._append)
            self._err_tee.written.connect(self._append)
            sys.stdout = self._out_tee
            sys.stderr = self._err_tee
            self._append("Dev mode on - console attached.")
            self.show()
            self.raise_()
            self.activateWindow()
        elif not enabled and self._out_tee is not None:
            sys.stdout = self._out_tee.real
            sys.stderr = self._err_tee.real
            self._out_tee = None
            self._err_tee = None
            self.hide()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save dev console log", "strikeworks_dev_log.txt",
            "Text files (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log.toPlainText())
        except Exception as exc:
            self._append(f"Save failed: {exc}")
