# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""StrikeWorks (once "Simple mode"): the app itself - a guided, one-window
walkthrough of Deploy > Process > Validate > Predict > Report, and the
first thing the app shows, maximised (main.py opens it on launch). The
Development toolkit (the full app, MainWindow) is behind the "Development
toolkit" button at its lower left and a password (`_DEV_TOOLKIT_PASSWORD`);
the Simple edition has no way in at all. Layout per simple_spec/*.png.

Each step uses the same pieces as the full app:

  Deploy    - deployment_editor.DeploymentEditor (Create and edit
              deployment).
  Process   - inventory_widgets.FileInventory (Raw data processing).
  Validate  - page_annotate.AnnotationPage (Validate and annotate, with
              StrikeWorks's saving): Auto process all, the weak-HIG flag
              that points at the sensors worth a second look, user
              validation, Save and export; the nadir line can be dragged,
              so a flagged sensor can be corrected by hand and re-saved
              with Save + Next.
  Predict   - the shared PredictionState (window.ml_prediction_page.state).
  Report    - ml_figures / ml_report.
"""

from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import (
    hig_peaks, ml_figures, ml_report, settings, severity,
    win_utils,
)
from . import validation_core as vc
from .canvas import FigureCanvas
from .deployment_editor import DeploymentEditor
from .edition import simple_only
from .inventory_widgets import FileInventory
from .cards import MetaCard, RingCard
from .layout import Section, scroll_area
from .page_annotate import AnnotationPage
from .tables import fill_acceleration_table
from .theme import (
    PALETTE, PINK, muted_label, style,
)
from .startup import ICON_PATH, logo_label

# the "Development toolkit" button's password: a door for the people who
# develop models, not security - it is in the source
_DEV_TOOLKIT_PASSWORD = "devmode_123"

# The left step list: (label, indent level, stack page index or None).
# None means a group heading - "Process" and "Report" are each a heading
# over two real pages (file inventory/validate, report-view/download)
# rather than a page of their own; clicking one opens its first sub-step.
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

# the steps in bold - the tagline's four
_BOLD_STEPS = ("Deploy", "Process", "Predict", "Report")

# each step's title, in the top row beside About / Settings
_TITLES = {
    1: "Build a sensor deployment by adding a test site, treatment "
       "condition and sensor files…",
    2: "Process, validate and segment sensor data…",
    3: "Process, validate and segment sensor data…",
    4: "Predict blade strike from sensor data…",
    5: "Report blade strike from sensor data…",
}

# the Output step's figures: their height on screen
REPORT_FIG_H = 380

# the logo's size: on Home and Finished (width), in the bottom bar (height)
BIG_LOGO_W = 520
BOTTOM_LOGO_H = 60

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
    """The StrikeWorks window. Built once and reopened with `exec()`;
    "Development toolkit" (`_go_development_toolkit`) switches to the full
    app."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("StrikeWorks")
        # the stylesheet's selector for this window's own look (#strikeWorks)
        self.setObjectName("strikeWorks")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        # a normal window: minimise, maximise and close, resizable
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint)
        self.setMinimumSize(900, 560)
        # the app's first visible window, and its owner (MainWindow) is
        # hidden, so it needs the taskbar fix (win_utils.py)
        win_utils.ensure_taskbar_button(self)
        # within the screen's work area (not under the taskbar), centred
        win_utils.fit_to_screen(self, 1340, 800)
        # window-modal, so the console stays usable
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self._lib_root = window.session_state.library
        self._validate_dirty = False    # written since the last Save and export
        self._advance_after_export = False   # "Save and continue" on the unsaved-data prompt
        self.went_to_dev_toolkit = False
        self._built_dataset_path = None

        self._build()
        state = self.window.ml_prediction_page.state
        state.run_finished.connect(self._on_predict_finished)
        state.run_failed.connect(self._on_predict_failed)
        # the HIG peak analysis box follows Predict's (one shared setting)
        state.config_changed.connect(self._on_prediction_config_changed)
        self._on_prediction_config_changed()
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
            if not indent and label in _BOLD_STEPS:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.step_list.addItem(item)
        self.step_list.itemClicked.connect(self._on_step_clicked)
        # sized to exactly what the list needs, in the stylesheet's font
        # (polished first) and each item's own (the bold steps)
        self.step_list.ensurePolished()
        width = max(QFontMetrics(self.step_list.item(r).font()
                                 if self.step_list.item(r).font().bold()
                                 else self.step_list.font()).horizontalAdvance(
                        self.step_list.item(r).text())
                    for r in range(self.step_list.count())) + 36
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
        self.lbl_title = QLabel("")
        style(self.lbl_title, role="strong")
        top_row.addWidget(self.lbl_title)
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

        # each step in a scroll area: a small window scrolls the step
        # rather than squashing it
        self.stack = QStackedWidget()
        for build in (self._build_welcome_page, self._build_deployment_page,
                      self._build_process_inventory_page,
                      self._build_process_validate_page,
                      self._build_predict_page, self._build_report_page,
                      self._build_finished_page):
            self.stack.addWidget(scroll_area(build()))
        right_col.addWidget(self.stack, stretch=1)
        body.addLayout(right_col, stretch=1)
        outer.addLayout(body, stretch=1)

        # the bottom bar: Development toolkit (Home) or the small logos
        # (the other steps) on the left, the guidance line over Back / Next
        # / Close on the right - all bottom-aligned, so the bar is no taller
        # than the logos and the buttons sit where they do on Home
        bottom = Qt.AlignmentFlag.AlignBottom
        nav = QHBoxLayout()
        nav.setContentsMargins(10, 6, 10, 10)
        # the way into the Development toolkit: on Home only, and not in
        # the Simple edition (_sync_step_highlight)
        self.btn_dev_toolkit = QPushButton("Development toolkit")
        self.btn_dev_toolkit.setAutoDefault(False)
        self.btn_dev_toolkit.setToolTip(
            "The full app: blade strike modelling, annotation, model "
            "training and the rest (password protected).")
        self.btn_dev_toolkit.clicked.connect(self._go_development_toolkit)
        nav.addWidget(self.btn_dev_toolkit, alignment=bottom)
        # the small logo, on the pages without the big one
        # (_sync_step_highlight)
        self.logos = QWidget()
        logos = QHBoxLayout(self.logos)
        logos.setContentsMargins(0, 0, 0, 0)
        logo = logo_label(height=BOTTOM_LOGO_H, large=False)
        if logo is not None:
            logos.addWidget(logo)
        nav.addWidget(self.logos, alignment=bottom)
        nav.addStretch()
        steer = QWidget()
        sv = QVBoxLayout(steer)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(6)
        self.lbl_guidance = QLabel("")
        style(self.lbl_guidance, role="hint")
        sv.addWidget(self.lbl_guidance, alignment=Qt.AlignmentFlag.AlignRight)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self._go_next)
        self.btn_back = QPushButton("< Back")
        self.btn_back.clicked.connect(self._go_back)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        buttons.addWidget(self.btn_back)
        buttons.addWidget(self.btn_next)
        buttons.addWidget(btn_close)
        sv.addLayout(buttons)
        nav.addWidget(steer, alignment=bottom)
        outer.addLayout(nav)


    def _show_about(self):
        from .about_dialog import AboutDialog
        AboutDialog(self).exec()

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
                self.validation.save_and_export()
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
        _auto, user_validated, flagged, _bad = self.validation.validation_status()
        outstanding = [f for f in self.validation.files
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
            # a group heading ("Process"/"Report") opens its first sub-step
            below = self.step_list.item(self.step_list.row(item) + 1)
            page = below.data(Qt.ItemDataRole.UserRole) if below else None
            if page is None:
                self._sync_step_highlight()
                return
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
        self.logos.setVisible(page not in _NO_SMALL_LOGO_PAGES)
        self.btn_dev_toolkit.setVisible(page == 0 and not simple_only())
        self.lbl_guidance.setText(_GUIDANCE.get(page, ""))
        self.lbl_title.setText(_TITLES.get(page, ""))

    # ── page 0: welcome ──────────────────────────────────────────────────────
    def _build_welcome_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        logo = logo_label(width=BIG_LOGO_W)
        if logo is not None:
            v.addWidget(logo)
        v.addSpacing(12)
        subtitle = QLabel("Deploy. Process. Predict. Report.")
        style(subtitle, role="tagline")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(subtitle)
        v.addStretch()
        return page

    def _go_development_toolkit(self):
        """The "Development toolkit" button: asks for the password, then
        opens it. Does nothing in the Simple edition."""
        if simple_only():
            return
        password, ok = QInputDialog.getText(
            self, "Development toolkit", "Password:",
            QLineEdit.EchoMode.Password)
        if not ok:
            return
        if password != _DEV_TOOLKIT_PASSWORD:
            QMessageBox.warning(self, "Development toolkit",
                                "That password isn't right.")
            return
        self.open_development_toolkit()

    def open_development_toolkit(self):
        """Show the full app (MainWindow), maximised, with its sidebar
        enabled, and close this window - `went_to_dev_toolkit` tells
        main.py not to quit when it closes. No password (the demo calls
        this); nothing in the Simple edition."""
        if simple_only():
            return
        self.went_to_dev_toolkit = True
        self.window.home_page._go_advanced()
        self.window.showMaximized()
        self.reject()

    # ── page 1: deployment ───────────────────────────────────────────────────
    def _build_deployment_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)
        # the same editor as Create and edit deployment
        self.editor = DeploymentEditor(self.window, self.window.session_state)
        v.addWidget(self.editor, stretch=1)
        return page

    def _on_prediction_config_changed(self):
        state = self.window.ml_prediction_page.state
        self.chk_hig_peaks.blockSignals(True)
        self.chk_hig_peaks.setChecked(state.hig_peaks)
        self.chk_hig_peaks.blockSignals(False)
        self._refresh_hig_card()

    def _refresh_hig_card(self):
        """The collisions card: shown only while HIG peak analysis is
        ticked, filled when the last run did the analysis."""
        state = self.window.ml_prediction_page.state
        self.card_severity.setVisible(state.hig_peaks)
        acc = state.acc_summary
        if acc is None or not len(acc):
            self.card_severity.clear()
            return
        total = acc.iloc[-1]       # the "All recordings" row, or the only one
        k, n_rec = int(total["n_collision"]), int(total["n_sensors"])
        self.card_severity.set_segments([
            ("Collision", k, PINK), ("No collision", n_rec - k, PALETTE[0])])

    def _on_session_library_changed_simple(self, path):
        self._lib_root = path

    # ── page 2: process (file inventory) ────────────────────────────────────
    def _build_process_inventory_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(8)
        # the same inventory as Raw data processing
        self.inventory = FileInventory(inventory_title="", log_title="")
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
        """The Development toolkit's Validate and annotate page itself
        (page_annotate.py), with StrikeWorks's saving: Next continues with
        the export, named after the deployment picked on Deploy."""
        self.validate_page = AnnotationPage(
            self, self.window.session_state, for_strikeworks=True)
        self.validate_page.setContentsMargins(0, 0, 0, 0)
        self.validation = self.validate_page.view
        self.validation.export_name = lambda: self.editor.deployment_id()
        self.validation.index_changed.connect(self._on_validation_written)
        self.validation.export_done.connect(self._on_extract_done)
        return self.validate_page

    def _on_validation_written(self):
        self._validate_dirty = True

    def _refresh_validate_step(self):
        """Re-list the library's processed sensors (Process may have just
        added some)."""
        self._lib_root = self.window.session_state.library
        self.validate_page.refresh()

    def _on_extract_done(self, df, path, _message):
        if df is None:
            self._advance_after_export = False
            return
        self._built_dataset_path = path
        self._validate_dirty = False
        # straight into the shared PredictionState
        self.window.ml_prediction_page.on_dataset_ready(
            df, f"StrikeWorks - {path.stem}")
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

        # equal stretch above and below keeps the block centred
        v.addStretch(1)

        grp_ds = Section("Dataset")
        grp_ds.setMaximumWidth(430)
        dv = QVBoxLayout(grp_ds)
        self.card_predict_dataset = MetaCard()
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

        state = self.window.ml_prediction_page.state
        chk_row = QHBoxLayout()
        chk_row.addStretch()
        self.chk_hig_peaks = QCheckBox("HIG peak analysis")
        self.chk_hig_peaks.setChecked(state.hig_peaks)
        self.chk_hig_peaks.setToolTip(
            "Count the acceleration events in each recording's high-g "
            f"magnitude (peaks of at least {hig_peaks.HEIGHT_G:.0f} g) within "
            "0.1 s of the nadir, and the recordings with a collision (an "
            f"event of {hig_peaks.COLLISION_G} g or more). Measured, "
            "alongside the model's prediction.")
        self.chk_hig_peaks.toggled.connect(state.set_hig_peaks)
        chk_row.addWidget(self.chk_hig_peaks)
        chk_row.addStretch()
        v.addLayout(chk_row)

        self.lbl_predict_status = QLabel("")
        style(self.lbl_predict_status, role="muted")
        self.lbl_predict_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl_predict_status)

        self.lbl_predict_done = QLabel("")
        style(self.lbl_predict_done, role="strong", tone="ok")
        self.lbl_predict_done.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl_predict_done)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.addStretch()
        self.card_predicted_strikes = RingCard("Predicted strikes")
        cards_row.addWidget(self.card_predicted_strikes)
        self.card_strike_classes = RingCard("Strike classes")
        cards_row.addWidget(self.card_strike_classes)
        # the HIG peak analysis, shown while its box is ticked
        self.card_severity = RingCard(f"Collisions (≥ {hig_peaks.COLLISION_G} g)")
        self.card_severity.setToolTip(
            f"Recordings with an acceleration event of "
            f"{hig_peaks.COLLISION_G} g or more within 0.1 s of the nadir "
            "(HIG peak analysis). Measured, not predicted.")
        cards_row.addWidget(self.card_severity)
        cards_row.addStretch()
        v.addLayout(cards_row)

        v.addStretch(1)
        return page

    def _refresh_predict_step(self):
        state = self.window.ml_prediction_page.state
        state.use_default_models()
        self._refresh_predict_dataset_card()
        self.btn_run_predict.setEnabled(state.dataset_df is not None)

    def _load_dataset_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Load dataset CSV", str(settings.get_input_data_dir()),
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
            ("Annotations",   state.annotation_status()),
        ])

    def _run_predict(self):
        state = self.window.ml_prediction_page.state
        self.btn_run_predict.setEnabled(False)
        self.lbl_predict_status.setText("Running…")
        style(self.lbl_predict_status, tone="accent")
        state.run_prediction()

    def _on_predict_finished(self):
        state = self.window.ml_prediction_page.state
        self.btn_run_predict.setEnabled(True)
        meta = state.run_meta
        n = meta.get("n_files", 0)
        style(self.lbl_predict_status, tone="ok")
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

        self._refresh_hig_card()

    def _on_predict_failed(self, msg):
        self.btn_run_predict.setEnabled(True)
        style(self.lbl_predict_status, tone="bad")
        self.lbl_predict_status.setText(f"Prediction failed: {msg.splitlines()[-1]}")

    # ── page 5: report ───────────────────────────────────────────────────────
    def _build_report_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        self.tbl_report = QTableWidget(0, 0)
        self.tbl_report.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_report.setMinimumHeight(150)
        v.addWidget(self.tbl_report)

        # the HIG peak analysis table, as in the reports
        self.tbl_report_acc = QTableWidget(0, 0)
        self.tbl_report_acc.setProperty("noRowNumbers", True)   # its own header rows
        self.tbl_report_acc.horizontalHeader().setVisible(False)
        self.tbl_report_acc.verticalHeader().setVisible(False)
        self.tbl_report_acc.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_report_acc.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(self.tbl_report_acc)
        self.lbl_report_acc_notes = muted_label(
            "\n".join(hig_peaks.TABLE_NOTES))
        self.lbl_report_acc_notes.setWordWrap(True)
        v.addWidget(self.lbl_report_acc_notes)

        # the two model figures side by side, the HIG peak figure (three
        # panels) the full width under them
        grp_figs = Section("")
        fv = QGridLayout(grp_figs)
        self.fig_report_bin = Figure(figsize=(4.3, 3.2), dpi=100)
        self.canvas_report_bin = FigureCanvas(self.fig_report_bin)
        self.fig_report_mc = Figure(figsize=(4.3, 3.2), dpi=100)
        self.canvas_report_mc = FigureCanvas(self.fig_report_mc)
        self.fig_report_peaks = Figure(figsize=(8.6, 3.2), dpi=100)
        self.canvas_report_peaks = FigureCanvas(self.fig_report_peaks)
        for c in (self.canvas_report_bin, self.canvas_report_mc,
                  self.canvas_report_peaks):
            c.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)
            c.setMinimumHeight(REPORT_FIG_H)
        fv.addWidget(self.canvas_report_bin, 0, 0)
        fv.addWidget(self.canvas_report_mc, 0, 1)
        fv.addWidget(self.canvas_report_peaks, 1, 0, 1, 2)
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
        # severity columns only without the HIG peak analysis (its own table)
        measured = severity.available(df) and state.acc_summary is None
        headers = (["Treatment", "N", "Strikes", "No strike", "Strike rate",
                    "95% CI", "Mean prob", "Mean conf"] + list(class_names)
                   + (severity.TABLE_HEADERS if measured else []))
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
                if measured:
                    vals += severity.table_values(r)
                for col, val in enumerate(vals):
                    self.tbl_report.setItem(row, col, QTableWidgetItem(val))
        self.tbl_report.resizeColumnsToContents()

        ml_figures.draw_strike_rate(self.fig_report_bin, df, dark=True)
        self.canvas_report_bin.draw()
        ml_figures.draw_region(self.fig_report_mc, df,
                               class_names if mc_run else [], dark=True)
        self.canvas_report_mc.draw()

        have_peaks = state.acc_summary is not None
        for w in (self.tbl_report_acc, self.lbl_report_acc_notes,
                  self.canvas_report_peaks):
            w.setVisible(have_peaks)
        if have_peaks:
            fill_acceleration_table(self.tbl_report_acc, state.acc_summary)
            ml_figures.draw_peak_summary(self.fig_report_peaks,
                                         state.acc_summary, state.predictions,
                                         dark=True)
            self.canvas_report_peaks.draw()

    def _processing_review_rows(self):
        """How Validate went for this library (validation_core) - fed
        into the *downloaded* report, not this wizard's Report step."""
        return vc.processing_review_rows(
            [f["stem"] for f in self.validation.files],
            self.validation.read_index())

    # ── page 6: finished ─────────────────────────────────────────────────────
    def _build_finished_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        logo = logo_label(width=BIG_LOGO_W)
        if logo is not None:
            v.addWidget(logo)
        v.addSpacing(12)
        title = QLabel("Finished!")
        style(title, role="display")
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
        win_utils.open_folder(out)
        QMessageBox.information(
            self.window, "Report downloaded", f"Saved to:\n{out}")
