"""LevelGrouper - assign a variable's observed levels to named classes
(Model training's class grouping, Annotate's variable editor).
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)
from .layout import discard_widget
from .theme import style


# level grouping
class LevelGrouper(QWidget):
    """Map the observed levels of a variable to named classes, or exclude
    them. Levels come from the data and class names are free text - they
    become the model's class names.
    """

    changed = Signal()
    EXCLUDE = -1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._levels = []
        self._groups = []          # [{"name": str, "levels": [key, ...]}]
        self._updating = False
        self._name_edits = []
        self._level_combos = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # the class names beside the levels' assignments, each under a
        # muted heading
        cols = QHBoxLayout()
        cols.setSpacing(16)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(self._heading("Classes"))
        self._names_box = QVBoxLayout()
        self._names_box.setSpacing(2)
        names.addLayout(self._names_box)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add class")
        self.btn_add.clicked.connect(self._add_group)
        btn_row.addWidget(self.btn_add)
        btn_row.addStretch()
        names.addLayout(btn_row)
        names.addStretch()
        cols.addLayout(names, stretch=1)

        levels = QVBoxLayout()
        levels.setSpacing(2)
        levels.addWidget(self._heading("Levels"))
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(2)
        levels.addLayout(self._grid)
        levels.addStretch()
        cols.addLayout(levels, stretch=1)
        v.addLayout(cols)

    @staticmethod
    def _heading(text):
        lab = QLabel(text)
        style(lab, role="muted")
        return lab

    # public API
    def set_data(self, levels, groups):
        """levels: [(key, display, count)]; groups: [{"name", "levels"}].
        Nothing is rebuilt when they are what's shown already - the host
        hands back the grouping this widget just reported, and rebuilding
        would take away the class-name field being typed in."""
        levels = list(levels)
        groups = [{"name": g["name"], "levels": list(g["levels"])}
                  for g in groups]
        if levels == self._levels and groups == self._groups:
            return
        self._levels = levels
        self._groups = groups
        self._rebuild()

    def groups(self):
        return [{"name": g["name"], "levels": list(g["levels"])}
                for g in self._groups]

    # rebuild
    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                discard_widget(w)
            elif item.layout() is not None:
                self._clear(item.layout())

    def _rebuild(self):
        self._updating = True
        try:
            self._clear(self._names_box)
            self._clear(self._grid)
            self._name_edits = []
            self._level_combos = {}

            for i, g in enumerate(self._groups):
                row = QHBoxLayout()
                lab = QLabel(f"Class {i + 1}")
                style(lab, role="muted")
                lab.setMinimumWidth(56)
                ed = QLineEdit(g["name"])
                ed.setMinimumWidth(110)
                ed.setPlaceholderText("class name")
                ed.textChanged.connect(
                    lambda text, idx=i: self._name_changed(idx, text))
                btn = QPushButton("✕")
                btn.setFixedWidth(28)
                btn.setToolTip("Remove this class")
                btn.setEnabled(len(self._groups) > 1)
                btn.clicked.connect(lambda _c=False, idx=i:
                                    self._remove_group(idx))
                row.addWidget(lab)
                row.addWidget(ed, stretch=1)
                row.addWidget(btn)
                self._names_box.addLayout(row)
                self._name_edits.append(ed)

            assign = self._assignment()
            for r, (key, display, count) in enumerate(self._levels):
                lab = QLabel(f"{display}   (n={count})" if count is not None
                             else str(display))
                style(lab)
                cmb = QComboBox()
                cmb.setMinimumWidth(110)
                for i, g in enumerate(self._groups):
                    cmb.addItem(g["name"] or f"Class {i + 1}", i)
                cmb.addItem("Exclude", self.EXCLUDE)
                idx = cmb.findData(assign.get(key, self.EXCLUDE))
                cmb.setCurrentIndex(idx if idx >= 0 else cmb.count() - 1)
                cmb.currentIndexChanged.connect(
                    lambda _i, k=key: self._level_changed(k))
                self._grid.addWidget(lab, r, 0)
                self._grid.addWidget(cmb, r, 1)
                self._level_combos[key] = cmb
        finally:
            self._updating = False

    def _assignment(self):
        out = {}
        for i, g in enumerate(self._groups):
            for key in g["levels"]:
                out[key] = i
        return out

    # edits
    def _name_changed(self, idx, text):
        if self._updating or idx >= len(self._groups):
            return
        self._groups[idx]["name"] = text
        for cmb in self._level_combos.values():
            cmb.setItemText(idx, text or f"Class {idx + 1}")
        self.changed.emit()

    def _level_changed(self, key):
        if self._updating:
            return
        cmb = self._level_combos.get(key)
        if cmb is None:
            return
        target = cmb.currentData()
        for g in self._groups:
            if key in g["levels"]:
                g["levels"].remove(key)
        if target != self.EXCLUDE and target < len(self._groups):
            self._groups[target]["levels"].append(key)
        self.changed.emit()

    def _add_group(self):
        self._groups.append({"name": f"class_{len(self._groups) + 1}",
                             "levels": []})
        self._rebuild()
        self.changed.emit()

    def _remove_group(self, idx):
        if len(self._groups) <= 1 or idx >= len(self._groups):
            return
        del self._groups[idx]
        self._rebuild()
        self.changed.emit()
