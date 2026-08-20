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
stack. Publication-styled on white, like all StrikeWorks figures.
"""
import numpy as np

_MUTED = "#94a3b8"
_PALETTE = ["#2196F3", "#E91E63", "#FF9800", "#4CAF50", "#9C27B0", "#00BCD4"]


def _empty(fig, msg="No cross-validation run"):
    fig.clear()
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, msg, ha="center", va="center",
            transform=ax.transAxes, color=_MUTED, fontsize=10)
    ax.set_axis_off()
    fig.tight_layout()


# ── binary figures ───────────────────────────────────────────────────────────

def draw_roc(fig, curves, metrics):
    if not curves or "fpr" not in curves:
        _empty(fig)
        return
    fig.clear()
    ax = fig.add_subplot(111)
    fpr = np.asarray(curves["fpr"])
    tpr = np.asarray(curves["tpr"])
    perf = metrics["out_of_fold_performance"]
    opt = int(curves.get("roc_optimal_idx", 0))

    ax.plot(fpr, tpr, "b-", lw=2.2,
            label=f"ROC curve (AUC = {perf['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1.2, alpha=0.5, label="Random classifier")
    ax.scatter(fpr[opt], tpr[opt], c="red", s=90, zorder=5,
               edgecolors="black", lw=1.2,
               label=f"Optimal threshold = {perf['optimal_threshold']:.3f}")
    ax.set_xlabel("False positive rate", fontsize=9)
    ax.set_ylabel("True positive rate", fontsize=9)
    ax.set_title("ROC curve (out-of-fold)", fontsize=10, fontweight="bold")
    ax.legend(loc="lower right", fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()


def draw_pr(fig, curves, metrics):
    if not curves or "precision" not in curves:
        _empty(fig)
        return
    fig.clear()
    ax = fig.add_subplot(111)
    perf = metrics["out_of_fold_performance"]
    ax.plot(curves["recall"], curves["precision"], "g-", lw=2.2,
            label=f"PR curve (AUC = {perf['pr_auc']:.3f})")
    base = curves.get("baseline_rate")
    if base is not None:
        ax.axhline(y=base, color="gray", linestyle="--", lw=1.2,
                   label=f"Baseline (strike rate = {base:.3f})")
    ax.set_xlabel("Recall", fontsize=9)
    ax.set_ylabel("Precision", fontsize=9)
    ax.set_title("Precision–recall curve (out-of-fold)",
                 fontsize=10, fontweight="bold")
    ax.legend(loc="lower left", fontsize=7)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.grid(alpha=0.3)
    fig.tight_layout()


def _heatmap(ax, cm, labels, title):
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


def draw_confusion_binary(fig, metrics):
    perf = (metrics or {}).get("out_of_fold_performance", {})
    cm = perf.get("confusion_matrix")
    if not cm:
        _empty(fig)
        return
    fig.clear()
    ax = fig.add_subplot(111)
    mat = [[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]]
    _heatmap(ax, mat, ["No strike", "Strike"],
             f"Confusion matrix (accuracy = {perf['overall_accuracy']:.3f})")
    fig.tight_layout()


def draw_probability_distribution(fig, cv_predictions, metrics):
    if cv_predictions is None or "probability" not in cv_predictions.columns:
        _empty(fig)
        return
    fig.clear()
    ax = fig.add_subplot(111)
    perf = metrics["out_of_fold_performance"]
    y = cv_predictions["y_true"].values
    p = cv_predictions["probability"].values
    bins = np.linspace(0, 1, 21)
    ax.hist(p[y == 0], bins=bins, alpha=0.6,
            label=f"No strike (n={int((y == 0).sum())})",
            color="steelblue", edgecolor="black", lw=0.5)
    ax.hist(p[y == 1], bins=bins, alpha=0.6,
            label=f"Strike (n={int((y == 1).sum())})",
            color="tomato", edgecolor="black", lw=0.5)
    ax.axvline(perf["optimal_threshold"], color="green", linestyle="--",
               lw=1.8,
               label=f"Optimal threshold ({perf['optimal_threshold']:.3f})")
    ax.set_xlabel("Predicted probability", fontsize=9)
    ax.set_ylabel("Frequency", fontsize=9)
    ax.set_title("Out-of-fold predicted probabilities",
                 fontsize=10, fontweight="bold")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()


def draw_accuracy_by_type(fig, metrics):
    by_type = (metrics or {}).get("performance_by_strike_type", {})
    if not by_type:
        _empty(fig, "No strike-type information")
        return
    fig.clear()
    ax = fig.add_subplot(111)
    perf = metrics["out_of_fold_performance"]
    names = list(by_type.keys())
    accs = [by_type[n]["accuracy"] for n in names]
    ns = [by_type[n]["n_files"] for n in names]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]
    bars = ax.bar(range(len(names)), accs, color=colors,
                  edgecolor="black", width=0.6)
    ax.axhline(y=perf["overall_accuracy"], color="black", linestyle="--",
               lw=1.2,
               label=f"Overall accuracy ({perf['overall_accuracy']:.3f})")
    for bar, acc, n in zip(bars, accs, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{acc:.2f}\nn={n}", ha="center", fontsize=7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Accuracy", fontsize=9)
    ax.set_title("Accuracy by strike type", fontsize=10, fontweight="bold")
    ax.set_ylim([0, 1.12])
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()


# ── multiclass figures ───────────────────────────────────────────────────────

def draw_confusion_multiclass(fig, metrics):
    perf = (metrics or {}).get("out_of_fold_performance", {})
    cm = perf.get("confusion_matrix")
    names = (metrics or {}).get("class_names")
    if cm is None or not names:
        _empty(fig)
        return
    fig.clear()
    ax = fig.add_subplot(111)
    _heatmap(ax, cm, names,
             f"Confusion matrix (accuracy = {perf['overall_accuracy']:.3f})")
    fig.tight_layout()


def draw_per_class_recall(fig, metrics):
    perf = (metrics or {}).get("out_of_fold_performance", {})
    per_class = perf.get("per_class_metrics")
    if not per_class:
        _empty(fig)
        return
    fig.clear()
    ax = fig.add_subplot(111)
    names = list(per_class.keys())
    recalls = [per_class[n]["recall"] for n in names]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]
    bars = ax.bar(names, recalls, color=colors, edgecolor="black", width=0.6)
    ax.axhline(y=perf["overall_accuracy"], color="black", linestyle="--",
               lw=1.2,
               label=f"Overall accuracy ({perf['overall_accuracy']:.3f})")
    for bar, v in zip(bars, recalls):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{v:.3f}", ha="center", fontsize=8)
    ax.set_ylabel("Recall", fontsize=9)
    ax.set_ylim([0, 1.1])
    ax.set_title("Per-class recall", fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()


def draw_confidence_by_class(fig, cv_predictions, metrics):
    names = (metrics or {}).get("class_names")
    if cv_predictions is None or not names \
            or "true_class" not in cv_predictions.columns:
        _empty(fig)
        return
    fig.clear()
    axes = fig.subplots(1, len(names), squeeze=False)
    for i, cn in enumerate(names):
        ax = axes[0, i]
        col = f"prob_{cn}"
        mask = cv_predictions["true_class"] == cn
        if col in cv_predictions.columns and mask.any():
            ax.hist(cv_predictions.loc[mask, col], bins=15, alpha=0.75,
                    edgecolor="black", color=_PALETTE[i % len(_PALETTE)])
        ax.set_xlabel("P(true class)", fontsize=8)
        if i == 0:
            ax.set_ylabel("Frequency", fontsize=8)
        ax.set_title(f"True: {cn}\n(n={int(mask.sum())})", fontsize=8,
                     fontweight="bold")
        ax.set_xlim([0, 1])
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
    fig.suptitle("Prediction confidence by true class", fontsize=10,
                 fontweight="bold")
    fig.tight_layout()


def draw_all(figures, metrics, cv_predictions, curves):
    """Redraw every evaluation figure for one model's results.

    `figures` maps name -> Figure. Unused figures are cleared to a note.
    """
    if metrics is None:
        for f in figures.values():
            _empty(f)
        return
    binary = "roc_auc" in metrics.get("out_of_fold_performance", {})

    if binary:
        draw_roc(figures["fig1"], curves, metrics)
        draw_pr(figures["fig2"], curves, metrics)
        draw_confusion_binary(figures["fig3"], metrics)
        draw_probability_distribution(figures["fig4"], cv_predictions,
                                      metrics)
        draw_accuracy_by_type(figures["fig5"], metrics)
    else:
        draw_confusion_multiclass(figures["fig1"], metrics)
        draw_per_class_recall(figures["fig2"], metrics)
        draw_confidence_by_class(figures["fig3"], cv_predictions, metrics)
        _empty(figures["fig4"], "Binary-only figure")
        _empty(figures["fig5"], "Binary-only figure")
