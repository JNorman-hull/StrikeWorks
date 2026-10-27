# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The console: everything the app prints - the pages' `[status]` lines,
the demos' `[demo]` lines, worker output, warnings and errors - from the
moment it starts, and the demos (dev_runner.py). Opened from Settings >
Console.

`install_capture()` (main.py, first thing) swaps sys.stdout/sys.stderr for
tees that still write to the original stream when there is one (a windowed
build has none - both are None), keep the last lines in memory for the
console window, and append every line to this session's log file
(`logs/strikeworks_<date>_<time>.log` beside the settings file; the last
`_KEEP_LOGS` are kept). Unhandled errors - in a slot, a thread or start-up
- are printed there with their traceback, Qt's own warnings too, and a
hard crash (Python's faulthandler) writes its traceback into the same
file, so the log of a session that crashed is already on disk.

The window has no Qt parent, so no window-modal dialog blocks it.
"""
import faulthandler
import io
import sys
import threading
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QtMsgType, Signal, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .layout import Section
from .theme import style

_KEEP_LINES = 5000      # in memory, for the console window
_KEEP_LOGS = 20         # session log files kept in logs/


class _Capture(QObject):
    """The session's output: the last lines (`lines`), the log file, and
    `line` for the console window. Qt queues `line` onto the GUI thread
    when the write comes from a worker QThread."""
    line = Signal(str)

    def __init__(self, log_path):
        super().__init__()
        self.lines = deque(maxlen=_KEEP_LINES)
        self.log_path = log_path
        self._lock = threading.Lock()
        self._file = None
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(log_path, "a", encoding="utf-8", buffering=1)
        except OSError:
            self.log_path = None       # an unwritable folder: memory only

    @property
    def file(self):
        return self._file

    def add(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        out = []
        for line in text.rstrip("\n").split("\n"):
            if line.strip():
                out.append(f"[{ts}] {line}")
        if not out:
            return
        with self._lock:
            self.lines.extend(out)
            if self._file is not None:
                try:
                    self._file.write("\n".join(out) + "\n")
                except (OSError, ValueError):
                    pass
        for line in out:
            self.line.emit(line)


class _StreamTee:
    """Stands in for stdout/stderr: writes still reach the real stream
    when there is one, and each complete line goes to the capture."""

    def __init__(self, real_stream, capture):
        self.real = real_stream
        self._capture = capture
        self._partial = ""
        self._lock = threading.Lock()   # threads print too

    def write(self, text):
        if self.real is not None:
            try:
                self.real.write(text)
            except (OSError, ValueError):
                pass    # a closed stream; reporting it would loop back here
        with self._lock:
            self._partial += text
            done = None
            if "\n" in self._partial:
                done, self._partial = self._partial.rsplit("\n", 1)
        if done is not None:
            self._capture.add(done)
        return len(text)

    def flush(self):
        with self._lock:
            rest, self._partial = self._partial, ""
        if rest:
            self._capture.add(rest)
        if self.real is not None:
            try:
                self.real.flush()
            except (OSError, ValueError):
                pass

    def isatty(self):
        return False

    def fileno(self):
        # the real stream's, where there is one (a run from PyCharm)
        if self.real is None:
            raise io.UnsupportedOperation("no file behind this stream")
        return self.real.fileno()


_capture = None


def capture():
    """This session's capture, or None before `install_capture()` (the
    tests, which leave stdout alone)."""
    return _capture


def install_capture(log_dir):
    """Capture the app's output from here on - see the module docstring.
    Safe to call twice."""
    global _capture
    if _capture is not None:
        return _capture
    log_dir = Path(log_dir)
    _prune_logs(log_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _capture = _Capture(log_dir / f"strikeworks_{stamp}.log")
    sys.stdout = _StreamTee(sys.stdout, _capture)
    sys.stderr = _StreamTee(sys.stderr, _capture)
    if _capture.file is not None:
        # a hard crash (access violation, abort) writes its traceback here
        faulthandler.enable(file=_capture.file, all_threads=True)
    sys.excepthook = _excepthook
    threading.excepthook = lambda args: _excepthook(
        args.exc_type, args.exc_value, args.exc_traceback,
        where=f"thread {args.thread.name if args.thread else '?'}")
    qInstallMessageHandler(_qt_message)
    print(f"StrikeWorks started - this session's log: "
          f"{_capture.log_path or 'not saved (logs folder not writable)'}")
    return _capture


def _excepthook(exc_type, exc, tb, where=None):
    """Unhandled errors: printed with their traceback (so to the console
    and the log file) rather than lost - a windowed build has no stderr."""
    lines = "".join(traceback.format_exception(exc_type, exc, tb))
    print(f"ERROR - unhandled{f' in {where}' if where else ''}:\n{lines}",
          file=sys.stderr)
    try:
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


_QT_LEVELS = {QtMsgType.QtWarningMsg: "warning",
              QtMsgType.QtCriticalMsg: "critical",
              QtMsgType.QtFatalMsg: "fatal"}


def _qt_message(mode, _context, message):
    level = _QT_LEVELS.get(mode)
    if level is not None:        # debug/info messages are left out
        print(f"[Qt {level}] {message}", file=sys.stderr)


def _prune_logs(log_dir):
    """Keep the newest `_KEEP_LOGS - 1` session logs (this one makes the
    last)."""
    try:
        logs = sorted(log_dir.glob("strikeworks_*.log"))
    except OSError:
        return
    for old in logs[:max(0, len(logs) - (_KEEP_LOGS - 1))]:
        try:
            old.unlink()
        except OSError:
            pass


class DevConsole(QDialog):
    """The console window and demo controls; one instance, `MainWindow.
    dev_console`. It has no Qt parent: a window-modal dialog (Settings,
    the StrikeWorks window) blocks its parent's whole window group on
    Windows. `app_window` is only a reference, for the demos."""

    def __init__(self, app_window=None):
        super().__init__(None)
        self._app_window = app_window
        self._runner = None
        self.setWindowTitle("Console")
        self.setMinimumSize(760, 460)
        self.setModal(False)
        self._build()
        cap = capture()
        if cap is not None:
            for line in cap.lines:
                self.log.appendPlainText(line)
            cap.line.connect(self.log.appendPlainText)

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        title = QLabel("Console")
        style(title, role="heading")
        v.addWidget(title)

        grp_demo = Section("Demo")
        dv = QHBoxLayout(grp_demo)
        from .dev_runner import available_demos
        labels = {"simple": "StrikeWorks (no training)",
                  "advanced": "Development toolkit (full workflow, trains a "
                              "model)"}
        self.cmb_demo = QComboBox()
        for mode in available_demos():
            self.cmb_demo.addItem(labels[mode], mode)
        self.cmb_demo.setToolTip(
            "StrikeWorks drives the StrikeWorks window's own steps exactly "
            "as clicking through them would. Development toolkit drives the "
            "full app's pages: blade strike estimate, study design, "
            "deployment, processing, validation + annotation, training, "
            "deployment, prediction, report. Both use the demo pack "
            "(demo_data) from the libraries folder and build a "
            "'StrikeWorks_demo' library there.")
        dv.addWidget(self.cmb_demo, stretch=1)
        self.btn_run = QPushButton("Run demo")
        style(self.btn_run, role="primary")
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
        self.log.setMaximumBlockCount(_KEEP_LINES)
        self.log.setFont(QFont("Consolas", 9))
        v.addWidget(self.log, stretch=1)

        cap = capture()
        if cap is not None and cap.log_path is not None:
            lbl_file = QLabel(f"Saved as it goes to {cap.log_path}")
            style(lbl_file, role="muted")
            lbl_file.setWordWrap(True)
            lbl_file.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            v.addWidget(lbl_file)

        row = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.setToolTip("Clear this window (the log file keeps "
                             "everything).")
        btn_clear.clicked.connect(self.log.clear)
        row.addWidget(btn_clear)
        btn_save = QPushButton("Save log...")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        if cap is not None and cap.log_path is not None:
            btn_folder = QPushButton("Open logs folder")
            btn_folder.clicked.connect(self._open_logs_folder)
            row.addWidget(btn_folder)
        row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.hide)
        row.addWidget(btn_close)
        v.addLayout(row)

    def bring_up(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _set_on_top(self, on):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.show()   # changing window flags hides the window

    def _open_logs_folder(self):
        from . import win_utils
        cap = capture()
        if cap is not None and cap.log_path is not None:
            win_utils.open_folder(cap.log_path.parent)

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
        detail = ("The StrikeWorks window's steps, end to end - no "
                  "training, predicts with the deployed default model."
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

        self.bring_up()
        self.chk_on_top.setChecked(True)
        self._runner = RUNNERS[mode](self._app_window)
        self._runner.finished.connect(self._on_demo_finished)
        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running…")
        self.btn_stop.setEnabled(True)
        self.cmb_demo.setEnabled(False)
        style(self.lbl_demo, tone="accent")
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
        style(self.lbl_demo, tone="ok" if ok else "bad")
        self.lbl_demo.setText(message)
        self.bring_up()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save console log", "strikeworks_log.txt",
            "Text files (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log.toPlainText())
        except Exception as exc:
            print(f"Save failed: {exc}")
