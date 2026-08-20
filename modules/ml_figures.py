# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Prediction figures, ported from the MVP prediction page.

Factored to draw onto any matplotlib Figure so the same code produces the
on-screen canvases (Predict tab) and the exported publication figures
(Report tab / Export analysis). White backgrounds are intentional - all
StrikeWorks figures are publication-styled, not theme-styled.
"""
import numpy as np

_BLUES   = ["#1e3a5f", "#2e5d9f", "#4a86c8", "#6fa8dc", "#9fc5e8"]
_PALETTE = ["#2196F3", "#E91E63", "#FF9800", "#4CAF50", "#9C27B0", "#00BCD4"]
_MUTED   = "#94a3b8"


def draw_strike_rate(fig, summary):
    """Predicted blade strike rate by treatment, with Wilson 95% CIs."""
    fig.clear()
    ax = fig.add_subplot(111)
    if summary is None or not len(summary):
        ax.text(0.5, 0.5, "No prediction run", ha="center", va="center",
                transform=ax.transAxes, color=_MUTED, fontsize=10)
        ax.set_axis_off()
        fig.tight_layout()
        return

    x     = np.arange(len(summary))
    rates = summary["strike_rate"].values * 100
    lo    = (summary["strike_rate"].values - summary["ci_lo"].values) * 100
    hi    = (summary["ci_hi"].values - summary["strike_rate"].values) * 100

    colors = [_BLUES[i % len(_BLUES)] for i in range(len(summary))]
    bars   = ax.bar(x, rates, color=colors, edgecolor="black", width=0.6,
                    alpha=0.9)
    ax.errorbar(x, rates, yerr=[lo, hi],
                fmt="none", ecolor="black", capsize=5, linewidth=1.2)

    y_pad = hi.max() * 0.15 + 1 if len(hi) else 2
    for bar, val in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + y_pad,
                f"{val:.1f}%", ha="center", va="bottom",
                fontsize=8, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(summary["treatment"].values, rotation=30,
                       ha="right", fontsize=8)
    ax.set_ylabel("Predicted blade strike rate (%)", fontsize=9)
    ax.set_title("Blade strike rate by treatment",
                 fontsize=10, fontweight="bold")
    ax.set_ylim(0, min(100, rates.max() + hi.max() * 1.5 + 10)
                if len(rates) else 10)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="grey", linewidth=0.5, alpha=0.5)
    fig.tight_layout()


def draw_region(fig, summary, class_names):
    """Predicted strike location (class share of strikes) by treatment."""
    fig.clear()
    ax = fig.add_subplot(111)

    have_regions = (summary is not None and len(summary)
                    and bool(class_names)
                    and all(f"n_{cn}" in summary.columns for cn in class_names))
    if not have_regions:
        ax.text(0.5, 0.5, "No region model loaded", ha="center", va="center",
                transform=ax.transAxes, color=_MUTED, fontsize=10)
        ax.set_axis_off()
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
               edgecolor="black", lw=0.5, width=0.6, label=cn)
        bottom += props

    ax.set_xticks(x)
    ax.set_xticklabels(summary["treatment"].values, rotation=30,
                       ha="right", fontsize=8)
    ax.set_ylabel("Region share of strikes", fontsize=9)
    ax.set_title("Predicted strike location by treatment",
                 fontsize=10, fontweight="bold")
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=max(1, len(class_names)))
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="grey", linewidth=0.5, alpha=0.5)
    fig.tight_layout()


def render_figures(state, out_dir, formats=("png",)):
    """Render the prediction figures to files. Returns {name: [paths]}.

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
        fig.savefig(p, dpi=300, bbox_inches="tight")
        out["predicted_strike_rate"].append(p)

    if state.class_names and state.run_meta.get("mode") == "multiclass":
        fig2 = Figure(figsize=(6.0, 4.2), dpi=100)
        draw_region(fig2, state.summary, state.class_names)
        out["predicted_strike_region"] = []
        for fmt in formats:
            p = out_dir / f"predicted_strike_region.{fmt}"
            fig2.savefig(p, dpi=300, bbox_inches="tight")
            out["predicted_strike_region"].append(p)
    return out
