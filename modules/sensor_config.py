"""Sensor configurations: how a device's raw files are named, paired,
parsed and brought onto a common time base.

A configuration is data: the timestamp clock, the output rate, the files
that make one recording with their packet sizes and native rates, the
channel list and the parser. Pages read the *selected* configuration
(Setup and deploy > Sensor configuration), except where a deployment has
its own saved.

Rates
-----
``timebase_hz``
    Ticks per second of the raw counter; counter / timebase = seconds.
    RAPID stamps both files from one 2000 Hz clock.

``native_rate_hz`` (per file)
    How fast that file's channels arrive. RAPID's .imp block (IMU,
    pressure, temperature, battery) is 100 Hz; its .hig block is 2000 Hz
    but event-triggered, so sparse.

``output_rate_hz``
    The uniform grid the processed CSV is written on - 2000 Hz for RAPID.

A device whose files state their own rate (the EEL tag's HIG header) is
written at each recording's rate instead: ``SensorConfig.recording_rate``
answers for any recording, and later stages read the rate from the
processed data (recording_rate.py).

A file's ``method`` says how it reaches the grid. RAPID's .imp channels are
interpolated up to 2000 Hz. Its .hig channels arrive in bursts around
events (about 29% of a typical run, with gaps of up to 13 s), so they are
*standardised*: each recorded sample goes into its own slot and every
other slot is 0, rather than interpolating across the gaps.

Computed channels
-----------------
``magnitudes`` lists the three-axis sensors that get a magnitude column -
``higacc_mag_g``, ``inacc_mag_ms`` (minus g) and ``rot_mag_degs``; all
three by default. ``nadir_method`` names the nadir detector in
``rapid_functions.NADIR_METHODS``: by default the lowest pressure just
before pressure steps up through the pump, falling back to the lowest
pressure near the acceleration peak for a recording with no such step.

Adding a sensor
---------------
1. In the app: Setup and deploy > Sensor configuration > New / Duplicate,
   then Save. User configurations are written to the settings file and
   read back on the next start.
2. In code: add a dict to ``BUILTIN``. Built-ins can be edited (saved as
   an override) and put back with ``reset_to_builtin()``.

Adding a parser
---------------
``PARSERS`` maps a configuration's parser name to

    parser(paths, out_dir, config) -> (DataFrame, summary_dict)

where ``paths`` maps a lower-case extension to that recording's raw file
(``{".imp": Path(...), ".hig": Path(...)}`` for RAPID), ``out_dir`` is the
library's ``processed_sens_data`` folder and ``config`` the SensorConfig in
use. A new device needs only its reader, registered here.
"""
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import settings

# Channels the RAPID parser produces and the models consume. Kept here so a
# configuration can carry its own list; ml_train_state.DEFAULT_CHANNELS is
# the training-side default and matches this one.
RAPID_CHANNELS = [
    "higacc_x_g", "higacc_y_g", "higacc_z_g",
    "inacc_x_ms", "inacc_y_ms", "inacc_z_ms",
    "rot_x_degs", "rot_y_degs", "rot_z_degs",
    "pressure_kpa",
]

# filename pattern: SENSOR-MMDDHHMMSS  e.g. B61-0703140718. Not shown in
# Sensor configuration (RAPID-family devices all name files this way); a
# device that doesn't can have it edited in the JSON store.
RAPID_FNAME_PATTERN = r"^([A-Za-z0-9]{2,4})-(\d{4})(\d{6})$"

# EEL tag: the last ten digits are MMDDhhmmss and everything before them is
# an operator-set device name ("EEL-001", "EEEEL-") - never a fixed prefix
# (EEL Tag Binary Format Specification, section 2)
EEL_FNAME_PATTERN = r"^(.+?)-?(\d{4})(\d{6})$"

# How far either side of the acceleration peak the parser looks for the
# pressure nadir. 1.5 s each way - the RAPID code's ±3000 samples at 2000 Hz.
NADIR_SEARCH_SEC = 1.5

# Three-axis sensors that can have a magnitude channel computed from them.
# The maths is in rapid_functions.MAGNITUDES; these are the keys and how
# they read in Sensor configuration.
MAGNITUDE_KEYS = ["higacc", "inacc", "rot"]
MAGNITUDE_LABELS = {
    "higacc": "High-g acceleration magnitude (g)",
    "inacc": "Inertial acceleration magnitude (m/s)",
    "rot": "Rotational magnitude (degs)",
}

# Nadir detectors, by name. The callables live in rapid_functions so the
# parser can be loaded on its own; this is the list Sensor configuration shows
# and the default a new configuration takes.
NADIR_METHOD_LABELS = {
    "pressure_step":
        "Pressure step at the pump (else near the acceleration peak)",
    "pressure_near_peak":
        "Lowest pressure near the acceleration peak",
}
DEFAULT_NADIR_METHOD = "pressure_step"
# what each does, under the list in Sensor configuration
NADIR_METHOD_NOTES = {
    "pressure_step":
        "The lowest pressure just before pressure steps up through the "
        "pump. A recording with no such step falls back to the lowest "
        "pressure within 1.5 s of its largest acceleration.",
    "pressure_near_peak":
        "The lowest pressure within 1.5 s of the recording's largest "
        "acceleration.",
}
# the one method there was before the pressure step; it is the step's fallback
_FORMER_NADIR_METHOD = "pressure_min_near_peak"

# How a file's channels reach the output grid.
#
# "standardise" is not a resampling: every sample the device wrote is placed
# in its own slot on the grid and every slot it did not write is set to 0.
# That is what RAPID does with .hig, which records at the full rate but only
# in bursts around events - the output is a continuous 2000 Hz series where
# the quiet stretches read as zero. Interpolating instead would invent
# signal across the seconds where nothing was recorded.
METHODS = [
    ("Standardise to grid, gaps filled with 0", "nearest"),
    ("Interpolate (linear)", "linear"),
    ("Interpolate (cubic spline)", "cubic"),
    ("Hold previous value", "previous"),
]

# this module's section of the settings file (settings.py)
_SECTION = "sensor_configs"


# one raw file within a recording
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

    def describe(self, output_rate) -> str:
        rate = (f"{self.native_rate_hz:g} Hz" if self.native_rate_hz
                else "unknown rate")
        if self.method == "nearest":
            return (f"{self.extension} {rate} standardised to "
                    f"{output_rate:g} Hz, gaps filled with 0")
        how = dict((v, k) for k, v in METHODS).get(self.method, self.method)
        return (f"{self.extension} {rate} {how.lower()} onto the "
                f"{output_rate:g} Hz grid")


# the configuration record
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

    # computed channels: magnitude of each three-axis sensor
    magnitudes: list = field(default_factory=lambda: list(MAGNITUDE_KEYS))

    # how the passage nadir is found (rapid_functions.NADIR_METHODS)
    nadir_method: str = DEFAULT_NADIR_METHOD

    # how far pressure lags acceleration in the processed CSV, seconds:
    # corrected for when Export animations lines the two up. Not shown in
    # Sensor configuration.
    pressure_offset_s: float = 0.01

    # the code point for the device's reader (see PARSERS)
    parser: str = "rapid_imp_hig"

    # derived values
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
        """Rows in `seconds` of processed signal at this sensor's configured
        rate, for showing in Sensor configuration."""
        return int(round(float(seconds) * self.output_rate_hz))

    @property
    def rate_in_file(self) -> bool:
        """Whether this sensor's files state their own rate."""
        return self.parser in RATE_READERS

    def recording_rate(self, paths: dict) -> float:
        """The rate one recording is processed at, `paths` as a parser takes
        them: what its file states, otherwise the configured output rate.
        Opens a file only for a sensor whose files state their rate."""
        read = RATE_READERS.get(self.parser)
        return (read(paths) if read else None) or self.output_rate_hz

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

    # serialisation
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

    # validation
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
        if self.nadir_method not in NADIR_METHOD_LABELS:
            out.append(f"No nadir method called '{self.nadir_method}'.")
        return out


def _upgrade(data: dict) -> dict:
    """Bring a saved configuration up to date: the nadir method saved
    before the pressure step existed becomes the pressure step (which falls
    back to it), and the first format (one ``sampling_rate_hz`` plus an
    optional resample) is read into the rates-and-sources shape.
    """
    if data.get("nadir_method") == _FORMER_NADIR_METHOD:
        data["nadir_method"] = DEFAULT_NADIR_METHOD
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


# shipped configurations
# Add a dict here to ship a third sensor. Nothing else in the app needs to
# change, other than registering its parser in PARSERS below.
BUILTIN = {
    "rapid": dict(
        key="rapid",
        name="RAPID",
        description=(
            "Default RAPID sensor - Taltech 100 + 2000hz "),
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
        magnitudes=list(MAGNITUDE_KEYS),
        nadir_method=DEFAULT_NADIR_METHOD,
        parser="rapid_imp_hig",
    ),
    "micro_eel": dict(
        key="micro_eel",
        name="Micro-EEL",
        description=(
            "EEL tag - a .HIG high-g stream (event-triggered; 2000, 2500 or "
            "5000 Hz) and a .IMP IMU/pressure stream (100 Hz) on one master "
            "clock, decoded per the EEL Tag Binary Format Specification "
            "v1.1.0: header records discarded, re-emitted HIG records "
            "removed. Each recording's rate comes from its HIG header and "
            "its processed CSV is written at that rate; the rates set here "
            "are only used for a file with no rate in its header."),
        timebase_hz=5000.0,
        output_rate_hz=5000.0,
        sources=[
            dict(extension=".imp", packet_size=23,
                 native_rate_hz=100.0, method="linear"),
            dict(extension=".hig", packet_size=11,
                 native_rate_hz=5000.0, method="nearest"),
        ],
        channels=list(RAPID_CHANNELS),
        filename_pattern=EEL_FNAME_PATTERN,
        magnitudes=list(MAGNITUDE_KEYS),
        nadir_method=DEFAULT_NADIR_METHOD,
        pressure_offset_s=0.0,      # one master clock: no offset to correct
        parser="eel_imp_hig",
    ),
}

DEFAULT_KEY = "rapid"


# parsers
_rapid_module = None


def _load_rapid_module():
    """Import rapid_functions on first use, so a session that never
    processes anything doesn't load scipy."""
    global _rapid_module
    if _rapid_module is None:
        from . import rapid_functions
        _rapid_module = rapid_functions
    return _rapid_module


def _parse_rapid(paths, out_dir, config):
    """RAPID: one .imp and one .hig, merged onto a uniform grid."""
    rf = _load_rapid_module()
    return rf.process_imp_hig_direct(
        paths[".imp"], paths[".hig"], out_dir, config=config)


def _parse_eel(paths, out_dir, config):
    """EEL tag: one .imp and one .hig on a shared master clock (eel_format)."""
    from . import eel_format
    return eel_format.process_eel(paths, out_dir, config)


def _eel_rate(paths):
    """The rate in an EEL recording's HIG header, or None (no file, or no
    rate in it)."""
    if ".hig" not in paths:
        return None
    from . import eel_format
    return eel_format.recording_rate(paths[".hig"])


def _parse_unconfigured(paths, out_dir, config):
    raise NotImplementedError(
        f"'{config.name}' has no parser yet. Write its reader, register it "
        "in modules/sensor_config.py under PARSERS, and select it in "
        "Sensor configuration.")


#: parser name -> callable(paths, out_dir, config) -> (DataFrame, summary)
PARSERS = {
    "rapid_imp_hig": _parse_rapid,
    "eel_imp_hig": _parse_eel,
    "unconfigured": _parse_unconfigured,
}


#: parser name -> callable(paths) -> the rate one recording states, or None
RATE_READERS = {
    "eel_imp_hig": _eel_rate,
}


def get_parser(name):
    return PARSERS.get(name, _parse_unconfigured)


# change notification
class _Notifier(QObject):
    """Emits when the selected configuration changes or is edited."""
    changed = Signal(str)          # key of the selected configuration


notifier = _Notifier()


# store
_store = None                      # {"active": key, "configs": {key: cfg}}


def config_path() -> Path:
    """Where user configurations and the current choice are kept."""
    return settings.SETTINGS_FILE


def _load():
    global _store
    if _store is not None:
        return _store

    configs = {k: SensorConfig.from_dict(d) for k, d in BUILTIN.items()}

    data = settings.read_section(_SECTION)
    for d in data.get("sensors", []):
        try:
            cfg = SensorConfig.from_dict(d)
        except (KeyError, TypeError, ValueError) as e:
            print(f"Skipped a saved sensor configuration that can't be read: {e}")
            continue
        configs[cfg.key] = cfg          # user copy overrides the built-in

    active = data.get("active")
    if active not in configs:
        active = DEFAULT_KEY if DEFAULT_KEY in configs else next(iter(configs))

    _store = {"active": active, "configs": configs}
    return _store


def _is_unmodified_builtin(cfg) -> bool:
    """True when `cfg` is a shipped configuration nobody has edited."""
    if cfg.key not in BUILTIN:
        return False
    return cfg.to_dict() == SensorConfig.from_dict(BUILTIN[cfg.key]).to_dict()


def _write():
    """Save the selection and any configuration that differs from its
    built-in. Untouched built-ins aren't written, so later changes to them in
    code still apply.
    """
    store = _load()
    payload = {
        "active": store["active"],
        "sensors": [c.to_dict() for c in store["configs"].values()
                    if not _is_unmodified_builtin(c)],
    }
    settings.write_section(_SECTION, payload)


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
