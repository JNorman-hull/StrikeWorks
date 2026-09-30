# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# GUI built on the PyDracula template (MIT licence) - credit and link
# available under Settings > About. See LICENSE.
#
# ///////////////////////////////////////////////////////////////
"""The window frame's behaviour: custom title bar (move, maximise,
resize grips), the sliding sidebar and side panels, and the selected-menu
highlight. Every function takes the main window as its first argument."""
from PySide6.QtCore import (
    QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QSizeGrip

from widgets import CustomGrip

from .theme import set_flag
from .ui_config import UIConfig


class UIFunctions:
    # ── maximise / restore ──────────────────────────────────────────────────
    def maximize_restore(self):
        grips = (self.left_grip, self.right_grip, self.top_grip, self.bottom_grip)
        if not getattr(self, "_maximized", False):
            self.showMaximized()
            self._maximized = True
            self.ui.appMargins.setContentsMargins(0, 0, 0, 0)
            self.ui.maximizeRestoreAppBtn.setToolTip("Restore")
            self.ui.maximizeRestoreAppBtn.setIcon(
                QIcon(":/icons/images/icons/icon_restore.png"))
            self.ui.frame_size_grip.hide()
            for grip in grips:
                grip.hide()
        else:
            self._maximized = False
            self.showNormal()
            self.resize(self.width() + 1, self.height() + 1)
            self.ui.appMargins.setContentsMargins(10, 10, 10, 10)
            self.ui.maximizeRestoreAppBtn.setToolTip("Maximize")
            self.ui.maximizeRestoreAppBtn.setIcon(
                QIcon(":/icons/images/icons/icon_maximize.png"))
            self.ui.frame_size_grip.show()
            for grip in grips:
                grip.show()

    # ── sidebar ─────────────────────────────────────────────────────────────
    def toggleMenu(self, enable):
        """Expand/collapse the sidebar. Both its minimum and maximum width
        are animated so it is pinned to an exact width either way - with
        only the minimum animated, an opening side panel could squeeze it."""
        if enable:
            width = self.ui.leftMenuBg.width()
            target = (UIConfig.MENU_WIDTH if width == UIConfig.MENU_COLLAPSED_WIDTH
                      else UIConfig.MENU_COLLAPSED_WIDTH)
            UIFunctions.animate_menu_width(self, width, target)

    def animate_menu_width(self, start, end):
        self.menu_group = QParallelAnimationGroup()
        for prop in (b"minimumWidth", b"maximumWidth"):
            anim = QPropertyAnimation(self.ui.leftMenuBg, prop)
            anim.setDuration(UIConfig.TIME_ANIMATION)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.InOutQuart)
            self.menu_group.addAnimation(anim)
        self.menu_group.start()

    # ── side panels ─────────────────────────────────────────────────────────
    def toggleLeftBox(self, enable):
        """Open/close the section panel; the section's top button
        (`self._panel_btn`) carries the "owns the panel" highlight."""
        if not enable:
            return
        width = self.ui.extraLeftBox.width()
        width_right = self.ui.extraRightBox.width()
        btn = getattr(self, "_panel_btn", None) or self.ui.btn_sensor
        set_flag(btn, "boxOwner", width == 0)
        if width == 0 and width_right != 0:
            set_flag(self.ui.settingsTopBtn, "boxOwner", False)
        UIFunctions.start_box_animation(self, width, width_right, "left")

    def toggleRightBox(self, enable):
        if not enable:
            return
        width = self.ui.extraRightBox.width()
        width_left = self.ui.extraLeftBox.width()
        set_flag(self.ui.settingsTopBtn, "boxOwner", width == 0)
        if width == 0 and width_left != 0:
            panel_btn = getattr(self, "_panel_btn", None) or self.ui.btn_sensor
            set_flag(panel_btn, "boxOwner", False)
        UIFunctions.start_box_animation(self, width_left, width, "right")

    def start_box_animation(self, left_box_width, right_box_width, direction):
        left_width = (UIConfig.LEFT_BOX_WIDTH
                      if left_box_width == 0 and direction == "left" else 0)
        right_width = (UIConfig.RIGHT_BOX_WIDTH
                       if right_box_width == 0 and direction == "right" else 0)
        self.group = QParallelAnimationGroup()
        for box, start, end in ((self.ui.extraLeftBox, left_box_width, left_width),
                                (self.ui.extraRightBox, right_box_width, right_width)):
            anim = QPropertyAnimation(box, b"minimumWidth")
            anim.setDuration(UIConfig.TIME_ANIMATION)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.InOutQuart)
            self.group.addAnimation(anim)
        self.group.start()

    # ── selected-menu highlight (the "selected" property, app.qss) ─────────
    def resetStyle(self, keep):
        """Clear the highlight from every sidebar button but `keep`."""
        for w in self.ui.topMenu.findChildren(QPushButton):
            if w.objectName() != keep:
                set_flag(w, "selected", False)

    def resetPanelStyle(self, keep):
        """Clear the highlight from every section-panel button but `keep`."""
        for w in self.ui.extraTopMenu.findChildren(QPushButton):
            if w.objectName() != keep:
                set_flag(w, "selected", False)

    # ── window frame set-up ─────────────────────────────────────────────────
    def uiDefinitions(self):
        def double_click_maximize(event):
            if event.type() == QEvent.MouseButtonDblClick:
                QTimer.singleShot(250, lambda: UIFunctions.maximize_restore(self))
        self.ui.titleRightInfo.mouseDoubleClickEvent = double_click_maximize

        if UIConfig.ENABLE_CUSTOM_TITLE_BAR:
            # OR'd onto the existing flags: FramelessWindowHint alone drops
            # the Qt.Window type, and Windows then gives the window no
            # taskbar button
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)

            def move_window(event):
                if getattr(self, "_maximized", False):
                    UIFunctions.maximize_restore(self)
                if event.buttons() == Qt.LeftButton:
                    self.move(self.pos() + event.globalPos() - self.dragPos)
                    self.dragPos = event.globalPos()
                    event.accept()
            self.ui.titleRightInfo.mouseMoveEvent = move_window

            self.left_grip = CustomGrip(self, Qt.LeftEdge, True)
            self.right_grip = CustomGrip(self, Qt.RightEdge, True)
            self.top_grip = CustomGrip(self, Qt.TopEdge, True)
            self.bottom_grip = CustomGrip(self, Qt.BottomEdge, True)
        else:
            self.ui.appMargins.setContentsMargins(0, 0, 0, 0)
            self.ui.minimizeAppBtn.hide()
            self.ui.maximizeRestoreAppBtn.hide()
            self.ui.closeAppBtn.hide()
            self.ui.frame_size_grip.hide()

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(17)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(0)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.ui.bgApp.setGraphicsEffect(self.shadow)

        self.sizegrip = QSizeGrip(self.ui.frame_size_grip)
        self.sizegrip.setStyleSheet("width: 20px; height: 20px; margin 0px; padding: 0px;")

        self.ui.minimizeAppBtn.clicked.connect(lambda: self.showMinimized())
        self.ui.maximizeRestoreAppBtn.clicked.connect(
            lambda: UIFunctions.maximize_restore(self))
        self.ui.closeAppBtn.clicked.connect(lambda: self.close())

    def resize_grips(self):
        if UIConfig.ENABLE_CUSTOM_TITLE_BAR:
            self.left_grip.setGeometry(0, 10, 10, self.height())
            self.right_grip.setGeometry(self.width() - 10, 10, 10, self.height())
            self.top_grip.setGeometry(0, 0, self.width(), 10)
            self.bottom_grip.setGeometry(0, self.height() - 10, self.width(), 10)
