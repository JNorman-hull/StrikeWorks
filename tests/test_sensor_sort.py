"""Sort by for the sensor lists (modules/sensor_sort.py)."""
import unittest

from support import isolate, pump, qt_app


def _rows(*stems):
    return [{"stem": s} for s in stems]


class SortRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()

    def test_name_is_natural(self):
        from modules import sensor_sort as ss
        rows = _rows("B300-0924101751", "B61-0928151555", "B117-0928153351")
        self.assertEqual([r["stem"] for r in ss.sort_rows(rows, ss.NAME)],
                         ["B61-0928151555", "B117-0928153351", "B300-0924101751"])

    def test_recording_time(self):
        from modules import sensor_sort as ss
        rows = _rows("B61-0928151555", "no_time", "B300-0924101751",
                     "B117-0928153351")
        self.assertEqual([r["stem"] for r in ss.sort_rows(rows, ss.TIME)],
                         ["B300-0924101751", "B61-0928151555",
                          "B117-0928153351", "no_time"])

    def test_needs_review_first_is_stable(self):
        from modules import sensor_sort as ss
        rows = _rows("a", "b", "c", "d")
        flagged = {"c", "a"}
        self.assertEqual(
            [r["stem"] for r in ss.sort_rows(rows, ss.REVIEW,
                                             needs_review=flagged.__contains__)],
            ["a", "c", "b", "d"])
        self.assertEqual([r["stem"] for r in ss.sort_rows(rows, ss.REVIEW)],
                         ["a", "b", "c", "d"])

    def test_one_choice_for_every_list(self):
        from modules import sensor_sort as ss
        first, second = ss.SortControl(), ss.SortControl()
        seen = []
        second.changed.connect(seen.append)
        first.cmb.setCurrentIndex(first.cmb.findData(ss.TIME))
        self.assertEqual(ss.current(), ss.TIME)
        self.assertEqual(second.cmb.currentData(), ss.TIME)
        self.assertEqual(seen, [ss.TIME])
        ss.set_current(ss.REVIEW)
        # deleted now, not left to the garbage collector mid-way through a
        # later test
        for control in (first, second):
            control.deleteLater()
        pump(20)


if __name__ == "__main__":
    unittest.main()
