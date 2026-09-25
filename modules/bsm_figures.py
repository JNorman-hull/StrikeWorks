# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Blade strike modelling figures - port of the old MVP app's
`bsm/plotting.py`, redrawn with the shared in-app dark theme
(`ml_figures.style_axes`/`fg_colour`/`style_legend`) instead of its own
white-on-navy styling, so these plots read as part of the same app as
every other evaluation figure rather than a second visual language.

dark=True (the default here - these only ever appear on in-app canvases,
unlike ml_figures' report-vs-canvas split) gives the themed presentation;
dark=False is available for anything exported to a light-background report.
"""
import textwrap
import warnings

from matplotlib.layout_engine import TightLayoutEngine

from .ml_figures import _PALETTE, _awaiting, fg_colour, style_axes, style_legend, _grid

CEN_COLOR = _PALETTE[3]   # green - "the model's own estimate"
OBS_COLOR = _PALETTE[0]   # blue - "what was actually observed"

# dual-species default (Model comparison's Cen bars, Predict's mortality
# vcrit sweep) - one colour per species so scaly/eel are visually
# distinguishable wherever both appear on the same figure
SPECIES_COLORS = {"scaly": CEN_COLOR, "eel": _PALETTE[4]}


def _bar_style(ax, dark, ylabel, fontsize=9):
    ax.set_ylabel(ylabel, fontsize=fontsize)
    ax.set_ylim(0, 100)
    _grid(ax, dark)
    style_axes(ax.figure, ax, dark)


def _label_bars(ax, bars, values, dark=True, fontsize=8, tops=None):
    """Prints each bar's own value (%) just above it - every BSM output
    plot shows its actual numbers now, not just a shape to eyeball. A bar
    reaching the top of the 0-100 axis gets its label just inside the bar
    instead, so it can't run into the title above."""
    fg = fg_colour(dark)
    # `tops`: where each label sits, when a bar carries an error bar - above
    # its upper whisker rather than on it
    tops = tops or [None] * len(values)
    for bar, value, top in zip(bars, values, tops):
        inside = value > 90 and top is None
        y = bar.get_height() if top is None else top
        ax.annotate(f"{value:.1f}%",
                   xy=(bar.get_x() + bar.get_width() / 2, y),
                   xytext=(0, -3 if inside else 3), textcoords="offset points",
                   ha="center", va="top" if inside else "bottom",
                   fontsize=fontsize, color="white" if inside else fg,
                   fontweight="bold" if inside else "normal", zorder=5)


SPECIES_TITLES = {"scaly": "Scaly fish", "eel": "Eel"}

# report figure sizes (cm) - the 4-panel results and the 4-panel sweeps
RESULTS_PANELS_CM = (12.0, 12.0)
SWEEP_PANELS_CM = (20.0, 16.0)


def _pco_bars(ax, res, dark, value_fs=8, ylabel_fs=9):
    fg = fg_colour(dark)
    if "Pco_obs" in res:
        values = [res["Pco_tip"] * 100, res["Pco_obs"] * 100]
        bars = ax.bar(["CEN", "Observed"], values,
                      width=0.55, color=[CEN_COLOR, OBS_COLOR], edgecolor=fg)
        ax.errorbar(1, res["Pco_obs"] * 100,
                    yerr=[[(res["Pco_obs"] - res["wilson_lo"]) * 100],
                          [(res["wilson_hi"] - res["Pco_obs"]) * 100]],
                    fmt="none", ecolor=fg, capsize=6, linewidth=1.2)
        tops = [None, res["wilson_hi"] * 100]
        ylabel = "Collision probability (%) [95% CI]"
    else:
        values = [res["Pco_tip"] * 100]
        bars = ax.bar(["CEN"], values, width=0.55,
                      color=[CEN_COLOR], edgecolor=fg)
        tops = None
        ylabel = "Collision probability (%)"
    _label_bars(ax, bars, values, dark, fontsize=value_fs, tops=tops)
    _bar_style(ax, dark, ylabel, fontsize=ylabel_fs)


def _pm_bars(ax, res, dark, value_fs=8, ylabel_fs=9):
    fg = fg_colour(dark)
    if "Pco_obs" in res:
        values = [res["Pm"] * 100, res["Pm_obs"] * 100]
        bars = ax.bar(["CEN", "Observed"], values,
                      width=0.55, color=[CEN_COLOR, OBS_COLOR], edgecolor=fg)
    else:
        values = [res["Pm"] * 100]
        bars = ax.bar(["CEN"], values, width=0.55,
                      color=[CEN_COLOR], edgecolor=fg)
    _label_bars(ax, bars, values, dark, fontsize=value_fs)
    _bar_style(ax, dark, "Mortality probability (%)", fontsize=ylabel_fs)


def draw_pco(fig, res, dark=True):
    fig.clear()
    _pco_bars(fig.add_subplot(111), res, dark)
    fig.tight_layout()


def draw_pm(fig, res, dark=True):
    fig.clear()
    _pm_bars(fig.add_subplot(111), res, dark)
    fig.tight_layout()


def _panel_letter(ax, letter, dark):
    """(a)/(b)/... top-left, above the axes - the multi-panel figures'
    own panel labels."""
    ax.text(-0.02, 1.03, f"({letter})", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9, fontweight="bold",
            color=fg_colour(dark))


def draw_results_panels(fig, results, dark=False):
    """The blade strike model's headline results as one 2x2 figure:
    (a) scaly collision, (b) scaly mortality, (c) eel collision,
    (d) eel mortality - CEN (and Observed, with its Wilson 95% CI, when
    observed counts were entered) per panel. `results`: {"scaly": res,
    "eel": res}, either may be missing (drawn as "Not calculated")."""
    fig.clear()
    fg = fg_colour(dark)
    axes = fig.subplots(2, 2)
    panels = (("scaly", "pco"), ("scaly", "pm"), ("eel", "pco"), ("eel", "pm"))
    for letter, ax, (species, kind) in zip("abcd", axes.flat, panels):
        res = (results or {}).get(species)
        what = "collision" if kind == "pco" else "mortality"
        if res is None:
            ax.set_xticks([])
            _awaiting(ax, "Not calculated")
            _bar_style(ax, dark, f"{what.capitalize()} probability (%)",
                       fontsize=8)
        elif kind == "pco":
            _pco_bars(ax, res, dark, value_fs=7, ylabel_fs=8)
        else:
            _pm_bars(ax, res, dark, value_fs=7, ylabel_fs=8)
        # letter and title as one left-aligned title, so they can't run
        # into each other however narrow the panel gets
        ax.set_title(rf"$\bf{{({letter})}}$  {SPECIES_TITLES[species]} - {what}",
                     fontsize=9, color=fg, loc="left")
        ax.tick_params(labelsize=8)
    _finish_layout(fig, dark)


def _quiet_tight_layout(fig, rect=None):
    """tight_layout, skipped while a canvas is still tiny (before it's
    first laid out on screen) and without its "cannot make Axes small
    enough" warning."""
    w, h = fig.get_size_inches() * fig.dpi
    if w < 120 or h < 100:
        return
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        fig.tight_layout(rect=rect)


class _LiveTightLayout(TightLayoutEngine):
    def execute(self, fig):
        w, h = fig.get_size_inches() * fig.dpi
        if w < 120 or h < 100:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            super().execute(fig)


def _rotate_bar_labels(fig, ax, n_bars, label_px):
    """Bar labels flat when each bar's slot is wide enough for its
    (wrapped) label, slanted when it's tighter, vertical when it's very
    narrow (the half-width mortality figure on screen) - worked out from
    the figure's actual width, so the same figure reads at report size
    and on a narrow canvas."""
    slot = fig.get_size_inches()[0] * fig.dpi * 0.8 / max(n_bars, 1)
    rotation = 0 if slot >= label_px else (30 if slot >= label_px * 0.55 else 90)
    for lab in ax.get_xticklabels():
        lab.set_rotation(rotation)
        if rotation == 30:
            lab.set_ha("right")
            lab.set_rotation_mode("anchor")


def _finish_layout(fig, dark, rect=None):
    """tight_layout once - and for an in-app (dark) canvas, keep it as the
    figure's layout engine so every resize re-lays the panels out rather
    than stretching positions computed at the figure's first size."""
    _quiet_tight_layout(fig, rect=rect)
    if dark:
        fig.set_layout_engine(_LiveTightLayout(rect=rect))


def _nice_ceiling(value):
    """Upper y limit for a mortality panel: the next 10 above the data
    (at least 10), capped at 100."""
    import math
    return float(min(100, max(10, math.ceil(value * 1.1 / 10) * 10)))


def draw_sweep_panels(fig, sweeps, dark=False, title=None):
    """Sensitivity as one 2x2 figure, one line per flow rate Q in every
    panel (viridis, the design Q drawn heavier, its design point marked):
    (a) collision probability vs shaft speed, (b) collision probability
    vs relative fish velocity, (c) mortality probability vs shaft speed,
    (d) mortality probability vs relative fish velocity. One shared
    legend underneath. `sweeps`: `bsm_model.sensitivity_sweeps()`'s dict,
    or None for the awaiting-data placeholder."""
    import matplotlib
    import numpy as np

    fig.clear()
    fg = fg_colour(dark)
    axes = fig.subplots(2, 2)
    specs = (("pco_n", "N", "Shaft speed N (rpm)", "Collision probability (%)"),
             ("pco_wf", "wf", "Relative fish velocity wf (m/s)",
              "Collision probability (%)"),
             ("pm_n", "N", "Shaft speed N (rpm)", "Mortality probability (%)"),
             ("pm_wf", "wf", "Relative fish velocity wf (m/s)",
              "Mortality probability (%)"))
    pm_top = 10.0
    if sweeps:
        pm_max = max((float(np.max(y)) for key in ("pm_n", "pm_wf")
                      for _x, y in sweeps[key].values()), default=0.0)
        pm_top = _nice_ceiling(pm_max)
    cmap = matplotlib.colormaps["viridis"]
    handles = []
    for letter, ax, (key, x_key, x_label, y_label) in zip("abcd", axes.flat,
                                                         specs):
        _grid(ax, dark)
        ax.set_xlabel(x_label, fontsize=9)
        ax.set_ylabel(y_label, fontsize=9)
        ax.set_ylim(0, 100 if key.startswith("pco") else pm_top)
        ax.tick_params(labelsize=8)
        _panel_letter(ax, letter, dark)
        if not sweeps:
            ax.set_xticks([])
            _awaiting(ax, "Run a Blade Strike Modelling calculation first")
            style_axes(fig, ax, dark)
            continue
        if x_key == "wf":
            ax.axvline(0, color=fg, linewidth=0.8, linestyle="--", alpha=0.6)
        curves = sweeps[key]
        n = max(len(curves) - 1, 1)
        design_label = sweeps.get("design_label")
        lines = []
        x_lo, x_hi = None, None
        for i, (label, (x_arr, y_arr)) in enumerate(curves.items()):
            is_design = label == design_label
            line, = ax.plot(x_arr, y_arr, color=cmap(i / n),
                            linewidth=2.0 if is_design else 1.2,
                            label=label, zorder=3 if is_design else 2)
            lines.append(line)
            x_lo = float(np.min(x_arr)) if x_lo is None else min(x_lo, float(np.min(x_arr)))
            x_hi = float(np.max(x_arr)) if x_hi is None else max(x_hi, float(np.max(x_arr)))
            if is_design:
                dx = sweeps["design"][x_key]
                ax.scatter([dx], [float(np.interp(dx, x_arr, y_arr))], s=28,
                           color=cmap(i / n), edgecolor=fg, linewidth=0.8,
                           zorder=4)
        if x_lo is not None and x_hi > x_lo:
            ax.set_xlim(x_lo, x_hi)
        handles = handles or lines
        style_axes(fig, ax, dark)
    if handles:
        leg = fig.legend(handles=handles, loc="lower center",
                         ncol=min(len(handles), 3), fontsize=8, frameon=False)
        if dark:
            for text in leg.get_texts():
                text.set_color(fg)
    if title:
        fig.suptitle(title, fontsize=9, color=fg, y=0.99)
    _finish_layout(fig, dark, rect=(0, 0.08 if handles else 0, 1,
                                    0.97 if title else 1))


def sweep_panels_title(species, params):
    """The fixed inputs every sweep panel holds constant, as a one-line
    figure title."""
    return (f"{SPECIES_TITLES.get(species, species)} - EVS-EN 18110 (2025); "
            f"Lf = {params['lf'] * 1000:g} mm, Bf = {params['bf'] * 1000:g} mm, "
            f"design Q = {params['Q']:g} m\u00b3/s, N = {params['N']:g} rpm, "
            f"wf = {params['wf']:g} m/s")


def draw_sens_wf(fig, x, y, x_fit, y_fit, span=4.0, dark=True,
                 x_label="Relative fish velocity wf (m/s)",
                 y_label="Collision probability (%)"):
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    _grid(ax, dark)
    ax.axvline(0, color=fg, linewidth=0.8, linestyle="--", alpha=0.6)
    ax.plot(x_fit, y_fit, color=CEN_COLOR, linewidth=1.5, zorder=2)
    ax.scatter(x, y, s=14, color=CEN_COLOR, edgecolor=fg,
               linewidth=0.4, zorder=3)
    ax.set_xlim(-span, span)
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlabel(x_label, fontsize=9)
    ax.set_ylabel(y_label, fontsize=9)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_sweep_lines(fig, x_label, y_label, curves, design_label=None,
                     annotation=None, dark=True, y_max=100.0):
    """Multiple sweeps on one axis, one line per key in `curves` (an
    ordered dict: label -> (x_arr, y_arr)) - the Q_LEVELS fan-out from the
    standalone Mathematical BSM scripts (`cen_2025_..._CUSTOM.py`):
    viridis-coloured lines, `design_label`'s curve drawn heavier, each
    curve labelled directly on the line (cascaded across x so labels don't
    stack), an optional corner annotation box for the fixed parameters the
    sweep held constant.
    """
    import matplotlib
    import numpy as np

    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    _grid(ax, dark)

    labels = list(curves.keys())
    cmap = matplotlib.colormaps["viridis"]
    n = max(len(labels) - 1, 1)
    all_x = np.concatenate([x for x, _ in curves.values()]) if curves else [0]
    x_min, x_max = float(np.min(all_x)), float(np.max(all_x))
    label_x = np.linspace(x_max * 0.95, x_min * 0.95, len(labels))

    for i, (label, (x_arr, y_arr)) in enumerate(curves.items()):
        color = cmap(i / n)
        lw = 2.0 if label == design_label else 1.2
        ax.plot(x_arr, y_arr, color=color, linewidth=lw, zorder=2)
        lx = label_x[i]
        ly = float(np.interp(lx, x_arr, y_arr))
        ax.text(lx, ly, str(label), color=color, fontsize=9, fontweight="bold",
               ha="center", va="center", zorder=4,
               bbox=dict(facecolor=("#1b1e24" if dark else "white"),
                        edgecolor="none", pad=1.2, alpha=0.85))

    if annotation:
        ax.text(0.02, 0.03, annotation, transform=ax.transAxes,
               ha="left", va="bottom", fontsize=7.5, color=fg, zorder=4,
               bbox=dict(facecolor=("#1b1e24" if dark else "white"),
                        edgecolor="none", alpha=0.75, pad=1.5))

    ax.set_xlabel(x_label, fontsize=9)
    ax.set_ylabel(y_label, fontsize=9)
    if y_max is not None:
        ax.set_ylim(0, y_max)
    ax.tick_params(labelsize=8)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_vcrit_sweep(fig, series, dark=True, title=None):
    """Mortality probability vs critical velocity - dual-species default:
    one line per species, each with its own highlighted point marking
    what that species' own regression would derive by itself, so each
    sweep is read against its actual default rather than an arbitrary
    baseline.

    `series`: list of (species_label, vcrit_vals, pm_vals, default_vcrit,
    default_pm) - a species whose `vcrit_vals` is empty/None is skipped;
    every series empty (or `series` itself empty) draws the themed
    awaiting-data placeholder instead of a blank white canvas - the same
    idiom `ml_figures.draw_strike_rate`/`draw_region` use before a run
    exists. `title` - which treatment's pump condition this nominally
    represents (Predict's own treatment picker, purely a label - BSM
    itself has no per-treatment input), shown even on the placeholder so
    "no treatment selected" is visible before a BSM run exists too.
    """
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    _grid(ax, dark)
    if title:
        ax.set_title(title, fontsize=9, color=fg)
    ax.set_xlabel("Critical velocity vcrit (m/s)", fontsize=9)
    ax.set_ylabel("Mortality probability (%)", fontsize=9)
    ax.set_ylim(0, 100)
    usable = [s for s in series if s[1] is not None and len(s[1])]
    if not usable:
        ax.set_xticks([])
        _awaiting(ax, "Run a Blade Strike Modelling calculation first")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    for label, vcrit_vals, pm_vals, default_v, default_pm in usable:
        color = SPECIES_COLORS.get(label, CEN_COLOR)
        ax.plot(vcrit_vals, pm_vals, color=color, linewidth=1.5, zorder=2,
               label=f"{label} default ({default_v:.2f} m/s)")
        ax.scatter([default_v], [default_pm], s=50, color=color,
                  edgecolor=fg, linewidth=0.8, zorder=4)
        ax.annotate(f"{default_pm:.1f}%", xy=(default_v, default_pm),
                   xytext=(6, 6), textcoords="offset points",
                   fontsize=8, color=color, fontweight="bold", zorder=5)
    style_legend(ax.legend(loc="upper right", fontsize=8), dark)
    ax.tick_params(labelsize=8)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_comparison_bars(fig, cen_values, comparisons, dark=True,
                         ylabel="Strike / collision probability (%)",
                         title="Model comparison"):
    """The mathematical (Cen) estimate against one bar per comparison -
    each treatment's data-driven strike rate, plus optional manually
    entered comparisons - the "BSM vs predicted" figure on Model
    comparison. Dual-species default: one Cen bar per species with a
    result, each in that species' own colour.

    `cen_values`: {species_label: value_pct_or_None}. `comparisons`: list
    of (label, value_pct, ci_lo, ci_hi) - ci_lo/ci_hi may be None for a
    bar with no confidence interval.

    No Cen value and no comparisons draws the themed awaiting-data
    placeholder instead of a blank white canvas - the same idiom
    `ml_figures.draw_strike_rate`/`draw_region` use before a run exists.
    """
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    cen_items = [(species, v) for species, v in (cen_values or {}).items()
                if v is not None]
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", color=fg)
    if not cen_items and not comparisons:
        ax.set_xticks([])
        _awaiting(ax, "Run a Blade Strike Modelling calculation first")
        _bar_style(ax, dark, ylabel)
        _finish_layout(fig, dark)
        return
    labels = [f"Cen ({sp})" for sp, _ in cen_items] + [c[0] for c in comparisons]
    heights = [v for _, v in cen_items] + [c[1] for c in comparisons]
    # keys are the page's own labels ("Blade strike model - eel") - the
    # species is their last word
    colors = ([SPECIES_COLORS.get(str(sp).split()[-1].lower(), CEN_COLOR)
               for sp, _ in cen_items]
              + [OBS_COLOR] * len(comparisons))
    # long labels ("Cen (Blade strike model - scaly)") wrapped onto a few
    # lines so neighbouring bars' labels don't run into each other when the
    # figure isn't wide; positions are numeric so duplicate labels still
    # get their own bar
    x = list(range(len(labels)))
    bars = ax.bar(x, heights, width=0.55, color=colors, edgecolor=fg)
    ax.set_xticks(x)
    ax.set_xticklabels([textwrap.fill(str(lab), 18) for lab in labels])
    for i, (_label, value, lo, hi) in enumerate(comparisons, start=len(cen_items)):
        if lo is not None and hi is not None:
            ax.errorbar(i, value, yerr=[[max(0.0, value - lo)],
                                        [max(0.0, hi - value)]],
                       fmt="none", ecolor=fg, capsize=4, linewidth=1.0)
    tops = [None] * len(cen_items) + [c[3] for c in comparisons]
    _label_bars(ax, bars, heights, dark, tops=tops)
    ax.tick_params(axis="x", labelsize=8)
    _rotate_bar_labels(fig, ax, len(labels), label_px=110)
    _bar_style(ax, dark, ylabel)
    _finish_layout(fig, dark)


def draw_mortality_bars(fig, items, dark=True, title="Mortality",
                        ylabel="Mortality probability (%)"):
    """Model comparison's mortality figure - the Blade Strike Model's own
    mortality per species against the model-projected mortality (the
    current model's predicted strike rate put through each species' BSM
    injury model) and any video-observed mortality.

    `items`: [(label, value_pct, ci_lo, ci_hi, kind)] - kind "scaly"/"eel"
    for a BSM bar (that species' colour), anything else a data-driven bar;
    ci_lo/ci_hi may be None. Same look as `draw_comparison_bars`; the y
    axis tops out just above the tallest bar/whisker (mortality is usually
    far below 100%) rather than always at 100."""
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", color=fg)
    if not items:
        ax.set_xticks([])
        _awaiting(ax, "Run a Blade Strike Modelling calculation first")
        _bar_style(ax, dark, ylabel)
        _finish_layout(fig, dark)
        return
    x = list(range(len(items)))
    heights = [it[1] for it in items]
    colors = [SPECIES_COLORS.get(it[4], OBS_COLOR) for it in items]
    bars = ax.bar(x, heights, width=0.55, color=colors, edgecolor=fg)
    ax.set_xticks(x)
    ax.set_xticklabels([textwrap.fill(str(it[0]), 14) for it in items])
    tops = []
    for i, (_label, value, lo, hi, _kind) in enumerate(items):
        if lo is not None and hi is not None:
            ax.errorbar(i, value, yerr=[[max(0.0, value - lo)],
                                        [max(0.0, hi - value)]],
                        fmt="none", ecolor=fg, capsize=4, linewidth=1.0)
            tops.append(hi)
        else:
            tops.append(None)
    _label_bars(ax, bars, heights, dark, tops=tops)
    ax.tick_params(axis="x", labelsize=7)
    _rotate_bar_labels(fig, ax, len(items), label_px=85)
    _bar_style(ax, dark, ylabel)
    peak = max([h for h in heights] + [t for t in tops if t is not None])
    ax.set_ylim(0, _nice_ceiling(peak * 1.12))
    _finish_layout(fig, dark)
