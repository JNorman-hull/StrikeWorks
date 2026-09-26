# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Dev mode - a pop-out console window that mirrors everything the app
prints (every page's status handler already does `print(f"[status] ...")`,
plus the demo runners' `[demo] ...` lines and worker/subprocess chatter) so
a walkthrough has a live scrollback log to watch instead of whatever
terminal happened to launch the app - or nothing at all for a built .exe.

It also hosts the demos (dev_runner.py): pick Simple or Advanced, Run,
Stop. They live here rather than in Adjustments so the controls and the log
are one window that stays usable for the whole run - Adjustments can be
closed and the app watched while it is driven.

Toggled from Adjustments ("Dev mode"); the toggle is persisted
(settings.get_dev_mode/set_dev_mode). Installing/uninstalling only swaps
sys.stdout/sys.stderr for a tee that also still writes to the original
stream - nothing else in the app needs to know dev mode exists.

Two things that used to leave this window blank or unreachable:

  * A windowed build (StrikeWorks.spec, console=False) has no stdout/
    stderr at all - both are None. The tee used to call None.write, which
    made every print() in the app raise, so nothing ever reached the log.
    It now only forwards to a real stream when there is one.
  * Simple mode (shown at launch) used exec()'s default application
    modality, which input-blocked every other window - this one included.
    It is window-modal now (page_simple_mode.py); this window also has no
    Qt parent, so no window-modal dialog anywhere can block it.
"""
import sys
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .layout import Section
from .theme import ACCENT, ACCENT_BUTTON, BAD, MUTED, OK, TEXT


class _StreamTee(QObject):
    """Wraps a real stream (stdout/stderr) - which may be None in a
    windowed build: writes still reach it when it exists, and each write
    also emits a signal. Qt auto-queues the connected slot onto the GUI
    thread when the write comes from a worker QThread."""
    written = Signal(str)

    def __init__(self, real_stream):
        super().__init__()
        self.real = real_stream

    def write(self, text):
        if self.real is not None:
            try:
                self.real.write(text)
            except Exception:
                pass
        if text.strip():
            self.written.emit(text)
        return len(text)

    def flush(self):
        if self.real is not None:
            try:
                self.real.flush()
            except Exception:
                pass

    def isatty(self):
        return False


class DevConsole(QDialog):
    """Non-modal pop-out log window + demo controls. One instance, held by
    MainWindow (`self.dev_console`) - deliberately built with NO Qt parent:
    a window-modal dialog (Adjustments, Simple mode) blocks its parent's
    whole window group on Windows, and a parent here would put the console
    inside that group. `app_window` is kept only as a reference (for the
    demos), never as a parent."""

    def __init__(self, app_window=None):
        super().__init__(None)
        self._app_window = app_window
        self._runner = None
        self.setWindowTitle("Dev console")
        self.setMinimumSize(760, 460)
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
            "Live app output - every status message plus worker/prediction "
            "output, while Dev mode is on.")
        subtitle.setStyleSheet(f"color:{MUTED};font-size:11px;")
        subtitle.setWordWrap(True)
        v.addWidget(subtitle)

        grp_demo = Section("Demo")
        dv = QHBoxLayout(grp_demo)
        self.cmb_demo = QComboBox()
        self.cmb_demo.addItem("Simple mode (no training)", "simple")
        self.cmb_demo.addItem("Advanced (full workflow, trains a model)", "advanced")
        self.cmb_demo.setToolTip(
            "Simple drives Simple mode's own wizard exactly as clicking "
            "through it would. Advanced drives the full app's pages: blade "
            "strike estimate, study design, deployment, processing, "
            "validation + annotation, training, deployment, prediction, "
            "report. Both use the demo pack (demo_data) from the libraries "
            "folder and build a 'StrikeWorks_demo' library there.")
        dv.addWidget(self.cmb_demo, stretch=1)
        self.btn_run = QPushButton("Run demo")
        self.btn_run.setStyleSheet(ACCENT_BUTTON)
        self.btn_run.clicked.connect(self._run_demo)
        dv.addWidget(self.btn_run)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_demo)
        dv.addWidget(self.btn_stop)
        self.chk_on_top = QCheckBox("Keep on top")
        self.chk_on_top.setToolTip("Keep this window above the app while it "
                                   "is being driven.")
        self.chk_on_top.toggled.connect(self._set_on_top)
        dv.addWidget(self.chk_on_top)
        v.addWidget(grp_demo)
        self.lbl_demo = QLabel("")
        self.lbl_demo.setWordWrap(True)
        v.addWidget(self.lbl_demo)

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
            self.bring_up()
        elif not enabled and self._out_tee is not None:
            sys.stdout = self._out_tee.real
            sys.stderr = self._err_tee.real
            self._out_tee = None
            self._err_tee = None
            self.hide()

    def bring_up(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _set_on_top(self, on):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.show()   # changing window flags hides the window

    # ── demos (dev_runner.py) ────────────────────────────────────────────────
    def _run_demo(self):
        from . import settings
        from .dev_runner import DEMO_LIBRARY_NAME, RUNNERS, DemoSource
        if self._app_window is None or self._runner is not None:
            return
        mode = self.cmb_demo.currentData()
        source = DemoSource.find()
        if source is None:
            QMessageBox.warning(
                self, "No demo pack",
                "Put the 'demo_data' folder into the libraries folder:\n"
                f"{settings.get_libraries_dir()}")
            return
        detail = ("Simple mode's wizard, end to end - no training, "
                  "predicts with the deployed default model."
                  if mode == "simple" else
                  "The full app's pages, end to end - including training "
                  "and deploying a new model version (several minutes).")
        reply = QMessageBox.question(
            self, "Run demo",
            f"{detail}\n\nRecordings are copied from\n{source}\ninto a "
            f"'{DEMO_LIBRARY_NAME}' library in\n{settings.get_libraries_dir()}"
            "\n(created, or reused if it exists). Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.set_enabled(True)
        self.chk_on_top.setChecked(True)
        self._runner = RUNNERS[mode](self._app_window)
        self._runner.finished.connect(self._on_demo_finished)
        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running…")
        self.btn_stop.setEnabled(True)
        self.cmb_demo.setEnabled(False)
        self.lbl_demo.setStyleSheet(f"color:{ACCENT};")
        self.lbl_demo.setText("Demo running - Stop cancels at the next step.")
        self._runner.run()

    def _stop_demo(self):
        if self._runner is not None:
            self.btn_stop.setEnabled(False)
            self._runner.request_stop()

    def _on_demo_finished(self, ok, message):
        self._runner = None
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Run demo")
        self.btn_stop.setEnabled(False)
        self.cmb_demo.setEnabled(True)
        self.chk_on_top.setChecked(False)
        self.lbl_demo.setStyleSheet(f"color:{OK if ok else BAD};")
        self.lbl_demo.setText(message)
        self.bring_up()

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
