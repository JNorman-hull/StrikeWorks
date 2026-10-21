"""A plot's "Export ▾" image (modules/plot_style.py): the window the plot
shows - its time range and both y ranges - not the whole recording."""
import unittest

import numpy as np

from support import pump, qt_app


class PlotExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        import pyqtgraph as pg
        self.t = np.arange(0, 10, 0.001)
        self.left = np.sin(self.t)
        self.right = 100 * np.cos(self.t)
        self.pw = pg.PlotWidget()
        self.pw.plot(self.t, self.left)
        self.vb2 = pg.ViewBox()
        self.pw.plotItem.scene().addItem(self.vb2)
        self.vb2.setXLink(self.pw.plotItem)
        self.vb2.addItem(pg.PlotCurveItem(self.t, self.right))
        self.pw.resize(600, 400)
        self.pw.show()
        # the user's zoom
        self.pw.plotItem.vb.setRange(xRange=(2.0, 3.0), yRange=(-0.5, 0.25),
                                     padding=0)
        self.vb2.setRange(yRange=(-20, 40), padding=0)
        pump(100)

    def tearDown(self):
        self.pw.close()
        self.pw.deleteLater()

    def test_export_is_the_visible_window(self):
        from modules import plot_style
        data = plot_style.build_export_data(
            self.t, "Pressure", self.left, "HIG", self.right, self.pw,
            self.vb2)
        self.assertEqual(tuple(round(v, 6) for v in data["xlim"]), (2.0, 3.0))
        self.assertEqual(tuple(round(v, 6) for v in data["ylim"]), (-0.5, 0.25))
        self.assertEqual(tuple(round(v, 6) for v in data["right_ylim"]),
                         (-20.0, 40.0))
        # only the samples in view, plus one either side
        for _label, xs, ys, _colour, _axis in data["series"]:
            self.assertEqual(len(xs), len(ys))
            self.assertLessEqual(xs[0], 2.0)
            self.assertGreaterEqual(xs[-1], 3.0)
            self.assertLess(len(xs), 1100)

        fig = plot_style.render_export_figure(
            16, 10, 100, data["series"], data["x_label"], data["y_label"],
            data["right_label"], data["xlim"], None, data["ylim"],
            data["right_ylim"])
        ax_left, ax_right = fig.axes
        np.testing.assert_allclose(ax_left.get_xlim(), (2.0, 3.0), atol=1e-6)
        np.testing.assert_allclose(ax_left.get_ylim(), (-0.5, 0.25), atol=1e-6)
        np.testing.assert_allclose(ax_right.get_ylim(), (-20, 40), atol=1e-6)

    def test_left_channel_only(self):
        from modules import plot_style
        data = plot_style.build_export_data(
            self.t, "Pressure", self.left, "", None, self.pw, self.vb2)
        self.assertEqual(len(data["series"]), 1)
        self.assertIsNone(data["right_ylim"])


if __name__ == "__main__":
    unittest.main()
