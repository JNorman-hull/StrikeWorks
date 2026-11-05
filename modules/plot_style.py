# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared styling and static-image export for the live pyqtgraph plots
(Annotate, Export animations, Misclassification analysis, Model
prediction > Inspect, Segmentation).

Margins
-------
pyqtgraph only reserves space on a side with a *visible* axis, so with no
top axis and the right axis hidden a curve can sit flush against the top
and right edges. `reserve_top_margin` and `set_right_axis_active` keep the
right axis always shown (blank until a second channel is plotted) and
reserve a matching blank strip at the top.

Export
------
Export redraws what the plot shows - its time window and both axes' y
ranges, as the user has zoomed them - with matplotlib in a print style:
white background, black axes, the left channel black and the right
channel red.
`add_export_button` adds a toolbar button with PNG (300 dpi) / SVG; the
caller supplies `get_export_data()`, which returns None when there is
nothing to export yet.
"""
import numpy as np

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QToolButton,
)

from .layout import popup_menu

CM_PER_INCH = 2.54
DEFAULT_WIDTH_CM = 16.0
DEFAULT_HEIGHT_CM = 10.0

EXPORT_BG = "white"
EXPORT_AXIS_COLOR = "black"
EXPORT_LEFT_COLOR = "black"     # primary (left-axis) channel, e.g. pressure
EXPORT_RIGHT_COLOR = "red"      # secondary (right-axis) channel, e.g. higacc


# ── margins ──────────────────────────────────────────────────────────────────
# room above the plot for the side axes' top value ("1.0"), drawn centred on
# its tick - half of it otherwise falls outside the plot and is cut off
TOP_MARGIN_PX = 12


def reserve_top_margin(plot_item):
    """Blank top axis, shown once at setup - no page ever plots on it - a
    fixed TOP_MARGIN_PX tall."""
    plot_item.showAxis("top")
    ax = plot_item.getAxis("top")
    ax.setStyle(showValues=False)
    ax.setPen(None)
    ax.setLabel("")
    ax.setHeight(TOP_MARGIN_PX)


def set_right_axis_active(plot_item, active):
    """Toggle the right axis's *values*, not its presence - the margin it
    reserves stays whether or not a second channel is currently plotted,
    so the plot's right edge never presses flush against the widget. The
    caller still sets the label itself (`plot_item.setLabel("right", ...)`)
    when active, matching how the left/bottom labels are already set."""
    plot_item.showAxis("right")
    ax = plot_item.getAxis("right")
    ax.setStyle(showValues=active)
    ax.setPen(pg_default_pen() if active else None)
    if not active:
        plot_item.setLabel("right", "")


def pg_default_pen():
    import pyqtgraph as pg
    return pg.mkPen(pg.getConfigOption("foreground"))


# ── export ───────────────────────────────────────────────────────────────────
class _ExportSizeDialog(QDialog):
    """Width/height in cm for a static plot export."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export plot image")
        form = QFormLayout(self)

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(1.0, 100.0)
        self.spin_w.setValue(DEFAULT_WIDTH_CM)
        self.spin_w.setSuffix(" cm")
        form.addRow("Width", self.spin_w)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(1.0, 100.0)
        self.spin_h.setValue(DEFAULT_HEIGHT_CM)
        self.spin_h.setSuffix(" cm")
        form.addRow("Height", self.spin_h)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def size_cm(self):
        return self.spin_w.value(), self.spin_h.value()


def render_export_figure(width_cm, height_cm, dpi, series, x_label,
                         y_label, right_label=None, xlim=None,
                         title=None, ylim=None, right_ylim=None):
    """`series`: [(label, x_arr, y_arr, color, axis)], axis 'left'/'right';
    `xlim`/`ylim`/`right_ylim` the axes' ranges (None: fitted to the data).

    Returns a matplotlib Figure styled for static export (white
    background, black axes) - not attached to any Qt widget, ready for
    `fig.savefig(path, dpi=dpi, facecolor="white")`.
    """
    w_in = width_cm / CM_PER_INCH
    h_in = height_cm / CM_PER_INCH
    fig = Figure(figsize=(w_in, h_in), dpi=dpi, facecolor=EXPORT_BG)
    FigureCanvasAgg(fig)
    ax_left = fig.add_subplot(111)
    ax_left.set_facecolor(EXPORT_BG)
    ax_right = None

    for label, xs, ys, color, axis in series:
        target = ax_left
        if axis == "right":
            if ax_right is None:
                ax_right = ax_left.twinx()
                ax_right.set_facecolor(EXPORT_BG)
            target = ax_right
        target.plot(xs, ys, color=color, linewidth=1, label=label)

    for spine in ax_left.spines.values():
        spine.set_color(EXPORT_AXIS_COLOR)
    ax_left.tick_params(colors=EXPORT_AXIS_COLOR)
    ax_left.xaxis.label.set_color(EXPORT_AXIS_COLOR)
    ax_left.set_xlabel(x_label)
    ax_left.set_ylabel(y_label, color=EXPORT_LEFT_COLOR)
    if title:
        ax_left.set_title(title, color=EXPORT_AXIS_COLOR)
    if xlim:
        ax_left.set_xlim(*xlim)
    if ylim:
        ax_left.set_ylim(*ylim)

    if ax_right is not None:
        for spine in ax_right.spines.values():
            spine.set_color(EXPORT_AXIS_COLOR)
        ax_right.tick_params(colors=EXPORT_RIGHT_COLOR)
        ax_right.set_ylabel(right_label or "", color=EXPORT_RIGHT_COLOR)
        if right_ylim:
            ax_right.set_ylim(*right_ylim)

    fig.tight_layout()
    return fig


def build_export_data(time, left_label, left_y, right_label, right_y,
                      plot_widget, right_view=None, x_label="Time (s)"):
    """The common shape every page's `get_export_data()` needs: one left
    (primary) channel and an optional right (secondary) one, coloured per
    the EXPORT_LEFT_COLOR/EXPORT_RIGHT_COLOR convention above, over the
    window `plot_widget` shows - its time range, its y range and, with a
    right channel, the y range of `right_view` (the ViewBox the right axis
    is linked to). Only the samples in that window are kept (one either
    side, so the lines reach the edges). None if there's nothing plotted
    yet."""
    if time is None or left_y is None:
        return None
    (x0, x1), ylim = plot_widget.plotItem.vb.viewRange()
    time = np.asarray(time, dtype=float)
    window = slice(None)
    if len(time) > 1 and np.all(np.diff(time) >= 0):
        lo = max(0, int(np.searchsorted(time, x0, "left")) - 1)
        hi = min(len(time), int(np.searchsorted(time, x1, "right")) + 1)
        if hi - lo >= 2:
            window = slice(lo, hi)
    t = time[window]
    series = [(left_label, t, np.asarray(left_y)[window],
               EXPORT_LEFT_COLOR, "left")]
    right_label_out = right_ylim = None
    if right_y is not None:
        series.append((right_label, t, np.asarray(right_y)[window],
                       EXPORT_RIGHT_COLOR, "right"))
        right_label_out = right_label
        if right_view is not None:
            right_ylim = tuple(right_view.viewRange()[1])
    return {
        "series": series, "x_label": x_label, "y_label": left_label,
        "right_label": right_label_out, "xlim": (x0, x1),
        "ylim": tuple(ylim), "right_ylim": right_ylim,
    }


def add_export_button(toolbar_layout, get_export_data, parent, file_stub="plot"):
    """Attach a small "Export ▾" button (PNG 300dpi / SVG) to a toolbar
    layout. `get_export_data()` is called at click time and must return a
    dict with `series`/`x_label`/`y_label` (see `render_export_figure`),
    or None/empty if there is nothing to export yet."""
    btn = QToolButton()
    btn.setText("Export ▾")
    btn.setToolTip("Save the plot as an image, zoomed as it is now")
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = popup_menu()
    btn.export_menu = menu       # (the button doesn't keep it)
    act_png = menu.addAction("Export as PNG (300 dpi)…")
    act_svg = menu.addAction("Export as SVG…")
    btn.setMenu(menu)
    toolbar_layout.addWidget(btn)

    def _export(fmt):
        data = get_export_data()
        if not data or not data.get("series"):
            return
        dlg = _ExportSizeDialog(parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        w_cm, h_cm = dlg.size_cm()
        dpi = 300 if fmt == "png" else 100
        fig = render_export_figure(
            w_cm, h_cm, dpi, data["series"], data.get("x_label", ""),
            data.get("y_label", ""), data.get("right_label"),
            data.get("xlim"), data.get("title"), data.get("ylim"),
            data.get("right_ylim"))
        ext = "png" if fmt == "png" else "svg"
        path, _ = QFileDialog.getSaveFileName(
            parent, "Export plot image", f"{file_stub}.{ext}",
            f"{ext.upper()} files (*.{ext})")
        if not path:
            return
        fig.savefig(path, dpi=dpi, facecolor=EXPORT_BG)

    act_png.triggered.connect(lambda: _export("png"))
    act_svg.triggered.connect(lambda: _export("svg"))
    return btn
