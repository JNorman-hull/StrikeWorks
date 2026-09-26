# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Simple mode: a guided, one-window walkthrough of Deploy > Process >
Validate > Predict > Report, and the first thing the app shows (main.py
opens it on launch). Layout per simple_spec/*.png.

Each step uses the same pieces as the full app:

  Deploy    - deployment_editor.DeploymentEditor (Create and edit
              deployment).
  Process   - inventory_widgets.FileInventory (Raw data processing).
  Validate  - validation_core (Annotate): Auto process all, the weak-HIG
              flag that points at the sensors worth a second look, user
              validation, Save and export.
  Predict   - the shared PredictionState (window.ml_prediction_page.state).
  Report    - ml_figures / ml_report.

The nadir line on the signal preview can be dragged, so a flagged sensor
can be corrected by hand and re-saved with Save + Next.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLayout,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import deployment_index as di
from . import ml_figures, ml_report, settings, win_utils
from . import validation_core as vc
from .deployment_editor import DeploymentEditor
from .inventory_widgets import FileInventory
from .cards import MetaCard, RingCard, Spinner
from .layout import Section
from .theme import (
    ACCENT, ACCENT_BUTTON, BAD, MUTED, OK, PALETTE, PINK, TEXT, WARN,
    muted_label,
)
from .plot_style import add_export_button, build_export_data
from .startup import ICON_PATH

_WIN_SEC = vc.WIN_SEC
_IMAGES_DIR = Path(__file__).parent.parent / "images" / "images"

# The left step list: (label, indent level, stack page index or None).
# None means a non-clickable group heading - "Process" and "Report" are
# each a heading over two real pages (file inventory/validate,
# report-view/download) rather than a page of their own.
_LIST_ITEMS = [
    ("Home",     0, 0),
    ("Deploy",   0, 1),
    ("Process",  0, None),
    ("Process",  1, 2),
    ("Validate", 1, 3),
    ("Predict",  0, 4),
    ("Report",   0, None),
    ("Output",   1, 5),
    ("Download", 1, 6),
]

# pages that show the big logo, so not the small bottom-left one
_NO_SMALL_LOGO_PAGES = {0, 6}

# the guidance line above Back/Next/Close, per stack page index
_GUIDANCE = {
    0: "Pressing next continues with blade strike prediction…",
    1: "Create a deployment and add data to continue…",
    2: "Select files and process them to continue…",
    3: "Pressing next continues with data saved here or an existing dataset…",
    4: "Continue to plot and export data…",
    5: "Review the report, then continue to download…",
    6: "Download your report to finish, or close.",
}


class SimpleModeDialog(QDialog):
    """Simple mode's window. Built once and reopened with `exec()`;
    "Development toolkit" (`_go_development_toolkit`) switches to the full
    app."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("StrikeWorks")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        # resizable; 640 high fits a 1366x768 screen with the taskbar and
        # title bar
        self.resize(1340, 640)
        self.setMinimumSize(900, 560)
        # a maximum as well: while the window is dragged by its title bar,
        # Windows sizes it against Qt's minimum/maximum, and without one
        # it can jump to a page's larger natural size mid-drag
        self.setMaximumSize(1600, 900)
        # the app's first visible window, and its owner (MainWindow) is
        # hidden, so it needs the taskbar fix (win_utils.py)
        win_utils.ensure_taskbar_button(self)
        # window-modal, so the dev console stays usable
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self._lib_root = window.session_state.library
        self._validate_files = []       # [{"stem","path"}]
        self._cur_validate_stem = None
        # the rest of the currently-loaded sensor's data - None until a
        # sensor is loaded, so anything reading them first (the Export
        # button) behaves like "nothing loaded yet"
        self._cur_validate_df = None
        self._cur_validate_time = None
        self._cur_validate_pres = None
        self._cur_validate_hig = None
        self._cur_validate_nadir_idx = None
        self._loaded_nadir_idx = None
        self._auto_process_thread = None
        self._validate_dirty = False    # written since the last Save and export
        self._advance_after_export = False   # "Save and continue" on the unsaved-data prompt
        self.went_to_dev_toolkit = False
        self._built_dataset_path = None
        self._win_sec = _WIN_SEC   # ROI window width - user-adjustable via cmb_window
        self._exporter = vc.DatasetExporter(self)
        self._exporter.finished.connect(self._on_extract_done)

        self._build()
        state = self.window.ml_prediction_page.state
        state.run_finished.connect(self._on_predict_finished)
        state.run_failed.connect(self._on_predict_failed)
        self.window.session_state.library_changed.connect(
            self._on_session_library_changed_simple)

    # ── top-level layout ────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)
        outer.setSpacing(0)
        # SetNoConstraint: the window's size follows the user, not the
        # current page's size hint (a queued resize could otherwise land
        # mid-drag)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        body = QHBoxLayout()
        body.setContentsMargins(5, 0, 5, 0)
        body.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        self.step_list = QListWidget()
        self.step_list.setSizePolicy(QSizePolicy.Policy.Fixed,
                                     QSizePolicy.Policy.Fixed)
        for label, indent, page in _LIST_ITEMS:
            item = QListWidgetItem(("    " if indent else "") + label)
            item.setData(Qt.ItemDataRole.UserRole, page)
            if page is None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.step_list.addItem(item)
        self.step_list.itemClicked.connect(self._on_step_clicked)
        # sized to exactly what the list needs
        fm = self.step_list.fontMetrics()
        width = max(fm.horizontalAdvance(("    " if i else "") + t)
                    for t, i, _p in _LIST_ITEMS) + 36
        self.step_list.setFixedWidth(width)
        height = (sum(self.step_list.sizeHintForRow(i)
                      for i in range(self.step_list.count()))
                 + 2 * self.step_list.frameWidth())
        self.step_list.setFixedHeight(height)
        left_col.addWidget(self.step_list)
        left_col.addStretch()
        body.addLayout(left_col)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.addStretch()
        btn_about = QPushButton("About")
        # not autoDefault: a dialog's first button otherwise becomes the
        # Enter default and is drawn highlighted
        btn_about.setAutoDefault(False)
        btn_about.setDefault(False)
        btn_about.clicked.connect(self._show_about)
        top_row.addWidget(btn_about)
        btn_settings = QPushButton("Settings")
        btn_settings.setAutoDefault(False)
        btn_settings.setDefault(False)
        btn_settings.setToolTip("Settings")
        btn_settings.clicked.connect(self.window.openSettings)
        top_row.addWidget(btn_settings)
        right_col.addLayout(top_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome_page())
        self.stack.addWidget(self._build_deployment_page())
        self.stack.addWidget(self._build_process_inventory_page())
        self.stack.addWidget(self._build_process_validate_page())
        self.stack.addWidget(self._build_predict_page())
        self.stack.addWidget(self._build_report_page())
        self.stack.addWidget(self._build_finished_page())
        right_col.addWidget(self.stack, stretch=1)
        body.addLayout(right_col, stretch=1)
        outer.addLayout(body, stretch=1)

        guidance_row = QHBoxLayout()
        guidance_row.setContentsMargins(10, 0, 10, 0)
        guidance_row.addStretch()
        self.lbl_guidance = QLabel("")
        self.lbl_guidance.setStyleSheet(f"color:{MUTED};font-style:italic;")
        guidance_row.addWidget(self.lbl_guidance)
        outer.addLayout(guidance_row)

        nav = QHBoxLayout()
        nav.setContentsMargins(10, 6, 10, 10)
        self.logo_h = self._make_logo("PyDracula_horizontal.png", width=160)
        if self.logo_h is not None:
            nav.addWidget(self.logo_h)
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self._go_next)
        self.btn_back = QPushButton("< Back")
        self.btn_back.clicked.connect(self._go_back)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        nav.addStretch()
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_next)
        nav.addWidget(btn_close)
        outer.addLayout(nav)

    def _show_about(self):
        from .about_dialog import AboutDialog
        AboutDialog(self).exec()

    @staticmethod
    def _make_logo(filename, width):
        """Loads an images/images/<filename> logo scaled to `width`, or
        None if it's missing - callers skip adding the widget rather than
        show a broken image."""
        path = _IMAGES_DIR / filename
        if not path.exists():
            return None
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        lbl = QLabel()
        lbl.setPixmap(pix.scaledToWidth(
            width, Qt.TransformationMode.SmoothTransformation))
        return lbl

    def showEvent(self, event):
        super().showEvent(event)
        self.went_to_dev_toolkit = False
        self.stack.setCurrentIndex(0)
        self._sync_step_highlight()
        self._lib_root = self.window.session_state.library
        # (the Deploy editor refreshes itself whenever it's shown)

    # ── navigation ───────────────────────────────────────────────────────────
    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 1:
            if not self.editor.confirm_leave(self):
                return
            self._refresh_process_inventory()
        elif idx == 2:
            self._refresh_validate_step()
        elif idx == 3:
            if not self._confirm_leave_validate():
                return
            action = self._confirm_unsaved_dataset()
            if action == "cancel":
                return
            if action == "save":
                # advancing happens once the export actually finishes -
                # _on_extract_done, guarded by _advance_after_export
                self._advance_after_export = True
                self._save_and_export()
                return
            self._refresh_predict_step()
        elif idx == 4:
            self._refresh_report_step()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._sync_step_highlight()

    def _confirm_unsaved_dataset(self):
        """Leaving Validate with changes not yet exported (Predict would
        use the last export). Returns "proceed", "save" (Save and continue:
        _on_extract_done moves on once the export finishes) or "cancel"."""
        if self._built_dataset_path is not None and not self._validate_dirty:
            return "proceed"
        box = QMessageBox(self.window)
        box.setWindowTitle("Unsaved processed data")
        box.setText("Processed data not saved or has unsaved changes. Continue?")
        btn_save = box.addButton("Save and continue",
                                 QMessageBox.ButtonRole.AcceptRole)
        btn_continue = box.addButton("Continue",
                                     QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_save:
            return "save"
        if clicked is btn_continue:
            return "proceed"
        return "cancel"

    def _confirm_leave_validate(self):
        """Asks before leaving Validate with flagged sensors unreviewed
        (the rest can be trusted). True to go on, False to stay."""
        _auto, user_validated, flagged, _bad = self._validation_status()
        outstanding = [f for f in self._validate_files
                       if f["stem"] in flagged and f["stem"] not in user_validated]
        if not outstanding:
            return True
        reply = QMessageBox.question(
            self.window, "Sensors flagged for review",
            f"Caution, {len(outstanding)}/{len(flagged)} flagged sensors "
            "still need user-validation. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._sync_step_highlight()

    def _on_step_clicked(self, item):
        page = item.data(Qt.ItemDataRole.UserRole)
        if page is None:
            self._sync_step_highlight()
            return   # a group heading ("Process"/"Report") - not clickable
        if (self.stack.currentIndex() == 1 and page != 1
                and not self.editor.confirm_leave(self)):
            self._sync_step_highlight()
            return
        if page == 2:
            self._refresh_process_inventory()
        elif page == 3:
            self._refresh_validate_step()
        elif page == 4:
            self._refresh_predict_step()
        elif page == 5:
            self._refresh_report_step()
        self.stack.setCurrentIndex(page)
        self._sync_step_highlight()

    def _sync_step_highlight(self):
        page = self.stack.currentIndex()
        self.step_list.blockSignals(True)
        target_row = next(
            (i for i in range(self.step_list.count())
             if self.step_list.item(i).data(Qt.ItemDataRole.UserRole) == page),
            -1)
        self.step_list.setCurrentRow(target_row)
        self.step_list.blockSignals(False)
        self.btn_back.setEnabled(page > 0)
        last_page = self.stack.count() - 1
        self.btn_next.setText(
            "Finish" if page == last_page - 1 else "Next >")
        self.btn_next.setEnabled(page != last_page)
        if self.logo_h is not None:
            self.logo_h.setVisible(page not in _NO_SMALL_LOGO_PAGES)
        self.lbl_guidance.setText(_GUIDANCE.get(page, ""))

    # ── page 0: welcome ──────────────────────────────────────────────────────
    def _build_welcome_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        logo = self._make_logo("PyDracula_vertical.png", width=220)
        if logo is not None:
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(logo)
        subtitle = QLabel("Deploy. Process. Predict.")
        subtitle.setStyleSheet(f"color:{MUTED};font-size:28px;font-style:italic;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_blade_strike = QPushButton("Blade strike\n(next)")
        btn_blade_strike.setMinimumSize(140, 44)
        btn_blade_strike.setStyleSheet(ACCENT_BUTTON)
        btn_blade_strike.clicked.connect(self._go_next)
        btn_row.addWidget(btn_blade_strike)
        btn_dev_toolkit = QPushButton("Development\ntoolkit")
        btn_dev_toolkit.setMinimumSize(140, 44)
        btn_dev_toolkit.setStyleSheet(
            f"QPushButton{{background-color:{BAD};color:#ffffff;"
            "border-radius:5px;font-weight:bold;}")
        btn_dev_toolkit.clicked.connect(self._go_development_toolkit)
        btn_row.addWidget(btn_dev_toolkit)
        btn_row.addStretch()
        v.addSpacing(20)
        v.addLayout(btn_row)

        v.addStretch()
        return page

    def _go_development_toolkit(self):
        """Open the full app in Advanced mode (the same entry as Home's
        Advanced mode button), then close this window.
        `went_to_dev_toolkit` tells main.py not to quit when it closes."""
        self.went_to_dev_toolkit = True
        self.window.home_page._go_advanced()
        self.window.show()
        self.reject()

    # ── page 1: deployment ───────────────────────────────────────────────────
    def _build_deployment_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Build a sensor deployment by adding a test site, "
                       "treatment condition and sensor files…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        title.setWordWrap(True)
        v.addWidget(title)
        # the same editor as Create and edit deployment
        self.editor = DeploymentEditor(self.window, self.window.session_state)
        v.addWidget(self.editor, stretch=1)
        return page

    def _on_session_library_changed_simple(self, path):
        self._lib_root = path

    # ── page 2: process (file inventory) ────────────────────────────────────
    def _build_process_inventory_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(8)
        title = QLabel("Process, validate and segment sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)
        # the same inventory as Raw data processing
        self.inventory = FileInventory()
        v.addWidget(self.inventory, stretch=1)
        return page

    def _refresh_process_inventory(self):
        """Every recording in the deployment chosen on Deploy - all of its
        treatments and runs at once."""
        self._lib_root = self.window.session_state.library
        self.editor.ensure_loaded()   # e.g. jumped here without visiting Deploy
        self.inventory.set_source(self._lib_root, self.editor.deployment_dir())
        self.inventory.refresh()      # in the background, behind a spinner

    # ── page 3: process (validate/segment) ──────────────────────────────────
    def _build_process_validate_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(8)
        title = QLabel("Process, validate and segment sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        # a fixed-width list column (no splitter, per simple_spec/Validate.png)
        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(10)

        left = QWidget()
        left.setFixedWidth(240)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.validate_list = QListWidget()
        # the highlighted sensor is the loaded one - by mouse or arrow keys
        self.validate_list.currentItemChanged.connect(
            self._on_validate_current_changed)
        lv.addWidget(self.validate_list, stretch=1)

        mark_row = QHBoxLayout()
        self.btn_mark = QPushButton("Mark bad")
        self.btn_mark.setStyleSheet(f"color:{BAD};font-weight:bold;")
        self.btn_mark.clicked.connect(self._mark_good_bad)
        mark_row.addWidget(self.btn_mark)
        self.chk_show_bad = QCheckBox("Show bad")
        self.chk_show_bad.toggled.connect(self._refresh_validate_list)
        mark_row.addWidget(self.chk_show_bad)
        lv.addLayout(mark_row)

        self.lbl_validated_count = QLabel("")
        self.lbl_validated_count.setStyleSheet(f"color:{TEXT};")
        lv.addWidget(self.lbl_validated_count)
        lbl_legend = QLabel(vc.legend_html(OK, WARN, BAD, ACCENT, TEXT))
        lbl_legend.setStyleSheet(f"color:{MUTED};")
        lbl_legend.setWordWrap(True)
        lv.addWidget(lbl_legend)

        self.btn_save_next_v = QPushButton(f"Save + Next  ({vc.SAVE_NEXT_KEYS})")
        self.btn_save_next_v.setToolTip(
            "Save this sensor's window as reviewed (clears its flag) and go "
            f"to the next sensor in the list - {vc.SAVE_NEXT_KEYS}. The "
            "arrow keys move through the list.")
        self.btn_save_next_v.clicked.connect(self._save_and_next_validate)
        lv.addWidget(self.btn_save_next_v)
        self.btn_reset_v = QPushButton("Reset current sensor")
        self.btn_reset_v.clicked.connect(self._reset_current_validate)
        lv.addWidget(self.btn_reset_v)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        add_export_button(toolbar, self._validate_export_data, self.window,
                          file_stub="validate_signal")
        rv.addLayout(toolbar)
        self._pw_validate = pg.PlotWidget()
        pi = self._pw_validate.plotItem
        pi.setLabel("bottom", "Time (s)")
        pi.setLabel("left", "Pressure (kPa)")
        self._vb2_validate = pg.ViewBox()
        pi.scene().addItem(self._vb2_validate)
        pi.getAxis("right").linkToView(self._vb2_validate)
        self._vb2_validate.setXLink(pi)
        pi.showAxis("right")
        pi.getAxis("right").setLabel("HIG acc mag (g)")
        pi.vb.sigResized.connect(self._sync_vb2_validate)
        self._validate_region = pg.LinearRegionItem(
            movable=False, brush=pg.mkBrush(120, 170, 255, 35),
            pen=pg.mkPen(120, 170, 255, 90))
        pi.addItem(self._validate_region)
        self._validate_nadir_line = pg.InfiniteLine(
            angle=90, movable=True,
            pen=pg.mkPen(color=(255, 220, 0), width=2), label="Nadir",
            labelOpts={"position": 0.92, "color": (180, 150, 0)})
        self._validate_nadir_line.sigPositionChanged.connect(
            self._on_validate_nadir_moved)
        pi.addItem(self._validate_nadir_line)
        self._validate_curve = None
        self._validate_curve2 = None
        rv.addWidget(self._pw_validate, stretch=1)
        split.addWidget(right, stretch=1)
        v.addLayout(split, stretch=1)

        bottom = QHBoxLayout()
        auto_col = QVBoxLayout()
        auto_col.setSpacing(2)
        auto_row = QHBoxLayout()
        self.btn_auto_process_all = QPushButton("Auto process all")
        self.btn_auto_process_all.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.btn_auto_process_all.clicked.connect(self._auto_process_all)
        auto_row.addWidget(self.btn_auto_process_all)
        self._auto_spinner = Spinner(size=20)
        self._auto_spinner.setVisible(False)
        auto_row.addWidget(self._auto_spinner)
        auto_col.addLayout(auto_row)
        auto_col.addWidget(muted_label(
            "Tip: press Auto process all first, then check the sensors "
            "it flagged for review.", wrap=True))
        bottom.addLayout(auto_col)
        bottom.addWidget(muted_label("ROI window:", wrap=True))
        self.cmb_window = QComboBox()
        self.cmb_window.currentIndexChanged.connect(self._on_validate_win_size_changed)
        bottom.addWidget(self.cmb_window)
        self._fill_validate_window_combo()
        self.lbl_all_validated = QLabel("")
        self.lbl_all_validated.setStyleSheet(f"color:{MUTED};")
        bottom.addWidget(self.lbl_all_validated)
        bottom.addStretch()
        self.btn_save_export = QPushButton("Save and export")
        self.btn_save_export.setStyleSheet(f"color:{BAD};font-weight:bold;")
        self.btn_save_export.clicked.connect(self._save_and_export)
        bottom.addWidget(self.btn_save_export)
        v.addLayout(bottom)
        self._save_next_shortcut = vc.install_save_next_shortcut(
            page, self.validate_list, self._save_and_next_validate)
        return page

    def _sync_vb2_validate(self):
        pi = self._pw_validate.plotItem
        self._vb2_validate.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2_validate.linkedViewChanged(pi.vb, self._vb2_validate.XAxis)

    def _validate_export_data(self):
        """Feeds the "Export ▾" toolbar button (plot_style.add_export_button,
        the same one Advanced mode's own Validate page uses) - None while
        nothing is loaded yet, matching build_export_data's own contract."""
        time = self._cur_validate_time
        if time is None or not len(time):
            return None
        return build_export_data(
            time, "Pressure (kPa)", self._cur_validate_pres,
            "HIG acc mag (g)", self._cur_validate_hig,
            (float(time[0]), float(time[-1])))

    # -- validate step logic (validation_core.py, shared with Annotate) ----
    def _validate_index(self):
        return di.read_index(self._lib_root) if self._lib_root else None

    def _save_validate_index(self, df):
        vc.write_index(self._lib_root, df)

    def _refresh_validate_step(self):
        self._lib_root = self.window.session_state.library
        self._validate_files = vc.processed_sensor_files(self._lib_root)
        self._refresh_validate_list()

    def _validation_status(self):
        """(auto_validated, user_validated, flagged, bad) stem sets from
        the current index - the one place every Validate-step method reads
        these from, so the list, the counts, Jump, and the Next
        confirmation can't quietly disagree with each other."""
        return vc.validation_status(self._validate_index())

    def _refresh_validate_list(self):
        status = self._validation_status()
        bad = status[3]
        show_bad = self.chk_show_bad.isChecked()

        # flagged-and-unreviewed first, otherwise in the usual order
        ordered = sorted(self._validate_files,
                         key=lambda f: not vc.needs_review(f["stem"], status))

        # rebuilt with signals blocked - the loaded sensor is re-highlighted
        # afterwards, not reloaded (which would drop an unsaved nadir move)
        self.validate_list.blockSignals(True)
        self.validate_list.clear()
        for f in ordered:
            stem = f["stem"]
            if stem in bad and not show_bad:
                continue
            # plain stem, no decoration - colour alone marks the state
            # (item.text() == stem lookups rely on it)
            item = QListWidgetItem(stem)
            colour = vc.status_colour(stem, status, OK, WARN, BAD, ACCENT)
            if colour:
                item.setForeground(QColor(colour))
            self.validate_list.addItem(item)
            if stem == self._cur_validate_stem:
                self.validate_list.setCurrentItem(item)
        self.validate_list.blockSignals(False)

        stems = [f["stem"] for f in self._validate_files]
        self.lbl_validated_count.setText(vc.counts_text(stems, status))
        self.lbl_all_validated.setText(
            "All sensors validated" if vc.all_validated(stems, status) else "")

    def _on_validate_current_changed(self, current, _previous):
        if current is not None and current.text() != self._cur_validate_stem:
            self._load_validate_file(current.text())

    def _load_validate_file(self, stem):
        match = next((f for f in self._validate_files if f["stem"] == stem), None)
        if match is None:
            return
        try:
            df = pd.read_csv(match["path"], low_memory=False)
        except Exception as e:
            QMessageBox.warning(self.window, "Load failed", str(e))
            return
        self._cur_validate_stem = stem
        self._cur_validate_df = df
        (self._cur_validate_time, self._cur_validate_pres,
         self._cur_validate_hig) = vc.signals(df)
        self._cur_validate_nadir_idx = vc.detect_nadir_idx(
            stem, df, self._cur_validate_time, self._cur_validate_pres,
            self._validate_index())
        # the nadir as loaded: Save compares against it to record whether
        # the user moved it
        self._loaded_nadir_idx = self._cur_validate_nadir_idx
        self._draw_validate_plot()
        # select it in the list too (_on_validate_current_changed sees
        # it's already loaded)
        for i in range(self.validate_list.count()):
            if self.validate_list.item(i).text() == stem:
                self.validate_list.setCurrentRow(i)
                break

    def _update_validate_region(self, t: float):
        self._validate_region.setRegion(
            (t - self._win_sec / 2, t + self._win_sec / 2))

    def _fill_validate_window_combo(self):
        """Offer 100-1000 ms, defaulting to this page's own width - same
        convention as Advanced mode's Validate page (page_validate.py's
        own _fill_window_combo)."""
        cmb = self.cmb_window
        want = int(round(self._win_sec * 1000))
        options = sorted(set(range(100, 1001, 100)) | {want})
        cmb.blockSignals(True)
        cmb.clear()
        for ms in options:
            cmb.addItem(f"{ms} ms", ms)
        cmb.setCurrentIndex(max(0, cmb.findData(want)))
        cmb.blockSignals(False)

    def _on_validate_win_size_changed(self):
        ms = self.cmb_window.currentData()
        if ms is None:
            return
        self._win_sec = ms / 1000.0
        if self._cur_validate_time is not None and self._cur_validate_nadir_idx is not None:
            self._update_validate_region(
                float(self._cur_validate_time[self._cur_validate_nadir_idx]))

    def _on_validate_nadir_moved(self):
        """The nadir line is user-draggable (movable=True) so any sensor -
        already validated or not - can be corrected: dragging snaps to the
        nearest sample and moves the ROI window preview with it; nothing
        is written to disk until Save + Next."""
        time = self._cur_validate_time
        if time is None:
            return
        raw_t = self._validate_nadir_line.value()
        idx = int(np.argmin(np.abs(time - raw_t)))
        self._cur_validate_nadir_idx = idx
        t_snap = float(time[idx])
        self._validate_nadir_line.blockSignals(True)
        self._validate_nadir_line.setPos(t_snap)
        self._validate_nadir_line.blockSignals(False)
        self._update_validate_region(t_snap)

    def _draw_validate_plot(self):
        pi = self._pw_validate.plotItem
        if self._validate_curve is not None:
            pi.removeItem(self._validate_curve)
            self._validate_curve = None
        if self._validate_curve2 is not None:
            self._vb2_validate.removeItem(self._validate_curve2)
            self._validate_curve2 = None
        time = self._cur_validate_time
        if self._cur_validate_pres is not None:
            self._validate_curve = self._pw_validate.plot(
                time, self._cur_validate_pres, pen=pg.mkPen(TEXT, width=1))
        if self._cur_validate_hig is not None:
            self._validate_curve2 = pg.PlotCurveItem(
                pen=pg.mkPen("#ff5555", width=1))
            self._vb2_validate.addItem(self._validate_curve2)
            self._validate_curve2.setData(time, self._cur_validate_hig)
            self._vb2_validate.enableAutoRange("y", True)
        t = float(time[self._cur_validate_nadir_idx])
        self._validate_nadir_line.blockSignals(True)
        self._validate_nadir_line.setPos(t)
        self._validate_nadir_line.blockSignals(False)
        self._update_validate_region(t)
        pi.enableAutoRange("x", True)
        pi.enableAutoRange("y", True)

    def _mark_good_bad(self):
        """Always marks the current sensor Bad - marking bad doesn't
        un-validate it (Save and export excludes bad sensors from the
        dataset separately, via the same bad_sens=N filter every other
        dataset-building path already uses)."""
        if not self._cur_validate_stem or self._lib_root is None:
            return
        index_df = self._validate_index()
        if index_df is None or "file" not in index_df.columns:
            return
        mask = index_df["file"] == self._cur_validate_stem
        if not mask.any():
            new_row = pd.DataFrame([{"file": self._cur_validate_stem}])
            index_df = pd.concat([index_df, new_row], ignore_index=True)
            mask = index_df["file"] == self._cur_validate_stem
        if di.BAD_SENS_COL not in index_df.columns:
            index_df[di.BAD_SENS_COL] = ""
        index_df[di.BAD_SENS_COL] = index_df[di.BAD_SENS_COL].astype(object)
        index_df.loc[mask, di.BAD_SENS_COL] = "Y"
        self._save_validate_index(index_df)
        self._validate_dirty = True
        self.lbl_all_validated.setText(f"{self._cur_validate_stem} marked Bad.")
        self._refresh_validate_list()

    def _save_and_next_validate(self):
        """Save + Next (Ctrl+V): saves the window as reviewed by a person -
        which clears the sensor's flag (it turns green and leaves the
        flagged group at the top) - then loads the next sensor in the
        list (validation_core.next_after_save)."""
        if not self._cur_validate_stem:
            return
        index_df = self._validate_index()
        if index_df is None:
            return
        stem = self._cur_validate_stem
        order = [self.validate_list.item(i).text()
                 for i in range(self.validate_list.count())]
        nadir_changed = (self._loaded_nadir_idx is not None
                         and self._cur_validate_nadir_idx != self._loaded_nadir_idx)
        index_df = vc.save_window(
            self._lib_root, index_df, stem, self._cur_validate_df,
            self._cur_validate_nadir_idx, self._win_sec,
            user_validated=True, nadir_changed=nadir_changed)
        self._validate_dirty = True
        self._save_validate_index(index_df)
        self._refresh_validate_list()
        target = vc.next_after_save(order, stem, self._validation_status())
        if target is not None:
            self._load_validate_file(target)
        else:
            self.lbl_all_validated.setText(
                f"{stem} saved - end of the list.")
        # keep the arrow keys / Ctrl+V on the list after a button click
        self.validate_list.setFocus()

    def _reset_current_validate(self):
        if self._cur_validate_stem:
            self._load_validate_file(self._cur_validate_stem)

    def _auto_process_all(self):
        """Starts Auto process all in the background (validation_core.
        AutoProcessThread) and returns the thread - or None with nothing
        to do. Callers that need to wait (the demo runner) wait on its
        `done`."""
        if self._lib_root is None or not self._validate_files:
            return None
        if (self._auto_process_thread is not None
                and self._auto_process_thread.isRunning()):
            return self._auto_process_thread
        self.btn_auto_process_all.setEnabled(False)
        self.btn_save_export.setEnabled(False)
        self._auto_spinner.start()
        self.lbl_all_validated.setText("Auto-processing…")
        self._auto_process_thread = vc.AutoProcessThread(
            self._lib_root, self._win_sec, self._validate_files,
            self._validate_index())
        self._auto_process_thread.progress.connect(self._on_auto_process_progress)
        self._auto_process_thread.done.connect(self._on_auto_process_done)
        self._auto_process_thread.start()
        return self._auto_process_thread

    def _on_auto_process_progress(self, done, total):
        self.lbl_all_validated.setText(f"Auto-processing… {done}/{total}")

    def _on_auto_process_done(self, index_df, n_done):
        self._auto_spinner.stop()
        self.btn_auto_process_all.setEnabled(True)
        self.btn_save_export.setEnabled(True)
        self._validate_dirty = True
        self._save_validate_index(index_df)
        self._refresh_validate_list()
        status = self._validation_status()
        n_flagged = sum(1 for f in self._validate_files if f["stem"] in status[2])
        self.lbl_all_validated.setText(
            f"Auto-processed {n_done} sensor(s), {n_flagged} flagged for review.")
        # straight into the review: the first flagged sensor, list focused
        # for the arrow keys and Ctrl+V
        pending = [self.validate_list.item(i).text()
                   for i in range(self.validate_list.count())
                   if vc.needs_review(self.validate_list.item(i).text(), status)]
        if pending and not vc.needs_review(self._cur_validate_stem or "", status):
            self._load_validate_file(pending[0])
        self.validate_list.setFocus()

    def _save_and_export(self):
        if self._lib_root is None or self._exporter.running:
            return
        self.btn_save_export.setEnabled(False)
        self.lbl_all_validated.setText("Building dataset…")
        self._exporter.start(self._lib_root,
                             self.editor.deployment_id() or self._lib_root.name)

    def _on_extract_done(self, df, path, message):
        self.btn_save_export.setEnabled(True)
        self.lbl_all_validated.setText(message)
        if df is None:
            self._advance_after_export = False
            return
        self._built_dataset_path = path
        self._validate_dirty = False
        # straight into the shared PredictionState
        self.window.ml_prediction_page.on_dataset_ready(
            df, f"Simple mode - {path.stem}")
        if self._advance_after_export:
            # "Save and continue" (_go_next) moves on once the export is done
            self._advance_after_export = False
            self._refresh_predict_step()
            self.stack.setCurrentIndex(4)
            self._sync_step_highlight()

    # ── page 4: predict ──────────────────────────────────────────────────────
    def _build_predict_page(self):
        """One centred column (simple_spec/Predict.png): the dataset card,
        Load / Run, the status line, then the "Predicted strikes" and
        "Strike classes" rings."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Predict blade strike from sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        # equal stretch above and below keeps the block centred
        v.addStretch(1)

        grp_ds = Section("Dataset")
        grp_ds.setMaximumWidth(430)
        dv = QVBoxLayout(grp_ds)
        self.card_predict_dataset = MetaCard("Curated sensor dataset")
        dv.addWidget(self.card_predict_dataset)
        ds_row = QHBoxLayout()
        ds_row.addStretch()
        ds_row.addWidget(grp_ds)
        ds_row.addStretch()
        v.addLayout(ds_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_load_dataset = QPushButton("Load dataset CSV…")
        self.btn_load_dataset.setMinimumSize(180, 40)
        self.btn_load_dataset.clicked.connect(self._load_dataset_csv)
        btn_row.addWidget(self.btn_load_dataset)
        self.btn_run_predict = QPushButton("Run prediction")
        self.btn_run_predict.setMinimumSize(180, 40)
        self.btn_run_predict.clicked.connect(self._run_predict)
        btn_row.addWidget(self.btn_run_predict)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self.lbl_predict_status = QLabel("")
        self.lbl_predict_status.setStyleSheet(f"color:{MUTED};")
        self.lbl_predict_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl_predict_status)

        self.lbl_predict_done = QLabel("")
        self.lbl_predict_done.setStyleSheet(f"color:{OK};font-weight:bold;")
        self.lbl_predict_done.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl_predict_done)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.addStretch()
        self.card_predicted_strikes = RingCard("Predicted strikes")
        cards_row.addWidget(self.card_predicted_strikes)
        self.card_strike_classes = RingCard("Strike classes")
        cards_row.addWidget(self.card_strike_classes)
        cards_row.addStretch()
        v.addLayout(cards_row)

        v.addStretch(1)
        return page

    def _refresh_predict_step(self):
        state = self.window.ml_prediction_page.state
        self._auto_select_model(state)
        self._refresh_predict_dataset_card()
        self.btn_run_predict.setEnabled(state.dataset_df is not None)

    def _auto_select_model(self, state):
        """Pick the models in the models folder: the one pinned in
        Settings, else 'binary1' / 'multiclass1', else the newest. Rescans
        each time, since an earlier load may have pointed `state.models_dir`
        elsewhere."""
        models_dir = settings.get_models_dir()
        state.load_models_from_dir(models_dir)

        bin_candidates = state.bin_candidates
        if bin_candidates:
            default = settings.get_default_model()
            if default is not None and Path(default) in bin_candidates:
                chosen = Path(default)
            else:
                chosen = (next((p for p in bin_candidates if p.stem == "binary1"),
                               None)
                          or max(bin_candidates, key=lambda p: p.stat().st_mtime))
            if state.bin_model_path != chosen:
                state.select_bin_model(chosen)

        mc_candidates = state.mc_candidates
        if mc_candidates:
            mc_default = settings.get_default_mc_model()
            if mc_default is not None and Path(mc_default) in mc_candidates:
                mc_chosen = Path(mc_default)
            else:
                mc_chosen = (next((p for p in mc_candidates
                                   if p.stem == "multiclass1"), None)
                             or max(mc_candidates, key=lambda p: p.stat().st_mtime))
            if state.mc_model_path != mc_chosen:
                state.select_mc_model(mc_chosen)

    def _load_dataset_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Load dataset CSV", str(Path.cwd()),
            "CSV files (*.csv)")
        if not path:
            return
        state = self.window.ml_prediction_page.state
        ok, msg = state.load_dataset_csv(path)
        self.lbl_predict_status.setText(msg)
        self._refresh_predict_dataset_card()
        self.btn_run_predict.setEnabled(ok)

    def _refresh_predict_dataset_card(self):
        state = self.window.ml_prediction_page.state
        m = state.dataset_meta
        if not m:
            self.card_predict_dataset.set_rows([("Dataset", "No dataset loaded")])
            return
        sr = m.get("sampling_rate_hz")
        seq = None
        if m.get("seq_len_min") is not None:
            if m["seq_len_min"] == m["seq_len_max"]:
                seq = f"{m['seq_len_max']} samples"
                if sr:
                    seq += f" ({m['seq_len_max'] / sr * 1000:.0f} ms)"
            else:
                seq = f"{m['seq_len_min']}-{m['seq_len_max']} samples (varying)"
        req = set(state.required_channels())
        n_chan_present = (len([c for c in m.get("columns", []) if c in req])
                          if req else None)
        self.card_predict_dataset.set_rows([
            ("Dataset",       m.get("name")),
            ("Source",        state.dataset_source),
            ("Recordings",    m.get("n_files")),
            ("Sensor rows",   f"{m.get('n_rows'):,}" if m.get("n_rows") else None),
            ("Treatments",    f"{len(m['treatments'])} "
                              f"({', '.join(m['treatments'])})"
                              if m.get("treatments") else None),
            ("Sampling rate", f"{sr} Hz" if sr else None),
            ("Window length", seq),
            ("Model channels",
             f"{n_chan_present}/{len(req)} present" if req else None),
            ("Annotations",   f"ground-truth labels present "
                              f"({m['annotation_column']})"
                              if m.get("annotated") else "none"),
        ])

    def _run_predict(self):
        state = self.window.ml_prediction_page.state
        self.btn_run_predict.setEnabled(False)
        self.lbl_predict_status.setText("Running…")
        self.lbl_predict_status.setStyleSheet(f"color:{ACCENT};")
        state.run_prediction()

    def _on_predict_finished(self):
        state = self.window.ml_prediction_page.state
        self.btn_run_predict.setEnabled(True)
        meta = state.run_meta
        n = meta.get("n_files", 0)
        self.lbl_predict_status.setStyleSheet(f"color:{OK};")
        self.lbl_predict_status.setText(f"Predicting {n} recordings… done.")
        self.lbl_predict_done.setText("Blade strike predicted")
        df = state.summary
        if df is not None and len(df):
            n_total = int(df["n"].sum())
            n_strike = int(df["n_strike"].sum())
            self.card_predicted_strikes.set_segments([
                ("Strike", n_strike, PINK),
                ("No strike", n_total - n_strike, PALETTE[0]),
            ])

        mc_run = meta.get("mode") == "multiclass"
        have_classes = (mc_run and df is not None and len(df) and state.class_names
                        and all(f"n_{cn}" in df.columns for cn in state.class_names))
        self.card_strike_classes.setVisible(bool(have_classes))
        if have_classes:
            self.card_strike_classes.set_segments([
                (cn, int(df[f"n_{cn}"].sum()), PALETTE[i % len(PALETTE)])
                for i, cn in enumerate(state.class_names)
            ])
        else:
            self.card_strike_classes.clear()

    def _on_predict_failed(self, msg):
        self.btn_run_predict.setEnabled(True)
        self.lbl_predict_status.setStyleSheet(f"color:{BAD};")
        self.lbl_predict_status.setText(f"Prediction failed: {msg.splitlines()[-1]}")

    # ── page 5: report ───────────────────────────────────────────────────────
    def _build_report_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        title = QLabel("Report blade strike from sensor data…")
        title.setStyleSheet(f"color:{TEXT};font-weight:bold;")
        v.addWidget(title)

        self.tbl_report = QTableWidget(0, 0)
        self.tbl_report.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.tbl_report)

        grp_figs = Section("Prediction figures")
        fv = QHBoxLayout(grp_figs)
        self.fig_report_bin = Figure(figsize=(4.3, 3.2), dpi=100)
        self.canvas_report_bin = FigureCanvas(self.fig_report_bin)
        self.fig_report_mc = Figure(figsize=(4.3, 3.2), dpi=100)
        self.canvas_report_mc = FigureCanvas(self.fig_report_mc)
        for c in (self.canvas_report_bin, self.canvas_report_mc):
            c.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)
            fv.addWidget(c)
        v.addWidget(grp_figs, stretch=1)
        return page

    def _refresh_report_step(self):
        state = self.window.ml_prediction_page.state
        df = state.summary
        mc_run = state.run_meta.get("mode") == "multiclass"
        class_names = (state.class_names if mc_run and state.class_names
                       and df is not None
                       and all(f"n_{cn}" in df.columns for cn in state.class_names)
                       else [])
        headers = (["Treatment", "N", "Strikes", "No strike", "Strike rate",
                    "95% CI", "Mean prob", "Mean conf"] + list(class_names))
        self.tbl_report.setColumnCount(len(headers))
        self.tbl_report.setHorizontalHeaderLabels(headers)
        self.tbl_report.setRowCount(0 if df is None else len(df))
        if df is not None:
            for row, (_, r) in enumerate(df.iterrows()):
                n_strike = int(r["n_strike"])
                vals = [
                    str(r["treatment"]), str(int(r["n"])), str(n_strike),
                    str(int(r["n_no_strike"])),
                    f"{r['strike_rate'] * 100:.1f}%",
                    f"{r['ci_lo'] * 100:.1f}% - {r['ci_hi'] * 100:.1f}%",
                    f"{r['mean_prob']:.3f}", f"{r['mean_conf']:.3f}",
                ]
                for cn in class_names:
                    nc = int(r[f"n_{cn}"])
                    pct = nc / n_strike * 100 if n_strike else 0
                    vals.append(f"{nc} ({pct:.0f}%)")
                for col, val in enumerate(vals):
                    self.tbl_report.setItem(row, col, QTableWidgetItem(val))
        self.tbl_report.resizeColumnsToContents()

        ml_figures.draw_strike_rate(self.fig_report_bin, df, dark=True)
        self.canvas_report_bin.draw()
        ml_figures.draw_region(self.fig_report_mc, df,
                               class_names if mc_run else [], dark=True)
        self.canvas_report_mc.draw()

    def _processing_review_rows(self):
        """How Validate went for this library (validation_core) - fed
        into the *downloaded* report, not this wizard's Report step."""
        return vc.processing_review_rows(
            [f["stem"] for f in self._validate_files], self._validate_index())

    # ── page 6: finished ─────────────────────────────────────────────────────
    def _build_finished_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        logo = self._make_logo("PyDracula_vertical.png", width=220)
        if logo is not None:
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(logo)
        title = QLabel("Finished!")
        title.setStyleSheet(f"color:{TEXT};font-size:20px;font-style:italic;"
                            "font-weight:bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        btn_download = QPushButton("Download StrikeWorks report")
        btn_download.setMinimumHeight(36)
        btn_download.clicked.connect(self._download_report)
        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addWidget(btn_download)
        wrap.addStretch()
        v.addLayout(wrap)
        v.addStretch()
        return page

    def _download_report(self):
        state = self.window.ml_prediction_page.state
        if state.summary is None or state.run_id is None:
            QMessageBox.information(
                self.window, "Nothing to report",
                "Run a prediction first (Predict step).")
            return
        dirpath = QFileDialog.getExistingDirectory(
            self.window, "Download StrikeWorks report to folder",
            str(settings.get_output_dir()))
        if not dirpath:
            return
        try:
            out = ml_report.export_analysis(
                state, dirpath,
                processing_review=self._processing_review_rows())
        except Exception as e:
            QMessageBox.critical(self.window, "Download failed", str(e))
            return
        QMessageBox.information(
            self.window, "Report downloaded", f"Saved to:\n{out}")
