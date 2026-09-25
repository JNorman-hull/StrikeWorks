"""Validation rules (flags, review order, Save + Next's target, the
counter) and the raw folder layout."""
import unittest

from support import temp_dir

from modules import raw_layout as rl
from modules import validation_core as vc

import pandas as pd


def _status(auto=(), user=(), flagged=(), bad=()):
    return set(auto), set(user), set(flagged), set(bad)


class ValidationRules(unittest.TestCase):
    def test_needs_review_is_flagged_and_not_reviewed(self):
        st = _status(auto="abc", user="b", flagged="ab")
        self.assertTrue(vc.needs_review("a", st))
        self.assertFalse(vc.needs_review("b", st))    # reviewed clears it
        self.assertFalse(vc.needs_review("c", st))    # never flagged

    def test_colours(self):
        st = _status(auto="abcd", user="b", flagged="ab", bad="d")
        colour = lambda s: vc.status_colour(s, st, "ok", "warn", "bad", "accent")
        self.assertEqual(colour("a"), "warn")
        self.assertEqual(colour("b"), "ok")
        self.assertEqual(colour("c"), "accent")
        self.assertEqual(colour("d"), "bad")
        self.assertIsNone(vc.status_colour("e", st, "ok", "warn", "bad", "accent"))

    def test_counter_counts_down(self):
        stems = ["a", "b", "c"]
        before = vc.counts_text(stems, _status(auto="abc", flagged="ab"))
        after = vc.counts_text(stems, _status(auto="abc", user="a", flagged="ab"))
        self.assertTrue(before.startswith("Flagged, to review: 2 of 2"))
        self.assertTrue(after.startswith("Flagged, to review: 1 of 2"))

    def test_next_after_save(self):
        order = ["f1", "f2", "f3", "p1", "p2"]         # flagged first
        after_f1 = _status(auto=order, user=["f1"], flagged=["f1", "f2", "f3"])
        self.assertEqual(vc.next_after_save(order, "f1", after_f1), "f2")
        # from the middle of the flagged group: the one after it
        after_f2 = _status(auto=order, user=["f2"], flagged=["f1", "f2", "f3"])
        self.assertEqual(vc.next_after_save(order, "f2", after_f2), "f3")
        # last flagged saved, one skipped earlier: back to that one
        after_f3 = _status(auto=order, user=["f2", "f3"], flagged=["f1", "f2", "f3"])
        self.assertEqual(vc.next_after_save(order, "f3", after_f3), "f1")
        # nothing flagged left: simply the next in the list, then the end
        done = _status(auto=order, user=["f1", "f2", "f3"], flagged=["f1", "f2", "f3"])
        self.assertEqual(vc.next_after_save(order, "f3", done), "p1")
        self.assertIsNone(vc.next_after_save(order, "p2", done))

    def test_all_validated(self):
        stems = ["a", "b"]
        self.assertFalse(vc.all_validated(stems, _status(auto="ab", flagged="a")))
        self.assertTrue(vc.all_validated(stems, _status(auto="ab", user="a", flagged="a")))

    def test_save_window_flags_on_weak_hig(self):
        lib = temp_dir("lib_")
        n = 2000
        time = [i / 2000 for i in range(n)]
        df = pd.DataFrame({"time_s": time,
                           "pressure_kpa": [100 - (i == 1000) for i in range(n)],
                           "higacc_mag_g": [300.0 if i == 1000 else 1.0 for i in range(n)]})
        index = vc.save_window(lib, None, "strong", df, 1000, 0.2)
        weak = df.assign(higacc_mag_g=1.0)
        index = vc.save_window(lib, index, "weak", weak, 1000, 0.2, user_validated=True)
        row = index.set_index("file")
        self.assertEqual(row.loc["strong", vc.FLAGGED_COL], "N")
        self.assertEqual(row.loc["weak", vc.FLAGGED_COL], "Y")
        self.assertEqual(row.loc["weak", vc.USER_VALIDATED_COL], "Y")
        self.assertTrue((lib / vc.WIN_DIR / "strong_200ms.csv").exists())


class RawLayout(unittest.TestCase):
    def test_run_names(self):
        self.assertEqual(rl.run_folder_name(3), "Run 3")
        for name in ("Run 2", "run_2", "RUN-2", " run 2 "):
            self.assertEqual(rl.run_label(name), "2")
        self.assertIsNone(rl.run_label("Treatment 1"))

    def test_scan_tree(self):
        lib = temp_dir("lib_")
        run = rl.run_dir(lib, "Dep", "T1", 2)
        (run / "VIDEO").mkdir(parents=True)
        for ext in (".IMP", ".HIG"):
            (run / f"B61-0703140718{ext}").write_bytes(b"x")
        (run / "VIDEO" / "B61-0703140718_vid_1.mp4").write_bytes(b"x")
        legacy = rl.treatment_dir(lib, "Dep", "Old")      # no Run level
        legacy.mkdir(parents=True)
        (legacy / "B62-0703140412.IMP").write_bytes(b"x")

        tree = rl.scan_tree(rl.raw_root(lib))
        self.assertEqual(tree.locations["B61-0703140718"][:3], ("Dep", "T1", "2"))
        self.assertEqual(len(tree.files["B61-0703140718"]), 2)
        self.assertEqual(len(tree.videos["B61-0703140718"]), 1)
        self.assertEqual(tree.locations["B62-0703140412"][:3], ("Dep", "Old", "1"))

    def test_processed_csvs(self):
        lib = temp_dir("lib_")
        csv_dir = lib / rl.CSV_DIR
        csv_dir.mkdir(parents=True)
        for name in ("B61-0703140718.csv", "B61-0703140718_min.csv",
                     "B62-0703140412.csv", "notes.txt"):
            (csv_dir / name).write_text("x")
        self.assertEqual([p.name for p in rl.processed_csvs(lib)],
                         ["B61-0703140718.csv", "B62-0703140412.csv"])
        self.assertEqual(rl.processed_csvs(temp_dir("empty_")), [])

    def test_video_index(self):
        libs = temp_dir("libs_")
        for lib in ("A", "B"):
            video = rl.run_dir(libs / lib, "Dep", "T1", 1) / "VIDEO"
            video.mkdir(parents=True)
            (video / "B61-0703140718_vid_1.mp4").write_bytes(b"x")
        index = rl.video_index(libs)
        self.assertEqual(len(index["B61-0703140718"]), 2)


if __name__ == "__main__":
    unittest.main()
