"""Annotation variables (modules/annotation_schema.py): read from the
settings file, else the shipped defaults; the position group and its
checkbox on Annotate; Misclassification's corrections reaching the
library's sensor index."""
import json
import unittest

import pandas as pd

from support import isolate, main_window, pump, qt_app


def _fresh_schema():
    from modules import annotation_schema as asch
    asch._store = None
    return asch


class Variables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        self.env = isolate()

    def tearDown(self):
        _fresh_schema()

    def test_the_shipped_defaults_until_the_settings_have_their_own(self):
        from modules import settings
        asch = _fresh_schema()
        shipped = json.loads(settings.DEFAULTS_FILE.read_text(encoding="utf-8"))
        names = [v["name"] for v in shipped["annotation_variables"]["variables"]]
        self.assertEqual([v.name for v in asch.all_variables()], names)
        self.assertEqual(
            [v.name for v in asch.all_variables(asch.POSITION_GROUP)],
            [v["name"] for v in shipped["annotation_variables"]["variables"]
             if v["group"] == asch.POSITION_GROUP])
        self.assertFalse(asch.show_position())          # unticked
        # once the settings file has its own list, that is the list - as it
        # is: nothing added, renamed or recoded
        settings.write_section("annotation_variables", {"variables": [
            {"name": "contact", "label": "Contact", "values": ["No contact"]}]})
        asch = _fresh_schema()
        self.assertEqual([(v.name, v.values) for v in asch.all_variables()],
                         [("contact", ["No contact"])])

    def test_edits_are_written_to_the_settings_file(self):
        from modules import settings
        asch = _fresh_schema()
        asch.add_value("other_type", "hub_3")
        saved = json.loads(settings.SETTINGS_FILE.read_text())
        other = next(v for v in saved["annotation_variables"]["variables"]
                     if v["name"] == "other_type")
        self.assertEqual(other["values"][-1], "hub_3")

    def test_moving_a_variable_between_groups(self):
        from modules.annotation_widgets import VariableListDialog
        asch = _fresh_schema()
        dlg = VariableListDialog()
        main = dlg.lists[asch.MAIN_GROUP]
        main.setCurrentRow(1)                       # leading_type
        dlg._move_selected()
        self.assertEqual(asch.get("leading_type").group, asch.POSITION_GROUP)
        self.assertEqual(dlg.lists[asch.POSITION_GROUP].count(),
                         len(asch.all_variables(asch.POSITION_GROUP)))
        from PySide6.QtCore import Qt
        position = dlg.lists[asch.POSITION_GROUP]
        row = next(i for i in range(position.count())
                   if position.item(i).data(Qt.ItemDataRole.UserRole)
                   == "leading_type")
        position.setCurrentRow(row)
        dlg._move_selected()
        self.assertEqual(asch.get("leading_type").group, asch.MAIN_GROUP)
        # deleted now, not left to the garbage collector (its signal
        # lambdas hold it in a cycle) to delete in the middle of a later
        # test's stylesheet repolish
        dlg.close()
        dlg.deleteLater()
        pump(50)

class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        cls.env = isolate()
        _fresh_schema()
        cls.main, cls.window = main_window()
        cls.window.resize(1400, 900)
        cls.window.show()
        cls.window.expand_sidebar()
        pump(200)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        _fresh_schema()

    def test_position_annotations_checkbox(self):
        from modules import annotation_schema as asch
        page = self.window.annotation_page
        self.window.navigate_to("btn_annotate")
        win = page.annotations           # the Annotations and notes window
        win.bring_up()
        pump(100)
        try:
            self.assertIn("strike_location", win._editors)
            win.chk_position.setChecked(False)
            pump(20)
            self.assertFalse(win.position_box.isVisible())
            win.chk_position.setChecked(True)
            pump(20)
            self.assertTrue(win.position_box.isVisible())
            self.assertTrue(asch.show_position())
            win.chk_position.setChecked(False)
            self.assertFalse(asch.show_position())
        finally:
            win.hide()

    def test_strikeworks_validate_is_the_same_page(self):
        """StrikeWorks's Validate step is Validate and annotate itself -
        filters, Annotations and notes, the export's name."""
        from modules.page_annotate import AnnotationPage
        page = self.window.simple_mode_dialog.validate_page
        self.assertIs(type(page), AnnotationPage)
        self.assertIs(self.window.simple_mode_dialog.validation, page.view)
        self.assertEqual(page.view.export_name, page._export_name)

    def test_deployment_filter_waits_for_the_scan(self):
        """select_deployment before the library's scan applies once the
        scan has filled the filter in (StrikeWorks's Validate step)."""
        from modules import raw_layout
        sel = self.window.simple_mode_dialog.validate_page.lib_selector
        tree = raw_layout.RawTree()
        tree.locations = {"S1": ("DEP_A", "T1", "1", None),
                          "S2": ("DEP_B", "T1", "1", None)}
        sel._tree = None
        sel.select_deployment("DEP_B")
        self.assertIsNone(sel.wanted_deployment())
        sel._scan_gen += 1
        sel._apply_tree(sel._scan_gen, tree)
        self.assertEqual(sel.wanted_deployment(), "DEP_B")
        sel.select_deployment("DEP_A")       # scanned: straight away
        self.assertEqual(sel.wanted_deployment(), "DEP_A")
        sel.cmb_deployment.setCurrentIndex(0)

    def test_annotations_window_closes_with_its_page(self):
        page = self.window.annotation_page
        self.window.navigate_to("btn_annotate")
        pump(50)
        page.annotations.bring_up()
        pump(50)
        self.assertTrue(page.annotations.isVisible())
        self.window.navigate_to("btn_ml_training")
        pump(50)
        self.assertFalse(page.annotations.isVisible())

    def test_annotations_window_follows_the_sensor(self):
        """It shows the loaded sensor's values from the index, and Save +
        Next writes what's entered (nothing when nothing is)."""
        page = self.window.annotation_page
        win = page.annotations
        page._index_df = pd.DataFrame([{"file": "S1", "passage_type": "other",
                                        "notes": "seen twice"}])
        win.set_sensor("S1")
        self.assertEqual(win.lbl_sensor.text(), "S1")
        self.assertEqual(win._editors["passage_type"].current(), "other")
        self.assertEqual(win.txt_notes.toPlainText(), "seen twice")
        self.assertEqual(win.save_values()["passage_type"], "other")
        win.set_sensor("S2")                # not in the index: blank
        self.assertEqual(win._editors["passage_type"].current(), "")
        self.assertEqual(win.save_values(), {})
        win.set_sensor(None)
        page._load_index()

    def test_misclassification_labels_are_the_datasets(self):
        """One editor per variable the model's dataset has a column for,
        position ones included - not every variable in the settings."""
        page = self.window.misclassification_page
        entry = object()
        page._entry = entry
        try:
            page._df_cache[id(entry)] = pd.DataFrame(
                columns=["file", "time_s", "passage_type", "strike_location"])
            page._rebuild_labels()
            self.assertEqual(set(page._editors),
                             {"passage_type", "strike_location"})
            page._df_cache[id(entry)] = pd.DataFrame(
                columns=["file", "time_s", "passage_type", "leading_type"])
            page._rebuild_labels()
            self.assertEqual(set(page._editors), {"passage_type", "leading_type"})
        finally:
            page._entry = None
            page._df_cache.pop(id(entry), None)
            page._rebuild_labels()
        self.assertEqual(page._editors, {})

    def test_misclassification_correction_reaches_the_index(self):
        from modules import deployment_index as di
        lib = self.env / "libraries" / "LibA"
        (lib / "raw_sens_data" / "Dep1").mkdir(parents=True)
        index = di.index_path(lib)
        index.parent.mkdir(parents=True)
        pd.DataFrame([{"file": "S1", "deployment_id": "Dep1"},
                      {"file": "S2", "deployment_id": "Dep1"}]).to_csv(
            index, index=False)
        page = self.window.misclassification_page
        row = pd.Series({"file": "S1", "deployment_id": "Dep1"})
        # not the session library: found through its deployment folder
        self.assertEqual(page._index_libraries("S1", row), [lib])
        written = page._sync_index("S1", {"passage_type": "other"}, row)
        self.assertEqual(written, [lib])
        df = di.read_index(lib).set_index("file")
        self.assertEqual(df.loc["S1", "passage_type"], "other")
        self.assertTrue(pd.isna(df.loc["S2", "passage_type"])
                        or df.loc["S2", "passage_type"] == "")
        self.assertEqual(page._index_libraries("S9", row), [])


if __name__ == "__main__":
    unittest.main()
