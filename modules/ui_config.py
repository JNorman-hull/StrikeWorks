# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# GUI built on the PyDracula template (MIT licence) - credit and link
# available under Settings > About. See LICENSE.
#
# ///////////////////////////////////////////////////////////////
"""Window-frame look: sidebar and side-panel widths, animation time, and
the highlight styles of the selected menu buttons."""


class UIConfig:
    ENABLE_CUSTOM_TITLE_BAR = True
    MENU_WIDTH = 240
    MENU_COLLAPSED_WIDTH = 60      # the icon strip
    LEFT_BOX_WIDTH = 240
    RIGHT_BOX_WIDTH = 240
    TIME_ANIMATION = 500

    # the button that owns the open left / right panel
    BTN_LEFT_BOX_COLOR = "background-color: rgb(44, 49, 58);"
    BTN_RIGHT_BOX_COLOR = "background-color: #ff79c6;"

    # the selected menu button
    MENU_SELECTED_STYLESHEET = """
    border-left: 22px solid qlineargradient(spread:pad, x1:0.034, y1:0, x2:0.216, y2:0, stop:0.499 rgba(255, 121, 198, 255), stop:0.5 rgba(85, 170, 255, 0));
    background-color: rgb(40, 44, 52);
    """
