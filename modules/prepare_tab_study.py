# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Study design tab - plan a deployment before any sensor is wetted.

The deployment is described once (site, deployment ID, machine and its
type), then one row per treatment: head, flow, BEP, RPM and how many runs.
Adding a treatment copies the previous one, because in practice treatments
differ in one or two values rather than all of them.

Saving writes the plan into the library's ``global_sensor_index.csv`` as one
row per treatment (see ``deployment_index``), which is what the Process page
then offers as an assignment: select a batch of sensors, pick the treatment
they were run under, process, and every one of them lands in the index
carrying that treatment's conditions. The workflow is treatment by
treatment, so the deployment metadata is never typed per file.

The Process page's Metadata tab still edits individual sensors, which is
what it is good for once the bulk labelling is done here.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import settings
from .ml_widgets import (
    ACCENT, BAD, BORDER, CARD_BG, MUTED, OK, TEXT, WARN, MetaCard, Section,
    apply_section_defaults,
)


class _TreatmentRow(QFrame):
    """One treatment: its name and the conditions it is run at."""

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
            f"#treatmentRow QLineEdit{{background-color:#1b1e23;"
            f"border:1px solid {BORDER};border-radius:4px;padding:3px 6px;"
            f"color:{TEXT};}}"
            f"#treatmentRow QLineEdit:focus{{border:1px solid {ACCENT};}}")
        self._on_change = on_change

        values = values or {}
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        self.edits = {}
        for col, (column, label) in enumerate(di.TREATMENT_FIELDS):
            lab = QLabel(label)
            lab.setStyleSheet(f"color:{MUTED};font-size:10px;border:none;")
            edit = QLineEdit(str(values.get(column, "")))
            edit.setMinimumWidth(90)
            edit.setMaximumWidth(150 if column == di.TREATMENT_COL else 110)
            if on_change is not None:
                edit.textEdited.connect(lambda _t: on_change())
            grid.addWidget(lab, 0, col)
            grid.addWidget(edit, 1, col)
            self.edits[column] = edit

        last = len(di.TREATMENT_FIELDS)
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setToolTip("Remove this treatment")
        if on_remove is not None:
            self.btn_remove.clicked.connect(lambda: on_remove(self))
        grid.addWidget(QLabel(""), 0, last)
        grid.addWidget(self.btn_remove, 1, last, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(last, 1)   # the fields pack to the left

    def values(self):
        return {c: e.text().strip() for c, e in self.edits.items()}

    def name(self):
        return self.edits[di.TREATMENT_COL].text().strip()


class StudyTab:
    """Builds the Study design tab into `frame`."""

    def __init__(self, frame, window, status=None):
        self.window = window
        self._status = status
        self._lib_dir = settings.get_libraries_dir()
        self._root = None
        self._rows = []

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

        # ── row 1: the deployment + what is already planned ─────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        grp_dep = Section("Deployment")
        dv = QVBoxLayout(grp_dep)
        dv.setSpacing(6)

        lib_row = QHBoxLayout()
        lib_row.setSpacing(6)
        lib_row.addWidget(self._muted("Library"))
        self.cmb_library = QComboBox()
        self.cmb_library.setMinimumWidth(200)
        self.cmb_library.currentIndexChanged.connect(self._on_library_changed)
        lib_row.addWidget(self.cmb_library, stretch=1)
        self.btn_change_libs = QPushButton("Change libraries folder…")
        self.btn_change_libs.clicked.connect(self._change_libraries)
        lib_row.addWidget(self.btn_change_libs)
        dv.addLayout(lib_row)

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

        note = self._muted(
            "These apply to every treatment below. Each sensor assigned to a "
            "treatment on the Process page is stamped with them.")
        note.setWordWrap(True)
        dv.addWidget(note)
        row1.addWidget(grp_dep, stretch=3)

        self.card_plan = MetaCard("Saved plan")
        self.card_plan.setMinimumWidth(260)
        self.card_plan.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Expanding)
        row1.addWidget(self.card_plan, stretch=2)
        v.addLayout(row1)

        # ── row 2: the treatments ───────────────────────────────────────────
        grp_tr = Section("Treatments")
        tv = QVBoxLayout(grp_tr)
        tv.setSpacing(6)
        tv.addWidget(self._muted(
            "One set of conditions per treatment. Adding a treatment copies "
            "the one above it, so only what differs needs changing."))

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
        self.btn_reload = QPushButton("Load saved plan")
        self.btn_reload.clicked.connect(self._load_plan)
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
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        try:
            libs = sorted(p for p in self._lib_dir.iterdir() if p.is_dir())
        except Exception:
            libs = []
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))
        self.cmb_library.blockSignals(False)
        self.btn_change_libs.setToolTip(str(self._lib_dir))

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
        path = self.cmb_library.currentData()
        self._root = Path(path) if path else None
        self._load_plan(quiet=True)

    # ── treatments ───────────────────────────────────────────────────────────
    def _add_treatment(self, values=None):
        if values is None:
            # a new treatment starts as a copy of the last one, renamed
            values = self._rows[-1].values() if self._rows else {}
            values = dict(values)
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
        if not self._deployment_values().get("deployment_id"):
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
        self.btn_save.setEnabled(not problems)
        self.btn_reload.setEnabled(self._root is not None)

        if problems:
            self.lbl_state.setText("• " + "<br>• ".join(problems))
            self.lbl_state.setStyleSheet(f"color:{WARN};")
        else:
            self.lbl_state.setText(
                f"{len(self._rows)} treatment(s) ready to save. Saving "
                "replaces the plan already in this library; processed "
                "sensors already in the index are untouched.")
            self.lbl_state.setStyleSheet(f"color:{TEXT};")

        if self._root is None:
            self.lbl_path.setText(f"No libraries found in {self._lib_dir}")
            self.card_plan.set_title("Saved plan")
            self.card_plan.set_rows([])
            return

        self.lbl_path.setText(f"Writes to {di.index_path(self._root)}")
        saved = di.treatments(self._root)
        df = di.read_index(self._root)
        n_sensors = 0 if df is None else len(di.sensor_rows(df))
        self.card_plan.set_title(f"Saved plan: {self._root.name}")
        rows = [("Treatments", len(saved) or None),
                ("Sensors in index", n_sensors or None)]
        for t in saved[:6]:
            rows.append((t.get(di.TREATMENT_COL, "—"), di.describe(t)))
        if len(saved) > 6:
            rows.append(("…", f"{len(saved) - 6} more"))
        self.card_plan.set_rows(rows)

    # ── load / save ──────────────────────────────────────────────────────────
    def _load_plan(self, quiet=False):
        if self._root is None:
            return
        saved = di.treatments(self._root)
        self._clear_treatments()

        if saved:
            for column, edit in self.edits.items():
                edit.setText(str(saved[0].get(column, "")))
            for t in saved:
                self._add_treatment(t)
            if not quiet:
                self._emit(f"Loaded {len(saved)} treatment(s) from "
                           f"{self._root.name}.")
        else:
            for edit in self.edits.values():
                edit.setText("")
            self._add_treatment({di.TREATMENT_COL: "Treatment 1"})
            if not quiet:
                self._emit(f"{self._root.name} has no saved plan yet.")
        self._refresh_state()

    def _save(self):
        problems = self._problems()
        if problems:
            QMessageBox.warning(self.window, "Cannot save",
                                "\n".join(f"• {p}" for p in problems))
            return

        treatments = [r.values() for r in self._rows]
        path = di.index_path(self._root)
        existing = di.read_index(self._root)
        n_sensors = 0 if existing is None else len(di.sensor_rows(existing))
        n_planned = len(di.treatments(self._root))

        detail = f"Write {len(treatments)} treatment row(s) to\n{path}"
        if n_planned:
            detail += f"\n\nThe {n_planned} treatment row(s) already there " \
                      "are replaced."
        if n_sensors:
            detail += f"\n{n_sensors} processed sensor row(s) are left as " \
                      "they are."
        if QMessageBox.question(self.window, "Save deployment plan", detail) \
                != QMessageBox.StandardButton.Yes:
            return

        try:
            path, n = di.save_plan(
                self._root, self._deployment_values(), treatments)
        except Exception as e:
            QMessageBox.critical(self.window, "Save failed", str(e))
            return

        self._refresh_state()
        self.lbl_state.setText(
            f"Saved {n} treatment(s). Process now offers them when sensors "
            "are processed.")
        self.lbl_state.setStyleSheet(f"color:{OK};")
        self._emit(f"Deployment plan saved to {path}")

    def _emit(self, message, ms=5000):
        if self._status is not None:
            self._status(message, ms)
