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
from .ml_figures import _PALETTE, _awaiting, fg_colour, style_axes, style_legend, _grid

CEN_COLOR = _PALETTE[3]   # green - "the model's own estimate"
OBS_COLOR = _PALETTE[0]   # blue - "what was actually observed"

# dual-species default (Model comparison's Cen bars, Predict's mortality
# vcrit sweep) - one colour per species so scaly/eel are visually
# distinguishable wherever both appear on the same figure
SPECIES_COLORS = {"scaly": CEN_COLOR, "eel": _PALETTE[4]}


def _bar_style(ax, dark, ylabel):
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_ylim(0, 100)
    _grid(ax, dark)
    style_axes(ax.figure, ax, dark)


def _label_bars(ax, bars, values, dark=True):
    """Prints each bar's own value (%) just above it - every BSM output
    plot shows its actual numbers now, not just a shape to eyeball."""
    fg = fg_colour(dark)
    for bar, value in zip(bars, values):
        ax.annotate(f"{value:.1f}%",
                   xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                   xytext=(0, 3), textcoords="offset points",
                   ha="center", va="bottom", fontsize=8, color=fg, zorder=5)


def draw_pco(fig, res, dark=True):
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    if "Pco_obs" in res:
        values = [res["Pco_tip"] * 100, res["Pco_obs"] * 100]
        bars = ax.bar(["CEN", "Observed"], values,
                      width=0.55, color=[CEN_COLOR, OBS_COLOR], edgecolor=fg)
        ax.errorbar(1, res["Pco_obs"] * 100,
                    yerr=[[(res["Pco_obs"] - res["wilson_lo"]) * 100],
                          [(res["wilson_hi"] - res["Pco_obs"]) * 100]],
                    fmt="none", ecolor=fg, capsize=6, linewidth=1.2)
        _label_bars(ax, bars, values, dark)
        _bar_style(ax, dark, "Collision probability (%) [95% CI]")
    else:
        values = [res["Pco_tip"] * 100]
        bars = ax.bar(["CEN"], values, width=0.55,
                      color=[CEN_COLOR], edgecolor=fg)
        _label_bars(ax, bars, values, dark)
        _bar_style(ax, dark, "Collision probability (%)")
    fig.tight_layout()


def draw_pm(fig, res, dark=True):
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    if "Pco_obs" in res:
        values = [res["Pm"] * 100, res["Pm_obs"] * 100]
        bars = ax.bar(["CEN", "Observed"], values,
                      width=0.55, color=[CEN_COLOR, OBS_COLOR], edgecolor=fg)
    else:
        values = [res["Pm"] * 100]
        bars = ax.bar(["CEN"], values, width=0.55,
                      color=[CEN_COLOR], edgecolor=fg)
    _label_bars(ax, bars, values, dark)
    _bar_style(ax, dark, "Mortality probability (%)")
    fig.tight_layout()


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
                         ylabel="Strike / collision probability (%)"):
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
    if not cen_items and not comparisons:
        ax.set_xticks([])
        _awaiting(ax, "Run a Blade Strike Modelling calculation first")
        _bar_style(ax, dark, ylabel)
        fig.tight_layout()
        return
    labels = [f"Cen ({sp})" for sp, _ in cen_items] + [c[0] for c in comparisons]
    heights = [v for _, v in cen_items] + [c[1] for c in comparisons]
    colors = ([SPECIES_COLORS.get(sp, CEN_COLOR) for sp, _ in cen_items]
              + [OBS_COLOR] * len(comparisons))
    bars = ax.bar(labels, heights, width=0.55, color=colors, edgecolor=fg)
    for i, (_label, value, lo, hi) in enumerate(comparisons, start=len(cen_items)):
        if lo is not None and hi is not None:
            ax.errorbar(i, value, yerr=[[max(0.0, value - lo)],
                                        [max(0.0, hi - value)]],
                       fmt="none", ecolor=fg, capsize=4, linewidth=1.0)
    _label_bars(ax, bars, heights, dark)
    ax.tick_params(axis="x", labelsize=8,
                   rotation=30 if len(labels) > 3 else 0)
    _bar_style(ax, dark, ylabel)
    fig.tight_layout()
