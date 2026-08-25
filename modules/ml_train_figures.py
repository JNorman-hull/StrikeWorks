# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Model-evaluation figures for the Model Training page.

Ports of the figures produced by 01_binary_model.py and
05_multiclass_collapsed.py, redrawn with pure matplotlib (no seaborn
dependency) from the worker's outputs (performance_metrics.json,
cv_curves.json, cv_predictions.csv) so the GUI never touches the model
stack.

dark=True gives the in-app themed presentation (empty figures still draw
their expected axes); dark=False is the publication styling used for
exported figures and reports.
"""
import numpy as np

from .ml_figures import (
    _MUTED, _PALETTE, _awaiting, _grid, fg_colour, style_axes, style_legend,
)


def _base_axes(fig, dark, xlabel, ylabel, title):
    ax = fig.add_subplot(111)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold")
    return ax


# ── binary figures ───────────────────────────────────────────────────────────

def draw_roc(fig, curves, metrics, dark=False):
    fig.clear()
    ax = _base_axes(fig, dark, "False positive rate", "True positive rate",
                    "ROC curve (out-of-fold)")
    ax.grid(alpha=0.3)
    if not curves or "fpr" not in curves:
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        _awaiting(ax, "Awaiting cross-validation")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    fg = fg_colour(dark)
    fpr = np.asarray(curves["fpr"])
    tpr = np.asarray(curves["tpr"])
    perf = metrics["out_of_fold_performance"]
    opt = int(curves.get("roc_optimal_idx", 0))

    ax.plot(fpr, tpr, color="#4a9df0", lw=2.2,
            label=f"ROC curve (AUC = {perf['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], linestyle="--", color=fg, lw=1.2, alpha=0.5,
            label="Random classifier")
    ax.scatter(fpr[opt], tpr[opt], c="red", s=90, zorder=5,
               edgecolors=fg, lw=1.2,
               label=f"Optimal threshold = {perf['optimal_threshold']:.3f}")
    leg = ax.legend(loc="lower right", fontsize=7)
    style_legend(leg, dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_pr(fig, curves, metrics, dark=False):
    fig.clear()
    ax = _base_axes(fig, dark, "Recall", "Precision",
                    "Precision–recall curve (out-of-fold)")
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.grid(alpha=0.3)
    if not curves or "precision" not in curves:
        _awaiting(ax, "Awaiting cross-validation")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    perf = metrics["out_of_fold_performance"]
    ax.plot(curves["recall"], curves["precision"], color="#37c26e", lw=2.2,
            label=f"PR curve (AUC = {perf['pr_auc']:.3f})")
    base = curves.get("baseline_rate")
    if base is not None:
        ax.axhline(y=base, color="gray", linestyle="--", lw=1.2,
                   label=f"Baseline (strike rate = {base:.3f})")
    leg = ax.legend(loc="lower left", fontsize=7)
    style_legend(leg, dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def _heatmap(ax, cm, labels, title, dark):
    cm = np.asarray(cm, dtype=float)
    rs = cm.sum(axis=1, keepdims=True)
    pct = np.divide(cm, rs, out=np.zeros_like(cm), where=rs != 0) * 100
    ax.imshow(cm, cmap="Blues")
    n = len(labels)
    for i in range(n):
        for j in range(n):
            colour = "white" if cm[i, j] > cm.max() * 0.6 else "#1e3a5f"
            ax.text(j, i, f"{int(cm[i, j])}\n({pct[i, j]:.1f}%)",
                    ha="center", va="center", fontsize=8, color=colour)
    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Predicted", fontsize=9)
    ax.set_ylabel("True", fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold")


def draw_confusion_binary(fig, metrics, dark=False):
    fig.clear()
    perf = (metrics or {}).get("out_of_fold_performance", {})
    cm = perf.get("confusion_matrix")
    if not cm:
        ax = _base_axes(fig, dark, "Predicted", "True", "Confusion matrix")
        ax.set_xticks([])
        ax.set_yticks([])
        _awaiting(ax, "Awaiting cross-validation")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    ax = fig.add_subplot(111)
    mat = [[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]]
    _heatmap(ax, mat, ["No strike", "Strike"],
             f"Confusion matrix (accuracy = {perf['overall_accuracy']:.3f})",
             dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_probability_distribution(fig, cv_predictions, metrics, dark=False):
    fig.clear()
    ax = _base_axes(fig, dark, "Predicted probability", "Frequency",
                    "Out-of-fold predicted probabilities")
    ax.grid(alpha=0.3, axis="y")
    if cv_predictions is None or "probability" not in cv_predictions.columns:
        ax.set_xlim(0, 1)
        _awaiting(ax, "Per-recording CV predictions unavailable")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    fg = fg_colour(dark)
    perf = metrics["out_of_fold_performance"]
    y = cv_predictions["y_true"].values
    p = cv_predictions["probability"].values
    bins = np.linspace(0, 1, 21)
    ax.hist(p[y == 0], bins=bins, alpha=0.65,
            label=f"No strike (n={int((y == 0).sum())})",
            color="steelblue", edgecolor=fg, lw=0.5)
    ax.hist(p[y == 1], bins=bins, alpha=0.65,
            label=f"Strike (n={int((y == 1).sum())})",
            color="tomato", edgecolor=fg, lw=0.5)
    ax.axvline(perf["optimal_threshold"], color="#37c26e", linestyle="--",
               lw=1.8,
               label=f"Optimal threshold ({perf['optimal_threshold']:.3f})")
    leg = ax.legend(fontsize=7)
    style_legend(leg, dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_accuracy_by_type(fig, metrics, dark=False):
    fig.clear()
    ax = _base_axes(fig, dark, "Strike type", "Accuracy",
                    "Accuracy by strike type")
    ax.set_ylim([0, 1.12])
    ax.grid(alpha=0.3, axis="y")
    by_type = (metrics or {}).get("performance_by_strike_type", {})
    if not by_type:
        ax.set_xticks([])
        _awaiting(ax, "No strike-type information")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    fg = fg_colour(dark)
    perf = metrics["out_of_fold_performance"]
    names = list(by_type.keys())
    accs = [by_type[n]["accuracy"] for n in names]
    ns = [by_type[n]["n_files"] for n in names]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]
    bars = ax.bar(range(len(names)), accs, color=colors,
                  edgecolor=fg, width=0.6)
    ax.axhline(y=perf["overall_accuracy"], color=fg, linestyle="--",
               lw=1.2,
               label=f"Overall accuracy ({perf['overall_accuracy']:.3f})")
    for bar, acc, n in zip(bars, accs, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{acc:.2f}\nn={n}", ha="center", fontsize=7, color=fg)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    leg = ax.legend(fontsize=7)
    style_legend(leg, dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


# ── multiclass figures ───────────────────────────────────────────────────────

def draw_confusion_multiclass(fig, metrics, dark=False):
    fig.clear()
    perf = (metrics or {}).get("out_of_fold_performance", {})
    cm = perf.get("confusion_matrix")
    names = (metrics or {}).get("class_names")
    if cm is None or not names:
        ax = _base_axes(fig, dark, "Predicted", "True", "Confusion matrix")
        ax.set_xticks([])
        ax.set_yticks([])
        _awaiting(ax, "Awaiting cross-validation")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    ax = fig.add_subplot(111)
    _heatmap(ax, cm, names,
             f"Confusion matrix (accuracy = {perf['overall_accuracy']:.3f})",
             dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_per_class_recall(fig, metrics, dark=False):
    fig.clear()
    ax = _base_axes(fig, dark, "Class", "Recall", "Per-class recall")
    ax.set_ylim([0, 1.1])
    ax.grid(alpha=0.3, axis="y")
    perf = (metrics or {}).get("out_of_fold_performance", {})
    per_class = perf.get("per_class_metrics")
    if not per_class:
        ax.set_xticks([])
        _awaiting(ax, "Awaiting cross-validation")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    fg = fg_colour(dark)
    names = list(per_class.keys())
    recalls = [per_class[n]["recall"] for n in names]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]
    bars = ax.bar(names, recalls, color=colors, edgecolor=fg, width=0.6)
    ax.axhline(y=perf["overall_accuracy"], color=fg, linestyle="--",
               lw=1.2,
               label=f"Overall accuracy ({perf['overall_accuracy']:.3f})")
    for bar, v in zip(bars, recalls):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{v:.3f}", ha="center", fontsize=8, color=fg)
    ax.tick_params(axis="x", labelsize=8)
    leg = ax.legend(fontsize=7)
    style_legend(leg, dark)
    style_axes(fig, ax, dark)
    fig.tight_layout()


def draw_confidence_by_class(fig, cv_predictions, metrics, dark=False):
    fig.clear()
    names = (metrics or {}).get("class_names")
    if cv_predictions is None or not names \
            or "true_class" not in cv_predictions.columns:
        ax = _base_axes(fig, dark, "P(true class)", "Frequency",
                        "Prediction confidence by true class")
        ax.set_xlim(0, 1)
        _awaiting(ax, "Per-recording CV predictions unavailable")
        style_axes(fig, ax, dark)
        fig.tight_layout()
        return
    axes = fig.subplots(1, len(names), squeeze=False)
    for i, cn in enumerate(names):
        ax = axes[0, i]
        col = f"prob_{cn}"
        mask = cv_predictions["true_class"] == cn
        if col in cv_predictions.columns and mask.any():
            ax.hist(cv_predictions.loc[mask, col], bins=15, alpha=0.8,
                    edgecolor=fg_colour(dark),
                    color=_PALETTE[i % len(_PALETTE)])
        ax.set_xlabel("P(true class)", fontsize=8)
        if i == 0:
            ax.set_ylabel("Frequency", fontsize=8)
        ax.set_title(f"True: {cn}\n(n={int(mask.sum())})", fontsize=8,
                     fontweight="bold")
        ax.set_xlim([0, 1])
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
        style_axes(fig, ax, dark)
    fig.suptitle("Prediction confidence by true class", fontsize=10,
                 fontweight="bold",
                 color=fg_colour(dark))
    fig.tight_layout()


def draw_all(figures, metrics, cv_predictions, curves, dark=False):
    """Redraw every evaluation figure for one model's results.

    `figures` maps name -> Figure. Unused figures are cleared to a note.
    """
    if metrics is None:
        draw_roc(figures["fig1"], None, None, dark)
        draw_pr(figures["fig2"], None, None, dark)
        draw_confusion_binary(figures["fig3"], None, dark)
        draw_probability_distribution(figures["fig4"], None, None, dark)
        draw_accuracy_by_type(figures["fig5"], None, dark)
        return
    binary = "roc_auc" in metrics.get("out_of_fold_performance", {})

    if binary:
        draw_roc(figures["fig1"], curves, metrics, dark)
        draw_pr(figures["fig2"], curves, metrics, dark)
        draw_confusion_binary(figures["fig3"], metrics, dark)
        draw_probability_distribution(figures["fig4"], cv_predictions,
                                      metrics, dark)
        draw_accuracy_by_type(figures["fig5"], metrics, dark)
    else:
        draw_confusion_multiclass(figures["fig1"], metrics, dark)
        draw_per_class_recall(figures["fig2"], metrics, dark)
        draw_confidence_by_class(figures["fig3"], cv_predictions, metrics,
                                 dark)
        for name in ("fig4", "fig5"):
            fig = figures[name]
            fig.clear()
            ax = _base_axes(fig, dark, None, None, None)
            ax.set_axis_off()
            _awaiting(ax, "Binary-only figure")
            style_axes(fig, ax, dark)
            fig.tight_layout()


def render_model_figures(out_dir, metrics, cv_predictions, curves,
                         formats=("png",)):
    """Render the evaluation figures for one model to files (publication
    styling). Returns {figure name: path} for the first format."""
    from matplotlib.figure import Figure

    binary = "roc_auc" in (metrics or {}).get("out_of_fold_performance", {})
    if binary:
        spec = [("roc_curve", lambda f: draw_roc(f, curves, metrics)),
                ("precision_recall_curve", lambda f: draw_pr(f, curves,
                                                             metrics)),
                ("confusion_matrix",
                 lambda f: draw_confusion_binary(f, metrics)),
                ("probability_distribution",
                 lambda f: draw_probability_distribution(f, cv_predictions,
                                                         metrics)),
                ("accuracy_by_strike_type",
                 lambda f: draw_accuracy_by_type(f, metrics))]
        if curves is None:
            spec = [s for s in spec
                    if s[0] not in ("roc_curve", "precision_recall_curve")]
        if cv_predictions is None:
            spec = [s for s in spec if s[0] != "probability_distribution"]
    else:
        spec = [("confusion_matrix",
                 lambda f: draw_confusion_multiclass(f, metrics)),
                ("per_class_recall",
                 lambda f: draw_per_class_recall(f, metrics))]
        if cv_predictions is not None:
            spec.append(("prediction_confidence",
                         lambda f: draw_confidence_by_class(
                             f, cv_predictions, metrics)))

    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, draw in spec:
        fig = Figure(figsize=(6.0, 4.4), dpi=100)
        draw(fig)
        for fmt in formats:
            p = out_dir / f"{name}.{fmt}"
            fig.savefig(p, dpi=300, bbox_inches="tight")
            if name not in out:
                out[name] = p
    return out
