# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for Create and edit deployment (Setup and deploy).

Object names (`page_initiate_deployment`, `btn_initiate_deployment`, this
module's filename) still say "initiate deployment" - that was this page's
working name before it absorbed Study design's planning form; renaming the
object graph for a label change isn't worth the main.ui/main.py churn (see
ROADMAP.md Chunk 5's "renames are text-only" note), so only the sidebar
button text says "Create and edit deployment" now.

One-stop shop for getting a deployment ready for fieldwork: pick or create
the library, describe the deployment (site, machine) and its treatments
(head, flow, BEP, RPM, runs - the same fields Study design's plan form used
to collect, now here instead), and "Save deployment plan" both writes that
plan into `global_sensor_index.csv` (via `deployment_index.save_plan`,
exactly what the old Study design tab did) *and* builds the
`raw_sens_data/<deployment>/<treatment>/VIDEO/` folder tree Annotate and
Process already expect - so once sensors and video come back from the
field, they only need dragging into the right folder. Saving is
idempotent: revisiting an existing deployment, or adding a new one, never
disturbs files already dropped into earlier folders.

Deliberately not the same "root + combo of existing subfolders" library
picker every other page uses (`page_annotate.py`, ...): this page's job
includes *creating* a library, not just picking among ones that already
exist, so a single native folder dialog - which lets the user browse
anywhere (any drive, a network path) and make a new folder inline, exactly
like Explorer - covers both create and select in one step.

A deployment can exist purely as a folder tree with no index plan yet (or
vice versa - an old library's sensors carry conditions but were never
planned here): `_all_deployments()` merges both so neither location loses
track of what the other already has.
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import settings
from .ml_widgets import (
    ACCENT, BORDER, CARD_BG, MUTED, OK, TEXT, WARN, MetaCard, Section,
    apply_section_defaults,
)
from .library_widgets import RAW_DIR as _RAW_DIR, VIDEO_FOLDER_NAME as _VIDEO_FOLDER_NAME

_NEW_DEPLOYMENT = "__new__"
_SUMMARY_NAME = "deployment_summary.txt"


class _TreatmentRow(QFrame):
    """One treatment: its name, the conditions it runs at, and its runs.

    Moved here from the retired `prepare_tab_study.py` - this page is now
    the only place a treatment's full conditions are entered.
    """

    def __init__(self, values=None, on_change=None, on_remove=None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("treatmentRow")
        self.setStyleSheet(
            f"#treatmentRow{{background-color:{CARD_BG};border-radius:6px;"
            f"border:1px solid {BORDER};}}"
            f"#treatmentRow QLineEdit, #treatmentRow QSpinBox"
            f"{{background-color:#1b1e23;border:1px solid {BORDER};"
            f"border-radius:4px;padding:3px 6px;color:{TEXT};}}"
            f"#treatmentRow QLineEdit:focus, #treatmentRow QSpinBox:focus"
            f"{{border:1px solid {ACCENT};}}"
            "#treatmentRow QSpinBox::up-button, "
            "#treatmentRow QSpinBox::down-button{width:14px;}"
            "#treatmentRow QSpinBox::up-arrow{"
            "image:none;border-left:3px solid transparent;"
            "border-right:3px solid transparent;border-bottom:4px solid "
            f"{TEXT};width:0;height:0;}}"
            "#treatmentRow QSpinBox::down-arrow{"
            "image:none;border-left:3px solid transparent;"
            "border-right:3px solid transparent;border-top:4px solid "
            f"{TEXT};width:0;height:0;}}")

        values = values or {}
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        self.edits = {}
        for col, (column, label) in enumerate(di.TREATMENT_FIELDS):
            grid.addWidget(self._caption(label), 0, col)
            edit = QLineEdit(str(values.get(column, "")))
            edit.setMinimumWidth(90)
            edit.setMaximumWidth(150 if column == di.TREATMENT_COL else 110)
            if on_change is not None:
                edit.textEdited.connect(lambda _t: on_change())
            grid.addWidget(edit, 1, col)
            self.edits[column] = edit

        runs_col = len(di.TREATMENT_FIELDS)
        grid.addWidget(self._caption("Number of runs"), 0, runs_col)
        self.spin_runs = QSpinBox()
        self.spin_runs.setRange(1, di.MAX_RUNS)
        self.spin_runs.setValue(int(values.get("runs", 1) or 1))
        self.spin_runs.setToolTip("Runs can be assigned during processing.")
        self.spin_runs.setMaximumWidth(80)
        if on_change is not None:
            self.spin_runs.valueChanged.connect(lambda _v: on_change())
        grid.addWidget(self.spin_runs, 1, runs_col)

        last = runs_col + 1
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setToolTip("Remove this treatment")
        if on_remove is not None:
            self.btn_remove.clicked.connect(lambda: on_remove(self))
        grid.addWidget(QLabel(""), 0, last)
        grid.addWidget(self.btn_remove, 1, last)
        grid.setColumnStretch(last, 1)

    @staticmethod
    def _caption(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};font-size:10px;border:none;")
        return lab

    def values(self):
        out = {c: e.text().strip() for c, e in self.edits.items()}
        out["runs"] = self.spin_runs.value()
        return out

    def name(self):
        return self.edits[di.TREATMENT_COL].text().strip()

    def runs(self):
        return self.spin_runs.value()


class InitiateDeploymentPage(QObject):
    """Binds Create and edit deployment to `ui.content_initiate_deployment`."""

    status = Signal(str, int)

    def __init__(self, ui, window):
        super().__init__(window)
        self.ui = ui
        self.window = window

        self._lib_root = None
        self._deployments = []
        self._rows = []
        self._loading = False

        self._build(ui.content_initiate_deployment)
        self._connect()
        self._refresh_state()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        v = QVBoxLayout(frame)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        grp_lib = Section("Library and deployment")
        lv = QVBoxLayout(grp_lib)
        lv.setSpacing(6)
        lib_row = QHBoxLayout()
        lib_row.setSpacing(6)
        self.lbl_library = QLabel("No library selected")
        self.lbl_library.setStyleSheet(f"color:{MUTED};")
        self.lbl_library.setWordWrap(True)
        lib_row.addWidget(self.lbl_library, stretch=1)
        self.btn_choose_library = QPushButton("Choose library…")
        self.btn_choose_library.setToolTip(
            "Browse to an existing library, or create a new folder for one "
            "- exactly like Windows Explorer.")
        lib_row.addWidget(self.btn_choose_library)
        lv.addLayout(lib_row)

        dep_row = QHBoxLayout()
        dep_row.setSpacing(6)
        dep_row.addWidget(self._muted("Deployment"))
        self.cmb_deployment = QComboBox()
        self.cmb_deployment.setMinimumWidth(160)
        dep_row.addWidget(self.cmb_deployment, stretch=1)
        lv.addLayout(dep_row)

        form = QGridLayout()
        form.setVerticalSpacing(6)
        form.setColumnStretch(1, 1)
        self.edits = {}
        for i, (column, label) in enumerate(di.DEPLOYMENT_FIELDS):
            form.addWidget(self._muted(label), i, 0)
            edit = QLineEdit()
            edit.textEdited.connect(self._refresh_state)
            form.addWidget(edit, i, 1)
            self.edits[column] = edit
        lv.addLayout(form)
        row1.addWidget(grp_lib, stretch=3)

        self.card_summary = MetaCard("Library")
        self.card_summary.setMinimumWidth(260)
        self.card_summary.setSizePolicy(QSizePolicy.Policy.Preferred,
                                        QSizePolicy.Policy.Expanding)
        row1.addWidget(self.card_summary, stretch=2)
        v.addLayout(row1)

        grp_tr = Section("Treatments")
        tv = QVBoxLayout(grp_tr)
        tv.setSpacing(6)
        self.rows_holder = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_holder)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        # a scroll area rather than letting the Section grow unbounded - a
        # deployment with many treatments (each carrying its own run count)
        # used to squash everything below it instead of scrolling
        rows_scroll = QScrollArea()
        rows_scroll.setWidgetResizable(True)
        rows_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        rows_scroll.setWidget(self.rows_holder)
        rows_scroll.setMinimumHeight(160)
        rows_scroll.setMaximumHeight(420)
        tv.addWidget(rows_scroll)
        add_row = QHBoxLayout()
        self.btn_add_treatment = QPushButton("+  Add treatment")
        self.btn_add_treatment.setMinimumHeight(28)
        add_row.addWidget(self.btn_add_treatment)
        add_row.addStretch()
        self.lbl_rows = QLabel("")
        self.lbl_rows.setStyleSheet(f"color:{MUTED};")
        add_row.addWidget(self.lbl_rows)
        tv.addLayout(add_row)
        v.addWidget(grp_tr)

        grp_save = Section("Save deployment plan")
        gv = QVBoxLayout(grp_save)
        gv.setSpacing(6)
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        gv.addWidget(self.lbl_state)
        self.btn_save = QPushButton("Save deployment plan")
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        gv.addWidget(self.btn_save)
        self.lbl_path = QLabel("")
        self.lbl_path.setStyleSheet(f"color:{MUTED};font-size:10px;")
        self.lbl_path.setWordWrap(True)
        gv.addWidget(self.lbl_path)
        v.addWidget(grp_save)

        v.addStretch()
        apply_section_defaults(frame)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    def _connect(self):
        self.btn_choose_library.clicked.connect(self._choose_library)
        self.cmb_deployment.currentIndexChanged.connect(
            self._on_deployment_changed)
        self.btn_add_treatment.clicked.connect(lambda: self._add_treatment())
        self.btn_save.clicked.connect(self._save)

    # ── library ──────────────────────────────────────────────────────────────
    def _choose_library(self):
        start = str(self._lib_root or settings.get_libraries_dir())
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Select or create a library folder", start)
        if not chosen:
            return
        self._lib_root = Path(chosen)
        self.lbl_library.setText(str(self._lib_root))
        self._load_deployments()
        self.status.emit(f"Library: {self._lib_root.name}", 4000)

    # ── deployments ──────────────────────────────────────────────────────────
    def _load_deployments(self, select=None):
        if self._lib_root is None:
            self._refresh_state()
            return
        self._deployments = self._all_deployments()
        self._loading = True
        self.cmb_deployment.clear()
        for dep in self._deployments:
            self.cmb_deployment.addItem(
                di.describe_deployment(dep), dep.get(di.DEPLOYMENT_COL, ""))
        self.cmb_deployment.addItem("New deployment…", _NEW_DEPLOYMENT)
        idx = (self.cmb_deployment.findData(select) if select is not None
               else 0)
        self.cmb_deployment.setCurrentIndex(max(0, idx))
        self._loading = False
        self._show_deployment(self.cmb_deployment.currentData())

    def _on_deployment_changed(self, *_args):
        if self._loading:
            return
        self._show_deployment(self.cmb_deployment.currentData())

    def _all_deployments(self):
        """Index-planned deployments, plus any that only exist as a folder
        on disk so far, and vice versa - a library processed before this
        page existed has sensors carrying conditions but no plan row, and
        `deployment_index.deployments()` already falls back to reading
        those; this only adds the case *neither* index nor conditions
        exist yet, just a folder tree from a previous save here."""
        indexed = di.deployments(self._lib_root)
        indexed_ids = {d.get(di.DEPLOYMENT_COL, "") for d in indexed}
        raw_dir = self._lib_root / _RAW_DIR
        on_disk = []
        if raw_dir.exists():
            for entry in sorted(raw_dir.iterdir()):
                if entry.is_dir() and entry.name not in indexed_ids:
                    on_disk.append({di.DEPLOYMENT_COL: entry.name})
        return indexed + on_disk

    def _show_deployment(self, ident):
        self._clear_treatments()
        is_new = ident is None or ident == _NEW_DEPLOYMENT
        if is_new:
            for edit in self.edits.values():
                edit.setText("")
            self._add_treatment()
            self._refresh_state()
            return

        dep = next((d for d in self._deployments
                    if d.get(di.DEPLOYMENT_COL, "") == ident), {})
        for column, edit in self.edits.items():
            edit.setText(dep.get(column, ""))

        planned = di.treatments(self._lib_root, ident)
        if planned:
            for treatment in planned:
                self._add_treatment(treatment)
        else:
            # no index plan yet - fall back to treatment names on disk
            dep_dir = self._lib_root / _RAW_DIR / ident
            names = (sorted(p.name for p in dep_dir.iterdir() if p.is_dir())
                     if dep_dir.exists() else [])
            for name in names or [None]:
                self._add_treatment({di.TREATMENT_COL: name} if name else None)
        self._refresh_state()

    # ── treatments ───────────────────────────────────────────────────────────
    def _add_treatment(self, values=None):
        if values is None:
            values = dict(self._rows[-1].values()) if self._rows else {}
            values[di.TREATMENT_COL] = self._next_name()
        row = _TreatmentRow(values, on_change=self._refresh_state,
                            on_remove=self._remove_treatment)
        self.rows_layout.addWidget(row)
        self._rows.append(row)
        self._refresh_state()
        return row

    def _next_name(self):
        used = {r.name() for r in self._rows}
        n = len(self._rows) + 1
        while f"Treatment {n}" in used:
            n += 1
        return f"Treatment {n}"

    def _remove_treatment(self, row):
        if row not in self._rows:
            return
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_state()

    def _clear_treatments(self):
        for row in list(self._rows):
            row.setParent(None)
            row.deleteLater()
        self._rows = []

    # ── state / validation ──────────────────────────────────────────────────
    def _deployment_values(self):
        return {c: e.text().strip() for c, e in self.edits.items()}

    def _problems(self):
        out = []
        if self._lib_root is None:
            out.append("Choose a library first.")
        if not self._deployment_values().get(di.DEPLOYMENT_COL):
            out.append("The deployment needs an ID.")
        if not self._rows:
            out.append("Add at least one treatment.")
        names = [r.name() for r in self._rows]
        if any(not n for n in names):
            out.append("Every treatment needs a name.")
        if len(set(names)) != len(names):
            out.append("Two treatments share a name.")
        return out

    def _refresh_state(self, *_args):
        problems = self._problems()
        self.btn_save.setEnabled(not problems)

        if self._lib_root is None:
            self.lbl_state.setText("")
            self.lbl_path.setText("")
            self.card_summary.set_title("Library")
            self.card_summary.set_rows([])
            self.lbl_rows.setText("")
            return

        ident = self._deployment_values().get(di.DEPLOYMENT_COL, "")
        n_rows = sum(r.runs() for r in self._rows)
        self.lbl_rows.setText(
            f"{len(self._rows)} treatment(s), {n_rows} row(s)"
            if self._rows else "")

        if problems:
            self.lbl_state.setText("• " + "<br>• ".join(problems))
            self.lbl_state.setStyleSheet(f"color:{WARN};")
        else:
            self.lbl_state.setText(
                f"{len(self._rows)} treatment(s) over {n_rows} run(s). "
                f"Saving writes the plan for '{ident}' and builds its "
                "folder structure.")
            self.lbl_state.setStyleSheet(f"color:{TEXT};")
        if ident:
            self.lbl_path.setText(
                f"Writes {di.index_path(self._lib_root)}; creates "
                f"{self._lib_root / _RAW_DIR / ident}\\<treatment>\\"
                f"{_VIDEO_FOLDER_NAME}\\")
        else:
            self.lbl_path.setText("")

        deps = self._deployments
        df = di.read_index(self._lib_root)
        n_sensors = 0 if df is None else len(di.sensor_rows(df))
        self.card_summary.set_title(f"Library: {self._lib_root.name}")
        rows = [("Deployments", len(deps) or None),
                ("Sensors in index", n_sensors or None)]
        raw_dir = self._lib_root / _RAW_DIR
        if raw_dir.exists():
            on_disk = sorted(p.name for p in raw_dir.iterdir() if p.is_dir())
            rows.append(("Deployment folders on disk",
                        ", ".join(on_disk) if on_disk else None))
        self.card_summary.set_rows(rows)

    # ── save ─────────────────────────────────────────────────────────────────
    def _save(self):
        problems = self._problems()
        if problems:
            QMessageBox.warning(self.window, "Cannot save",
                                "\n".join(f"• {p}" for p in problems))
            return

        deployment = self._deployment_values()
        ident = deployment.get(di.DEPLOYMENT_COL, "")
        treatments = [r.values() for r in self._rows]
        n_rows = sum(t["runs"] for t in treatments)

        df = di.read_index(self._lib_root)
        n_sensors = 0 if df is None else len(di.sensor_rows(df))
        existing = di.treatments(self._lib_root, ident)

        detail = (f"Write {len(treatments)} treatment(s) over {n_rows} "
                  f"run(s) for '{ident}' to\n{di.index_path(self._lib_root)}"
                  f"\n\nand create its raw_sens_data folder structure.")
        if existing:
            detail += (f"\n\nThe {len(existing)} treatment(s) already "
                       f"planned for '{ident}' are replaced.")
        if n_sensors:
            detail += (f"\n{n_sensors} processed sensor row(s) are left as "
                       "they are.")
        if QMessageBox.question(self.window, "Save deployment plan", detail) \
                != QMessageBox.StandardButton.Yes:
            return

        try:
            path, n = di.save_plan(self._lib_root, deployment, treatments)
            created = self._build_folders(ident, [t[di.TREATMENT_COL]
                                                   for t in treatments])
            self._write_summary(ident, created)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return

        self._load_deployments(select=ident)
        self.lbl_state.setText(
            f"Saved {n} row(s) for '{ident}' and built its folder "
            "structure. Drop raw sensor files into each treatment folder "
            f"and video into its {_VIDEO_FOLDER_NAME} subfolder.")
        self.lbl_state.setStyleSheet(f"color:{OK};")
        self.status.emit(f"Deployment plan saved to {path}", 5000)

    def _build_folders(self, ident, names):
        """`raw_sens_data/<ident>/<name>/VIDEO/` for each treatment name -
        idempotent, so re-saving an existing deployment (or adding a new
        one) never disturbs files already dropped into earlier folders."""
        dep_dir = self._lib_root / _RAW_DIR / ident
        created = []
        for name in names:
            treatment_dir = dep_dir / name
            existed = treatment_dir.exists()
            (treatment_dir / _VIDEO_FOLDER_NAME).mkdir(
                parents=True, exist_ok=True)
            created.append((name, "already existed" if existed else "created"))
        return created

    def _write_summary(self, ident, created):
        lines = [
            f"Deployment: {ident}",
            f"Library: {self._lib_root.name}",
            f"Saved: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "Treatments:",
        ]
        for name, state in created:
            lines.append(
                f"  - {name}  ({state}: "
                f"{_RAW_DIR}/{ident}/{name}/, {_VIDEO_FOLDER_NAME}/)")
        dep_dir = self._lib_root / _RAW_DIR / ident
        dep_dir.mkdir(parents=True, exist_ok=True)
        (dep_dir / _SUMMARY_NAME).write_text("\n".join(lines))
