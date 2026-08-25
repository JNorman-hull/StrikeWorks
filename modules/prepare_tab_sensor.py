# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Sensor configuration tab - pick the device this session works with.

The selection becomes the app's ``sensor_config.SensorConfig``: raw import
on Process reads it for the extensions to scan, the parser to run and the
packet sizes to unpack, and Validate and Dataset creation read the output
rate to know what a second of signal is worth in samples.

The rates panel is the important part, because three different rates are
easy to conflate: the counter clock the raw files are stamped from, the
rate each file's channels actually arrive at, and the uniform grid the
processed CSV is written on. RAPID's .imp channels arrive at 100 Hz and are
interpolated up onto a 2000 Hz grid, while the .hig channels arrive at
2000 Hz but only around events, so each sample is placed at its nearest
grid point. This tab states that rather than leaving it implicit in the
parser.

Every field here is data, not code. A new device is a New (or Duplicate)
plus a Save; only its reader needs writing, registered under
``sensor_config.PARSERS``.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)

from . import sensor_config
from .ml_widgets import (
    ACCENT, BAD, MUTED, OK, TEXT, WARN, MetaCard, Section,
    apply_section_defaults,
)


class SensorTab:
    """Builds the Sensor configuration tab into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._cfg = sensor_config.active().copy()
        self._loading = False
        self._dirty = False
        self._source_rows = []          # [{extension, packet, rate, method}]

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

        # ── row 1: the session's sensor + what it means downstream ──────────
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

        name_row = QHBoxLayout()
        name_row.addWidget(self._muted("Name"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Display name")
        self.ed_name.textEdited.connect(self._touch)
        name_row.addWidget(self.ed_name, stretch=1)
        sv.addLayout(name_row)

        self.ed_description = QPlainTextEdit()
        self.ed_description.setPlaceholderText(
            "What this device is and anything a user should know about it.")
        self.ed_description.setFixedHeight(96)
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
        self.btn_reset = QPushButton("Restore defaults")
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

        self.card_summary = MetaCard("Current sensor")
        self.card_summary.setMinimumWidth(260)
        self.card_summary.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Expanding)
        row1.addWidget(self.card_summary, stretch=2)
        v.addLayout(row1)

        # ── row 2: rates and raw files ──────────────────────────────────────
        grp_acq = Section("Rates and raw files")
        av = QVBoxLayout(grp_acq)
        av.setSpacing(6)

        rates = QGridLayout()
        rates.setVerticalSpacing(6)
        rates.setColumnStretch(3, 1)

        rates.addWidget(self._muted("Timestamp clock (Hz)"), 0, 0)
        self.spin_clock = QDoubleSpinBox()
        self.spin_clock.setRange(1.0, 1_000_000.0)
        self.spin_clock.setDecimals(1)
        self.spin_clock.setSingleStep(100.0)
        self.spin_clock.valueChanged.connect(self._touch)
        rates.addWidget(self.spin_clock, 0, 1)

        rates.addWidget(self._muted("Output rate (Hz)"), 0, 2)
        self.spin_output = QDoubleSpinBox()
        self.spin_output.setRange(1.0, 1_000_000.0)
        self.spin_output.setDecimals(1)
        self.spin_output.setSingleStep(100.0)
        self.spin_output.valueChanged.connect(self._touch)
        rates.addWidget(self.spin_output, 0, 3)

        clock_note = self._muted(
            "The clock is what the counter in the raw file ticks at - "
            "dividing by it turns the counter into seconds. The output rate "
            "is the uniform grid every channel is brought onto and the "
            "processed CSV is written at.")
        clock_note.setWordWrap(True)
        rates.addWidget(clock_note, 1, 0, 1, 4)
        av.addLayout(rates)

        header = QGridLayout()
        header.setVerticalSpacing(4)
        for col, text in enumerate(
                ("File", "Packet (bytes)", "Native rate (Hz)",
                 "Onto the output grid")):
            lab = self._muted(text)
            lab.setStyleSheet(f"color:{MUTED};font-size:10px;")
            header.addWidget(lab, 0, col)
        self.sources_layout = header
        holder = QWidget()
        holder.setLayout(header)
        av.addWidget(holder)

        src_btns = QHBoxLayout()
        src_btns.setSpacing(6)
        self.btn_src_add = QPushButton("Add file")
        self.btn_src_add.clicked.connect(self._add_source)
        self.btn_src_remove = QPushButton("Remove last file")
        self.btn_src_remove.clicked.connect(self._remove_source)
        src_btns.addWidget(self.btn_src_add)
        src_btns.addWidget(self.btn_src_remove)
        src_btns.addStretch()
        av.addLayout(src_btns)

        src_note = self._muted(
            "The first file defines a recording; the rest pair to it by "
            "filename stem. Interpolation lifts a slower file onto the "
            "output grid; nearest sample places a sparse, event-triggered "
            "file without inventing signal between its samples.")
        src_note.setWordWrap(True)
        av.addWidget(src_note)

        self.lbl_rates = QLabel("")
        self.lbl_rates.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        self.lbl_rates.setWordWrap(True)
        av.addWidget(self.lbl_rates)
        v.addWidget(grp_acq)

        # ── row 3: channels + parser ────────────────────────────────────────
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
        self.btn_ch_default = QPushButton("RAPID channels")
        self.btn_ch_default.clicked.connect(self._default_channels)
        for b in (self.btn_ch_add, self.btn_ch_remove, self.btn_ch_default):
            ch_btns.addWidget(b)
        ch_btns.addStretch()
        cv.addLayout(ch_btns)
        row3.addWidget(grp_ch, stretch=1)

        grp_parser = Section("Parser")
        pv = QVBoxLayout(grp_parser)
        pv.setSpacing(6)
        prow = QHBoxLayout()
        prow.addWidget(self._muted("Reader for this device"))
        self.cmb_parser = QComboBox()
        self.cmb_parser.currentIndexChanged.connect(self._touch)
        prow.addWidget(self.cmb_parser, stretch=1)
        pv.addLayout(prow)
        parser_note = self._muted(
            "Registered readers only. To add one: write the reader, register "
            "it in modules/sensor_config.py under PARSERS with the signature "
            "parser(paths, out_dir, config), then select it here. RAPID "
            "keeps calling rapid_functions.process_imp_hig_direct.")
        parser_note.setWordWrap(True)
        pv.addWidget(parser_note)
        pv.addStretch()
        row3.addWidget(grp_parser, stretch=1)
        v.addLayout(row3)

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
            self.cmb_sensor.addItem(cfg.name, cfg.key)
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
        self.ed_description.setPlainText(cfg.description)
        self.spin_clock.setValue(float(cfg.timebase_hz))
        self.spin_output.setValue(float(cfg.output_rate_hz))

        self.list_channels.clear()
        for name in cfg.channels:
            self._append_channel(name)

        self.cmb_parser.clear()
        for name in sorted(sensor_config.PARSERS):
            self.cmb_parser.addItem(name, name)
        if self.cmb_parser.findData(cfg.parser) < 0:
            self.cmb_parser.addItem(cfg.parser, cfg.parser)
        self.cmb_parser.setCurrentIndex(self.cmb_parser.findData(cfg.parser))

        self._rebuild_source_rows(cfg.sources)
        self._loading = False
        self._refresh_state()

    def _collect(self):
        """Read the widgets back into the SensorConfig being edited."""
        cfg = self._cfg
        cfg.name = self.ed_name.text().strip() or cfg.key
        cfg.description = self.ed_description.toPlainText().strip()
        cfg.timebase_hz = float(self.spin_clock.value())
        cfg.output_rate_hz = float(self.spin_output.value())
        cfg.sources = [
            sensor_config.SensorSource(
                extension=r["extension"].text().strip(),
                packet_size=r["packet"].value(),
                native_rate_hz=r["rate"].value(),
                method=r["method"].currentData() or "linear")
            for r in self._source_rows
            if r["extension"].text().strip()]
        cfg.channels = [self.list_channels.item(i).text().strip()
                        for i in range(self.list_channels.count())
                        if self.list_channels.item(i).text().strip()]
        cfg.parser = self.cmb_parser.currentData() or cfg.parser
        return cfg

    # ── one row per raw file ─────────────────────────────────────────────────
    def _rebuild_source_rows(self, sources):
        was_loading = self._loading
        self._loading = True

        # drop everything below the header row
        for i in reversed(range(self.sources_layout.count())):
            item = self.sources_layout.itemAt(i)
            row, _, _, _ = self.sources_layout.getItemPosition(i)
            if row == 0:
                continue
            w = item.widget()
            self.sources_layout.takeAt(i)
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._source_rows = []

        for i, src in enumerate(sources, start=1):
            ext = QLineEdit(src.extension)
            ext.setPlaceholderText(".imp")
            ext.setMaximumWidth(90)
            ext.editingFinished.connect(self._on_extension_edited)

            packet = QSpinBox()
            packet.setRange(0, 65535)
            packet.setSpecialValueText("not set")
            packet.setValue(int(src.packet_size))
            packet.valueChanged.connect(self._touch)

            rate = QDoubleSpinBox()
            rate.setRange(0.0, 1_000_000.0)
            rate.setDecimals(1)
            rate.setSingleStep(100.0)
            rate.setSpecialValueText("not set")
            rate.setValue(float(src.native_rate_hz))
            rate.valueChanged.connect(self._touch)

            method = QComboBox()
            for label, key in sensor_config.METHODS:
                method.addItem(label, key)
            method.setCurrentIndex(max(0, method.findData(src.method)))
            method.currentIndexChanged.connect(self._touch)

            self.sources_layout.addWidget(ext, i, 0)
            self.sources_layout.addWidget(packet, i, 1)
            self.sources_layout.addWidget(rate, i, 2)
            self.sources_layout.addWidget(method, i, 3)
            self._source_rows.append(
                dict(extension=ext, packet=packet, rate=rate, method=method))

        self._loading = was_loading
        self.btn_src_remove.setEnabled(len(self._source_rows) > 1)

    def _on_extension_edited(self):
        for row in self._source_rows:
            text = row["extension"].text().strip().lower()
            if text and not text.startswith("."):
                text = "." + text
            row["extension"].setText(text)
        self._touch()

    def _add_source(self):
        cfg = self._collect()
        cfg.sources.append(sensor_config.SensorSource(
            extension="", packet_size=0,
            native_rate_hz=cfg.output_rate_hz, method="linear"))
        self._rebuild_source_rows(cfg.sources)
        self._touch()

    def _remove_source(self):
        cfg = self._collect()
        if len(cfg.sources) <= 1:
            return
        cfg.sources = cfg.sources[:-1]
        self._rebuild_source_rows(cfg.sources)
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

    # ── state ────────────────────────────────────────────────────────────────
    def _touch(self, *_args):
        if self._loading:
            return
        self._dirty = True
        self._collect()
        self._refresh_state()

    def _refresh_state(self):
        cfg = self._cfg
        problems = cfg.problems()

        self.lbl_rates.setText(cfg.describe_sources())

        if problems:
            self.lbl_state.setText("• " + "<br>• ".join(problems))
            self.lbl_state.setStyleSheet(f"color:{BAD};")
        elif self._dirty:
            self.lbl_state.setText("Unsaved changes.")
            self.lbl_state.setStyleSheet(f"color:{WARN};")
        elif cfg.key == sensor_config.active_key():
            self.lbl_state.setText(
                "Selected - raw import, validation and dataset creation use "
                "this sensor.")
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
        self.lbl_file.setText(f"Stored in {sensor_config.config_path()}")

        live = sensor_config.active()
        self.card_summary.set_title(f"Current sensor: {live.name}")
        self.card_summary.set_rows([
            ("Timestamp clock", f"{live.timebase_hz:g} Hz"),
            ("Output rate", f"{live.output_rate_hz:g} Hz"),
            ("Files per recording",
             f"{live.files_per_recording} "
             f"({', '.join(live.file_extensions)})"),
            ("Channels", f"{len(live.channels)}"),
            ("Parser", live.parser),
            ("200 ms window", f"{live.window_samples(0.2)} samples"),
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
        self._emit(f"Session sensor: {cfg.name} - {cfg.describe_sources()}")

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
                self.window, "Restore defaults",
                f"Replace '{self._cfg.name}' with the values StrikeWorks "
                "provides? Your edits to it are lost.") \
                != QMessageBox.StandardButton.Yes:
            return
        self._cfg = sensor_config.reset_to_builtin(key).copy()
        self._dirty = False
        self._reload_list(key)
        self._load_into_widgets()
        self._emit(f"{self._cfg.name} restored to its default values.")

    def _new(self):
        name, ok = QInputDialog.getText(
            self.window, "New sensor configuration", "Sensor name:")
        if not ok or not name.strip():
            return
        if self._dirty and not self._confirm_discard():
            return
        cfg = sensor_config.SensorConfig(
            key=sensor_config.unique_key(name), name=name.strip())
        cfg.description = "New configuration - review every field below."
        cfg.sources = [sensor_config.SensorSource(
            extension="", packet_size=0, native_rate_hz=2000.0,
            method="linear")]
        sensor_config.upsert(cfg)
        self._cfg = cfg.copy()
        self._dirty = False
        self._reload_list(cfg.key)
        self._load_into_widgets()
        self._emit(f"Created sensor configuration '{cfg.name}'.")

    def _duplicate(self):
        source = self._collect()
        name = f"{source.name} copy"
        cfg = source.copy(key=sensor_config.unique_key(name), name=name)
        sensor_config.upsert(cfg)
        self._cfg = cfg
        self._dirty = False
        self._reload_list(cfg.key)
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
