"""Every table from one place (tables.py): set up as it's first shown -
centred cells, sort and filter from the headers (none on "file"), filters
kept through a refill - right-click copy, and menus parented to their
window; and Model comparison's table filled to what it shows (Blade
strike results: test_bsm_page.py)."""
import unittest

from support import isolate, main_window, pump, qt_app


def _table(headers, rows):
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
    tbl = QTableWidget(len(rows), len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            tbl.setItem(r, c, QTableWidgetItem(text))
    return tbl


def _column(tbl, col):
    return [tbl.item(r, col).text() for r in range(tbl.rowCount())
            if not tbl.isRowHidden(r)]


class Tables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modules import tables
        tables.install(qt_app())

    def _shown(self, tbl):
        tbl.show()
        self.addCleanup(lambda: (tbl.close(), tbl.deleteLater(), pump(20)))
        pump(20)
        return tbl

    def test_set_up_as_first_shown(self):
        from modules import tables
        tbl = self._shown(_table(["file", "x"], [["S1", "1"]]))
        self.assertTrue(tbl.property("tableSetUp"))
        self.assertFalse(tbl.isSortingEnabled())       # the menu sorts
        self.assertIsInstance(tbl.itemDelegate(), tables._Centred)

    def test_dragged_column_widths_are_kept(self):
        from modules import tables
        tbl = self._shown(_table(["file", "x"], [["S1", "1"]]))
        fitted = tbl.columnWidth(0)
        tbl.setColumnWidth(0, fitted + 120)       # set by code: fitted again
        tbl.hide()
        tbl.show()
        pump(20)
        self.assertEqual(tbl.columnWidth(0), fitted)
        tbl.setColumnWidth(0, fitted + 120)       # dragged: kept
        tbl.setProperty(tables.DRAGGED, True)
        tbl.hide()
        tbl.show()
        pump(20)
        self.assertEqual(tbl.columnWidth(0), fitted + 120)

    def test_sort_numbers_and_names(self):
        from PySide6.QtCore import Qt
        from modules.tables import sort_column
        tbl = self._shown(_table(
            ["file", "rate"],
            [["S10", "12.5%"], ["S2", "9.0%"], ["S1", "-"], ["S3", "100.0%"]]))
        sort_column(tbl, 1)
        self.assertEqual(_column(tbl, 1), ["9.0%", "12.5%", "100.0%", "-"])
        sort_column(tbl, 0, Qt.SortOrder.DescendingOrder)
        self.assertEqual(_column(tbl, 0), ["S10", "S3", "S2", "S1"])

    def test_filters_never_on_file_and_kept_through_a_refill(self):
        from PySide6.QtWidgets import QTableWidgetItem
        from modules.tables import (
            filter_values, header_name, set_header_filter,
        )
        rows = [["S1", "direct"], ["S2", "indirect"], ["S3", "direct"]]
        tbl = self._shown(_table(["file", "leading_type"], rows))
        self.assertIsNone(filter_values(tbl, 0))
        self.assertEqual(filter_values(tbl, 1), ["direct", "indirect"])
        set_header_filter(tbl, "leading_type", "direct")
        self.assertEqual(_column(tbl, 0), ["S1", "S3"])
        self.assertEqual(tbl.horizontalHeaderItem(1).text(),
                         "leading_type: direct")
        self.assertEqual(header_name(tbl, 1), "leading_type")
        # refilled by its page: still filtered
        tbl.setRowCount(0)
        tbl.setRowCount(4)
        for r, (f, t) in enumerate(rows + [["S4", "direct"]]):
            tbl.setItem(r, 0, QTableWidgetItem(f))
            tbl.setItem(r, 1, QTableWidgetItem(t))
        pump(20)
        self.assertEqual(_column(tbl, 0), ["S1", "S3", "S4"])
        set_header_filter(tbl, "leading_type", None)
        self.assertEqual(_column(tbl, 0), ["S1", "S2", "S3", "S4"])

    def test_copy_highlighted_cells_and_the_entire_table(self):
        from modules.tables import selection_text, set_header_filter, table_text
        tbl = self._shown(_table(["file", "type"],
                                 [["S1", "a"], ["S2", "b"], ["S3", "a"]]))
        tbl.setCurrentCell(1, 0)
        self.assertEqual(selection_text(tbl), "S2")
        set_header_filter(tbl, "type", "a")
        # the column names without the filter, and the rows it leaves
        self.assertEqual(table_text(tbl), "file\ttype\nS1\ta\nS3\ta")

    def test_menus_parented_to_the_window(self):
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        from modules.layout import popup_menu
        holder = QWidget()
        tbl = _table(["x"], [["1"]])
        QVBoxLayout(holder).addWidget(tbl)
        self.addCleanup(holder.deleteLater)
        self.assertIs(popup_menu(tbl).parent(), holder)


class PagesTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        isolate()
        cls.main, cls.window = main_window()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.window.deleteLater()
        pump(50)

    def test_model_comparison_columns_follow_what_is_included(self):
        page = self.window.model_comparison_page

        def headers():
            from modules.tables import header_name
            return [header_name(page.tbl_compare, c)
                    for c in range(page.tbl_compare.columnCount())]

        self.assertEqual(page.ed_model1_label.text(), "Model comparison")
        self.assertIn("Collision probability (Pco)",
                      page.ed_bsm_label.toolTip())
        for box in (page.chk_video_plot, page.chk_model1_plot):
            self.assertEqual(box.text(), "Include")
            self.assertFalse(box.isChecked())
        # nothing entered, no Blade Strike Model run: the model's own column
        model = page._run_model_name()
        self.assertEqual(headers(), ["Treatment", "N", model])
        page.spin_model1_total.setValue(10)
        self.assertTrue(page.chk_model1_plot.isChecked())
        page.spin_model1_strike.setValue(2)
        self.assertEqual(headers(), ["Treatment", "N", model,
                                     "Model comparison"])
        page.chk_model1_plot.setChecked(False)
        self.assertEqual(headers(), ["Treatment", "N", model])
        page.spin_model1_total.setValue(0)
        page.spin_model1_strike.setValue(0)
        self.assertFalse(page.chk_model1_plot.isChecked())


if __name__ == "__main__":
    unittest.main()
