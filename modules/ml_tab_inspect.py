# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Inspect tab - interrogate individual predictions.

Select a prediction -> inspect the underlying sensor event -> understand how
it was classified. The browser lists the per-recording predictions produced
by the worker; the detail panel shows the class probabilities and the exact
model-input signal (the same segmented channels that were supplied to the
model), plotted with the same pyqtgraph navigation used on the Validate &
segment page. Ground-truth comparison appears only when the dataset carries
annotation labels.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import settings
from .ml_state import annotation_column, is_strike_value
from .ml_tab_predict import _NumItem
from .ml_widgets import (
    BAD, INFO, MUTED, OK, PALETTE, PINK, TEXT, WARN, ProbBars, Section,
    apply_section_defaults,
)
from .page_validate import _CsvLoadThread, _NavViewBox
from .plot_style import (
    add_export_button, build_export_data, reserve_top_margin,
    set_right_axis_active,
)

_VIEW_WINDOW = "window"   # exact model-input segment
_VIEW_FULL   = "full"     # full sensor passage from the library

_FILTER_ALL       = "all"
_FILTER_STRIKES   = "strikes"
_FILTER_NO_STRIKE = "no_strikes"
_FILTER_LOW_CONF  = "low_conf"
_FILTER_MISCLASS  = "misclass"


class InspectTab:
    """Builds the Inspect tab UI into `frame` and binds it to `state`."""

    def __init__(self, frame, state, window):
        self.state = state
        self.window = window
        self._updating_table = False
        self._left_curve = None
        self._right_curve = None
        self._nadir_line = None
        self._window_region = None
        self._full_cache = {}       # recording id -> full-passage DataFrame
        self._full_missing = set()  # recordings with no library CSV
        self._loaders = []
        self._pending_full = None
        self._export_t = None
        self._export_left = None
        self._export_right = None

        self._build(frame)
        self._connect_state()
        self._rebuild_filters()
        self._populate_table()
        self._refresh_detail()

    # ── layout ───────────────────────────────────────────────────────────────
    def _build(self, frame):
        root = QHBoxLayout(frame)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(0)

        # A splitter rather than fixed widths, so the user can rebalance the
        # browser against the signal view at any window size.
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        # ── left: browser ───────────────────────────────────────────────────
        left = QWidget()
        left.setMinimumWidth(360)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)

        grp_filter = Section("Filter predictions")
        fv = QVBoxLayout(grp_filter)
        fv.setSpacing(6)

        row1 = QHBoxLayout()
        self.cmb_filter = QComboBox()
        self.cmb_filter.currentIndexChanged.connect(self._populate_table)
        self.spin_low = QDoubleSpinBox()
        self.spin_low.setRange(0.0, 1.0)
        self.spin_low.setDecimals(2)
        self.spin_low.setSingleStep(0.05)
        self.spin_low.setValue(self.state.low_conf_threshold)
        self.spin_low.setToolTip("Low-confidence threshold")
        self.spin_low.valueChanged.connect(self._on_low_conf_changed)
        row1.addWidget(self.cmb_filter, stretch=1)
        row1.addWidget(self.spin_low)
        fv.addLayout(row1)

        row2 = QHBoxLayout()
        self.cmb_treatment = QComboBox()
        self.cmb_treatment.currentIndexChanged.connect(self._populate_table)
        self.cmb_class = QComboBox()
        self.cmb_class.currentIndexChanged.connect(self._populate_table)
        row2.addWidget(self.cmb_treatment, stretch=1)
        row2.addWidget(self.cmb_class, stretch=1)
        fv.addLayout(row2)

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Search recording…")
        self.ed_search.textChanged.connect(self._populate_table)
        fv.addWidget(self.ed_search)

        self.lbl_count = QLabel("No prediction run yet.")
        self.lbl_count.setStyleSheet(f"color:{MUTED};")
        fv.addWidget(self.lbl_count)
        lv.addWidget(grp_filter)

        self.tbl = QTableWidget(0, 0)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.itemSelectionChanged.connect(self._on_row_selected)
        lv.addWidget(self.tbl, stretch=1)
        lv.setContentsMargins(0, 0, 5, 0)
        split.addWidget(left)

        # ── right: detail ───────────────────────────────────────────────────
        # scrollable so the stacked sections below don't clip on a short
        # window, and inside the splitter (not root) so it's resizable
        # against the browser like the header comment always claimed
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        right_scroll.setMinimumWidth(420)
        right = QWidget()
        right.setStyleSheet("background:transparent;")
        right_scroll.setWidget(right)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(5, 0, 0, 0)
        rv.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)

        grp_sel = Section("Selected prediction")
        sv = QVBoxLayout(grp_sel)
        sv.setSpacing(3)
        self.lbl_rec = QLabel("No prediction selected")
        self.lbl_rec.setStyleSheet(
            f"color:{TEXT};font-weight:bold;")
        self.lbl_tx = QLabel("")
        self.lbl_tx.setStyleSheet(f"color:{MUTED};")
        self.lbl_verdict = QLabel("")
        self.lbl_verdict.setStyleSheet(
            f"color:{PINK};font-weight:bold;font-size:16px;")
        self.lbl_prob = QLabel("")
        self.lbl_prob.setStyleSheet(f"color:{TEXT};")
        self.lbl_region = QLabel("")
        self.lbl_region.setStyleSheet(f"color:{TEXT};")
        self.lbl_gt = QLabel("")
        self.lbl_gt.setStyleSheet(f"color:{TEXT};")
        self.lbl_gt.setWordWrap(True)
        self.lbl_gt.setTextFormat(Qt.TextFormat.RichText)
        for w in (self.lbl_rec, self.lbl_tx, self.lbl_verdict,
                  self.lbl_prob, self.lbl_region, self.lbl_gt):
            sv.addWidget(w)
        sv.addStretch()
        top.addWidget(grp_sel, stretch=1)

        grp_probs = Section("Class probabilities")
        pv = QVBoxLayout(grp_probs)
        self.prob_bars = ProbBars()
        pv.addWidget(self.prob_bars)
        pv.addStretch()
        top.addWidget(grp_probs, stretch=1)
        rv.addLayout(top)

        grp_sig = Section("Model input signal")
        gv = QVBoxLayout(grp_sig)
        gv.setSpacing(6)

        ctl = QHBoxLayout()
        self.cmb_view = QComboBox()
        self.cmb_view.addItem("Blade interaction only", _VIEW_WINDOW)
        self.cmb_view.addItem("Full sensor passage", _VIEW_FULL)
        self.cmb_view.setToolTip(
            "Blade interaction only: the exact segmented window supplied to "
            "the model.\nFull sensor passage: the recording's complete "
            "sensor file from the library, with the model window marked.")
        self.cmb_view.currentIndexChanged.connect(self._refresh_signal)
        lab_l = QLabel("Left axis")
        lab_l.setStyleSheet(f"color:{MUTED};")
        self.cmb_left = QComboBox()
        self.cmb_left.currentIndexChanged.connect(self._refresh_signal)
        lab_r = QLabel("Right axis")
        lab_r.setStyleSheet(f"color:{MUTED};")
        self.cmb_right = QComboBox()
        self.cmb_right.currentIndexChanged.connect(self._refresh_signal)
        self.btn_reset_view = QPushButton("Reset view")
        self.btn_reset_view.clicked.connect(self._reset_view)
        ctl.addWidget(self.cmb_view, stretch=1)
        ctl.addWidget(lab_l)
        ctl.addWidget(self.cmb_left, stretch=1)
        ctl.addWidget(lab_r)
        ctl.addWidget(self.cmb_right, stretch=1)
        ctl.addWidget(self.btn_reset_view)
        add_export_button(ctl, self._export_data, self.window,
                          file_stub="inspect")
        gv.addLayout(ctl)

        self._pw = pg.PlotWidget(viewBox=_NavViewBox())
        self._pw.setMinimumHeight(220)
        self._pw.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Expanding)
        pi = self._pw.plotItem
        pi.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        pi.setLabel("bottom", "Time (s)")
        reserve_top_margin(pi)

        # secondary ViewBox for the optional right-axis channel
        self._vb2 = pg.ViewBox()
        pi.scene().addItem(self._vb2)
        pi.getAxis("right").linkToView(self._vb2)
        self._vb2.setXLink(pi)
        set_right_axis_active(pi, False)
        pi.vb.sigResized.connect(self._sync_vb2)
        gv.addWidget(self._pw, stretch=1)

        self.lbl_sig_note = QLabel(
            "This is the exact segmented window supplied to the model. "
            "Drag to box-zoom, wheel to pan, Shift+wheel to pan vertically.")
        self.lbl_sig_note.setStyleSheet(f"color:{MUTED};")
        self.lbl_sig_note.setWordWrap(True)
        gv.addWidget(self.lbl_sig_note)
        rv.addWidget(grp_sig, stretch=1)

        split.addWidget(right_scroll)
        split.setSizes([1, 1])

        apply_section_defaults(frame)

    # ── state wiring ─────────────────────────────────────────────────────────
    def _connect_state(self):
        s = self.state
        s.run_finished.connect(self._on_run_finished)
        s.models_changed.connect(self._rebuild_channel_combos)
        s.dataset_changed.connect(self._rebuild_channel_combos)
        s.selection_changed.connect(self._on_selection_changed)
        s.treatment_selected.connect(self._on_treatment_from_predict)

    # ── filters ──────────────────────────────────────────────────────────────
    def _rebuild_filters(self):
        s = self.state
        thr = s.low_conf_threshold

        self.cmb_filter.blockSignals(True)
        current = self.cmb_filter.currentData()
        self.cmb_filter.clear()
        self.cmb_filter.addItem("All predictions", _FILTER_ALL)
        self.cmb_filter.addItem("Strikes only", _FILTER_STRIKES)
        self.cmb_filter.addItem("No strikes", _FILTER_NO_STRIKE)
        self.cmb_filter.addItem(f"Low confidence (< {thr:.2f})",
                                _FILTER_LOW_CONF)
        if self._have_ground_truth():
            self.cmb_filter.addItem("Misclassified (vs ground truth)",
                                    _FILTER_MISCLASS)
        idx = self.cmb_filter.findData(current)
        self.cmb_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_filter.blockSignals(False)

        self.cmb_treatment.blockSignals(True)
        current = self.cmb_treatment.currentText()
        self.cmb_treatment.clear()
        self.cmb_treatment.addItem("All treatments", None)
        if s.predictions is not None and "treatment" in s.predictions.columns:
            for tx in sorted(s.predictions["treatment"].astype(str).unique()):
                self.cmb_treatment.addItem(tx, tx)
        idx = self.cmb_treatment.findText(current)
        self.cmb_treatment.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_treatment.blockSignals(False)

        self.cmb_class.blockSignals(True)
        current = self.cmb_class.currentText()
        self.cmb_class.clear()
        self.cmb_class.addItem("All classes", None)
        if (s.predictions is not None
                and "predicted_region" in s.predictions.columns):
            for cn in s.class_names:
                self.cmb_class.addItem(cn, cn)
            self.cmb_class.setVisible(True)
        else:
            self.cmb_class.setVisible(False)
        idx = self.cmb_class.findText(current)
        self.cmb_class.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_class.blockSignals(False)

        self._rebuild_channel_combos()

    def _rebuild_channel_combos(self):
        """Offer the model input channels plus the derived magnitude
        channels the dataset carries - the magnitudes are what an analyst
        actually reads a blade interaction from."""
        chans = self.state.required_channels()
        df = self.state.dataset_df
        if df is not None:
            chans = [c for c in chans if c in df.columns]
            derived = [c for c in df.columns
                       if c not in chans and "_mag_" in c]
            chans = derived + chans

        # pressure on the left (white), high-g magnitude on the right (red)
        for cmb, default, extra_none in (
                (self.cmb_left, "pressure_kpa", False),
                (self.cmb_right, "higacc_mag_g", True)):
            cmb.blockSignals(True)
            current = cmb.currentData()
            cmb.clear()
            if extra_none:
                cmb.addItem("None", None)
            for c in chans:
                cmb.addItem(c, c)
            idx = cmb.findData(current if current in chans else default)
            cmb.setCurrentIndex(idx if idx >= 0 else 0)
            cmb.blockSignals(False)
        self._refresh_signal()

    def _on_low_conf_changed(self, value):
        self.state.low_conf_threshold = float(value)
        idx = self.cmb_filter.findData(_FILTER_LOW_CONF)
        if idx >= 0:
            self.cmb_filter.setItemText(idx, f"Low confidence (< {value:.2f})")
        if self.cmb_filter.currentData() == _FILTER_LOW_CONF:
            self._populate_table()

    def apply_filter_preset(self, preset):
        """External navigation hook (e.g. Predict's low-confidence button)."""
        idx = self.cmb_filter.findData(preset)
        if idx >= 0:
            self.cmb_filter.setCurrentIndex(idx)

    def _on_treatment_from_predict(self, treatment):
        if not treatment:
            return
        idx = self.cmb_treatment.findText(treatment)
        if idx >= 0:
            self.cmb_treatment.setCurrentIndex(idx)

    # ── ground truth helpers ─────────────────────────────────────────────────
    def _have_ground_truth(self):
        p = self.state.predictions
        return p is not None and "overall_passage_type" in p.columns \
            and p["overall_passage_type"].notna().any()

    def _filtered(self):
        s = self.state
        df = s.predictions
        if df is None:
            return None
        out = df

        mode = self.cmb_filter.currentData()
        if mode == _FILTER_STRIKES:
            out = out[out["predicted_strike"] == 1]
        elif mode == _FILTER_NO_STRIKE:
            out = out[out["predicted_strike"] == 0]
        elif mode == _FILTER_LOW_CONF:
            out = out[out["confidence"] < s.low_conf_threshold]
        elif mode == _FILTER_MISCLASS:
            col = annotation_column(out)
            if col is not None:
                has_gt = (out[col].notna()
                          & (out[col].astype(str).str.strip() != ""))
                gt_strike = out[col].map(is_strike_value)
                out = out[has_gt
                          & (out["predicted_strike"].astype(bool)
                             != gt_strike)]

        tx = self.cmb_treatment.currentData()
        if tx is not None and "treatment" in out.columns:
            out = out[out["treatment"].astype(str) == tx]

        cls = self.cmb_class.currentData()
        if cls is not None and "predicted_region" in out.columns:
            out = out[out["predicted_region"] == cls]

        text = self.ed_search.text().strip().lower()
        if text:
            out = out[out["file"].astype(str).str.lower()
                      .str.contains(text, regex=False)]
        return out

    # ── prediction browser table ─────────────────────────────────────────────
    def _on_run_finished(self):
        self._rebuild_filters()
        self._populate_table()
        self._refresh_detail()

    def _populate_table(self):
        s = self.state
        df = self._filtered()
        have_mc = df is not None and "predicted_region" in (
            df.columns if df is not None else [])
        have_gt = self._have_ground_truth()

        headers = ["Recording", "Treatment", "Prediction", "P(strike)",
                   "Confidence"]
        if have_mc:
            headers += ["Region", "Region conf"]
        if have_gt:
            headers += ["Ground truth", "Match"]

        self._updating_table = True
        self.tbl.setSortingEnabled(False)
        self.tbl.clear()
        self.tbl.setColumnCount(len(headers))
        self.tbl.setHorizontalHeaderLabels(headers)
        self.tbl.setRowCount(0 if df is None else len(df))

        if df is None:
            self.lbl_count.setText("No prediction run yet.")
            self._updating_table = False
            self.tbl.setSortingEnabled(True)
            return

        total = len(s.predictions)
        self.lbl_count.setText(f"Showing {len(df)} of {total} predictions.")

        for row, (_, r) in enumerate(df.iterrows()):
            is_strike = int(r["predicted_strike"]) == 1
            items = [
                QTableWidgetItem(str(r["file"])),
                QTableWidgetItem(str(r.get("treatment", "-"))),
                QTableWidgetItem("Strike" if is_strike else "No strike"),
                _NumItem(f"{r['probability_strike']:.3f}",
                         float(r["probability_strike"])),
                _NumItem(f"{r['confidence']:.3f}", float(r["confidence"])),
            ]
            if have_mc:
                region = r.get("predicted_region", "")
                rc = r.get("region_confidence")
                items.append(QTableWidgetItem(
                    str(region) if isinstance(region, str) and region else "-"))
                items.append(_NumItem(
                    f"{rc:.3f}" if pd.notna(rc) else "-",
                    float(rc) if pd.notna(rc) else -1.0))
            if have_gt:
                gt_strike, gt_label, _gt_cls = s.ground_truth_for(r)
                if gt_strike is None:
                    items.append(QTableWidgetItem("-"))
                    items.append(QTableWidgetItem("-"))
                else:
                    items.append(QTableWidgetItem(gt_label))
                    match = is_strike == gt_strike
                    it = QTableWidgetItem("✓" if match else "✗")
                    it.setForeground(
                        pg.mkColor(OK) if match else pg.mkColor(BAD))
                    items.append(it)

            items[0].setData(Qt.ItemDataRole.UserRole, str(r["file"]))
            low = float(r["confidence"]) < s.low_conf_threshold
            for col, item in enumerate(items):
                if col >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if low and col == 4:
                    item.setForeground(pg.mkColor(WARN))
                self.tbl.setItem(row, col, item)

        self.tbl.setSortingEnabled(True)
        self._updating_table = False
        self._reselect_current()

    def _reselect_current(self):
        """Keep the table selection in sync with the shared state."""
        target = self.state.selected_file
        if not target:
            return
        self._updating_table = True
        try:
            for row in range(self.tbl.rowCount()):
                item = self.tbl.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == target:
                    self.tbl.selectRow(row)
                    break
            else:
                self.tbl.clearSelection()
        finally:
            self._updating_table = False

    def _on_row_selected(self):
        if self._updating_table:
            return
        items = self.tbl.selectedItems()
        if not items:
            return
        file_id = self.tbl.item(items[0].row(), 0).data(
            Qt.ItemDataRole.UserRole)
        self.state.select_file(file_id)

    # ── detail panel ─────────────────────────────────────────────────────────
    def _on_selection_changed(self, _file_id):
        self._reselect_current()
        self._refresh_detail()

    def _refresh_detail(self):
        s = self.state
        row = s.selected_row()
        if row is None:
            self.lbl_rec.setText("No prediction selected")
            self.lbl_tx.setText("Run a prediction and pick a recording "
                                "from the browser.")
            self.lbl_verdict.setText("")
            self.lbl_prob.setText("")
            self.lbl_region.setText("")
            self.lbl_gt.setText("")
            self.prob_bars.clear()
            self._clear_signal()
            return

        is_strike = int(row["predicted_strike"]) == 1
        self.lbl_rec.setText(f"Recording: {row['file']}")
        self.lbl_tx.setText(f"Treatment: {row.get('treatment', '-')}")
        self.lbl_verdict.setText("STRIKE" if is_strike else "NO STRIKE")
        self.lbl_verdict.setStyleSheet(
            f"color:{PINK if is_strike else INFO};"
            "font-weight:bold;font-size:16px;")
        self.lbl_prob.setText(
            f"Strike probability: {row['probability_strike']:.3f}    "
            f"Confidence: {row['confidence']:.3f}")

        region = row.get("predicted_region")
        rc = row.get("region_confidence")
        if is_strike and isinstance(region, str) and region:
            txt = f"Region: {region}"
            if pd.notna(rc):
                txt += f"    Region confidence: {float(rc):.3f}"
            self.lbl_region.setText(txt)
            self.lbl_region.setVisible(True)
        else:
            self.lbl_region.setVisible(False)

        gt_strike, gt_label, gt_cls = s.ground_truth_for(row)
        if gt_strike is None:
            self.lbl_gt.setVisible(False)
        else:
            match = is_strike == gt_strike
            verdict = ("<span style='color:%s;'>✓ Correct</span>" % OK
                       if match else
                       "<span style='color:%s;'>⚠ Misclassification</span>" % BAD)
            gt_txt = f"Ground truth: {gt_label}"
            if gt_cls:
                gt_txt += f" ({gt_cls})"
            self.lbl_gt.setText(f"{gt_txt}<br/>{verdict}")
            self.lbl_gt.setVisible(True)

        self._refresh_prob_bars(row, is_strike)
        self._refresh_signal()

    def _refresh_prob_bars(self, row, is_strike):
        s = self.state
        prob_cols = [c for c in row.index if c.startswith("prob_")]
        if prob_cols:
            bars = []
            ordered = [f"prob_{cn}" for cn in s.class_names
                       if f"prob_{cn}" in prob_cols] or prob_cols
            for i, col in enumerate(ordered):
                label = col[len("prob_"):]
                bars.append((label, float(row[col]),
                             PALETTE[i % len(PALETTE)]))
            self.prob_bars.set_probs(bars)
        else:
            p = float(row["probability_strike"])
            self.prob_bars.set_probs([
                ("No strike", 1.0 - p, INFO),
                ("Strike",    p,       PINK),
            ])

    # ── signal plot ──────────────────────────────────────────────────────────
    def _clear_signal(self):
        pi = self._pw.plotItem
        if self._left_curve is not None:
            pi.removeItem(self._left_curve)
            self._left_curve = None
        if self._right_curve is not None:
            self._vb2.removeItem(self._right_curve)
            self._right_curve = None
        if self._nadir_line is not None:
            pi.removeItem(self._nadir_line)
            self._nadir_line = None
        if self._window_region is not None:
            pi.removeItem(self._window_region)
            self._window_region = None
        set_right_axis_active(pi, False)
        self._export_t = None
        self._export_left = None
        self._export_right = None

    # ── full-passage lookup (library CSVs, loaded off the GUI thread) ────────
    def _find_full_csv(self, stem):
        lib_dir = settings.get_libraries_dir()
        roots = [lib_dir]
        try:
            roots += [p for p in lib_dir.iterdir() if p.is_dir()]
        except OSError:
            pass
        for root in roots:
            csv_dir = root / "processed_sens_data" / "csv"
            if not csv_dir.exists():
                continue
            direct = csv_dir / f"{stem}.csv"
            if direct.exists():
                return direct
            hits = list(csv_dir.rglob(f"{stem}.csv"))
            if hits:
                return hits[0]
        return None

    def _request_full(self, file_id):
        """Start loading the full sensor CSV; returns True if now loading."""
        if file_id in self._full_missing:
            return False
        path = self._find_full_csv(file_id)
        if path is None:
            self._full_missing.add(file_id)
            return False
        if self._pending_full == file_id:
            return True
        self._pending_full = file_id
        loader = _CsvLoadThread(path)
        loader.loaded.connect(
            lambda p, df, fid=file_id: self._on_full_loaded(fid, df))
        loader.failed.connect(
            lambda p, msg, fid=file_id: self._on_full_failed(fid, msg))
        loader.finished.connect(lambda lt=loader: self._loaders.remove(lt))
        self._loaders.append(loader)
        loader.start()
        return True

    def _on_full_loaded(self, file_id, df):
        if self._pending_full == file_id:
            self._pending_full = None
        self._full_cache[file_id] = df
        if self.state.selected_file == file_id:
            self._refresh_signal()

    def _on_full_failed(self, file_id, msg):
        if self._pending_full == file_id:
            self._pending_full = None
        self._full_missing.add(file_id)
        self.state.status.emit(f"Full sensor file load failed: {msg}", 6000)
        if self.state.selected_file == file_id:
            self._refresh_signal()

    def _refresh_signal(self):
        s = self.state
        self._clear_signal()

        window_sig = s.file_signal(s.selected_file)
        if window_sig is None:
            self.lbl_sig_note.setText(
                "Select a prediction to view its sensor signal.")
            return

        mode = self.cmb_view.currentData() or _VIEW_WINDOW
        sig = window_sig
        note = ("This is the exact segmented window supplied to the model. "
                "Drag to box-zoom, wheel to pan, Shift+wheel to pan "
                "vertically.")

        if mode == _VIEW_FULL:
            full = self._full_cache.get(s.selected_file)
            if full is not None:
                sig = full.sort_values("time_s")
                note = ("Full sensor passage from the library; the shaded "
                        "band is the model-input window.")
            elif self._request_full(s.selected_file):
                self.lbl_sig_note.setText(
                    "Loading the full sensor file from the library…")
                return
            else:
                note = ("Full sensor file not found in the configured "
                        "libraries - showing the model-input window instead.")

        pi = self._pw.plotItem
        t = sig["time_s"].to_numpy(dtype=float)
        self._export_t = t
        self._export_left = None
        self._export_right = None

        left = self.cmb_left.currentData()
        if left and left in sig.columns:
            y = sig[left].to_numpy(dtype=float)
            self._left_curve = self._pw.plot(
                t, y, pen=pg.mkPen("#dddddd", width=1))
            self._left_curve.setDownsampling(auto=True, method="peak")
            self._left_curve.setClipToView(True)
            pi.setLabel("left", left)
            self._export_left = (left, y)

        right = self.cmb_right.currentData()
        if right and right in sig.columns:
            set_right_axis_active(pi, True)
            pi.setLabel("right", right)
            self._right_curve = pg.PlotCurveItem(
                pen=pg.mkPen("#ff5555", width=1))
            self._vb2.addItem(self._right_curve)
            right_y = sig[right].to_numpy(dtype=float)
            self._right_curve.setData(t, right_y)
            self._sync_vb2()
            self._vb2.enableAutoRange("y", True)
            self._export_right = (right, right_y)

        # model-input window: shaded when viewing the full passage
        w_t = window_sig["time_s"].to_numpy(dtype=float)
        if sig is not window_sig and len(w_t):
            self._window_region = pg.LinearRegionItem(
                values=[float(w_t[0]), float(w_t[-1])], movable=False,
                brush=pg.mkBrush(85, 170, 255, 35),
                pen=pg.mkPen(85, 170, 255, 90))
            pi.addItem(self._window_region)

        # event indication: pressure nadir inside the model window
        if "pressure_kpa" in window_sig.columns and len(w_t):
            pres = window_sig["pressure_kpa"].to_numpy(dtype=float)
            if np.isfinite(pres).any():
                t_nadir = float(w_t[int(np.nanargmin(pres))])
                self._nadir_line = pg.InfiniteLine(
                    pos=t_nadir, angle=90, movable=False,
                    pen=pg.mkPen(color=(255, 220, 0), width=2),
                    label="Nadir",
                    labelOpts={"position": 0.92, "color": (200, 170, 0)})
                pi.addItem(self._nadir_line)

        self.lbl_sig_note.setText(note)
        self._reset_view()

    def _reset_view(self):
        pi = self._pw.plotItem
        pi.enableAutoRange("x", True)
        pi.enableAutoRange("y", True)
        if self._right_curve is not None:
            self._vb2.enableAutoRange("y", True)

    def _sync_vb2(self):
        pi = self._pw.plotItem
        self._vb2.setGeometry(pi.vb.sceneBoundingRect())
        self._vb2.linkedViewChanged(pi.vb, self._vb2.XAxis)

    def _export_data(self):
        if self._export_t is None or self._export_left is None:
            return None
        (x0, x1), _ = self._pw.plotItem.vb.viewRange()
        left_label, left_y = self._export_left
        right_label, right_y = self._export_right or (None, None)
        return build_export_data(
            self._export_t, left_label, left_y, right_label, right_y,
            (x0, x1))
