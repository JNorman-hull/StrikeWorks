# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The app's persisted settings, in one JSON file:

  - the packaged app: `settings.json` beside StrikeWorks.exe, so the
    folder is self-contained - it starts on its own libraries, models,
    input and output folders, and can be copied or handed over as it is;
  - from source: `%APPDATA%\\StrikeWorks\\settings.json`;
  - either way, the `STRIKEWORKS_SETTINGS` environment variable, when set,
    names the file instead (the tests and the smoke test use it).

Top-level keys are the app settings below (folders, default models, the
last library, dev mode, recent datasets). Other modules keep their own
data in a named section (`read_section` / `write_section`): the sensor
configurations and the annotation variables.

From source, the first start reads the three files earlier versions kept
in the home folder (`.hifistrike_settings.json`,
`.strikeworks_sensors.json`, `.strikeworks_annotations.json`) once; those
files are left where they are.
"""
import json
import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Where the default data folders (libraries, models, output_data,
    input_data) live: next to the exe once packaged, the repo root from
    source."""
    if _frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def settings_path() -> Path:
    override = os.environ.get("STRIKEWORKS_SETTINGS")
    if override:
        return Path(override)
    if _frozen():
        return app_root() / "settings.json"
    base = os.environ.get("APPDATA")
    return ((Path(base) if base else Path.home() / ".config")
            / "StrikeWorks" / "settings.json")


SETTINGS_FILE = settings_path()

# section name (None: the app settings themselves) -> the older file; a
# packaged app starts from its own folders instead
_LEGACY_FILES = {} if _frozen() else {
    None: Path.home() / ".hifistrike_settings.json",
    "sensor_configs": Path.home() / ".strikeworks_sensors.json",
    "annotation_variables": Path.home() / ".strikeworks_annotations.json",
}

_DEFAULT_LIBRARIES = app_root() / "libraries"
_DEFAULT_MODELS = app_root() / "models"
_DEFAULT_OUTPUT = app_root() / "output_data"
_DEFAULT_INPUT_DATA = app_root() / "input_data"


def _read_json(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"Could not read settings file {path}: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _migrate() -> dict:
    """The settings from the older home-folder files (empty if none)."""
    data = {}
    for section, path in _LEGACY_FILES.items():
        old = _read_json(path)
        if not old:
            continue
        if section is None:
            data.update(old)
        else:
            data[section] = old
    return data


def _load() -> dict:
    if SETTINGS_FILE.exists():
        return _read_json(SETTINGS_FILE)
    data = _migrate()
    if data:
        _save(data)
    return data


def _save(data: dict):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"Could not save settings to {SETTINGS_FILE}: {e}")


def _set(key, value):
    """Store `value` under `key` (`None` removes the key)."""
    data = _load()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    _save(data)


def read_section(name) -> dict:
    """A module's own section of the settings file ({} if unset)."""
    section = _load().get(name)
    return section if isinstance(section, dict) else {}


def write_section(name, payload: dict):
    _set(name, payload)


# ── folders ──────────────────────────────────────────────────────────────────
# A configured folder is used even when it can't be reached right now (a
# OneDrive folder not yet mounted), rather than silently switching to the
# default.

def get_libraries_dir() -> Path:
    p = _load().get("libraries_dir")
    return Path(p) if p else _DEFAULT_LIBRARIES


def set_libraries_dir(path) -> Path:
    p = Path(path)
    _set("libraries_dir", str(p))
    return p


#: the demo pack (dev_runner.py) sits in the libraries folder as a source of
#: raw files, so it's never listed as a library
DEMO_DATA_NAME = "demo_data"


def list_libraries() -> list:
    """Every library folder in the libraries folder, sorted by name."""
    try:
        return sorted(p for p in get_libraries_dir().iterdir()
                      if p.is_dir() and p.name.lower() != DEMO_DATA_NAME)
    except OSError:
        return []


def get_models_dir() -> Path:
    """Where Model prediction, Evaluate and Deploy look for models (created
    on first deploy)."""
    p = _load().get("models_dir")
    return Path(p) if p else _DEFAULT_MODELS


def set_models_dir(path) -> Path:
    p = Path(path)
    _set("models_dir", str(p))
    return p


def get_output_dir() -> Path:
    """Reports and exports when no session library is selected (otherwise
    the library's StrikeWorks_user_output/)."""
    p = _load().get("output_dir")
    return Path(p) if p else _DEFAULT_OUTPUT


def set_output_dir(path) -> Path:
    p = Path(path)
    _set("output_dir", str(p))
    return p


def get_input_data_dir() -> Path:
    """Where exported model-ready datasets are written."""
    p = _load().get("input_data_dir")
    return Path(p) if p else _DEFAULT_INPUT_DATA


def set_input_data_dir(path) -> Path:
    p = Path(path)
    _set("input_data_dir", str(p))
    return p


# ── Simple mode's default models ─────────────────────────────────────────────
# Unset (None) means 'binary1' / 'multiclass1'. Not checked for existence:
# the model may be in a library that isn't reachable right now.

def get_default_model():
    p = _load().get("default_model")
    return Path(p) if p else None


def set_default_model(path):
    _set("default_model", None if path is None else str(Path(path)))


def get_default_mc_model():
    p = _load().get("default_mc_model")
    return Path(p) if p else None


def set_default_mc_model(path):
    _set("default_mc_model", None if path is None else str(Path(path)))


# ── session ──────────────────────────────────────────────────────────────────
def get_last_library():
    """Last session's library, or None if unset or gone."""
    p = _load().get("last_library")
    return Path(p) if p and Path(p).exists() else None


def set_last_library(path):
    """`None` (New session) clears it."""
    _set("last_library", None if path is None else str(Path(path)))


def get_dev_mode() -> bool:
    return bool(_load().get("dev_mode", False))


def set_dev_mode(enabled: bool):
    _set("dev_mode", bool(enabled))


_MAX_RECENT = 8


def get_recent_training_datasets() -> list:
    """Recently used training datasets (absolute paths of existing files)."""
    return [p for p in _load().get("recent_training_datasets", [])
            if Path(p).is_absolute() and Path(p).exists()]


def add_recent_training_dataset(path):
    """Put `path` at the top of the recent list."""
    p = str(Path(path).resolve())
    recent = [r for r in get_recent_training_datasets() if r != p]
    _set("recent_training_datasets", [p] + recent[:_MAX_RECENT - 1])
