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


if __name__ == "__main__":
    unittest.main()
