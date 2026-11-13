"""The command that starts a worker (predict_worker.py / train_worker.py).

From source it is [python, <worker>.py, ...]. A frozen build has no
interpreter for a loose .py file, so the exe runs itself with
`--worker <name>`, which main.py handles before importing any Qt.
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
