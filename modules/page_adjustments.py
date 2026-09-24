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
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from . import settings
from .ml_widgets import MUTED, TEXT, Section, apply_section_defaults


class AdjustmentsDialog(QDialog):
    """Modal-to-its-parent folder-settings dialog, opened from the gear
    icon's Adjustments button."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Adjustments")
        self.setMinimumWidth(520)
        # window-modal, not the exec()-default application-modal - this
        # should only block MainWindow, not an unrelated top-level window
        # like the dev console, which needs to stay interactive with
        # Adjustments open (that's the whole point of the "Show console"
        # button living here)
        self.setWindowModality(Qt.WindowModality.WindowModal)
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

        grp_lib = Section("Libraries folder")
        gv = QVBoxLayout(grp_lib)
        gv.setSpacing(6)
        self.ed_libraries = self._folder_field(
            gv, settings.get_libraries_dir(), "libraries folder",
            "The folder containing every library. Which library this "
            "session works in is still chosen on Home.")
        v.addWidget(grp_lib)

        grp_models = Section("Models folder")
        gv = QVBoxLayout(grp_models)
        gv.setSpacing(6)
        self.ed_models = self._folder_field(
            gv, settings.get_models_dir(), "models folder (default)",
            "Where Model prediction/Evaluate look for deployed models by "
            "default, and where Deploy writes to before a session "
            "library is selected. Loading a model from elsewhere is "
            "always still a free browse.")
        self.ed_default_model = self._model_field(
            gv, "Default binary model:",
            settings.get_default_model, settings.set_default_model,
            "binary*.joblib",
            "Which deployed binary model Simple mode's Predict step uses "
            "automatically. Unset (the normal state) uses 'binary1' if "
            "present, else whichever model was deployed most recently.")
        self.ed_default_mc_model = self._model_field(
            gv, "Default multiclass model:",
            settings.get_default_mc_model, settings.set_default_mc_model,
            "multiclass*.joblib",
            "Same, for the optional region/multiclass stage. Unset uses "
            "'multiclass1' if present, else the most recently deployed "
            "multiclass model.")
        v.addWidget(grp_models)

        grp_out = Section("Default output folder")
        gv = QVBoxLayout(grp_out)
        gv.setSpacing(6)
        self.ed_output = self._folder_field(
            gv, settings.get_output_dir(), "default output folder",
            "Where reports/exports go when no session library is "
            "selected - once one is, output goes under that library's "
            "own StrikeWorks_user_output/ folder instead.")
        v.addWidget(grp_out)

        grp_input = Section("Default input data folder")
        gv = QVBoxLayout(grp_input)
        gv.setSpacing(6)
        self.ed_input_data = self._folder_field(
            gv, settings.get_input_data_dir(), "default input data folder",
            "Where Simple mode's Save and export (and the dev demo "
            "runner) write exported model-ready datasets by default.")
        v.addWidget(grp_input)

        self._dev_mode_row(v)

        v.addStretch()
        close_row = QHBoxLayout()
        close_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        v.addLayout(close_row)

        apply_section_defaults(self)

    def _folder_field(self, gv, current, caption, tip):
        """One folder path + Browse, inside a caller-supplied Section
        layout. The description that used to sit as an always-visible
        label under the row is now the Browse button's tooltip."""
        row = QHBoxLayout()
        ed = QLineEdit(str(current))
        ed.setReadOnly(True)
        ed.setToolTip(tip)
        row.addWidget(ed, stretch=1)
        btn = QPushButton("Browse…")
        btn.setToolTip(tip)
        btn.clicked.connect(lambda: self._browse(ed, caption))
        row.addWidget(btn)
        gv.addLayout(row)
        return ed

    def _browse(self, ed, caption):
        chosen = QFileDialog.getExistingDirectory(
            self, f"Select {caption}", ed.text())
        if not chosen:
            return
        ed.setText(chosen)
        if ed is self.ed_libraries:
            settings.set_libraries_dir(chosen)
        elif ed is self.ed_models:
            settings.set_models_dir(chosen)
        elif ed is self.ed_output:
            settings.set_output_dir(chosen)
        elif ed is self.ed_input_data:
            settings.set_input_data_dir(chosen)

    def _model_field(self, gv, label_text, getter, setter, glob_pattern, tip):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color:{MUTED};font-size:11px;")
        row.addWidget(lbl)
        current = getter()
        ed = QLineEdit(str(current) if current else "")
        ed.setReadOnly(True)
        ed.setPlaceholderText("Not set - uses the naming convention above")
        ed.setToolTip(tip)
        row.addWidget(ed, stretch=1)
        btn = QPushButton("Browse…")
        btn.setToolTip(tip)
        btn.clicked.connect(
            lambda: self._browse_model(ed, setter, glob_pattern))
        row.addWidget(btn)
        btn_clear = QPushButton("Clear")
        btn_clear.setToolTip("Unpin - back to the naming convention above.")
        btn_clear.clicked.connect(lambda: self._clear_model(ed, setter))
        row.addWidget(btn_clear)
        gv.addLayout(row)
        return ed

    def _browse_model(self, ed, setter, glob_pattern):
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select default model", str(settings.get_models_dir()),
            f"Model files ({glob_pattern})")
        if not chosen:
            return
        ed.setText(chosen)
        setter(chosen)

    def _clear_model(self, ed, setter):
        ed.setText("")
        setter(None)

    def _dev_mode_row(self, v):
        grp = Section("Dev mode")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        row = QHBoxLayout()
        self.btn_dev_mode = QPushButton()
        self.btn_dev_mode.setCheckable(True)
        self.btn_dev_mode.setChecked(settings.get_dev_mode())
        self.btn_dev_mode.setToolTip(
            "Pops out a live console that mirrors everything the app "
            "prints - status messages, worker/prediction output - handy "
            "while running through a page manually. Stays on for future "
            "launches until turned off here.")
        self._refresh_dev_mode_label()
        self.btn_dev_mode.toggled.connect(self._toggle_dev_mode)
        row.addWidget(self.btn_dev_mode)
        btn_show = QPushButton("Show console")
        btn_show.setToolTip(
            "Bring the dev console to the front (turns Dev mode on first "
            "if it's currently off).")
        btn_show.clicked.connect(self._show_dev_console)
        row.addWidget(btn_show)
        row.addStretch()
        gv.addLayout(row)
        note = QLabel("The demos (Simple / Advanced) run from the dev "
                      "console itself - open it, close this window, and "
                      "watch the app being driven.")
        note.setStyleSheet(f"color:{MUTED};font-size:11px;")
        note.setWordWrap(True)
        gv.addWidget(note)

        v.addWidget(grp)

    def _refresh_dev_mode_label(self):
        self.btn_dev_mode.setText(
            "Dev mode: ON" if self.btn_dev_mode.isChecked()
            else "Dev mode: OFF")

    def _toggle_dev_mode(self, checked):
        self._refresh_dev_mode_label()
        settings.set_dev_mode(checked)
        self.window.dev_console.set_enabled(checked)

    def _show_dev_console(self):
        console = self.window.dev_console
        if not self.btn_dev_mode.isChecked():
            # fires _toggle_dev_mode -> installs the tee, persists the
            # setting, and shows the console - without this, clicking
            # Show console while the toggle was off would raise an empty
            # window with no stdout/stderr tee ever attached to it
            self.btn_dev_mode.setChecked(True)
        else:
            console.set_enabled(True)   # no-op if already installed
        console.bring_up()
