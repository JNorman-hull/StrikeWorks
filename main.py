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
from modules import table_copy
os.environ["QT_FONT_DPI"] = "96" # FIX Problem for High DPI and Scale above 100%

# SET AS GLOBAL WIDGETS
# ///////////////////////////////////////////////////////////////
widgets = None

# UI TEMPLATE CREDIT (shown under Settings > About)
# ///////////////////////////////////////////////////////////////
TEMPLATE_URL = "https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6"


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

        # PAGE CONTROLLERS
        # ///////////////////////////////////////////////////////////////
        # Prepare comes first: the sensor chosen here drives raw import,
        # validation and dataset creation on the pages that follow.
        self.prepare_page = PreparePage(widgets, self)
        self.prepare_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.process_page = ProcessPage(widgets, self)
        self.process_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.validate_page = ValidatePage(widgets, self)
        self.validate_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.dataset_page = DatasetPage(widgets, self)
        self.dataset_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.initiate_deployment_page = InitiateDeploymentPage(widgets, self)
        self.initiate_deployment_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # ANNOTATION & VIDEO ANALYSIS PAGES
        self.annotation_page = AnnotationPage(widgets, self)
        self.annotation_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # MACHINE LEARNING ANALYSIS PAGES
        self.ml_prediction_page = MLPredictionPage(widgets, self)
        self.ml_prediction_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.ml_training_page = MLTrainingPage(widgets, self)
        self.ml_training_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # the curated dataset from Sensor Processing feeds Model Prediction
        self.dataset_page.dataset_ready.connect(
            self.ml_prediction_page.on_dataset_ready)

        # a freshly deployed model becomes available to Model Prediction
        self.ml_training_page.model_deployed.connect(
            lambda _p: self.ml_prediction_page.state.load_models_from_dir(
                self.ml_prediction_page.state.models_dir))

        # STUB PAGES (Chunk 5 restructure - not built yet; see ROADMAP.md)
        # ///////////////////////////////////////////////////////////////
        self._stub_pages = [
            StubPage(widgets.content_bsm_calculator, "Calculator",
                     "Blade strike calculator. Part of task 5 (blade strike "
                     "modelling port)."),
            StubPage(widgets.content_bsm_sensitivity, "Sensitivity analysis",
                     "Part of task 5."),
            StubPage(widgets.content_bsm_reporting, "Reporting",
                     "Blade strike modelling report, saved as JSON for "
                     "Setup and deploy to read. Part of task 5."),
            StubPage(widgets.content_data_analysis, "Data analysis",
                     "Passage duration, time-series normalisation, "
                     "barotrauma metrics, acceleration peak finding. Part "
                     "of task 7."),
            StubPage(widgets.content_export_animations, "Export animations",
                     "Ports video_sync.py. Part of task 4."),
            StubPage(widgets.content_misclassification,
                     "Misclassification analysis", "Part of task 3."),
            StubPage(widgets.content_biological, "Biological interpretation",
                     "Part of task 5."),
            StubPage(widgets.content_final_report, "Final reporting",
                     "Part of task 5."),
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

        move_before("btn_study_design", "btn_prepare")
        move_before("btn_export_animations", "btn_dataset")
        move_after("btn_deploy_train", "btn_misclassification")

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

        # SETTINGS PANEL (right hand box)
        def openCloseRightBox():
            UIFunctions.toggleRightBox(self, True)
        widgets.settingsTopBtn.clicked.connect(openCloseRightBox)
        widgets.btn_about.clicked.connect(self.openAbout)

        # SHOW APP
        # ///////////////////////////////////////////////////////////////
        self.show()

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
               ("btn_bsm_calculator", "btn_bsm_sensitivity",
                "btn_bsm_reporting"),
               "btn_bsm"),
        "setup_deploy": ("Setup and deploy",
                         ("btn_study_design", "btn_prepare",
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
                              "btn_report_pred", "btn_biological",
                              "btn_final_report"),
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
        "btn_report_pred":    ("page_ml_prediction", "tabs_ml_prediction", 2),
        "btn_biological":           ("page_biological", None, None),
        "btn_final_report":         ("page_final_report", None, None),
        # Mathematical Blade Strike Modelling
        "btn_bsm_calculator":       ("page_bsm_calculator", None, None),
        "btn_bsm_sensitivity":      ("page_bsm_sensitivity", None, None),
        "btn_bsm_reporting":        ("page_bsm_reporting", None, None),
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
        "go to Evaluate" link)."""
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("icon.ico"))
    table_copy.install(app)
    window = MainWindow()
    sys.exit(app.exec_())
