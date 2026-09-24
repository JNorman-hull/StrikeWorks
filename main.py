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
import platform
from pathlib import Path

# WORKER DISPATCH (predict_worker.py / train_worker.py, launched as a
# subprocess by ml_state.py / ml_train_state.py via modules/worker_launch.py)
# - checked before any GUI import so a frozen build's worker subprocess
# never pulls in PySide6/Qt at all. From source the worker runs directly
# as its own script (`sys.executable <script>.py args...`); a frozen exe
# has no bundled interpreter to hand a loose .py file to, so it instead
# re-invokes itself as `<exe> --worker <name> args...` and lands here.
# ///////////////////////////////////////////////////////////////
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

# IMPORT / GUI AND MODULES AND WIDGETS
# ///////////////////////////////////////////////////////////////
from modules import *
from widgets import *
from modules.page_prepare import PreparePage
from modules.page_process import ProcessPage
from modules.page_validate import ValidatePage
from modules.page_dataset import DatasetPage
from modules.page_annotate import AnnotationPage
from modules.page_ml_prediction import MLPredictionPage
from modules.page_ml_training import MLTrainingPage
from modules.page_stub import StubPage
from modules.page_initiate_deployment import InitiateDeploymentPage
from modules.page_misclassification import MisclassificationPage
from modules.page_export_animations import ExportAnimationsPage
from modules.session_state import SessionState
from modules.page_home import HomePage
from modules.page_adjustments import AdjustmentsDialog
from modules.dev_console import DevConsole
from modules.page_simple_mode import SimpleModeDialog
from modules.bsm_state import BSMState
from modules.page_bsm_calculator import CalculatorPage
from modules.page_bsm_sensitivity import SensitivityPage
from modules.page_bsm_biological import BiologicalPage
from modules.ml_widgets import style_table
from modules import table_copy
from modules import win_utils
os.environ["QT_FONT_DPI"] = "96" # FIX Problem for High DPI and Scale above 100%

# SET AS GLOBAL WIDGETS
# ///////////////////////////////////////////////////////////////
widgets = None

# UI TEMPLATE CREDIT (shown under Settings > About)
# ///////////////////////////////////////////////////////////////
TEMPLATE_URL = "https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6"

# matches UIFunctions.toggleMenu's own hardcoded "standard" icon-strip
# width - the sidebar's starting, deactivated state (Simple/Advanced mode)
_LEFT_MENU_COLLAPSED_WIDTH = 60

# APP ICON - __file__-relative, not a bare "icon.ico", so it still
# resolves once frozen: PyInstaller's `datas` (StrikeWorks.spec) bundles
# icon.ico into _internal/, and __file__ for this module resolves there
# too under a onedir build - the same reasoning _build_splash() below
# already relies on for the PyDracula logo. A relative "icon.ico" would
# instead be looked up against the process's current working directory,
# which is *not* guaranteed to be the .exe's own folder (e.g. launched
# from a pinned taskbar/Start Menu shortcut) - silently resolving to
# nothing, which is what was leaving the taskbar button blank.
_ICON_PATH = Path(__file__).parent / "icon.ico"


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        # SET AS GLOBAL WIDGETS
        # ///////////////////////////////////////////////////////////////
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        global widgets
        widgets = self.ui

        # USE CUSTOM TITLE BAR | USE AS "False" FOR MAC OR LINUX
        # ///////////////////////////////////////////////////////////////
        Settings.ENABLE_CUSTOM_TITLE_BAR = True

        # APP NAME
        # ///////////////////////////////////////////////////////////////
        title = "StrikeWorks"
        # APPLY TEXTS
        self.setWindowTitle(title)
        # set directly on this window too, not just QApplication - a
        # frameless custom-title-bar window (below) can otherwise lose
        # the app-level default and fall back to a generic taskbar icon
        self.setWindowIcon(QIcon(str(_ICON_PATH)))
        # NOTE: the header label (titleRightInfo) is deliberately NOT set here.
        # Its text comes from main.ui so it can be edited in Qt Designer.
        # Calling setText() on a widget here overrides the .ui at startup and
        # makes Designer edits look like they have no effect.

        # TOGGLE MENU
        # ///////////////////////////////////////////////////////////////
        widgets.toggleButton.clicked.connect(lambda: UIFunctions.toggleMenu(self, True))

        # SET UI DEFINITIONS
        # ///////////////////////////////////////////////////////////////
        UIFunctions.uiDefinitions(self)

        # DEV CONSOLE - constructed (hidden, no stdout/stderr tee) before
        # every page below, but deliberately never auto-shown here even if
        # settings.get_dev_mode() was left on from a previous session -
        # it should only ever appear because the user opened it, from
        # Adjustments' Dev mode toggle or "Show console" button.
        # ///////////////////////////////////////////////////////////////
        self.dev_console = DevConsole()

        # SESSION STATE + HOME (library selection) - constructed before
        # every page below, and in that order: Home's own construction is
        # what resolves session_state.library (persisted last library, or
        # auto-selecting the first one found - see page_home.py), so any
        # page reading it at construction time (soft-synced pickers,
        # default output folders) sees the real answer instead of None.
        # ///////////////////////////////////////////////////////////////
        self.session_state = SessionState(self)
        self.home_page = HomePage(widgets, self, self.session_state)
        self.home_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # PAGE CONTROLLERS
        # ///////////////////////////////////////////////////////////////
        # Prepare comes first: the sensor chosen here drives raw import,
        # validation and dataset creation on the pages that follow.
        self.prepare_page = PreparePage(widgets, self)
        self.prepare_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.process_page = ProcessPage(widgets, self, self.session_state)
        self.process_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.validate_page = ValidatePage(widgets, self, self.session_state)
        self.validate_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.dataset_page = DatasetPage(widgets, self, self.session_state)
        self.dataset_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.initiate_deployment_page = InitiateDeploymentPage(
            widgets, self, self.session_state)
        self.initiate_deployment_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # ANNOTATION & VIDEO ANALYSIS PAGES
        self.annotation_page = AnnotationPage(widgets, self, self.session_state)
        self.annotation_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.export_animations_page = ExportAnimationsPage(
            widgets, self, self.session_state)
        self.export_animations_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # MATHEMATICAL BLADE STRIKE MODELLING STATE - constructed before
        # Model Prediction since its Predict tab now hosts the mortality
        # panel (moved there from Biological interpretation / Model
        # comparison) and needs bsm_state to read the Calculator's result.
        self.bsm_state = BSMState(self)

        # MACHINE LEARNING ANALYSIS PAGES
        self.ml_prediction_page = MLPredictionPage(widgets, self, self.bsm_state)
        self.ml_prediction_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        # Simple mode reuses ml_prediction_page.state directly (Predict
        # step) - constructed after it for exactly that reason
        self.simple_mode_dialog = SimpleModeDialog(self)
        self.ml_training_page = MLTrainingPage(widgets, self)
        self.ml_training_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.misclassification_page = MisclassificationPage(
            widgets, self, self.ml_training_page.state)
        self.misclassification_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # the curated dataset from Sensor Processing feeds Model Prediction
        self.dataset_page.dataset_ready.connect(
            self.ml_prediction_page.on_dataset_ready)

        # a freshly deployed model becomes available to Model Prediction
        self.ml_training_page.model_deployed.connect(
            lambda _p: self.ml_prediction_page.state.load_models_from_dir(
                self.ml_prediction_page.state.models_dir))

        # MATHEMATICAL BLADE STRIKE MODELLING PAGES (Chunk 5 task 5)
        # Calculator owns each run; Analysis and reporting reacts to its
        # `calculated` signal via the shared BSMState and also owns export
        # (the standalone Reporting page was folded into it). Model
        # comparison (formerly Biological interpretation) additionally
        # compares against Model prediction's data-driven per-treatment
        # results; bsm_state itself is constructed earlier, above, for
        # Model prediction > Predict's mortality panel.
        # ///////////////////////////////////////////////////////////////
        self.bsm_calculator_page = CalculatorPage(
            widgets.content_bsm_calculator, self, self.bsm_state)
        self.bsm_calculator_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.bsm_sensitivity_page = SensitivityPage(
            widgets.content_bsm_sensitivity, self, self.bsm_state)
        self.bsm_sensitivity_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.biological_page = BiologicalPage(
            widgets.content_biological, self, self.bsm_state,
            self.ml_prediction_page.state)
        self.biological_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # STUB PAGES (Chunk 5 restructure - not built yet; see ROADMAP.md)
        # ///////////////////////////////////////////////////////////////
        self._stub_pages = [
            StubPage(widgets.content_data_analysis, "Data analysis",
                     "Passage duration, time-series normalisation, "
                     "barotrauma metrics, acceleration peak finding. Part "
                     "of task 7."),
        ]

        # TAB WIDGETS NOW DRIVEN BY THE SIDEBAR
        # Train/Evaluate/Deploy, Predict/Inspect/Report and Sensor
        # configuration/Study design are QTabWidgets standing in for what
        # is now a set of sidebar sub-pages (see ROADMAP.md, Chunk 5): the
        # tab bar is hidden and the sidebar drives setCurrentIndex().
        # ///////////////////////////////////////////////////////////////
        for tab_widget_name in ("tabs_prepare", "tabs_ml_training",
                                "tabs_ml_prediction"):
            getattr(widgets, tab_widget_name).tabBar().setVisible(False)

        # SUB-MENU DISPLAY ORDER
        # extraTopMenu is one flat layout shared by every section - a
        # button kept from before Chunk 5 (btn_prepare, btn_ml_training, ...)
        # stayed at its original position when new buttons were appended
        # after it, which does not always match the requested order within
        # its (new) section. Reorder just the handful that need it; a
        # brand-new button already sits in the right place relative to its
        # section siblings.
        # ///////////////////////////////////////////////////////////////
        def move_before(widget_name, before_name):
            layout = widgets.extraTopMenu.layout()
            widget = getattr(widgets, widget_name)
            layout.removeWidget(widget)
            layout.insertWidget(layout.indexOf(getattr(widgets, before_name)),
                                widget)

        def move_after(widget_name, after_name):
            layout = widgets.extraTopMenu.layout()
            widget = getattr(widgets, widget_name)
            layout.removeWidget(widget)
            layout.insertWidget(
                layout.indexOf(getattr(widgets, after_name)) + 1, widget)

        move_before("btn_export_animations", "btn_dataset")
        move_after("btn_deploy_train", "btn_misclassification")

        # PIN "EXPORT AND REPORT" TO THE BOTTOM OF THE SIDEBAR
        # Built in main.ui as an ordinary topMenu button (simplest safe
        # edit there) and relocated here at runtime into its own frame,
        # pushed to the bottom of the sidebar by a stretch - the same
        # "build normally, reposition in Python" approach move_before/
        # move_after use above, rather than restructuring topMenu's own
        # layout in the .ui file. `#bottomMenu` already has its own QSS
        # rule (carried over from the PyDracula template) that nothing
        # used until now, so this also gets a visually distinct treatment
        # for free.
        # ///////////////////////////////////////////////////////////////
        widgets.topMenu.layout().removeWidget(widgets.btn_export_report)
        bottomMenu = QFrame(widgets.leftMenuFrame)
        bottomMenu.setObjectName("bottomMenu")
        bottomMenuLayout = QVBoxLayout(bottomMenu)
        bottomMenuLayout.setContentsMargins(0, 0, 0, 0)
        bottomMenuLayout.setSpacing(0)

        # "Simple mode" - a way back into the guided wizard for anyone who
        # landed in Advanced mode (Development toolkit, or Close on Simple
        # mode with nothing chosen) and wants it again without relaunching
        # the app. Built the same way as btn_export_report just above it
        # (a plain QPushButton matching its sizePolicy/font/cursor, since
        # neither has any widget of its own in main.ui to relocate from).
        widgets.btn_simple_mode_nav = QPushButton()
        widgets.btn_simple_mode_nav.setObjectName("btn_simple_mode_nav")
        widgets.btn_simple_mode_nav.setSizePolicy(
            widgets.btn_export_report.sizePolicy())
        widgets.btn_simple_mode_nav.setMinimumSize(QSize(0, 45))
        widgets.btn_simple_mode_nav.setFont(widgets.btn_export_report.font())
        widgets.btn_simple_mode_nav.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        widgets.btn_simple_mode_nav.setLayoutDirection(Qt.LeftToRight)
        widgets.btn_simple_mode_nav.setStyleSheet(
            "background-image: url(:/icons/images/icons/cil-external-link.png);")
        widgets.btn_simple_mode_nav.setText("Simple mode")
        widgets.btn_simple_mode_nav.clicked.connect(self.openSimpleMode)
        bottomMenuLayout.addWidget(widgets.btn_simple_mode_nav)

        bottomMenuLayout.addWidget(widgets.btn_export_report)
        widgets.leftMenuFrame.layout().addStretch(1)
        widgets.leftMenuFrame.layout().addWidget(bottomMenu)

        # BUTTONS CLICK
        # ///////////////////////////////////////////////////////////////

        # LEFT MENUS
        widgets.btn_home.clicked.connect(self.buttonClick)

        # SLIDE-OUT PANEL (shared by every multi-page section - the panel
        # contents swap with the active section)
        self._panel_mode = "sensor"
        self._panel_btn = widgets.btn_sensor
        self._configure_panel("sensor")

        for mode, (_label, _names, top_btn) in self._PANEL_SECTIONS.items():
            getattr(widgets, top_btn).clicked.connect(
                lambda _checked=False, m=mode: self.openPanel(m))
        widgets.extraCloseColumnBtn.clicked.connect(
            lambda: UIFunctions.toggleLeftBox(self, True))

        # EVERY SECTION'S SUB-MENU - one dispatcher (see submenuButtonClick /
        # _SUBMENU_TARGETS) instead of one near-identical method per section
        for btn_name in self._SUBMENU_TARGETS:
            getattr(widgets, btn_name).clicked.connect(self.submenuButtonClick)

        # "Export and report" opens a pop-up dialog (ml_tab_report.py)
        # rather than navigating to a page/tab, so it's wired directly
        # instead of through _SUBMENU_TARGETS/submenuButtonClick.
        widgets.btn_export_report.clicked.connect(
            self.ml_prediction_page.open_report)

        # SETTINGS PANEL (right hand box)
        def openCloseRightBox():
            UIFunctions.toggleRightBox(self, True)
        widgets.settingsTopBtn.clicked.connect(openCloseRightBox)
        widgets.btn_about.clicked.connect(self.openAbout)
        widgets.btn_adjustments.clicked.connect(self.openAdjustments)

        # UNIFORM TABLE STYLING - one pass over every QTableWidget in the
        # app (built by every page above) rather than each page styling
        # its own tables: the same card background/outline everything
        # else gets, rows and columns both left user-resizable.
        # ///////////////////////////////////////////////////////////////
        for tbl in self.findChildren(QTableWidget):
            style_table(tbl)

        # SET CUSTOM THEME
        # ///////////////////////////////////////////////////////////////
        useCustomTheme = False
        themeFile = os.path.join("themes", "strikeworks_light.qss")

        # SET THEME AND HACKS
        if useCustomTheme:
            # LOAD AND APPLY STYLE
            UIFunctions.theme(self, themeFile, True)

            # SET HACKS
            AppFunctions.setThemeHack(self)

        # SET HOME PAGE AND SELECT MENU
        # ///////////////////////////////////////////////////////////////
        widgets.stackedWidget.setCurrentWidget(widgets.home)
        self.setSelected(widgets.btn_home)

        # SIMPLE/ADVANCED MODE - the sidebar starts collapsed to the
        # existing PyDracula icon-strip width (toggleButton still works
        # normally, purely cosmetic - it never got hidden, just started
        # narrow) and every section button on it starts disabled; only
        # Home's own "Advanced mode" button activates them, regardless of
        # whether the sidebar itself is later toggled wide or narrow.
        # ///////////////////////////////////////////////////////////////
        widgets.leftMenuBg.setMinimumWidth(_LEFT_MENU_COLLAPSED_WIDTH)
        widgets.leftMenuBg.setMaximumWidth(_LEFT_MENU_COLLAPSED_WIDTH)
        self.set_sidebar_active(False)

        # NOT shown here - Simple mode (page_simple_mode.py) is the app's
        # default landing experience now, opened over this window by
        # main.py's __main__ while this stays hidden; showing it
        # unconditionally at the end of construction (as this used to do)
        # meant it appeared *behind* that modal dialog immediately on
        # launch instead of staying out of the way until the user actually
        # asks for it ("Development toolkit", or closing Simple mode with
        # nothing chosen - both call/fall back to MainWindow.show()
        # themselves, in main.py and page_simple_mode.py respectively).
        # win_utils.ensure_taskbar_button() still runs unconditionally
        # here though: it must happen before this window's *first* show()
        # ever, from whichever of those two paths that turns out to be -
        # see its own docstring for why. SimpleModeDialog gets the same
        # call, in its own __init__ (page_simple_mode.py) - it's the one
        # actually shown first now, and had the identical missing-button
        # symptom for the same underlying reason (see that module).
        # ///////////////////////////////////////////////////////////////
        win_utils.ensure_taskbar_button(self)


    # APPLY THE "SELECTED" HIGHLIGHT TO A MENU BUTTON
    # Deselect first so repeated clicks don't stack the stylesheet.
    # ///////////////////////////////////////////////////////////////
    def setSelected(self, btn):
        clean = UIFunctions.deselectMenu(btn.styleSheet())
        btn.setStyleSheet(UIFunctions.selectMenu(clean))


    # CLOSE THE SLIDE-OUT PANEL IF IT IS OPEN
    # Navigating to another top-level page slides the panel away.
    # ///////////////////////////////////////////////////////////////
    def closeSensorPanel(self):
        if widgets.extraLeftBox.width() > 0:
            UIFunctions.toggleLeftBox(self, True)


    # SLIDE-OUT PANEL MODE
    # One panel serves every multi-page section: its header and sub-menu
    # swap with the requested section. See ROADMAP.md, Chunk 5.
    # ///////////////////////////////////////////////////////////////
    _PANEL_SECTIONS = {
        "bsm": ("Mathematical blade strike modelling",
               ("btn_bsm_calculator", "btn_bsm_sensitivity"),
               "btn_bsm"),
        "setup_deploy": ("Setup and deploy",
                         ("btn_prepare", "btn_study_design",
                          "btn_initiate_deployment"),
                         "btn_setup_deploy"),
        "sensor": ("Sensor processing",
                  ("btn_process", "btn_validate", "btn_data_analysis"),
                  "btn_sensor"),
        "annotation": ("Validate and annotate",
                      ("btn_annotate", "btn_export_animations", "btn_dataset"),
                      "btn_annotation"),
        "model_training": ("Model training",
                           ("btn_ml_training", "btn_evaluate_train",
                            "btn_misclassification", "btn_deploy_train"),
                           "btn_model_training"),
        "model_prediction": ("Model prediction",
                             ("btn_ml_prediction", "btn_inspect_pred",
                              "btn_biological"),
                             "btn_model_prediction"),
    }

    # Every sub-menu button's destination: the stacked-widget page to show,
    # and - for the buttons standing in for a promoted tab (Train/Evaluate/
    # Deploy, Predict/Inspect/Report, Sensor configuration/Study design) -
    # the tab widget and index to select on it. `None, None` for a button
    # that owns its whole page outright.
    _SUBMENU_TARGETS = {
        # Setup and deploy
        "btn_prepare":              ("page_prepare", "tabs_prepare", 0),
        "btn_study_design":         ("page_prepare", "tabs_prepare", 1),
        "btn_initiate_deployment":  ("page_initiate_deployment", None, None),
        # Sensor processing
        "btn_process":              ("page_process", None, None),
        "btn_validate":             ("page_validate", None, None),
        "btn_data_analysis":        ("page_data_analysis", None, None),
        # Validate and annotate
        "btn_annotate":             ("page_annotate", None, None),
        "btn_export_animations":    ("page_export_animations", None, None),
        "btn_dataset":              ("page_dataset", None, None),
        # Model training
        "btn_ml_training":         ("page_ml_training", "tabs_ml_training", 0),
        "btn_evaluate_train":      ("page_ml_training", "tabs_ml_training", 1),
        "btn_deploy_train":        ("page_ml_training", "tabs_ml_training", 2),
        "btn_misclassification":   ("page_misclassification", None, None),
        # Model prediction
        "btn_ml_prediction":  ("page_ml_prediction", "tabs_ml_prediction", 0),
        "btn_inspect_pred":   ("page_ml_prediction", "tabs_ml_prediction", 1),
        "btn_biological":           ("page_biological", None, None),
        # Mathematical Blade Strike Modelling
        "btn_bsm_calculator":       ("page_bsm_calculator", None, None),
        "btn_bsm_sensitivity":      ("page_bsm_sensitivity", None, None),
        # Export and report is NOT here - it's pinned to the bottom of the
        # sidebar (see the relocation right after uiDefinitions() below)
        # and opens a pop-up dialog (ml_tab_report.py) rather than
        # navigating to a page/tab, wired directly to
        # ml_prediction_page.open_report() instead.
    }

    def _section_for_button(self, btn_name):
        for mode, (_label, names, _top) in self._PANEL_SECTIONS.items():
            if btn_name in names:
                return mode
        return None

    def _configure_panel(self, mode):
        label, this_section, top_btn = self._PANEL_SECTIONS[mode]
        widgets.extraLabel.setText(label)
        all_sub_buttons = {
            name for _l, names, _b in self._PANEL_SECTIONS.values()
            for name in names}
        for name in all_sub_buttons:
            getattr(widgets, name).setVisible(name in this_section)
        self._panel_mode = mode
        self._panel_btn = getattr(widgets, top_btn)

    def _swap_panel_ownership(self, mode):
        """Reconfigure the panel for `mode` and move the "owns the open
        panel" highlight (`BTN_LEFT_BOX_COLOR`) from the old top button to
        the new one, in place - no close/reopen. Distinct from the
        MENU_SELECTED_STYLESHEET highlight setSelected()/resetStyle() apply,
        which marks the active top-level page rather than the open panel."""
        color = Settings.BTN_LEFT_BOX_COLOR
        old_btn = self._panel_btn
        old_btn.setStyleSheet(old_btn.styleSheet().replace(color, ''))
        self._configure_panel(mode)
        self._panel_btn.setStyleSheet(self._panel_btn.styleSheet() + color)

    def openPanel(self, mode):
        is_open = widgets.extraLeftBox.width() > 0
        if is_open and self._panel_mode != mode:
            self._swap_panel_ownership(mode)
            return
        self._configure_panel(mode)
        UIFunctions.toggleLeftBox(self, True)


    # BUTTONS CLICK
    # Post here your functions for clicked buttons
    # ///////////////////////////////////////////////////////////////
    def buttonClick(self):
        # GET BUTTON CLICKED
        btn = self.sender()
        btnName = btn.objectName()

        # SHOW HOME PAGE
        if btnName == "btn_home":
            widgets.stackedWidget.setCurrentWidget(widgets.home)
            UIFunctions.resetStyle(self, btnName)
            UIFunctions.resetPanelStyle(self, "")
            self.closeSensorPanel()
            self.setSelected(btn)

        # PRINT BTN NAME
        print(f'Button "{btnName}" pressed!')


    # EVERY SECTION'S SUB-MENU CLICK
    # One dispatcher for every promoted-tab-or-page sub-button (see
    # _SUBMENU_TARGETS above) instead of one near-identical method per
    # section - there are six sections sharing this pattern now.
    # ///////////////////////////////////////////////////////////////
    def navigate_to(self, btn_name):
        """Switch to `btn_name`'s page (and tab index, if it targets one),
        reconfiguring the slide-out panel to its section first so this also
        works when called from outside that section (e.g. a cross-page
        "go to Evaluate" link).

        Leaving Misclassification analysis with at least one correction
        made overrides wherever the user was headed: notify, load the
        corrected dataset into Model training > Train, and land there
        instead - whatever button was actually clicked."""
        mp = self.misclassification_page
        if (widgets.stackedWidget.currentWidget() is
                widgets.page_misclassification
                and btn_name != "btn_misclassification"
                and mp.has_changes()):
            mp.notify_and_load_into_training()
            btn_name = "btn_ml_training"

        section = self._section_for_button(btn_name)
        if section is not None:
            is_open = widgets.extraLeftBox.width() > 0
            if is_open and section != self._panel_mode:
                self._swap_panel_ownership(section)
            else:
                self._configure_panel(section)

        target = self._SUBMENU_TARGETS.get(btn_name)
        if target is None:
            return
        page_name, tab_widget_name, tab_index = target
        widgets.stackedWidget.setCurrentWidget(getattr(widgets, page_name))
        if tab_widget_name is not None:
            getattr(widgets, tab_widget_name).setCurrentIndex(tab_index)

        # HIGHLIGHT THE SUB-MENU ENTRY
        UIFunctions.resetPanelStyle(self, btn_name)
        self.setSelected(getattr(widgets, btn_name))

        # KEEP THE SECTION MARKED AS THE ACTIVE TOP-LEVEL MENU
        if section is not None:
            top_btn = self._PANEL_SECTIONS[section][2]
            UIFunctions.resetStyle(self, top_btn)
            self.setSelected(getattr(widgets, top_btn))

    def submenuButtonClick(self):
        btn = self.sender()
        self.navigate_to(btn.objectName())
        print(f'Button "{btn.objectName()}" pressed!')


    # ABOUT - UI TEMPLATE CREDIT
    # ///////////////////////////////////////////////////////////////
    def openAbout(self):
        QDesktopServices.openUrl(QUrl(TEMPLATE_URL))
        print(f"Opened UI template credit: {TEMPLATE_URL}")

    # ADJUSTMENTS - folder settings (modules/page_adjustments.py)
    # ///////////////////////////////////////////////////////////////
    def openAdjustments(self):
        dlg = AdjustmentsDialog(self)
        dlg.exec()
        # the libraries folder may have changed - Home owns library
        # discovery, so it's what re-reads settings.get_libraries_dir()
        self.home_page._refresh_library_combo()

    # SIDEBAR ACTIVATION - Simple/Advanced mode (Home; page_simple_mode.py)
    # The sidebar's own show/hide (`toggleButton`, unchanged - still just
    # animates leftMenuBg between the 60px icon strip and MENU_WIDTH) is
    # purely cosmetic now: every section button on it starts disabled
    # (`_SIDEBAR_NAV_BUTTONS`, greyed out) regardless of width, and stays
    # that way through any amount of toggling. Only Home's own "Advanced
    # mode" button - `expand_sidebar()` - actually activates them; the
    # sidebar's width and its buttons' enabled state are deliberately two
    # separate things now, not one.
    # ///////////////////////////////////////////////////////////////
    _SIDEBAR_NAV_BUTTONS = (
        "btn_bsm", "btn_setup_deploy", "btn_sensor", "btn_annotation",
        "btn_model_training", "btn_model_prediction", "btn_export_report",
    )

    def set_sidebar_active(self, active):
        for name in self._SIDEBAR_NAV_BUTTONS:
            getattr(widgets, name).setEnabled(active)

    def expand_sidebar(self):
        widgets.leftMenuBg.setMinimumWidth(Settings.MENU_WIDTH)
        widgets.leftMenuBg.setMaximumWidth(Settings.MENU_WIDTH)
        self.set_sidebar_active(True)

    # SIMPLE MODE - pop-up walkthrough (modules/page_simple_mode.py)
    # ///////////////////////////////////////////////////////////////
    def openSimpleMode(self):
        """Runs Simple mode's wizard modally. Returns True if it was left
        via "Development toolkit" (which already made MainWindow visible
        itself - page_simple_mode.py's _go_development_toolkit), False
        if closed any other way (Close button, window X). main.py's own
        startup call uses this to decide whether to fall back to showing
        MainWindow or quit the app entirely; the sidebar's own "Simple
        mode" button - already in Advanced mode, by definition, whenever
        it's reachable - ignores the return value."""
        self.simple_mode_dialog.exec()
        return self.simple_mode_dialog.went_to_dev_toolkit


    # RESIZE EVENTS
    # ///////////////////////////////////////////////////////////////
    def resizeEvent(self, event):
        # Update Size Grips
        UIFunctions.resize_grips(self)

    # MOUSE CLICK EVENTS
    # ///////////////////////////////////////////////////////////////
    def mousePressEvent(self, event):
        # SET DRAG POS WINDOW
        self.dragPos = event.globalPos()

        # PRINT MOUSE EVENTS
        if event.buttons() == Qt.LeftButton:
            print('Mouse click: LEFT CLICK')
        if event.buttons() == Qt.RightButton:
            print('Mouse click: RIGHT CLICK')

def _build_splash():
    """Loading splash shown while MainWindow() constructs every page -
    same look as Simple mode's Welcome page (page_simple_mode.py): the
    PyDracula_vertical logo + "Deploy. Process. Predict.", plus a
    "Loading application..." message for this moment specifically.

    The logo + tagline are centred as one block within the space above
    the loading message (not pinned near the top with the message just
    tacked on at the bottom) - they used to be positioned independently
    at fixed offsets, which read as slightly top-heavy/off-centre."""
    pix = QPixmap(420, 480)
    pix.fill(QColor("#21252b"))   # PyDracula's own dark background
    painter = QPainter(pix)

    logo_path = Path(__file__).parent / "images" / "images" / "PyDracula_vertical.png"
    logo = QPixmap(str(logo_path)) if logo_path.exists() else None
    if logo is not None and not logo.isNull():
        logo = logo.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation)

    font = QFont()
    font.setPointSize(13)
    font.setItalic(True)
    painter.setFont(font)
    tagline = "Deploy. Process. Predict."
    tagline_h = painter.fontMetrics().height()

    bottom_reserved = 60   # room for the "Loading application..." message
    usable_h = pix.height() - bottom_reserved
    spacing = 20
    logo_h = logo.height() if logo is not None and not logo.isNull() else 0
    block_h = logo_h + (spacing if logo_h else 0) + tagline_h
    top = max(20, (usable_h - block_h) // 2)

    if logo is not None and not logo.isNull():
        painter.drawPixmap((pix.width() - logo.width()) // 2, top, logo)
        top += logo_h + spacing

    painter.setPen(QColor("#dddddd"))
    painter.drawText(0, top, pix.width(), tagline_h,
                     int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                     tagline)
    painter.end()

    splash = QSplashScreen(pix)
    # stay above every other window for the whole loading window,
    # including MainWindow's own brief pre-final-layout state and any
    # other top-level widget that happens to construct itself in the
    # process - nothing should visibly pop up in front of/beside it
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.showMessage(
        "Loading application...",
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
        QColor("#8a95aa"))
    return splash


def _ensure_default_folders():
    """Creates the four default data folders (libraries/models/
    output_data/input_data) if they don't already exist - packaged, these
    live next to the .exe (settings.app_root()); a fresh install should
    show them immediately rather than only after something happens to
    write into one for the first time. Cheap and safe to call on every
    launch, source or frozen."""
    from modules import settings
    for getter in (settings.get_libraries_dir, settings.get_models_dir,
                  settings.get_output_dir, settings.get_input_data_dir):
        try:
            getter().mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def _set_windows_app_id():
    """Windows groups/identifies taskbar buttons by AppUserModelID, not
    by window icon alone - without explicitly setting one, a Python-based
    exe can get folded under (and iconed as) a generic "python"/host
    identity rather than showing its own icon.ico. No-op off Windows."""
    if platform.system() != "Windows":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "StrikeWorks.App")
    except Exception:
        pass


if __name__ == "__main__":
    _set_windows_app_id()
    _ensure_default_folders()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(_ICON_PATH)))
    table_copy.install(app)
    splash = _build_splash()
    splash.show()
    app.processEvents()
    window = MainWindow()
    # MainWindow itself is NOT shown here (see its own __init__) - Simple
    # mode is what the user actually sees first, and QSplashScreen.finish()
    # only hides the splash once the widget passed to it isVisible(), so
    # it's closed directly instead of via finish(window), which would
    # otherwise silently no-op forever against a window that's staying
    # hidden on purpose.
    splash.close()
    # exec() blocks in its own nested Qt event loop until the user closes
    # Simple mode or picks "Development toolkit" (which shows MainWindow,
    # already switched to Advanced mode, itself - page_simple_mode.py's
    # _go_development_toolkit, and is what the True return means here).
    # Any other way out (Close button, window X) means the user never
    # asked for the full app at all - quit outright rather than falling
    # back to showing it anyway, which used to happen unconditionally.
    went_to_dev_toolkit = window.openSimpleMode()
    if not went_to_dev_toolkit:
        sys.exit(0)
    sys.exit(app.exec_())
