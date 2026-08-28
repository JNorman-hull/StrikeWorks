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
from .ml_figures import _PALETTE, fg_colour, style_axes, _grid

CEN_COLOR = _PALETTE[3]   # green - "the model's own estimate"
OBS_COLOR = _PALETTE[0]   # blue - "what was actually observed"


def _bar_style(ax, dark, ylabel):
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_ylim(0, 100)
    _grid(ax, dark)
    style_axes(ax.figure, ax, dark)


def draw_pco(fig, res, dark=True):
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    if "Pco_obs" in res:
        ax.bar(["CEN", "Observed"], [res["Pco_tip"] * 100, res["Pco_obs"] * 100],
               width=0.55, color=[CEN_COLOR, OBS_COLOR], edgecolor=fg)
        ax.errorbar(1, res["Pco_obs"] * 100,
                    yerr=[[(res["Pco_obs"] - res["wilson_lo"]) * 100],
                          [(res["wilson_hi"] - res["Pco_obs"]) * 100]],
                    fmt="none", ecolor=fg, capsize=6, linewidth=1.2)
        _bar_style(ax, dark, "Collision probability (%) [95% CI]")
    else:
        ax.bar(["CEN"], [res["Pco_tip"] * 100], width=0.55,
               color=[CEN_COLOR], edgecolor=fg)
        _bar_style(ax, dark, "Collision probability (%)")
    fig.tight_layout()


def draw_pm(fig, res, dark=True):
    fig.clear()
    ax = fig.add_subplot(111)
    fg = fg_colour(dark)
    if "Pco_obs" in res:
        ax.bar(["CEN", "Observed"], [res["Pm"] * 100, res["Pm_obs"] * 100],
               width=0.55, color=[CEN_COLOR, OBS_COLOR], edgecolor=fg)
    else:
        ax.bar(["CEN"], [res["Pm"] * 100], width=0.55,
               color=[CEN_COLOR], edgecolor=fg)
    _bar_style(ax, dark, "Mortality probability (%)")
    fig.tight_layout()


def draw_sens_wf(fig, x, y, x_fit, y_fit, span=4.0, dark=True):
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
    ax.set_xlabel("Relative fish velocity wf (m/s)", fontsize=9)
    ax.set_ylabel("Collision probability (%)", fontsize=9)
    style_axes(fig, ax, dark)
    fig.tight_layout()
