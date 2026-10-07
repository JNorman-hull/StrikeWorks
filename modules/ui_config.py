# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# GUI built on the PyDracula template (MIT licence) - credit and link
# available under Settings > About. See LICENSE.
#
# ///////////////////////////////////////////////////////////////
"""Window-frame sizes: sidebar and side-panel widths, animation time.
(Colours are the theme's - modules/theme.py.)"""


class UIConfig:
    # False: the standard Windows title bar and frame (move, snap,
    # maximise, resize as any Windows app). True: the template's own
    # frameless title bar
    ENABLE_CUSTOM_TITLE_BAR = False
    MENU_WIDTH = 240
    MENU_COLLAPSED_WIDTH = 60      # the icon strip
    LEFT_BOX_WIDTH = 240
    RIGHT_BOX_WIDTH = 240
    TIME_ANIMATION = 500
