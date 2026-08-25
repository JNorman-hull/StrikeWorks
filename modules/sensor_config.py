# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Sensor configurations - one source of truth for how a device's raw files
are named, paired, parsed and sampled.

Everything the rest of the app used to hardcode for the RAPID sensor lives
here as data: the sampling rate, how many files make one recording and with
which extensions, the raw packet sizes, the filename pattern, the channel
list and the analysis window. Pages read the *active* configuration rather
than module constants, so selecting a different sensor on the Prepare page
changes raw import, validation and dataset creation together.

Adding a sensor
---------------
Two ways, neither of which needs a code change to the pages:

1. In the app: Prepare > Sensor configuration > New / Duplicate, then Save.
   User configurations are written to the JSON file returned by
   ``config_path()`` and are read back on the next start.

2. In this file: add a dict to ``BUILTIN``. Built-in configurations always
   exist, can be edited (the edit is saved as an override) and can be put
   back with ``reset_to_builtin()``.

Adding a parser
---------------
A configuration names its parser by key. ``PARSERS`` maps that key to a
callable with the signature

    parser(paths, out_dir, config) -> (DataFrame, summary_dict)

where ``paths`` maps a lowercase file extension to the raw file for one
recording (``{".imp": Path(...), ".hig": Path(...)}`` for RAPID), ``out_dir``
is the library's ``processed_sens_data`` folder and ``config`` is the
SensorConfig in force. This is the single code point a new device needs:
write the reader, register it here, and point a configuration at it.
"""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

# Channels the RAPID parser produces and the models consume. Kept here so a
# configuration can carry its own list; ml_train_state.DEFAULT_CHANNELS is
# the training-side default and matches this one.
RAPID_CHANNELS = [
    "higacc_x_g", "higacc_y_g", "higacc_z_g",
    "inacc_x_ms", "inacc_y_ms", "inacc_z_ms",
    "rot_x_degs", "rot_y_degs", "rot_z_degs",
    "pressure_kpa",
]

# filename pattern: SENSOR-MMDDHHMMSS  e.g. B61-0703140718
RAPID_FNAME_PATTERN = r"^([A-Za-z0-9]{2,4})-(\d{4})(\d{6})$"

# How far either side of the acceleration peak the parser looks for the
# pressure nadir. 1.5 s each way - the RAPID code's ±3000 samples at 2000 Hz.
NADIR_SEARCH_SEC = 1.5

RESAMPLE_METHODS = [
    ("Linear", "linear"),
    ("Cubic spline", "cubic"),
    ("Nearest sample", "nearest"),
    ("Hold previous", "previous"),
]

_SETTINGS_FILE = Path.home() / ".strikeworks_sensors.json"


# ── the configuration record ─────────────────────────────────────────────────
@dataclass
class SensorConfig:
    """Everything about a sensor that raw import and processing depend on."""

    key: str
    name: str
    description: str = ""

    # acquisition
    sampling_rate_hz: float = 2000.0
    files_per_recording: int = 2
    file_extensions: list = field(default_factory=lambda: [".imp", ".hig"])
    packet_sizes: dict = field(default_factory=dict)   # extension -> bytes
    filename_pattern: str = RAPID_FNAME_PATTERN

    # signals and analysis
    channels: list = field(default_factory=lambda: list(RAPID_CHANNELS))
    window_sec: float = 0.2

    # interpolation: resample a lower-rate device up to a target rate so the
    # model input length is comparable across sensors
    resample: bool = False
    target_rate_hz: float = 0.0        # 0 = no target set
    resample_method: str = "linear"

    # the code point for the device's reader (see PARSERS)
    parser: str = "rapid_imp_hig"

    # ── derived values ──────────────────────────────────────────────────────
    @property
    def output_rate_hz(self) -> float:
        """Rate of the processed CSV: the target rate when resampling."""
        if self.resample and self.target_rate_hz > 0:
            return float(self.target_rate_hz)
        return float(self.sampling_rate_hz)

    @property
    def primary_extension(self) -> str:
        """The extension that defines a recording; others pair to it."""
        return self.file_extensions[0] if self.file_extensions else ""

    @property
    def required_extensions(self) -> list:
        """Extensions that must all be present for a complete recording."""
        n = max(1, int(self.files_per_recording))
        return list(self.file_extensions[:n])

    @property
    def window_samples(self) -> int:
        """Rows in one analysis window - the model's input length."""
        return int(round(self.window_sec * self.output_rate_hz))

    @property
    def half_window_samples(self) -> int:
        return int(round(self.window_sec / 2 * self.output_rate_hz))

    @property
    def window_suffix(self) -> str:
        """Filename suffix for saved windows, e.g. '_200ms'."""
        return f"_{int(round(self.window_sec * 1000))}ms"

    @property
    def nadir_search_samples(self) -> int:
        return int(round(NADIR_SEARCH_SEC * self.output_rate_hz))

    def packet_size(self, ext: str, default: int = 0) -> int:
        return int(self.packet_sizes.get(ext.lower(), default))

    def compiled_pattern(self):
        """The filename pattern, or None when it does not compile."""
        try:
            return re.compile(self.filename_pattern, re.IGNORECASE)
        except re.error:
            return None

    def parse_stem(self, stem: str):
        """Split a filename stem into (sensor, DD/MM, HH:MM:SS).

        Falls back to (stem, "", "") when the name does not match, which is
        what the inventory table shows for an unrecognised file.
        """
        rx = self.compiled_pattern()
        m = rx.match(stem) if rx else None
        if not m:
            return stem, "", ""
        groups = m.groups()
        sensor = groups[0].upper() if groups else stem
        date = time = ""
        if len(groups) >= 2 and groups[1] and len(groups[1]) >= 4:
            date = f"{groups[1][2:4]}/{groups[1][:2]}"          # DD/MM
        if len(groups) >= 3 and groups[2] and len(groups[2]) >= 6:
            t = groups[2]
            time = f"{t[:2]}:{t[2:4]}:{t[4:6]}"
        return sensor, date, time

    # ── serialisation ───────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SensorConfig":
        fields = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in fields}
        clean.setdefault("key", "sensor")
        clean.setdefault("name", clean["key"])
        cfg = cls(**clean)
        cfg.file_extensions = [str(e).lower() for e in cfg.file_extensions]
        cfg.packet_sizes = {str(k).lower(): int(v)
                            for k, v in dict(cfg.packet_sizes).items()}
        return cfg

    def copy(self, **changes) -> "SensorConfig":
        """A detached copy - asdict() deep-copies the lists and dicts."""
        data = self.to_dict()
        data.update(changes)
        return SensorConfig.from_dict(data)

    # ── validation ──────────────────────────────────────────────────────────
    def problems(self) -> list:
        """Human-readable reasons this configuration cannot be used."""
        out = []
        if not self.key.strip():
            out.append("The configuration needs a key.")
        if self.sampling_rate_hz <= 0:
            out.append("Sampling rate must be greater than zero.")
        if self.files_per_recording < 1:
            out.append("A recording needs at least one file.")
        if len(self.file_extensions) < self.files_per_recording:
            out.append(
                f"{self.files_per_recording} file(s) per recording but only "
                f"{len(self.file_extensions)} extension(s) listed.")
        if any(not e.startswith(".") for e in self.file_extensions):
            out.append("File extensions must start with a dot.")
        if self.compiled_pattern() is None:
            out.append("The filename pattern is not a valid expression.")
        if self.window_sec <= 0:
            out.append("The analysis window must be longer than zero.")
        if self.resample and self.target_rate_hz <= 0:
            out.append("Resampling is on but no target rate is set.")
        if self.parser not in PARSERS:
            out.append(f"No parser registered under '{self.parser}'.")
        return out


# ── shipped configurations ───────────────────────────────────────────────────
# Add a dict here to ship a third sensor. Nothing else in the app needs to
# change, other than registering its parser in PARSERS below.
BUILTIN = {
    "rapid": dict(
        key="rapid",
        name="RAPID",
        description=(
            "The current setup: paired .imp (IMU, pressure, temperature, "
            "battery) and .hig (high-g accelerometer) files at 2000 Hz, "
            "merged onto one uniform time base by the RAPID parser."),
        sampling_rate_hz=2000.0,
        files_per_recording=2,
        file_extensions=[".imp", ".hig"],
        packet_sizes={".imp": 29, ".hig": 11},
        filename_pattern=RAPID_FNAME_PATTERN,
        channels=list(RAPID_CHANNELS),
        window_sec=0.2,
        resample=False,
        target_rate_hz=0.0,
        resample_method="linear",
        parser="rapid_imp_hig",
    ),
    "micro_eel": dict(
        key="micro_eel",
        name="Micro-EEL",
        description=(
            "Anticipated device, not yet in service. One file per recording "
            "at roughly 6000 Hz. Extension, packet size and parser are "
            "placeholders until a real recording is available - set the "
            "parser once its reader is registered in sensor_config.PARSERS."),
        sampling_rate_hz=6000.0,
        files_per_recording=1,
        file_extensions=[".dat"],
        packet_sizes={".dat": 0},
        filename_pattern=RAPID_FNAME_PATTERN,
        channels=list(RAPID_CHANNELS),
        window_sec=0.2,
        resample=False,
        target_rate_hz=6000.0,
        resample_method="linear",
        parser="unconfigured",
    ),
}

DEFAULT_KEY = "rapid"


# ── parsers ──────────────────────────────────────────────────────────────────
_rapid_module = None


def _load_rapid_module():
    """Load rapid_functions from the modules folder.

    Loaded by path rather than imported so the processing thread picks up an
    edited parser without restarting the app - the behaviour the Process page
    has always had.
    """
    global _rapid_module
    if _rapid_module is None:
        import importlib.util
        target = Path(__file__).parent / "rapid_functions.py"
        spec = importlib.util.spec_from_file_location("rapid_functions", target)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _rapid_module = mod
    return _rapid_module


def _parse_rapid(paths, out_dir, config):
    """RAPID: one .imp and one .hig, merged onto a uniform time base."""
    rf = _load_rapid_module()
    return rf.process_imp_hig_direct(
        paths[".imp"], paths[".hig"], out_dir, config=config)


def _parse_unconfigured(paths, out_dir, config):
    raise NotImplementedError(
        f"'{config.name}' has no parser yet. Write its reader, register it "
        "in modules/sensor_config.py under PARSERS, and select it on the "
        "Prepare page.")


#: parser key -> callable(paths, out_dir, config) -> (DataFrame, summary)
PARSERS = {
    "rapid_imp_hig": _parse_rapid,
    "unconfigured": _parse_unconfigured,
}


def register_parser(key, fn):
    """Register a device reader under `key` (see the module docstring)."""
    PARSERS[key] = fn


def get_parser(key):
    return PARSERS.get(key, _parse_unconfigured)


# ── resampling ───────────────────────────────────────────────────────────────
_INTERP_KIND = {"linear": "linear", "cubic": "cubic",
                "nearest": "nearest", "previous": "previous"}


def resample_frame(df, out_rate, time_col="time_s", method="linear"):
    """Put `df` on a uniform grid at `out_rate` Hz.

    Used to lift a lower-rate device (say 100 Hz) up to the rate the models
    were trained at, since the model input length is a sample count. Returns
    a new frame; the original is untouched.
    """
    import numpy as np
    import pandas as pd
    from scipy.interpolate import interp1d

    if out_rate <= 0 or time_col not in df.columns or len(df) < 2:
        return df

    t = df[time_col].to_numpy(dtype=float)
    step = 1.0 / float(out_rate)
    grid = np.arange(t.min(), t.max() + step, step)

    out = pd.DataFrame({time_col: grid})
    kind = _INTERP_KIND.get(method, "linear")
    for col in df.columns:
        if col == time_col:
            continue
        try:
            f = interp1d(t, df[col].to_numpy(dtype=float), kind=kind,
                         bounds_error=False, fill_value="extrapolate")
            out[col] = f(grid)
        except (ValueError, TypeError):
            # non-numeric or too few points for the chosen kind
            out[col] = df[col].iloc[0] if len(df) else None
    return out


# ── change notification ──────────────────────────────────────────────────────
class _Notifier(QObject):
    """Emits when the active configuration changes or is edited."""
    changed = Signal(str)          # key of the active configuration


notifier = _Notifier()


# ── store ────────────────────────────────────────────────────────────────────
_store = None                      # {"active": key, "configs": {key: cfg}}


def config_path() -> Path:
    """Where user configurations and the active choice are kept."""
    return _SETTINGS_FILE


def _read_file() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load():
    global _store
    if _store is not None:
        return _store

    configs = {k: SensorConfig.from_dict(d) for k, d in BUILTIN.items()}

    data = _read_file()
    for d in data.get("sensors", []):
        try:
            cfg = SensorConfig.from_dict(d)
        except Exception:
            continue
        configs[cfg.key] = cfg          # user copy overrides the built-in

    active = data.get("active")
    if active not in configs:
        active = DEFAULT_KEY if DEFAULT_KEY in configs else next(iter(configs))

    _store = {"active": active, "configs": configs}
    return _store


def _write():
    store = _load()
    payload = {
        "active": store["active"],
        "sensors": [c.to_dict() for c in store["configs"].values()],
    }
    try:
        _SETTINGS_FILE.write_text(json.dumps(payload, indent=2),
                                  encoding="utf-8")
    except Exception:
        pass


def all_configs() -> list:
    """Every configuration, built-ins first, then user additions."""
    store = _load()
    order = [k for k in BUILTIN if k in store["configs"]]
    order += [k for k in store["configs"] if k not in BUILTIN]
    return [store["configs"][k] for k in order]


def get(key) -> SensorConfig:
    return _load()["configs"].get(key)


def is_builtin(key) -> bool:
    return key in BUILTIN


def active() -> SensorConfig:
    """The configuration in force for this session."""
    store = _load()
    return store["configs"][store["active"]]


def active_key() -> str:
    return _load()["active"]


def set_active(key) -> SensorConfig:
    store = _load()
    if key in store["configs"]:
        store["active"] = key
        _write()
        notifier.changed.emit(key)
    return active()


def upsert(cfg: SensorConfig) -> SensorConfig:
    """Add or replace a configuration and persist it."""
    store = _load()
    store["configs"][cfg.key] = cfg
    _write()
    if store["active"] == cfg.key:
        notifier.changed.emit(cfg.key)
    return cfg


def delete(key) -> bool:
    """Remove a user configuration (built-ins are reset instead)."""
    store = _load()
    if key not in store["configs"]:
        return False
    if key in BUILTIN:
        store["configs"][key] = SensorConfig.from_dict(BUILTIN[key])
    else:
        del store["configs"][key]
        if store["active"] == key:
            store["active"] = (DEFAULT_KEY if DEFAULT_KEY in store["configs"]
                               else next(iter(store["configs"])))
    _write()
    notifier.changed.emit(store["active"])
    return True


def reset_to_builtin(key) -> SensorConfig:
    """Discard edits to a shipped configuration."""
    if key not in BUILTIN:
        return get(key)
    store = _load()
    cfg = SensorConfig.from_dict(BUILTIN[key])
    store["configs"][key] = cfg
    _write()
    if store["active"] == key:
        notifier.changed.emit(key)
    return cfg


def unique_key(base: str) -> str:
    """A key not already in use, derived from `base`."""
    store = _load()
    slug = re.sub(r"[^a-z0-9_]+", "_", str(base).strip().lower()).strip("_")
    slug = slug or "sensor"
    if slug not in store["configs"]:
        return slug
    n = 2
    while f"{slug}_{n}" in store["configs"]:
        n += 1
    return f"{slug}_{n}"
