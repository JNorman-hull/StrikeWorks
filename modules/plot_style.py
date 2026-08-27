# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Shared styling and static-image export for every live pyqtgraph plot.

Exactly three live (pyqtgraph, as opposed to the matplotlib report figures)
plots exist app-wide: Sensor processing > Segmentation (`page_validate.py`),
Validate and annotate > Annotate (`page_annotate.py`), and Model prediction
> Inspect (`ml_tab_inspect.py`). They already share one construction
pattern (`pg.PlotWidget(viewBox=_NavViewBox())`, an optional right-axis
ViewBox for a second channel) - this module is the "same settings
everywhere" piece from ROADMAP.md Chunk 5 task 2: consistent margins on
every side, and one PNG(300dpi)/SVG export flow, kept in one place so a
future style change lands on all three plots at once rather than three
separately-maintained copies.

Margins
-------
pyqtgraph only reserves outer space on a side that has a *visible* axis -
left/bottom always do (ticks, labels), but with no top axis and the right
axis hidden until a second channel is chosen, a curve can end up flush
against the plot's top and right edges. `reserve_top_margin` and
`set_right_axis_active` fix this by keeping the right axis always shown
(blank when unused, real values when a second channel is plotted) instead
of the hideAxis()/showAxis() toggle each page used to do directly, and by
reserving a matching blank strip at the top permanently.

Export
------
The live plots stay themed for the dark UI; export re-renders the
currently visible window with matplotlib for a fixed, print-style look
regardless of on-screen colours: white background, black axes, the left
(primary) channel drawn black, the right (secondary) channel drawn red -
mirrors the app's own convention of a light primary trace against a red
secondary one. `add_export_button` wires a small toolbar button with a
PNG (300 dpi) / SVG menu; the caller supplies `get_export_data()`, called
at click time, returning None if there is nothing to export yet.
"""
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QMenu, QToolButton,
)

CM_PER_INCH = 2.54
DEFAULT_WIDTH_CM = 16.0
DEFAULT_HEIGHT_CM = 10.0

EXPORT_BG = "white"
EXPORT_AXIS_COLOR = "black"
EXPORT_LEFT_COLOR = "black"     # primary (left-axis) channel, e.g. pressure
EXPORT_RIGHT_COLOR = "red"      # secondary (right-axis) channel, e.g. higacc


# ── margins ──────────────────────────────────────────────────────────────────
def reserve_top_margin(plot_item):
    """Blank top axis, shown once at setup - no page ever plots on it."""
    plot_item.showAxis("top")
    ax = plot_item.getAxis("top")
    ax.setStyle(showValues=False)
    ax.setPen(None)
    ax.setLabel("")


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
                         title=None):
    """`series`: [(label, x_arr, y_arr, color, axis)], axis 'left'/'right'.

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

    if ax_right is not None:
        for spine in ax_right.spines.values():
            spine.set_color(EXPORT_AXIS_COLOR)
        ax_right.tick_params(colors=EXPORT_RIGHT_COLOR)
        ax_right.set_ylabel(right_label or "", color=EXPORT_RIGHT_COLOR)

    fig.tight_layout()
    return fig


def build_export_data(time, left_label, left_y, right_label, right_y, xlim,
                      x_label="Time (s)"):
    """The common shape every page's `get_export_data()` needs: one left
    (primary) channel and an optional right (secondary) one, coloured per
    the EXPORT_LEFT_COLOR/EXPORT_RIGHT_COLOR convention above. None if
    there's nothing plotted yet."""
    if time is None or left_y is None:
        return None
    series = [(left_label, time, left_y, EXPORT_LEFT_COLOR, "left")]
    right_label_out = None
    if right_y is not None:
        series.append((right_label, time, right_y, EXPORT_RIGHT_COLOR, "right"))
        right_label_out = right_label
    return {
        "series": series, "x_label": x_label, "y_label": left_label,
        "right_label": right_label_out, "xlim": xlim,
    }


def add_export_button(toolbar_layout, get_export_data, parent, file_stub="plot"):
    """Attach a small "Export ▾" button (PNG 300dpi / SVG) to a toolbar
    layout. `get_export_data()` is called at click time and must return a
    dict with `series`/`x_label`/`y_label` (see `render_export_figure`),
    or None/empty if there is nothing to export yet."""
    btn = QToolButton()
    btn.setText("Export ▾")
    btn.setToolTip("Save the currently plotted signal as an image")
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(btn)
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
            data.get("xlim"), data.get("title"))
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
