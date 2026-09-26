"""Shared set-up for the tests: a throwaway settings folder, an offscreen
QApplication, and the main window built the way main.py builds it.

Nothing a test does touches the real settings files, libraries or the
repo's own output folders - every path the app writes to at run time is
pointed into a temporary folder first.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TESTBED = ROOT / "libraries" / "Testbed"
BSM_CONFIG = ROOT / "input_data" / "BSM_config" / "pumpflow_configuration.txt"


def temp_dir(prefix="strikeworks_test_"):
    return Path(tempfile.mkdtemp(prefix=prefix))


def isolate(env_dir=None):
    """Point every settings file and run-time output folder into `env_dir`
    (a new temp folder by default). Returns the folder."""
    env = Path(env_dir) if env_dir else temp_dir()
    for sub in ("libraries", "input_data", "output", "training_runs", "bsm"):
        (env / sub).mkdir(parents=True, exist_ok=True)
    settings_file = env / "settings.json"
    if not settings_file.exists():
        settings_file.write_text(json.dumps({
            "libraries_dir": str(env / "libraries"),
            "input_data_dir": str(env / "input_data"),
            "output_dir": str(env / "output"),
        }))

    from modules import (bsm_state, ml_train_state, page_bsm_calculator,
                         setup_precision, settings)
    settings.SETTINGS_FILE = settings_file
    settings._LEGACY_FILES = {}
    latest = env / "bsm" / "latest_result.json"
    bsm_state.LATEST_RESULT_PATH = latest
    page_bsm_calculator.LATEST_RESULT_PATH = latest
    setup_precision.LATEST_RESULT_PATH = latest
    ml_train_state._RUNS_DIR = env / "training_runs"
    return env


_app = None


def qt_app():
    global _app
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)
    return _app


def main_window():
    """(the `main` module, a new main window), built as main.py builds it."""
    qt_app()
    import main
    return main, main.MainWindow()


def pump(ms=200):
    """Let queued Qt events run for `ms` milliseconds."""
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
