"""What a model was trained on, read from its metrics as recorded
(modules/model_labels.py), and predictions compared with the annotations
only on those terms (ml_state.PredictionState.ground_truth_for)."""
import unittest

import pandas as pd

from support import isolate, qt_app

_BIN = {"training": {"target_column": "contact", "negative_class": "clear",
                     "breakdown_columns": ["kind"]}}
_MC = {"region_column": "hub_zone", "class_names": ["inner", "outer"],
       "region_to_class": {"a": 0, "b": 1, "2": 1}}


class ModelLabels(unittest.TestCase):
    def test_columns_from_the_metrics(self):
        from modules import model_labels as ml
        self.assertEqual(ml.label_columns(_BIN, _MC),
                         ["contact", "hub_zone", "kind"])
        # a region model trained before "region_column" was recorded
        self.assertEqual(ml.region_column(
            {"target": "concentric_pump_region (collapsed)"}),
            "concentric_pump_region")
        self.assertIsNone(ml.region_column(None))
        self.assertEqual(ml.label_columns({}, None), [])
        # as recorded - an older model's names are not translated
        old = {"training": {"target_column": "passage_type",
                            "negative_class": "No contact"}}
        self.assertEqual((ml.target_column(old), ml.negative_class(old)),
                         ("passage_type", "No contact"))

    def test_region_levels_match_training(self):
        from modules import model_labels as ml
        self.assertEqual(ml.region_class("b", _MC, _MC["class_names"]), "outer")
        # a number read back as a float is the same level
        self.assertEqual(ml.region_class(2.0, _MC, _MC["class_names"]), "outer")
        self.assertIsNone(ml.region_class("z", _MC, _MC["class_names"]))


class GroundTruth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()

    def _state(self, predictions):
        from modules.ml_state import PredictionState
        state = PredictionState()
        state.bin_metrics, state.mc_metrics = _BIN, _MC
        state.class_names = _MC["class_names"]
        state.predictions = predictions
        return state

    def test_compared_on_the_models_own_terms(self):
        preds = pd.DataFrame({"file": ["x", "y"], "contact": ["blade", "clear"],
                              "hub_zone": ["a", "b"]})
        state = self._state(preds)
        self.assertEqual(state.ground_truth_column(), "contact")
        self.assertEqual(state.ground_truth_for(preds.iloc[0]),
                         (True, "blade", "inner"))
        self.assertEqual(state.ground_truth_for(preds.iloc[1]),
                         (False, "clear", None))

    def test_not_compared_without_the_models_no_strike_value(self):
        # the target column is there, but its values are spelled otherwise
        preds = pd.DataFrame({"file": ["x"], "contact": ["Clear"]})
        state = self._state(preds)
        self.assertIsNone(state.ground_truth_column())
        self.assertEqual(state.ground_truth_for(preds.iloc[0]),
                         (None, None, None))
        self.assertIn("not compared", state.annotation_status(preds))
        # no target column at all
        preds = pd.DataFrame({"file": ["x"], "passage_type": ["no_contact"]})
        state = self._state(preds)
        self.assertIsNone(state.ground_truth_column())
        self.assertIn("none for this model", state.annotation_status(preds))


if __name__ == "__main__":
    unittest.main()
