# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# GUI built on the PyDracula template (MIT licence) - credit and link
# available under Settings > About. See LICENSE.
#
# ///////////////////////////////////////////////////////////////

import sys
import os
from pathlib import Path

# Worker subprocesses (prediction / training). A frozen exe has no Python
# to hand a .py file to, so worker_launch.py re-runs the exe as
# `<exe> --worker <name> args...`. Checked before the GUI imports so a
# worker never loads Qt.
if len(sys.argv) > 2 and sys.argv[1] == "--worker":
    _worker_name = sys.argv[2]
    sys.argv = [sys.argv[0]] + sys.argv[3:]
    import traceback
    try:
        if _worker_name == "predict":
            from modules.predict_worker import main as _worker_main
        elif _worker_name == "train":
            from modules.train_worker import main as _worker_main
        else:
            print(f"Unknown worker: {_worker_name}", file=sys.stderr)
            sys.exit(1)
        _worker_main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    sys.exit(0)

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QMainWindow, QPushButton, QTableWidget, QVBoxLayout,
)

from modules import settings, startup, table_copy, theme, win_utils
from modules.bsm_state import BSMState
from modules.dev_console import DevConsole
from modules.layout import scroll_area, when_visible
from modules.page_annotate import AnnotationPage
from modules.page_bsm_analysis import BSMAnalysisPage
from modules.page_bsm_calculator import CalculatorPage
from modules.page_dataset import DatasetPage
from modules.page_deployment import DeploymentPage
from modules.page_export_animations import ExportAnimationsPage
from modules.page_home import HomePage
from modules.page_misclassification import MisclassificationPage
from modules.page_ml_prediction import MLPredictionPage
from modules.page_ml_training import MLTrainingPage
from modules.page_model_comparison import ModelComparisonPage
from modules.page_process import ProcessPage
from modules.page_settings import SettingsDialog
from modules.page_setup import SetupPage
from modules.page_simple_mode import SimpleModeDialog
from modules.page_stub import StubPage
from modules.page_validate import ValidatePage
from modules.plot_widgets import configure_pyqtgraph
from modules.session_state import SessionState
from modules.tables import style_table
from modules.theme import set_flag
from modules.ui_config import UIConfig
from modules.ui_functions import UIFunctions
from modules.ui_main import Ui_MainWindow

os.environ["QT_FONT_DPI"] = "96"  # consistent sizing at display scaling above 100 %


def _print_status(msg, _ms=0):
    print(f"[status] {msg}")


class MainWindow(QMainWindow):
    # Sidebar sections: panel title, sub-menu buttons, top-level button.
    _PANEL_SECTIONS = {
        "bsm": ("Mathematical blade strike modelling",
                ("btn_bsm_calculator", "btn_bsm_sensitivity"),
                "btn_bsm"),
        "setup_deploy": ("Setup and deploy",
                         ("btn_prepare", "btn_study_design",
                          "btn_initiate_deployment"),
                         "btn_setup_deploy"),
        "sensor": ("Sensor processing",
                   ("btn_process",),
                   "btn_sensor"),
        "annotation": ("Validate and annotate",
                       ("btn_annotate", "btn_export_animations"),
                       "btn_annotation"),
        "model_training": ("Model training",
                           ("btn_ml_training", "btn_evaluate_train",
                            "btn_misclassification"),
                           "btn_model_training"),
        "model_prediction": ("Model prediction",
                             ("btn_ml_prediction", "btn_inspect_pred",
                              "btn_biological"),
                             "btn_model_prediction"),
    }

    # Each sub-menu button's destination: the page (a MainWindow attribute)
    # and, for a page of tabs (TabbedPage), the tab to show. Export and
    # report isn't here - it opens a dialog.
    _SUBMENU_TARGETS = {
        # Setup and deploy
        "btn_prepare":             ("setup_page", 0),
        "btn_study_design":        ("setup_page", 1),
        "btn_initiate_deployment": ("deployment_page", None),
        # Sensor processing
        "btn_process":             ("process_page", None),
        "btn_validate":            ("validate_page", None),
        "btn_data_analysis":       ("data_analysis_page", None),
        # Validate and annotate
        "btn_annotate":            ("annotation_page", None),
        "btn_export_animations":   ("export_animations_page", None),
        "btn_dataset":             ("dataset_page", None),
        # Model training
        "btn_ml_training":         ("ml_training_page", 0),
        "btn_evaluate_train":      ("ml_training_page", 1),
        "btn_misclassification":   ("misclassification_page", None),
        # Model prediction
        "btn_ml_prediction":       ("ml_prediction_page", 0),
        "btn_inspect_pred":        ("ml_prediction_page", 1),
        "btn_biological":          ("model_comparison_page", None),
        # Mathematical blade strike modelling
        "btn_bsm_calculator":      ("bsm_calculator_page", None),
        "btn_bsm_sensitivity":     ("bsm_analysis_page", None),
    }

    # built but not offered in the sidebar for now (ROADMAP.md, "Hidden for now")
    _HIDDEN_PAGES = ("btn_validate", "btn_data_analysis", "btn_dataset")

    # greyed out until Home's "Advanced mode" enables them
    _SIDEBAR_NAV_BUTTONS = (
        "btn_bsm", "btn_setup_deploy", "btn_sensor", "btn_annotation",
        "btn_model_training", "btn_model_prediction", "btn_export_report",
    )

    def __init__(self):
        super().__init__()
        # the theme's stylesheet, for every window the app opens
        theme.apply(QApplication.instance())
        self.ui = ui = Ui_MainWindow()
        ui.setupUi(self)
        self.setWindowTitle("StrikeWorks")
        # set on the window as well as the app: the frameless window can
        # otherwise lose the app-level icon on the taskbar
        self.setWindowIcon(QIcon(str(startup.ICON_PATH)))
        # (the header text, titleRightInfo, comes from main.ui)

        ui.toggleButton.clicked.connect(lambda: UIFunctions.toggleMenu(self, True))
        UIFunctions.uiDefinitions(self)

        configure_pyqtgraph()
        # hidden until opened from Settings; `self` is only a reference for
        # its demo runners, not its Qt parent
        self.dev_console = DevConsole(self)

        # Every page builds its own contents (layout.Page) and is added to
        # the page stack here, in a scroll area of its own (_page). Home
        # first: it resolves the session library, which the pages below
        # read while they're built.
        self._page_holders = {}
        self.session_state = SessionState(self)
        self.home_page = self._page(HomePage(self, self.session_state))

        # Setup and deploy comes first: its sensor drives processing,
        # validation and dataset building
        self.setup_page = self._page(SetupPage(self))
        self.process_page = self._page(ProcessPage(self, self.session_state))
        self.validate_page = self._page(ValidatePage(self, self.session_state))
        self.dataset_page = self._page(DatasetPage(self, self.session_state))
        self.deployment_page = self._page(
            DeploymentPage(self, self.session_state))
        self.annotation_page = self._page(
            AnnotationPage(self, self.session_state))
        self.export_animations_page = self._page(
            ExportAnimationsPage(self, self.session_state))

        # before Model prediction: its Predict tab shows BSM mortality
        self.bsm_state = BSMState(self)
        self.ml_prediction_page = self._page(
            MLPredictionPage(self, self.bsm_state))
        # Simple mode shares ml_prediction_page.state
        self.simple_mode_dialog = SimpleModeDialog(self)
        self.ml_training_page = self._page(MLTrainingPage(self))
        self.misclassification_page = self._page(
            MisclassificationPage(self, self.ml_training_page.state))

        self.dataset_page.dataset_ready.connect(
            self.ml_prediction_page.on_dataset_ready)
        # a newly deployed model becomes available to Model prediction
        self.ml_training_page.model_deployed.connect(
            lambda _p: self.ml_prediction_page.state.load_models_from_dir(
                self.ml_prediction_page.state.models_dir))

        # Calculator runs the BSM; Analysis and reporting and Model
        # comparison follow its result through the shared BSMState
        self.bsm_calculator_page = self._page(
            CalculatorPage(self, self.bsm_state))
        self.bsm_analysis_page = self._page(
            BSMAnalysisPage(self, self.bsm_state))
        self.model_comparison_page = self._page(ModelComparisonPage(
            self, self.bsm_state, self.ml_prediction_page.state))

        self.data_analysis_page = self._page(StubPage(
            self, "Data analysis",
            "Passage duration, time-series normalisation, "
            "barotrauma metrics, acceleration peak finding."))

        self._order_panel_buttons()
        self._build_bottom_menu()

        ui.btn_home.clicked.connect(self._go_home)

        self._panel_mode = "sensor"
        self._panel_btn = ui.btn_sensor
        self._configure_panel("sensor")
        for name in self._HIDDEN_PAGES:
            getattr(ui, name).setVisible(False)
        for mode, (_label, _names, top_btn) in self._PANEL_SECTIONS.items():
            getattr(ui, top_btn).clicked.connect(
                lambda _checked=False, m=mode: self.openPanel(m))
        ui.extraCloseColumnBtn.clicked.connect(
            lambda: UIFunctions.toggleLeftBox(self, True))
        for btn_name in self._SUBMENU_TARGETS:
            getattr(ui, btn_name).clicked.connect(self.submenuButtonClick)
        ui.btn_export_report.clicked.connect(self.ml_prediction_page.open_report)

        # the right-hand settings panel
        ui.settingsTopBtn.clicked.connect(
            lambda: UIFunctions.toggleRightBox(self, True))
        ui.btn_about.clicked.connect(self.openAbout)
        ui.btn_adjustments.clicked.connect(self.openSettings)

        for tbl in self.findChildren(QTableWidget):
            style_table(tbl)

        self.show_page(self.home_page)
        self.setSelected(ui.btn_home)

        # start as the collapsed icon strip, section buttons disabled
        ui.leftMenuBg.setMinimumWidth(UIConfig.MENU_COLLAPSED_WIDTH)
        ui.leftMenuBg.setMaximumWidth(UIConfig.MENU_COLLAPSED_WIDTH)
        self.set_sidebar_active(False)

        # Not shown here: Simple mode opens first (see __main__). The
        # taskbar fix has to run before the window's first show().
        win_utils.ensure_taskbar_button(self)
        # within the screen's work area (not under the taskbar), centred
        win_utils.fit_to_screen(self, 1280, 860)

    def _page(self, page):
        """Add `page` to the page stack, in a scroll area: a window smaller
        than the page's minimum size scrolls rather than growing past the
        screen."""
        page.status.connect(_print_status)
        holder = scroll_area(page)
        self._page_holders[page] = holder
        self.ui.stackedWidget.addWidget(holder)
        return page

    def show_page(self, page):
        self.ui.stackedWidget.setCurrentWidget(self._page_holders[page])

    def current_page(self):
        holder = self.ui.stackedWidget.currentWidget()
        return next((p for p, h in self._page_holders.items() if h is holder),
                    None)

    # ── sidebar layout ──────────────────────────────────────────────────────
    def _order_panel_buttons(self):
        """extraTopMenu is one flat layout for every section; put the few
        buttons that main.ui has out of order in their place."""
        layout = self.ui.extraTopMenu.layout()

        def move(name, anchor, offset):
            widget = getattr(self.ui, name)
            layout.removeWidget(widget)
            layout.insertWidget(
                layout.indexOf(getattr(self.ui, anchor)) + offset, widget)

        move("btn_export_animations", "btn_dataset", 0)

    def _build_bottom_menu(self):
        """Pin "Simple mode" and "Export and report" to the bottom of the
        sidebar, in the template's `#bottomMenu` frame."""
        ui = self.ui
        ui.topMenu.layout().removeWidget(ui.btn_export_report)
        bottom = QFrame(ui.leftMenuFrame)
        bottom.setObjectName("bottomMenu")
        bottom_v = QVBoxLayout(bottom)
        bottom_v.setContentsMargins(0, 0, 0, 0)
        bottom_v.setSpacing(0)

        btn = ui.btn_simple_mode_nav = QPushButton("Simple mode")
        btn.setObjectName("btn_simple_mode_nav")
        btn.setSizePolicy(ui.btn_export_report.sizePolicy())
        btn.setMinimumSize(QSize(0, 45))
        btn.setFont(ui.btn_export_report.font())
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setLayoutDirection(Qt.LeftToRight)
        btn.setStyleSheet(
            "background-image: url(:/icons/images/icons/cil-external-link.png);")
        btn.clicked.connect(self.openSimpleMode)
        # the University brandmark above them, white on the sidebar (it
        # shrinks to the collapsed icon strip)
        ui.uoh_brandmark = startup.Brandmark(84, reverse=True)
        bottom_v.addWidget(ui.uoh_brandmark)
        bottom_v.addSpacing(8)
        bottom_v.addWidget(btn)
        bottom_v.addWidget(ui.btn_export_report)

        ui.leftMenuFrame.layout().addStretch(1)
        ui.leftMenuFrame.layout().addWidget(bottom)

    def set_sidebar_active(self, active):
        for name in self._SIDEBAR_NAV_BUTTONS:
            getattr(self.ui, name).setEnabled(active)

    def expand_sidebar(self):
        """Advanced mode: open the sidebar and enable its sections."""
        self.ui.leftMenuBg.setMinimumWidth(UIConfig.MENU_WIDTH)
        self.ui.leftMenuBg.setMaximumWidth(UIConfig.MENU_WIDTH)
        self.set_sidebar_active(True)

    # ── menu highlight and section panel ────────────────────────────────────
    def setSelected(self, btn):
        set_flag(btn, "selected", True)

    def _section_for_button(self, btn_name):
        for mode, (_label, names, _top) in self._PANEL_SECTIONS.items():
            if btn_name in names:
                return mode
        return None

    def _configure_panel(self, mode):
        label, this_section, top_btn = self._PANEL_SECTIONS[mode]
        self.ui.extraLabel.setText(label)
        for _l, names, _b in self._PANEL_SECTIONS.values():
            for name in names:
                getattr(self.ui, name).setVisible(name in this_section)
        self._panel_mode = mode
        self._panel_btn = getattr(self.ui, top_btn)

    def _swap_panel_ownership(self, mode):
        """Switch the open panel to `mode`, moving the "owns the panel"
        highlight to the new section's button without closing it."""
        set_flag(self._panel_btn, "boxOwner", False)
        self._configure_panel(mode)
        set_flag(self._panel_btn, "boxOwner", True)

    def openPanel(self, mode):
        if self.ui.extraLeftBox.width() > 0 and self._panel_mode != mode:
            self._swap_panel_ownership(mode)
            return
        self._configure_panel(mode)
        UIFunctions.toggleLeftBox(self, True)

    # ── navigation ──────────────────────────────────────────────────────────
    def _go_home(self):
        ui = self.ui
        self.show_page(self.home_page)
        UIFunctions.resetStyle(self, "btn_home")
        UIFunctions.resetPanelStyle(self, "")
        if ui.extraLeftBox.width() > 0:
            UIFunctions.toggleLeftBox(self, True)
        self.setSelected(ui.btn_home)

    def navigate_to(self, btn_name):
        """Show `btn_name`'s page (and tab), switching the section panel to
        its section first, so it also works from a link on another page.

        Leaving Misclassification analysis with corrections made goes to
        Model training > Train instead, with the corrected dataset loaded."""
        ui = self.ui
        mp = self.misclassification_page
        if (self.current_page() is mp
                and btn_name != "btn_misclassification"
                and mp.has_changes()):
            mp.notify_and_load_into_training()
            btn_name = "btn_ml_training"

        section = self._section_for_button(btn_name)
        if section is not None:
            if ui.extraLeftBox.width() > 0 and section != self._panel_mode:
                self._swap_panel_ownership(section)
            else:
                self._configure_panel(section)

        target = self._SUBMENU_TARGETS.get(btn_name)
        if target is None:
            return
        page_name, tab_index = target
        page = getattr(self, page_name)
        self.show_page(page)
        if tab_index is not None:
            page.show_tab(tab_index)

        UIFunctions.resetPanelStyle(self, btn_name)
        self.setSelected(getattr(ui, btn_name))
        if section is not None:
            top_btn = self._PANEL_SECTIONS[section][2]
            UIFunctions.resetStyle(self, top_btn)
            self.setSelected(getattr(ui, top_btn))

    def submenuButtonClick(self):
        self.navigate_to(self.sender().objectName())

    # ── dialogs ─────────────────────────────────────────────────────────────
    def openAbout(self):
        from modules.about_dialog import AboutDialog
        AboutDialog(self).exec()

    def openSettings(self):
        models_before = settings.get_models_dir()
        SettingsDialog(self).exec()
        # Home owns library discovery; the libraries folder may have changed
        self.home_page._refresh_library_combo()
        if settings.get_models_dir() != models_before:
            self._on_models_dir_changed(models_before)

    def _on_models_dir_changed(self, old_dir):
        """Settings' models folder changed: every model page still on the
        default folder follows it (a folder picked on a page stays)."""
        new_dir = settings.get_models_dir()
        training = self.ml_training_page
        training.tab_evaluate.follow_default_models_dir()
        training.deployment.follow_default_models_dir()
        mp = self.misclassification_page
        when_visible(mp, mp._reload_models,
                     key="models")
        state = self.ml_prediction_page.state
        if Path(state.models_dir) == Path(old_dir):
            ok, msg = state.load_models_from_dir(new_dir)
            if not ok:
                # nothing deployed there yet: point at it anyway, keeping
                # the model already loaded
                state.models_dir = new_dir
                state.models_changed.emit()
            _print_status(f"Models folder: {new_dir} - {msg}")

    def openSimpleMode(self):
        """Run Simple mode. True if it was left through "Development
        toolkit" (which shows this window itself), False otherwise."""
        self.simple_mode_dialog.exec()
        return self.simple_mode_dialog.went_to_dev_toolkit

    # ── window events ───────────────────────────────────────────────────────
    def resizeEvent(self, event):
        UIFunctions.resize_grips(self)

    def mousePressEvent(self, event):
        # the custom title bar drags the window from here
        self.dragPos = event.globalPos()


def _run_demo(mode, log_path=None):
    """`StrikeWorks --demo simple|advanced [--log <file>]`: run one demo
    to the end, unattended, and exit 0 if it passed - checks a build from
    raw files to a report (tools/smoke_test.ps1 -Demos)."""
    from modules.dev_runner import available_demos, run_headless
    if mode not in available_demos():
        print(f"No '{mode}' demo in this edition (choose "
              f"{', '.join(available_demos())})", file=sys.stderr)
        return 2
    if log_path:
        sys.stdout = sys.stderr = open(log_path, "w", encoding="utf-8",
                                       buffering=1)
    window = MainWindow()
    passed, message = run_headless(window, mode)
    print(f"[demo] {mode}: {'PASSED' if passed else 'FAILED'} - {message}")
    return 0 if passed else 1


def _option(name):
    """The value after `name` on the command line, or None."""
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    return None


if __name__ == "__main__":
    startup.set_windows_app_id()
    startup.ensure_default_folders()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(startup.ICON_PATH)))
    table_copy.install(app)
    if _option("--demo") is not None:
        sys.exit(_run_demo(_option("--demo"), _option("--log")))
    splash = startup.build_splash()
    splash.show()
    app.processEvents()
    window = MainWindow()
    # close() rather than finish(window): finish() waits for the window to
    # become visible, and it stays hidden behind Simple mode
    splash.close()
    # Simple mode first; the full app only if the user asks for it
    if not window.openSimpleMode():
        sys.exit(0)
    sys.exit(app.exec())
