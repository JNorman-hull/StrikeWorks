"""Building a model-ready dataset from a library's processed sensors: one
fixed-length window per sensor around its pressure nadir, with the
deployment / treatment / run carried over from the sensor index.

  OPT_SEGMENTED    bind the windows Validate saved (processed_sens_data/
                   nadir_window) - what Save and export uses
  OPT_UNSEGMENTED  cut the window straight out of each full sensor CSV
                   around the index's nadir time

The window is 200 ms; how many rows that is follows each recording's own
rate (400 at 2000 Hz, 1000 at 5000 Hz). A dataset holds one sensor at one rate
(recording_rate.py), so a build that would mix them stops with `error` set.
"""
import re

import pandas as pd

from PySide6.QtCore import QThread, Signal

from . import deployment_index as di
from . import recording_rate
from .raw_layout import CSV_DIR, INDEX_REL, WINDOW_DIR

WIN_SEC = 0.2
NADIR_COL = "pres_min.time."
WIN_SUFFIX_RE = re.compile(r"_\d+ms$")
BAD_SENS_COL = "bad_sens"

# index columns carried into every dataset row
META_COLS = ["deployment_id", "treatment", "run", recording_rate.SENSOR_COL]

OPT_UNSEGMENTED = 2
OPT_SEGMENTED = 3


def window_rows(time):
    """Rows in the window at the rate of `time` (one recording's time_s), or
    None if there's too little of it to tell."""
    rate = recording_rate.time_rate(time)
    return int(round(WIN_SEC * rate)) if rate else None


def standardise(df, target):
    """Trim or pad df to exactly `target` rows; tolerate a one-row shortfall."""
    n = len(df)
    if n >= target:
        return df.iloc[:target].copy()
    if n == target - 1:
        return pd.concat([df, df.iloc[[-1]]]).reset_index(drop=True)
    return None


class ExtractThread(QThread):
    """Builds the dataset off the GUI thread; `result` holds it once
    `done` fires."""
    log = Signal(str)
    done = Signal(int, int, int)   # n_ok, n_skip, n_rows

    def __init__(self, root, option, selected_files, index_df):
        super().__init__()
        self._root = root
        self._option = option
        self._selected_files = selected_files
        self._index_df = index_df
        self._result_df = None
        self.error = None

    @property
    def _win_suffix(self):
        return f"_{int(round(WIN_SEC * 1000))}ms"

    def _strip_window_suffix(self, stem):
        """The sensor stem from a saved window filename, without its '_<n>ms'
        suffix (the window may have been saved at another width)."""
        if stem.endswith(self._win_suffix):
            return stem[: -len(self._win_suffix)]
        return WIN_SUFFIX_RE.sub("", stem)

    @property
    def result(self):
        return self._result_df

    def run(self):
        try:
            if self._option == OPT_UNSEGMENTED:
                df, n_ok, n_skip = self._run_unsegmented()
            else:
                df, n_ok, n_skip = self._run_segmented()
            problem = recording_rate.dataset_problem(df) if df is not None else None
            if problem:
                raise ValueError(problem)
            self._result_df = df
            self.done.emit(n_ok, n_skip, len(df) if df is not None else 0)
        except Exception as e:
            self.error = str(e)
            self.log.emit(f"\nFATAL: {e}")
            self.done.emit(0, 0, 0)

    def _meta_lookup(self):
        if self._index_df is None or "file" not in self._index_df.columns:
            return {}
        # drop plan rows: they all have file == "label_pad", which would
        # break set_index("file") below
        df = di.sensor_rows(self._index_df)
        available = [c for c in META_COLS if c in df.columns]
        return (df.drop_duplicates("file", keep="last")
                  .set_index("file")[available].to_dict(orient="index"))

    def _attach_meta(self, df, stem, meta):
        info = meta.get(stem, {})
        insert_at = 1
        cols = self._index_df.columns if self._index_df is not None else []
        for col in META_COLS:
            if col in cols:
                df.insert(insert_at, col, info.get(col, pd.NA))
                insert_at += 1
        return df

    # auto nadir +/- half a window out of the full sensor CSV
    def _run_unsegmented(self):
        index_path = self._root / INDEX_REL
        csv_dir = self._root / CSV_DIR

        if not index_path.exists():
            raise FileNotFoundError(f"Sensor index not found:\n  {index_path}")
        if not csv_dir.exists():
            raise FileNotFoundError(f"Sensor CSV folder not found:\n  {csv_dir}")

        index = di.sensor_rows(pd.read_csv(index_path, low_memory=False))

        if NADIR_COL not in index.columns:
            alt = next((c for c in index.columns
                        if "nadir" in c.lower() and "time" in c.lower()), None)
            if alt is None:
                raise ValueError(
                    f"Column '{NADIR_COL}' not found in sensor index.")
            nadir_col = alt
            self.log.emit(f"Note: using '{nadir_col}' as nadir time column.\n")
        else:
            nadir_col = NADIR_COL

        if "file" not in index.columns:
            raise ValueError("Sensor index has no 'file' column.")

        if self._selected_files:
            index = index[index["file"].isin(self._selected_files)]

        self.log.emit(f"Processing {len(index)} sensor file(s).\n")
        meta = self._meta_lookup()
        parts, n_ok, n_skip = [], 0, 0

        for _, row in index.iterrows():
            stem = str(row["file"])
            nadir_time = row[nadir_col]

            if pd.isna(nadir_time):
                self.log.emit(f"  SKIP {stem} - {nadir_col} is NaN")
                n_skip += 1
                continue

            sensor_path = csv_dir / f"{stem}.csv"
            if not sensor_path.exists():
                self.log.emit(f"  SKIP {stem} - sensor CSV not found")
                n_skip += 1
                continue

            try:
                half_sec = WIN_SEC / 2
                t_start = float(nadir_time) - half_sec
                t_end = float(nadir_time) + half_sec

                sensor = pd.read_csv(sensor_path, low_memory=False)
                sliced = sensor[(sensor["time_s"] >= t_start)
                                & (sensor["time_s"] <= t_end)].copy()

                rows = window_rows(sensor["time_s"])
                out = standardise(sliced, rows) if rows else None
                if out is None:
                    self.log.emit(
                        f"  SKIP {stem} - only {len(sliced)} rows in window "
                        f"(nadir near data boundary?)")
                    n_skip += 1
                    continue

                out.insert(0, "file", stem)
                out = self._attach_meta(out, stem, meta)
                parts.append(out)
                self.log.emit(f"  OK   {stem}")
                n_ok += 1
            except Exception as e:
                self.log.emit(f"  FAIL {stem} - {e}")
                n_skip += 1

        result = pd.concat(parts, ignore_index=True) if parts else None
        self.log.emit(f"\n-- Done: {n_ok} extracted, {n_skip} skipped.")
        return result, n_ok, n_skip

    # bind the saved nadir windows
    def _run_segmented(self):
        win_dir = self._root / WINDOW_DIR
        if not win_dir.exists():
            raise FileNotFoundError(
                f"Nadir window folder not found:\n  {win_dir}\n"
                "Validate the sensors first (Validate and annotate).")

        win_files = sorted(win_dir.glob("*.csv"))
        if not win_files:
            raise FileNotFoundError(f"No CSV files in:\n  {win_dir}")

        valid = None
        if self._index_df is not None and "file" in self._index_df.columns:
            if BAD_SENS_COL in self._index_df.columns:
                ok = self._index_df[
                    self._index_df[BAD_SENS_COL]
                    .astype(str).str.strip().str.upper() == "N"]
                valid = set(ok["file"].astype(str))
                self.log.emit(
                    f"Index: {len(valid)} sensor(s) with {BAD_SENS_COL}=N.\n")
            else:
                self.log.emit(
                    f"Note: '{BAD_SENS_COL}' not in index - binding all files.\n")
        else:
            self.log.emit("Note: no index - binding all files.\n")

        self.log.emit(f"Found {len(win_files)} nadir-window file(s).\n")
        meta = self._meta_lookup()
        parts, n_ok, n_skip = [], 0, 0

        for win_path in win_files:
            stem = self._strip_window_suffix(win_path.stem)

            if self._selected_files and stem not in self._selected_files:
                continue
            if valid is not None and stem not in valid:
                self.log.emit(f"  SKIP {stem} - not in the index, or flagged bad")
                n_skip += 1
                continue

            try:
                win = pd.read_csv(win_path, low_memory=False)
                rows = window_rows(win["time_s"])
                out = standardise(win, rows) if rows else None
                if out is None:
                    self.log.emit(
                        f"  SKIP {stem} - only {len(win)} rows "
                        f"(expected >= {(rows or 1) - 1})")
                    n_skip += 1
                    continue

                out.insert(0, "file", stem)
                out = self._attach_meta(out, stem, meta)
                parts.append(out)
                self.log.emit(f"  OK   {stem}  ({len(out)} rows)")
                n_ok += 1
            except Exception as e:
                self.log.emit(f"  FAIL {stem} - {e}")
                n_skip += 1

        result = pd.concat(parts, ignore_index=True) if parts else None
        self.log.emit(f"\n-- Done: {n_ok} bound, {n_skip} skipped.")
        return result, n_ok, n_skip
