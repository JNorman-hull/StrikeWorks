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
from modules.page_process import ProcessPage
from modules.page_validate import ValidatePage
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

        # QTableWidget PARAMETERS
        # ///////////////////////////////////////////////////////////////
        widgets.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # PAGE CONTROLLERS
        # ///////////////////////////////////////////////////////////////
        self.process_page = ProcessPage(widgets, self)
        self.process_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))
        self.validate_page = ValidatePage(widgets, self)
        self.validate_page.status.connect(
            lambda msg, ms: print(f"[status] {msg}"))

        # BUTTONS CLICK
        # ///////////////////////////////////////////////////////////////

        # LEFT MENUS
        widgets.btn_home.clicked.connect(self.buttonClick)
        widgets.btn_widgets.clicked.connect(self.buttonClick)
        widgets.btn_new.clicked.connect(self.buttonClick)
        widgets.btn_save.clicked.connect(self.buttonClick)

        # SENSOR PROCESSING PANEL (slides out of the left menu)
        def openCloseSensorBox():
            UIFunctions.toggleLeftBox(self, True)
        widgets.btn_sensor.clicked.connect(openCloseSensorBox)
        widgets.extraCloseColumnBtn.clicked.connect(openCloseSensorBox)

        # SENSOR PROCESSING SUB-MENU
        widgets.btn_prepare.clicked.connect(self.sensorButtonClick)
        widgets.btn_process.clicked.connect(self.sensorButtonClick)
        widgets.btn_validate.clicked.connect(self.sensorButtonClick)
        widgets.btn_dataset.clicked.connect(self.sensorButtonClick)

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


    # CLOSE THE SENSOR PROCESSING PANEL IF IT IS OPEN
    # Navigating to another top-level page slides the panel away.
    # ///////////////////////////////////////////////////////////////
    def closeSensorPanel(self):
        if widgets.extraLeftBox.width() > 0:
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

        # SHOW WIDGETS PAGE
        if btnName == "btn_widgets":
            widgets.stackedWidget.setCurrentWidget(widgets.widgets)
            UIFunctions.resetStyle(self, btnName)
            UIFunctions.resetPanelStyle(self, "")
            self.closeSensorPanel()
            self.setSelected(btn)

        # SHOW NEW PAGE
        if btnName == "btn_new":
            widgets.stackedWidget.setCurrentWidget(widgets.new_page) # SET PAGE
            UIFunctions.resetStyle(self, btnName) # RESET ANOTHERS BUTTONS SELECTED
            UIFunctions.resetPanelStyle(self, "")
            self.closeSensorPanel()
            self.setSelected(btn) # SELECT MENU

        if btnName == "btn_save":
            print("Save BTN clicked!")

        # PRINT BTN NAME
        print(f'Button "{btnName}" pressed!')


    # SENSOR PROCESSING SUB-MENU CLICK
    # ///////////////////////////////////////////////////////////////
    def sensorButtonClick(self):
        btn = self.sender()
        btnName = btn.objectName()

        pages = {
            "btn_prepare":  widgets.page_prepare,
            "btn_process":  widgets.page_process,
            "btn_validate": widgets.page_validate,
            "btn_dataset":  widgets.page_dataset,
        }

        if btnName in pages:
            widgets.stackedWidget.setCurrentWidget(pages[btnName])

            # HIGHLIGHT THE SUB-MENU ENTRY
            UIFunctions.resetPanelStyle(self, btnName)
            self.setSelected(btn)

            # KEEP "SENSOR PROCESSING" MARKED AS THE ACTIVE TOP-LEVEL MENU
            UIFunctions.resetStyle(self, "btn_sensor")
            self.setSelected(widgets.btn_sensor)

        # PRINT BTN NAME
        print(f'Button "{btnName}" pressed!')


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
    window = MainWindow()
    sys.exit(app.exec_())
