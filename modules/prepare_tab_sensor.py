# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Sensor configuration tab - pick the device this session works with.

The selection is the app's active ``sensor_config.SensorConfig``: raw
import (Process), nadir validation (Validate) and dataset creation all read
it, so switching sensors here changes the extensions scanned for, the
filename pattern, the parser that runs, the sample rate assumed by the
signal plots and the number of rows in a model input window.

Every field on this tab is data, not code. A third device is a New (or
Duplicate) plus a Save; only its reader needs writing, registered under
``sensor_config.PARSERS``.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from . import sensor_config
from .ml_widgets import (
    ACCENT, BAD, MUTED, OK, TEXT, WARN, MetaCard, Section,
    apply_section_defaults,
)

_EXAMPLE_STEM = "B61-0703140718"


class SensorTab:
    """Builds the Sensor configuration tab into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._cfg = sensor_config.active().copy()
        self._loading = False
        self._dirty = False
        self._packet_rows = {}          # extension -> QSpinBox

        self._build(frame)
        self._reload_list()
        self._load_into_widgets()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        outer.addWidget(scroll)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        scroll.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        # ── row 1: the session's sensor + a summary of what it implies ──────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        grp_sel = Section("Session sensor")
        sv = QVBoxLayout(grp_sel)
        sv.setSpacing(6)

        pick = QHBoxLayout()
        pick.setSpacing(6)
        self.cmb_sensor = QComboBox()
        self.cmb_sensor.setMinimumWidth(220)
        self.cmb_sensor.currentIndexChanged.connect(self._on_select)
        pick.addWidget(self.cmb_sensor, stretch=1)
        self.btn_new = QPushButton("New…")
        self.btn_new.clicked.connect(self._new)
        self.btn_dup = QPushButton("Duplicate")
        self.btn_dup.clicked.connect(self._duplicate)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._delete)
        for b in (self.btn_new, self.btn_dup, self.btn_delete):
            pick.addWidget(b)
        sv.addLayout(pick)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Display name")
        self.ed_name.textEdited.connect(self._touch)
        name_row = QHBoxLayout()
        name_row.addWidget(self._muted("Name"))
        name_row.addWidget(self.ed_name, stretch=1)
        name_row.addWidget(self._muted("Key"))
        self.lbl_key = QLabel("")
        self.lbl_key.setStyleSheet(f"color:{TEXT};")
        name_row.addWidget(self.lbl_key)
        sv.addLayout(name_row)

        self.ed_description = QPlainTextEdit()
        self.ed_description.setPlaceholderText(
            "What this device is and anything a user should know about it.")
        self.ed_description.setFixedHeight(64)
        self.ed_description.textChanged.connect(self._touch)
        sv.addWidget(self.ed_description)

        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        sv.addWidget(self.lbl_state)

        act = QHBoxLayout()
        act.setSpacing(6)
        self.btn_save = QPushButton("Save and use this sensor")
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_save.clicked.connect(self._save)
        self.btn_revert = QPushButton("Discard changes")
        self.btn_revert.clicked.connect(self._revert)
        self.btn_reset = QPushButton("Restore shipped values")
        self.btn_reset.clicked.connect(self._reset_builtin)
        act.addWidget(self.btn_save)
        act.addWidget(self.btn_revert)
        act.addWidget(self.btn_reset)
        act.addStretch()
        sv.addLayout(act)

        self.lbl_file = QLabel("")
        self.lbl_file.setStyleSheet(f"color:{MUTED};font-size:10px;")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        sv.addWidget(self.lbl_file)

        row1.addWidget(grp_sel, stretch=3)

        self.card_summary = MetaCard("In force")
        self.card_summary.setMinimumWidth(260)
        self.card_summary.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Expanding)
        row1.addWidget(self.card_summary, stretch=2)
        v.addLayout(row1)

        # ── row 2: acquisition + filename pattern ───────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        grp_acq = Section("Acquisition")
        av = QGridLayout(grp_acq)
        av.setVerticalSpacing(6)
        av.setColumnStretch(1, 1)

        av.addWidget(self._muted("Sampling rate (Hz)"), 0, 0)
        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(1.0, 1_000_000.0)
        self.spin_rate.setDecimals(1)
        self.spin_rate.setSingleStep(100.0)
        self.spin_rate.valueChanged.connect(self._touch)
        av.addWidget(self.spin_rate, 0, 1)

        av.addWidget(self._muted("Files per recording"), 1, 0)
        self.spin_files = QSpinBox()
        self.spin_files.setRange(1, 8)
        self.spin_files.valueChanged.connect(self._on_files_changed)
        av.addWidget(self.spin_files, 1, 1)

        av.addWidget(self._muted("File extensions"), 2, 0)
        self.ed_extensions = QLineEdit()
        self.ed_extensions.setPlaceholderText(".imp, .hig")
        self.ed_extensions.editingFinished.connect(self._on_extensions_changed)
        av.addWidget(self.ed_extensions, 2, 1)

        hint = self._muted(
            "The first extension defines a recording; the rest pair to it by "
            "filename stem.")
        hint.setWordWrap(True)
        av.addWidget(hint, 3, 0, 1, 2)

        av.addWidget(self._muted("Packet size (bytes)"), 4, 0,
                     Qt.AlignmentFlag.AlignTop)
        self.packet_holder = QWidget()
        self.packet_layout = QGridLayout(self.packet_holder)
        self.packet_layout.setContentsMargins(0, 0, 0, 0)
        self.packet_layout.setVerticalSpacing(4)
        av.addWidget(self.packet_holder, 4, 1)

        row2.addWidget(grp_acq, stretch=1)

        grp_name = Section("Filename pattern")
        nv = QVBoxLayout(grp_name)
        nv.setSpacing(6)
        nv.addWidget(self._muted(
            "Expression matched against a file's stem. Group 1 is the sensor, "
            "group 2 MMDD, group 3 HHMMSS."))
        self.ed_pattern = QLineEdit()
        self.ed_pattern.textEdited.connect(self._on_pattern_changed)
        nv.addWidget(self.ed_pattern)
        test_row = QHBoxLayout()
        test_row.addWidget(self._muted("Test a name"))
        self.ed_pattern_test = QLineEdit(_EXAMPLE_STEM)
        self.ed_pattern_test.textEdited.connect(self._update_pattern_preview)
        test_row.addWidget(self.ed_pattern_test, stretch=1)
        nv.addLayout(test_row)
        self.lbl_pattern = QLabel("")
        self.lbl_pattern.setWordWrap(True)
        nv.addWidget(self.lbl_pattern)
        nv.addStretch()
        row2.addWidget(grp_name, stretch=1)
        v.addLayout(row2)

        # ── row 3: channels + window/resampling ─────────────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(10)

        grp_ch = Section("Channels")
        cv = QVBoxLayout(grp_ch)
        cv.setSpacing(6)
        cv.addWidget(self._muted(
            "Columns the parser produces that a model may use as input. "
            "Double-click to rename."))
        self.list_channels = QListWidget()
        self.list_channels.setMinimumHeight(150)
        self.list_channels.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_channels.itemChanged.connect(self._touch)
        cv.addWidget(self.list_channels)
        ch_btns = QHBoxLayout()
        ch_btns.setSpacing(6)
        self.btn_ch_add = QPushButton("Add")
        self.btn_ch_add.clicked.connect(self._add_channel)
        self.btn_ch_remove = QPushButton("Remove")
        self.btn_ch_remove.clicked.connect(self._remove_channels)
        self.btn_ch_default = QPushButton("RAPID defaults")
        self.btn_ch_default.clicked.connect(self._default_channels)
        for b in (self.btn_ch_add, self.btn_ch_remove, self.btn_ch_default):
            ch_btns.addWidget(b)
        ch_btns.addStretch()
        cv.addLayout(ch_btns)
        row3.addWidget(grp_ch, stretch=1)

        grp_win = Section("Analysis window and interpolation")
        wv = QGridLayout(grp_win)
        wv.setVerticalSpacing(6)
        wv.setColumnStretch(1, 1)

        wv.addWidget(self._muted("Analysis window (s)"), 0, 0)
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.001, 60.0)
        self.spin_window.setDecimals(3)
        self.spin_window.setSingleStep(0.05)
        self.spin_window.valueChanged.connect(self._touch)
        wv.addWidget(self.spin_window, 0, 1)

        note = self._muted(
            "The window is the model's input: it sets the nadir window saved "
            "on Validate and the rows per recording on Dataset creation.")
        note.setWordWrap(True)
        wv.addWidget(note, 1, 0, 1, 2)

        self.chk_resample = QCheckBox(
            "Interpolate onto a different target rate")
        self.chk_resample.toggled.connect(self._on_resample_toggled)
        wv.addWidget(self.chk_resample, 2, 0, 1, 2)

        wv.addWidget(self._muted("Target rate (Hz)"), 3, 0)
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(1.0, 1_000_000.0)
        self.spin_target.setDecimals(1)
        self.spin_target.setSingleStep(100.0)
        self.spin_target.valueChanged.connect(self._touch)
        wv.addWidget(self.spin_target, 3, 1)

        wv.addWidget(self._muted("Method"), 4, 0)
        self.cmb_method = QComboBox()
        for label, key in sensor_config.RESAMPLE_METHODS:
            self.cmb_method.addItem(label, key)
        self.cmb_method.currentIndexChanged.connect(self._touch)
        wv.addWidget(self.cmb_method, 4, 1)

        resample_note = self._muted(
            "A lower-rate device can be lifted to the rate the models were "
            "trained at - model input length is a sample count, so 100 Hz "
            "and 6000 Hz do not describe the same window.")
        resample_note.setWordWrap(True)
        wv.addWidget(resample_note, 5, 0, 1, 2)

        self.lbl_window = QLabel("")
        self.lbl_window.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        self.lbl_window.setWordWrap(True)
        wv.addWidget(self.lbl_window, 6, 0, 1, 2)
        row3.addWidget(grp_win, stretch=1)
        v.addLayout(row3)

        # ── row 4: parser ───────────────────────────────────────────────────
        grp_parser = Section("Parser")
        pv = QGridLayout(grp_parser)
        pv.setVerticalSpacing(6)
        pv.setColumnStretch(1, 1)
        pv.addWidget(self._muted("Reader for this device"), 0, 0)
        self.cmb_parser = QComboBox()
        self.cmb_parser.currentIndexChanged.connect(self._touch)
        pv.addWidget(self.cmb_parser, 0, 1)
        parser_note = self._muted(
            "Registered readers only. To add one: write the reader, register "
            "it in modules/sensor_config.py under PARSERS with the signature "
            "parser(paths, out_dir, config), then select it here. RAPID keeps "
            "calling rapid_functions.process_imp_hig_direct.")
        parser_note.setWordWrap(True)
        pv.addWidget(parser_note, 1, 0, 1, 2)
        v.addWidget(grp_parser)

        v.addStretch()
        apply_section_defaults(frame)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── configuration list ───────────────────────────────────────────────────
    def _reload_list(self, select=None):
        select = select or self._cfg.key
        self._loading = True
        self.cmb_sensor.clear()
        for cfg in sensor_config.all_configs():
            suffix = " (shipped)" if sensor_config.is_builtin(cfg.key) else ""
            self.cmb_sensor.addItem(f"{cfg.name}{suffix}", cfg.key)
        idx = self.cmb_sensor.findData(select)
        self.cmb_sensor.setCurrentIndex(max(0, idx))
        self._loading = False

    def _on_select(self, _idx):
        if self._loading:
            return
        key = self.cmb_sensor.currentData()
        if key is None or key == self._cfg.key:
            return
        if self._dirty and not self._confirm_discard():
            self._loading = True
            self.cmb_sensor.setCurrentIndex(
                self.cmb_sensor.findData(self._cfg.key))
            self._loading = False
            return
        self._cfg = sensor_config.get(key).copy()
        self._dirty = False
        self._load_into_widgets()

    def _confirm_discard(self):
        answer = QMessageBox.question(
            self.window, "Unsaved changes",
            f"'{self._cfg.name}' has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    # ── widgets <-> configuration ────────────────────────────────────────────
    def _load_into_widgets(self):
        cfg = self._cfg
        self._loading = True

        self.ed_name.setText(cfg.name)
        self.lbl_key.setText(cfg.key)
        self.ed_description.setPlainText(cfg.description)
        self.spin_rate.setValue(float(cfg.sampling_rate_hz))
        self.spin_files.setValue(int(cfg.files_per_recording))
        self.ed_extensions.setText(", ".join(cfg.file_extensions))
        self.ed_pattern.setText(cfg.filename_pattern)
        self.spin_window.setValue(float(cfg.window_sec))
        self.chk_resample.setChecked(bool(cfg.resample))
        self.spin_target.setValue(float(cfg.target_rate_hz
                                        or cfg.sampling_rate_hz))
        self.spin_target.setEnabled(bool(cfg.resample))
        self.cmb_method.setEnabled(bool(cfg.resample))
        m = self.cmb_method.findData(cfg.resample_method)
        self.cmb_method.setCurrentIndex(max(0, m))

        self.list_channels.clear()
        for name in cfg.channels:
            self._append_channel(name)

        self.cmb_parser.clear()
        for key in sorted(sensor_config.PARSERS):
            self.cmb_parser.addItem(key, key)
        if self.cmb_parser.findData(cfg.parser) < 0:
            self.cmb_parser.addItem(cfg.parser, cfg.parser)
        self.cmb_parser.setCurrentIndex(self.cmb_parser.findData(cfg.parser))

        self._rebuild_packet_rows(cfg.file_extensions)
        self._loading = False

        self._update_pattern_preview()
        self._refresh_state()

    def _collect(self):
        """Read the widgets back into a SensorConfig (unsaved)."""
        cfg = self._cfg
        cfg.name = self.ed_name.text().strip() or cfg.key
        cfg.description = self.ed_description.toPlainText().strip()
        cfg.sampling_rate_hz = float(self.spin_rate.value())
        cfg.files_per_recording = int(self.spin_files.value())
        cfg.file_extensions = self._parse_extensions(self.ed_extensions.text())
        cfg.packet_sizes = {ext: int(spin.value())
                            for ext, spin in self._packet_rows.items()}
        cfg.filename_pattern = self.ed_pattern.text().strip()
        cfg.channels = [self.list_channels.item(i).text().strip()
                        for i in range(self.list_channels.count())
                        if self.list_channels.item(i).text().strip()]
        cfg.window_sec = float(self.spin_window.value())
        cfg.resample = self.chk_resample.isChecked()
        cfg.target_rate_hz = float(self.spin_target.value())
        cfg.resample_method = self.cmb_method.currentData() or "linear"
        cfg.parser = self.cmb_parser.currentData() or cfg.parser
        return cfg

    @staticmethod
    def _parse_extensions(text):
        out = []
        for part in str(text).replace(";", ",").split(","):
            part = part.strip().lower()
            if not part:
                continue
            if not part.startswith("."):
                part = "." + part
            if part not in out:
                out.append(part)
        return out

    # ── packet sizes follow the extension list ───────────────────────────────
    def _rebuild_packet_rows(self, extensions):
        while self.packet_layout.count():
            item = self.packet_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._packet_rows = {}

        if not extensions:
            self.packet_layout.addWidget(
                self._muted("No extensions listed."), 0, 0)
            return

        for i, ext in enumerate(extensions):
            lab = QLabel(ext)
            lab.setStyleSheet(f"color:{TEXT};")
            spin = QSpinBox()
            spin.setRange(0, 65535)
            spin.setSpecialValueText("not set")
            spin.setValue(self._cfg.packet_size(ext))
            spin.valueChanged.connect(self._touch)
            self.packet_layout.addWidget(lab, i, 0)
            self.packet_layout.addWidget(spin, i, 1)
            self._packet_rows[ext] = spin
        self.packet_layout.setColumnStretch(1, 1)

    def _on_extensions_changed(self):
        exts = self._parse_extensions(self.ed_extensions.text())
        if exts == list(self._packet_rows):
            return
        # keep the sizes already entered for extensions that survived
        self._cfg.packet_sizes = {ext: int(spin.value())
                                  for ext, spin in self._packet_rows.items()}
        self.ed_extensions.setText(", ".join(exts))
        self._rebuild_packet_rows(exts)
        self._touch()

    def _on_files_changed(self, _value):
        self._touch()

    def _on_resample_toggled(self, on):
        self.spin_target.setEnabled(on)
        self.cmb_method.setEnabled(on)
        self._touch()

    # ── channels ─────────────────────────────────────────────────────────────
    def _append_channel(self, name):
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.list_channels.addItem(item)

    def _add_channel(self):
        name, ok = QInputDialog.getText(
            self.window, "Add channel", "Column name:")
        if ok and name.strip():
            self._append_channel(name.strip())
            self._touch()

    def _remove_channels(self):
        for item in self.list_channels.selectedItems():
            self.list_channels.takeItem(self.list_channels.row(item))
        self._touch()

    def _default_channels(self):
        self.list_channels.clear()
        for name in sensor_config.RAPID_CHANNELS:
            self._append_channel(name)
        self._touch()

    # ── pattern preview ──────────────────────────────────────────────────────
    def _on_pattern_changed(self, _text):
        self._update_pattern_preview()
        self._touch()

    def _update_pattern_preview(self):
        probe = self._cfg.copy(filename_pattern=self.ed_pattern.text().strip())
        stem = self.ed_pattern_test.text().strip()
        if probe.compiled_pattern() is None:
            self.lbl_pattern.setText("Not a valid expression.")
            self.lbl_pattern.setStyleSheet(f"color:{BAD};")
            return
        if not stem:
            self.lbl_pattern.setText("")
            return
        sensor, date, time = probe.parse_stem(stem)
        if not date and not time:
            self.lbl_pattern.setText(
                "No match - the inventory would show the whole stem and no "
                "deployment date or time.")
            self.lbl_pattern.setStyleSheet(f"color:{WARN};")
            return
        self.lbl_pattern.setText(
            f"Sensor {sensor} · date {date} · time {time}")
        self.lbl_pattern.setStyleSheet(f"color:{OK};")

    # ── state ────────────────────────────────────────────────────────────────
    def _touch(self, *_args):
        if self._loading:
            return
        self._dirty = True
        self._collect()
        self._refresh_state()

    def _refresh_state(self):
        cfg = self._cfg
        active_key = sensor_config.active_key()
        problems = cfg.problems()

        self.lbl_window.setText(
            f"Model input window: {cfg.window_sec:g} s → "
            f"{cfg.window_samples} samples at {cfg.output_rate_hz:g} Hz "
            f"(saved as *{cfg.window_suffix}.csv)")

        if problems:
            self.lbl_state.setText("• " + "<br>• ".join(problems))
            self.lbl_state.setStyleSheet(f"color:{BAD};")
        elif self._dirty:
            self.lbl_state.setText("Unsaved changes.")
            self.lbl_state.setStyleSheet(f"color:{WARN};")
        elif cfg.key == active_key:
            self.lbl_state.setText(
                "Active - raw import, validation and dataset creation use "
                "this configuration.")
            self.lbl_state.setStyleSheet(f"color:{OK};")
        else:
            self.lbl_state.setText(
                f"Not the session sensor (that is "
                f"'{sensor_config.active().name}'). Save to switch to it.")
            self.lbl_state.setStyleSheet(f"color:{MUTED};")

        self.btn_save.setEnabled(not problems)
        self.btn_revert.setEnabled(self._dirty)
        self.btn_reset.setEnabled(sensor_config.is_builtin(cfg.key))
        self.btn_delete.setEnabled(not sensor_config.is_builtin(cfg.key))
        self.btn_delete.setText(
            "Delete" if not sensor_config.is_builtin(cfg.key) else "Shipped")
        self.lbl_file.setText(f"Stored in {sensor_config.config_path()}")

        self.card_summary.set_title(f"In force: {sensor_config.active().name}")
        live = sensor_config.active()
        self.card_summary.set_rows([
            ("Sensor", live.name),
            ("Sampling rate", f"{live.sampling_rate_hz:g} Hz"),
            ("Processed rate", f"{live.output_rate_hz:g} Hz"),
            ("Files per recording",
             f"{live.files_per_recording} ({', '.join(live.required_extensions)})"),
            ("Window", f"{live.window_sec:g} s / {live.window_samples} samples"),
            ("Channels", f"{len(live.channels)}"),
            ("Parser", live.parser),
        ])

    # ── actions ──────────────────────────────────────────────────────────────
    def _save(self):
        cfg = self._collect()
        problems = cfg.problems()
        if problems:
            QMessageBox.warning(self.window, "Cannot save",
                                "\n".join(f"• {p}" for p in problems))
            return
        sensor_config.upsert(cfg)
        sensor_config.set_active(cfg.key)
        self._dirty = False
        self._reload_list(cfg.key)
        self._refresh_state()
        self._emit(f"Session sensor: {cfg.name} "
                   f"({cfg.output_rate_hz:g} Hz, {cfg.window_samples} samples "
                   f"per window)")

    def _revert(self):
        stored = sensor_config.get(self._cfg.key)
        if stored is None:
            return
        self._cfg = stored.copy()
        self._dirty = False
        self._load_into_widgets()
        self._emit(f"Reverted {self._cfg.name} to the stored configuration.")

    def _reset_builtin(self):
        key = self._cfg.key
        if not sensor_config.is_builtin(key):
            return
        if QMessageBox.question(
                self.window, "Restore shipped values",
                f"Replace '{self._cfg.name}' with the values StrikeWorks "
                "ships? Your edits to it are lost.") \
                != QMessageBox.StandardButton.Yes:
            return
        self._cfg = sensor_config.reset_to_builtin(key).copy()
        self._dirty = False
        self._reload_list(key)
        self._load_into_widgets()
        self._emit(f"{self._cfg.name} restored to shipped values.")

    def _new(self):
        name, ok = QInputDialog.getText(
            self.window, "New sensor configuration", "Sensor name:")
        if not ok or not name.strip():
            return
        if self._dirty and not self._confirm_discard():
            return
        key = sensor_config.unique_key(name)
        cfg = sensor_config.SensorConfig(key=key, name=name.strip())
        cfg.description = "New configuration - review every field below."
        sensor_config.upsert(cfg)
        self._cfg = cfg.copy()
        self._dirty = False
        self._reload_list(key)
        self._load_into_widgets()
        self._emit(f"Created sensor configuration '{cfg.name}'.")

    def _duplicate(self):
        source = self._collect()
        name = f"{source.name} copy"
        key = sensor_config.unique_key(name)
        cfg = source.copy(key=key, name=name)
        sensor_config.upsert(cfg)
        self._cfg = cfg
        self._dirty = False
        self._reload_list(key)
        self._load_into_widgets()
        self._emit(f"Duplicated to '{cfg.name}'.")

    def _delete(self):
        key = self._cfg.key
        if sensor_config.is_builtin(key):
            return
        if QMessageBox.question(
                self.window, "Delete configuration",
                f"Delete '{self._cfg.name}'?") \
                != QMessageBox.StandardButton.Yes:
            return
        sensor_config.delete(key)
        self._cfg = sensor_config.active().copy()
        self._dirty = False
        self._reload_list(self._cfg.key)
        self._load_into_widgets()
        self._emit("Configuration deleted.")

    def _emit(self, message, ms=5000):
        if self._status is not None:
            self._status(message, ms)
