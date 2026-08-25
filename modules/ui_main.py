# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main.ui'
##
## Created by: Qt User Interface Compiler version 6.11.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea, QApplication, QCheckBox,
    QComboBox, QCommandLinkButton, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QPlainTextEdit, QPushButton, QRadioButton, QScrollArea,
    QScrollBar, QSizePolicy, QSlider, QSpacerItem,
    QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QTreeView, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget)
import resources_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1205, 896)
        MainWindow.setMinimumSize(QSize(940, 560))
        self.styleSheet = QWidget(MainWindow)
        self.styleSheet.setObjectName(u"styleSheet")
        font = QFont()
        font.setFamilies([u"Segoe UI"])
        font.setPointSize(10)
        font.setBold(False)
        font.setItalic(False)
        self.styleSheet.setFont(font)
        self.styleSheet.setStyleSheet(u"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"\n"
"SET APP STYLESHEET - FULL STYLES HERE\n"
"STRIKEWORKS - DEFAULT DARK THEME\n"
"\n"
"///////////////////////////////////////////////////////////////////////////////////////////////// */\n"
"\n"
"QWidget{\n"
"	color: rgb(221, 221, 221);\n"
"	font: 10pt \"Segoe UI\";\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Tooltip */\n"
"QToolTip {\n"
"	color: #ffffff;\n"
"	background-color: rgba(33, 37, 43, 180);\n"
"	border: 1px solid rgb(44, 49, 58);\n"
"	background-image: none;\n"
"	background-position: left center;\n"
"    background-repeat: no-repeat;\n"
"	border: none;\n"
"	border-left: 2px solid rgb(255, 121, 198);\n"
"	text-align: left;\n"
"	padding-left: 8px;\n"
"	margin: 0px;\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Bg App */\n"
"#bgApp {	\n"
"	background"
                        "-color: rgb(40, 44, 52);\n"
"	border: 1px solid rgb(44, 49, 58);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Left Menu */\n"
"#leftMenuBg {	\n"
"	background-color: rgb(33, 37, 43);\n"
"}\n"
"#topLogo {\n"
"	background-color: rgb(33, 37, 43);\n"
"	background-image: url(:/images/images/images/PyDracula.png);\n"
"	background-position: centered;\n"
"	background-repeat: no-repeat;\n"
"}\n"
"#titleLeftApp { font: 63 12pt \"Segoe UI Semibold\"; }\n"
"#titleLeftDescription { font: 8pt \"Segoe UI\"; color: rgb(189, 147, 249); }\n"
"\n"
"/* MENUS */\n"
"#topMenu .QPushButton {	\n"
"	background-position: left center;\n"
"    background-repeat: no-repeat;\n"
"	border: none;\n"
"	border-left: 22px solid transparent;\n"
"	background-color: transparent;\n"
"	text-align: left;\n"
"	padding-left: 44px;\n"
"}\n"
"#topMenu .QPushButton:hover {\n"
"	background-color: rgb(40, 44, 52);\n"
"}\n"
"#topMenu .QPushButton:pressed {	\n"
"	background-color: rgb(18"
                        "9, 147, 249);\n"
"	color: rgb(255, 255, 255);\n"
"}\n"
"#bottomMenu .QPushButton {	\n"
"	background-position: left center;\n"
"    background-repeat: no-repeat;\n"
"	border: none;\n"
"	border-left: 20px solid transparent;\n"
"	background-color:transparent;\n"
"	text-align: left;\n"
"	padding-left: 44px;\n"
"}\n"
"#bottomMenu .QPushButton:hover {\n"
"	background-color: rgb(40, 44, 52);\n"
"}\n"
"#bottomMenu .QPushButton:pressed {	\n"
"	background-color: rgb(189, 147, 249);\n"
"	color: rgb(255, 255, 255);\n"
"}\n"
"#leftMenuFrame{\n"
"	border-top: 3px solid rgb(44, 49, 58);\n"
"}\n"
"\n"
"/* Toggle Button */\n"
"#toggleButton {\n"
"	background-position: left center;\n"
"    background-repeat: no-repeat;\n"
"	border: none;\n"
"	border-left: 20px solid transparent;\n"
"	background-color: rgb(37, 41, 48);\n"
"	text-align: left;\n"
"	padding-left: 44px;\n"
"	color: rgb(113, 126, 149);\n"
"}\n"
"#toggleButton:hover {\n"
"	background-color: rgb(40, 44, 52);\n"
"}\n"
"#toggleButton:pressed {\n"
"	background-color: rgb("
                        "189, 147, 249);\n"
"}\n"
"\n"
"/* Title Menu */\n"
"#titleRightInfo { padding-left: 10px; }\n"
"\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Extra Tab */\n"
"#extraLeftBox {	\n"
"	background-color: rgb(44, 49, 58);\n"
"}\n"
"#extraTopBg{	\n"
"	background-color: rgb(189, 147, 249)\n"
"}\n"
"\n"
"/* Icon */\n"
"#extraIcon {\n"
"	background-position: center;\n"
"	background-repeat: no-repeat;\n"
"	background-image: url(:/icons/images/icons/icon_settings.png);\n"
"}\n"
"\n"
"/* Label */\n"
"#extraLabel { color: rgb(255, 255, 255); }\n"
"\n"
"/* Btn Close */\n"
"#extraCloseColumnBtn { background-color: rgba(255, 255, 255, 0); border: none;  border-radius: 5px; }\n"
"#extraCloseColumnBtn:hover { background-color: rgb(196, 161, 249); border-style: solid; border-radius: 4px; }\n"
"#extraCloseColumnBtn:pressed { background-color: rgb(180, 141, 238); border-style: solid; border-radius: 4px; }\n"
"\n"
"/* Extra Content */\n"
"#extraContent{\n"
"	border"
                        "-top: 3px solid rgb(40, 44, 52);\n"
"}\n"
"\n"
"/* Extra Top Menus */\n"
"#extraTopMenu .QPushButton {\n"
"background-position: left center;\n"
"    background-repeat: no-repeat;\n"
"	border: none;\n"
"	border-left: 22px solid transparent;\n"
"	background-color:transparent;\n"
"	text-align: left;\n"
"	padding-left: 44px;\n"
"}\n"
"#extraTopMenu .QPushButton:hover {\n"
"	background-color: rgb(40, 44, 52);\n"
"}\n"
"#extraTopMenu .QPushButton:pressed {	\n"
"	background-color: rgb(189, 147, 249);\n"
"	color: rgb(255, 255, 255);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Content App */\n"
"#contentTopBg{	\n"
"	background-color: rgb(33, 37, 43);\n"
"}\n"
"#contentBottom{\n"
"	border-top: 3px solid rgb(44, 49, 58);\n"
"}\n"
"\n"
"/* Top Buttons */\n"
"#rightButtons .QPushButton { background-color: rgba(255, 255, 255, 0); border: none;  border-radius: 5px; }\n"
"#rightButtons .QPushButton:hover { background-color: rgb(44, 49, 57); border-sty"
                        "le: solid; border-radius: 4px; }\n"
"#rightButtons .QPushButton:pressed { background-color: rgb(23, 26, 30); border-style: solid; border-radius: 4px; }\n"
"\n"
"/* Theme Settings */\n"
"#extraRightBox { background-color: rgb(44, 49, 58); }\n"
"#themeSettingsTopDetail { background-color: rgb(189, 147, 249); }\n"
"\n"
"/* Bottom Bar */\n"
"#bottomBar { background-color: rgb(44, 49, 58); }\n"
"#bottomBar QLabel { font-size: 11px; color: rgb(113, 126, 149); padding-left: 10px; padding-right: 10px; padding-bottom: 2px; }\n"
"\n"
"/* CONTENT SETTINGS */\n"
"/* MENUS */\n"
"#contentSettings .QPushButton {	\n"
"	background-position: left center;\n"
"    background-repeat: no-repeat;\n"
"	border: none;\n"
"	border-left: 22px solid transparent;\n"
"	background-color:transparent;\n"
"	text-align: left;\n"
"	padding-left: 44px;\n"
"}\n"
"#contentSettings .QPushButton:hover {\n"
"	background-color: rgb(40, 44, 52);\n"
"}\n"
"#contentSettings .QPushButton:pressed {	\n"
"	background-color: rgb(189, 147, 249);\n"
"	color: rgb"
                        "(255, 255, 255);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"QTableWidget */\n"
"QTableWidget {	\n"
"	background-color: transparent;\n"
"	padding: 10px;\n"
"	border-radius: 5px;\n"
"	gridline-color: rgb(44, 49, 58);\n"
"	border-bottom: 1px solid rgb(44, 49, 60);\n"
"}\n"
"QTableWidget::item{\n"
"	border-color: rgb(44, 49, 60);\n"
"	padding-left: 5px;\n"
"	padding-right: 5px;\n"
"	gridline-color: rgb(44, 49, 60);\n"
"}\n"
"QTableWidget::item:selected{\n"
"	background-color: rgb(189, 147, 249);\n"
"}\n"
"QHeaderView::section{\n"
"	background-color: rgb(33, 37, 43);\n"
"	max-width: 30px;\n"
"	border: 1px solid rgb(44, 49, 58);\n"
"	border-style: none;\n"
"    border-bottom: 1px solid rgb(44, 49, 60);\n"
"    border-right: 1px solid rgb(44, 49, 60);\n"
"}\n"
"QTableWidget::horizontalHeader {	\n"
"	background-color: rgb(33, 37, 43);\n"
"}\n"
"QHeaderView::section:horizontal\n"
"{\n"
"    border: 1px solid rgb(33, 37, 43);\n"
"	background-co"
                        "lor: rgb(33, 37, 43);\n"
"	padding: 3px;\n"
"	border-top-left-radius: 7px;\n"
"    border-top-right-radius: 7px;\n"
"}\n"
"QHeaderView::section:vertical\n"
"{\n"
"    border: 1px solid rgb(44, 49, 60);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"LineEdit */\n"
"QLineEdit {\n"
"	background-color: rgb(33, 37, 43);\n"
"	border-radius: 5px;\n"
"	border: 2px solid rgb(33, 37, 43);\n"
"	padding-left: 10px;\n"
"	selection-color: rgb(255, 255, 255);\n"
"	selection-background-color: rgb(255, 121, 198);\n"
"}\n"
"QLineEdit:hover {\n"
"	border: 2px solid rgb(64, 71, 88);\n"
"}\n"
"QLineEdit:focus {\n"
"	border: 2px solid rgb(91, 101, 124);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"PlainTextEdit */\n"
"QPlainTextEdit {\n"
"	background-color: rgb(27, 29, 35);\n"
"	border-radius: 5px;\n"
"	padding: 10px;\n"
"	selection-color: rgb(255, 255, 255);\n"
"	selection-background-c"
                        "olor: rgb(255, 121, 198);\n"
"}\n"
"QPlainTextEdit  QScrollBar:vertical {\n"
"    width: 8px;\n"
" }\n"
"QPlainTextEdit  QScrollBar:horizontal {\n"
"    height: 8px;\n"
" }\n"
"QPlainTextEdit:hover {\n"
"	border: 2px solid rgb(64, 71, 88);\n"
"}\n"
"QPlainTextEdit:focus {\n"
"	border: 2px solid rgb(91, 101, 124);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"ScrollBars */\n"
"QScrollBar:horizontal {\n"
"    border: none;\n"
"    background: rgb(52, 59, 72);\n"
"    height: 8px;\n"
"    margin: 0px 21px 0 21px;\n"
"	border-radius: 0px;\n"
"}\n"
"QScrollBar::handle:horizontal {\n"
"    background: rgb(189, 147, 249);\n"
"    min-width: 25px;\n"
"	border-radius: 4px\n"
"}\n"
"QScrollBar::add-line:horizontal {\n"
"    border: none;\n"
"    background: rgb(55, 63, 77);\n"
"    width: 20px;\n"
"	border-top-right-radius: 4px;\n"
"    border-bottom-right-radius: 4px;\n"
"    subcontrol-position: right;\n"
"    subcontrol-origin: margin;\n"
"}\n"
""
                        "QScrollBar::sub-line:horizontal {\n"
"    border: none;\n"
"    background: rgb(55, 63, 77);\n"
"    width: 20px;\n"
"	border-top-left-radius: 4px;\n"
"    border-bottom-left-radius: 4px;\n"
"    subcontrol-position: left;\n"
"    subcontrol-origin: margin;\n"
"}\n"
"QScrollBar::up-arrow:horizontal, QScrollBar::down-arrow:horizontal\n"
"{\n"
"     background: none;\n"
"}\n"
"QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal\n"
"{\n"
"     background: none;\n"
"}\n"
" QScrollBar:vertical {\n"
"	border: none;\n"
"    background: rgb(52, 59, 72);\n"
"    width: 8px;\n"
"    margin: 21px 0 21px 0;\n"
"	border-radius: 0px;\n"
" }\n"
" QScrollBar::handle:vertical {	\n"
"	background: rgb(189, 147, 249);\n"
"    min-height: 25px;\n"
"	border-radius: 4px\n"
" }\n"
" QScrollBar::add-line:vertical {\n"
"     border: none;\n"
"    background: rgb(55, 63, 77);\n"
"     height: 20px;\n"
"	border-bottom-left-radius: 4px;\n"
"    border-bottom-right-radius: 4px;\n"
"     subcontrol-position: bottom;\n"
"     su"
                        "bcontrol-origin: margin;\n"
" }\n"
" QScrollBar::sub-line:vertical {\n"
"	border: none;\n"
"    background: rgb(55, 63, 77);\n"
"     height: 20px;\n"
"	border-top-left-radius: 4px;\n"
"    border-top-right-radius: 4px;\n"
"     subcontrol-position: top;\n"
"     subcontrol-origin: margin;\n"
" }\n"
" QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {\n"
"     background: none;\n"
" }\n"
"\n"
" QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {\n"
"     background: none;\n"
" }\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"CheckBox */\n"
"QCheckBox::indicator {\n"
"    border: 3px solid rgb(52, 59, 72);\n"
"	width: 15px;\n"
"	height: 15px;\n"
"	border-radius: 10px;\n"
"    background: rgb(44, 49, 60);\n"
"}\n"
"QCheckBox::indicator:hover {\n"
"    border: 3px solid rgb(58, 66, 81);\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    background: 3px solid rgb(52, 59, 72);\n"
"	border: 3px solid rgb(52, 59, 72);	\n"
"	back"
                        "ground-image: url(:/icons/images/icons/cil-check-alt.png);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"RadioButton */\n"
"QRadioButton::indicator {\n"
"    border: 3px solid rgb(52, 59, 72);\n"
"	width: 15px;\n"
"	height: 15px;\n"
"	border-radius: 10px;\n"
"    background: rgb(44, 49, 60);\n"
"}\n"
"QRadioButton::indicator:hover {\n"
"    border: 3px solid rgb(58, 66, 81);\n"
"}\n"
"QRadioButton::indicator:checked {\n"
"    background: 3px solid rgb(94, 106, 130);\n"
"	border: 3px solid rgb(52, 59, 72);	\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"ComboBox */\n"
"QComboBox{\n"
"	background-color: rgb(27, 29, 35);\n"
"	border-radius: 5px;\n"
"	border: 2px solid rgb(33, 37, 43);\n"
"	padding: 5px;\n"
"	padding-left: 10px;\n"
"}\n"
"QComboBox:hover{\n"
"	border: 2px solid rgb(64, 71, 88);\n"
"}\n"
"QComboBox::drop-down {\n"
"	subcontrol-origin: padding;\n"
"	subco"
                        "ntrol-position: top right;\n"
"	width: 25px; \n"
"	border-left-width: 3px;\n"
"	border-left-color: rgba(39, 44, 54, 150);\n"
"	border-left-style: solid;\n"
"	border-top-right-radius: 3px;\n"
"	border-bottom-right-radius: 3px;	\n"
"	background-image: url(:/icons/images/icons/cil-arrow-bottom.png);\n"
"	background-position: center;\n"
"	background-repeat: no-reperat;\n"
" }\n"
"QComboBox QAbstractItemView {\n"
"	color: rgb(255, 121, 198);	\n"
"	background-color: rgb(33, 37, 43);\n"
"	padding: 10px;\n"
"	selection-background-color: rgb(39, 44, 54);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Sliders */\n"
"QSlider::groove:horizontal {\n"
"    border-radius: 5px;\n"
"    height: 10px;\n"
"	margin: 0px;\n"
"	background-color: rgb(52, 59, 72);\n"
"}\n"
"QSlider::groove:horizontal:hover {\n"
"	background-color: rgb(55, 62, 76);\n"
"}\n"
"QSlider::handle:horizontal {\n"
"    background-color: rgb(189, 147, 249);\n"
"    border: none;\n"
"    h"
                        "eight: 10px;\n"
"    width: 10px;\n"
"    margin: 0px;\n"
"	border-radius: 5px;\n"
"}\n"
"QSlider::handle:horizontal:hover {\n"
"    background-color: rgb(195, 155, 255);\n"
"}\n"
"QSlider::handle:horizontal:pressed {\n"
"    background-color: rgb(255, 121, 198);\n"
"}\n"
"\n"
"QSlider::groove:vertical {\n"
"    border-radius: 5px;\n"
"    width: 10px;\n"
"    margin: 0px;\n"
"	background-color: rgb(52, 59, 72);\n"
"}\n"
"QSlider::groove:vertical:hover {\n"
"	background-color: rgb(55, 62, 76);\n"
"}\n"
"QSlider::handle:vertical {\n"
"    background-color: rgb(189, 147, 249);\n"
"	border: none;\n"
"    height: 10px;\n"
"    width: 10px;\n"
"    margin: 0px;\n"
"	border-radius: 5px;\n"
"}\n"
"QSlider::handle:vertical:hover {\n"
"    background-color: rgb(195, 155, 255);\n"
"}\n"
"QSlider::handle:vertical:pressed {\n"
"    background-color: rgb(255, 121, 198);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"CommandLinkButton */\n"
"QCommandLi"
                        "nkButton {	\n"
"	color: rgb(255, 121, 198);\n"
"	border-radius: 5px;\n"
"	padding: 5px;\n"
"	color: rgb(255, 170, 255);\n"
"}\n"
"QCommandLinkButton:hover {	\n"
"	color: rgb(255, 170, 255);\n"
"	background-color: rgb(44, 49, 60);\n"
"}\n"
"QCommandLinkButton:pressed {	\n"
"	color: rgb(189, 147, 249);\n"
"	background-color: rgb(52, 58, 71);\n"
"}\n"
"\n"
"/* /////////////////////////////////////////////////////////////////////////////////////////////////\n"
"Button */\n"
"#pagesContainer QPushButton {\n"
"	border: 2px solid rgb(52, 59, 72);\n"
"	border-radius: 5px;	\n"
"	background-color: rgb(52, 59, 72);\n"
"}\n"
"#pagesContainer QPushButton:hover {\n"
"	background-color: rgb(57, 65, 80);\n"
"	border: 2px solid rgb(61, 70, 86);\n"
"}\n"
"#pagesContainer QPushButton:pressed {	\n"
"	background-color: rgb(35, 40, 49);\n"
"	border: 2px solid rgb(43, 50, 61);\n"
"}\n"
"\n"
"")
        self.appMargins = QVBoxLayout(self.styleSheet)
        self.appMargins.setSpacing(0)
        self.appMargins.setObjectName(u"appMargins")
        self.appMargins.setContentsMargins(10, 10, 10, 10)
        self.bgApp = QFrame(self.styleSheet)
        self.bgApp.setObjectName(u"bgApp")
        self.bgApp.setStyleSheet(u"")
        self.bgApp.setFrameShape(QFrame.NoFrame)
        self.bgApp.setFrameShadow(QFrame.Raised)
        self.appLayout = QHBoxLayout(self.bgApp)
        self.appLayout.setSpacing(0)
        self.appLayout.setObjectName(u"appLayout")
        self.appLayout.setContentsMargins(0, 0, 0, 0)
        self.leftMenuBg = QFrame(self.bgApp)
        self.leftMenuBg.setObjectName(u"leftMenuBg")
        self.leftMenuBg.setMinimumSize(QSize(240, 0))
        self.leftMenuBg.setMaximumSize(QSize(240, 16777215))
        self.leftMenuBg.setFrameShape(QFrame.NoFrame)
        self.leftMenuBg.setFrameShadow(QFrame.Raised)
        self.verticalLayout_3 = QVBoxLayout(self.leftMenuBg)
        self.verticalLayout_3.setSpacing(0)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.verticalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.topLogoInfo = QFrame(self.leftMenuBg)
        self.topLogoInfo.setObjectName(u"topLogoInfo")
        self.topLogoInfo.setMinimumSize(QSize(0, 50))
        self.topLogoInfo.setMaximumSize(QSize(16777215, 50))
        self.topLogoInfo.setFrameShape(QFrame.NoFrame)
        self.topLogoInfo.setFrameShadow(QFrame.Raised)
        self.topLogo = QFrame(self.topLogoInfo)
        self.topLogo.setObjectName(u"topLogo")
        self.topLogo.setGeometry(QRect(10, 5, 42, 42))
        self.topLogo.setMinimumSize(QSize(42, 42))
        self.topLogo.setMaximumSize(QSize(42, 42))
        self.topLogo.setFrameShape(QFrame.NoFrame)
        self.topLogo.setFrameShadow(QFrame.Raised)
        self.titleLeftApp = QLabel(self.topLogoInfo)
        self.titleLeftApp.setObjectName(u"titleLeftApp")
        self.titleLeftApp.setGeometry(QRect(70, 8, 160, 20))
        font1 = QFont()
        font1.setFamilies([u"Segoe UI Semibold"])
        font1.setPointSize(12)
        font1.setBold(False)
        font1.setItalic(False)
        self.titleLeftApp.setFont(font1)
        self.titleLeftDescription = QLabel(self.topLogoInfo)
        self.titleLeftDescription.setObjectName(u"titleLeftDescription")
        self.titleLeftDescription.setGeometry(QRect(70, 27, 160, 16))
        self.titleLeftDescription.setMaximumSize(QSize(16777215, 16))
        font2 = QFont()
        font2.setFamilies([u"Segoe UI"])
        font2.setPointSize(8)
        font2.setBold(False)
        font2.setItalic(False)
        self.titleLeftDescription.setFont(font2)

        self.verticalLayout_3.addWidget(self.topLogoInfo)

        self.leftMenuFrame = QFrame(self.leftMenuBg)
        self.leftMenuFrame.setObjectName(u"leftMenuFrame")
        self.leftMenuFrame.setFrameShape(QFrame.NoFrame)
        self.leftMenuFrame.setFrameShadow(QFrame.Raised)
        self.verticalMenuLayout = QVBoxLayout(self.leftMenuFrame)
        self.verticalMenuLayout.setSpacing(0)
        self.verticalMenuLayout.setObjectName(u"verticalMenuLayout")
        self.verticalMenuLayout.setContentsMargins(0, 0, 0, 0)
        self.toggleBox = QFrame(self.leftMenuFrame)
        self.toggleBox.setObjectName(u"toggleBox")
        self.toggleBox.setMaximumSize(QSize(16777215, 45))
        self.toggleBox.setFrameShape(QFrame.NoFrame)
        self.toggleBox.setFrameShadow(QFrame.Raised)
        self.verticalLayout_4 = QVBoxLayout(self.toggleBox)
        self.verticalLayout_4.setSpacing(0)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.verticalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.toggleButton = QPushButton(self.toggleBox)
        self.toggleButton.setObjectName(u"toggleButton")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.toggleButton.sizePolicy().hasHeightForWidth())
        self.toggleButton.setSizePolicy(sizePolicy)
        self.toggleButton.setMinimumSize(QSize(0, 45))
        self.toggleButton.setFont(font)
        self.toggleButton.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggleButton.setLayoutDirection(Qt.LeftToRight)
        self.toggleButton.setStyleSheet(u"background-image: url(:/icons/images/icons/icon_menu.png);")

        self.verticalLayout_4.addWidget(self.toggleButton)


        self.verticalMenuLayout.addWidget(self.toggleBox)

        self.topMenu = QFrame(self.leftMenuFrame)
        self.topMenu.setObjectName(u"topMenu")
        self.topMenu.setFrameShape(QFrame.NoFrame)
        self.topMenu.setFrameShadow(QFrame.Raised)
        self.verticalLayout_8 = QVBoxLayout(self.topMenu)
        self.verticalLayout_8.setSpacing(0)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.verticalLayout_8.setContentsMargins(0, 0, 0, 0)
        self.btn_home = QPushButton(self.topMenu)
        self.btn_home.setObjectName(u"btn_home")
        sizePolicy.setHeightForWidth(self.btn_home.sizePolicy().hasHeightForWidth())
        self.btn_home.setSizePolicy(sizePolicy)
        self.btn_home.setMinimumSize(QSize(0, 45))
        self.btn_home.setFont(font)
        self.btn_home.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_home.setLayoutDirection(Qt.LeftToRight)
        self.btn_home.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-home.png);")

        self.verticalLayout_8.addWidget(self.btn_home)

        self.btn_sensor = QPushButton(self.topMenu)
        self.btn_sensor.setObjectName(u"btn_sensor")
        sizePolicy.setHeightForWidth(self.btn_sensor.sizePolicy().hasHeightForWidth())
        self.btn_sensor.setSizePolicy(sizePolicy)
        self.btn_sensor.setMinimumSize(QSize(0, 45))
        self.btn_sensor.setFont(font)
        self.btn_sensor.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_sensor.setLayoutDirection(Qt.LeftToRight)
        self.btn_sensor.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-microphone.png);")

        self.verticalLayout_8.addWidget(self.btn_sensor)

        self.btn_ml = QPushButton(self.topMenu)
        self.btn_ml.setObjectName(u"btn_ml")
        sizePolicy.setHeightForWidth(self.btn_ml.sizePolicy().hasHeightForWidth())
        self.btn_ml.setSizePolicy(sizePolicy)
        self.btn_ml.setMinimumSize(QSize(0, 45))
        self.btn_ml.setFont(font)
        self.btn_ml.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ml.setLayoutDirection(Qt.LeftToRight)
        self.btn_ml.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-chart-line.png);")

        self.verticalLayout_8.addWidget(self.btn_ml)

        self.btn_widgets = QPushButton(self.topMenu)
        self.btn_widgets.setObjectName(u"btn_widgets")
        sizePolicy.setHeightForWidth(self.btn_widgets.sizePolicy().hasHeightForWidth())
        self.btn_widgets.setSizePolicy(sizePolicy)
        self.btn_widgets.setMinimumSize(QSize(0, 45))
        self.btn_widgets.setFont(font)
        self.btn_widgets.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_widgets.setLayoutDirection(Qt.LeftToRight)
        self.btn_widgets.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-gamepad.png);")

        self.verticalLayout_8.addWidget(self.btn_widgets)

        self.btn_new = QPushButton(self.topMenu)
        self.btn_new.setObjectName(u"btn_new")
        sizePolicy.setHeightForWidth(self.btn_new.sizePolicy().hasHeightForWidth())
        self.btn_new.setSizePolicy(sizePolicy)
        self.btn_new.setMinimumSize(QSize(0, 45))
        self.btn_new.setFont(font)
        self.btn_new.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_new.setLayoutDirection(Qt.LeftToRight)
        self.btn_new.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-file.png);")

        self.verticalLayout_8.addWidget(self.btn_new)

        self.btn_save = QPushButton(self.topMenu)
        self.btn_save.setObjectName(u"btn_save")
        sizePolicy.setHeightForWidth(self.btn_save.sizePolicy().hasHeightForWidth())
        self.btn_save.setSizePolicy(sizePolicy)
        self.btn_save.setMinimumSize(QSize(0, 45))
        self.btn_save.setFont(font)
        self.btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_save.setLayoutDirection(Qt.LeftToRight)
        self.btn_save.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-save.png)")

        self.verticalLayout_8.addWidget(self.btn_save)

        self.btn_exit = QPushButton(self.topMenu)
        self.btn_exit.setObjectName(u"btn_exit")
        sizePolicy.setHeightForWidth(self.btn_exit.sizePolicy().hasHeightForWidth())
        self.btn_exit.setSizePolicy(sizePolicy)
        self.btn_exit.setMinimumSize(QSize(0, 45))
        self.btn_exit.setFont(font)
        self.btn_exit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_exit.setLayoutDirection(Qt.LeftToRight)
        self.btn_exit.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-x.png);")

        self.verticalLayout_8.addWidget(self.btn_exit)


        self.verticalMenuLayout.addWidget(self.topMenu, 0, Qt.AlignTop)


        self.verticalLayout_3.addWidget(self.leftMenuFrame)


        self.appLayout.addWidget(self.leftMenuBg)

        self.extraLeftBox = QFrame(self.bgApp)
        self.extraLeftBox.setObjectName(u"extraLeftBox")
        self.extraLeftBox.setMinimumSize(QSize(0, 0))
        self.extraLeftBox.setMaximumSize(QSize(0, 16777215))
        self.extraLeftBox.setFrameShape(QFrame.NoFrame)
        self.extraLeftBox.setFrameShadow(QFrame.Raised)
        self.extraColumLayout = QVBoxLayout(self.extraLeftBox)
        self.extraColumLayout.setSpacing(0)
        self.extraColumLayout.setObjectName(u"extraColumLayout")
        self.extraColumLayout.setContentsMargins(0, 0, 0, 0)
        self.extraTopBg = QFrame(self.extraLeftBox)
        self.extraTopBg.setObjectName(u"extraTopBg")
        self.extraTopBg.setMinimumSize(QSize(0, 50))
        self.extraTopBg.setMaximumSize(QSize(16777215, 50))
        self.extraTopBg.setFrameShape(QFrame.NoFrame)
        self.extraTopBg.setFrameShadow(QFrame.Raised)
        self.verticalLayout_5 = QVBoxLayout(self.extraTopBg)
        self.verticalLayout_5.setSpacing(0)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.extraTopLayout = QGridLayout()
        self.extraTopLayout.setObjectName(u"extraTopLayout")
        self.extraTopLayout.setHorizontalSpacing(10)
        self.extraTopLayout.setVerticalSpacing(0)
        self.extraTopLayout.setContentsMargins(10, -1, 10, -1)
        self.extraIcon = QFrame(self.extraTopBg)
        self.extraIcon.setObjectName(u"extraIcon")
        self.extraIcon.setMinimumSize(QSize(20, 0))
        self.extraIcon.setMaximumSize(QSize(20, 20))
        self.extraIcon.setFrameShape(QFrame.NoFrame)
        self.extraIcon.setFrameShadow(QFrame.Raised)

        self.extraTopLayout.addWidget(self.extraIcon, 0, 0, 1, 1)

        self.extraLabel = QLabel(self.extraTopBg)
        self.extraLabel.setObjectName(u"extraLabel")
        self.extraLabel.setMinimumSize(QSize(150, 0))

        self.extraTopLayout.addWidget(self.extraLabel, 0, 1, 1, 1)

        self.extraCloseColumnBtn = QPushButton(self.extraTopBg)
        self.extraCloseColumnBtn.setObjectName(u"extraCloseColumnBtn")
        self.extraCloseColumnBtn.setMinimumSize(QSize(28, 28))
        self.extraCloseColumnBtn.setMaximumSize(QSize(28, 28))
        self.extraCloseColumnBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        icon = QIcon()
        icon.addFile(u":/icons/images/icons/icon_close.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.extraCloseColumnBtn.setIcon(icon)
        self.extraCloseColumnBtn.setIconSize(QSize(20, 20))

        self.extraTopLayout.addWidget(self.extraCloseColumnBtn, 0, 2, 1, 1)


        self.verticalLayout_5.addLayout(self.extraTopLayout)


        self.extraColumLayout.addWidget(self.extraTopBg)

        self.extraContent = QFrame(self.extraLeftBox)
        self.extraContent.setObjectName(u"extraContent")
        self.extraContent.setFrameShape(QFrame.NoFrame)
        self.extraContent.setFrameShadow(QFrame.Raised)
        self.verticalLayout_12 = QVBoxLayout(self.extraContent)
        self.verticalLayout_12.setSpacing(0)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.verticalLayout_12.setContentsMargins(0, 0, 0, 0)
        self.extraTopMenu = QFrame(self.extraContent)
        self.extraTopMenu.setObjectName(u"extraTopMenu")
        self.extraTopMenu.setFrameShape(QFrame.NoFrame)
        self.extraTopMenu.setFrameShadow(QFrame.Raised)
        self.verticalLayout_11 = QVBoxLayout(self.extraTopMenu)
        self.verticalLayout_11.setSpacing(0)
        self.verticalLayout_11.setObjectName(u"verticalLayout_11")
        self.verticalLayout_11.setContentsMargins(0, 0, 0, 0)
        self.btn_prepare = QPushButton(self.extraTopMenu)
        self.btn_prepare.setObjectName(u"btn_prepare")
        sizePolicy.setHeightForWidth(self.btn_prepare.sizePolicy().hasHeightForWidth())
        self.btn_prepare.setSizePolicy(sizePolicy)
        self.btn_prepare.setMinimumSize(QSize(0, 45))
        self.btn_prepare.setFont(font)
        self.btn_prepare.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_prepare.setLayoutDirection(Qt.LeftToRight)
        self.btn_prepare.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-folder-open.png);")

        self.verticalLayout_11.addWidget(self.btn_prepare)

        self.btn_process = QPushButton(self.extraTopMenu)
        self.btn_process.setObjectName(u"btn_process")
        sizePolicy.setHeightForWidth(self.btn_process.sizePolicy().hasHeightForWidth())
        self.btn_process.setSizePolicy(sizePolicy)
        self.btn_process.setMinimumSize(QSize(0, 45))
        self.btn_process.setFont(font)
        self.btn_process.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_process.setLayoutDirection(Qt.LeftToRight)
        self.btn_process.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-loop-circular.png);")

        self.verticalLayout_11.addWidget(self.btn_process)

        self.btn_validate = QPushButton(self.extraTopMenu)
        self.btn_validate.setObjectName(u"btn_validate")
        sizePolicy.setHeightForWidth(self.btn_validate.sizePolicy().hasHeightForWidth())
        self.btn_validate.setSizePolicy(sizePolicy)
        self.btn_validate.setMinimumSize(QSize(0, 45))
        self.btn_validate.setFont(font)
        self.btn_validate.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_validate.setLayoutDirection(Qt.LeftToRight)
        self.btn_validate.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-check-alt.png);")

        self.verticalLayout_11.addWidget(self.btn_validate)

        self.btn_dataset = QPushButton(self.extraTopMenu)
        self.btn_dataset.setObjectName(u"btn_dataset")
        sizePolicy.setHeightForWidth(self.btn_dataset.sizePolicy().hasHeightForWidth())
        self.btn_dataset.setSizePolicy(sizePolicy)
        self.btn_dataset.setMinimumSize(QSize(0, 45))
        self.btn_dataset.setFont(font)
        self.btn_dataset.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_dataset.setLayoutDirection(Qt.LeftToRight)
        self.btn_dataset.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-library-add.png);")

        self.verticalLayout_11.addWidget(self.btn_dataset)

        self.btn_ml_training = QPushButton(self.extraTopMenu)
        self.btn_ml_training.setObjectName(u"btn_ml_training")
        sizePolicy.setHeightForWidth(self.btn_ml_training.sizePolicy().hasHeightForWidth())
        self.btn_ml_training.setSizePolicy(sizePolicy)
        self.btn_ml_training.setMinimumSize(QSize(0, 45))
        self.btn_ml_training.setFont(font)
        self.btn_ml_training.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ml_training.setLayoutDirection(Qt.LeftToRight)
        self.btn_ml_training.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-equalizer.png);")

        self.verticalLayout_11.addWidget(self.btn_ml_training)

        self.btn_ml_performance = QPushButton(self.extraTopMenu)
        self.btn_ml_performance.setObjectName(u"btn_ml_performance")
        sizePolicy.setHeightForWidth(self.btn_ml_performance.sizePolicy().hasHeightForWidth())
        self.btn_ml_performance.setSizePolicy(sizePolicy)
        self.btn_ml_performance.setMinimumSize(QSize(0, 45))
        self.btn_ml_performance.setFont(font)
        self.btn_ml_performance.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ml_performance.setLayoutDirection(Qt.LeftToRight)
        self.btn_ml_performance.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-speedometer.png);")

        self.verticalLayout_11.addWidget(self.btn_ml_performance)

        self.btn_ml_prediction = QPushButton(self.extraTopMenu)
        self.btn_ml_prediction.setObjectName(u"btn_ml_prediction")
        sizePolicy.setHeightForWidth(self.btn_ml_prediction.sizePolicy().hasHeightForWidth())
        self.btn_ml_prediction.setSizePolicy(sizePolicy)
        self.btn_ml_prediction.setMinimumSize(QSize(0, 45))
        self.btn_ml_prediction.setFont(font)
        self.btn_ml_prediction.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ml_prediction.setLayoutDirection(Qt.LeftToRight)
        self.btn_ml_prediction.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-lightbulb.png);")

        self.verticalLayout_11.addWidget(self.btn_ml_prediction)


        self.verticalLayout_12.addWidget(self.extraTopMenu, 0, Qt.AlignTop)

        self.extraCenter = QFrame(self.extraContent)
        self.extraCenter.setObjectName(u"extraCenter")
        self.extraCenter.setFrameShape(QFrame.NoFrame)
        self.extraCenter.setFrameShadow(QFrame.Raised)
        self.verticalLayout_10 = QVBoxLayout(self.extraCenter)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")

        self.verticalLayout_12.addWidget(self.extraCenter)

        self.extraBottom = QFrame(self.extraContent)
        self.extraBottom.setObjectName(u"extraBottom")
        self.extraBottom.setFrameShape(QFrame.NoFrame)
        self.extraBottom.setFrameShadow(QFrame.Raised)

        self.verticalLayout_12.addWidget(self.extraBottom)


        self.extraColumLayout.addWidget(self.extraContent)


        self.appLayout.addWidget(self.extraLeftBox)

        self.contentBox = QFrame(self.bgApp)
        self.contentBox.setObjectName(u"contentBox")
        self.contentBox.setFrameShape(QFrame.NoFrame)
        self.contentBox.setFrameShadow(QFrame.Raised)
        self.verticalLayout_2 = QVBoxLayout(self.contentBox)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.contentTopBg = QFrame(self.contentBox)
        self.contentTopBg.setObjectName(u"contentTopBg")
        self.contentTopBg.setMinimumSize(QSize(0, 50))
        self.contentTopBg.setMaximumSize(QSize(16777215, 50))
        self.contentTopBg.setFrameShape(QFrame.NoFrame)
        self.contentTopBg.setFrameShadow(QFrame.Raised)
        self.horizontalLayout = QHBoxLayout(self.contentTopBg)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 10, 0)
        self.leftBox = QFrame(self.contentTopBg)
        self.leftBox.setObjectName(u"leftBox")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.leftBox.sizePolicy().hasHeightForWidth())
        self.leftBox.setSizePolicy(sizePolicy1)
        self.leftBox.setFrameShape(QFrame.NoFrame)
        self.leftBox.setFrameShadow(QFrame.Raised)
        self.horizontalLayout_3 = QHBoxLayout(self.leftBox)
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.titleRightInfo = QLabel(self.leftBox)
        self.titleRightInfo.setObjectName(u"titleRightInfo")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.titleRightInfo.sizePolicy().hasHeightForWidth())
        self.titleRightInfo.setSizePolicy(sizePolicy2)
        self.titleRightInfo.setMaximumSize(QSize(16777215, 45))
        self.titleRightInfo.setFont(font)

        self.horizontalLayout_3.addWidget(self.titleRightInfo)


        self.horizontalLayout.addWidget(self.leftBox)

        self.rightButtons = QFrame(self.contentTopBg)
        self.rightButtons.setObjectName(u"rightButtons")
        self.rightButtons.setMinimumSize(QSize(0, 28))
        self.rightButtons.setFrameShape(QFrame.NoFrame)
        self.rightButtons.setFrameShadow(QFrame.Raised)
        self.horizontalLayout_2 = QHBoxLayout(self.rightButtons)
        self.horizontalLayout_2.setSpacing(5)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.settingsTopBtn = QPushButton(self.rightButtons)
        self.settingsTopBtn.setObjectName(u"settingsTopBtn")
        self.settingsTopBtn.setMinimumSize(QSize(28, 28))
        self.settingsTopBtn.setMaximumSize(QSize(28, 28))
        self.settingsTopBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        icon1 = QIcon()
        icon1.addFile(u":/icons/images/icons/icon_settings.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.settingsTopBtn.setIcon(icon1)
        self.settingsTopBtn.setIconSize(QSize(20, 20))

        self.horizontalLayout_2.addWidget(self.settingsTopBtn)

        self.minimizeAppBtn = QPushButton(self.rightButtons)
        self.minimizeAppBtn.setObjectName(u"minimizeAppBtn")
        self.minimizeAppBtn.setMinimumSize(QSize(28, 28))
        self.minimizeAppBtn.setMaximumSize(QSize(28, 28))
        self.minimizeAppBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        icon2 = QIcon()
        icon2.addFile(u":/icons/images/icons/icon_minimize.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.minimizeAppBtn.setIcon(icon2)
        self.minimizeAppBtn.setIconSize(QSize(20, 20))

        self.horizontalLayout_2.addWidget(self.minimizeAppBtn)

        self.maximizeRestoreAppBtn = QPushButton(self.rightButtons)
        self.maximizeRestoreAppBtn.setObjectName(u"maximizeRestoreAppBtn")
        self.maximizeRestoreAppBtn.setMinimumSize(QSize(28, 28))
        self.maximizeRestoreAppBtn.setMaximumSize(QSize(28, 28))
        font3 = QFont()
        font3.setFamilies([u"Segoe UI"])
        font3.setPointSize(10)
        font3.setBold(False)
        font3.setItalic(False)
        font3.setStyleStrategy(QFont.PreferDefault)
        self.maximizeRestoreAppBtn.setFont(font3)
        self.maximizeRestoreAppBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        icon3 = QIcon()
        icon3.addFile(u":/icons/images/icons/icon_maximize.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.maximizeRestoreAppBtn.setIcon(icon3)
        self.maximizeRestoreAppBtn.setIconSize(QSize(20, 20))

        self.horizontalLayout_2.addWidget(self.maximizeRestoreAppBtn)

        self.closeAppBtn = QPushButton(self.rightButtons)
        self.closeAppBtn.setObjectName(u"closeAppBtn")
        self.closeAppBtn.setMinimumSize(QSize(28, 28))
        self.closeAppBtn.setMaximumSize(QSize(28, 28))
        self.closeAppBtn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.closeAppBtn.setIcon(icon)
        self.closeAppBtn.setIconSize(QSize(20, 20))

        self.horizontalLayout_2.addWidget(self.closeAppBtn)


        self.horizontalLayout.addWidget(self.rightButtons, 0, Qt.AlignRight)


        self.verticalLayout_2.addWidget(self.contentTopBg)

        self.contentBottom = QFrame(self.contentBox)
        self.contentBottom.setObjectName(u"contentBottom")
        self.contentBottom.setFrameShape(QFrame.NoFrame)
        self.contentBottom.setFrameShadow(QFrame.Raised)
        self.verticalLayout_6 = QVBoxLayout(self.contentBottom)
        self.verticalLayout_6.setSpacing(0)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.verticalLayout_6.setContentsMargins(0, 0, 0, 0)
        self.content = QFrame(self.contentBottom)
        self.content.setObjectName(u"content")
        self.content.setFrameShape(QFrame.NoFrame)
        self.content.setFrameShadow(QFrame.Raised)
        self.horizontalLayout_4 = QHBoxLayout(self.content)
        self.horizontalLayout_4.setSpacing(0)
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.horizontalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.pagesContainer = QFrame(self.content)
        self.pagesContainer.setObjectName(u"pagesContainer")
        self.pagesContainer.setStyleSheet(u"")
        self.pagesContainer.setFrameShape(QFrame.NoFrame)
        self.pagesContainer.setFrameShadow(QFrame.Raised)
        self.verticalLayout_15 = QVBoxLayout(self.pagesContainer)
        self.verticalLayout_15.setSpacing(0)
        self.verticalLayout_15.setObjectName(u"verticalLayout_15")
        self.verticalLayout_15.setContentsMargins(10, 10, 10, 10)
        self.stackedWidget = QStackedWidget(self.pagesContainer)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.stackedWidget.setStyleSheet(u"background: transparent;")
        self.home = QWidget()
        self.home.setObjectName(u"home")
        self.home.setStyleSheet(u"background-image: url(:/images/images/images/PyDracula_vertical.png);\n"
"background-position: center;\n"
"background-repeat: no-repeat;")
        self.stackedWidget.addWidget(self.home)
        self.widgets = QWidget()
        self.widgets.setObjectName(u"widgets")
        self.widgets.setStyleSheet(u"b")
        self.verticalLayout = QVBoxLayout(self.widgets)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(10, 10, 10, 10)
        self.row_1 = QFrame(self.widgets)
        self.row_1.setObjectName(u"row_1")
        self.row_1.setFrameShape(QFrame.StyledPanel)
        self.row_1.setFrameShadow(QFrame.Raised)
        self.verticalLayout_16 = QVBoxLayout(self.row_1)
        self.verticalLayout_16.setSpacing(0)
        self.verticalLayout_16.setObjectName(u"verticalLayout_16")
        self.verticalLayout_16.setContentsMargins(0, 0, 0, 0)
        self.frame_div_content_1 = QFrame(self.row_1)
        self.frame_div_content_1.setObjectName(u"frame_div_content_1")
        self.frame_div_content_1.setMinimumSize(QSize(0, 110))
        self.frame_div_content_1.setMaximumSize(QSize(16777215, 110))
        self.frame_div_content_1.setFrameShape(QFrame.NoFrame)
        self.frame_div_content_1.setFrameShadow(QFrame.Raised)
        self.verticalLayout_17 = QVBoxLayout(self.frame_div_content_1)
        self.verticalLayout_17.setSpacing(0)
        self.verticalLayout_17.setObjectName(u"verticalLayout_17")
        self.verticalLayout_17.setContentsMargins(0, 0, 0, 0)
        self.frame_title_wid_1 = QFrame(self.frame_div_content_1)
        self.frame_title_wid_1.setObjectName(u"frame_title_wid_1")
        self.frame_title_wid_1.setMaximumSize(QSize(16777215, 35))
        self.frame_title_wid_1.setFrameShape(QFrame.StyledPanel)
        self.frame_title_wid_1.setFrameShadow(QFrame.Raised)
        self.verticalLayout_18 = QVBoxLayout(self.frame_title_wid_1)
        self.verticalLayout_18.setObjectName(u"verticalLayout_18")
        self.labelBoxBlenderInstalation = QLabel(self.frame_title_wid_1)
        self.labelBoxBlenderInstalation.setObjectName(u"labelBoxBlenderInstalation")
        self.labelBoxBlenderInstalation.setFont(font)
        self.labelBoxBlenderInstalation.setStyleSheet(u"")

        self.verticalLayout_18.addWidget(self.labelBoxBlenderInstalation)


        self.verticalLayout_17.addWidget(self.frame_title_wid_1)

        self.frame_content_wid_1 = QFrame(self.frame_div_content_1)
        self.frame_content_wid_1.setObjectName(u"frame_content_wid_1")
        self.frame_content_wid_1.setFrameShape(QFrame.NoFrame)
        self.frame_content_wid_1.setFrameShadow(QFrame.Raised)
        self.horizontalLayout_9 = QHBoxLayout(self.frame_content_wid_1)
        self.horizontalLayout_9.setObjectName(u"horizontalLayout_9")
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(-1, -1, -1, 0)
        self.lineEdit = QLineEdit(self.frame_content_wid_1)
        self.lineEdit.setObjectName(u"lineEdit")
        self.lineEdit.setMinimumSize(QSize(0, 30))
        self.lineEdit.setStyleSheet(u"background-color: rgb(33, 37, 43);")

        self.gridLayout.addWidget(self.lineEdit, 0, 0, 1, 1)

        self.pushButton = QPushButton(self.frame_content_wid_1)
        self.pushButton.setObjectName(u"pushButton")
        self.pushButton.setMinimumSize(QSize(150, 30))
        self.pushButton.setFont(font)
        self.pushButton.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.pushButton.setStyleSheet(u"background-color: rgb(52, 59, 72);")
        icon4 = QIcon()
        icon4.addFile(u":/icons/images/icons/cil-folder-open.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.pushButton.setIcon(icon4)

        self.gridLayout.addWidget(self.pushButton, 0, 1, 1, 1)

        self.labelVersion_3 = QLabel(self.frame_content_wid_1)
        self.labelVersion_3.setObjectName(u"labelVersion_3")
        self.labelVersion_3.setStyleSheet(u"color: rgb(113, 126, 149);")
        self.labelVersion_3.setLineWidth(1)

        self.gridLayout.addWidget(self.labelVersion_3, 1, 0, 1, 2)


        self.horizontalLayout_9.addLayout(self.gridLayout)


        self.verticalLayout_17.addWidget(self.frame_content_wid_1)


        self.verticalLayout_16.addWidget(self.frame_div_content_1)


        self.verticalLayout.addWidget(self.row_1)

        self.row_2 = QFrame(self.widgets)
        self.row_2.setObjectName(u"row_2")
        self.row_2.setMinimumSize(QSize(0, 150))
        self.row_2.setFrameShape(QFrame.StyledPanel)
        self.row_2.setFrameShadow(QFrame.Raised)
        self.verticalLayout_19 = QVBoxLayout(self.row_2)
        self.verticalLayout_19.setObjectName(u"verticalLayout_19")
        self.gridLayout_2 = QGridLayout()
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.checkBox = QCheckBox(self.row_2)
        self.checkBox.setObjectName(u"checkBox")
        self.checkBox.setAutoFillBackground(False)
        self.checkBox.setStyleSheet(u"")

        self.gridLayout_2.addWidget(self.checkBox, 0, 0, 1, 1)

        self.radioButton = QRadioButton(self.row_2)
        self.radioButton.setObjectName(u"radioButton")
        self.radioButton.setStyleSheet(u"")

        self.gridLayout_2.addWidget(self.radioButton, 0, 1, 1, 1)

        self.verticalSlider = QSlider(self.row_2)
        self.verticalSlider.setObjectName(u"verticalSlider")
        self.verticalSlider.setStyleSheet(u"")
        self.verticalSlider.setOrientation(Qt.Vertical)

        self.gridLayout_2.addWidget(self.verticalSlider, 0, 2, 3, 1)

        self.verticalScrollBar = QScrollBar(self.row_2)
        self.verticalScrollBar.setObjectName(u"verticalScrollBar")
        self.verticalScrollBar.setStyleSheet(u" QScrollBar:vertical { background: rgb(52, 59, 72); }\n"
" QScrollBar:horizontal { background: rgb(52, 59, 72); }")
        self.verticalScrollBar.setOrientation(Qt.Vertical)

        self.gridLayout_2.addWidget(self.verticalScrollBar, 0, 4, 3, 1)

        self.scrollArea = QScrollArea(self.row_2)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setStyleSheet(u" QScrollBar:vertical {\n"
"    background: rgb(52, 59, 72);\n"
" }\n"
" QScrollBar:horizontal {\n"
"    background: rgb(52, 59, 72);\n"
" }")
        self.scrollArea.setFrameShape(QFrame.NoFrame)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 315, 218))
        self.scrollAreaWidgetContents.setStyleSheet(u" QScrollBar:vertical {\n"
"	border: none;\n"
"    background: rgb(52, 59, 72);\n"
"    width: 14px;\n"
"    margin: 21px 0 21px 0;\n"
"	border-radius: 0px;\n"
" }")
        self.horizontalLayout_11 = QHBoxLayout(self.scrollAreaWidgetContents)
        self.horizontalLayout_11.setObjectName(u"horizontalLayout_11")
        self.plainTextEdit = QPlainTextEdit(self.scrollAreaWidgetContents)
        self.plainTextEdit.setObjectName(u"plainTextEdit")
        self.plainTextEdit.setMinimumSize(QSize(200, 200))
        self.plainTextEdit.setStyleSheet(u"background-color: rgb(33, 37, 43);")

        self.horizontalLayout_11.addWidget(self.plainTextEdit)

        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.gridLayout_2.addWidget(self.scrollArea, 0, 5, 3, 1)

        self.comboBox = QComboBox(self.row_2)
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.setObjectName(u"comboBox")
        self.comboBox.setFont(font)
        self.comboBox.setAutoFillBackground(False)
        self.comboBox.setStyleSheet(u"background-color: rgb(33, 37, 43);")
        self.comboBox.setIconSize(QSize(16, 16))
        self.comboBox.setFrame(True)

        self.gridLayout_2.addWidget(self.comboBox, 1, 0, 1, 2)

        self.horizontalScrollBar = QScrollBar(self.row_2)
        self.horizontalScrollBar.setObjectName(u"horizontalScrollBar")
        sizePolicy.setHeightForWidth(self.horizontalScrollBar.sizePolicy().hasHeightForWidth())
        self.horizontalScrollBar.setSizePolicy(sizePolicy)
        self.horizontalScrollBar.setStyleSheet(u" QScrollBar:vertical { background: rgb(52, 59, 72); }\n"
" QScrollBar:horizontal { background: rgb(52, 59, 72); }")
        self.horizontalScrollBar.setOrientation(Qt.Horizontal)

        self.gridLayout_2.addWidget(self.horizontalScrollBar, 1, 3, 1, 1)

        self.commandLinkButton = QCommandLinkButton(self.row_2)
        self.commandLinkButton.setObjectName(u"commandLinkButton")
        self.commandLinkButton.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.commandLinkButton.setStyleSheet(u"")
        icon5 = QIcon()
        icon5.addFile(u":/icons/images/icons/cil-link.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.commandLinkButton.setIcon(icon5)

        self.gridLayout_2.addWidget(self.commandLinkButton, 1, 6, 1, 1)

        self.horizontalSlider = QSlider(self.row_2)
        self.horizontalSlider.setObjectName(u"horizontalSlider")
        self.horizontalSlider.setStyleSheet(u"")
        self.horizontalSlider.setOrientation(Qt.Horizontal)

        self.gridLayout_2.addWidget(self.horizontalSlider, 2, 0, 1, 2)


        self.verticalLayout_19.addLayout(self.gridLayout_2)


        self.verticalLayout.addWidget(self.row_2)

        self.row_3 = QFrame(self.widgets)
        self.row_3.setObjectName(u"row_3")
        self.row_3.setMinimumSize(QSize(0, 150))
        self.row_3.setFrameShape(QFrame.StyledPanel)
        self.row_3.setFrameShadow(QFrame.Raised)
        self.horizontalLayout_12 = QHBoxLayout(self.row_3)
        self.horizontalLayout_12.setSpacing(0)
        self.horizontalLayout_12.setObjectName(u"horizontalLayout_12")
        self.horizontalLayout_12.setContentsMargins(0, 0, 0, 0)
        self.tableWidget = QTableWidget(self.row_3)
        if (self.tableWidget.columnCount() < 4):
            self.tableWidget.setColumnCount(4)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidget.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        if (self.tableWidget.rowCount() < 16):
            self.tableWidget.setRowCount(16)
        font4 = QFont()
        font4.setFamilies([u"Segoe UI"])
        __qtablewidgetitem4 = QTableWidgetItem()
        __qtablewidgetitem4.setFont(font4)
        self.tableWidget.setVerticalHeaderItem(0, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(1, __qtablewidgetitem5)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(2, __qtablewidgetitem6)
        __qtablewidgetitem7 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(3, __qtablewidgetitem7)
        __qtablewidgetitem8 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(4, __qtablewidgetitem8)
        __qtablewidgetitem9 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(5, __qtablewidgetitem9)
        __qtablewidgetitem10 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(6, __qtablewidgetitem10)
        __qtablewidgetitem11 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(7, __qtablewidgetitem11)
        __qtablewidgetitem12 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(8, __qtablewidgetitem12)
        __qtablewidgetitem13 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(9, __qtablewidgetitem13)
        __qtablewidgetitem14 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(10, __qtablewidgetitem14)
        __qtablewidgetitem15 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(11, __qtablewidgetitem15)
        __qtablewidgetitem16 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(12, __qtablewidgetitem16)
        __qtablewidgetitem17 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(13, __qtablewidgetitem17)
        __qtablewidgetitem18 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(14, __qtablewidgetitem18)
        __qtablewidgetitem19 = QTableWidgetItem()
        self.tableWidget.setVerticalHeaderItem(15, __qtablewidgetitem19)
        __qtablewidgetitem20 = QTableWidgetItem()
        self.tableWidget.setItem(0, 0, __qtablewidgetitem20)
        __qtablewidgetitem21 = QTableWidgetItem()
        self.tableWidget.setItem(0, 1, __qtablewidgetitem21)
        __qtablewidgetitem22 = QTableWidgetItem()
        self.tableWidget.setItem(0, 2, __qtablewidgetitem22)
        __qtablewidgetitem23 = QTableWidgetItem()
        self.tableWidget.setItem(0, 3, __qtablewidgetitem23)
        self.tableWidget.setObjectName(u"tableWidget")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.tableWidget.sizePolicy().hasHeightForWidth())
        self.tableWidget.setSizePolicy(sizePolicy3)
        palette = QPalette()
        brush = QBrush(QColor(221, 221, 221, 255))
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, brush)
        brush1 = QBrush(QColor(0, 0, 0, 0))
        brush1.setStyle(Qt.BrushStyle.SolidPattern)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Button, brush1)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, brush)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, brush)
        brush2 = QBrush(QColor(0, 0, 0, 255))
        brush2.setStyle(Qt.BrushStyle.NoBrush)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Base, brush2)
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, brush1)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, brush)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, brush1)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, brush)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, brush)
        brush3 = QBrush(QColor(0, 0, 0, 255))
        brush3.setStyle(Qt.BrushStyle.NoBrush)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, brush3)
        palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, brush1)
        palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, brush)
        palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, brush1)
        palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, brush)
        palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, brush)
        brush4 = QBrush(QColor(0, 0, 0, 255))
        brush4.setStyle(Qt.BrushStyle.NoBrush)
        palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, brush4)
        palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, brush1)
        self.tableWidget.setPalette(palette)
        self.tableWidget.setFrameShape(QFrame.NoFrame)
        self.tableWidget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.tableWidget.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableWidget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableWidget.setShowGrid(True)
        self.tableWidget.setGridStyle(Qt.SolidLine)
        self.tableWidget.setSortingEnabled(False)
        self.tableWidget.horizontalHeader().setVisible(False)
        self.tableWidget.horizontalHeader().setCascadingSectionResizes(True)
        self.tableWidget.horizontalHeader().setDefaultSectionSize(200)
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.verticalHeader().setCascadingSectionResizes(False)
        self.tableWidget.verticalHeader().setHighlightSections(False)
        self.tableWidget.verticalHeader().setStretchLastSection(True)

        self.horizontalLayout_12.addWidget(self.tableWidget)


        self.verticalLayout.addWidget(self.row_3)

        self.stackedWidget.addWidget(self.widgets)
        self.new_page = QWidget()
        self.new_page.setObjectName(u"new_page")
        self.verticalLayout_20 = QVBoxLayout(self.new_page)
        self.verticalLayout_20.setObjectName(u"verticalLayout_20")
        self.label = QLabel(self.new_page)
        self.label.setObjectName(u"label")

        self.verticalLayout_20.addWidget(self.label)

        self.stackedWidget.addWidget(self.new_page)
        self.page_prepare = QWidget()
        self.page_prepare.setObjectName(u"page_prepare")
        self.layout_prepare = QVBoxLayout(self.page_prepare)
        self.layout_prepare.setSpacing(10)
        self.layout_prepare.setObjectName(u"layout_prepare")
        self.layout_prepare.setContentsMargins(10, 10, 10, 10)
        self.title_prepare = QLabel(self.page_prepare)
        self.title_prepare.setObjectName(u"title_prepare")
        self.title_prepare.setMaximumSize(QSize(16777215, 30))
        self.title_prepare.setFont(font)

        self.layout_prepare.addWidget(self.title_prepare)

        self.subtitle_prepare = QLabel(self.page_prepare)
        self.subtitle_prepare.setObjectName(u"subtitle_prepare")
        self.subtitle_prepare.setMaximumSize(QSize(16777215, 20))
        self.subtitle_prepare.setWordWrap(True)

        self.layout_prepare.addWidget(self.subtitle_prepare)

        self.content_prepare = QFrame(self.page_prepare)
        self.content_prepare.setObjectName(u"content_prepare")
        self.content_prepare.setFrameShape(QFrame.NoFrame)
        self.content_prepare.setFrameShadow(QFrame.Raised)
        self.layout_content_prepare = QVBoxLayout(self.content_prepare)
        self.layout_content_prepare.setSpacing(0)
        self.layout_content_prepare.setObjectName(u"layout_content_prepare")
        self.layout_content_prepare.setContentsMargins(0, 0, 0, 0)
        self.tabs_prepare = QTabWidget(self.content_prepare)
        self.tabs_prepare.setObjectName(u"tabs_prepare")
        self.tab_prepare_sensor = QWidget()
        self.tab_prepare_sensor.setObjectName(u"tab_prepare_sensor")
        self.layout_tab_prepare_sensor = QVBoxLayout(self.tab_prepare_sensor)
        self.layout_tab_prepare_sensor.setSpacing(0)
        self.layout_tab_prepare_sensor.setObjectName(u"layout_tab_prepare_sensor")
        self.layout_tab_prepare_sensor.setContentsMargins(0, 0, 0, 0)
        self.frame_prepare_sensor = QFrame(self.tab_prepare_sensor)
        self.frame_prepare_sensor.setObjectName(u"frame_prepare_sensor")
        self.frame_prepare_sensor.setFrameShape(QFrame.NoFrame)
        self.frame_prepare_sensor.setFrameShadow(QFrame.Raised)

        self.layout_tab_prepare_sensor.addWidget(self.frame_prepare_sensor)

        self.tabs_prepare.addTab(self.tab_prepare_sensor, "")
        self.tab_prepare_study = QWidget()
        self.tab_prepare_study.setObjectName(u"tab_prepare_study")
        self.layout_tab_prepare_study = QVBoxLayout(self.tab_prepare_study)
        self.layout_tab_prepare_study.setSpacing(0)
        self.layout_tab_prepare_study.setObjectName(u"layout_tab_prepare_study")
        self.layout_tab_prepare_study.setContentsMargins(0, 0, 0, 0)
        self.frame_prepare_study = QFrame(self.tab_prepare_study)
        self.frame_prepare_study.setObjectName(u"frame_prepare_study")
        self.frame_prepare_study.setFrameShape(QFrame.NoFrame)
        self.frame_prepare_study.setFrameShadow(QFrame.Raised)

        self.layout_tab_prepare_study.addWidget(self.frame_prepare_study)

        self.tabs_prepare.addTab(self.tab_prepare_study, "")

        self.layout_content_prepare.addWidget(self.tabs_prepare)


        self.layout_prepare.addWidget(self.content_prepare)

        self.stackedWidget.addWidget(self.page_prepare)
        self.page_process = QWidget()
        self.page_process.setObjectName(u"page_process")
        self.layout_process = QVBoxLayout(self.page_process)
        self.layout_process.setSpacing(10)
        self.layout_process.setObjectName(u"layout_process")
        self.layout_process.setContentsMargins(10, 10, 10, 10)
        self.title_process = QLabel(self.page_process)
        self.title_process.setObjectName(u"title_process")
        self.title_process.setMaximumSize(QSize(16777215, 30))
        self.title_process.setFont(font)

        self.layout_process.addWidget(self.title_process)

        self.subtitle_process = QLabel(self.page_process)
        self.subtitle_process.setObjectName(u"subtitle_process")
        self.subtitle_process.setMaximumSize(QSize(16777215, 20))
        self.subtitle_process.setWordWrap(True)

        self.layout_process.addWidget(self.subtitle_process)

        self.content_process = QFrame(self.page_process)
        self.content_process.setObjectName(u"content_process")
        self.content_process.setFrameShape(QFrame.NoFrame)
        self.content_process.setFrameShadow(QFrame.Raised)
        self.layout_content_process = QVBoxLayout(self.content_process)
        self.layout_content_process.setSpacing(0)
        self.layout_content_process.setObjectName(u"layout_content_process")
        self.layout_content_process.setContentsMargins(0, 0, 0, 0)
        self.tabs_process = QTabWidget(self.content_process)
        self.tabs_process.setObjectName(u"tabs_process")
        self.tab_raw = QWidget()
        self.tab_raw.setObjectName(u"tab_raw")
        self.grid_raw = QGridLayout(self.tab_raw)
        self.grid_raw.setSpacing(8)
        self.grid_raw.setObjectName(u"grid_raw")
        self.grid_raw.setContentsMargins(8, 8, 8, 8)
        self.grp_library = QGroupBox(self.tab_raw)
        self.grp_library.setObjectName(u"grp_library")
        self.layout_grp_library = QVBoxLayout(self.grp_library)
        self.layout_grp_library.setSpacing(6)
        self.layout_grp_library.setObjectName(u"layout_grp_library")
        self.layout_grp_library.setContentsMargins(6, 6, 6, 6)
        self.tree_library = QTreeView(self.grp_library)
        self.tree_library.setObjectName(u"tree_library")

        self.layout_grp_library.addWidget(self.tree_library)

        self.btn_change_libraries = QPushButton(self.grp_library)
        self.btn_change_libraries.setObjectName(u"btn_change_libraries")
        self.btn_change_libraries.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_grp_library.addWidget(self.btn_change_libraries)


        self.grid_raw.addWidget(self.grp_library, 0, 0, 1, 1)

        self.grp_index = QGroupBox(self.tab_raw)
        self.grp_index.setObjectName(u"grp_index")
        self.layout_grp_index = QVBoxLayout(self.grp_index)
        self.layout_grp_index.setSpacing(6)
        self.layout_grp_index.setObjectName(u"layout_grp_index")
        self.layout_grp_index.setContentsMargins(6, 6, 6, 6)
        self.tree_index = QTreeView(self.grp_index)
        self.tree_index.setObjectName(u"tree_index")

        self.layout_grp_index.addWidget(self.tree_index)


        self.grid_raw.addWidget(self.grp_index, 1, 0, 1, 1)

        self.grp_inventory = QGroupBox(self.tab_raw)
        self.grp_inventory.setObjectName(u"grp_inventory")
        self.layout_grp_inventory = QVBoxLayout(self.grp_inventory)
        self.layout_grp_inventory.setSpacing(6)
        self.layout_grp_inventory.setObjectName(u"layout_grp_inventory")
        self.layout_grp_inventory.setContentsMargins(6, 6, 6, 6)
        self.table_inventory = QTableWidget(self.grp_inventory)
        if (self.table_inventory.columnCount() < 7):
            self.table_inventory.setColumnCount(7)
        __qtablewidgetitem24 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(0, __qtablewidgetitem24)
        __qtablewidgetitem25 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(1, __qtablewidgetitem25)
        __qtablewidgetitem26 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(2, __qtablewidgetitem26)
        __qtablewidgetitem27 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(3, __qtablewidgetitem27)
        __qtablewidgetitem28 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(4, __qtablewidgetitem28)
        __qtablewidgetitem29 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(5, __qtablewidgetitem29)
        __qtablewidgetitem30 = QTableWidgetItem()
        self.table_inventory.setHorizontalHeaderItem(6, __qtablewidgetitem30)
        self.table_inventory.setObjectName(u"table_inventory")
        self.table_inventory.setMinimumSize(QSize(0, 220))
        self.table_inventory.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_inventory.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.layout_grp_inventory.addWidget(self.table_inventory)

        self.layout_inventory_controls = QHBoxLayout()
        self.layout_inventory_controls.setObjectName(u"layout_inventory_controls")
        self.chk_select_all = QCheckBox(self.grp_inventory)
        self.chk_select_all.setObjectName(u"chk_select_all")
        self.chk_select_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_inventory_controls.addWidget(self.chk_select_all)

        self.spacer_1 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_inventory_controls.addItem(self.spacer_1)

        self.lbl_treatment = QLabel(self.grp_inventory)
        self.lbl_treatment.setObjectName(u"lbl_treatment")

        self.layout_inventory_controls.addWidget(self.lbl_treatment)

        self.cmb_treatment = QComboBox(self.grp_inventory)
        self.cmb_treatment.setObjectName(u"cmb_treatment")
        self.cmb_treatment.setMinimumSize(QSize(200, 0))

        self.layout_inventory_controls.addWidget(self.cmb_treatment)

        self.btn_process_selected = QPushButton(self.grp_inventory)
        self.btn_process_selected.setObjectName(u"btn_process_selected")
        self.btn_process_selected.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_inventory_controls.addWidget(self.btn_process_selected)


        self.layout_grp_inventory.addLayout(self.layout_inventory_controls)


        self.grid_raw.addWidget(self.grp_inventory, 0, 1, 1, 1)

        self.grp_console = QGroupBox(self.tab_raw)
        self.grp_console.setObjectName(u"grp_console")
        self.layout_grp_console = QVBoxLayout(self.grp_console)
        self.layout_grp_console.setSpacing(6)
        self.layout_grp_console.setObjectName(u"layout_grp_console")
        self.layout_grp_console.setContentsMargins(6, 6, 6, 6)
        self.console_output = QPlainTextEdit(self.grp_console)
        self.console_output.setObjectName(u"console_output")
        self.console_output.setReadOnly(True)

        self.layout_grp_console.addWidget(self.console_output)


        self.grid_raw.addWidget(self.grp_console, 1, 1, 1, 1)

        self.grp_selection_info = QGroupBox(self.tab_raw)
        self.grp_selection_info.setObjectName(u"grp_selection_info")
        self.layout_grp_selection_info = QVBoxLayout(self.grp_selection_info)
        self.layout_grp_selection_info.setSpacing(6)
        self.layout_grp_selection_info.setObjectName(u"layout_grp_selection_info")
        self.layout_grp_selection_info.setContentsMargins(6, 6, 6, 6)
        self.frame_cards = QFrame(self.grp_selection_info)
        self.frame_cards.setObjectName(u"frame_cards")
        self.frame_cards.setFrameShape(QFrame.NoFrame)

        self.layout_grp_selection_info.addWidget(self.frame_cards)


        self.grid_raw.addWidget(self.grp_selection_info, 0, 2, 1, 1)

        self.grp_processed = QGroupBox(self.tab_raw)
        self.grp_processed.setObjectName(u"grp_processed")
        self.layout_grp_processed = QVBoxLayout(self.grp_processed)
        self.layout_grp_processed.setSpacing(6)
        self.layout_grp_processed.setObjectName(u"layout_grp_processed")
        self.layout_grp_processed.setContentsMargins(6, 6, 6, 6)
        self.list_processed = QListWidget(self.grp_processed)
        self.list_processed.setObjectName(u"list_processed")

        self.layout_grp_processed.addWidget(self.list_processed)


        self.grid_raw.addWidget(self.grp_processed, 1, 2, 1, 1)

        self.grid_raw.setRowStretch(0, 1)
        self.grid_raw.setRowStretch(1, 1)
        self.grid_raw.setColumnStretch(0, 1)
        self.grid_raw.setColumnStretch(1, 2)
        self.grid_raw.setColumnStretch(2, 1)
        self.tabs_process.addTab(self.tab_raw, "")
        self.tab_meta = QWidget()
        self.tab_meta.setObjectName(u"tab_meta")
        self.grid_meta = QGridLayout(self.tab_meta)
        self.grid_meta.setSpacing(8)
        self.grid_meta.setObjectName(u"grid_meta")
        self.grid_meta.setContentsMargins(8, 8, 8, 8)
        self.grp_deployment = QGroupBox(self.tab_meta)
        self.grp_deployment.setObjectName(u"grp_deployment")
        self.layout_grp_deployment = QVBoxLayout(self.grp_deployment)
        self.layout_grp_deployment.setSpacing(6)
        self.layout_grp_deployment.setObjectName(u"layout_grp_deployment")
        self.layout_grp_deployment.setContentsMargins(6, 6, 6, 6)
        self.grid_deployment_fields = QGridLayout()
        self.grid_deployment_fields.setObjectName(u"grid_deployment_fields")
        self.lbl_ed_deployment_config_label = QLabel(self.grp_deployment)
        self.lbl_ed_deployment_config_label.setObjectName(u"lbl_ed_deployment_config_label")

        self.grid_deployment_fields.addWidget(self.lbl_ed_deployment_config_label, 0, 0, 1, 1)

        self.ed_deployment_config_label = QLineEdit(self.grp_deployment)
        self.ed_deployment_config_label.setObjectName(u"ed_deployment_config_label")

        self.grid_deployment_fields.addWidget(self.ed_deployment_config_label, 0, 1, 1, 1)

        self.lbl_ed_site = QLabel(self.grp_deployment)
        self.lbl_ed_site.setObjectName(u"lbl_ed_site")

        self.grid_deployment_fields.addWidget(self.lbl_ed_site, 1, 0, 1, 1)

        self.ed_site = QLineEdit(self.grp_deployment)
        self.ed_site.setObjectName(u"ed_site")

        self.grid_deployment_fields.addWidget(self.ed_site, 1, 1, 1, 1)

        self.lbl_ed_deployment_id = QLabel(self.grp_deployment)
        self.lbl_ed_deployment_id.setObjectName(u"lbl_ed_deployment_id")

        self.grid_deployment_fields.addWidget(self.lbl_ed_deployment_id, 2, 0, 1, 1)

        self.ed_deployment_id = QLineEdit(self.grp_deployment)
        self.ed_deployment_id.setObjectName(u"ed_deployment_id")

        self.grid_deployment_fields.addWidget(self.ed_deployment_id, 2, 1, 1, 1)

        self.lbl_ed_pump_turbine = QLabel(self.grp_deployment)
        self.lbl_ed_pump_turbine.setObjectName(u"lbl_ed_pump_turbine")

        self.grid_deployment_fields.addWidget(self.lbl_ed_pump_turbine, 3, 0, 1, 1)

        self.ed_pump_turbine = QLineEdit(self.grp_deployment)
        self.ed_pump_turbine.setObjectName(u"ed_pump_turbine")

        self.grid_deployment_fields.addWidget(self.ed_pump_turbine, 3, 1, 1, 1)

        self.lbl_ed_type = QLabel(self.grp_deployment)
        self.lbl_ed_type.setObjectName(u"lbl_ed_type")

        self.grid_deployment_fields.addWidget(self.lbl_ed_type, 4, 0, 1, 1)

        self.ed_type = QLineEdit(self.grp_deployment)
        self.ed_type.setObjectName(u"ed_type")

        self.grid_deployment_fields.addWidget(self.ed_type, 4, 1, 1, 1)

        self.lbl_ed_rpm = QLabel(self.grp_deployment)
        self.lbl_ed_rpm.setObjectName(u"lbl_ed_rpm")

        self.grid_deployment_fields.addWidget(self.lbl_ed_rpm, 5, 0, 1, 1)

        self.ed_rpm = QLineEdit(self.grp_deployment)
        self.ed_rpm.setObjectName(u"ed_rpm")

        self.grid_deployment_fields.addWidget(self.ed_rpm, 5, 1, 1, 1)

        self.lbl_ed_head = QLabel(self.grp_deployment)
        self.lbl_ed_head.setObjectName(u"lbl_ed_head")

        self.grid_deployment_fields.addWidget(self.lbl_ed_head, 6, 0, 1, 1)

        self.ed_head = QLineEdit(self.grp_deployment)
        self.ed_head.setObjectName(u"ed_head")

        self.grid_deployment_fields.addWidget(self.ed_head, 6, 1, 1, 1)

        self.lbl_ed_flow = QLabel(self.grp_deployment)
        self.lbl_ed_flow.setObjectName(u"lbl_ed_flow")

        self.grid_deployment_fields.addWidget(self.lbl_ed_flow, 7, 0, 1, 1)

        self.ed_flow = QLineEdit(self.grp_deployment)
        self.ed_flow.setObjectName(u"ed_flow")

        self.grid_deployment_fields.addWidget(self.ed_flow, 7, 1, 1, 1)

        self.lbl_ed_point_bep = QLabel(self.grp_deployment)
        self.lbl_ed_point_bep.setObjectName(u"lbl_ed_point_bep")

        self.grid_deployment_fields.addWidget(self.lbl_ed_point_bep, 8, 0, 1, 1)

        self.ed_point_bep = QLineEdit(self.grp_deployment)
        self.ed_point_bep.setObjectName(u"ed_point_bep")

        self.grid_deployment_fields.addWidget(self.ed_point_bep, 8, 1, 1, 1)

        self.lbl_ed_treatment = QLabel(self.grp_deployment)
        self.lbl_ed_treatment.setObjectName(u"lbl_ed_treatment")

        self.grid_deployment_fields.addWidget(self.lbl_ed_treatment, 9, 0, 1, 1)

        self.ed_treatment = QLineEdit(self.grp_deployment)
        self.ed_treatment.setObjectName(u"ed_treatment")

        self.grid_deployment_fields.addWidget(self.ed_treatment, 9, 1, 1, 1)

        self.lbl_ed_run = QLabel(self.grp_deployment)
        self.lbl_ed_run.setObjectName(u"lbl_ed_run")

        self.grid_deployment_fields.addWidget(self.lbl_ed_run, 10, 0, 1, 1)

        self.ed_run = QLineEdit(self.grp_deployment)
        self.ed_run.setObjectName(u"ed_run")

        self.grid_deployment_fields.addWidget(self.ed_run, 10, 1, 1, 1)


        self.layout_grp_deployment.addLayout(self.grid_deployment_fields)

        self.btn_save_deployment = QPushButton(self.grp_deployment)
        self.btn_save_deployment.setObjectName(u"btn_save_deployment")
        self.btn_save_deployment.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_grp_deployment.addWidget(self.btn_save_deployment)


        self.grid_meta.addWidget(self.grp_deployment, 0, 0, 2, 1)

        self.grp_meta_inventory = QGroupBox(self.tab_meta)
        self.grp_meta_inventory.setObjectName(u"grp_meta_inventory")
        self.layout_grp_meta_inventory = QVBoxLayout(self.grp_meta_inventory)
        self.layout_grp_meta_inventory.setSpacing(6)
        self.layout_grp_meta_inventory.setObjectName(u"layout_grp_meta_inventory")
        self.layout_grp_meta_inventory.setContentsMargins(6, 6, 6, 6)
        self.table_meta = QTableWidget(self.grp_meta_inventory)
        if (self.table_meta.columnCount() < 5):
            self.table_meta.setColumnCount(5)
        __qtablewidgetitem31 = QTableWidgetItem()
        self.table_meta.setHorizontalHeaderItem(0, __qtablewidgetitem31)
        __qtablewidgetitem32 = QTableWidgetItem()
        self.table_meta.setHorizontalHeaderItem(1, __qtablewidgetitem32)
        __qtablewidgetitem33 = QTableWidgetItem()
        self.table_meta.setHorizontalHeaderItem(2, __qtablewidgetitem33)
        __qtablewidgetitem34 = QTableWidgetItem()
        self.table_meta.setHorizontalHeaderItem(3, __qtablewidgetitem34)
        __qtablewidgetitem35 = QTableWidgetItem()
        self.table_meta.setHorizontalHeaderItem(4, __qtablewidgetitem35)
        self.table_meta.setObjectName(u"table_meta")
        self.table_meta.setMinimumSize(QSize(0, 200))
        self.table_meta.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_meta.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.layout_grp_meta_inventory.addWidget(self.table_meta)

        self.layout_meta_controls = QHBoxLayout()
        self.layout_meta_controls.setObjectName(u"layout_meta_controls")
        self.chk_meta_select_all = QCheckBox(self.grp_meta_inventory)
        self.chk_meta_select_all.setObjectName(u"chk_meta_select_all")
        self.chk_meta_select_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_meta_controls.addWidget(self.chk_meta_select_all)

        self.spacer_2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_meta_controls.addItem(self.spacer_2)

        self.btn_apply_deployment = QPushButton(self.grp_meta_inventory)
        self.btn_apply_deployment.setObjectName(u"btn_apply_deployment")
        self.btn_apply_deployment.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_meta_controls.addWidget(self.btn_apply_deployment)


        self.layout_grp_meta_inventory.addLayout(self.layout_meta_controls)


        self.grid_meta.addWidget(self.grp_meta_inventory, 2, 0, 1, 1)

        self.grp_dash_library = QGroupBox(self.tab_meta)
        self.grp_dash_library.setObjectName(u"grp_dash_library")
        self.layout_grp_dash_library = QVBoxLayout(self.grp_dash_library)
        self.layout_grp_dash_library.setSpacing(6)
        self.layout_grp_dash_library.setObjectName(u"layout_grp_dash_library")
        self.layout_grp_dash_library.setContentsMargins(6, 6, 6, 6)
        self.lbl_dash_library_value = QLabel(self.grp_dash_library)
        self.lbl_dash_library_value.setObjectName(u"lbl_dash_library_value")
        self.lbl_dash_library_value.setFont(font)

        self.layout_grp_dash_library.addWidget(self.lbl_dash_library_value)

        self.lbl_dash_library_caption = QLabel(self.grp_dash_library)
        self.lbl_dash_library_caption.setObjectName(u"lbl_dash_library_caption")

        self.layout_grp_dash_library.addWidget(self.lbl_dash_library_caption)

        self.lbl_dash_library_detail = QLabel(self.grp_dash_library)
        self.lbl_dash_library_detail.setObjectName(u"lbl_dash_library_detail")

        self.layout_grp_dash_library.addWidget(self.lbl_dash_library_detail)

        self.spacer_3 = QSpacerItem(40, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_grp_dash_library.addItem(self.spacer_3)


        self.grid_meta.addWidget(self.grp_dash_library, 0, 1, 1, 1)

        self.grp_dash_coverage = QGroupBox(self.tab_meta)
        self.grp_dash_coverage.setObjectName(u"grp_dash_coverage")
        self.layout_grp_dash_coverage = QVBoxLayout(self.grp_dash_coverage)
        self.layout_grp_dash_coverage.setSpacing(6)
        self.layout_grp_dash_coverage.setObjectName(u"layout_grp_dash_coverage")
        self.layout_grp_dash_coverage.setContentsMargins(6, 6, 6, 6)
        self.lbl_dash_coverage_value = QLabel(self.grp_dash_coverage)
        self.lbl_dash_coverage_value.setObjectName(u"lbl_dash_coverage_value")
        self.lbl_dash_coverage_value.setFont(font)

        self.layout_grp_dash_coverage.addWidget(self.lbl_dash_coverage_value)

        self.lbl_dash_coverage_caption = QLabel(self.grp_dash_coverage)
        self.lbl_dash_coverage_caption.setObjectName(u"lbl_dash_coverage_caption")

        self.layout_grp_dash_coverage.addWidget(self.lbl_dash_coverage_caption)

        self.lbl_dash_coverage_detail = QLabel(self.grp_dash_coverage)
        self.lbl_dash_coverage_detail.setObjectName(u"lbl_dash_coverage_detail")

        self.layout_grp_dash_coverage.addWidget(self.lbl_dash_coverage_detail)

        self.spacer_4 = QSpacerItem(40, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_grp_dash_coverage.addItem(self.spacer_4)


        self.grid_meta.addWidget(self.grp_dash_coverage, 0, 2, 1, 1)

        self.grp_dash_quality = QGroupBox(self.tab_meta)
        self.grp_dash_quality.setObjectName(u"grp_dash_quality")
        self.layout_grp_dash_quality = QVBoxLayout(self.grp_dash_quality)
        self.layout_grp_dash_quality.setSpacing(6)
        self.layout_grp_dash_quality.setObjectName(u"layout_grp_dash_quality")
        self.layout_grp_dash_quality.setContentsMargins(6, 6, 6, 6)
        self.lbl_dash_quality_value = QLabel(self.grp_dash_quality)
        self.lbl_dash_quality_value.setObjectName(u"lbl_dash_quality_value")
        self.lbl_dash_quality_value.setFont(font)

        self.layout_grp_dash_quality.addWidget(self.lbl_dash_quality_value)

        self.lbl_dash_quality_caption = QLabel(self.grp_dash_quality)
        self.lbl_dash_quality_caption.setObjectName(u"lbl_dash_quality_caption")

        self.layout_grp_dash_quality.addWidget(self.lbl_dash_quality_caption)

        self.lbl_dash_quality_detail = QLabel(self.grp_dash_quality)
        self.lbl_dash_quality_detail.setObjectName(u"lbl_dash_quality_detail")

        self.layout_grp_dash_quality.addWidget(self.lbl_dash_quality_detail)

        self.spacer_5 = QSpacerItem(40, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_grp_dash_quality.addItem(self.spacer_5)


        self.grid_meta.addWidget(self.grp_dash_quality, 1, 1, 1, 1)

        self.grp_dash_sites = QGroupBox(self.tab_meta)
        self.grp_dash_sites.setObjectName(u"grp_dash_sites")
        self.layout_grp_dash_sites = QVBoxLayout(self.grp_dash_sites)
        self.layout_grp_dash_sites.setSpacing(6)
        self.layout_grp_dash_sites.setObjectName(u"layout_grp_dash_sites")
        self.layout_grp_dash_sites.setContentsMargins(6, 6, 6, 6)
        self.lbl_dash_sites_value = QLabel(self.grp_dash_sites)
        self.lbl_dash_sites_value.setObjectName(u"lbl_dash_sites_value")
        self.lbl_dash_sites_value.setFont(font)

        self.layout_grp_dash_sites.addWidget(self.lbl_dash_sites_value)

        self.lbl_dash_sites_caption = QLabel(self.grp_dash_sites)
        self.lbl_dash_sites_caption.setObjectName(u"lbl_dash_sites_caption")

        self.layout_grp_dash_sites.addWidget(self.lbl_dash_sites_caption)

        self.lbl_dash_sites_detail = QLabel(self.grp_dash_sites)
        self.lbl_dash_sites_detail.setObjectName(u"lbl_dash_sites_detail")

        self.layout_grp_dash_sites.addWidget(self.lbl_dash_sites_detail)

        self.spacer_6 = QSpacerItem(40, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_grp_dash_sites.addItem(self.spacer_6)


        self.grid_meta.addWidget(self.grp_dash_sites, 1, 2, 1, 1)

        self.grp_dash_delineated = QGroupBox(self.tab_meta)
        self.grp_dash_delineated.setObjectName(u"grp_dash_delineated")
        self.layout_grp_dash_delineated = QVBoxLayout(self.grp_dash_delineated)
        self.layout_grp_dash_delineated.setSpacing(6)
        self.layout_grp_dash_delineated.setObjectName(u"layout_grp_dash_delineated")
        self.layout_grp_dash_delineated.setContentsMargins(6, 6, 6, 6)
        self.lbl_dash_delineated_value = QLabel(self.grp_dash_delineated)
        self.lbl_dash_delineated_value.setObjectName(u"lbl_dash_delineated_value")
        self.lbl_dash_delineated_value.setFont(font)

        self.layout_grp_dash_delineated.addWidget(self.lbl_dash_delineated_value)

        self.lbl_dash_delineated_caption = QLabel(self.grp_dash_delineated)
        self.lbl_dash_delineated_caption.setObjectName(u"lbl_dash_delineated_caption")

        self.layout_grp_dash_delineated.addWidget(self.lbl_dash_delineated_caption)

        self.lbl_dash_delineated_detail = QLabel(self.grp_dash_delineated)
        self.lbl_dash_delineated_detail.setObjectName(u"lbl_dash_delineated_detail")

        self.layout_grp_dash_delineated.addWidget(self.lbl_dash_delineated_detail)

        self.spacer_dash_delineated = QSpacerItem(40, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_grp_dash_delineated.addItem(self.spacer_dash_delineated)


        self.grid_meta.addWidget(self.grp_dash_delineated, 2, 1, 1, 1)

        self.grp_dash_treatments = QGroupBox(self.tab_meta)
        self.grp_dash_treatments.setObjectName(u"grp_dash_treatments")
        self.layout_grp_dash_treatments = QVBoxLayout(self.grp_dash_treatments)
        self.layout_grp_dash_treatments.setSpacing(6)
        self.layout_grp_dash_treatments.setObjectName(u"layout_grp_dash_treatments")
        self.layout_grp_dash_treatments.setContentsMargins(6, 6, 6, 6)
        self.lbl_dash_treatments_value = QLabel(self.grp_dash_treatments)
        self.lbl_dash_treatments_value.setObjectName(u"lbl_dash_treatments_value")
        self.lbl_dash_treatments_value.setFont(font)

        self.layout_grp_dash_treatments.addWidget(self.lbl_dash_treatments_value)

        self.lbl_dash_treatments_caption = QLabel(self.grp_dash_treatments)
        self.lbl_dash_treatments_caption.setObjectName(u"lbl_dash_treatments_caption")

        self.layout_grp_dash_treatments.addWidget(self.lbl_dash_treatments_caption)

        self.lbl_dash_treatments_detail = QLabel(self.grp_dash_treatments)
        self.lbl_dash_treatments_detail.setObjectName(u"lbl_dash_treatments_detail")

        self.layout_grp_dash_treatments.addWidget(self.lbl_dash_treatments_detail)

        self.spacer_dash_treatments = QSpacerItem(40, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.layout_grp_dash_treatments.addItem(self.spacer_dash_treatments)


        self.grid_meta.addWidget(self.grp_dash_treatments, 2, 2, 1, 1)

        self.grid_meta.setRowStretch(0, 1)
        self.grid_meta.setRowStretch(1, 1)
        self.grid_meta.setRowStretch(2, 1)
        self.grid_meta.setColumnStretch(0, 4)
        self.grid_meta.setColumnStretch(1, 3)
        self.grid_meta.setColumnStretch(2, 3)
        self.tabs_process.addTab(self.tab_meta, "")

        self.layout_content_process.addWidget(self.tabs_process)


        self.layout_process.addWidget(self.content_process)

        self.stackedWidget.addWidget(self.page_process)
        self.page_validate = QWidget()
        self.page_validate.setObjectName(u"page_validate")
        self.layout_validate = QVBoxLayout(self.page_validate)
        self.layout_validate.setSpacing(10)
        self.layout_validate.setObjectName(u"layout_validate")
        self.layout_validate.setContentsMargins(10, 10, 10, 10)
        self.title_validate = QLabel(self.page_validate)
        self.title_validate.setObjectName(u"title_validate")
        self.title_validate.setMaximumSize(QSize(16777215, 30))
        self.title_validate.setFont(font)

        self.layout_validate.addWidget(self.title_validate)

        self.subtitle_validate = QLabel(self.page_validate)
        self.subtitle_validate.setObjectName(u"subtitle_validate")
        self.subtitle_validate.setMaximumSize(QSize(16777215, 20))
        self.subtitle_validate.setWordWrap(True)

        self.layout_validate.addWidget(self.subtitle_validate)

        self.content_validate = QFrame(self.page_validate)
        self.content_validate.setObjectName(u"content_validate")
        self.content_validate.setFrameShape(QFrame.NoFrame)
        self.content_validate.setFrameShadow(QFrame.Raised)
        self.grid_validate = QGridLayout(self.content_validate)
        self.grid_validate.setSpacing(8)
        self.grid_validate.setObjectName(u"grid_validate")
        self.grid_validate.setContentsMargins(8, 8, 8, 8)
        self.grp_val_library = QGroupBox(self.content_validate)
        self.grp_val_library.setObjectName(u"grp_val_library")
        self.layout_grp_val_library = QVBoxLayout(self.grp_val_library)
        self.layout_grp_val_library.setSpacing(6)
        self.layout_grp_val_library.setObjectName(u"layout_grp_val_library")
        self.layout_grp_val_library.setContentsMargins(6, 6, 6, 6)
        self.tree_val_library = QTreeView(self.grp_val_library)
        self.tree_val_library.setObjectName(u"tree_val_library")

        self.layout_grp_val_library.addWidget(self.tree_val_library)

        self.btn_val_change_libraries = QPushButton(self.grp_val_library)
        self.btn_val_change_libraries.setObjectName(u"btn_val_change_libraries")
        self.btn_val_change_libraries.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_grp_val_library.addWidget(self.btn_val_change_libraries)


        self.grid_validate.addWidget(self.grp_val_library, 0, 0, 1, 1)

        self.grp_val_files = QGroupBox(self.content_validate)
        self.grp_val_files.setObjectName(u"grp_val_files")
        self.layout_grp_val_files = QVBoxLayout(self.grp_val_files)
        self.layout_grp_val_files.setSpacing(6)
        self.layout_grp_val_files.setObjectName(u"layout_grp_val_files")
        self.layout_grp_val_files.setContentsMargins(6, 6, 6, 6)
        self.tree_val_files = QTreeWidget(self.grp_val_files)
        self.tree_val_files.setObjectName(u"tree_val_files")
        self.tree_val_files.setHeaderHidden(True)

        self.layout_grp_val_files.addWidget(self.tree_val_files)

        self.lbl_val_progress = QLabel(self.grp_val_files)
        self.lbl_val_progress.setObjectName(u"lbl_val_progress")
        font5 = QFont()
        font5.setBold(True)
        self.lbl_val_progress.setFont(font5)
        self.lbl_val_progress.setAlignment(Qt.AlignCenter)

        self.layout_grp_val_files.addWidget(self.lbl_val_progress)

        self.btn_val_save_next = QPushButton(self.grp_val_files)
        self.btn_val_save_next.setObjectName(u"btn_val_save_next")
        self.btn_val_save_next.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_val_save_next.setEnabled(False)

        self.layout_grp_val_files.addWidget(self.btn_val_save_next)

        self.btn_val_reset = QPushButton(self.grp_val_files)
        self.btn_val_reset.setObjectName(u"btn_val_reset")
        self.btn_val_reset.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_val_reset.setEnabled(False)

        self.layout_grp_val_files.addWidget(self.btn_val_reset)

        self.btn_val_jump = QPushButton(self.grp_val_files)
        self.btn_val_jump.setObjectName(u"btn_val_jump")
        self.btn_val_jump.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_val_jump.setEnabled(False)

        self.layout_grp_val_files.addWidget(self.btn_val_jump)


        self.grid_validate.addWidget(self.grp_val_files, 1, 0, 1, 1)

        self.grp_val_plot = QGroupBox(self.content_validate)
        self.grp_val_plot.setObjectName(u"grp_val_plot")
        self.layout_grp_val_plot = QVBoxLayout(self.grp_val_plot)
        self.layout_grp_val_plot.setSpacing(6)
        self.layout_grp_val_plot.setObjectName(u"layout_grp_val_plot")
        self.layout_grp_val_plot.setContentsMargins(6, 6, 6, 6)
        self.layout_val_controls = QHBoxLayout()
        self.layout_val_controls.setObjectName(u"layout_val_controls")
        self.lbl_val_left = QLabel(self.grp_val_plot)
        self.lbl_val_left.setObjectName(u"lbl_val_left")

        self.layout_val_controls.addWidget(self.lbl_val_left)

        self.cmb_val_left = QComboBox(self.grp_val_plot)
        self.cmb_val_left.setObjectName(u"cmb_val_left")

        self.layout_val_controls.addWidget(self.cmb_val_left)

        self.lbl_val_right = QLabel(self.grp_val_plot)
        self.lbl_val_right.setObjectName(u"lbl_val_right")

        self.layout_val_controls.addWidget(self.lbl_val_right)

        self.cmb_val_right = QComboBox(self.grp_val_plot)
        self.cmb_val_right.setObjectName(u"cmb_val_right")

        self.layout_val_controls.addWidget(self.cmb_val_right)

        self.lbl_val_window = QLabel(self.grp_val_plot)
        self.lbl_val_window.setObjectName(u"lbl_val_window")

        self.layout_val_controls.addWidget(self.lbl_val_window)

        self.cmb_val_window = QComboBox(self.grp_val_plot)
        self.cmb_val_window.setObjectName(u"cmb_val_window")

        self.layout_val_controls.addWidget(self.cmb_val_window)

        self.spacer_val_controls = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_val_controls.addItem(self.spacer_val_controls)


        self.layout_grp_val_plot.addLayout(self.layout_val_controls)

        self.frame_val_plot = QFrame(self.grp_val_plot)
        self.frame_val_plot.setObjectName(u"frame_val_plot")
        self.frame_val_plot.setFrameShape(QFrame.NoFrame)

        self.layout_grp_val_plot.addWidget(self.frame_val_plot)

        self.layout_val_loading = QHBoxLayout()
        self.layout_val_loading.setObjectName(u"layout_val_loading")
        self.frame_val_spinner = QFrame(self.grp_val_plot)
        self.frame_val_spinner.setObjectName(u"frame_val_spinner")
        self.frame_val_spinner.setFrameShape(QFrame.NoFrame)
        self.frame_val_spinner.setMinimumSize(QSize(20, 20))
        self.frame_val_spinner.setMaximumSize(QSize(20, 20))

        self.layout_val_loading.addWidget(self.frame_val_spinner)

        self.lbl_val_loading = QLabel(self.grp_val_plot)
        self.lbl_val_loading.setObjectName(u"lbl_val_loading")

        self.layout_val_loading.addWidget(self.lbl_val_loading)


        self.layout_grp_val_plot.addLayout(self.layout_val_loading)


        self.grid_validate.addWidget(self.grp_val_plot, 0, 1, 2, 1)

        self.grid_validate.setRowStretch(0, 1)
        self.grid_validate.setRowStretch(1, 1)
        self.grid_validate.setColumnStretch(0, 3)
        self.grid_validate.setColumnStretch(1, 7)

        self.layout_validate.addWidget(self.content_validate)

        self.stackedWidget.addWidget(self.page_validate)
        self.page_dataset = QWidget()
        self.page_dataset.setObjectName(u"page_dataset")
        self.layout_dataset = QVBoxLayout(self.page_dataset)
        self.layout_dataset.setSpacing(10)
        self.layout_dataset.setObjectName(u"layout_dataset")
        self.layout_dataset.setContentsMargins(10, 10, 10, 10)
        self.title_dataset = QLabel(self.page_dataset)
        self.title_dataset.setObjectName(u"title_dataset")
        self.title_dataset.setMaximumSize(QSize(16777215, 30))
        self.title_dataset.setFont(font)

        self.layout_dataset.addWidget(self.title_dataset)

        self.subtitle_dataset = QLabel(self.page_dataset)
        self.subtitle_dataset.setObjectName(u"subtitle_dataset")
        self.subtitle_dataset.setMaximumSize(QSize(16777215, 20))
        self.subtitle_dataset.setWordWrap(True)

        self.layout_dataset.addWidget(self.subtitle_dataset)

        self.content_dataset = QFrame(self.page_dataset)
        self.content_dataset.setObjectName(u"content_dataset")
        self.content_dataset.setFrameShape(QFrame.NoFrame)
        self.content_dataset.setFrameShadow(QFrame.Raised)
        self.grid_dataset = QGridLayout(self.content_dataset)
        self.grid_dataset.setSpacing(8)
        self.grid_dataset.setObjectName(u"grid_dataset")
        self.grid_dataset.setContentsMargins(8, 8, 8, 8)
        self.grp_ds_library = QGroupBox(self.content_dataset)
        self.grp_ds_library.setObjectName(u"grp_ds_library")
        self.layout_grp_ds_library = QVBoxLayout(self.grp_ds_library)
        self.layout_grp_ds_library.setSpacing(6)
        self.layout_grp_ds_library.setObjectName(u"layout_grp_ds_library")
        self.layout_grp_ds_library.setContentsMargins(6, 6, 6, 6)
        self.tree_ds_library = QTreeView(self.grp_ds_library)
        self.tree_ds_library.setObjectName(u"tree_ds_library")

        self.layout_grp_ds_library.addWidget(self.tree_ds_library)

        self.btn_ds_change_libraries = QPushButton(self.grp_ds_library)
        self.btn_ds_change_libraries.setObjectName(u"btn_ds_change_libraries")
        self.btn_ds_change_libraries.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_grp_ds_library.addWidget(self.btn_ds_change_libraries)


        self.grid_dataset.addWidget(self.grp_ds_library, 0, 0, 1, 1)

        self.grp_ds_filter = QGroupBox(self.content_dataset)
        self.grp_ds_filter.setObjectName(u"grp_ds_filter")
        self.layout_grp_ds_filter = QVBoxLayout(self.grp_ds_filter)
        self.layout_grp_ds_filter.setSpacing(6)
        self.layout_grp_ds_filter.setObjectName(u"layout_grp_ds_filter")
        self.layout_grp_ds_filter.setContentsMargins(6, 6, 6, 6)
        self.tree_ds_filter = QTreeWidget(self.grp_ds_filter)
        self.tree_ds_filter.setObjectName(u"tree_ds_filter")
        self.tree_ds_filter.setHeaderHidden(True)

        self.layout_grp_ds_filter.addWidget(self.tree_ds_filter)

        self.chk_ds_select_all = QCheckBox(self.grp_ds_filter)
        self.chk_ds_select_all.setObjectName(u"chk_ds_select_all")
        self.chk_ds_select_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_grp_ds_filter.addWidget(self.chk_ds_select_all)


        self.grid_dataset.addWidget(self.grp_ds_filter, 1, 0, 1, 1)

        self.grp_ds_console = QGroupBox(self.content_dataset)
        self.grp_ds_console.setObjectName(u"grp_ds_console")
        self.layout_grp_ds_console = QVBoxLayout(self.grp_ds_console)
        self.layout_grp_ds_console.setSpacing(6)
        self.layout_grp_ds_console.setObjectName(u"layout_grp_ds_console")
        self.layout_grp_ds_console.setContentsMargins(6, 6, 6, 6)
        self.console_ds = QPlainTextEdit(self.grp_ds_console)
        self.console_ds.setObjectName(u"console_ds")
        self.console_ds.setReadOnly(True)

        self.layout_grp_ds_console.addWidget(self.console_ds)


        self.grid_dataset.addWidget(self.grp_ds_console, 2, 0, 1, 1)

        self.grp_ds_create = QGroupBox(self.content_dataset)
        self.grp_ds_create.setObjectName(u"grp_ds_create")
        self.layout_grp_ds_create = QVBoxLayout(self.grp_ds_create)
        self.layout_grp_ds_create.setSpacing(6)
        self.layout_grp_ds_create.setObjectName(u"layout_grp_ds_create")
        self.layout_grp_ds_create.setContentsMargins(6, 6, 6, 6)
        self.rb_ds_unsegmented = QRadioButton(self.grp_ds_create)
        self.rb_ds_unsegmented.setObjectName(u"rb_ds_unsegmented")
        self.rb_ds_unsegmented.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.rb_ds_unsegmented.setChecked(True)

        self.layout_grp_ds_create.addWidget(self.rb_ds_unsegmented)

        self.rb_ds_segmented = QRadioButton(self.grp_ds_create)
        self.rb_ds_segmented.setObjectName(u"rb_ds_segmented")
        self.rb_ds_segmented.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_grp_ds_create.addWidget(self.rb_ds_segmented)

        self.layout_ds_create_buttons = QHBoxLayout()
        self.layout_ds_create_buttons.setObjectName(u"layout_ds_create_buttons")
        self.btn_ds_create = QPushButton(self.grp_ds_create)
        self.btn_ds_create.setObjectName(u"btn_ds_create")
        self.btn_ds_create.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ds_create.setEnabled(False)

        self.layout_ds_create_buttons.addWidget(self.btn_ds_create)

        self.btn_ds_save = QPushButton(self.grp_ds_create)
        self.btn_ds_save.setObjectName(u"btn_ds_save")
        self.btn_ds_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ds_save.setEnabled(False)

        self.layout_ds_create_buttons.addWidget(self.btn_ds_save)

        self.spacer_ds_create = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_ds_create_buttons.addItem(self.spacer_ds_create)


        self.layout_grp_ds_create.addLayout(self.layout_ds_create_buttons)


        self.grid_dataset.addWidget(self.grp_ds_create, 0, 1, 1, 1)

        self.grp_ds_annotate = QGroupBox(self.content_dataset)
        self.grp_ds_annotate.setObjectName(u"grp_ds_annotate")
        self.layout_grp_ds_annotate = QVBoxLayout(self.grp_ds_annotate)
        self.layout_grp_ds_annotate.setSpacing(6)
        self.layout_grp_ds_annotate.setObjectName(u"layout_grp_ds_annotate")
        self.layout_grp_ds_annotate.setContentsMargins(6, 6, 6, 6)
        self.layout_ds_feat_row = QHBoxLayout()
        self.layout_ds_feat_row.setObjectName(u"layout_ds_feat_row")
        self.lbl_ds_features = QLabel(self.grp_ds_annotate)
        self.lbl_ds_features.setObjectName(u"lbl_ds_features")

        self.layout_ds_feat_row.addWidget(self.lbl_ds_features)

        self.ed_ds_features = QLineEdit(self.grp_ds_annotate)
        self.ed_ds_features.setObjectName(u"ed_ds_features")
        self.ed_ds_features.setReadOnly(True)

        self.layout_ds_feat_row.addWidget(self.ed_ds_features)

        self.btn_ds_browse_features = QPushButton(self.grp_ds_annotate)
        self.btn_ds_browse_features.setObjectName(u"btn_ds_browse_features")
        self.btn_ds_browse_features.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_ds_feat_row.addWidget(self.btn_ds_browse_features)


        self.layout_grp_ds_annotate.addLayout(self.layout_ds_feat_row)

        self.layout_ds_lab_row = QHBoxLayout()
        self.layout_ds_lab_row.setObjectName(u"layout_ds_lab_row")
        self.lbl_ds_labels = QLabel(self.grp_ds_annotate)
        self.lbl_ds_labels.setObjectName(u"lbl_ds_labels")

        self.layout_ds_lab_row.addWidget(self.lbl_ds_labels)

        self.ed_ds_labels = QLineEdit(self.grp_ds_annotate)
        self.ed_ds_labels.setObjectName(u"ed_ds_labels")
        self.ed_ds_labels.setReadOnly(True)

        self.layout_ds_lab_row.addWidget(self.ed_ds_labels)

        self.btn_ds_browse_labels = QPushButton(self.grp_ds_annotate)
        self.btn_ds_browse_labels.setObjectName(u"btn_ds_browse_labels")
        self.btn_ds_browse_labels.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.layout_ds_lab_row.addWidget(self.btn_ds_browse_labels)


        self.layout_grp_ds_annotate.addLayout(self.layout_ds_lab_row)

        self.layout_ds_annotate_buttons = QHBoxLayout()
        self.layout_ds_annotate_buttons.setObjectName(u"layout_ds_annotate_buttons")
        self.btn_ds_append = QPushButton(self.grp_ds_annotate)
        self.btn_ds_append.setObjectName(u"btn_ds_append")
        self.btn_ds_append.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ds_append.setEnabled(False)

        self.layout_ds_annotate_buttons.addWidget(self.btn_ds_append)

        self.btn_ds_save_annotated = QPushButton(self.grp_ds_annotate)
        self.btn_ds_save_annotated.setObjectName(u"btn_ds_save_annotated")
        self.btn_ds_save_annotated.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ds_save_annotated.setEnabled(False)

        self.layout_ds_annotate_buttons.addWidget(self.btn_ds_save_annotated)

        self.spacer_ds_annotate = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layout_ds_annotate_buttons.addItem(self.spacer_ds_annotate)


        self.layout_grp_ds_annotate.addLayout(self.layout_ds_annotate_buttons)


        self.grid_dataset.addWidget(self.grp_ds_annotate, 1, 1, 1, 1)

        self.grp_ds_figure = QGroupBox(self.content_dataset)
        self.grp_ds_figure.setObjectName(u"grp_ds_figure")
        self.layout_grp_ds_figure = QVBoxLayout(self.grp_ds_figure)
        self.layout_grp_ds_figure.setSpacing(6)
        self.layout_grp_ds_figure.setObjectName(u"layout_grp_ds_figure")
        self.layout_grp_ds_figure.setContentsMargins(6, 6, 6, 6)
        self.frame_ds_figure = QFrame(self.grp_ds_figure)
        self.frame_ds_figure.setObjectName(u"frame_ds_figure")
        self.frame_ds_figure.setFrameShape(QFrame.NoFrame)

        self.layout_grp_ds_figure.addWidget(self.frame_ds_figure)


        self.grid_dataset.addWidget(self.grp_ds_figure, 2, 1, 1, 1)

        self.grid_dataset.setRowStretch(0, 1)
        self.grid_dataset.setRowStretch(1, 2)
        self.grid_dataset.setRowStretch(2, 2)
        self.grid_dataset.setColumnStretch(0, 3)
        self.grid_dataset.setColumnStretch(1, 7)

        self.layout_dataset.addWidget(self.content_dataset)

        self.stackedWidget.addWidget(self.page_dataset)
        self.page_ml_training = QWidget()
        self.page_ml_training.setObjectName(u"page_ml_training")
        self.layout_ml_training = QVBoxLayout(self.page_ml_training)
        self.layout_ml_training.setSpacing(10)
        self.layout_ml_training.setObjectName(u"layout_ml_training")
        self.layout_ml_training.setContentsMargins(10, 10, 10, 10)
        self.title_ml_training = QLabel(self.page_ml_training)
        self.title_ml_training.setObjectName(u"title_ml_training")
        self.title_ml_training.setMaximumSize(QSize(16777215, 30))
        self.title_ml_training.setFont(font)

        self.layout_ml_training.addWidget(self.title_ml_training)

        self.subtitle_ml_training = QLabel(self.page_ml_training)
        self.subtitle_ml_training.setObjectName(u"subtitle_ml_training")
        self.subtitle_ml_training.setMaximumSize(QSize(16777215, 20))
        self.subtitle_ml_training.setWordWrap(True)

        self.layout_ml_training.addWidget(self.subtitle_ml_training)

        self.content_ml_training = QFrame(self.page_ml_training)
        self.content_ml_training.setObjectName(u"content_ml_training")
        self.content_ml_training.setFrameShape(QFrame.NoFrame)
        self.content_ml_training.setFrameShadow(QFrame.Raised)
        self.layout_content_ml_training = QVBoxLayout(self.content_ml_training)
        self.layout_content_ml_training.setSpacing(0)
        self.layout_content_ml_training.setObjectName(u"layout_content_ml_training")
        self.layout_content_ml_training.setContentsMargins(0, 0, 0, 0)
        self.tabs_ml_training = QTabWidget(self.content_ml_training)
        self.tabs_ml_training.setObjectName(u"tabs_ml_training")
        self.tab_train_configure = QWidget()
        self.tab_train_configure.setObjectName(u"tab_train_configure")
        self.layout_tab_train_configure = QVBoxLayout(self.tab_train_configure)
        self.layout_tab_train_configure.setSpacing(0)
        self.layout_tab_train_configure.setObjectName(u"layout_tab_train_configure")
        self.layout_tab_train_configure.setContentsMargins(0, 0, 0, 0)
        self.frame_train_configure = QFrame(self.tab_train_configure)
        self.frame_train_configure.setObjectName(u"frame_train_configure")
        self.frame_train_configure.setFrameShape(QFrame.NoFrame)
        self.frame_train_configure.setFrameShadow(QFrame.Raised)

        self.layout_tab_train_configure.addWidget(self.frame_train_configure)

        self.tabs_ml_training.addTab(self.tab_train_configure, "")
        self.tab_train_evaluate = QWidget()
        self.tab_train_evaluate.setObjectName(u"tab_train_evaluate")
        self.layout_tab_train_evaluate = QVBoxLayout(self.tab_train_evaluate)
        self.layout_tab_train_evaluate.setSpacing(0)
        self.layout_tab_train_evaluate.setObjectName(u"layout_tab_train_evaluate")
        self.layout_tab_train_evaluate.setContentsMargins(0, 0, 0, 0)
        self.frame_train_evaluate = QFrame(self.tab_train_evaluate)
        self.frame_train_evaluate.setObjectName(u"frame_train_evaluate")
        self.frame_train_evaluate.setFrameShape(QFrame.NoFrame)
        self.frame_train_evaluate.setFrameShadow(QFrame.Raised)

        self.layout_tab_train_evaluate.addWidget(self.frame_train_evaluate)

        self.tabs_ml_training.addTab(self.tab_train_evaluate, "")
        self.tab_train_deploy = QWidget()
        self.tab_train_deploy.setObjectName(u"tab_train_deploy")
        self.layout_tab_train_deploy = QVBoxLayout(self.tab_train_deploy)
        self.layout_tab_train_deploy.setSpacing(0)
        self.layout_tab_train_deploy.setObjectName(u"layout_tab_train_deploy")
        self.layout_tab_train_deploy.setContentsMargins(0, 0, 0, 0)
        self.frame_train_deploy = QFrame(self.tab_train_deploy)
        self.frame_train_deploy.setObjectName(u"frame_train_deploy")
        self.frame_train_deploy.setFrameShape(QFrame.NoFrame)
        self.frame_train_deploy.setFrameShadow(QFrame.Raised)

        self.layout_tab_train_deploy.addWidget(self.frame_train_deploy)

        self.tabs_ml_training.addTab(self.tab_train_deploy, "")

        self.layout_content_ml_training.addWidget(self.tabs_ml_training)


        self.layout_ml_training.addWidget(self.content_ml_training)

        self.stackedWidget.addWidget(self.page_ml_training)
        self.page_ml_performance = QWidget()
        self.page_ml_performance.setObjectName(u"page_ml_performance")
        self.layout_ml_performance = QVBoxLayout(self.page_ml_performance)
        self.layout_ml_performance.setSpacing(10)
        self.layout_ml_performance.setObjectName(u"layout_ml_performance")
        self.layout_ml_performance.setContentsMargins(10, 10, 10, 10)
        self.title_ml_performance = QLabel(self.page_ml_performance)
        self.title_ml_performance.setObjectName(u"title_ml_performance")
        self.title_ml_performance.setMaximumSize(QSize(16777215, 30))
        self.title_ml_performance.setFont(font)

        self.layout_ml_performance.addWidget(self.title_ml_performance)

        self.subtitle_ml_performance = QLabel(self.page_ml_performance)
        self.subtitle_ml_performance.setObjectName(u"subtitle_ml_performance")
        self.subtitle_ml_performance.setMaximumSize(QSize(16777215, 20))
        self.subtitle_ml_performance.setWordWrap(True)

        self.layout_ml_performance.addWidget(self.subtitle_ml_performance)

        self.content_ml_performance = QFrame(self.page_ml_performance)
        self.content_ml_performance.setObjectName(u"content_ml_performance")
        self.content_ml_performance.setFrameShape(QFrame.NoFrame)
        self.content_ml_performance.setFrameShadow(QFrame.Raised)

        self.layout_ml_performance.addWidget(self.content_ml_performance)

        self.stackedWidget.addWidget(self.page_ml_performance)
        self.page_ml_prediction = QWidget()
        self.page_ml_prediction.setObjectName(u"page_ml_prediction")
        self.layout_ml_prediction = QVBoxLayout(self.page_ml_prediction)
        self.layout_ml_prediction.setSpacing(10)
        self.layout_ml_prediction.setObjectName(u"layout_ml_prediction")
        self.layout_ml_prediction.setContentsMargins(10, 10, 10, 10)
        self.title_ml_prediction = QLabel(self.page_ml_prediction)
        self.title_ml_prediction.setObjectName(u"title_ml_prediction")
        self.title_ml_prediction.setMaximumSize(QSize(16777215, 30))
        self.title_ml_prediction.setFont(font)

        self.layout_ml_prediction.addWidget(self.title_ml_prediction)

        self.subtitle_ml_prediction = QLabel(self.page_ml_prediction)
        self.subtitle_ml_prediction.setObjectName(u"subtitle_ml_prediction")
        self.subtitle_ml_prediction.setMaximumSize(QSize(16777215, 20))
        self.subtitle_ml_prediction.setWordWrap(True)

        self.layout_ml_prediction.addWidget(self.subtitle_ml_prediction)

        self.content_ml_prediction = QFrame(self.page_ml_prediction)
        self.content_ml_prediction.setObjectName(u"content_ml_prediction")
        self.content_ml_prediction.setFrameShape(QFrame.NoFrame)
        self.content_ml_prediction.setFrameShadow(QFrame.Raised)
        self.layout_content_ml_prediction = QVBoxLayout(self.content_ml_prediction)
        self.layout_content_ml_prediction.setSpacing(0)
        self.layout_content_ml_prediction.setObjectName(u"layout_content_ml_prediction")
        self.layout_content_ml_prediction.setContentsMargins(0, 0, 0, 0)
        self.tabs_ml_prediction = QTabWidget(self.content_ml_prediction)
        self.tabs_ml_prediction.setObjectName(u"tabs_ml_prediction")
        self.tab_ml_predict = QWidget()
        self.tab_ml_predict.setObjectName(u"tab_ml_predict")
        self.layout_tab_ml_predict = QVBoxLayout(self.tab_ml_predict)
        self.layout_tab_ml_predict.setSpacing(0)
        self.layout_tab_ml_predict.setObjectName(u"layout_tab_ml_predict")
        self.layout_tab_ml_predict.setContentsMargins(0, 0, 0, 0)
        self.frame_ml_predict = QFrame(self.tab_ml_predict)
        self.frame_ml_predict.setObjectName(u"frame_ml_predict")
        self.frame_ml_predict.setFrameShape(QFrame.NoFrame)
        self.frame_ml_predict.setFrameShadow(QFrame.Raised)

        self.layout_tab_ml_predict.addWidget(self.frame_ml_predict)

        self.tabs_ml_prediction.addTab(self.tab_ml_predict, "")
        self.tab_ml_inspect = QWidget()
        self.tab_ml_inspect.setObjectName(u"tab_ml_inspect")
        self.layout_tab_ml_inspect = QVBoxLayout(self.tab_ml_inspect)
        self.layout_tab_ml_inspect.setSpacing(0)
        self.layout_tab_ml_inspect.setObjectName(u"layout_tab_ml_inspect")
        self.layout_tab_ml_inspect.setContentsMargins(0, 0, 0, 0)
        self.frame_ml_inspect = QFrame(self.tab_ml_inspect)
        self.frame_ml_inspect.setObjectName(u"frame_ml_inspect")
        self.frame_ml_inspect.setFrameShape(QFrame.NoFrame)
        self.frame_ml_inspect.setFrameShadow(QFrame.Raised)

        self.layout_tab_ml_inspect.addWidget(self.frame_ml_inspect)

        self.tabs_ml_prediction.addTab(self.tab_ml_inspect, "")
        self.tab_ml_report = QWidget()
        self.tab_ml_report.setObjectName(u"tab_ml_report")
        self.layout_tab_ml_report = QVBoxLayout(self.tab_ml_report)
        self.layout_tab_ml_report.setSpacing(0)
        self.layout_tab_ml_report.setObjectName(u"layout_tab_ml_report")
        self.layout_tab_ml_report.setContentsMargins(0, 0, 0, 0)
        self.frame_ml_report = QFrame(self.tab_ml_report)
        self.frame_ml_report.setObjectName(u"frame_ml_report")
        self.frame_ml_report.setFrameShape(QFrame.NoFrame)
        self.frame_ml_report.setFrameShadow(QFrame.Raised)

        self.layout_tab_ml_report.addWidget(self.frame_ml_report)

        self.tabs_ml_prediction.addTab(self.tab_ml_report, "")

        self.layout_content_ml_prediction.addWidget(self.tabs_ml_prediction)


        self.layout_ml_prediction.addWidget(self.content_ml_prediction)

        self.stackedWidget.addWidget(self.page_ml_prediction)

        self.verticalLayout_15.addWidget(self.stackedWidget)


        self.horizontalLayout_4.addWidget(self.pagesContainer)

        self.extraRightBox = QFrame(self.content)
        self.extraRightBox.setObjectName(u"extraRightBox")
        self.extraRightBox.setMinimumSize(QSize(0, 0))
        self.extraRightBox.setMaximumSize(QSize(0, 16777215))
        self.extraRightBox.setFrameShape(QFrame.NoFrame)
        self.extraRightBox.setFrameShadow(QFrame.Raised)
        self.verticalLayout_7 = QVBoxLayout(self.extraRightBox)
        self.verticalLayout_7.setSpacing(0)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.verticalLayout_7.setContentsMargins(0, 0, 0, 0)
        self.themeSettingsTopDetail = QFrame(self.extraRightBox)
        self.themeSettingsTopDetail.setObjectName(u"themeSettingsTopDetail")
        self.themeSettingsTopDetail.setMaximumSize(QSize(16777215, 3))
        self.themeSettingsTopDetail.setFrameShape(QFrame.NoFrame)
        self.themeSettingsTopDetail.setFrameShadow(QFrame.Raised)

        self.verticalLayout_7.addWidget(self.themeSettingsTopDetail)

        self.contentSettings = QFrame(self.extraRightBox)
        self.contentSettings.setObjectName(u"contentSettings")
        self.contentSettings.setFrameShape(QFrame.NoFrame)
        self.contentSettings.setFrameShadow(QFrame.Raised)
        self.verticalLayout_13 = QVBoxLayout(self.contentSettings)
        self.verticalLayout_13.setSpacing(0)
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.verticalLayout_13.setContentsMargins(0, 0, 0, 0)
        self.topMenus = QFrame(self.contentSettings)
        self.topMenus.setObjectName(u"topMenus")
        self.topMenus.setFrameShape(QFrame.NoFrame)
        self.topMenus.setFrameShadow(QFrame.Raised)
        self.verticalLayout_14 = QVBoxLayout(self.topMenus)
        self.verticalLayout_14.setSpacing(0)
        self.verticalLayout_14.setObjectName(u"verticalLayout_14")
        self.verticalLayout_14.setContentsMargins(0, 0, 0, 0)
        self.btn_adjustments = QPushButton(self.topMenus)
        self.btn_adjustments.setObjectName(u"btn_adjustments")
        sizePolicy.setHeightForWidth(self.btn_adjustments.sizePolicy().hasHeightForWidth())
        self.btn_adjustments.setSizePolicy(sizePolicy)
        self.btn_adjustments.setMinimumSize(QSize(0, 45))
        self.btn_adjustments.setFont(font)
        self.btn_adjustments.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_adjustments.setLayoutDirection(Qt.LeftToRight)
        self.btn_adjustments.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-equalizer.png);")

        self.verticalLayout_14.addWidget(self.btn_adjustments)

        self.btn_about = QPushButton(self.topMenus)
        self.btn_about.setObjectName(u"btn_about")
        sizePolicy.setHeightForWidth(self.btn_about.sizePolicy().hasHeightForWidth())
        self.btn_about.setSizePolicy(sizePolicy)
        self.btn_about.setMinimumSize(QSize(0, 45))
        self.btn_about.setFont(font)
        self.btn_about.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_about.setLayoutDirection(Qt.LeftToRight)
        self.btn_about.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-external-link.png);")

        self.verticalLayout_14.addWidget(self.btn_about)

        self.btn_more = QPushButton(self.topMenus)
        self.btn_more.setObjectName(u"btn_more")
        sizePolicy.setHeightForWidth(self.btn_more.sizePolicy().hasHeightForWidth())
        self.btn_more.setSizePolicy(sizePolicy)
        self.btn_more.setMinimumSize(QSize(0, 45))
        self.btn_more.setFont(font)
        self.btn_more.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_more.setLayoutDirection(Qt.LeftToRight)
        self.btn_more.setStyleSheet(u"background-image: url(:/icons/images/icons/cil-layers.png);")

        self.verticalLayout_14.addWidget(self.btn_more)


        self.verticalLayout_13.addWidget(self.topMenus, 0, Qt.AlignTop)


        self.verticalLayout_7.addWidget(self.contentSettings)


        self.horizontalLayout_4.addWidget(self.extraRightBox)


        self.verticalLayout_6.addWidget(self.content)

        self.bottomBar = QFrame(self.contentBottom)
        self.bottomBar.setObjectName(u"bottomBar")
        self.bottomBar.setMinimumSize(QSize(0, 22))
        self.bottomBar.setMaximumSize(QSize(16777215, 22))
        self.bottomBar.setFrameShape(QFrame.NoFrame)
        self.bottomBar.setFrameShadow(QFrame.Raised)
        self.horizontalLayout_5 = QHBoxLayout(self.bottomBar)
        self.horizontalLayout_5.setSpacing(0)
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.horizontalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.creditsLabel = QLabel(self.bottomBar)
        self.creditsLabel.setObjectName(u"creditsLabel")
        self.creditsLabel.setMaximumSize(QSize(16777215, 16))
        font6 = QFont()
        font6.setFamilies([u"Segoe UI"])
        font6.setBold(False)
        font6.setItalic(False)
        self.creditsLabel.setFont(font6)

        self.horizontalLayout_5.addWidget(self.creditsLabel)

        self.version = QLabel(self.bottomBar)
        self.version.setObjectName(u"version")

        self.horizontalLayout_5.addWidget(self.version)

        self.frame_size_grip = QFrame(self.bottomBar)
        self.frame_size_grip.setObjectName(u"frame_size_grip")
        self.frame_size_grip.setMinimumSize(QSize(20, 0))
        self.frame_size_grip.setMaximumSize(QSize(20, 16777215))
        self.frame_size_grip.setFrameShape(QFrame.NoFrame)
        self.frame_size_grip.setFrameShadow(QFrame.Raised)

        self.horizontalLayout_5.addWidget(self.frame_size_grip)


        self.verticalLayout_6.addWidget(self.bottomBar)


        self.verticalLayout_2.addWidget(self.contentBottom)


        self.appLayout.addWidget(self.contentBox)


        self.appMargins.addWidget(self.bgApp)

        MainWindow.setCentralWidget(self.styleSheet)

        self.retranslateUi(MainWindow)

        self.stackedWidget.setCurrentIndex(4)
        self.tabs_prepare.setCurrentIndex(0)
        self.tabs_process.setCurrentIndex(1)
        self.tabs_ml_training.setCurrentIndex(0)
        self.tabs_ml_prediction.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.titleLeftApp.setText(QCoreApplication.translate("MainWindow", u"StrikeWorks", None))
        self.titleLeftDescription.setText(QCoreApplication.translate("MainWindow", u"Passive sensor data toolkit", None))
        self.toggleButton.setText(QCoreApplication.translate("MainWindow", u"Hide", None))
        self.btn_home.setText(QCoreApplication.translate("MainWindow", u"Home", None))
        self.btn_sensor.setText(QCoreApplication.translate("MainWindow", u"Sensor processing", None))
        self.btn_ml.setText(QCoreApplication.translate("MainWindow", u"Machine learning analysis", None))
        self.btn_widgets.setText(QCoreApplication.translate("MainWindow", u"Widgets", None))
        self.btn_new.setText(QCoreApplication.translate("MainWindow", u"New", None))
        self.btn_save.setText(QCoreApplication.translate("MainWindow", u"Save", None))
        self.btn_exit.setText(QCoreApplication.translate("MainWindow", u"Exit", None))
        self.extraLabel.setText(QCoreApplication.translate("MainWindow", u"Sensor processing", None))
#if QT_CONFIG(tooltip)
        self.extraCloseColumnBtn.setToolTip(QCoreApplication.translate("MainWindow", u"Close sensor processing", None))
#endif // QT_CONFIG(tooltip)
        self.extraCloseColumnBtn.setText("")
        self.btn_prepare.setText(QCoreApplication.translate("MainWindow", u"Prepare", None))
        self.btn_process.setText(QCoreApplication.translate("MainWindow", u"Process", None))
        self.btn_validate.setText(QCoreApplication.translate("MainWindow", u"Validate & segment", None))
        self.btn_dataset.setText(QCoreApplication.translate("MainWindow", u"Dataset creation", None))
        self.btn_ml_training.setText(QCoreApplication.translate("MainWindow", u"Model training", None))
        self.btn_ml_performance.setText(QCoreApplication.translate("MainWindow", u"Model performance", None))
        self.btn_ml_prediction.setText(QCoreApplication.translate("MainWindow", u"Model prediction", None))
        self.titleRightInfo.setText("")
#if QT_CONFIG(tooltip)
        self.settingsTopBtn.setToolTip(QCoreApplication.translate("MainWindow", u"Settings", None))
#endif // QT_CONFIG(tooltip)
        self.settingsTopBtn.setText("")
#if QT_CONFIG(tooltip)
        self.minimizeAppBtn.setToolTip(QCoreApplication.translate("MainWindow", u"Minimize", None))
#endif // QT_CONFIG(tooltip)
        self.minimizeAppBtn.setText("")
#if QT_CONFIG(tooltip)
        self.maximizeRestoreAppBtn.setToolTip(QCoreApplication.translate("MainWindow", u"Maximize", None))
#endif // QT_CONFIG(tooltip)
        self.maximizeRestoreAppBtn.setText("")
#if QT_CONFIG(tooltip)
        self.closeAppBtn.setToolTip(QCoreApplication.translate("MainWindow", u"Close", None))
#endif // QT_CONFIG(tooltip)
        self.closeAppBtn.setText("")
        self.labelBoxBlenderInstalation.setText(QCoreApplication.translate("MainWindow", u"FILE BOX", None))
        self.lineEdit.setText("")
        self.lineEdit.setPlaceholderText(QCoreApplication.translate("MainWindow", u"Type here", None))
        self.pushButton.setText(QCoreApplication.translate("MainWindow", u"Open", None))
        self.labelVersion_3.setText(QCoreApplication.translate("MainWindow", u"Label description", None))
        self.checkBox.setText(QCoreApplication.translate("MainWindow", u"CheckBox", None))
        self.radioButton.setText(QCoreApplication.translate("MainWindow", u"RadioButton", None))
        self.comboBox.setItemText(0, QCoreApplication.translate("MainWindow", u"Test 1", None))
        self.comboBox.setItemText(1, QCoreApplication.translate("MainWindow", u"Test 2", None))
        self.comboBox.setItemText(2, QCoreApplication.translate("MainWindow", u"Test 3", None))

        self.commandLinkButton.setText(QCoreApplication.translate("MainWindow", u"Link Button", None))
        self.commandLinkButton.setDescription(QCoreApplication.translate("MainWindow", u"Link description", None))
        ___qtablewidgetitem = self.tableWidget.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("MainWindow", u"0", None))
        ___qtablewidgetitem1 = self.tableWidget.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("MainWindow", u"1", None))
        ___qtablewidgetitem2 = self.tableWidget.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("MainWindow", u"2", None))
        ___qtablewidgetitem3 = self.tableWidget.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("MainWindow", u"3", None))
        ___qtablewidgetitem4 = self.tableWidget.verticalHeaderItem(0)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem5 = self.tableWidget.verticalHeaderItem(1)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem6 = self.tableWidget.verticalHeaderItem(2)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem7 = self.tableWidget.verticalHeaderItem(3)
        ___qtablewidgetitem7.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem8 = self.tableWidget.verticalHeaderItem(4)
        ___qtablewidgetitem8.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem9 = self.tableWidget.verticalHeaderItem(5)
        ___qtablewidgetitem9.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem10 = self.tableWidget.verticalHeaderItem(6)
        ___qtablewidgetitem10.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem11 = self.tableWidget.verticalHeaderItem(7)
        ___qtablewidgetitem11.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem12 = self.tableWidget.verticalHeaderItem(8)
        ___qtablewidgetitem12.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem13 = self.tableWidget.verticalHeaderItem(9)
        ___qtablewidgetitem13.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem14 = self.tableWidget.verticalHeaderItem(10)
        ___qtablewidgetitem14.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem15 = self.tableWidget.verticalHeaderItem(11)
        ___qtablewidgetitem15.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem16 = self.tableWidget.verticalHeaderItem(12)
        ___qtablewidgetitem16.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem17 = self.tableWidget.verticalHeaderItem(13)
        ___qtablewidgetitem17.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem18 = self.tableWidget.verticalHeaderItem(14)
        ___qtablewidgetitem18.setText(QCoreApplication.translate("MainWindow", u"New Row", None))
        ___qtablewidgetitem19 = self.tableWidget.verticalHeaderItem(15)
        ___qtablewidgetitem19.setText(QCoreApplication.translate("MainWindow", u"New Row", None))

        __sortingEnabled = self.tableWidget.isSortingEnabled()
        self.tableWidget.setSortingEnabled(False)
        ___qtablewidgetitem20 = self.tableWidget.item(0, 0)
        ___qtablewidgetitem20.setText(QCoreApplication.translate("MainWindow", u"Test", None))
        ___qtablewidgetitem21 = self.tableWidget.item(0, 1)
        ___qtablewidgetitem21.setText(QCoreApplication.translate("MainWindow", u"Text", None))
        ___qtablewidgetitem22 = self.tableWidget.item(0, 2)
        ___qtablewidgetitem22.setText(QCoreApplication.translate("MainWindow", u"Cell", None))
        ___qtablewidgetitem23 = self.tableWidget.item(0, 3)
        ___qtablewidgetitem23.setText(QCoreApplication.translate("MainWindow", u"Line", None))
        self.tableWidget.setSortingEnabled(__sortingEnabled)

        self.label.setText(QCoreApplication.translate("MainWindow", u"NEW PAGE TEST", None))
        self.title_prepare.setText(QCoreApplication.translate("MainWindow", u"Prepare", None))
        self.subtitle_prepare.setText(QCoreApplication.translate("MainWindow", u"Choose the sensor this session works with, and plan the study it feeds.", None))
        self.tabs_prepare.setTabText(self.tabs_prepare.indexOf(self.tab_prepare_sensor), QCoreApplication.translate("MainWindow", u"Sensor configuration", None))
        self.tabs_prepare.setTabText(self.tabs_prepare.indexOf(self.tab_prepare_study), QCoreApplication.translate("MainWindow", u"Study design", None))
        self.title_process.setText(QCoreApplication.translate("MainWindow", u"Process", None))
        self.subtitle_process.setText(QCoreApplication.translate("MainWindow", u"Import and process raw sensor data", None))
        self.grp_library.setTitle(QCoreApplication.translate("MainWindow", u"Library", None))
        self.btn_change_libraries.setText(QCoreApplication.translate("MainWindow", u"Change libraries folder\u2026", None))
        self.grp_index.setTitle(QCoreApplication.translate("MainWindow", u"Index", None))
        self.grp_inventory.setTitle(QCoreApplication.translate("MainWindow", u"File inventory", None))
        ___qtablewidgetitem24 = self.table_inventory.horizontalHeaderItem(0)
        ___qtablewidgetitem24.setText(QCoreApplication.translate("MainWindow", u"#", None))
        ___qtablewidgetitem25 = self.table_inventory.horizontalHeaderItem(1)
        ___qtablewidgetitem25.setText(QCoreApplication.translate("MainWindow", u"Filename", None))
        ___qtablewidgetitem26 = self.table_inventory.horizontalHeaderItem(2)
        ___qtablewidgetitem26.setText(QCoreApplication.translate("MainWindow", u"Sensor", None))
        ___qtablewidgetitem27 = self.table_inventory.horizontalHeaderItem(3)
        ___qtablewidgetitem27.setText(QCoreApplication.translate("MainWindow", u"Date", None))
        ___qtablewidgetitem28 = self.table_inventory.horizontalHeaderItem(4)
        ___qtablewidgetitem28.setText(QCoreApplication.translate("MainWindow", u"Time", None))
        ___qtablewidgetitem29 = self.table_inventory.horizontalHeaderItem(5)
        ___qtablewidgetitem29.setText(QCoreApplication.translate("MainWindow", u"Complete", None))
        ___qtablewidgetitem30 = self.table_inventory.horizontalHeaderItem(6)
        ___qtablewidgetitem30.setText(QCoreApplication.translate("MainWindow", u"Status", None))
        self.chk_select_all.setText(QCoreApplication.translate("MainWindow", u"Select / unselect all", None))
        self.lbl_treatment.setText(QCoreApplication.translate("MainWindow", u"Treatment", None))
#if QT_CONFIG(tooltip)
        self.cmb_treatment.setToolTip(QCoreApplication.translate("MainWindow", u"Treatments planned on Prepare > Study design. Selected sensors are labelled with this treatment's conditions when they are processed.", None))
#endif // QT_CONFIG(tooltip)
        self.btn_process_selected.setText(QCoreApplication.translate("MainWindow", u"Process selected", None))
        self.grp_console.setTitle(QCoreApplication.translate("MainWindow", u"Console output", None))
        self.grp_selection_info.setTitle(QCoreApplication.translate("MainWindow", u"Selection information", None))
        self.grp_processed.setTitle(QCoreApplication.translate("MainWindow", u"Processed data", None))
        self.tabs_process.setTabText(self.tabs_process.indexOf(self.tab_raw), QCoreApplication.translate("MainWindow", u"Raw data processing", None))
        self.grp_deployment.setTitle(QCoreApplication.translate("MainWindow", u"Deployment information", None))
        self.lbl_ed_deployment_config_label.setText(QCoreApplication.translate("MainWindow", u"Configuration label:", None))
        self.ed_deployment_config_label.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. PumpWizard_configuration", None))
        self.lbl_ed_site.setText(QCoreApplication.translate("MainWindow", u"Site:", None))
        self.ed_site.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. Johnson_Lane", None))
        self.lbl_ed_deployment_id.setText(QCoreApplication.translate("MainWindow", u"Deployment ID:", None))
        self.ed_deployment_id.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. JL_2025_FFP", None))
        self.lbl_ed_pump_turbine.setText(QCoreApplication.translate("MainWindow", u"Pump/turbine model:", None))
        self.ed_pump_turbine.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. Pentair_XRW", None))
        self.lbl_ed_type.setText(QCoreApplication.translate("MainWindow", u"Pump/turbine type:", None))
        self.ed_type.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. Axial_flow", None))
        self.lbl_ed_rpm.setText(QCoreApplication.translate("MainWindow", u"Rotation per minute (RPM):", None))
        self.ed_rpm.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. 500", None))
        self.lbl_ed_head.setText(QCoreApplication.translate("MainWindow", u"Head:", None))
        self.ed_head.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. 3", None))
        self.lbl_ed_flow.setText(QCoreApplication.translate("MainWindow", u"Flow:", None))
        self.ed_flow.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. 1.32", None))
        self.lbl_ed_point_bep.setText(QCoreApplication.translate("MainWindow", u"Point of best efficiency (BEP):", None))
        self.ed_point_bep.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. 100", None))
        self.lbl_ed_treatment.setText(QCoreApplication.translate("MainWindow", u"Treatment:", None))
        self.ed_treatment.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. Scenario_1", None))
        self.lbl_ed_run.setText(QCoreApplication.translate("MainWindow", u"Run:", None))
        self.ed_run.setPlaceholderText(QCoreApplication.translate("MainWindow", u"e.g. 1", None))
        self.btn_save_deployment.setText(QCoreApplication.translate("MainWindow", u"Apply to selected sensors", None))
        self.grp_meta_inventory.setTitle(QCoreApplication.translate("MainWindow", u"Processed sensor index", None))
        ___qtablewidgetitem31 = self.table_meta.horizontalHeaderItem(0)
        ___qtablewidgetitem31.setText(QCoreApplication.translate("MainWindow", u"#", None))
        ___qtablewidgetitem32 = self.table_meta.horizontalHeaderItem(1)
        ___qtablewidgetitem32.setText(QCoreApplication.translate("MainWindow", u"Filename", None))
        ___qtablewidgetitem33 = self.table_meta.horizontalHeaderItem(2)
        ___qtablewidgetitem33.setText(QCoreApplication.translate("MainWindow", u"Sensor", None))
        ___qtablewidgetitem34 = self.table_meta.horizontalHeaderItem(3)
        ___qtablewidgetitem34.setText(QCoreApplication.translate("MainWindow", u"Date", None))
        ___qtablewidgetitem35 = self.table_meta.horizontalHeaderItem(4)
        ___qtablewidgetitem35.setText(QCoreApplication.translate("MainWindow", u"Status", None))
        self.chk_meta_select_all.setText(QCoreApplication.translate("MainWindow", u"Select / unselect all", None))
        self.btn_apply_deployment.setText(QCoreApplication.translate("MainWindow", u"Load values from selected sensor", None))
        self.grp_dash_library.setTitle(QCoreApplication.translate("MainWindow", u"Library overview", None))
        self.lbl_dash_library_value.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.lbl_dash_library_caption.setText(QCoreApplication.translate("MainWindow", u"Sensors in global index", None))
        self.lbl_dash_library_detail.setText(QCoreApplication.translate("MainWindow", u"No library selected", None))
        self.grp_dash_coverage.setTitle(QCoreApplication.translate("MainWindow", u"Deployment coverage", None))
        self.lbl_dash_coverage_value.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.lbl_dash_coverage_caption.setText(QCoreApplication.translate("MainWindow", u"Complete deployment info", None))
        self.lbl_dash_coverage_detail.setText(QCoreApplication.translate("MainWindow", u"No library selected", None))
        self.grp_dash_quality.setTitle(QCoreApplication.translate("MainWindow", u"Data quality", None))
        self.lbl_dash_quality_value.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.lbl_dash_quality_caption.setText(QCoreApplication.translate("MainWindow", u"Flagged bad_sens", None))
        self.lbl_dash_quality_detail.setText(QCoreApplication.translate("MainWindow", u"No library selected", None))
        self.grp_dash_sites.setTitle(QCoreApplication.translate("MainWindow", u"Sites and configurations", None))
        self.lbl_dash_sites_value.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.lbl_dash_sites_caption.setText(QCoreApplication.translate("MainWindow", u"Distinct sites", None))
        self.lbl_dash_sites_detail.setText(QCoreApplication.translate("MainWindow", u"No library selected", None))
        self.grp_dash_delineated.setTitle(QCoreApplication.translate("MainWindow", u"Signal processing", None))
        self.lbl_dash_delineated_value.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.lbl_dash_delineated_caption.setText(QCoreApplication.translate("MainWindow", u"Delineated signals", None))
        self.lbl_dash_delineated_detail.setText(QCoreApplication.translate("MainWindow", u"No library selected", None))
        self.grp_dash_treatments.setTitle(QCoreApplication.translate("MainWindow", u"Treatments and runs", None))
        self.lbl_dash_treatments_value.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.lbl_dash_treatments_caption.setText(QCoreApplication.translate("MainWindow", u"Distinct treatments", None))
        self.lbl_dash_treatments_detail.setText(QCoreApplication.translate("MainWindow", u"No library selected", None))
        self.tabs_process.setTabText(self.tabs_process.indexOf(self.tab_meta), QCoreApplication.translate("MainWindow", u"Metadata", None))
        self.title_validate.setText(QCoreApplication.translate("MainWindow", u"Validate & segment", None))
        self.subtitle_validate.setText(QCoreApplication.translate("MainWindow", u"Review processed signals, flag bad records and cut them into event segments.", None))
        self.grp_val_library.setTitle(QCoreApplication.translate("MainWindow", u"Library", None))
        self.btn_val_change_libraries.setText(QCoreApplication.translate("MainWindow", u"Change libraries folder\u2026", None))
        self.grp_val_files.setTitle(QCoreApplication.translate("MainWindow", u"Sensor files", None))
        self.lbl_val_progress.setText(QCoreApplication.translate("MainWindow", u"\u2014", None))
        self.btn_val_save_next.setText(QCoreApplication.translate("MainWindow", u"Save + Next", None))
        self.btn_val_reset.setText(QCoreApplication.translate("MainWindow", u"Reset current sensor", None))
        self.btn_val_jump.setText(QCoreApplication.translate("MainWindow", u"Jump to next unvalidated", None))
        self.grp_val_plot.setTitle(QCoreApplication.translate("MainWindow", u"Nadir validation", None))
        self.lbl_val_left.setText(QCoreApplication.translate("MainWindow", u"Left axis:", None))
        self.lbl_val_right.setText(QCoreApplication.translate("MainWindow", u"Right axis:", None))
        self.lbl_val_window.setText(QCoreApplication.translate("MainWindow", u"ROI window:", None))
        self.lbl_val_loading.setText("")
        self.title_dataset.setText(QCoreApplication.translate("MainWindow", u"Dataset creation", None))
        self.subtitle_dataset.setText(QCoreApplication.translate("MainWindow", u"Assemble validated segments into labelled datasets for model development.", None))
        self.grp_ds_library.setTitle(QCoreApplication.translate("MainWindow", u"Library", None))
        self.btn_ds_change_libraries.setText(QCoreApplication.translate("MainWindow", u"Change libraries folder\u2026", None))
        self.grp_ds_filter.setTitle(QCoreApplication.translate("MainWindow", u"Sensor selection", None))
        self.chk_ds_select_all.setText(QCoreApplication.translate("MainWindow", u"Select / unselect all", None))
        self.grp_ds_console.setTitle(QCoreApplication.translate("MainWindow", u"Console output", None))
        self.grp_ds_create.setTitle(QCoreApplication.translate("MainWindow", u"Create dataset", None))
        self.rb_ds_unsegmented.setText(QCoreApplication.translate("MainWindow", u"Create from unsegmented (auto nadir, 200 ms window)", None))
        self.rb_ds_segmented.setText(QCoreApplication.translate("MainWindow", u"Create from segmented (bind saved nadir windows)", None))
        self.btn_ds_create.setText(QCoreApplication.translate("MainWindow", u"Create dataset", None))
        self.btn_ds_save.setText(QCoreApplication.translate("MainWindow", u"Save dataset", None))
        self.grp_ds_annotate.setTitle(QCoreApplication.translate("MainWindow", u"Annotate dataset", None))
        self.lbl_ds_features.setText(QCoreApplication.translate("MainWindow", u"Sensor dataset:", None))
        self.ed_ds_features.setPlaceholderText(QCoreApplication.translate("MainWindow", u"no file selected", None))
        self.btn_ds_browse_features.setText(QCoreApplication.translate("MainWindow", u"Browse\u2026", None))
        self.lbl_ds_labels.setText(QCoreApplication.translate("MainWindow", u"Annotation dataset:", None))
        self.ed_ds_labels.setPlaceholderText(QCoreApplication.translate("MainWindow", u"no file selected", None))
        self.btn_ds_browse_labels.setText(QCoreApplication.translate("MainWindow", u"Browse\u2026", None))
        self.btn_ds_append.setText(QCoreApplication.translate("MainWindow", u"Append features", None))
        self.btn_ds_save_annotated.setText(QCoreApplication.translate("MainWindow", u"Save annotated dataset", None))
        self.grp_ds_figure.setTitle(QCoreApplication.translate("MainWindow", u"Annotation summary", None))
        self.title_ml_training.setText(QCoreApplication.translate("MainWindow", u"Model training", None))
        self.subtitle_ml_training.setText(QCoreApplication.translate("MainWindow", u"Train and version blade-strike models from curated sensor datasets.", None))
        self.tabs_ml_training.setTabText(self.tabs_ml_training.indexOf(self.tab_train_configure), QCoreApplication.translate("MainWindow", u"Train", None))
        self.tabs_ml_training.setTabText(self.tabs_ml_training.indexOf(self.tab_train_evaluate), QCoreApplication.translate("MainWindow", u"Evaluate", None))
        self.tabs_ml_training.setTabText(self.tabs_ml_training.indexOf(self.tab_train_deploy), QCoreApplication.translate("MainWindow", u"Deploy", None))
        self.title_ml_performance.setText(QCoreApplication.translate("MainWindow", u"Model performance", None))
        self.subtitle_ml_performance.setText(QCoreApplication.translate("MainWindow", u"Evaluate trained models: metrics, confusion matrices, ROC/PR curves and threshold analysis.", None))
        self.title_ml_prediction.setText(QCoreApplication.translate("MainWindow", u"Model prediction", None))
        self.subtitle_ml_prediction.setText(QCoreApplication.translate("MainWindow", u"Apply a deployed blade-strike model to a curated sensor dataset. Predict, inspect, report.", None))
        self.tabs_ml_prediction.setTabText(self.tabs_ml_prediction.indexOf(self.tab_ml_predict), QCoreApplication.translate("MainWindow", u"Predict", None))
        self.tabs_ml_prediction.setTabText(self.tabs_ml_prediction.indexOf(self.tab_ml_inspect), QCoreApplication.translate("MainWindow", u"Inspect", None))
        self.tabs_ml_prediction.setTabText(self.tabs_ml_prediction.indexOf(self.tab_ml_report), QCoreApplication.translate("MainWindow", u"Report", None))
        self.btn_adjustments.setText(QCoreApplication.translate("MainWindow", u"Adjustments", None))
        self.btn_about.setText(QCoreApplication.translate("MainWindow", u"About", None))
        self.btn_more.setText(QCoreApplication.translate("MainWindow", u"More", None))
        self.creditsLabel.setText(QCoreApplication.translate("MainWindow", u"StrikeWorks", None))
        self.version.setText(QCoreApplication.translate("MainWindow", u"v0.1.0", None))
    # retranslateUi

