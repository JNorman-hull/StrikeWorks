"""Annotation variables: the columns Annotate records for each recording,
and their known values.

Read from the settings file's "annotation_variables" section, falling back
to config/default_settings.json. Names are used as given - a variable's
name is the index column it reads and writes. Variables are in two groups:
annotations (always shown) and position annotations (`POSITION_GROUP`,
shown while Annotate's "Position annotations" box is ticked). The values
themselves are written by `deployment_index.set_row_values`.
"""
from dataclasses import asdict, dataclass, field

from PySide6.QtCore import QObject, Signal

from . import settings

# this module's section of the settings file (settings.py)
_SECTION = "annotation_variables"

MAIN_GROUP, POSITION_GROUP = "", "position"
GROUP_LABELS = {MAIN_GROUP: "Annotations",
                POSITION_GROUP: "Position annotations"}


@dataclass
class AnnotationVariable:
    """One annotation column: its name, display label and known values."""

    name: str
    label: str = ""
    values: list = field(default_factory=list)
    group: str = MAIN_GROUP      # MAIN_GROUP or POSITION_GROUP

    def __post_init__(self):
        if not self.label:
            self.label = self.name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AnnotationVariable":
        return cls(name=data["name"], label=data.get("label", ""),
                  values=[str(v) for v in data.get("values", [])],
                  group=data.get("group", MAIN_GROUP))


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
        _store = [AnnotationVariable.from_dict(d) for d in
                  settings.read_section(_SECTION).get("variables", [])]
    except (KeyError, TypeError, ValueError) as e:
        print(f"Saved annotation variables can't be read: {e}")
        _store = []
    return _store


def _write():
    section = dict(settings.read_section(_SECTION))
    section["variables"] = [v.to_dict() for v in _load()]
    settings.write_section(_SECTION, section)


def all_variables(group=None) -> list:
    """Every annotation variable, in the order they were added - or only
    those in `group` ("" for the main group)."""
    return [v for v in _load() if group is None or v.group == group]


def set_group(name, group):
    """Move variable `name` to `group` ("" or POSITION_GROUP)."""
    var = get(name)
    if var is None or var.group == group:
        return
    var.group = group
    _write()
    notifier.changed.emit()


def show_position() -> bool:
    """Whether Annotate shows the position annotations."""
    return bool(settings.read_section(_SECTION).get("show_position", False))


def set_show_position(on: bool):
    section = dict(settings.read_section(_SECTION))
    section["show_position"] = bool(on)
    settings.write_section(_SECTION, section)


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
