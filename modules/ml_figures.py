"""Prediction figures, drawn onto any matplotlib Figure. Two presentations:

  dark=True   the on-screen look, in the theme's canvas colours. Empty
              figures still draw their expected axes (labels, limits,
              grid) so the panels read as live plots awaiting data.
  dark=False  publication styling on white, for every exported figure.

Both use the theme's figure palette.
"""
import math

import numpy as np

from . import hig_peaks, theme

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
    """Bar width for a by-treatment chart: half the usual 0.6 with three
    or fewer bars, so one treatment doesn't fill the plot. The x limits are
    then pinned to where full-width bars would put them, or autoscale would
    stretch the narrow bars back out."""
    if n_bars > 3:
        return 0.6
    span = n_bars - 1 + 0.6
    ax.set_xlim(-0.3 - 0.05 * span, n_bars - 1 + 0.3 + 0.05 * span)
    return 0.3


def _awaiting(ax, msg):
    note = ax.annotate(msg, xy=(0.5, 0.5), xycoords="axes fraction",
                       ha="center", va="center", color=_MUTED, fontsize=10)
    # tight_layout would otherwise shrink the axes to fit a message wider
    # than them
    note.set_in_layout(False)


def draw_strike_rate(fig, summary, dark=False):
    """Predicted blade strike rate by treatment, with Wilson 95% CIs."""
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    ax.set_ylabel("Predicted blade strike rate (%)", fontsize=9)
    ax.set_xlabel("Treatment", fontsize=9)
    ax.set_title("Blade strike rate by treatment",
                 fontsize=10)
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
                fontsize=8, color=fg)

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
                 fontsize=10)
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


def _peak_groups(acc_summary):
    """The summary rows plotted: each treatment, without the "All
    recordings" total when there are several."""
    if len(acc_summary) > 1:
        return acc_summary[acc_summary["treatment"] != hig_peaks.ALL_LABEL]
    return acc_summary


def _group_label(value):
    """A treatment as the acceleration table writes it: whole numbers
    without ".0" (a CSV round trip turns 500 into 500.0), blanks empty."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sensor_peaks(predictions, rows):
    """Each plotted group's per-recording HIG peaks (g), from the
    predictions' `hig_peak_g`: [array per row of `rows`], or None when the
    run has none."""
    if predictions is None or "hig_peak_g" not in predictions.columns:
        return None
    peaks = predictions["hig_peak_g"].astype(float)
    labels = [_group_label(t) for t in rows["treatment"]]
    if labels == [hig_peaks.ALL_LABEL] or "treatment" not in predictions.columns:
        values = [peaks.dropna().values]
    else:
        tx = predictions["treatment"].map(_group_label)
        values = [peaks[tx == label].dropna().values for label in labels]
    return values if any(len(v) for v in values) else None


def _panel_text(ax, letter, corner, fg):
    """The panel's letter top left ("a)") and its n (and CI) top right."""
    ax.text(0.03, 0.97, f"{letter})", transform=ax.transAxes, ha="left",
            va="top", fontsize=11, color=fg)
    if corner:
        ax.text(0.97, 0.97, corner, transform=ax.transAxes, ha="right",
                va="top", multialignment="center", fontsize=9, color=fg)


def draw_peak_summary(fig, acc_summary, predictions=None, dark=False,
                      note=None):
    """HIG peak analysis in three panels: (a) each recording's peak
    acceleration (`hig_peak_g` in `predictions`) as a box plot per
    treatment; (b) the number of acceleration events at or over 95, 200
    and 400 g, one dot per treatment; (c) the collision probability -
    recordings with an event of at least 400 g within 0.1 s of the nadir -
    with its Wilson 95% interval, on 0-100%. `note` replaces the
    "awaiting" message when there is nothing to draw."""
    fig.clear()
    ax_a, ax_b, ax_c = fig.subplots(1, 3)
    fg = fg_colour(dark)
    thresholds = hig_peaks.THRESHOLDS_G
    ax_a.set_ylabel("Peak acceleration (g)", fontsize=9)
    ax_b.set_ylabel("Acceleration events", fontsize=9)
    ax_b.set_xlabel("HIG peak", fontsize=9)
    ax_c.set_ylabel("Collision / blade strike probability (%)", fontsize=9)
    ax_b.set_xticks(range(len(thresholds)))
    ax_b.set_xticklabels([f"≥{g} g" for g in thresholds], fontsize=8)
    ax_b.set_xlim(-0.5, len(thresholds) - 0.5)
    ax_c.set_ylim(0, 100)

    if acc_summary is None or not len(acc_summary):
        ax_a.set_ylim(0, 500)
        ax_b.set_ylim(0, 10)
        for ax in (ax_a, ax_c):
            ax.set_xticks([])
        for letter, ax in zip("abc", (ax_a, ax_b, ax_c)):
            _panel_text(ax, letter, None, fg)
        _awaiting(ax_b, note or "Awaiting prediction run")
        for ax in (ax_a, ax_b, ax_c):
            style_axes(fig, ax, dark)
        fig.tight_layout()
        return

    rows = _peak_groups(acc_summary).reset_index(drop=True)
    n = len(rows)
    names = [_group_label(t) for t in rows["treatment"]]
    total = int(rows["n_sensors"].sum())
    x = np.arange(n)

    def treatment_ticks(ax):
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=30 if n > 2 else 0,
                           ha="right" if n > 2 else "center",
                           fontsize=8 if n > 2 else 9)
        ax.set_xlim(-0.6, n - 0.4)

    # a: each recording's peak
    values = _sensor_peaks(predictions, rows)
    if values is None:
        ax_a.set_xticks([])
        ax_a.set_ylim(0, 500)
        _awaiting(ax_a, "No per-sensor peaks")
    else:
        box = ax_a.boxplot(
            values, positions=x, widths=0.5, patch_artist=True,
            medianprops={"color": fg, "linewidth": 1.5},
            whiskerprops={"color": fg}, capprops={"color": fg},
            flierprops={"marker": "o", "markersize": 4,
                        "markerfacecolor": "none", "markeredgecolor": fg})
        for j, patch in enumerate(box["boxes"]):
            patch.set_facecolor(_PALETTE[j % len(_PALETTE)])
            patch.set_edgecolor(fg)
        treatment_ticks(ax_a)
        top = max(float(np.max(v)) for v in values if len(v))
        ax_a.set_ylim(0, top * 1.15)
    _panel_text(ax_a, "a", f"n = {total}", fg)

    # b: events over each threshold
    step = min(0.22, 0.6 / max(n, 1))
    top = 0
    for j, r in rows.iterrows():
        colour = _PALETTE[j % len(_PALETTE)]
        counts = [int(r[f"n_events_{g}g"]) for g in thresholds]
        top = max(top, *counts)
        xs = np.arange(len(thresholds)) + (j - (n - 1) / 2) * step
        ax_b.scatter(xs, counts, s=46, color=colour, edgecolors=fg,
                     linewidths=0.6, zorder=3, label=names[j])
        if n <= 3:
            for xi, c in zip(xs, counts):
                ax_b.annotate(str(c), (xi, c), xytext=(6, 0),
                              textcoords="offset points", va="center",
                              fontsize=7, color=fg)
    ax_b.set_ylim(0, top * 1.15 + 1)
    if n > 1:
        style_legend(ax_b.legend(fontsize=7, loc="upper right",
                                 bbox_to_anchor=(1.0, 0.88)), dark)
    _panel_text(ax_b, "b", f"n = {total}", fg)

    # c: collision probability
    rate = rows["collision_rate"].values * 100
    lo = rate - rows["ci_lo"].values * 100
    hi = rows["ci_hi"].values * 100 - rate
    for j in range(n):
        ax_c.errorbar(x[j], rate[j], yerr=[[lo[j]], [hi[j]]], fmt="o",
                      markersize=7, color=_PALETTE[j % len(_PALETTE)],
                      markeredgecolor=fg, markeredgewidth=0.6, ecolor=fg,
                      elinewidth=1.1, capsize=5, zorder=3)
        ax_c.annotate(f"{rate[j]:.1f}%", (x[j], rate[j] + hi[j]),
                      xytext=(0, 4), textcoords="offset points", ha="center",
                      va="bottom", fontsize=7, color=fg)
    treatment_ticks(ax_c)
    _panel_text(ax_c, "c", f"CI = 95%\nn = {total}", fg)

    for ax in (ax_a, ax_b, ax_c):
        style_axes(fig, ax, dark)
    fig.tight_layout()


_ALIGN = {
    "acc": ("time_norm_acc", "Normalised time (peak acceleration = 0.5)",
            "Acceleration-aligned"),
    "nadir": ("time_norm_nadir", "Normalised time (pressure nadir = 0.5)",
              "Nadir-aligned"),
}
_TRACE_RED = "#d62728"


def draw_acc_centred(fig, traces, align="acc", dark=False, note=None):
    """The HIG magnitude of every recording with a collision on a
    normalised time axis - each sample a faint red point, the median in
    0.0025 bins as a line, 0.5 dashed - one panel per treatment, in name
    order as the prediction summary. `align` "acc" puts each recording's
    peak acceleration at 0.5, "nadir" its pressure nadir
    (`hig_peaks.centred_traces`)."""
    fig.clear()
    x_col, x_label, title = _ALIGN[align]
    fg = fg_colour(dark)
    if traces is None or not len(traces):
        ax = fig.add_subplot(111)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 700)
        ax.set_xlabel(x_label, fontsize=9)
        ax.set_ylabel("Acceleration (g)", fontsize=9)
        _grid(ax, dark)
        _awaiting(ax, note or (f"No collisions (≥{hig_peaks.COLLISION_G} g "
                               "at the nadir)" if traces is not None
                               else "Awaiting prediction run"))
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return

    facets = sorted(set(traces["facet"]))
    ncols = min(3, len(facets))
    nrows = math.ceil(len(facets) / ncols)
    axes = fig.subplots(nrows, ncols, sharex=True, sharey=True,
                        squeeze=False).ravel()
    medians = hig_peaks.median_trace(traces, x_col)
    peak = float(traces[hig_peaks.CHANNEL].max())
    y_top = max(700.0, math.ceil(peak / 50) * 50)
    for ax, facet in zip(axes, facets):
        rec = traces[traces["facet"] == facet]
        med = medians[medians["facet"] == facet]
        ax.scatter(rec[x_col], rec[hig_peaks.CHANNEL], s=2, color=_TRACE_RED,
                   alpha=0.3, linewidths=0, rasterized=True)
        ax.plot(med["time_bin"], med["median_g"], color=fg, linewidth=1.2)
        ax.axvline(0.5, color=fg, linestyle="--", linewidth=0.9)
        ax.set_title(f"{facet} (n = {rec['file'].nunique()})", fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, y_top)
        ax.set_yticks(np.arange(0, y_top + 1, 100))
        ax.tick_params(labelsize=7)
        _grid(ax, dark)
        style_axes(fig, ax, dark)
    for ax in axes[len(facets):]:
        ax.set_visible(False)
    fig.supxlabel(x_label, fontsize=9, color=fg)
    fig.supylabel("Acceleration (g)", fontsize=9, color=fg)
    fig.suptitle(f"{title}: recordings with a collision "
                 f"(n = {traces['file'].nunique()})",
                 fontsize=10, color=fg)
    if dark:
        fig.patch.set_facecolor(SCREEN_BG)
    fig.tight_layout()


def centred_figure_height(traces, width_rows=2.6):
    """Inches for an acceleration-centred figure: a row per three facets."""
    n = traces["facet"].nunique() if traces is not None and len(traces) else 1
    return 1.0 + width_rows * math.ceil(n / min(3, n))


def draw_region(fig, summary, class_names, dark=False):
    """Predicted strike location (class share of strikes) by treatment."""
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    ax.set_ylabel("Region share of strikes", fontsize=9)
    ax.set_xlabel("Treatment", fontsize=9)
    ax.set_title("Predicted strike location by treatment",
                 fontsize=10)
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
    # the legend along the figure's foot, outside the plot: the constrained
    # layout keeps room for it under the "Treatment" title at any size
    fig.set_layout_engine("constrained")
    handles, labels = ax.get_legend_handles_labels()
    leg = fig.legend(handles, labels, fontsize=7, loc="outside lower center",
                     ncol=max(1, len(class_names)))
    style_legend(leg, dark)
    style_axes(fig, ax, dark)


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

    acc_summary = getattr(state, "acc_summary", None)
    if acc_summary is not None:
        fig_pk = Figure(figsize=(10.5, 3.6), dpi=100)
        draw_peak_summary(fig_pk, acc_summary,
                          getattr(state, "predictions", None))
        out["hig_peak_summary"] = []
        for fmt in formats:
            p = out_dir / f"hig_peak_summary.{fmt}"
            fig_pk.savefig(p, dpi=dpi, bbox_inches="tight")
            out["hig_peak_summary"].append(p)
        traces = state.collision_traces()
        for align in ("acc", "nadir"):
            fig_c = Figure(figsize=(7.5, centred_figure_height(traces)), dpi=100)
            draw_acc_centred(fig_c, traces, align)
            name = f"{align}_aligned_acceleration"
            out[name] = []
            for fmt in formats:
                p = out_dir / f"{name}.{fmt}"
                fig_c.savefig(p, dpi=dpi, bbox_inches="tight")
                out[name].append(p)
    elif getattr(state, "severity_summary", None) is not None:
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
