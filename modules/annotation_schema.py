# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Annotation variables - what the Annotate page lets a user record about a
recording, and the known values each one offers.

Mirrors ``sensor_config.py``'s pattern: a small dataclass, a JSON store in
the user's home folder, a ``notifier`` the page follows. Nothing here reads
or writes ``global_sensor_index.csv`` directly - that is
``deployment_index.set_row_values`` - this module only tracks which
columns exist and what values are known for each.

Defaults are today's four annotation columns, unchanged, so nothing already
built around them needs to change:

  * ``modules/page_dataset.py`` - ``_LABEL_COLS``, the external annotation
    CSV join (``sens_file`` -> ``file``)
  * ``modules/ml_state.py`` - ``ANNOTATION_COLUMNS``, ground-truth detection
    at prediction time

Annotate writes the same column names directly onto the sensor's index row
instead of via a separate CSV, but a dataset already carrying these columns
from the old workflow is read identically either way.
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

_SETTINGS_FILE = Path.home() / ".strikeworks_annotations.json"


@dataclass
class AnnotationVariable:
    """One annotation column: its name, display label and known values."""

    name: str
    label: str = ""
    values: list = field(default_factory=list)

    def __post_init__(self):
        if not self.label:
            self.label = self.name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AnnotationVariable":
        return cls(name=data["name"], label=data.get("label", ""),
                  values=list(data.get("values", [])))


# The four columns the MVP's model_labels.csv workflow already uses
# (modules/page_dataset.py:_LABEL_COLS), with the value sets already implied
# elsewhere in the app (modules/page_dataset.py:_STRIKE_TYPES/_REGION_ORDER)
# offered as a starting point rather than an empty list.
DEFAULT_VARIABLES = [
    AnnotationVariable(
        name="overall_passage_type", label="Overall passage type",
        values=["no_contact", "leading_edge", "other"]),
    AnnotationVariable(
        name="leading_edge_type", label="Leading edge type", values=[]),
    AnnotationVariable(
        name="other_type", label="Other contact type", values=[]),
    AnnotationVariable(
        name="concentric_pump_region", label="Concentric pump region",
        values=["1", "2", "3", "4", "5"]),
]


class _Notifier(QObject):
    """Emits when the variable set or a variable's values change."""
    changed = Signal()


notifier = _Notifier()

_store = None   # [AnnotationVariable, ...]


def _load():
    global _store
    if _store is not None:
        return _store
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        _store = [AnnotationVariable.from_dict(d) for d in data.get(
            "variables", [])]
        if not _store:
            _store = [AnnotationVariable.from_dict(v.to_dict())
                      for v in DEFAULT_VARIABLES]
    except Exception:
        _store = [AnnotationVariable.from_dict(v.to_dict())
                  for v in DEFAULT_VARIABLES]
    return _store


def _write():
    payload = {"variables": [v.to_dict() for v in _load()]}
    try:
        _SETTINGS_FILE.write_text(json.dumps(payload, indent=2),
                                  encoding="utf-8")
    except Exception:
        pass


def all_variables() -> list:
    """Every annotation variable, in the order they were added."""
    return list(_load())


def get(name) -> AnnotationVariable:
    return next((v for v in _load() if v.name == name), None)


def upsert(var: AnnotationVariable):
    store = _load()
    existing = next((i for i, v in enumerate(store) if v.name == var.name),
                    None)
    if existing is None:
        store.append(var)
    else:
        store[existing] = var
    _write()
    notifier.changed.emit()


def delete(name):
    store = _load()
    store[:] = [v for v in store if v.name != name]
    _write()
    notifier.changed.emit()


def add_value(var_name, value):
    """Add `value` to a variable's known list, if not already there."""
    value = str(value).strip()
    if not value:
        return
    var = get(var_name)
    if var is None or value in var.values:
        return
    var.values.append(value)
    _write()
    notifier.changed.emit()


def rename_value(var_name, old, new):
    """Rename a known value. Does not touch rows already carrying `old` -
    that is a bulk-edit the caller can offer separately if wanted."""
    new = str(new).strip()
    if not new:
        return
    var = get(var_name)
    if var is None or old not in var.values:
        return
    if new in var.values and new != old:
        var.values.remove(old)
    else:
        var.values[var.values.index(old)] = new
    _write()
    notifier.changed.emit()


def remove_value(var_name, value):
    """Remove a value from the known list. Rows already using it keep it -
    this only changes what the picker offers going forward."""
    var = get(var_name)
    if var is None or value not in var.values:
        return
    var.values.remove(value)
    _write()
    notifier.changed.emit()


def unique_name(base: str) -> str:
    """An index-safe column name not already in use, derived from `base`."""
    import re
    slug = re.sub(r"[^a-z0-9_]+", "_", str(base).strip().lower()).strip("_")
    slug = slug or "annotation"
    existing = {v.name for v in _load()}
    if slug not in existing:
        return slug
    n = 2
    while f"{slug}_{n}" in existing:
        n += 1
    return f"{slug}_{n}"
