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
  Predict   - ml_tab_predict.PredictPanel (Model prediction > Predict's
              own Predict tab, on the shared PredictionState).
  Report    - ml_tab_predict.ResultsPanel (its Results tab); the
              downloaded report is ml_report's.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLayout,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from . import ml_report, settings, win_utils
from . import validation_core as vc
from .deployment_editor import DeploymentEditor
from .edition import simple_only
from .inventory_widgets import FileInventory
from .layout import scroll_area
from .ml_tab_predict import PredictPanel, ResultsPanel
from .page_annotate import AnnotationPage
from .theme import style
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
            "The full app: the blade strike calculator, annotation, model "
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
                # (_confirm_leave_validate has just asked about flagged ones)
                self.validation.save_and_export(confirm=False)
                # (not started if asked which frequency and cancelled)
                self._advance_after_export = self.validation.exporter.running
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
        # edge to edge, as on Process and Validate
        v.setContentsMargins(0, 0, 0, 0)
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
        # edge to edge, as on Deploy and Validate
        v.setContentsMargins(0, 0, 0, 0)
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
        (page_annotate.py); Next continues to Predict with its export."""
        self.validate_page = AnnotationPage(
            self, self.window.session_state, for_strikeworks=True)
        self.validate_page.setContentsMargins(0, 0, 0, 0)
        self.validation = self.validate_page.view
        self._validate_deployment = None    # the Deploy deployment last shown
        self.validation.index_changed.connect(self._on_validation_written)
        self.validation.export_done.connect(self._on_extract_done)
        return self.validate_page

    def _on_validation_written(self):
        self._validate_dirty = True

    def _refresh_validate_step(self):
        """Re-list the library's processed sensors (Process may have just
        added some), filtered to the deployment picked on Deploy whenever
        that changes - a filter changed here stays until it does."""
        self._lib_root = self.window.session_state.library
        dep_dir = self.editor.deployment_dir()
        if dep_dir is not None and dep_dir.name != self._validate_deployment:
            self._validate_deployment = dep_dir.name
            self.validate_page.lib_selector.select_deployment(dep_dir.name)
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
        """Model prediction's own Predict page (ml_tab_predict.PredictPanel)."""
        self.predict_panel = PredictPanel(
            self.window.ml_prediction_page.state, self,
            bsm_state=self.window.bsm_state)
        return self.predict_panel

    def _refresh_predict_step(self):
        # Settings' default models, in case they changed
        self.window.ml_prediction_page.state.use_default_models()

    def _run_predict(self):
        self.predict_panel.run()

    # ── page 5: report ───────────────────────────────────────────────────────
    def _build_report_page(self):
        """Model prediction's own Results page (ml_tab_predict.ResultsPanel)."""
        self.results_panel = ResultsPanel(
            self.window.ml_prediction_page.state, self.window.bsm_state)
        return self.results_panel

    def _refresh_report_step(self):
        self.results_panel.refresh()

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
