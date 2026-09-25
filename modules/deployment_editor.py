# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The deployment editor - one widget shared by Simple mode's Deploy step
and Advanced mode's Create and edit deployment page, so both build and edit
deployments exactly the same way.

  Session library   - soft-synced to session_state like every other
                      picker, plus New library / New session (Home's own).
  Library status    - page_home.library_status_rows, the shared summary.
  Sensors           - every sensor configuration (edited on Setup and
                      deploy > Sensor configuration), RAPID by default. It
                      is recorded on the deployment's plan
                      (deployment_index.SENSOR_CONFIG_COL), so reopening a
                      deployment restores it.
  Deployment        - pick an existing deployment or "New deployment…",
                      and its site/ID/machine fields.
  Treatments        - one table row per treatment (conditions + number of
                      runs); a new deployment starts with "Treatment 1".

Create & open data folder - only for a deployment whose folder doesn't
exist yet: saves the plan and builds raw_sens_data/<deployment>/<treatment>/
Run 1..N/VIDEO/ for every treatment, then opens it in Explorer.

Update - once anything has changed: saves the plan and makes the folders
match it. A renamed deployment or treatment has its folder renamed and its
already-processed sensors relabelled (index and the library's running
dataset); changed conditions are re-stamped onto those sensors; a removed
treatment (or a run dropped from one) has its folder removed - after an
explicit "Remove folder and content" confirmation whenever it holds files.
No Explorer window.

Leaving with unsaved changes (the host's Next, or picking another
deployment) asks: Save and continue / Continue / Cancel -
`confirm_leave()`.
"""
import os
import shutil

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import raw_layout, sensor_config, settings
from .ml_widgets import ACCENT, MUTED, OK, WARN, MetaCard, Section, style_table

NEW_DEPLOYMENT = "__new__"
_TMP_SUFFIX = ".__renaming__"


class TreatmentTable(QTableWidget):
    """Editable table of treatments: one row per treatment, plain cells for
    the di.TREATMENT_FIELDS columns, a spin box for its number of runs, a
    Remove button. Each row remembers the treatment name it was loaded
    with (None for a row added since), which is how Update tells a rename
    from a remove-and-add."""

    changed = Signal()

    _RUNS_COL = len(di.TREATMENT_FIELDS)
    _REMOVE_COL = len(di.TREATMENT_FIELDS) + 1
    _NAME_COL = next(i for i, (c, _l) in enumerate(di.TREATMENT_FIELDS)
                     if c == di.TREATMENT_COL)

    def __init__(self, parent=None):
        headers = ([label for _c, label in di.TREATMENT_FIELDS]
                   + ["Number of runs", ""])
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        style_table(self)
        self.itemChanged.connect(lambda _i: self.changed.emit())

    def add_row(self, values=None, orig_name=None):
        values = values or {}
        row = self.rowCount()
        self.blockSignals(True)
        self.insertRow(row)
        for col, (column, _label) in enumerate(di.TREATMENT_FIELDS):
            item = QTableWidgetItem(str(values.get(column, "")))
            if col == self._NAME_COL:
                item.setData(Qt.ItemDataRole.UserRole, orig_name)
            self.setItem(row, col, item)
        self.blockSignals(False)

        spin = QSpinBox()
        spin.setRange(1, di.MAX_RUNS)
        spin.setValue(int(values.get("runs", 1) or 1))
        spin.setToolTip("Each run gets its own folder (Run 1, Run 2, ...).")
        spin.valueChanged.connect(lambda _v: self.changed.emit())
        self.setCellWidget(row, self._RUNS_COL, spin)

        btn_remove = QPushButton("Remove")
        btn_remove.setToolTip("Remove this treatment")
        btn_remove.clicked.connect(lambda: self._remove_row_with_widget(btn_remove))
        self.setCellWidget(row, self._REMOVE_COL, btn_remove)

        self.resizeColumnsToContents()
        self.changed.emit()

    def _remove_row_with_widget(self, btn):
        for r in range(self.rowCount()):
            if self.cellWidget(r, self._REMOVE_COL) is btn:
                self.removeRow(r)
                self.changed.emit()
                return

    def row_values(self, row):
        out = {}
        for col, (column, _label) in enumerate(di.TREATMENT_FIELDS):
            item = self.item(row, col)
            out[column] = item.text().strip() if item is not None else ""
        spin = self.cellWidget(row, self._RUNS_COL)
        out["runs"] = spin.value() if spin is not None else 1
        return out

    def row_orig(self, row):
        item = self.item(row, self._NAME_COL)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def all_values(self):
        return [self.row_values(r) for r in range(self.rowCount())]

    def origs(self):
        return [self.row_orig(r) for r in range(self.rowCount())]

    def names(self):
        return [v[di.TREATMENT_COL] for v in self.all_values()]

    def clear_rows(self):
        self.setRowCount(0)


class DeploymentEditor(QWidget):
    """See module docstring. `window` is MainWindow (for Home's New
    library/New session and, optionally, navigating to Sensor
    configuration)."""

    saved = Signal(str)            # deployment ID just created/updated
    state_changed = Signal()       # dirty/valid state moved - hosts refresh
    status = Signal(str, int)

    def __init__(self, window, session_state, parent=None,
                 show_configure_link=False):
        super().__init__(parent)
        self._main = window
        self._session = session_state
        self._lib_root = session_state.library if session_state else None
        self._deployments = []
        self._loaded_ident = None      # None = a new, not-yet-created deployment
        self._snapshot = None
        self._loading = False
        self._combo_ident = None       # what cmb_deployment was last left on
        self._loaded_for = None        # the library the content was last loaded for
        self._build(show_configure_link)
        sensor_config.notifier.changed.connect(self._reload_sensor_list)
        if session_state is not None:
            session_state.library_changed.connect(self._on_session_library_changed)
        # no refresh here - showEvent does it, when (and every time) the
        # editor is actually looked at

    def showEvent(self, event):
        """Re-read the library every time the editor is shown - the
        deployments, treatments and status card go stale whenever the
        library's contents change somewhere else (the other mode's editor,
        processing, the demo). Unsaved edits to the same library are kept:
        then only the status card is refreshed."""
        super().showEvent(event)
        QTimer.singleShot(0, self._on_shown)

    def _on_shown(self):
        if not self.isVisible():
            return
        same_library = self._loaded_for == self._lib_root
        if same_library and self.has_unsaved():
            self._refresh_status_card()
        else:
            self.refresh()

    def ensure_loaded(self):
        """Load the current library's deployments if they haven't been for
        this library yet (the host needs deployment_dir() before the
        editor has ever been shown)."""
        if self._snapshot is None or self._loaded_for != self._lib_root:
            self.refresh()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, show_configure_link):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        grp_lib = Section("Session library")
        libv = QVBoxLayout(grp_lib)
        self.cmb_library = QComboBox()
        self.cmb_library.currentIndexChanged.connect(self._on_library_combo_changed)
        libv.addWidget(self.cmb_library)
        self.lbl_library_path = QLabel("No library selected.")
        self.lbl_library_path.setStyleSheet(f"color:{MUTED};")
        self.lbl_library_path.setWordWrap(True)
        libv.addWidget(self.lbl_library_path)
        lib_actions = QHBoxLayout()
        btn_new_library = QPushButton("New library")
        btn_new_library.setFlat(True)
        btn_new_library.setStyleSheet(f"color:{ACCENT};text-align:left;")
        btn_new_library.clicked.connect(
            lambda: self._main.home_page._new_library(parent=self.window()))
        lib_actions.addWidget(btn_new_library)
        lib_actions.addStretch()
        btn_new_session = QPushButton("New session")
        btn_new_session.setFlat(True)
        btn_new_session.setStyleSheet(f"color:{ACCENT};text-align:right;")
        btn_new_session.clicked.connect(
            lambda: self._main.home_page._new_session(parent=self.window()))
        lib_actions.addWidget(btn_new_session)
        libv.addLayout(lib_actions)
        lv.addWidget(grp_lib)

        grp_status = Section("Library status")
        sv = QVBoxLayout(grp_status)
        self.card_library_status = MetaCard("Nothing selected yet")
        sv.addWidget(self.card_library_status)
        lv.addWidget(grp_status)

        grp_sensor = Section("Sensors")
        sensv = QHBoxLayout(grp_sensor)
        self.cmb_sensor = QComboBox()
        self.cmb_sensor.setToolTip(
            "The sensor this deployment's recordings come from - saved with "
            "the deployment. Sensors themselves are set up on Setup and "
            "deploy > Sensor configuration.")
        self.cmb_sensor.currentIndexChanged.connect(self._on_sensor_changed)
        sensv.addWidget(self.cmb_sensor, stretch=1)
        if show_configure_link:
            btn_cfg = QPushButton("Configure…")
            btn_cfg.setToolTip("Open Setup and deploy > Sensor configuration")
            btn_cfg.clicked.connect(lambda: self._main.navigate_to("btn_prepare"))
            sensv.addWidget(btn_cfg)
        lv.addWidget(grp_sensor)
        self._reload_sensor_list()

        grp_dep = Section("Deployment")
        dv = QVBoxLayout(grp_dep)
        self.cmb_deployment = QComboBox()
        self.cmb_deployment.currentIndexChanged.connect(self._on_deployment_combo)
        dv.addWidget(self.cmb_deployment)
        form = QGridLayout()
        form.setColumnStretch(1, 1)
        self.dep_edits = {}
        for i, (column, label) in enumerate(di.DEPLOYMENT_FIELDS):
            form.addWidget(self._muted(label), i, 0)
            edit = QLineEdit()
            edit.textChanged.connect(self._on_edited)
            form.addWidget(edit, i, 1)
            self.dep_edits[column] = edit
        dv.addLayout(form)
        lv.addWidget(grp_dep)
        lv.addStretch()
        self._left = left
        self._grp_dep = grp_dep

        # the left column scrolls internally rather than forcing its host
        # window taller (four stacked sections)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        left_scroll.setWidget(left)
        row.addWidget(left_scroll, stretch=2)

        grp_tr = Section("Treatments")
        rv = QVBoxLayout(grp_tr)
        self.treatment_table = TreatmentTable()
        self.treatment_table.changed.connect(self._on_edited)
        rv.addWidget(self.treatment_table, stretch=1)
        add_row = QHBoxLayout()
        self.btn_add_treatment = QPushButton("+ Add treatment")
        self.btn_add_treatment.clicked.connect(lambda: self.add_treatment())
        add_row.addWidget(self.btn_add_treatment)
        add_row.addStretch()
        self.lbl_treatment_summary = QLabel("")
        self.lbl_treatment_summary.setStyleSheet(f"color:{MUTED};")
        add_row.addWidget(self.lbl_treatment_summary)
        rv.addLayout(add_row)

        # Create / Update live under the table (always in view), not at the
        # foot of the scrolling left column
        btn_row = QHBoxLayout()
        self.btn_create = QPushButton("Create && open\ndata folder")
        self.btn_create.setMinimumHeight(40)
        self.btn_create.setToolTip(
            "Save this deployment and build its folders - one per treatment, "
            "each with Run 1..N and a VIDEO folder per run - then open it in "
            "Explorer. Only for a deployment whose folder doesn't exist yet.")
        self.btn_create.clicked.connect(lambda: self.apply(open_folder=True))
        btn_row.addWidget(self.btn_create)
        self.btn_update = QPushButton("Update")
        self.btn_update.setMinimumHeight(40)
        self.btn_update.setToolTip(
            "Save changes to this deployment and make its folders match: "
            "renames carry the folder and already-processed sensors with "
            "them, removed treatments/runs remove their folders.")
        self.btn_update.clicked.connect(lambda: self.apply(open_folder=False))
        btn_row.addWidget(self.btn_update)
        btn_row.addStretch()
        rv.addLayout(btn_row)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        rv.addWidget(self.lbl_hint)
        self.lbl_files_found = QLabel("")
        self.lbl_files_found.setStyleSheet(f"color:{OK};")
        rv.addWidget(self.lbl_files_found)
        # the Treatments box ends where the left column's last box does
        # (_match_treatments_height) instead of running on down the page
        row.addWidget(grp_tr, stretch=3, alignment=Qt.AlignmentFlag.AlignTop)
        self._grp_tr = grp_tr
        left.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._left and event.type() in (QEvent.Type.Resize,
                                                  QEvent.Type.LayoutRequest):
            QTimer.singleShot(0, self._match_treatments_height)
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._match_treatments_height)

    def _match_treatments_height(self):
        """Treatments box: top level with the Session library box, bottom
        level with the Deployment box - never taller than the editor
        itself (a short window scrolls the left column), never shorter
        than its own table and buttons need."""
        if not self._grp_dep.isVisible():
            return
        bottom = self._grp_dep.mapTo(
            self, self._grp_dep.rect().bottomLeft()).y() + 1
        height = max(self._grp_tr.minimumSizeHint().height(),
                     min(bottom, self.height()))
        if self._grp_tr.height() != height or self._grp_tr.minimumHeight() != height:
            self._grp_tr.setFixedHeight(height)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        lab.setWordWrap(True)
        return lab

    # ── public ───────────────────────────────────────────────────────────────
    @property
    def lib_root(self):
        return self._lib_root

    def deployment_id(self):
        return self.dep_edits[di.DEPLOYMENT_COL].text().strip()

    def deployment_values(self):
        return {c: e.text().strip() for c, e in self.dep_edits.items()}

    def sensor_key(self):
        return self.cmb_sensor.currentData()

    def deployment_dir(self):
        ident = self.deployment_id()
        if self._lib_root is None or not ident:
            return None
        return raw_layout.deployment_dir(self._lib_root, ident)

    def refresh(self, select=None):
        """Re-read the libraries, the session library's status and its
        deployments - keeps the current deployment selected if it still
        exists (unless `select` names another)."""
        self._lib_root = self._session.library if self._session else self._lib_root
        self._refresh_library_combo()
        self._refresh_status_card()
        self._load_deployments(select=select if select is not None
                               else self._loaded_ident)
        self._loaded_for = self._lib_root

    def select_deployment(self, ident):
        """Programmatic pick (demo runner): an existing deployment by ID,
        or NEW_DEPLOYMENT."""
        idx = self.cmb_deployment.findData(ident)
        if idx < 0:
            idx = self.cmb_deployment.findData(NEW_DEPLOYMENT)
        self._loading = True
        self.cmb_deployment.setCurrentIndex(idx)
        self._loading = False
        self._show_deployment(self.cmb_deployment.currentData())

    def set_sensor(self, key):
        idx = self.cmb_sensor.findData(key)
        if idx >= 0:
            self.cmb_sensor.setCurrentIndex(idx)

    def has_unsaved(self):
        return self._snapshot is not None and self._state() != self._snapshot

    def confirm_leave(self, parent=None):
        """True = go ahead (nothing unsaved, saved, or the user chose
        Continue); False = stay. Save and continue saves without opening
        Explorer."""
        if not self.has_unsaved():
            return True
        box = QMessageBox(parent or self.window())
        box.setWindowTitle("Unsaved deployment or treatment conditions")
        box.setText("The deployment or its treatment conditions have "
                    "changes that haven't been saved.")
        btn_save = box.addButton("Save and continue",
                                 QMessageBox.ButtonRole.AcceptRole)
        btn_continue = box.addButton("Continue",
                                     QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_save:
            return self.apply(open_folder=False)
        return clicked is btn_continue

    # ── session library ──────────────────────────────────────────────────────
    def _refresh_library_combo(self):
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        for lib in settings.list_libraries():
            self.cmb_library.addItem(lib.name, str(lib))
        idx = self.cmb_library.findData(str(self._lib_root)) if self._lib_root else -1
        if idx < 0 and self._lib_root is not None:
            self.cmb_library.addItem(self._lib_root.name, str(self._lib_root))
            idx = self.cmb_library.count() - 1
        self.cmb_library.setCurrentIndex(idx)
        self.cmb_library.blockSignals(False)
        self.lbl_library_path.setText(
            str(self._lib_root) if self._lib_root else "No library selected.")

    def _refresh_status_card(self):
        from .page_home import library_status_rows
        title, rows = library_status_rows(self._lib_root, self._session)
        self.card_library_status.set_title(title)
        self.card_library_status.set_rows(rows)

    def _on_library_combo_changed(self, _idx):
        if self._session is not None:
            self._session.set_library(self.cmb_library.currentData())

    def _on_session_library_changed(self, path):
        self._lib_root = path
        self._loaded_ident = None
        # only if on screen - otherwise showEvent loads it when next shown
        if self.isVisible():
            self.refresh()

    # ── sensors ──────────────────────────────────────────────────────────────
    def _reload_sensor_list(self, *_args):
        current = self.cmb_sensor.currentData() or sensor_config.DEFAULT_KEY
        self.cmb_sensor.blockSignals(True)
        self.cmb_sensor.clear()
        for cfg in sensor_config.all_configs():
            self.cmb_sensor.addItem(cfg.name, cfg.key)
        idx = self.cmb_sensor.findData(current)
        self.cmb_sensor.setCurrentIndex(max(idx, 0))
        self.cmb_sensor.blockSignals(False)

    def _on_sensor_changed(self, *_args):
        key = self.cmb_sensor.currentData()
        if key and not self._loading and key != sensor_config.active_key():
            sensor_config.set_active(key)
        self._on_edited()

    def _show_sensor(self, key):
        idx = self.cmb_sensor.findData(key or sensor_config.DEFAULT_KEY)
        if idx < 0:
            idx = self.cmb_sensor.findData(sensor_config.DEFAULT_KEY)
        self.cmb_sensor.blockSignals(True)
        self.cmb_sensor.setCurrentIndex(max(idx, 0))
        self.cmb_sensor.blockSignals(False)

    # ── deployments ──────────────────────────────────────────────────────────
    def _all_deployments(self):
        """Planned deployments plus any that only exist as a folder."""
        if self._lib_root is None:
            return []
        indexed = di.deployments(self._lib_root)
        ids = {d.get(di.DEPLOYMENT_COL, "") for d in indexed}
        raw_dir = raw_layout.raw_root(self._lib_root)
        on_disk = []
        if raw_dir.exists():
            for entry in sorted(raw_dir.iterdir()):
                if entry.is_dir() and entry.name not in ids:
                    on_disk.append({di.DEPLOYMENT_COL: entry.name})
        return indexed + on_disk

    def _load_deployments(self, select=None):
        self._loading = True
        self.cmb_deployment.clear()
        self._deployments = self._all_deployments()
        for dep in self._deployments:
            self.cmb_deployment.addItem(
                di.describe_deployment(dep), dep.get(di.DEPLOYMENT_COL, ""))
        self.cmb_deployment.addItem("New deployment…", NEW_DEPLOYMENT)
        idx = self.cmb_deployment.findData(select) if select else 0
        self.cmb_deployment.setCurrentIndex(max(0, idx))
        self._loading = False
        self._show_deployment(self.cmb_deployment.currentData())

    def _on_deployment_combo(self, *_args):
        if self._loading:
            return
        wanted = self.cmb_deployment.currentData()
        # put the combo back on what's actually loaded while asking - if
        # the user saves, that reloads the combo; either way the switch
        # happens below only once they've agreed to leave
        self._loading = True
        self.cmb_deployment.setCurrentIndex(
            max(0, self.cmb_deployment.findData(self._combo_ident)))
        self._loading = False
        if not self.confirm_leave():
            return
        self.select_deployment(wanted)
        key = self.cmb_sensor.currentData()
        if key and key != sensor_config.active_key():
            sensor_config.set_active(key)

    def _show_deployment(self, ident):
        self._loading = True
        self._combo_ident = ident
        self.treatment_table.clear_rows()
        if ident is None or ident == NEW_DEPLOYMENT:
            self._loaded_ident = None
            for edit in self.dep_edits.values():
                edit.setText("")
            self._show_sensor(sensor_config.DEFAULT_KEY)
            self.add_treatment()
        else:
            self._loaded_ident = ident
            dep = next((d for d in self._deployments
                        if d.get(di.DEPLOYMENT_COL, "") == ident), {})
            for column, edit in self.dep_edits.items():
                edit.setText(dep.get(column, "") or (ident if column == di.DEPLOYMENT_COL else ""))
            self._show_sensor(dep.get(di.SENSOR_CONFIG_COL))
            planned = di.treatments(self._lib_root, ident)
            if planned:
                for t in planned:
                    self.treatment_table.add_row(t, orig_name=t.get(di.TREATMENT_COL))
            else:
                for name, runs in self._treatments_on_disk(ident):
                    self.treatment_table.add_row(
                        {di.TREATMENT_COL: name, "runs": runs}, orig_name=name)
                if not self.treatment_table.rowCount():
                    self.add_treatment()
        self._loading = False
        self._snapshot = self._state()
        self._refresh_state()
        self._refresh_files_found()

    def _treatments_on_disk(self, ident):
        """(name, run count) for each treatment folder of a deployment that
        has no saved plan yet - a folder with no Run subfolders is 1 run."""
        dep_dir = raw_layout.deployment_dir(self._lib_root, ident)
        out = []
        if dep_dir.exists():
            for entry in sorted(dep_dir.iterdir()):
                if not entry.is_dir() or raw_layout.is_video_dir(entry.name):
                    continue
                runs = [int(raw_layout.run_label(p.name))
                        for p in entry.iterdir()
                        if p.is_dir() and raw_layout.run_label(p.name)]
                out.append((entry.name, max(runs) if runs else 1))
        return out

    # ── treatments ───────────────────────────────────────────────────────────
    def add_treatment(self, values=None):
        """A new row - a copy of the last row's conditions under the next
        free "Treatment N" name, unless `values` are given."""
        if values is None:
            existing = self.treatment_table.all_values()
            values = dict(existing[-1]) if existing else {}
            used = set(self.treatment_table.names())
            n = self.treatment_table.rowCount() + 1
            while f"Treatment {n}" in used:
                n += 1
            values[di.TREATMENT_COL] = f"Treatment {n}"
        self.treatment_table.add_row(values)

    def upsert_treatment(self, values):
        """Set a treatment's conditions/runs by name - editing its existing
        row in place (so Update sees an edit, not a remove-and-add), or
        adding a row if there isn't one (demo runner)."""
        t = self.treatment_table
        name = values.get(di.TREATMENT_COL, "")
        for r in range(t.rowCount()):
            if t.row_values(r)[di.TREATMENT_COL] == name:
                for col, (column, _l) in enumerate(di.TREATMENT_FIELDS):
                    if column in values:
                        t.item(r, col).setText(str(values[column]))
                spin = t.cellWidget(r, t._RUNS_COL)
                if spin is not None and values.get("runs"):
                    spin.setValue(int(values["runs"]))
                return
        # a brand-new deployment starts with a placeholder "Treatment 1"
        # row nobody has named yet - reuse it rather than leave it behind
        if (t.rowCount() == 1 and t.row_orig(0) is None
                and t.row_values(0)[di.TREATMENT_COL] == "Treatment 1"
                and name != "Treatment 1"):
            t.clear_rows()
        t.add_row(values)

    # ── state ────────────────────────────────────────────────────────────────
    def _state(self):
        return (tuple(e.text().strip() for e in self.dep_edits.values()),
                self.cmb_sensor.currentData(),
                tuple((tuple(sorted(v.items())), o) for v, o in
                      zip(self.treatment_table.all_values(),
                          self.treatment_table.origs())))

    def _on_edited(self, *_args):
        if not self._loading:
            self._refresh_state()

    def _problems(self):
        out = []
        if self._lib_root is None:
            out.append("Select or create a library first.")
        ident = self.deployment_id()
        if not ident:
            out.append("The deployment needs an ID.")
        elif any(ch in ident for ch in '\\/:*?"<>|'):
            out.append("The deployment ID can't contain \\ / : * ? \" < > |")
        names = self.treatment_table.names()
        if not names:
            out.append("Add at least one treatment.")
        if any(not n for n in names):
            out.append("Every treatment needs a name.")
        if any(ch in n for n in names for ch in '\\/:*?"<>|'):
            out.append("Treatment names can't contain \\ / : * ? \" < > |")
        if len({n.lower() for n in names}) != len(names):
            out.append("Two treatments share a name.")
        return out

    def _refresh_state(self):
        problems = self._problems()
        ident = self.deployment_id()
        folder = self.deployment_dir()
        folder_exists = folder is not None and folder.exists()
        renaming_onto = (self._loaded_ident is not None and ident
                         and ident != self._loaded_ident and folder_exists)
        dirty = self.has_unsaved()

        loaded_folder_exists = (
            self._loaded_ident is not None and self._lib_root is not None
            and raw_layout.deployment_dir(self._lib_root, self._loaded_ident).exists())
        # Create is only for a deployment whose folder doesn't exist yet -
        # neither under its (possibly just edited) ID, nor, for one being
        # renamed, under the ID it was loaded with
        can_create = not problems and not folder_exists and not loaded_folder_exists
        # a deployment being created for the first time is Create's job;
        # Update is for one that already exists (planned or on disk)
        can_update = (not problems and dirty and self._loaded_ident is not None
                      and not renaming_onto)
        self.btn_create.setEnabled(can_create)
        self.btn_update.setEnabled(can_update)

        if problems and (dirty or self._loaded_ident is not None):
            self._set_hint("• " + "<br>• ".join(problems), WARN)
        elif renaming_onto or (self._loaded_ident is None and folder_exists):
            self._set_hint(f"A deployment folder called '{ident}' already "
                           "exists - pick it from the Deployment list to "
                           "edit it.", WARN)
        elif dirty and self._loaded_ident is not None:
            self._set_hint("Unsaved changes - press Update to save them.", WARN)
        elif self._loaded_ident is not None and not folder_exists:
            self._set_hint("Planned, but its folders haven't been built "
                           "yet - Create & open data folder builds them.", MUTED)
        else:
            self._set_hint("", MUTED)

        values = self.treatment_table.all_values()
        n_runs = sum(int(v.get("runs", 1) or 1) for v in values)
        self.lbl_treatment_summary.setText(
            f"{len(values)} treatment(s), {n_runs} run(s)" if values else "")
        self.state_changed.emit()

    def _set_hint(self, text, colour):
        self.lbl_hint.setText(text)
        self.lbl_hint.setStyleSheet(f"color:{colour};")

    def _refresh_files_found(self):
        """How many recordings the loaded deployment's folder holds - one
        walk, on load/save only (it used to run on every keystroke)."""
        folder = self.deployment_dir()
        if folder is None or not folder.exists():
            self.lbl_files_found.setText("")
            return
        cfg = sensor_config.active()
        primary = (cfg.required_extensions or [".imp"])[0].lower()
        tree = raw_layout.scan_tree(raw_layout.raw_root(self._lib_root), folder)
        n_files = sum(len(paths) for paths in tree.files.values())
        n_rec = sum(1 for paths in tree.files.values()
                    if any(p.suffix.lower() == primary for p in paths))
        self.lbl_files_found.setText(
            f"{n_rec} sensor recording(s) found in folder ({n_files} file(s))")

    # ── create / update ──────────────────────────────────────────────────────
    def apply(self, open_folder=False):
        """Create (`open_folder=True`) or Update - see module docstring.
        Returns True once saved."""
        problems = self._problems()
        if problems:
            QMessageBox.warning(self.window(), "Cannot save",
                                "\n".join(f"• {p}" for p in problems))
            return False
        root = self._lib_root
        raw = raw_layout.raw_root(root)
        new_id = self.deployment_id()
        old_id = self._loaded_ident
        values = self.treatment_table.all_values()
        origs = self.treatment_table.origs()
        cur_id = old_id or new_id
        cur_dep_dir = raw / cur_id

        if old_id is not None and old_id != new_id and (raw / new_id).exists():
            QMessageBox.warning(self.window(), "Deployment exists",
                                f"A deployment folder called '{new_id}' "
                                "already exists.")
            return False

        # what changes on disk: renames (by original name), removed
        # treatments, and runs dropped from a kept treatment
        renames = [(o, v[di.TREATMENT_COL]) for v, o in zip(values, origs)
                   if o and o != v[di.TREATMENT_COL]]
        snap_origs = {o for _v, o in (self._snapshot[2] if self._snapshot else ())
                      if o}
        kept = {o for o in origs if o}
        to_delete = [cur_dep_dir / o for o in sorted(snap_origs - kept)
                     if (cur_dep_dir / o).exists()]
        for v, o in zip(values, origs):
            if o:
                to_delete += raw_layout.extra_run_folders(
                    root, cur_id, o, v.get("runs", 1))
        away = {o for o, _n in renames}
        for o, n in renames:
            target = cur_dep_dir / n
            if target.exists() and n not in away and target not in to_delete:
                QMessageBox.warning(
                    self.window(), "Treatment exists",
                    f"Can't rename '{o}' to '{n}': a folder called '{n}' "
                    "already exists in this deployment.")
                return False

        with_content = [p for p in to_delete if raw_layout.has_files(p)]
        if with_content:
            lines = "\n".join(
                f"• {p.relative_to(raw)}  ({raw_layout.count_files(p)} file(s))"
                for p in with_content)
            box = QMessageBox(self.window())
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Remove folders")
            box.setText("These folders are no longer part of the deployment "
                        f"and still contain files:\n\n{lines}\n\n"
                        "Removing them deletes the folder and everything in "
                        "it. Already-processed data for these sensors is "
                        "kept.")
            btn_remove = box.addButton("Remove folder and content",
                                       QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is not btn_remove:
                return False

        sensor_key = self.sensor_key()
        created = []
        try:
            for p in to_delete:
                shutil.rmtree(p, ignore_errors=False)
            if old_id is not None and old_id != new_id:
                if cur_dep_dir.exists():
                    cur_dep_dir.rename(raw / new_id)
                di.rename_deployment(root, old_id, new_id)
            dep_dir = raw / new_id
            self._rename_treatments(root, new_id, dep_dir, renames)
            di.save_plan(root, self.deployment_values(), values,
                         sensor_key=sensor_key)
            for v in values:
                created += raw_layout.build_run_folders(
                    root, new_id, v[di.TREATMENT_COL], v.get("runs", 1))
            (dep_dir / raw_layout.README_NAME).write_text(
                raw_layout.README_TEXT, encoding="utf-8")
            n_restamped = di.restamp_deployment(root, new_id)
        except Exception as e:
            QMessageBox.critical(self.window(), "Could not save deployment",
                                 str(e))
            self.refresh(select=new_id if (raw / new_id).exists() else old_id)
            return False

        if sensor_key and sensor_key != sensor_config.active_key():
            sensor_config.set_active(sensor_key)
        self.refresh(select=new_id)
        what = "Created" if old_id is None else "Updated"
        msg = f"{what} deployment '{new_id}'"
        if n_restamped:
            msg += f" - {n_restamped} processed sensor(s) relabelled"
        self.status.emit(msg + ".", 5000)
        self.saved.emit(new_id)

        if open_folder:
            try:
                os.startfile(str(dep_dir))
            except Exception:
                pass
            QMessageBox.information(self.window(), "Deployment folder ready",
                                    raw_layout.README_TEXT)
        return True

    @staticmethod
    def _rename_treatments(root, dep_id, dep_dir, renames):
        """Two-phase (via a temporary name) so swapping two treatments'
        names works - folders and index labels alike."""
        staged = []
        for i, (old, new) in enumerate(renames):
            tmp = f"{old}{_TMP_SUFFIX}{i}"
            if (dep_dir / old).exists():
                (dep_dir / old).rename(dep_dir / tmp)
            di.rename_treatment(root, dep_id, old, tmp)
            staged.append((tmp, new))
        for tmp, new in staged:
            if (dep_dir / tmp).exists():
                (dep_dir / tmp).rename(dep_dir / new)
            di.rename_treatment(root, dep_id, tmp, new)
