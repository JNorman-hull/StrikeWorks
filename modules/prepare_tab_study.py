# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Study design tab - plan a deployment before any sensor is wetted.

A deployment is described once (site, deployment ID, machine and its type),
then one row per treatment: head, flow, BEP, RPM and how many runs it gets.
Adding a treatment copies the previous one, because in practice treatments
differ in one or two values rather than all of them.

A library holds as many deployments as it needs, so the deployment picker
lists what the library already has - read from its plan rows, or from the
conditions on its processed sensors when it was filled in before this tab
existed - and each is edited and saved on its own.

Saving writes the plan into ``global_sensor_index.csv`` as one row per
treatment *per run* (see ``deployment_index``). The Process page then offers
those treatments and runs: select a batch of sensors, pick the treatment
and run they were recorded under, process, and every one of them lands in
the index carrying those conditions. The workflow is treatment by
treatment, so deployment metadata is never typed per file.

The Process page's Metadata tab still edits individual sensors, which is
what it is good for once the bulk labelling is done here.
"""
from pathlib import Path

from PySide6.QtCore import Qt
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

_NEW_DEPLOYMENT = "__new__"


class _TreatmentRow(QFrame):
    """One treatment: its name, the conditions it runs at, and its runs."""

    def __init__(self, values=None, on_change=None, on_remove=None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("treatmentRow")
        # the fields are styled here too: a widget with its own stylesheet
        # does not pick up the page's QLineEdit rules, so without this the
        # boxes render as bare text on the card
        self.setStyleSheet(
            f"#treatmentRow{{background-color:{CARD_BG};border-radius:6px;"
            f"border:1px solid {BORDER};}}"
            f"#treatmentRow QLineEdit, #treatmentRow QSpinBox"
            f"{{background-color:#1b1e23;border:1px solid {BORDER};"
            f"border-radius:4px;padding:3px 6px;color:{TEXT};}}"
            f"#treatmentRow QLineEdit:focus, #treatmentRow QSpinBox:focus"
            f"{{border:1px solid {ACCENT};}}"
            # Once a stylesheet touches QSpinBox's box model (border/padding
            # above), Qt stops drawing the native up/down buttons unless the
            # sub-controls are styled explicitly too - otherwise they, and
            # the Up/Down arrow keys that rely on the same control, go dead.
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
        self.spin_runs.setToolTip(
            "Runs can be assigned during processing.")
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
        grid.addWidget(self.btn_remove, 1, last, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(last, 1)   # the fields pack to the left

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


class StudyTab:
    """Builds the Study design tab into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._lib_dir = settings.get_libraries_dir()
        self._root = None
        self._rows = []
        self._deployments = []
        self._loading = False

        self._build(frame)
        self._reload_libraries()

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

        # ── row 1: the deployment + what the library already holds ──────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        grp_dep = Section("Deployment")
        dv = QVBoxLayout(grp_dep)
        dv.setSpacing(6)

        lib_row = QHBoxLayout()
        lib_row.setSpacing(6)
        lib_row.addWidget(self._muted("Library"))
        self.cmb_library = QComboBox()
        self.cmb_library.setMinimumWidth(180)
        self.cmb_library.currentIndexChanged.connect(self._on_library_changed)
        lib_row.addWidget(self.cmb_library, stretch=1)
        self.btn_change_libs = QPushButton("Libraries")
        self.btn_change_libs.clicked.connect(self._change_libraries)
        lib_row.addWidget(self.btn_change_libs)
        dv.addLayout(lib_row)

        dep_row = QHBoxLayout()
        dep_row.setSpacing(6)
        dep_row.addWidget(self._muted("Deployment"))
        self.cmb_deployment = QComboBox()
        self.cmb_deployment.setMinimumWidth(180)
        self.cmb_deployment.currentIndexChanged.connect(
            self._on_deployment_changed)
        dep_row.addWidget(self.cmb_deployment, stretch=1)
        dv.addLayout(dep_row)

        form = QGridLayout()
        form.setVerticalSpacing(6)
        form.setColumnStretch(1, 1)
        self.edits = {}
        for i, (column, label) in enumerate(di.DEPLOYMENT_FIELDS):
            form.addWidget(self._muted(label), i, 0)
            edit = QLineEdit()
            edit.textEdited.connect(lambda _t: self._refresh_state())
            form.addWidget(edit, i, 1)
            self.edits[column] = edit
        dv.addLayout(form)
        row1.addWidget(grp_dep, stretch=3)

        self.card_plan = MetaCard("Library")
        self.card_plan.setMinimumWidth(260)
        self.card_plan.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Expanding)
        row1.addWidget(self.card_plan, stretch=2)
        v.addLayout(row1)

        # ── row 2: the treatments ───────────────────────────────────────────
        grp_tr = Section("Treatments")
        tv = QVBoxLayout(grp_tr)
        tv.setSpacing(6)

        self.rows_holder = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_holder)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        tv.addWidget(self.rows_holder)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.btn_add = QPushButton("+  Add treatment")
        self.btn_add.setMinimumHeight(28)
        self.btn_add.clicked.connect(lambda: self._add_treatment())
        add_row.addWidget(self.btn_add)
        add_row.addStretch()
        self.lbl_rows = QLabel("")
        self.lbl_rows.setStyleSheet(f"color:{MUTED};")
        add_row.addWidget(self.lbl_rows)
        tv.addLayout(add_row)
        v.addWidget(grp_tr)

        # ── row 3: save ─────────────────────────────────────────────────────
        grp_save = Section("Save to library")
        gv = QVBoxLayout(grp_save)
        gv.setSpacing(6)

        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        gv.addWidget(self.lbl_state)

        act = QHBoxLayout()
        act.setSpacing(6)
        self.btn_save = QPushButton("Save deployment plan")
        self.btn_save.setMinimumHeight(30)
        self.btn_save.setStyleSheet(
            f"QPushButton{{background-color:{ACCENT};color:#ffffff;"
            "border-radius:5px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:disabled{background-color:#3a4150;color:#8a95aa;}")
        self.btn_save.clicked.connect(self._save)
        self.btn_reload = QPushButton("Reload from library")
        self.btn_reload.clicked.connect(lambda: self._load_deployments())
        act.addWidget(self.btn_save)
        act.addWidget(self.btn_reload)
        act.addStretch()
        gv.addLayout(act)

        self.lbl_path = QLabel("")
        self.lbl_path.setStyleSheet(f"color:{MUTED};font-size:10px;")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        gv.addWidget(self.lbl_path)
        v.addWidget(grp_save)

        v.addStretch()
        apply_section_defaults(frame)

    @staticmethod
    def _muted(text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{MUTED};")
        return lab

    # ── libraries ────────────────────────────────────────────────────────────
    def _reload_libraries(self, select=None):
        self._loading = True
        self.cmb_library.clear()
        try:
            libs = sorted(p for p in self._lib_dir.iterdir() if p.is_dir())
        except Exception:
            libs = []
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))
        self.btn_change_libs.setToolTip(str(self._lib_dir))
        self._loading = False

        if not libs:
            self._root = None
            self._refresh_state()
            return
        idx = self.cmb_library.findData(str(select)) if select else 0
        self.cmb_library.setCurrentIndex(max(0, idx))
        self._on_library_changed()

    def _change_libraries(self):
        chosen = QFileDialog.getExistingDirectory(
            self.window, "Select libraries folder", str(self._lib_dir))
        if not chosen:
            return
        self._lib_dir = settings.set_libraries_dir(chosen)
        self._reload_libraries()
        self._emit(f"Libraries folder: {chosen}")

    def _on_library_changed(self, *_args):
        if self._loading:
            return
        path = self.cmb_library.currentData()
        self._root = Path(path) if path else None
        self._load_deployments(quiet=True)

    # ── deployments ──────────────────────────────────────────────────────────
    def _load_deployments(self, quiet=False, select=None):
        """Fill the deployment picker from whatever the library holds."""
        if self._root is None:
            self._refresh_state()
            return

        self._deployments = di.deployments(self._root)
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

        if not quiet:
            n = len(self._deployments)
            self._emit(f"{self._root.name}: {n} deployment(s) found."
                       if n else f"{self._root.name} has no deployments yet.")

    def _on_deployment_changed(self, *_args):
        if self._loading:
            return
        self._show_deployment(self.cmb_deployment.currentData())

    def _show_deployment(self, ident):
        """Load one deployment's fields and treatments into the form."""
        self._clear_treatments()

        if ident is None or ident == _NEW_DEPLOYMENT:
            for edit in self.edits.values():
                edit.setText("")
            self._add_treatment({di.TREATMENT_COL: "Treatment 1", "runs": 1})
            self._refresh_state()
            return

        dep = next((d for d in self._deployments
                    if d.get(di.DEPLOYMENT_COL, "") == ident), {})
        for column, edit in self.edits.items():
            edit.setText(dep.get(column, ""))

        planned = di.treatments(self._root, ident)
        if planned:
            for treatment in planned:
                self._add_treatment(treatment)
        else:
            self._add_treatment({di.TREATMENT_COL: "Treatment 1", "runs": 1})
        self._refresh_state()

    # ── treatments ───────────────────────────────────────────────────────────
    def _add_treatment(self, values=None):
        if values is None:
            # a new treatment starts as a copy of the last one, renamed
            values = dict(self._rows[-1].values()) if self._rows else {}
            values[di.TREATMENT_COL] = self._next_name()
        row = _TreatmentRow(values, on_change=self._refresh_state,
                            on_remove=self._remove_treatment)
        self.rows_layout.addWidget(row)
        self._rows.append(row)
        self._refresh_state()
        return row

    def _next_name(self):
        """Treatment 1, 2, 3 … skipping names already used."""
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

    # ── state ────────────────────────────────────────────────────────────────
    def _deployment_values(self):
        return {c: e.text().strip() for c, e in self.edits.items()}

    def _problems(self):
        out = []
        if self._root is None:
            out.append("Select a library to save into.")
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

    def _refresh_state(self):
        problems = self._problems()
        n_rows = sum(r.runs() for r in self._rows)
        self.btn_save.setEnabled(not problems)
        self.btn_reload.setEnabled(self._root is not None)
        self.lbl_rows.setText(
            f"{len(self._rows)} treatment(s), {n_rows} row(s)"
            if self._rows else "")

        if problems:
            self.lbl_state.setText("• " + "<br>• ".join(problems))
            self.lbl_state.setStyleSheet(f"color:{WARN};")
        else:
            ident = self._deployment_values().get(di.DEPLOYMENT_COL)
            self.lbl_state.setText(
                f"{len(self._rows)} treatment(s) over {n_rows} run(s). "
                f"Saving replaces the plan for '{ident}' only"
            )
            self.lbl_state.setStyleSheet(f"color:{TEXT};")

        if self._root is None:
            self.lbl_path.setText(f"No libraries found in {self._lib_dir}")
            self.card_plan.set_title("Library")
            self.card_plan.set_rows([])
            return

        self.lbl_path.setText(f"Writes to {di.index_path(self._root)}")
        df = di.read_index(self._root)
        n_sensors = 0 if df is None else len(di.sensor_rows(df))
        n_plan = 0 if df is None else len(di.plan_rows(df))
        deps = getattr(self, "_deployments", [])
        self.card_plan.set_title(f"Library: {self._root.name}")
        rows = [("Deployments", len(deps) or None),
                ("Planned rows", n_plan or None),
                ("Sensors in index", n_sensors or None)]
        for dep in deps[:5]:
            rows.append((di.describe_deployment(dep),
                         f"{len(di.treatments(self._root, dep.get(di.DEPLOYMENT_COL, '')))}"
                         " treatment(s)"))
        if len(deps) > 5:
            rows.append(("…", f"{len(deps) - 5} more"))
        self.card_plan.set_rows(rows)

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

        df = di.read_index(self._root)
        n_sensors = 0 if df is None else len(di.sensor_rows(df))
        existing = di.treatments(self._root, ident)

        detail = (f"Write {len(treatments)} treatment(s) over {n_rows} run(s) "
                  f"for '{ident}' to\n{di.index_path(self._root)}")
        if existing:
            detail += (f"\n\nThe {len(existing)} treatment(s) already planned "
                       f"for '{ident}' are replaced.")
        if n_sensors:
            detail += (f"\n{n_sensors} processed sensor row(s) are left as "
                       "they are.")
        if QMessageBox.question(self.window, "Save deployment plan", detail) \
                != QMessageBox.StandardButton.Yes:
            return

        try:
            path, n = di.save_plan(self._root, deployment, treatments)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return

        self._load_deployments(quiet=True, select=ident)
        self.lbl_state.setText(
            f"Saved {n} row(s) for '{ident}'. Process now offers these "
            "treatments and runs.")
        self.lbl_state.setStyleSheet(f"color:{OK};")
        self._emit(f"Deployment plan saved to {path}")

    def _emit(self, message, ms=5000):
        if self._status is not None:
            self._status(message, ms)
