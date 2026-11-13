"""Sort by, for every list of sensors - Annotate, Export animations (both
through `library_widgets.LibrarySelector`) and StrikeWorks's Validate step:
one control (`SortControl`), one order (`sort_rows`) and one choice,
remembered in the settings file and shared by every list.

  Needs review first  sensors flagged for review at the top (the order
                      validation_core has always used), else as listed
  Sensor name         by name, numbers in numeric order (B61 before B300)
  Recording time      by the time in the name (B300-0924101751: 24 Sep,
                      10:17:51), names without one after, by name
"""
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from . import settings
from .theme import muted_label

REVIEW, NAME, TIME = "review", "name", "time"
OPTIONS = ((REVIEW, "Needs review first"), (NAME, "Sensor name"),
           (TIME, "Recording time"))
_SECTION = "sensor_lists"

# a RAPID sensor's name: <device>-<MMDDhhmmss>
_TIME_RE = re.compile(r"-(\d{10})(?:\D|$)")


class _Notifier(QObject):
    changed = Signal(str)


notifier = _Notifier()


def current() -> str:
    how = settings.read_section(_SECTION).get("sort", REVIEW)
    return how if how in dict(OPTIONS) else REVIEW


def set_current(how):
    if how == current():
        return
    section = dict(settings.read_section(_SECTION))
    section["sort"] = how
    settings.write_section(_SECTION, section)
    notifier.changed.emit(how)


def natural_key(text):
    """Text with its runs of digits compared as numbers."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower())
            for part in re.split(r"(\d+)", str(text)) if part]


def time_key(stem):
    m = _TIME_RE.search(str(stem))
    return (0, m.group(1), natural_key(stem)) if m else (1, "", natural_key(stem))


def sort_rows(rows, how=None, needs_review=None, stem=lambda r: r["stem"]):
    """`rows` in the chosen order (`how`, default the remembered one).
    `needs_review(stem)` puts flagged sensors first for REVIEW; without it
    REVIEW keeps the rows as they are. Stable throughout."""
    how = how or current()
    if how == NAME:
        return sorted(rows, key=lambda r: natural_key(stem(r)))
    if how == TIME:
        return sorted(rows, key=lambda r: time_key(stem(r)))
    if needs_review is None:
        return list(rows)
    return sorted(rows, key=lambda r: not needs_review(stem(r)))


class SortControl(QWidget):
    """"Sort by" and its options. Every instance follows the one choice:
    changing it here saves it and updates the others, and each emits
    `changed` for its own list to re-sort."""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(muted_label("Sort by"))
        self.cmb = QComboBox()
        for key, label in OPTIONS:
            self.cmb.addItem(label, key)
        self.cmb.setToolTip(
            "The order of this list - and of every other sensor list, "
            "which follows the same choice.")
        self._show(current())
        self.cmb.currentIndexChanged.connect(
            lambda _i: set_current(self.cmb.currentData()))
        row.addWidget(self.cmb, stretch=1)
        notifier.changed.connect(self._on_changed)

    def _show(self, how):
        self.cmb.blockSignals(True)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(how)))
        self.cmb.blockSignals(False)

    def _on_changed(self, how):
        self._show(how)
        self.changed.emit(how)
