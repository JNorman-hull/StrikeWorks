# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Widgets for entering annotation values (Annotate, and later the
Misclassification tool's Labels box - the same component, not a second
implementation).

``AnnotationValueEditor`` is deliberately not ``ml_widgets.LevelGrouper``.
LevelGrouper groups *many observed levels* into *few named classes* for
training, and is dataframe-agnostic by design (``set_data``/``groups()``/
``changed``). Annotation entry is "pick or add one value for one
recording" - a flat known-value list, not a levels-into-classes mapping -
so it gets its own small widget. What is reused from LevelGrouper is the
pattern: the widget only holds what it is given and emits a signal on
change; ``annotation_schema`` is where values actually live and get edited
(add/rename/remove), the same split ``ml_train_state.py`` keeps from
LevelGrouper itself.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from .ml_widgets import MUTED

_BLANK = "-"   # em dash: "no value entered"


class AnnotationValueEditor(QWidget):
    """One variable: a value combo, add-new, and a values-management button."""

    changed = Signal(str)   # new value

    def __init__(self, var_name, parent=None):
        super().__init__(parent)
        self.var_name = var_name

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.cmb = QComboBox()
        self.cmb.setMinimumWidth(140)
        self.cmb.currentIndexChanged.connect(self._on_changed)
        row.addWidget(self.cmb, stretch=1)

        self.btn_edit = QPushButton("Edit…")
        self.btn_edit.setToolTip("Add, rename or remove known values")
        self.btn_edit.clicked.connect(self._edit_values)
        row.addWidget(self.btn_edit)

        self.refresh()

    # ── data ─────────────────────────────────────────────────────────────────
    def refresh(self, keep_current=True):
        current = self.current() if keep_current else None
        var = asch.get(self.var_name)
        values = list(var.values) if var else []

        self.cmb.blockSignals(True)
        self.cmb.clear()
        self.cmb.addItem(_BLANK, "")
        for v in values:
            self.cmb.addItem(v, v)
        if current and current not in values:
            # the row's stored value isn't in the known list (e.g. entered
            # before the value was added, or since removed) - show it
            # anyway rather than silently discarding what is on disk
            self.cmb.addItem(current, current)
        idx = self.cmb.findData(current or "")
        self.cmb.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb.blockSignals(False)

    def set_current(self, value):
        value = "" if value is None else str(value).strip()
        self.refresh(keep_current=False)
        idx = self.cmb.findData(value)
        if idx < 0 and value:
            self.cmb.addItem(value, value)
            idx = self.cmb.count() - 1
        self.cmb.blockSignals(True)
        self.cmb.setCurrentIndex(max(0, idx))
        self.cmb.blockSignals(False)

    def current(self) -> str:
        return self.cmb.currentData() or ""

    def _on_changed(self, _idx):
        self.changed.emit(self.current())

    # ── manage ───────────────────────────────────────────────────────────────
    def _edit_values(self):
        dlg = _ValueListDialog(self.var_name, self.window())
        dlg.exec()
        self.refresh()


class _ValueListDialog(QDialog):
    """Rename or remove a variable's known values."""

    def __init__(self, var_name, parent=None):
        super().__init__(parent)
        self.var_name = var_name
        var = asch.get(var_name)
        self.setWindowTitle(f"Known values - {var.label if var else var_name}")
        self.resize(320, 360)

        v = QVBoxLayout(self)
        note = QLabel(
            "Double-click to rename. Removing a value only changes what "
            "the picker offers - recordings already carrying it keep it.")
        note.setStyleSheet(f"color:{MUTED};")
        note.setWordWrap(True)
        v.addWidget(note)

        self.list = QListWidget()
        self._reload()
        self.list.itemChanged.connect(self._on_renamed)
        v.addWidget(self.list, stretch=1)

        add_row = QHBoxLayout()
        btn_add = QPushButton("Add value…")
        btn_add.clicked.connect(self._add_value)
        add_row.addWidget(btn_add)
        add_row.addStretch()
        v.addLayout(add_row)

        btn_row = QHBoxLayout()
        btn_remove = QPushButton("Remove selected")
        btn_remove.clicked.connect(self._remove_selected)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

    def _reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        var = asch.get(self.var_name)
        for value in (var.values if var else []):
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._prior_text = {id(self.list.item(i)): self.list.item(i).text()
                            for i in range(self.list.count())}

    def _add_value(self):
        var = asch.get(self.var_name)
        label = var.label if var else self.var_name
        text, ok = QInputDialog.getText(
            self, f"Add value - {label}", "New value:")
        text = text.strip()
        if not ok or not text:
            return
        asch.add_value(self.var_name, text)
        self._reload()

    def _on_renamed(self, item):
        old = self._prior_text.get(id(item), item.text())
        new = item.text().strip()
        if not new:
            item.setText(old)
            return
        if new != old:
            asch.rename_value(self.var_name, old, new)
        self._prior_text[id(item)] = new

    def _remove_selected(self):
        items = self.list.selectedItems()
        if not items:
            return
        names = ", ".join(i.text() for i in items)
        if QMessageBox.question(
                self, "Remove values",
                f"Remove {len(items)} value(s) from the known list?\n"
                f"{names}\n\nRecordings already using them keep them.") \
                != QMessageBox.StandardButton.Yes:
            return
        for item in items:
            asch.remove_value(self.var_name, item.text())
        self._reload()


class VariableListDialog(QDialog):
    """Add, rename or remove annotation variables (the columns, not their
    values). Renaming only changes the display label - the index column
    name is left alone, so historical data stays under the name it was
    written with."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Annotation variables")
        self.resize(360, 400)

        v = QVBoxLayout(self)
        note = QLabel(
            "Double-click to rename a variable's display label. Removing a "
            "variable stops it being offered here - recordings already "
            "carrying its column keep that data.")
        note.setStyleSheet(f"color:{MUTED};")
        note.setWordWrap(True)
        v.addWidget(note)

        self.list = QListWidget()
        self._reload()
        self.list.itemChanged.connect(self._on_renamed)
        v.addWidget(self.list, stretch=1)

        add_row = QHBoxLayout()
        self.btn_add = QPushButton("Add variable…")
        self.btn_add.clicked.connect(self._add_variable)
        add_row.addWidget(self.btn_add)
        add_row.addStretch()
        v.addLayout(add_row)

        btn_row = QHBoxLayout()
        btn_remove = QPushButton("Remove selected")
        btn_remove.clicked.connect(self._remove_selected)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

    def _reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        for var in asch.all_variables():
            item = QListWidgetItem(var.label)
            item.setData(Qt.ItemDataRole.UserRole, var.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._prior_text = {id(self.list.item(i)): self.list.item(i).text()
                            for i in range(self.list.count())}

    def _on_renamed(self, item):
        old = self._prior_text.get(id(item), item.text())
        new = item.text().strip()
        if not new:
            item.setText(old)
            return
        if new != old:
            var_name = item.data(Qt.ItemDataRole.UserRole)
            var = asch.get(var_name)
            if var is not None:
                var.label = new
                asch.upsert(var)
        self._prior_text[id(item)] = new

    def _add_variable(self):
        label, ok = QInputDialog.getText(
            self, "Add annotation variable",
            "Display name (e.g. \"Approach direction\"):")
        label = label.strip()
        if not ok or not label:
            return
        var = asch.AnnotationVariable(
            name=asch.unique_name(label), label=label, values=[])
        asch.upsert(var)
        self._reload()

    def _remove_selected(self):
        items = self.list.selectedItems()
        if not items:
            return
        names = ", ".join(i.text() for i in items)
        if QMessageBox.question(
                self, "Remove variables",
                f"Remove {len(items)} variable(s)?\n{names}\n\n"
                "Recordings already annotated with them keep that data.") \
                != QMessageBox.StandardButton.Yes:
            return
        for item in items:
            asch.delete(item.data(Qt.ItemDataRole.UserRole))
        self._reload()
