# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Settings: the app's folders, plus a few defaults (all in `settings.py`,
all optional).

  Libraries folder      - the folder holding every library (which library
                          is used is chosen on Home).
  Models folder         - where Model prediction, Evaluate and Deploy look
                          first; a model can still be loaded from anywhere.
  Default output folder - for reports and exports when no session library
                          is selected (otherwise the library's
                          StrikeWorks_user_output/).
  Default input data folder - where exported datasets are written.
  Default model         - the model StrikeWorks's Predict step uses;
                          unset means 'binary1' / 'multiclass1', else the
                          newest.
  Console (bottom left) - everything the app prints, errors included, and
                          the demos (dev_console.py).

After it closes, `main.py` has Home re-read the libraries folder.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)

from . import settings
from .layout import Section
from . import theme
from .theme import style


class SettingsDialog(QDialog):
    """Opened from the settings panel's Settings button."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        # window-modal, so the console (opened from here) stays usable
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        title = QLabel("Settings")
        style(title, role="title")
        v.addWidget(title)
        subtitle = QLabel("Folder locations used across the app.")
        style(subtitle, role="muted")
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
            "Which deployed binary model StrikeWorks's Predict step uses "
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
            "Where Save and export writes model-ready datasets by "
            "default.")
        v.addWidget(grp_input)

        self._appearance_row(v)

        v.addStretch()
        close_row = QHBoxLayout()
        btn_console = QPushButton("Console")
        btn_console.setToolTip(
            "Everything the app has printed this session - status "
            "messages, worker output, warnings and errors - and the demos. "
            "Also saved as it goes, to this session's log file.")
        btn_console.clicked.connect(self._show_console)
        close_row.addWidget(btn_console)
        close_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        v.addLayout(close_row)


    def _folder_field(self, gv, current, caption, tip):
        """A folder path and Browse (with `tip` as its tooltip)."""
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
        style(lbl, role="note")
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

    def _appearance_row(self, v):
        grp = Section("Appearance")
        gv = QHBoxLayout(grp)
        gv.addWidget(QLabel("Theme"))
        self.cmb_theme = QComboBox()
        for key, palette in theme.THEMES.items():
            self.cmb_theme.addItem(palette["label"], key)
        self.cmb_theme.setCurrentIndex(
            max(0, self.cmb_theme.findData(settings.get_theme())))
        self.cmb_theme.currentIndexChanged.connect(self._theme_chosen)
        gv.addWidget(self.cmb_theme)
        self.lbl_theme = QLabel("")
        style(self.lbl_theme, role="note")
        gv.addWidget(self.lbl_theme, stretch=1)
        v.addWidget(grp)

    def _theme_chosen(self, _index):
        key = self.cmb_theme.currentData()
        settings.set_theme(key)
        self.lbl_theme.setText(
            "" if key == theme.NAME
            else "Takes effect the next time StrikeWorks starts.")

    def _show_console(self):
        self.window.dev_console.bring_up()
