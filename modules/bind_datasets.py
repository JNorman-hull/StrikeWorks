"""Bind training data - several datasets (a model_features.csv per library,
typically) stacked into one training set, without merging the libraries
themselves. Lives in Model training > Train's Training dataset box, which
loads the result straight away.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from . import recording_rate, settings
from .theme import style


class MixedDataError(ValueError):
    """Datasets that can't be stacked: more than one sensor or frequency."""


def bind_csvs(paths):
    """(stacked DataFrame, columns_differ). Rows are stacked in file order,
    each tagged with its source file (`_bind_source`); a column missing
    from some files is kept and left blank there. Raises MixedDataError
    unless they all hold one sensor at one rate, as one model needs."""
    frames, column_sets = [], set()
    for path in paths:
        df = pd.read_csv(path, low_memory=False)
        column_sets.add(frozenset(df.columns))
        df.insert(0, "_bind_source", Path(path).name)
        frames.append(df)
    joined = pd.concat(frames, ignore_index=True, sort=False)
    problem = recording_rate.dataset_problem(joined)
    if problem:
        raise MixedDataError(problem)
    return joined, len(column_sets) > 1


class BindTrainingData(QWidget):
    """File list + Add / Remove / Bind and save. `bound(path)` fires with
    the saved file."""

    bound = Signal(str)

    def __init__(self, parent=None, start_dir=None):
        super().__init__(parent)
        self._paths = []
        self._start_dir = start_dir
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        title = QLabel("Bind training data")
        title.setToolTip(
            "Combine several datasets - e.g. one model_features.csv per "
            "library - into one training set. Rows are stacked; columns not "
            "shared by every file are kept and left blank where missing.")
        style(title, role="muted")
        v.addWidget(title)

        self.list_files = QListWidget()
        self.list_files.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_files.setMaximumHeight(90)
        v.addWidget(self.list_files)

        row = QHBoxLayout()
        btn_add = QPushButton("Add file…")
        btn_add.clicked.connect(self._add_files)
        row.addWidget(btn_add)
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(btn_remove)
        row.addStretch()
        self.btn_bind = QPushButton("Bind and save…")
        self.btn_bind.clicked.connect(self._bind)
        row.addWidget(self.btn_bind)
        v.addLayout(row)

        self.lbl_status = QLabel("")
        style(self.lbl_status, role="muted")
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)
        self._refresh()

    def _refresh(self, message=None):
        self.btn_bind.setEnabled(len(self._paths) >= 2)
        self.lbl_status.setText(
            message if message is not None
            else (f"{len(self._paths)} file(s) queued." if self._paths else ""))
        # no empty line under the buttons: they line up with what's beside them
        self.lbl_status.setVisible(bool(self.lbl_status.text()))

    def _add_files(self):
        start = str(self._start_dir() if callable(self._start_dir)
                    else settings.get_libraries_dir())
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add training dataset(s)", start, "CSV files (*.csv)")
        for p in paths:
            path = Path(p)
            if path not in self._paths:
                self._paths.append(path)
                self.list_files.addItem(str(path))
        self._refresh()

    def _remove_selected(self):
        for row in sorted((self.list_files.row(i)
                           for i in self.list_files.selectedItems()),
                          reverse=True):
            self.list_files.takeItem(row)
            del self._paths[row]
        self._refresh()

    def _bind(self):
        try:
            joined, columns_differ = bind_csvs(self._paths)
        except MixedDataError as e:
            QMessageBox.warning(self, "These datasets can't be bound", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Could not read file", str(e))
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save bound training data",
            str(settings.get_input_data_dir() / "model_features_bound.csv"),
            "CSV files (*.csv)")
        if not out_path:
            return
        try:
            joined.to_csv(out_path, index=False)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        msg = (f"Bound {len(self._paths)} file(s), {len(joined)} rows → "
               f"{Path(out_path).name}")
        if columns_differ:
            msg += (" - the files didn't all share the same columns, so some "
                    "values are blank; check it before training on it")
        self._refresh(msg)
        self.bound.emit(out_path)
