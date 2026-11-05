"""The one settings file: first-start migration from the older home-folder
files, sections, and the recent-datasets list."""
import json
import unittest

from support import temp_dir

from modules import settings


class SettingsFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir()
        self._saved = (settings.SETTINGS_FILE, settings._LEGACY_FILES)
        settings.SETTINGS_FILE = self.dir / "AppData" / "StrikeWorks" / "settings.json"
        self.old_app = self.dir / ".hifistrike_settings.json"
        self.old_sensors = self.dir / ".strikeworks_sensors.json"
        self.old_notes = self.dir / ".strikeworks_annotations.json"
        settings._LEGACY_FILES = {
            None: self.old_app,
            "sensor_configs": self.old_sensors,
            "annotation_variables": self.old_notes,
        }

    def tearDown(self):
        settings.SETTINGS_FILE, settings._LEGACY_FILES = self._saved

    def test_first_start_reads_the_old_files_once(self):
        self.old_app.write_text(json.dumps({"libraries_dir": "D:/libs"}))
        self.old_sensors.write_text(json.dumps({"active": "rapid", "sensors": []}))
        self.old_notes.write_text(json.dumps({"variables": [{"name": "x"}]}))

        self.assertEqual(str(settings.get_libraries_dir()), str(settings.Path("D:/libs")))
        self.assertTrue(settings.SETTINGS_FILE.exists())
        self.assertEqual(settings.read_section("sensor_configs")["active"], "rapid")
        self.assertEqual(settings.read_section("annotation_variables"),
                         {"variables": [{"name": "x"}]})

        # later changes to the old files are ignored; they stay in place
        self.old_app.write_text(json.dumps({"libraries_dir": "E:/other"}))
        self.assertEqual(str(settings.get_libraries_dir()), str(settings.Path("D:/libs")))
        self.assertTrue(self.old_app.exists())

    def test_no_old_files_means_defaults(self):
        self.assertEqual(settings.get_libraries_dir(), settings._DEFAULT_LIBRARIES)
        self.assertFalse(settings.SETTINGS_FILE.exists())
        settings.set_last_library(self.dir)
        self.assertEqual(settings.get_last_library(), self.dir)

    def test_sections_and_app_keys_are_kept_apart(self):
        settings.set_models_dir(self.dir / "models")
        settings.write_section("sensor_configs", {"active": "micro_eel"})
        settings.set_output_dir(self.dir / "out")
        self.assertEqual(settings.read_section("sensor_configs"), {"active": "micro_eel"})
        self.assertEqual(settings.get_models_dir(), self.dir / "models")

    def test_where_the_file_lives(self):
        import os
        import sys
        from unittest import mock
        with mock.patch.dict(os.environ, {"STRIKEWORKS_SETTINGS": ""}):
            with mock.patch.object(sys, "frozen", True, create=True):
                # packaged: beside the exe, so the folder is self-contained
                self.assertEqual(settings.settings_path(),
                                 settings.app_root() / "settings.json")
            with mock.patch.dict(os.environ, {"APPDATA": str(self.dir)}):
                self.assertEqual(settings.settings_path(),
                                 self.dir / "StrikeWorks" / "settings.json")
        with mock.patch.dict(os.environ, {"STRIKEWORKS_SETTINGS": str(self.dir / "x.json")}):
            self.assertEqual(settings.settings_path(), self.dir / "x.json")

    def test_recent_datasets_keep_existing_absolute_paths(self):
        real = self.dir / "a.csv"
        real.write_text("x\n1\n")
        settings._save({"recent_training_datasets": [
            "input_data\\relative.csv", str(self.dir / "missing.csv"), str(real)]})
        self.assertEqual(settings.get_recent_training_datasets(), [str(real)])

        other = self.dir / "b.csv"
        other.write_text("x\n1\n")
        settings.add_recent_training_dataset(other)
        self.assertEqual(settings.get_recent_training_datasets(),
                         [str(other.resolve()), str(real)])


if __name__ == "__main__":
    unittest.main()


class DefaultModelsTest(unittest.TestCase):
    """The default models pinned in Settings are the ones selected - at
    start-up, on a folder change, even from another folder - and a rescan
    keeps the model already selected."""

    def setUp(self):
        from support import qt_app
        qt_app()
        self.dir = temp_dir()
        self._saved = settings.SETTINGS_FILE
        settings.SETTINGS_FILE = self.dir / "settings.json"
        self.models = self.dir / "models"
        self.other = self.dir / "elsewhere"
        for folder, names in ((self.models, ("binary1", "binary1_4")),
                              (self.other, ("binary2",))):
            folder.mkdir()
            (folder / "performance_metrics.json").write_text("{}")
            for name in names:
                (folder / f"{name}.joblib").write_text("")
        settings.set_models_dir(self.models)

    def tearDown(self):
        settings.SETTINGS_FILE = self._saved

    def _state(self):
        from modules.ml_state import PredictionState
        return PredictionState()

    def test_unpinned_is_binary1(self):
        state = self._state()
        state.use_default_models()
        self.assertEqual(state.bin_model_path.stem, "binary1")

    def test_pinned_in_the_folder(self):
        settings.set_default_model(self.models / "binary1_4.joblib")
        state = self._state()
        state.use_default_models()
        self.assertEqual(state.bin_model_path.stem, "binary1_4")
        # a rescan (after a deploy) keeps what's selected
        state.select_bin_model(self.models / "binary1.joblib")
        state.load_models_from_dir(self.models)
        self.assertEqual(state.bin_model_path.stem, "binary1")

    def test_pinned_from_another_folder(self):
        settings.set_default_model(self.other / "binary2.joblib")
        state = self._state()
        state.use_default_models()
        self.assertEqual(state.bin_model_path.stem, "binary2")
        self.assertIn(self.other / "binary2.joblib", state.bin_candidates)
