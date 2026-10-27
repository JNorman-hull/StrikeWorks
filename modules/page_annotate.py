# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Validate and annotate (Development toolkit), and StrikeWorks's Validate
step - the same page in both (`for_strikeworks`): the validation screen
(sensor_validation.ValidationView) with the library's Deployment /
Treatment / Run filters above its sensor list and an "Annotations and
notes" window. Only the saving differs: in StrikeWorks, Save + Next doesn't
add to the running dataset and Save and export doesn't ask first - the
step's Next continues with the export instead (page_simple_mode.py).

A sensor's deployment and treatment are the folders its raw file sits in,
`raw_sens_data/<deployment>/<treatment>/[Run n/]`, which need not match a
planned deployment; a missing level shows as "(ungrouped)". Video is
`<treatment>/VIDEO/<stem>_vid_*.mp4`, matched case-insensitively.

The Annotations and notes window stays open beside the main one and
follows the sensor shown. Save + Next saves what's in it with the window,
and adds the sensor's window to the library's running dataset,
`processed_sens_data/model_features.csv` (`dataset_build.standardise`),
replacing its block if it's already there; opening a library reads that
file back, so review resumes where it stopped. Annotations are optional
per sensor ("No annotations for this sensor"). "Save annotations" saves
them without moving on; "Import annotations CSV…" stamps a spreadsheet of
annotations onto the index.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from . import annotation_schema as asch
from . import deployment_index as di
from . import sensor_config, settings
from . import raw_layout
from . import validation_core as vc
from .annotation_widgets import AnnotationValueEditor, VariableListDialog
from .cards import MetaCard
from .dataset_build import META_COLS, standardise
from .inventory_widgets import notifier as inventory_notifier
from .layout import discard_widget, Page, scroll_page, Section, when_visible
from .library_widgets import LibrarySelector
from .sensor_validation import ValidationView
from .theme import muted_label, style

_BAD_SENS_COL = di.BAD_SENS_COL
_NOTES_COL = "notes"


class AnnotationsWindow(QDialog):
    """The shown sensor's annotations and notes, in a window of their own
    (a dialog that doesn't block - shown, not exec'd) that stays open
    beside the main one and follows the sensor shown."""

    def __init__(self, page):
        super().__init__(page.main_window)
        self.page = page
        self.setWindowTitle("Annotations and notes")
        self._stem = None
        self._editors = {}
        self._build()
        asch.notifier.changed.connect(self._rebuild)
        self._rebuild()
        self.set_sensor(None)
        self.resize(460, 620)
        # it belongs to the page: gone when the page is (another page, or
        # the window closed or minimised)
        page.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.page and event.type() == QEvent.Type.Hide:
            self.hide()
        return super().eventFilter(obj, event)

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        self.lbl_sensor = QLabel("")
        style(self.lbl_sensor, role="heading")
        v.addWidget(self.lbl_sensor)

        grp = Section("Annotations")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)
        self.annotation_grid = QGridLayout()
        self.annotation_grid.setVerticalSpacing(6)
        self.annotation_grid.setColumnStretch(1, 1)
        gv.addLayout(self.annotation_grid)
        # the position annotations (annotation_schema's "position" group),
        # shown while ticked
        self.chk_position = QCheckBox("Position annotations")
        self.chk_position.setToolTip(
            "Where on the eel the blade struck, and the eel's orientation "
            "just before the strike.")
        self.chk_position.setChecked(asch.show_position())
        self.chk_position.toggled.connect(self._on_position_toggled)
        gv.addWidget(self.chk_position)
        self.position_box = QWidget()
        self.position_grid = QGridLayout(self.position_box)
        self.position_grid.setContentsMargins(0, 0, 0, 0)
        self.position_grid.setVerticalSpacing(6)
        self.position_grid.setColumnStretch(1, 1)
        self.position_box.setVisible(self.chk_position.isChecked())
        gv.addWidget(self.position_box)
        self.chk_no_annotations = QCheckBox("No annotations for this sensor")
        gv.addWidget(self.chk_no_annotations)
        v.addWidget(grp)

        notes = Section("Notes")
        nv = QVBoxLayout(notes)
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.setPlaceholderText("Free-text notes for this sensor…")
        nv.addWidget(self.txt_notes)
        v.addWidget(notes, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Save annotations")
        self.btn_save.setToolTip(
            "Save this sensor's annotations and notes and stay on it - Save "
            "+ Next saves them too, with the sensor's window.")
        self.btn_save.clicked.connect(self._save)
        btn_row.addWidget(self.btn_save)
        btn_manage = QPushButton("Manage variables…")
        btn_manage.clicked.connect(lambda: VariableListDialog(self).exec())
        btn_row.addWidget(btn_manage)
        btn_import = QPushButton("Import annotations CSV…")
        btn_import.setToolTip(
            "Stamp a spreadsheet of per-sensor annotations (a 'file' column "
            "plus annotation columns) onto this library's sensors.")
        btn_import.clicked.connect(lambda: self.import_csv())
        btn_row.addWidget(btn_import)
        btn_row.addStretch()
        v.addLayout(btn_row)
        # no Enter-key default button: Enter in a dropdown mustn't save
        for btn in (self.btn_save, btn_manage, btn_import):
            btn.setAutoDefault(False)

        self.lbl_status = QLabel("")
        style(self.lbl_status, role="muted")
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)

    def _rebuild(self):
        for grid in (self.annotation_grid, self.position_grid):
            while grid.count():
                item = grid.takeAt(0)
                if item.widget() is not None:
                    discard_widget(item.widget())
        self._editors = {}
        position = asch.all_variables(asch.POSITION_GROUP)
        main = [v for v in asch.all_variables() if v not in position]
        for grid, variables in ((self.annotation_grid, main),
                                (self.position_grid, position)):
            for row, var in enumerate(variables):
                editor = AnnotationValueEditor(var.name)
                grid.addWidget(muted_label(var.label), row, 0)
                grid.addWidget(editor, row, 1)
                self._editors[var.name] = editor
        # nothing to show once the position variables have been removed
        self.chk_position.setVisible(bool(position))
        self.position_box.setVisible(bool(position)
                                     and self.chk_position.isChecked())
        self.set_sensor(self._stem)

    def _on_position_toggled(self, on):
        self.position_box.setVisible(on)
        asch.set_show_position(on)

    # ── the sensor shown ─────────────────────────────────────────────────────
    def set_sensor(self, stem):
        """Show `stem`'s annotations and notes from the index (None: none)."""
        from .ml_train_state import level_key
        self._stem = stem
        self.lbl_sensor.setText(stem or "No sensor loaded")
        self.btn_save.setEnabled(bool(stem))
        row = self.page.index_row(stem) if stem else None
        for name, editor in self._editors.items():
            value = row.get(name, "") if row is not None else ""
            editor.set_current("" if pd.isna(value) else level_key(value))
        self.chk_no_annotations.setChecked(False)
        notes = row.get(_NOTES_COL, "") if row is not None else ""
        self.txt_notes.setPlainText("" if pd.isna(notes) else str(notes))

    def values(self):
        return {name: editor.current() for name, editor in self._editors.items()}

    def annotated(self):
        """Anything to save: a value, a note, or "No annotations" ticked."""
        return (any(self.values().values())
                or bool(self.txt_notes.toPlainText().strip())
                or self.chk_no_annotations.isChecked())

    def save_values(self, _stem=None):
        """The index columns Save + Next writes: the notes and the values
        entered - nothing without annotations (no empty ones written)."""
        if not self.annotated():
            return {}
        out = {_NOTES_COL: self.txt_notes.toPlainText().strip()}
        out.update({name: value for name, value in self.values().items() if value})
        return out

    def _save(self):
        """Save annotations: the values and notes only - no window saved,
        no dataset entry, no move to the next sensor."""
        lib = self.page.lib_root
        if not self._stem or lib is None:
            return
        if not self.annotated():
            QMessageBox.warning(
                self, "Nothing to save",
                "Enter at least one annotation value or a note, or tick "
                "\"No annotations for this sensor\" to save without any.")
            return
        try:
            di.set_row_values(lib, self._stem, self.save_values())
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))
            return
        self.page.reload()
        message = f"Saved annotations for {self._stem}."
        self.lbl_status.setText(message)
        self.page.status.emit(message, 4000)

    def import_csv(self, path=None):
        """`path` skips the file picker (demo runner). Returns how many
        sensors it stamped."""
        lib = self.page.lib_root
        if lib is None:
            return 0
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import annotations CSV", str(lib), "CSV files (*.csv)")
            if not path:
                return 0
        try:
            n, names = vc.import_annotations_csv(lib, path)
        except Exception as e:
            QMessageBox.warning(self, "Import failed", str(e))
            return 0
        self.page.reload()
        self.set_sensor(self._stem)
        message = (f"Imported {', '.join(names)} for {n} sensor(s) from "
                   f"{Path(path).name}.")
        self.lbl_status.setText(message)
        self.page.status.emit(message, 6000)
        return n

    def bring_up(self):
        self.show()
        self.raise_()
        self.activateWindow()


class AnnotationPage(Page):
    """Validate and annotate > Annotate - and, `for_strikeworks`, StrikeWorks's
    Validate step (`main_window` is then the StrikeWorks window, which sets
    `view.export_name` and takes the export from `view.export_done`)."""

    def __init__(self, main_window, session_state=None, for_strikeworks=False):
        super().__init__(main_window)
        self.session_state = session_state
        self.for_strikeworks = for_strikeworks
        self._index_df = None
        self._dataset_stems = set()

        self.lib_selector = LibrarySelector(session_state)
        self.annotations = AnnotationsWindow(self)
        btn_annotations = QPushButton("Annotations and notes")
        btn_annotations.setToolTip("This sensor's annotations and notes, in a "
                                   "window that stays open and follows it.")
        btn_annotations.clicked.connect(self.annotations.bring_up)
        self.view = ValidationView(main_window, top=self.lib_selector,
                                   extra_buttons=(btn_annotations,),
                                   confirm_export=not for_strikeworks)
        self.view.save_values = self.annotations.save_values
        self.view.counts_suffix = self._counts_suffix
        if for_strikeworks:
            self.view.btn_save_next.setToolTip(
                f"Save + Next ({vc.SAVE_NEXT_KEYS}) records your review of "
                "this sensor's window - clearing its flag - with any "
                "annotations or notes in the Annotations and notes window, "
                "and moves on to the next sensor in the list.")
        else:
            self.view.after_save = self._after_save
            self.view.export_name = self._export_name
            self.view.btn_save_next.setToolTip(
                f"Save + Next ({vc.SAVE_NEXT_KEYS}) records your review of "
                "this sensor's window - clearing its flag - with any "
                "annotations or notes in the Annotations and notes window, "
                "adds the window to the dataset when it's annotated, and "
                "moves on to the next sensor in the list.")

        self._build(self)
        self._connect()
        self._on_lib_changed()
        self._populate_sensor_table()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        # no frame round the one tab shown
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs)

        tab_annotate = QWidget()
        tv = QVBoxLayout(tab_annotate)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(self.view)
        self.tabs.addTab(tab_annotate, "Annotate")

        tab_report = QWidget()
        self._build_reporting_tab(tab_report)
        self.tabs.addTab(tab_report, "Reporting")
        # hidden for now - its summary still feeds the central report
        # (report_center.annotation_section); with one tab left, no tab bar
        self.tabs.setTabVisible(self.tabs.indexOf(tab_report), False)
        self.tabs.tabBar().setVisible(False)

    def _build_reporting_tab(self, frame):
        v = scroll_page(frame)
        grp_sum = Section("Annotation summary")
        sv = QVBoxLayout(grp_sum)
        self.card_report = MetaCard("Library")
        sv.addWidget(self.card_report)
        v.addWidget(grp_sum)

        grp_vars = Section("By annotation variable")
        vv = QVBoxLayout(grp_vars)
        self.tbl_report_vars = QTableWidget(0, 3)
        self.tbl_report_vars.setHorizontalHeaderLabels(
            ["Variable", "Value", "Count"])
        self.tbl_report_vars.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_report_vars.setMinimumHeight(180)
        vv.addWidget(self.tbl_report_vars)
        v.addWidget(grp_vars, stretch=1)

        grp_gen = Section("Dataset report")
        gv = QVBoxLayout(grp_gen)
        self.lbl_report_status = QLabel("")
        style(self.lbl_report_status, role="muted")
        self.lbl_report_status.setWordWrap(True)
        gv.addWidget(self.lbl_report_status)
        self.btn_generate_report = QPushButton("Generate dataset report")
        self.btn_generate_report.setMinimumHeight(30)
        style(self.btn_generate_report, role="primary")
        self.btn_generate_report.clicked.connect(self._generate_report)
        gv.addWidget(self.btn_generate_report)
        v.addWidget(grp_gen)
        v.addStretch()

    def _connect(self):
        self.lib_selector.library_changed.connect(self._on_lib_changed)
        self.lib_selector.filters_changed.connect(self._populate_sensor_table)
        self.view.status.connect(self.status)
        self.view.sensor_loaded.connect(self.annotations.set_sensor)
        self.view.index_changed.connect(self._load_index)
        self.view.export_done.connect(self._on_export_done)
        inventory_notifier.processed.connect(self._on_library_processed)

    # ── the library ──────────────────────────────────────────────────────────
    @property
    def lib_root(self):
        return self.lib_selector.lib_root

    # report_center.annotation_section reads these
    @property
    def _lib_root(self):
        return self.lib_selector.lib_root

    def _on_lib_changed(self):
        self._load_index()
        self._load_dataset_stems()
        if self.lib_root and not self.lib_selector.syncing:
            self.status.emit(f"Library: {self.lib_root.name}", 4000)

    def _load_index(self):
        self._index_df = di.read_index(self.lib_root) if self.lib_root else None

    def index_row(self, stem):
        """`stem`'s row of the library's sensor index, or None."""
        df = self._index_df
        if df is None or "file" not in df.columns:
            return None
        match = df[df["file"].astype(str) == str(stem)]
        return match.iloc[0] if len(match) else None

    def refresh(self):
        """Re-read the index and re-list the sensors (Process may have just
        added some)."""
        self._load_index()
        self._populate_sensor_table()

    def reload(self):
        """The index changed here (annotations saved or imported)."""
        self.view.index_changed.emit()      # tells the host; reloads it here
        self._populate_sensor_table()

    # ── the running dataset (resume support) ─────────────────────────────────
    def _dataset_path(self):
        return self.lib_root / raw_layout.DATASET_REL

    def _load_dataset_stems(self):
        self._dataset_stems = set()
        if self.lib_root is None:
            return
        path = self._dataset_path()
        if not path.exists():
            return
        try:
            df = pd.read_csv(path, usecols=["file"], low_memory=False)
            self._dataset_stems = set(df["file"].astype(str).unique())
        except (OSError, ValueError) as e:
            self.status.emit(f"Could not read the running dataset: {e}", 6000)

    # ── the sensors listed ───────────────────────────────────────────────────
    def _populate_sensor_table(self):
        files = self.lib_selector.list_sensor_csvs() if self.lib_root else []
        self.view.set_source(self.lib_root, files,
                             video_lookup=self.lib_selector.video_matches_for,
                             export_all=False)
        self._refresh_report()

    def _counts_suffix(self, stems):
        n = sum(1 for s in stems if s in self._dataset_stems)
        return f"In dataset: {n}/{len(stems)}"

    def _export_name(self):
        dep = self.lib_selector.wanted_deployment()
        return self.lib_root.name + (f"_{dep}" if dep else "")

    # ── Save + Next's own step: annotations into the running dataset ─────────
    def _after_save(self, stem, window):
        """With annotations entered, the sensor's window joins the running
        dataset (replacing its block if it's there already); without, Save +
        Next was just the review."""
        self._load_index()
        if not self.annotations.annotated():
            return f"Reviewed {stem} (no annotations entered)."
        target_rows = sensor_config.active().window_samples(self.view.win_sec)
        block = standardise(window, target_rows)
        if block is None:
            raise ValueError(
                f"Only {len(window)} rows in the window (expected "
                f"~{target_rows}) - too far from the sensor's boundary.")
        block = block.copy()
        block.insert(0, "file", stem)
        meta = self.index_row(stem)
        at = 1
        for col in META_COLS:
            if self._index_df is not None and col in self._index_df.columns:
                block.insert(at, col, meta.get(col, "") if meta is not None else "")
                at += 1
        for name, value in self.annotations.values().items():
            block[name] = value
        vc.merge_into_running_dataset(self.lib_root, block)
        self._dataset_stems.add(stem)
        return f"Saved {stem} ({len(self._dataset_stems)} in dataset)."

    def _on_export_done(self, df, path, _message):
        if df is None:
            return
        # (StrikeWorks takes its export on itself - _on_extract_done)
        if not self.for_strikeworks:
            settings.add_recent_training_dataset(path)
            self.main_window.ml_prediction_page.on_dataset_ready(
                df, f"Annotate - {path.stem}")
        self._load_dataset_stems()
        self._populate_sensor_table()

    def _on_library_processed(self, root):
        """A processing batch just finished somewhere (Raw data processing
        or StrikeWorks) - pick up its new sensors if it was this library."""
        if self.lib_root is not None and Path(root) == Path(self.lib_root):
            # a rescan re-emits library_changed, which reloads the index and
            # dataset stems too - deferred until this page is looked at
            when_visible(self.lib_selector, self.lib_selector.rescan, key="scan")

    # ── reporting tab (hidden; the central report reads it) ──────────────────
    def _library_sensor_rows(self):
        """Every sensor index row for the whole library, plan rows dropped -
        the summary is of the library, not the current filters."""
        if self._index_df is None:
            return None
        return di.sensor_rows(self._index_df)

    def _variable_value_counts(self, df):
        """[(variable label, value, count), ...] across every annotated
        sensor row, one group per variable - numeric levels (concentric
        pump region) in their own order (1, 2, 3...), anything else most
        common value first."""
        from .ml_train_state import level_key
        rows = []
        for var in asch.all_variables():
            if var.name not in df.columns:
                continue
            values = df[var.name].astype(str).str.strip()
            values = values[values.astype(bool) & (values.str.lower() != "nan")]
            # a numeric-looking annotation column (e.g. concentric_pump_region)
            # round-trips through the index CSV as float ("2.0") - normalise
            # as the training pipeline does (level_key)
            values = values.map(level_key)
            counts = list(values.value_counts().items())
            try:
                counts.sort(key=lambda vc_: float(vc_[0]))
            except ValueError:
                pass   # text levels - keep most common first
            for value, count in counts:
                rows.append((var.label, value, int(count)))
        return rows

    def _review_rows(self, df):
        stems = [str(s) for s in df["file"]] if df is not None and "file" in df.columns else []
        return vc.processing_review_rows(stems, self._index_df)

    def _bad_count(self, df):
        if _BAD_SENS_COL not in df.columns:
            return 0
        return int((df[_BAD_SENS_COL].astype(str).str.strip().str.upper() == "Y").sum())

    def _refresh_report(self):
        df = self._library_sensor_rows()
        if self.lib_root is None or df is None:
            self.card_report.set_title("Library")
            self.card_report.set_rows([])
            self.tbl_report_vars.setRowCount(0)
            self.lbl_report_status.setText(
                "Open a library to see its annotation summary.")
            return
        total = len(df)
        in_dataset = len(self._dataset_stems)
        self.card_report.set_title(f"Library: {self.lib_root.name}")
        self.card_report.set_rows([
            ("Sensors in index", total or None),
            ("In dataset (annotated + saved)", in_dataset or None),
            ("Not yet in dataset", (total - in_dataset) or None),
            ("Flagged bad", self._bad_count(df) or None),
        ] + self._review_rows(df))
        rows = self._variable_value_counts(df)
        self.tbl_report_vars.setRowCount(len(rows))
        for r, (label, value, count) in enumerate(rows):
            self.tbl_report_vars.setItem(r, 0, QTableWidgetItem(label))
            self.tbl_report_vars.setItem(r, 1, QTableWidgetItem(str(value)))
            item = QTableWidgetItem(str(count))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_report_vars.setItem(r, 2, item)
        self.tbl_report_vars.resizeColumnsToContents()
        self.lbl_report_status.setText(
            f"{in_dataset} of {total} sensor(s) in the dataset. Updates "
            "live as you annotate.")
        style(self.lbl_report_status, role="muted")

    def _generate_report(self):
        df = self._library_sensor_rows()
        if self.lib_root is None or df is None:
            return
        total = len(df)
        in_dataset = len(self._dataset_stems)
        lines = [
            f"# Annotation report - {self.lib_root.name}", "",
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
            "## Summary", "",
            f"- Sensors in index: {total}",
            f"- In dataset (annotated + saved): {in_dataset}",
            f"- Not yet in dataset: {total - in_dataset}",
            f"- Flagged bad: {self._bad_count(df)}", "",
            "## Validation", "",
        ]
        review = self._review_rows(df)
        lines += ([f"- {label}: {value}" for label, value in review]
                  or ["No sensors validated yet."])
        lines += ["", "## By annotation variable", ""]
        by_var = {}
        for label, value, count in self._variable_value_counts(df):
            by_var.setdefault(label, []).append((value, count))
        if by_var:
            for label, values in by_var.items():
                lines += [f"### {label}", ""]
                lines += [f"- {value}: {count}" for value, count in values]
                lines.append("")
        else:
            lines.append("No annotation values recorded yet.")
        out_path = self.lib_root / raw_layout.PROCESSED_DIR / "annotation_report.md"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("\n".join(lines))
        except Exception as e:
            QMessageBox.critical(self.main_window, "Report failed", str(e))
            return
        self.lbl_report_status.setText(f"Report written to {out_path}")
        style(self.lbl_report_status, tone="ok")
        self.status.emit(f"Dataset report saved to {out_path}", 5000)
