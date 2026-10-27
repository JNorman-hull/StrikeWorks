"""The shared figure canvas (modules/canvas.py): redrawn once a resize is
over, not at every step of one."""
import unittest

from support import pump, qt_app


class CanvasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()

    def setUp(self):
        from matplotlib.figure import Figure

        from modules import canvas
        self.canvas_module = canvas
        self.fig = Figure(dpi=100)
        self.fig.add_subplot(111).plot([0, 1], [0, 1])
        self.canvas = canvas.FigureCanvas(self.fig)
        self.draws = []
        self.canvas.mpl_connect("draw_event", self.draws.append)
        self.canvas.resize(400, 300)
        self.canvas.show()
        pump(200)

    def tearDown(self):
        self.canvas.close()
        self.canvas.deleteLater()

    def _size(self):
        return tuple(round(v) for v in self.fig.get_size_inches() * self.fig.dpi)

    def test_redrawn_once_a_resize_is_over(self):
        self.assertEqual(self._size(), (400, 300))
        self.draws.clear()
        # a drag: many small steps, faster than the settle time
        for w in range(410, 600, 10):
            self.canvas.resize(w, 300)
            pump(10)
        self.assertEqual(self.draws, [])
        self.assertEqual(self._size(), (400, 300))
        self.assertIsNotNone(self.canvas._stale)
        self.canvas.repaint()                  # the old drawing, stretched

        pump(self.canvas_module.SETTLE_MS * 3)
        self.assertEqual(self._size(), (590, 300))
        self.assertEqual(len(self.draws), 1)
        self.assertIsNone(self.canvas._stale)

    def test_hidden_canvas_laid_out_straight_away(self):
        self.canvas.hide()
        self.canvas.resize(500, 350)
        self.canvas.show()
        self.assertEqual(self._size(), (500, 350))

    def test_laid_out_again_at_the_size_shown(self):
        """A figure laid out while its canvas was bigger keeps its axis
        titles and legend inside it, clear of each other, once the page
        gives the canvas its real (smaller) size."""
        import pandas as pd
        from modules import ml_figures
        summary = pd.DataFrame({
            "treatment": ["400 (100%)", "400 (70%)", "500 (100%)"],
            "n": [102, 80, 76], "strike_rate": [0.39, 0.5, 0.5],
            "ci_lo": [0.3, 0.39, 0.39], "ci_hi": [0.49, 0.61, 0.61],
            "n_strike": [40, 40, 38], "n_region_1": [6, 6, 10],
            "n_region_2_3": [14, 18, 12], "n_region_4_5": [20, 16, 16]})
        draws = {
            "strike rate": lambda f: ml_figures.draw_strike_rate(
                f, summary, dark=True),
            "region": lambda f: ml_figures.draw_region(
                f, summary, ["region_1", "region_2_3", "region_4_5"],
                dark=True)}
        for name, draw in draws.items():
            with self.subTest(figure=name):
                self.canvas.resize(900, 700)
                pump(self.canvas_module.SETTLE_MS * 3)
                draw(self.fig)
                self.canvas.draw()
                self.canvas.resize(610, 300)
                pump(self.canvas_module.SETTLE_MS * 3)
                self.canvas.draw()
                r = self.canvas.get_renderer()
                ax = self.fig.axes[0]
                frame = self.fig.bbox
                for title in (ax.xaxis.label, ax.yaxis.label):
                    box = title.get_window_extent(r)
                    self.assertTrue(frame.x0 - 1 <= box.x0 and box.x1 <= frame.x1 + 1
                                    and frame.y0 - 1 <= box.y0 and box.y1 <= frame.y1 + 1,
                                    f"{title.get_text()} cut off")
                for leg in self.fig.legends:
                    self.assertFalse(leg.get_window_extent(r).overlaps(
                        ax.xaxis.label.get_window_extent(r)))


if __name__ == "__main__":
    unittest.main()
