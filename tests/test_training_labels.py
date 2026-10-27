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
        cfg = state.build_config()
        self.assertEqual(cfg["breakdown_columns"], ["leading_type", "other_type"])
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


if __name__ == "__main__":
    unittest.main()
