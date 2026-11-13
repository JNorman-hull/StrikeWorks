"""Blade strike model and Wilson interval - pinned to the values the app
produced before the refactor, so moving code around can't change them."""
import unittest

from support import BSM_CONFIG  # noqa: F401  (sets sys.path)

from modules.bsm_config import load_config
from modules.bsm_model import (compute, mortality_from_strike_rate,
                               sensitivity_sweeps, sweep_q_multipliers)
from modules.wilson_calc import required_n, wilson_interval


class BSMModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.params = load_config(BSM_CONFIG)

    def test_scaly(self):
        r = compute(dict(self.params, species="scaly"))
        self.assertAlmostEqual(r["Pco_tip"], 0.45331901578188577, places=12)
        self.assertAlmostEqual(r["Pm"], 0.17728337594996568, places=12)
        self.assertAlmostEqual(r["fMR_tip"], 0.8431812172158912, places=12)

    def test_eel(self):
        r = compute(dict(self.params, species="eel"))
        self.assertAlmostEqual(r["Pco_tip"], 0.3544097312358812, places=12)
        self.assertAlmostEqual(r["Pm"], 0.003303846249892599, places=12)

    def test_observed_counts(self):
        r = compute(dict(self.params, use_observed=True, total=200, strike=80))
        self.assertAlmostEqual(r["Pm_obs"], 0.15521489209875397, places=12)
        self.assertAlmostEqual(r["wilson_lo"], 0.3346046396837895, places=12)
        self.assertAlmostEqual(r["wilson_hi"], 0.46916456149987484, places=12)

    def test_model_projected_mortality_matches_observed_formula(self):
        r = compute(dict(self.params, use_observed=True, total=200, strike=80))
        self.assertAlmostEqual(mortality_from_strike_rate(r, r["Pco_obs"]),
                               r["Pm_obs"], places=12)

    def test_sensitivity_sweeps(self):
        s = sensitivity_sweeps(self.params)
        for key in ("pco_n", "pm_n", "pco_wf", "pm_wf"):
            self.assertEqual(len(s[key]), 6)
        # the design line passes through the design point's own result
        _x, pco = s["pco_n"][s["design_label"]]
        self.assertAlmostEqual(pco[20], 45.33190157818858, places=9)

    def test_sweep_ranges(self):
        """Calculator's Advanced options: Q lines from / to a step
        apart, the design Q always one; N between its multiples."""
        self.assertEqual(sweep_q_multipliers(),
                         [0.6, 0.8, 1.0, 1.2, 1.4, 1.6])
        self.assertEqual(sweep_q_multipliers((0.5, 1.5), 0.2),
                         [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5])
        s = sensitivity_sweeps(self.params, q_span=(1.2, 1.6), q_step=0.4,
                               n_span=(0.5, 1.5))
        self.assertEqual(len(s["pco_n"]), 3)        # 1.0, 1.2, 1.6
        n, _y = s["pco_n"][s["design_label"]]
        design_n = self.params["N"]
        self.assertAlmostEqual(n[0], design_n * 0.5)
        self.assertAlmostEqual(n[-1], design_n * 1.5)


class Wilson(unittest.TestCase):
    def test_interval(self):
        lo, hi, half = wilson_interval(0.3, 50, 95)
        self.assertAlmostEqual(lo, 0.1910338908960936, places=12)
        self.assertAlmostEqual(hi, 0.4375061227736339, places=12)
        self.assertAlmostEqual(half, 0.12323611593877014, places=12)
        lo, hi, _ = wilson_interval(0.1, 200, 90)
        self.assertAlmostEqual(lo, 0.07027110227833182, places=12)
        self.assertAlmostEqual(hi, 0.14040662624548866, places=12)

    def test_no_trials(self):
        self.assertIsNone(wilson_interval(0.5, 0, 95))

    def test_required_n(self):
        self.assertEqual(required_n(0.1, 0.05, 95), 141)
        self.assertEqual(required_n(0.45, 0.10, 95), 92)


if __name__ == "__main__":
    unittest.main()
