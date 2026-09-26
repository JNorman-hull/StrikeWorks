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
        settings.set_dev_mode(True)
        self.assertTrue(settings.get_dev_mode())

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
