# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Controller for the Initiate deployment page (Setup and deploy).

The last step before fieldwork: pick or create the library, name the
deployment and its treatments, and build the `raw_sens_data/<deployment>/
<treatment>/VIDEO/` folder tree Annotate and Process already expect - so
once sensors and video come back from the field, they only need dragging
into the right folder, nothing needs creating by hand.

Deliberately not the same "root + combo of existing subfolders" library
picker every other page uses (`page_annotate.py`, `prepare_tab_study.py`,
...): this page's job is to *create* a library, not just pick among ones
that already exist, so a single native folder dialog - which lets the user
browse anywhere (any drive, a network path) and make a new folder inline,
exactly like Explorer - covers both create and select in one step.

Treatment names entered here are for folder-naming only; nothing is written
to `global_sensor_index.csv` (that stays Study design's job, since it needs
the full set of conditions - head, flow, BEP, RPM - this page doesn't
collect). When the chosen deployment already has a plan there, its
treatment names are read back with `deployment_index.treatments()` so the
folders line up with it automatically; a deployment with no plan yet still
works, so folders can exist before Study design's numbers are finalised.
Building is idempotent (`mkdir(..., exist_ok=True)`), so re-running it for
an existing deployment - or adding a new one - never disturbs files already
dropped into earlier folders.
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import settings
from .ml_widgets import (
    ACCENT, MUTED, OK, TEXT, WARN, MetaCard, Section, apply_section_defaults,
)
from .page_annotate import _RAW_DIR, _VIDEO_FOLDER_NAME

_NEW_DEPLOYMENT = "__new__"
_SUMMARY_NAME = "deployment_summary.txt"


class _TreatmentNameRow(QWidget):
    """One treatment name field, for folder-naming purposes only."""

    def __init__(self, name="", on_change=None, on_remove=None, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.edit = QLineEdit(name)
        self.edit.setPlaceholderText("Treatment name")
        if on_change is not None:
            self.edit.textEdited.connect(lambda _t: on_change())
        h.addWidget(self.edit, stretch=1)
        self.btn_remove = QPushButton("Remove")
        if on_remove is not None:
            self.btn_remove.clicked.connect(lambda: on_remove(self))
        h.addWidget(self.btn_remove)

    def name(self):
        return self.edit.text().strip()


class InitiateDeploymentPage(QObject):
    """Binds the Initiate deployment page widgets to `ui.content_initiate_deployment`."""

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

        grp_lib = Section("Library")
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

        id_row = QHBoxLayout()
        id_row.setSpacing(6)
        id_row.addWidget(self._muted("Deployment ID"))
        self.ed_deployment_id = QLineEdit()
        self.ed_deployment_id.setPlaceholderText("e.g. PF_Test_Rig_2026")
        id_row.addWidget(self.ed_deployment_id, stretch=1)
        lv.addLayout(id_row)
        row1.addWidget(grp_lib, stretch=3)

        self.card_summary = MetaCard("Library")
        self.card_summary.setMinimumWidth(240)
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
        tv.addWidget(self.rows_holder)
        self.btn_add_treatment = QPushButton("+  Add treatment")
        self.btn_add_treatment.setMinimumHeight(28)
        tv.addWidget(self.btn_add_treatment)
        v.addWidget(grp_tr)

        grp_build = Section("Build folder structure")
        bv = QVBoxLayout(grp_build)
        bv.setSpacing(6)
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        bv.addWidget(self.lbl_state)
        self.btn_build = QPushButton("Build folder structure")
        self.btn_build.setMinimumHeight(30)
        self.btn_build.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        bv.addWidget(self.btn_build)
        self.lbl_path = QLabel("")
        self.lbl_path.setStyleSheet(f"color:{MUTED};font-size:10px;")
        self.lbl_path.setWordWrap(True)
        bv.addWidget(self.lbl_path)
        v.addWidget(grp_build)

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
        self.ed_deployment_id.textEdited.connect(self._refresh_state)
        self.btn_add_treatment.clicked.connect(lambda: self._add_treatment())
        self.btn_build.clicked.connect(self._build_folders)

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
        on disk so far - this page never writes the index (that stays
        Study design's job), so a deployment built here and nowhere else
        would otherwise vanish from the picker the next time it loads."""
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
        self.ed_deployment_id.setReadOnly(not is_new)
        if is_new:
            self.ed_deployment_id.setText("")
            self._add_treatment("Treatment 1")
            self._refresh_state()
            return

        self.ed_deployment_id.setText(ident)
        planned = di.treatments(self._lib_root, ident)
        names = [t.get(di.TREATMENT_COL, "") for t in planned if
                 t.get(di.TREATMENT_COL, "")]
        if not names:
            # no index plan yet - fall back to what's already on disk
            dep_dir = self._lib_root / _RAW_DIR / ident
            if dep_dir.exists():
                names = sorted(p.name for p in dep_dir.iterdir()
                               if p.is_dir())
        for name in names or ["Treatment 1"]:
            self._add_treatment(name)
        self._refresh_state()

    # ── treatments ───────────────────────────────────────────────────────────
    def _add_treatment(self, name=""):
        if not name:
            used = {r.name() for r in self._rows}
            n = len(self._rows) + 1
            while f"Treatment {n}" in used:
                n += 1
            name = f"Treatment {n}"
        row = _TreatmentNameRow(name, on_change=self._refresh_state,
                                on_remove=self._remove_treatment)
        self.rows_layout.addWidget(row)
        self._rows.append(row)
        self._refresh_state()

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
    def _problems(self):
        out = []
        if self._lib_root is None:
            out.append("Choose a library first.")
        ident = self.ed_deployment_id.text().strip()
        if not ident:
            out.append("The deployment needs an ID.")
        names = [r.name() for r in self._rows]
        if not any(names):
            out.append("Add at least one treatment.")
        if any(not n for n in names):
            out.append("Every treatment needs a name.")
        if len(set(n for n in names if n)) != len([n for n in names if n]):
            out.append("Two treatments share a name.")
        return out

    def _refresh_state(self, *_args):
        problems = self._problems()
        self.btn_build.setEnabled(not problems)

        if self._lib_root is None:
            self.lbl_state.setText("")
            self.lbl_path.setText("")
            self.card_summary.set_title("Library")
            self.card_summary.set_rows([])
            return

        ident = self.ed_deployment_id.text().strip()
        names = [r.name() for r in self._rows if r.name()]
        if problems:
            self.lbl_state.setText("• " + "<br>• ".join(problems))
            self.lbl_state.setStyleSheet(f"color:{WARN};")
        else:
            self.lbl_state.setText(
                f"{len(names)} treatment folder(s) will be created (or left "
                f"alone if they already exist) for '{ident}'.")
            self.lbl_state.setStyleSheet(f"color:{TEXT};")
        if ident:
            self.lbl_path.setText(
                f"Creates {self._lib_root / _RAW_DIR / ident}\\<treatment>\\"
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

    # ── build ────────────────────────────────────────────────────────────────
    def _build_folders(self):
        problems = self._problems()
        if problems:
            QMessageBox.warning(self.window, "Cannot build",
                                "\n".join(f"• {p}" for p in problems))
            return

        ident = self.ed_deployment_id.text().strip()
        names = [r.name() for r in self._rows if r.name()]
        dep_dir = self._lib_root / _RAW_DIR / ident

        try:
            created = []
            for name in names:
                treatment_dir = dep_dir / name
                video_dir = treatment_dir / _VIDEO_FOLDER_NAME
                existed = treatment_dir.exists()
                video_dir.mkdir(parents=True, exist_ok=True)
                created.append((name, "already existed" if existed else "created"))
            self._write_summary(ident, dep_dir, created)
        except Exception as e:
            QMessageBox.critical(self.window, "Build failed", str(e))
            return

        self._load_deployments(select=ident)
        self.status.emit(
            f"Folder structure ready for '{ident}' ({len(names)} "
            "treatment(s)).", 5000)
        self.lbl_state.setText(
            f"Done. Drop raw sensor files into each treatment folder and "
            f"video into its {_VIDEO_FOLDER_NAME} subfolder. Add treatment "
            "conditions (head, flow, BEP, RPM) in Study design when ready.")
        self.lbl_state.setStyleSheet(f"color:{OK};")

    def _write_summary(self, ident, dep_dir, created):
        lines = [
            f"Deployment: {ident}",
            f"Library: {self._lib_root.name}",
            f"Built: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "Treatments:",
        ]
        for name, state in created:
            lines.append(
                f"  - {name}  ({state}: "
                f"{_RAW_DIR}/{ident}/{name}/, {_VIDEO_FOLDER_NAME}/)")
        lines.append("")
        lines.append(
            "Add treatment conditions (head, flow, BEP, RPM) in Study "
            "design; this file only records the folder structure.")
        dep_dir.mkdir(parents=True, exist_ok=True)
        (dep_dir / _SUMMARY_NAME).write_text("\n".join(lines))
