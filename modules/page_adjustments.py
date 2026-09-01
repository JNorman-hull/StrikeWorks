# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Adjustments - the app's folder settings, in one place.

`btn_adjustments` already existed in main.ui (the gear-icon pop-out
settings panel's top row - Adjustments/About/More) but was never wired to
anything. This is its content: a plain modal dialog rather than a new
page or a restructured settings panel - "a simple pop-out window for the
basic settings" is exactly what a QDialog already gives for free, without
touching main.ui further.

Three folder settings, all in `settings.py`, all optional (every one of
them already has a working default before this dialog exists):

  Libraries folder   - the folder *containing* every library (was
                        changed via a "Libraries…" button on Home and on
                        every LibrarySelector/bespoke page picker - all
                        dropped in favour of this one central place;
                        selecting *which* library within it stays on
                        Home, the only place library selection happens
                        any more app-wide).
  Models folder       - default for Model prediction/Evaluate discovery
                        and Deploy's own default before a session library
                        is selected. Loading a model from anywhere else
                        is still a free browse wherever that already
                        existed - this only changes the starting point.
  Default output folder - fallback for reports/exports when no session
                        library is selected (StrikeWorks_user_output/
                        under the library takes over once one is).

A fourth, different in kind - not a folder, and not required the way the
three above are (each already has a working default; this one's default
*is* "unset"):

  Default model (Simple mode) - which deployed model Simple mode's
                        Predict step uses automatically, no picker shown
                        there. Unset (the normal state) means "most
                        recently deployed" instead of a pinned choice.

Changing the libraries folder here needs Home's own combo re-read
afterwards, since library discovery lives there - `main.py` calls
`window.home_page._refresh_library_combo()` after this dialog closes.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from . import settings
from .ml_widgets import MUTED, TEXT, Section, apply_section_defaults


class AdjustmentsDialog(QDialog):
    """Modal folder-settings dialog, opened from the gear icon's
    Adjustments button."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("Adjustments")
        self.setMinimumWidth(520)
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        title = QLabel("Adjustments")
        title.setStyleSheet(f"color:{TEXT};font-size:16px;font-weight:bold;")
        v.addWidget(title)
        subtitle = QLabel("Folder locations used across the app.")
        subtitle.setStyleSheet(f"color:{MUTED};")
        v.addWidget(subtitle)

        self.ed_libraries = self._folder_row(
            v, "Libraries folder",
            "The folder containing every library. Which library this "
            "session works in is still chosen on Home.",
            settings.get_libraries_dir())
        self.ed_models = self._folder_row(
            v, "Models folder (default)",
            "Where Model prediction/Evaluate look for deployed models by "
            "default, and where Deploy writes to before a session "
            "library is selected. Loading a model from elsewhere is "
            "always still a free browse.",
            settings.get_models_dir())
        self.ed_output = self._folder_row(
            v, "Default output folder",
            "Where reports/exports go when no session library is "
            "selected - once one is, output goes under that library's "
            "own StrikeWorks_user_output/ folder instead.",
            settings.get_output_dir())

        self.ed_default_model = self._model_row(v)

        v.addStretch()
        close_row = QHBoxLayout()
        close_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        v.addLayout(close_row)

        apply_section_defaults(self)

    def _folder_row(self, v, label, hint, current):
        grp = Section(label)
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet(f"color:{MUTED};font-size:11px;")
        hint_lbl.setWordWrap(True)
        gv.addWidget(hint_lbl)

        row = QHBoxLayout()
        ed = QLineEdit(str(current))
        ed.setReadOnly(True)
        row.addWidget(ed, stretch=1)
        btn = QPushButton("Browse…")
        btn.clicked.connect(lambda: self._browse(ed, label))
        row.addWidget(btn)
        gv.addLayout(row)

        v.addWidget(grp)
        return ed

    def _browse(self, ed, label):
        chosen = QFileDialog.getExistingDirectory(
            self, f"Select {label.lower()}", ed.text())
        if not chosen:
            return
        ed.setText(chosen)
        if ed is self.ed_libraries:
            settings.set_libraries_dir(chosen)
        elif ed is self.ed_models:
            settings.set_models_dir(chosen)
        elif ed is self.ed_output:
            settings.set_output_dir(chosen)

    def _model_row(self, v):
        grp = Section("Default model (Simple mode)")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        hint_lbl = QLabel(
            "Which deployed model Simple mode's Predict step uses "
            "automatically. Unset (the normal state) picks whichever "
            "model was deployed most recently instead.")
        hint_lbl.setStyleSheet(f"color:{MUTED};font-size:11px;")
        hint_lbl.setWordWrap(True)
        gv.addWidget(hint_lbl)

        current = settings.get_default_model()
        row = QHBoxLayout()
        ed = QLineEdit(str(current) if current else "")
        ed.setReadOnly(True)
        ed.setPlaceholderText("Not set - uses the most recently deployed model")
        row.addWidget(ed, stretch=1)
        btn = QPushButton("Browse…")
        btn.clicked.connect(lambda: self._browse_model(ed))
        row.addWidget(btn)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self._clear_model(ed))
        row.addWidget(btn_clear)
        gv.addLayout(row)
        v.addWidget(grp)
        return ed

    def _browse_model(self, ed):
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select default model", str(settings.get_models_dir()),
            "Model files (*.joblib)")
        if not chosen:
            return
        ed.setText(chosen)
        settings.set_default_model(chosen)

    def _clear_model(self, ed):
        ed.setText("")
        settings.set_default_model(None)
