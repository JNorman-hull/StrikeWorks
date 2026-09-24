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
import sys
from pathlib import Path


def app_root() -> Path:
    """Where the four default data folders (libraries/models/output_data/
    input_data) live. Packaged (PyInstaller), that's next to the .exe
    itself - `Path(__file__).parent.parent` would instead resolve inside
    the bundled _internal folder, since modules/settings.py's own file
    lives there once frozen, not at the real app root a user would look
    in. From source it's the repo root, same as before."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


_SETTINGS_FILE = Path.home() / ".hifistrike_settings.json"
_DEFAULT_LIBRARIES = app_root() / "libraries"
_DEFAULT_MODELS = app_root() / "models"
_DEFAULT_OUTPUT = app_root() / "output_data"
_DEFAULT_INPUT_DATA = app_root() / "input_data"


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
    """Return the configured libraries directory, or the bundled default.

    Deliberately does NOT check Path(p).exists() - unlike the other three
    folder getters below, this one used to, which meant a configured
    folder that happened to be momentarily unreachable (a cloud-synced
    folder - e.g. OneDrive - not yet mounted/settled at the moment the
    app read it) silently fell back to the bundled default instead of the
    real one, indistinguishable from "the setting wasn't retained" from
    the user's point of view even though it was still sitting correctly
    in the settings file the whole time. Trust what was set, same as
    models/output/input-data below."""
    p = _load().get("libraries_dir")
    return Path(p) if p else _DEFAULT_LIBRARIES


def set_libraries_dir(path) -> Path:
    """Persist a new libraries directory and return it as a Path."""
    p = Path(path)
    data = _load()
    data["libraries_dir"] = str(p)
    _save(data)
    return p


def list_libraries() -> list:
    """Every library folder under the configured libraries directory,
    sorted by name - the one scan every library combo (Home, Simple
    mode's Deploy page) populates itself from."""
    try:
        return sorted(p for p in get_libraries_dir().iterdir() if p.is_dir())
    except Exception:
        return []


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


def get_input_data_dir() -> Path:
    """Default folder for exported model-ready datasets - Simple mode's
    Save and export, the dev demo runner's own dataset write - the
    Adjustments dialog's own setting for it. Unrelated to bsm_config.py's
    CONFIG_DIR (the bundled BSM_config presets shipped with the app
    itself, always at app_root() regardless of this setting)."""
    p = _load().get("input_data_dir")
    return Path(p) if p else _DEFAULT_INPUT_DATA


def set_input_data_dir(path) -> Path:
    p = Path(path)
    data = _load()
    data["input_data_dir"] = str(p)
    _save(data)
    return p


def get_default_model():
    """The pinned "default binary model" (Adjustments) - Simple mode's
    Predict step uses this instead of the 'binary1' convention when the
    user has set one; unset (None) is the normal state, not an error.
    Doesn't check existence - a model path can point into a library that
    isn't the current session library, so a transient "not found right
    now" isn't the same as "never configure this"."""
    p = _load().get("default_model")
    return Path(p) if p else None


def set_default_model(path):
    """`path=None` clears the pin - back to the 'binary1' convention."""
    data = _load()
    if path is None:
        data.pop("default_model", None)
    else:
        data["default_model"] = str(Path(path))
    _save(data)


def get_default_mc_model():
    """The pinned "default multiclass model" (Adjustments) - same rule as
    `get_default_model`, just for the region/multiclass stage."""
    p = _load().get("default_mc_model")
    return Path(p) if p else None


def set_default_mc_model(path):
    """`path=None` clears the pin - back to the 'multiclass1' convention."""
    data = _load()
    if path is None:
        data.pop("default_mc_model", None)
    else:
        data["default_mc_model"] = str(Path(path))
    _save(data)


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


def get_dev_mode() -> bool:
    """Whether the Dev console (Adjustments) should be attached at
    startup - persisted so it comes back on for the next launch too."""
    return bool(_load().get("dev_mode", False))


def set_dev_mode(enabled: bool):
    data = _load()
    data["dev_mode"] = bool(enabled)
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
