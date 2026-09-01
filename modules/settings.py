# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Small persisted application settings.

Holds the user-selectable libraries directory. Persisted as JSON in the user's
home so the choice survives restarts.

The settings file and key are deliberately identical to the MVP's
(``~/.hifistrike_settings.json`` / ``libraries_dir``) so StrikeWorks picks up
the libraries folder already configured there.
"""
import json
from pathlib import Path

_SETTINGS_FILE = Path.home() / ".hifistrike_settings.json"
_DEFAULT_LIBRARIES = Path(__file__).parent.parent / "libraries"
_DEFAULT_MODELS = Path(__file__).parent.parent / "models"
_DEFAULT_OUTPUT = Path(__file__).parent.parent / "output_data"


def _load() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text())
    except Exception:
        return {}


def _save(data: dict):
    try:
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def get_libraries_dir() -> Path:
    """Return the configured libraries directory, or the bundled default."""
    p = _load().get("libraries_dir")
    if p and Path(p).exists():
        return Path(p)
    return _DEFAULT_LIBRARIES


def set_libraries_dir(path) -> Path:
    """Persist a new libraries directory and return it as a Path."""
    p = Path(path)
    data = _load()
    data["libraries_dir"] = str(p)
    _save(data)
    return p


def get_models_dir() -> Path:
    """Default models folder (Model prediction/Evaluate discovery, and
    Deploy's own default before a session library exists) - the Adjustments
    dialog's own setting for it. Doesn't need to exist yet (unlike
    libraries_dir - a models folder is created on first deploy)."""
    p = _load().get("models_dir")
    return Path(p) if p else _DEFAULT_MODELS


def set_models_dir(path) -> Path:
    p = Path(path)
    data = _load()
    data["models_dir"] = str(p)
    _save(data)
    return p


def get_output_dir() -> Path:
    """Default output folder for reports/exports when no session library
    is selected (session_state.py's StrikeWorks_user_output/ takes over
    once one is) - the Adjustments dialog's own setting for it."""
    p = _load().get("output_dir")
    return Path(p) if p else _DEFAULT_OUTPUT


def set_output_dir(path) -> Path:
    p = Path(path)
    data = _load()
    data["output_dir"] = str(p)
    _save(data)
    return p


def get_last_library():
    """The session library from last time, or None (never set, or the
    folder no longer exists - a stale value is worse than starting
    blank on Home)."""
    p = _load().get("last_library")
    return Path(p) if p and Path(p).exists() else None


def set_last_library(path):
    """Persist the session library (`path=None` clears it - New Session
    starting fresh shouldn't silently reopen the old one on next launch)."""
    data = _load()
    if path is None:
        data.pop("last_library", None)
    else:
        data["last_library"] = str(Path(path))
    _save(data)


_MAX_RECENT = 8


def get_recent_training_datasets() -> list:
    """Recently used training dataset CSVs (existing files only)."""
    paths = _load().get("recent_training_datasets", [])
    return [p for p in paths if Path(p).exists()]


def add_recent_training_dataset(path):
    """Move/insert a dataset path at the top of the recent list."""
    p = str(Path(path))
    data = _load()
    recent = [r for r in data.get("recent_training_datasets", []) if r != p]
    recent.insert(0, p)
    data["recent_training_datasets"] = recent[:_MAX_RECENT]
    _save(data)
