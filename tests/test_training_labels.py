"""Model training's labelling (ml_train_state.py, train_worker.py): the
user's choices, starting from the settings' "model_training" section
(shipped defaults: config/default_settings.json) - nothing guessed from
column names or values - and the strike-type breakdown."""
import unittest

import numpy as np
import pandas as pd

from support import isolate, pump, qt_app, temp_dir

_CHANNELS = ["higacc_x_g", "pressure_kpa"]


def _dataset(path, labels):
    """A small dataset: one 4-sample recording per row of `labels`."""
    rows = []
    for i, lab in enumerate(labels):
        for t in range(4):
            rows.append({"file": f"S{i}", "time_s": t / 2000,
                         **{c: float(np.sin(i + t)) for c in _CHANNELS}, **lab})
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


_LABELS = (
    [{"passage_type": "no_contact"}] * 6
    + [{"passage_type": "leading_edge", "leading_type": lt,
        "concentric_pump_region": r}
       for lt, r in zip(["direct", "indirect"] * 3, [1, 2, 3, 4, 5, 1])]
    + [{"passage_type": "other", "other_type": ot, "concentric_pump_region": r}
       for ot, r in zip(["hub_0", "hub_1", "hub_2", "surface"], [2, 3, 4, None])])


def TrainTab_(state):
    from modules.ml_tab_train_configure import TrainTab
    return TrainTab(state, None)


class Labelling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        isolate()
        self.dir = temp_dir()

    def test_starts_from_the_settings_choices(self):
        from modules.ml_train_state import TrainingState
        state = TrainingState()
        ok, msg = state.load_dataset_csv(_dataset(self.dir / "a.csv", _LABELS))
        self.assertTrue(ok, msg)
        self.assertEqual((state.target_column, state.negative_class,
                          state.region_column, state.breakdown_columns),
                         ("passage_type", "no_contact", "concentric_pump_region",
                          ["leading_type", "other_type"]))
        # each level its own class, named as the level - no presets
        self.assertEqual(state.region_groups,
                         [{"name": k, "levels": [k]} for k in "12345"])
        self.assertEqual(state.mc_breakdown_columns, ["leading_type", "other_type"])
        cfg = state.build_config()
        self.assertEqual(cfg["breakdown_columns"], ["leading_type", "other_type"])
        self.assertEqual(cfg["mc_breakdown_columns"],
                         ["leading_type", "other_type"])
        self.assertNotIn("include_surface_as_region1", cfg)

    def test_nothing_chosen_for_other_names(self):
        from modules.ml_train_state import TrainingState
        labels = [{"contact": "No contact" if i % 2 else "strike", "zone": i % 3}
                  for i in range(12)]
        state = TrainingState()
        state.load_dataset_csv(_dataset(self.dir / "b.csv", labels))
        self.assertIsNone(state.target_column)
        self.assertIsNone(state.negative_class)
        self.assertIsNone(state.region_column)
        self.assertFalse(state.ready)
        # chosen by the user, from the dropdowns' lists
        self.assertIn("contact", state.target_candidates())
        state.update(target_column="contact")
        self.assertIsNone(state.negative_class)        # not guessed
        self.assertIn("No contact", state.target_values())
        state.update(negative_class="No contact")
        self.assertEqual(state.binary_class_counts()[0], ("No contact", 6))

    def _train_tab(self):
        from modules.ml_tab_train_configure import TrainTab
        from modules.ml_train_state import TrainingState
        state = TrainingState()
        ok, msg = state.load_dataset_csv(_dataset(self.dir / "t.csv", _LABELS))
        self.assertTrue(ok, msg)
        tab = TrainTab(state, None)
        self.addCleanup(lambda: (tab.deleteLater(), pump(50)))
        return state, tab

    def _annotated(self):
        """Six recordings, two rows each: main and position annotations,
        numbers as numbers, some recordings with no value."""
        rows = []
        for n, (passage, leading, region, location) in enumerate(
                [("no_contact", "", "", ""), ("no_contact", "", "", 2),
                 ("leading_edge", "direct", 2, 1), ("leading_edge", "indirect", 10, 1),
                 ("leading_edge", "direct", 2, ""), ("other", "", 3, 2)]):
            for t in (0.0, 0.0005):
                rows.append({"file": f"S{n}", "time_s": t, "treatment": "A" if n < 3 else "B",
                             "pressure_kpa": 100.0, "passage_type": passage,
                             "leading_type": leading, "concentric_pump_region": region,
                             "strike_location": location})
        path = self.dir / "annotated.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_annotation_counts(self):
        from modules.ml_train_state import NOT_ANNOTATED, TrainingState
        state = TrainingState()
        state.load_dataset_csv(self._annotated())
        counts = {var.name: rows for var, rows in state.annotation_counts()}
        # main variables first, then position; only those the dataset has
        self.assertEqual(list(counts), ["passage_type", "leading_type",
                                        "concentric_pump_region", "strike_location"])
        self.assertEqual(counts["passage_type"],
                         [("leading_edge", 3), ("no_contact", 2), ("other", 1)])
        # numbers as written, in number order; a blank is "Not annotated"
        self.assertEqual(counts["concentric_pump_region"],
                         [("2", 2), ("3", 1), ("10", 1), (NOT_ANNOTATED, 2)])
        self.assertEqual(counts["strike_location"],
                         [("1", 2), ("2", 2), (NOT_ANNOTATED, 2)])
        for rows in counts.values():
            self.assertEqual(sum(n for _v, n in rows), 6)
        only = {var.name: rows for var, rows in state.annotation_counts(["S0", "S1"])}
        self.assertEqual(only["passage_type"], [("no_contact", 2)])

    def test_annotation_summary_follows_the_table_filter(self):
        from modules import tables
        from modules.ml_tab_train_configure import _ClassDist
        from modules.ml_train_state import TrainingState
        state = TrainingState()
        state.load_dataset_csv(self._annotated())
        tab = TrainTab_(state)
        self.addCleanup(lambda: (tab.deleteLater(), pump(50)))
        self.assertTrue(tab.btn_annotation_summary.isEnabled())
        window = tab.annotation_summary
        window.bring_up()
        pump(100)
        self.assertIn("annotated.csv - 6 recording(s)", window.lbl_source.text())
        dists = window.scroll.widget().findChildren(_ClassDist)
        self.assertEqual(len(dists), 4)
        self.assertEqual(dists[0]._rows, [("leading_edge", 3), ("no_contact", 2),
                                          ("other", 1)])

        tables.set_header_filter(tab.tbl_preview, "treatment", "B")
        window.refresh()
        self.assertIn("3 recording(s) of 6, filtered to treatment B", window.lbl_source.text())
        dists = window.scroll.widget().findChildren(_ClassDist)
        self.assertEqual(dists[0]._rows, [("leading_edge", 2), ("other", 1)])
        window.hide()

    def test_typing_a_class_name_keeps_the_field(self):
        """Each keystroke reaches the state without the grouping being
        rebuilt under the field being typed in."""
        from PySide6.QtTest import QTest
        state, tab = self._train_tab()
        state.update(train_multiclass=True)
        ed = tab.grouper._name_edits[0]
        QTest.keyClicks(ed, "_x")
        self.assertIs(tab.grouper._name_edits[0], ed)
        self.assertEqual(ed.text(), "1_x")
        self.assertEqual(state.region_groups[0]["name"], "1_x")

    def test_target_values_coded_0_1_or_excluded(self):
        """Each target value's row sets the null value (0) and the
        included values; the Null value dropdown follows."""
        state, tab = self._train_tab()
        rows = tab._value_combos
        self.assertEqual(
            {v: c.currentData() for v, c in rows.items()},
            {"no_contact": "null", "leading_edge": "positive",
             "other": "positive"})
        rows["other"].setCurrentIndex(rows["other"].findData("exclude"))
        self.assertEqual(state.include_values, {"no_contact", "leading_edge"})
        self.assertEqual(state.population_size(), 12)     # 6 + 6, other left out
        rows["leading_edge"].setCurrentIndex(rows["leading_edge"].findData("null"))
        self.assertEqual(state.negative_class, "leading_edge")
        self.assertEqual(tab.cmb_negative.currentData(), "leading_edge")
        self.assertEqual(rows["no_contact"].currentData(), "positive")
        # the null value chosen in the dropdown is always included
        tab.cmb_negative.setCurrentIndex(tab.cmb_negative.findData("other"))
        self.assertEqual(state.negative_class, "other")
        self.assertIsNone(state.include_values)

    def test_model_box_and_tooltips(self):
        """The Model box's numbered steps; the performance metric three to
        a column, the derived variables its tooltip, and the 0/1 coding
        the positive value's; the model card in a window of its own,
        closed with the page."""
        state, tab = self._train_tab()
        self.assertEqual(
            [b.text() for b in (tab.btn_train, tab.btn_evaluate,
                                tab.deployment.btn_final,
                                tab.deployment.btn_deploy)],
            ["(1) Train model (CV)", "(2) Evaluate performance",
             "(3) Train final model", "(4) Deploy model"])
        for key in ("binary", "multiclass"):
            grid = tab._breakdown_grids[key][1]
            for i, col in enumerate(state.breakdown_candidates()):
                self.assertIs(grid.itemAtPosition(i % 3, i // 3).widget(),
                              tab._breakdown_checks[key][col])
        self.assertIn("Derived variables: blade_strike (0/1), strike_type "
                      "for the binary model",
                      tab.lbl_metric.toolTip())
        # the multiclass model's own columns, and the variable's name
        tab._breakdown_checks["multiclass"]["other_type"].setChecked(False)
        self.assertEqual(state.mc_breakdown_columns, ["leading_type"])
        tab.ed_breakdown_name.setText("contact_type")
        tab.ed_breakdown_name.editingFinished.emit()
        self.assertEqual(state.build_config()["breakdown_name"], "contact_type")
        self.assertIn("contact_type for the multiclass model",
                      tab.lbl_metric.toolTip())
        # every sensor in the preview, filtered from its header
        from modules.tables import set_header_filter
        preview = tab.tbl_preview
        self.assertEqual(preview.rowCount(), len(_LABELS))
        set_header_filter(preview, "leading_type", "direct")
        shown = [r for r in range(preview.rowCount())
                 if not preview.isRowHidden(r)]
        self.assertEqual(len(shown), 3)
        col = next(c for c in range(preview.columnCount())
                   if preview.horizontalHeaderItem(c).text()
                   == "leading_type: direct")
        self.assertTrue(all(preview.item(r, col).text() == "direct"
                            for r in shown))
        set_header_filter(preview, "leading_type", None)
        self.assertFalse(any(preview.isRowHidden(r)
                             for r in range(preview.rowCount())))
        # the Model box: the Multiclass OOF card and the progress bar
        # shown before any run
        self.assertFalse(tab.card_mc.isHidden())
        self.assertEqual(tab.progress.format(), "Waiting for model run")
        self.assertIn('blade_strike = 1 where passage_type is any other '
                      'included value, 0 where it is "no_contact"',
                      tab.ed_positive.toolTip())
        info = tab.deployment.info
        tab.show()
        pump(50)
        info.bring_up()
        pump(50)
        self.assertTrue(info.isVisible())
        self.assertFalse(info.isModal())
        tab.hide()
        pump(50)
        self.assertFalse(info.isVisible())

    def test_strike_types_from_the_breakdown_columns(self):
        from modules.train_worker import derive_strike_type
        cfg = {"target_column": "passage_type", "negative_class": "no_contact",
               "breakdown_columns": ["leading_type", "other_type"]}
        cases = [({"passage_type": "no_contact", "other_type": "hub_1"},
                  "no_contact"),
                 ({"passage_type": "leading_edge", "leading_type": "direct"},
                  "direct"),
                 ({"passage_type": "other", "leading_type": None,
                   "other_type": "hub_2"}, "hub_2"),
                 ({"passage_type": "other"}, "other")]
        for row, expected in cases:
            self.assertEqual(derive_strike_type(pd.Series(row), cfg), expected)
        # the multiclass model's own columns
        row = pd.Series({"passage_type": "leading_edge",
                         "leading_type": "direct", "other_type": "hub_1"})
        self.assertEqual(derive_strike_type(row, cfg, ["other_type"]), "hub_1")
        from modules.train_worker import _by_strike_type
        res = pd.DataFrame({"file": ["a", "b", "c"],
                            "strike_type": ["x", "x", "y"],
                            "correct": [True, False, True]})
        self.assertEqual(_by_strike_type(res),
                         {"x": {"n_files": 2, "accuracy": 0.5},
                          "y": {"n_files": 1, "accuracy": 1.0}})
        self.assertEqual(_by_strike_type(res.drop(columns="strike_type")), {})

    def test_multiclass_measures_match_the_binary_ones(self):
        """The multiclass model's AUC, PR-AUC and specificity (each class
        against the rest, averaged), shown under the binary model's names
        - all but its threshold."""
        from sklearn.metrics import roc_auc_score
        from modules.ml_tab_train_configure import TrainTab
        from modules.train_worker import _macro_one_vs_rest
        rng = np.random.default_rng(1)
        y = np.repeat([0, 1, 2], 10)
        probs = rng.dirichlet([1, 1, 1], size=30)
        self.assertAlmostEqual(
            _macro_one_vs_rest(y, probs, roc_auc_score),
            roc_auc_score(y, probs, multi_class="ovr", average="macro"))
        perf = {"overall_accuracy": 0.6, "macro_recall": 0.5,
                "macro_specificity": 0.8, "macro_precision": 0.55,
                "macro_f1": 0.52, "macro_roc_auc": 0.75,
                "macro_pr_auc": 0.6, "mcc": 0.4}
        rows = TrainTab._perf_rows({"out_of_fold_performance": perf})
        self.assertEqual([label for label, _ in rows],
                         ["ROC AUC", "PR AUC", "Accuracy", "Sensitivity",
                          "Specificity", "Precision", "F1 score", "MCC"])
        self.assertEqual(dict(rows)["Sensitivity"], "0.500")


if __name__ == "__main__":
    unittest.main()
