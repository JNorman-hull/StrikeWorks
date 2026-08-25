# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Sensor configurations - one source of truth for how a device's raw files
are named, paired, parsed and brought onto a common time base.

Everything the rest of the app used to hardcode for the RAPID sensor lives
here as data: the timestamp clock, the output rate, the files that make one
recording with their packet sizes and native rates, the channel list and the
parser. Pages read the *selected* configuration rather than module constants,
so choosing a different sensor on the Prepare page changes raw import and the
rate the processed signals are assumed to be at.

Rates
-----
Three different rates matter, and conflating them is the easy mistake:

``timebase_hz``
    Ticks per second of the raw counter in the file. Dividing the counter by
    it gives seconds. RAPID stamps both files from one 2000 Hz clock.

``native_rate_hz`` (per file)
    How fast that file's channels actually arrive. For RAPID the .imp block
    (IMU, pressure, temperature, battery) is 100 Hz and the .hig block is
    2000 Hz but event-triggered, so it is sparse rather than continuous.

``output_rate_hz``
    The uniform grid the processed CSV is written on - 2000 Hz for RAPID.

A file's ``method`` says how it gets onto that grid. The 100 Hz .imp
channels are interpolated up to 2000 Hz - that is the interpolation the
RAPID processing has always done. The .hig channels are already at 2000 Hz
but arrive in bursts around events (about 29% of a typical run, with gaps
of up to 13 seconds), so each recorded sample is placed in its own grid
slot and the gaps are left empty rather than having signal invented across
them. Both are described here rather than left implicit in the parser.

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
A configuration names its parser. ``PARSERS`` maps that name to a callable

    parser(paths, out_dir, config) -> (DataFrame, summary_dict)

where ``paths`` maps a lowercase file extension to the raw file for one
recording (``{".imp": Path(...), ".hig": Path(...)}`` for RAPID), ``out_dir``
is the library's ``processed_sens_data`` folder and ``config`` is the
SensorConfig in use. This is the single code point a new device needs:
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

# filename pattern: SENSOR-MMDDHHMMSS  e.g. B61-0703140718. Not exposed on
# the Prepare page - RAPID and its successors name files the same way - but
# a device that does not can have this edited in the JSON store.
RAPID_FNAME_PATTERN = r"^([A-Za-z0-9]{2,4})-(\d{4})(\d{6})$"

# How far either side of the acceleration peak the parser looks for the
# pressure nadir. 1.5 s each way - the RAPID code's ±3000 samples at 2000 Hz.
NADIR_SEARCH_SEC = 1.5

# How a file's channels reach the output grid.
#
# "as recorded" is not a resampling: each sample the device wrote is placed
# in its own slot on the grid and the gaps between bursts are left empty.
# It is the right choice for an event-triggered file like RAPID's .hig,
# which records at the full rate but only around events - interpolating
# would invent signal across the seconds where nothing was recorded.
METHODS = [
    ("Interpolate (linear)", "linear"),
    ("Interpolate (cubic spline)", "cubic"),
    ("As recorded, gaps left empty", "nearest"),
    ("Hold previous value", "previous"),
]

_SETTINGS_FILE = Path.home() / ".strikeworks_sensors.json"


# ── one raw file within a recording ──────────────────────────────────────────
@dataclass
class SensorSource:
    """One of the raw files that together make a recording."""

    extension: str
    packet_size: int = 0            # bytes per packet, 0 = not known
    native_rate_hz: float = 0.0     # how fast this file's channels arrive
    method: str = "linear"          # how it reaches the output grid

    def __post_init__(self):
        self.extension = str(self.extension).lower()
        if self.extension and not self.extension.startswith("."):
            self.extension = "." + self.extension
        self.packet_size = int(self.packet_size or 0)
        self.native_rate_hz = float(self.native_rate_hz or 0.0)

    @property
    def interpolated(self) -> bool:
        return self.method in ("linear", "cubic")

    def describe(self, output_rate) -> str:
        rate = (f"{self.native_rate_hz:g} Hz" if self.native_rate_hz
                else "unknown rate")
        if self.method == "nearest":
            return (f"{self.extension} {rate}, placed as recorded on the "
                    f"{output_rate:g} Hz grid (gaps left empty)")
        how = dict((v, k) for k, v in METHODS).get(self.method, self.method)
        return (f"{self.extension} {rate} {how.lower()} onto the "
                f"{output_rate:g} Hz grid")


# ── the configuration record ─────────────────────────────────────────────────
@dataclass
class SensorConfig:
    """Everything about a sensor that raw import and processing depend on."""

    key: str
    name: str
    description: str = ""

    # rates (see the module docstring - these are three different things)
    timebase_hz: float = 2000.0
    output_rate_hz: float = 2000.0

    # the raw files that make one recording, primary first
    sources: list = field(default_factory=list)

    channels: list = field(default_factory=lambda: list(RAPID_CHANNELS))
    filename_pattern: str = RAPID_FNAME_PATTERN

    # the code point for the device's reader (see PARSERS)
    parser: str = "rapid_imp_hig"

    # ── derived values ──────────────────────────────────────────────────────
    @property
    def files_per_recording(self) -> int:
        return len(self.sources)

    @property
    def file_extensions(self) -> list:
        return [s.extension for s in self.sources]

    @property
    def required_extensions(self) -> list:
        """Extensions that must all be present for a complete recording."""
        return self.file_extensions

    @property
    def primary_extension(self) -> str:
        """The extension that defines a recording; others pair to it."""
        return self.sources[0].extension if self.sources else ""

    def source(self, ext: str):
        ext = str(ext).lower()
        return next((s for s in self.sources if s.extension == ext), None)

    def packet_size(self, ext: str, default: int = 0) -> int:
        s = self.source(ext)
        return s.packet_size if s and s.packet_size else default

    def method(self, ext: str, default: str = "linear") -> str:
        s = self.source(ext)
        return s.method if s else default

    def window_samples(self, seconds: float) -> int:
        """Rows in `seconds` of processed signal at this sensor's rate.

        The window length itself is a downstream decision (Validate chooses
        it, Dataset creation follows); the sample count it turns into is a
        property of the sensor, which is why it is answered here.
        """
        return int(round(float(seconds) * self.output_rate_hz))

    @property
    def nadir_search_samples(self) -> int:
        return int(round(NADIR_SEARCH_SEC * self.output_rate_hz))

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

    def describe_sources(self) -> str:
        if not self.sources:
            return "No raw files defined."
        return "; ".join(s.describe(self.output_rate_hz) for s in self.sources)

    # ── serialisation ───────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SensorConfig":
        data = _upgrade(dict(data))
        fields = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in data.items() if k in fields}
        clean.setdefault("key", "sensor")
        clean.setdefault("name", clean["key"])
        clean["sources"] = [
            s if isinstance(s, SensorSource) else SensorSource(**s)
            for s in clean.get("sources", [])]
        return cls(**clean)

    def copy(self, **changes) -> "SensorConfig":
        """A detached copy - asdict() deep-copies the nested records."""
        data = self.to_dict()
        data.update(changes)
        return SensorConfig.from_dict(data)

    # ── validation ──────────────────────────────────────────────────────────
    def problems(self) -> list:
        """Human-readable reasons this configuration cannot be used."""
        out = []
        if not str(self.name).strip():
            out.append("The configuration needs a name.")
        if self.timebase_hz <= 0:
            out.append("The timestamp clock must be greater than zero.")
        if self.output_rate_hz <= 0:
            out.append("The output rate must be greater than zero.")
        if not self.sources:
            out.append("A recording needs at least one raw file.")
        exts = self.file_extensions
        if any(len(e) < 2 for e in exts):
            out.append("Every raw file needs an extension.")
        if len(set(exts)) != len(exts):
            out.append("Two raw files share an extension.")
        if self.compiled_pattern() is None:
            out.append("The filename pattern is not a valid expression.")
        if self.parser not in PARSERS:
            out.append(f"No parser registered under '{self.parser}'.")
        return out


def _upgrade(data: dict) -> dict:
    """Bring a stored configuration up to the current shape.

    The first version of this file described a sensor with one
    ``sampling_rate_hz`` plus an optional resample, which could not say that
    RAPID's .imp channels arrive at 100 Hz and are interpolated up to the
    2000 Hz grid. Old records are read into the rates-and-sources shape so a
    user's saved sensors survive the change.
    """
    if "sources" in data or "sampling_rate_hz" not in data:
        return data

    clock = float(data.pop("sampling_rate_hz", 2000.0)) or 2000.0
    resample = bool(data.pop("resample", False))
    target = float(data.pop("target_rate_hz", 0.0) or 0.0)
    method = data.pop("resample_method", "linear")
    packets = {str(k).lower(): int(v)
               for k, v in dict(data.pop("packet_sizes", {})).items()}
    exts = [str(e).lower() for e in data.pop("file_extensions", [])]
    n = int(data.pop("files_per_recording", len(exts)) or len(exts))
    data.pop("window_sec", None)

    data["timebase_hz"] = clock
    data["output_rate_hz"] = target if (resample and target > 0) else clock
    data["sources"] = [
        {"extension": ext,
         "packet_size": packets.get(ext, 0),
         "native_rate_hz": clock,
         "method": method}
        for ext in exts[:max(1, n)]]
    return data


# ── shipped configurations ───────────────────────────────────────────────────
# Add a dict here to ship a third sensor. Nothing else in the app needs to
# change, other than registering its parser in PARSERS below.
BUILTIN = {
    "rapid": dict(
        key="rapid",
        name="RAPID",
        description=(
            "The current setup. Two files per recording, stamped from one "
            "2000 Hz clock: .imp carries the 100 Hz IMU, pressure, "
            "temperature and battery channels, .hig the high-g "
            "accelerometer, which records at the full 2000 Hz but only in "
            "bursts around events. Processing interpolates the .imp "
            "channels up onto a uniform 2000 Hz grid and drops each .hig "
            "sample into its slot on the same grid, leaving the gaps "
            "between bursts empty."),
        timebase_hz=2000.0,
        output_rate_hz=2000.0,
        sources=[
            dict(extension=".imp", packet_size=29,
                 native_rate_hz=100.0, method="linear"),
            dict(extension=".hig", packet_size=11,
                 native_rate_hz=2000.0, method="nearest"),
        ],
        channels=list(RAPID_CHANNELS),
        filename_pattern=RAPID_FNAME_PATTERN,
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
        timebase_hz=6000.0,
        output_rate_hz=6000.0,
        sources=[
            dict(extension=".dat", packet_size=0,
                 native_rate_hz=6000.0, method="linear"),
        ],
        channels=list(RAPID_CHANNELS),
        filename_pattern=RAPID_FNAME_PATTERN,
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
    """RAPID: one .imp and one .hig, merged onto a uniform grid."""
    rf = _load_rapid_module()
    return rf.process_imp_hig_direct(
        paths[".imp"], paths[".hig"], out_dir, config=config)


def _parse_unconfigured(paths, out_dir, config):
    raise NotImplementedError(
        f"'{config.name}' has no parser yet. Write its reader, register it "
        "in modules/sensor_config.py under PARSERS, and select it on the "
        "Prepare page.")


#: parser name -> callable(paths, out_dir, config) -> (DataFrame, summary)
PARSERS = {
    "rapid_imp_hig": _parse_rapid,
    "unconfigured": _parse_unconfigured,
}


def register_parser(name, fn):
    """Register a device reader under `name` (see the module docstring)."""
    PARSERS[name] = fn


def get_parser(name):
    return PARSERS.get(name, _parse_unconfigured)


# ── resampling ───────────────────────────────────────────────────────────────
_INTERP_KIND = {"linear": "linear", "cubic": "cubic",
                "nearest": "nearest", "previous": "previous"}


def resample_frame(df, out_rate, time_col="time_s", method="linear"):
    """Put `df` on a uniform grid at `out_rate` Hz.

    The generic form of what the RAPID parser does inline: lift a lower-rate
    block of channels onto the output grid. Available to any parser that
    does not build its own grid. Returns a new frame.
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
    """Emits when the selected configuration changes or is edited."""
    changed = Signal(str)          # key of the selected configuration


notifier = _Notifier()


# ── store ────────────────────────────────────────────────────────────────────
_store = None                      # {"active": key, "configs": {key: cfg}}


def config_path() -> Path:
    """Where user configurations and the current choice are kept."""
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
    """The configuration selected for this session."""
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
    """Discard edits to a configuration StrikeWorks provides."""
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
    """An internal identifier not already in use, derived from `base`."""
    store = _load()
    slug = re.sub(r"[^a-z0-9_]+", "_", str(base).strip().lower()).strip("_")
    slug = slug or "sensor"
    if slug not in store["configs"]:
        return slug
    n = 2
    while f"{slug}_{n}" in store["configs"]:
        n += 1
    return f"{slug}_{n}"
