# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Prediction figures, drawn onto any matplotlib Figure. Two presentations:

  dark=True   the on-screen look, in the theme's canvas colours (dark for
              the StrikeWorks theme, white for the University of Hull
              one). Empty figures still draw their expected axes (labels,
              limits, grid) so the panels read as live plots awaiting data.
  dark=False  publication styling on white, for every exported figure.

Both use the theme's figure palette.
"""
import numpy as np

from . import theme

_BLUES   = ["#4a86c8", "#2e5d9f", "#6fa8dc", "#1e3a5f", "#9fc5e8"]
_PALETTE = list(theme.P["figure_palette"])
_MUTED   = "#94a3b8"

# the on-screen look (dark=True)
SCREEN_BG   = theme.P["screen_bg"]
SCREEN_AX   = theme.P["screen_axes"]
SCREEN_FG   = theme.P["screen_fg"]
SCREEN_GRID = theme.P["screen_grid"]


def fg_colour(dark):
    return SCREEN_FG if dark else "black"


def style_axes(fig, ax, dark):
    """Give a figure/axes pair the on-screen look."""
    if not dark:
        return
    fig.patch.set_facecolor(SCREEN_BG)
    ax.set_facecolor(SCREEN_AX)
    for spine in ax.spines.values():
        spine.set_color(SCREEN_GRID)
    ax.tick_params(colors=SCREEN_FG, labelcolor=SCREEN_FG)
    ax.xaxis.label.set_color(SCREEN_FG)
    ax.yaxis.label.set_color(SCREEN_FG)
    ax.title.set_color(SCREEN_FG)


def style_legend(leg, dark):
    if leg is None or not dark:
        return
    leg.get_frame().set_facecolor(SCREEN_BG)
    leg.get_frame().set_edgecolor(SCREEN_GRID)
    for text in leg.get_texts():
        text.set_color(SCREEN_FG)


def _grid(ax, dark):
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=SCREEN_GRID if dark else "grey",
                  linewidth=0.5, alpha=0.8 if dark else 0.5)


def bar_width(ax, n_bars):
    """Bar width for a by-treatment bar chart - half the usual 0.6 with
    three or fewer bars, so a single treatment isn't one slab filling the
    plot. The x limits are pinned to where the full-width bars would have
    put them (autoscale would otherwise just stretch the narrower bars
    back out), so they really do show at half width."""
    if n_bars > 3:
        return 0.6
    span = n_bars - 1 + 0.6
    ax.set_xlim(-0.3 - 0.05 * span, n_bars - 1 + 0.3 + 0.05 * span)
    return 0.3


def _awaiting(ax, msg):
    ax.annotate(msg, xy=(0.5, 0.5), xycoords="axes fraction",
                ha="center", va="center", color=_MUTED, fontsize=10)


def draw_strike_rate(fig, summary, dark=False):
    """Predicted blade strike rate by treatment, with Wilson 95% CIs."""
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    ax.set_ylabel("Predicted blade strike rate (%)", fontsize=9)
    ax.set_xlabel("Treatment", fontsize=9)
    ax.set_title("Blade strike rate by treatment",
                 fontsize=10, fontweight="bold")
    _grid(ax, dark)

    if summary is None or not len(summary):
        ax.set_ylim(0, 100)
        ax.set_xticks([])
        _awaiting(ax, "Awaiting prediction run")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return

    x     = np.arange(len(summary))
    rates = summary["strike_rate"].values * 100
    lo    = (summary["strike_rate"].values - summary["ci_lo"].values) * 100
    hi    = (summary["ci_hi"].values - summary["strike_rate"].values) * 100

    colors = [_BLUES[i % len(_BLUES)] for i in range(len(summary))]
    bars   = ax.bar(x, rates, color=colors, edgecolor=fg,
                    width=bar_width(ax, len(summary)), alpha=0.9)
    ax.errorbar(x, rates, yerr=[lo, hi],
                fmt="none", ecolor=fg, capsize=5, linewidth=1.2)

    y_pad = hi.max() * 0.15 + 1 if len(hi) else 2
    for bar, val in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + y_pad,
                f"{val:.1f}%", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color=fg)

    ax.set_xticks(x)
    ax.set_xticklabels(summary["treatment"].values, rotation=30,
                       ha="right", fontsize=8)
    ax.set_ylim(0, min(100, rates.max() + hi.max() * 1.5 + 10)
                if len(rates) else 10)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_severity(fig, severity_summary, dark=False, measured=True):
    """Strike severity by treatment: the share of recordings whose HIG
    peak passed 95, 200 and 400 g, with Wilson 95% CIs - only > 400 g is
    a severe strike. `measured=False` says the dataset had no HIG."""
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    ax.set_ylabel("Recordings over the threshold (%)", fontsize=9)
    ax.set_xlabel("Treatment", fontsize=9)
    ax.set_title("Strike severity (HIG peak)",
                 fontsize=10, fontweight="bold")
    _grid(ax, dark)

    if severity_summary is None or not len(severity_summary):
        ax.set_ylim(0, 100)
        ax.set_xticks([])
        _awaiting(ax, "Awaiting prediction run" if measured
                  else "No HIG channel in this dataset")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return

    treatments = list(dict.fromkeys(severity_summary["treatment"]))
    thresholds = sorted(severity_summary["threshold_g"].unique())
    x = np.arange(len(treatments))
    width = 0.8 / len(thresholds)
    colours = [_PALETTE[0], _PALETTE[2], _PALETTE[1]]
    for j, g in enumerate(thresholds):
        rows = (severity_summary[severity_summary["threshold_g"] == g]
                .set_index("treatment").reindex(treatments))
        rate = rows["rate"].values * 100
        err = [rate - rows["ci_lo"].values * 100, rows["ci_hi"].values * 100 - rate]
        severe = bool(rows["severe"].iloc[0])
        label = f"> {g} g" + (" (severe)" if severe else "")
        pos = x + (j - (len(thresholds) - 1) / 2) * width
        ax.bar(pos, rate, width=width * 0.95, color=colours[j % len(colours)],
               edgecolor=fg, linewidth=1.4 if severe else 0.6,
               hatch="//" if severe else None, alpha=0.9, label=label)
        ax.errorbar(pos, rate, yerr=err, fmt="none", ecolor=fg,
                    capsize=3, linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(treatments, rotation=30, ha="right", fontsize=8)
    ax.set_ylim(0, 105)
    style_legend(ax.legend(fontsize=7, loc="upper right"), dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_region(fig, summary, class_names, dark=False):
    """Predicted strike location (class share of strikes) by treatment."""
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    ax.set_ylabel("Region share of strikes", fontsize=9)
    ax.set_xlabel("Treatment", fontsize=9)
    ax.set_title("Predicted strike location by treatment",
                 fontsize=10, fontweight="bold")
    ax.set_ylim(0, 1.0)
    _grid(ax, dark)

    have_regions = (summary is not None and len(summary)
                    and bool(class_names)
                    and all(f"n_{cn}" in summary.columns for cn in class_names))
    if not have_regions:
        ax.set_xticks([])
        _awaiting(ax, "Awaiting multiclass prediction"
                  if class_names else "No region model loaded")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return

    x = np.arange(len(summary))
    n_strike = summary["n_strike"].values.astype(float)
    bottom = np.zeros(len(summary))
    for i, cn in enumerate(class_names):
        counts = summary[f"n_{cn}"].values.astype(float)
        props  = np.divide(counts, n_strike, out=np.zeros_like(counts),
                           where=n_strike > 0)
        ax.bar(x, props, bottom=bottom, color=_PALETTE[i % len(_PALETTE)],
               edgecolor=fg, lw=0.5, width=bar_width(ax, len(summary)), label=cn)
        bottom += props

    ax.set_xticks(x)
    ax.set_xticklabels(summary["treatment"].values, rotation=30,
                       ha="right", fontsize=8)
    leg = ax.legend(fontsize=7, loc="upper center",
                    bbox_to_anchor=(0.5, -0.18),
                    ncol=max(1, len(class_names)))
    style_legend(leg, dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def render_figures(state, out_dir, formats=("png",), dpi=300):
    """Render the prediction figures to files (publication styling).

    Only figures applicable to the run are produced (the region figure needs
    a multiclass run).
    """
    from matplotlib.figure import Figure

    out = {}
    if state.summary is None:
        return out
    out_dir.mkdir(parents=True, exist_ok=True)

    fig = Figure(figsize=(6.0, 4.2), dpi=100)
    draw_strike_rate(fig, state.summary)
    out["predicted_strike_rate"] = []
    for fmt in formats:
        p = out_dir / f"predicted_strike_rate.{fmt}"
        fig.savefig(p, dpi=dpi, bbox_inches="tight")
        out["predicted_strike_rate"].append(p)

    if getattr(state, "severity_summary", None) is not None:
        fig_sev = Figure(figsize=(6.0, 4.2), dpi=100)
        draw_severity(fig_sev, state.severity_summary)
        out["strike_severity"] = []
        for fmt in formats:
            p = out_dir / f"strike_severity.{fmt}"
            fig_sev.savefig(p, dpi=dpi, bbox_inches="tight")
            out["strike_severity"].append(p)

    if state.class_names and state.run_meta.get("mode") == "multiclass":
        fig2 = Figure(figsize=(6.0, 4.2), dpi=100)
        draw_region(fig2, state.summary, state.class_names)
        out["predicted_strike_region"] = []
        for fmt in formats:
            p = out_dir / f"predicted_strike_region.{fmt}"
            fig2.savefig(p, dpi=dpi, bbox_inches="tight")
            out["predicted_strike_region"].append(p)
    return out
