# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Home page - session library selection, New session, and a resume
summary of what's already been done for the selected library.

Design (2026-08-31, see ROADMAP.md): `SessionState` is the single shared
"which library" value; this page is where the user sets it. Every other
page's own library picker (Process, Annotate, Export animations) soft-
syncs to it - starts here, still independently changeable per page. A
single unified picker replacing all of those is a planned follow-up, not
this pass.

The resume summary reads straight from the library's own files
(`deployment_index.py`, `model_features.csv`, the library's
`StrikeWorks_user_output/` folder) rather than reaching into other pages'
in-memory state - decoupled, and correct even before those pages have
been visited this session.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import settings
from .ml_widgets import ACCENT, MUTED, TEXT, MetaCard, Section, apply_section_defaults
from .session_state import OUTPUT_DIR_NAME

_LOGO_RESOURCE = ":/images/images/images/PyDracula_vertical.png"
_CARD_WIDTH = 360


class HomePage(QObject):
    """Binds the Home page to `ui.home`."""

    status = Signal(str, int)

    def __init__(self, ui, window, session_state):
        super().__init__(window)
        self.ui = ui
        self.window = window
        self.session_state = session_state

        self._build(ui.home)
        self._connect()
        self._refresh_library_combo()
        self._refresh_summary()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        # the stub background image fights with real content - a plain
        # dark background matches every other page instead; the same
        # image comes back below as a real (not stretched) logo
        frame.setStyleSheet("background:transparent;")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)

        content_row = QHBoxLayout()
        content_row.setSpacing(24)
        content_row.addWidget(self._build_card_column(), stretch=0)
        content_row.addStretch(1)
        content_row.addWidget(self._build_logo(), stretch=0)
        outer.addLayout(content_row, stretch=1)

        apply_section_defaults(frame)

    def _build_logo(self):
        lab = QLabel()
        pix = QPixmap(_LOGO_RESOURCE)
        if not pix.isNull():
            lab.setPixmap(pix.scaledToWidth(
                360, Qt.TransformationMode.SmoothTransformation))
        lab.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        return lab

    def _build_card_column(self):
        """The session-library card + resume summary + mode buttons,
        bounded to a fixed width - a "login box" rather than content
        stretched across the whole page."""
        col = QWidget()
        col.setMaximumWidth(_CARD_WIDTH)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        title = QLabel("StrikeWorks")
        title.setStyleSheet(f"color:{TEXT};font-size:20px;font-weight:bold;")
        v.addWidget(title)
        subtitle = QLabel("Select the library this session works in.")
        subtitle.setStyleSheet(f"color:{MUTED};")
        subtitle.setWordWrap(True)
        v.addWidget(subtitle)

        grp = Section("Session library")
        gv = QVBoxLayout(grp)
        gv.setSpacing(8)

        self.cmb_library = QComboBox()
        gv.addWidget(self.cmb_library)

        self.lbl_library_path = QLabel("No library selected.")
        self.lbl_library_path.setStyleSheet(f"color:{MUTED};font-size:11px;")
        self.lbl_library_path.setWordWrap(True)
        gv.addWidget(self.lbl_library_path)

        action_row = QHBoxLayout()
        self.btn_new_library = QPushButton("New library")
        self.btn_new_library.setFlat(True)
        self.btn_new_library.setStyleSheet(f"color:{ACCENT};text-align:left;")
        action_row.addWidget(self.btn_new_library)
        action_row.addStretch()
        self.btn_new_session = QPushButton("New session")
        self.btn_new_session.setFlat(True)
        self.btn_new_session.setStyleSheet(f"color:{ACCENT};text-align:right;")
        action_row.addWidget(self.btn_new_session)
        gv.addLayout(action_row)
        v.addWidget(grp)

        grp_sum = Section("Library status")
        sv = QVBoxLayout(grp_sum)
        self.card_status = MetaCard("Nothing selected yet")
        sv.addWidget(self.card_status)
        v.addWidget(grp_sum)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.btn_simple_mode = QPushButton("Simple mode")
        self.btn_simple_mode.setMinimumHeight(44)
        self.btn_simple_mode.setEnabled(False)
        self.btn_simple_mode.setToolTip(
            "Coming soon - a guided deployment > processing > predicting > "
            "reporting pipeline on top of Advanced mode's existing pages.")
        mode_row.addWidget(self.btn_simple_mode)
        self.btn_advanced_mode = QPushButton("Advanced mode")
        self.btn_advanced_mode.setMinimumHeight(44)
        self.btn_advanced_mode.setToolTip(
            "The current mode - every page, reached from the sidebar.")
        mode_row.addWidget(self.btn_advanced_mode)
        v.addLayout(mode_row)

        v.addStretch()
        return col

    def _connect(self):
        self.cmb_library.currentIndexChanged.connect(self._on_combo_changed)
        self.btn_new_library.clicked.connect(self._new_library)
        self.btn_new_session.clicked.connect(self._new_session)
        self.btn_advanced_mode.clicked.connect(self._go_advanced)
        self.session_state.library_changed.connect(self._on_session_library_changed)

    # ── library combo ───────────────────────────────────────────────────────
    def _refresh_library_combo(self, select=None):
        lib_dir = settings.get_libraries_dir()
        self.cmb_library.blockSignals(True)
        self.cmb_library.clear()
        try:
            libs = sorted(p for p in lib_dir.iterdir() if p.is_dir())
        except Exception:
            libs = []
        for lib in libs:
            self.cmb_library.addItem(lib.name, str(lib))

        want = str(select) if select else (
            str(self.session_state.library) if self.session_state.library else None)
        idx = self.cmb_library.findData(want) if want else -1
        if idx >= 0:
            self.cmb_library.setCurrentIndex(idx)
        self.cmb_library.blockSignals(False)

        # a freshly populated combo defaults to index 0 (same convention
        # LibrarySelector's own picker already uses) whether or not `want`
        # matched - apply that back into the session explicitly, since
        # blockSignals means currentIndexChanged never fired for it and
        # state/UI would otherwise silently disagree until the user
        # happens to touch the combo
        current = self.cmb_library.currentData()
        if str(self.session_state.library or "") != str(current or ""):
            self.session_state.set_library(current)

    def _new_library(self):
        name, ok = QInputDialog.getText(
            self.window, "New library", "Library name:")
        name = name.strip()
        if not ok or not name:
            return
        lib_dir = settings.get_libraries_dir()
        new_root = lib_dir / name
        if new_root.exists():
            QMessageBox.warning(
                self.window, "Already exists",
                f"A library named “{name}” already exists.")
            return
        try:
            new_root.mkdir(parents=True)
        except Exception as e:
            QMessageBox.critical(self.window, "Could not create library", str(e))
            return
        self._refresh_library_combo(select=str(new_root))
        self.status.emit(f"Created library: {name}", 4000)

    def _on_combo_changed(self, _idx):
        path = self.cmb_library.currentData()
        self.session_state.set_library(path)

    def _on_session_library_changed(self, path):
        idx = self.cmb_library.findData(str(path)) if path else -1
        if idx != self.cmb_library.currentIndex():
            self.cmb_library.blockSignals(True)
            self.cmb_library.setCurrentIndex(idx)
            self.cmb_library.blockSignals(False)
        self.lbl_library_path.setText(str(path) if path else "No library selected.")
        self._refresh_summary()

    # ── mode buttons ─────────────────────────────────────────────────────────
    def _go_advanced(self):
        """Advanced mode is every page as it exists today - there's
        nothing to switch on, just somewhere sensible to land. Simple
        mode (a guided pipeline on top of these same pages) is a planned
        follow-up, disabled here until it exists rather than a button
        that goes nowhere."""
        self.window.openPanel("setup_deploy")

    # ── new session ──────────────────────────────────────────────────────────
    def _new_session(self):
        reply = QMessageBox.warning(
            self.window, "New session",
            "Starting a new session clears the selected library here and "
            "on every page that follows it. Anything already saved to "
            "disk (processed files, annotations, deployed models, "
            "reports) is untouched - this only resets which library the "
            "app is currently pointed at.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.session_state.new_session()
        self.status.emit("New session started.", 4000)

    # ── resume summary ──────────────────────────────────────────────────────
    def _refresh_summary(self):
        root = self.session_state.library
        if root is None:
            self.card_status.set_title("Nothing selected yet")
            self.card_status.set_rows([])
            return

        self.card_status.set_title(root.name)
        rows = []

        deployments = di.deployments(root)
        treatments = di.treatments(root)
        rows.append(("Deployments", len(deployments) or "None recorded"))
        rows.append(("Treatments", len(treatments) or "None recorded"))

        index_df = di.read_index(root)
        if index_df is not None:
            sensors = di.sensor_rows(index_df)
            n = len(sensors)
            bad = 0
            if di.BAD_SENS_COL in sensors.columns:
                bad = int((sensors[di.BAD_SENS_COL].astype(str).str.strip()
                          .str.upper() == "Y").sum())
            rows.append(("Sensors indexed",
                        f"{n} ({bad} flagged bad)" if bad else n))
        else:
            rows.append(("Sensors indexed", "Not processed yet"))

        dataset_path = root / "processed_sens_data" / "model_features.csv"
        if dataset_path.exists():
            try:
                n_rows = len(pd.read_csv(dataset_path, usecols=[0]))
                rows.append(("Dataset built", f"Yes ({n_rows} rows)"))
            except Exception:
                rows.append(("Dataset built", "Yes"))
        else:
            rows.append(("Dataset built", "Not yet"))

        out_dir = self.session_state.output_dir(create=False)
        if out_dir is not None and out_dir.exists():
            n_items = sum(1 for _ in out_dir.iterdir())
            rows.append((OUTPUT_DIR_NAME, f"{n_items} item(s)"))
        else:
            rows.append((OUTPUT_DIR_NAME, "Nothing generated yet"))

        self.card_status.set_rows(rows)
