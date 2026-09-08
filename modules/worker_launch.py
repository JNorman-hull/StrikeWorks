# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Builds the subprocess argv prefix for launching a worker
(predict_worker.py / train_worker.py) - the one thing that differs
between running from source and running as a packaged (PyInstaller)
executable.

From source, `sys.executable` is a real Python interpreter, so the
worker is just "run this script file":
    [sys.executable, ".../predict_worker.py", "--bin-model", ...]

Frozen, there is no bundled interpreter to hand a loose .py file to, and
no separate worker executable is built - `sys.executable` IS the
packaged app's own .exe. Instead the frozen exe re-invokes *itself* with
a "--worker <name>" flag in front of the worker's own arguments:
    [sys.executable, "--worker", "predict", "--bin-model", ...]

main.py's own entry point checks for that flag before doing anything
Qt/GUI-related and dispatches straight to the matching worker's main()
instead of starting the app - see the top of main.py.
"""
import sys
from pathlib import Path

_WORKER_SCRIPTS = {
    "predict": Path(__file__).parent / "predict_worker.py",
    "train": Path(__file__).parent / "train_worker.py",
}


def worker_command(name):
    """The subprocess argv *prefix* for worker `name` - the caller
    appends that worker's own CLI flags after this."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", name]
    script = _WORKER_SCRIPTS.get(name)
    if script is None:
        raise ValueError(f"Unknown worker: {name}")
    if not script.exists():
        raise FileNotFoundError(f"Worker script not found: {script}")
    return [sys.executable, str(script)]
