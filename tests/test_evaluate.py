"""Evaluate and the names every model's measures go by (model_measures):
one summary table with each measure once, per-class rows from the
confusion matrix, and the figures laid out for each kind of model."""
import unittest

import numpy as np
import pandas as pd

from support import isolate, pump, qt_app, temp_dir

_BIN = {
    "n_samples": 20,
    "out_of_fold_performance": {
        "roc_auc": 0.9, "pr_auc": 0.8, "overall_accuracy": 0.85,
        "sensitivity": 0.8, "specificity": 0.9, "precision": 0.89,
        "f1_score": 0.84, "mcc": 0.7, "FNR": 0.2, "FPR": 0.1,
        "optimal_threshold": 0.45,
        "confusion_matrix": {"tn": 9, "fp": 1, "fn": 2, "tp": 8}},
    "cross_validation": {"n_folds": 5, "mean_auc": 0.91, "std_auc": 0.02,
                         "mean_accuracy": 0.84, "std_accuracy": 0.03}}
_MC = {
    "n_samples": 20, "class_names": ["a", "b"],
    "out_of_fold_performance": {
        "overall_accuracy": 0.7, "macro_recall": 0.7, "macro_precision": 0.7,
        "macro_f1": 0.7, "confusion_matrix": [[8, 2], [4, 6]]}}


class Measures(unittest.TestCase):
    def test_one_name_per_measure_for_both_models(self):
        from modules import model_measures as mm
        bcols, brows = mm.summary_table(_BIN)
        mcols, mrows = mm.summary_table(_MC)
        names = [n for _g, n in bcols]
        self.assertEqual(names, ["ROC AUC", "PR AUC", "Accuracy",
                                 "Sensitivity", "Specificity", "Precision",
                                 "F1 score", "MCC", "Decision threshold", "n"])
        # the same names for the multiclass model, but no threshold
        self.assertEqual([n for _g, n in mcols],
                         [n for n in names if n != "Decision threshold"])
        # FNR and FPR are 1 - sensitivity and 1 - specificity: not shown
        self.assertEqual(len(set(names)), len(names))
        oof = dict(zip(names, brows[0][1]))
        self.assertEqual((oof["ROC AUC"], oof["Decision threshold"], oof["n"]),
                         ("0.900", "0.450", "20"))
        cv_label, cv_cells = brows[1]
        self.assertIn("5 folds", cv_label)
        self.assertEqual(dict(zip(names, cv_cells))["ROC AUC"], "0.91 ± 0.02")
        # an older multiclass model: specificity from its confusion matrix
        moof = dict(zip([n for _g, n in mcols], mrows[0][1]))
        self.assertEqual(moof["Sensitivity"], "0.700")
        self.assertEqual(moof["Specificity"], "0.700")   # (6/10 + 8/10) / 2
        self.assertEqual(moof["ROC AUC"], "-")

    def test_classes_from_the_confusion_matrix(self):
        from modules import model_measures as mm
        rows = {r[0]: r for r in mm.class_table(_BIN)}
        self.assertEqual(list(rows), ["No strike", "Strike"])
        # Strike: 8 of 10 found; 9 of 10 no-strikes left out; 8 of 9 calls right
        self.assertEqual(rows["Strike"][1:5], ["10", "0.800", "0.900", "0.889"])
        rows = {r[0]: r for r in mm.class_table(_MC)}
        self.assertEqual(rows["b"][1:4], ["10", "0.600", "0.800"])


class EvaluatePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()

    def test_layout_for_each_kind_of_model(self):
        from modules.ml_model_library import ModelEntry
        from modules.ml_tab_train_evaluate import EvaluateTab
        tab = EvaluateTab(None, None, models_dir=temp_dir())
        self.addCleanup(lambda: (tab.deleteLater(), pump(50)))
        tab.resize(1000, 900)
        tab.show()
        pump(100)
        rng = np.random.default_rng(0)
        cv = pd.DataFrame({"file": list("abcdefghij"), "treatment": "A",
                           "y_true": [0, 1] * 5, "y_pred": [0, 1] * 5,
                           "correct": True, "probability": rng.random(10)})
        tab._entries = [ModelEntry("bin", "binary", _BIN, cv, None),
                        ModelEntry("mc", "multiclass", _MC, None, None)]
        for i, (shown, hidden) in enumerate((
                ({"roc", "pr", "confusion", "probability", "by_type"},
                 {"by_class"}),
                ({"roc", "confusion", "by_class", "probability", "by_type"},
                 {"pr"}))):
            tab.cmb_model.blockSignals(True)
            tab.cmb_model.clear()
            tab.cmb_model.addItems(["bin", "mc"])
            tab.cmb_model.setCurrentIndex(i)
            tab.cmb_model.blockSignals(False)
            tab._on_model_changed()
            pump(50)
            self.assertEqual({r for r, c in tab.canvases.items()
                              if c.isVisible()}, shown)
            self.assertTrue(all(tab.canvases[r].isHidden() for r in hidden))
            self.assertEqual(tab.canvases["roc"].height(), 300)
        # the multiclass halves are equal
        self.assertEqual(tab.canvases["roc"].width(),
                         tab.canvases["confusion"].width())
        self.assertFalse(tab.lbl_averaged.isHidden())
        self.assertEqual(tab.tbl_class.item(0, 0).text(), "a")
        # no Models folder or Export model report here any more
        from PySide6.QtWidgets import QPushButton
        self.assertEqual([b.text() for b in tab.findChildren(QPushButton)],
                         ["Refresh"])


if __name__ == "__main__":
    unittest.main()
