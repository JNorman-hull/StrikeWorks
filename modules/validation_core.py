# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Sensor validation shared by Simple mode's Validate step
(page_simple_mode.py) and Advanced mode's Annotate page (page_annotate.py)
- one implementation, so the two can't drift apart.

  Auto process all  - accepts every processed sensor's already-detected
                      nadir (`pres_min.time.` from the index, else the
                      pressure minimum), saves its ROI window and marks it
                      validated, with no per-file review. Each sensor also
                      gets the one "worth a look" check: a real blade-strike
                      window should show a real HIG (impact accelerometer)
                      peak, so a window whose HIG max is under
                      FLAG_HIG_THRESHOLD_G is *flagged* for a human to
                      review. Ad hoc by design - it points a person at the
                      sensors worth a second look, it never rejects one.
  Validation state  - hstrike_processed (window saved at all, auto or
                      user), hstrike_user_validated (a human reviewed it
                      with Save + next), hstrike_user_adjusted (they moved
                      the nadir, not just re-confirmed it), hstrike_flagged.
  Save and export   - binds every saved window into one model-ready dataset
                      (page_dataset's segmented extraction), joins the
                      annotation columns recorded on the index, writes it to
                      the input data folder and into the library's running
                      dataset (model_features.csv), and hands it back to the
                      caller (both callers pass it on to Model prediction).
"""
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtCore import QEvent, QObject, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut

from . import annotation_schema as asch
from . import deployment_index as di
from . import raw_layout, sensor_config, settings

NADIR_T_COL = "pres_min.time."
NADIR_V_COL = "pres_min.kPa."
VALIDATED_COL = "hstrike_processed"          # Y once a window's been saved at all
USER_VALIDATED_COL = "hstrike_user_validated"  # Y only once a human reviewed it
FLAGGED_COL = "hstrike_flagged"              # Y = auto process's "worth a look" check
USER_ADJUSTED_COL = "hstrike_user_adjusted"  # Y = human moved the nadir and re-saved
HIG_WINDOW_MAX_COL = "hstrike_hig_window_max_g"
FLAG_HIG_THRESHOLD_G = 95.0

WIN_SEC = 0.2
WIN_DIR = raw_layout.WINDOW_DIR


def sample_rate():
    return sensor_config.active().output_rate_hz or 2000


def processed_sensor_files(lib_root):
    """[{"stem", "path"}] for every processed sensor CSV in a library."""
    if not lib_root:
        return []
    return [{"stem": p.stem, "path": p} for p in raw_layout.processed_csvs(lib_root)]


def detect_nadir_idx(stem, df, time, pres, index_df):
    """The index's recorded nadir time if there is one, else the pressure
    minimum, else the middle of the recording."""
    if (index_df is not None and "file" in index_df.columns
            and NADIR_T_COL in index_df.columns):
        row = index_df[index_df["file"] == stem]
        if not row.empty:
            val = row[NADIR_T_COL].iloc[0]
            if pd.notna(val):
                return int(np.argmin(np.abs(time - float(val))))
    if pres is not None and len(pres):
        return int(np.argmin(pres))
    return len(df) // 2


def window_bounds(nadir_idx, n, win_sec, fs=None):
    half_n = int(round(win_sec / 2 * (fs or sample_rate())))
    return max(0, nadir_idx - half_n), min(n - 1, nadir_idx + half_n)


def signals(df):
    """(time, pressure, hig) arrays out of a processed sensor CSV."""
    time = (df["time_s"].to_numpy(dtype=float) if "time_s" in df.columns
            else np.arange(len(df), dtype=float))
    pres = (df["pressure_kpa"].to_numpy(dtype=float)
            if "pressure_kpa" in df.columns else None)
    hig = (df["higacc_mag_g"].to_numpy(dtype=float)
           if "higacc_mag_g" in df.columns else None)
    return time, pres, hig


def _yn_set(index_df, col):
    if index_df is None or col not in index_df.columns or "file" not in index_df.columns:
        return set()
    return set(index_df[index_df[col].astype(str).str.strip().str.upper() == "Y"]
               ["file"].astype(str))


def validation_status(index_df):
    """(auto_validated, user_validated, flagged, bad) stem sets - the one
    place every list, count, Jump and leave-warning reads these from."""
    return (_yn_set(index_df, VALIDATED_COL), _yn_set(index_df, USER_VALIDATED_COL),
            _yn_set(index_df, FLAGGED_COL), _yn_set(index_df, di.BAD_SENS_COL))


def needs_review(stem, status):
    """Flagged by Auto process all and not yet reviewed by a person."""
    _auto, user, flagged, _bad = status
    return stem in flagged and stem not in user


def status_colour(stem, status, ok, warn, bad, accent):
    """The list colour convention: bad red, user-validated green, flagged-
    and-unreviewed amber, auto-validated accent, anything else plain."""
    auto, user, _flagged, bad_set = status
    if stem in bad_set:
        return bad
    if stem in user:
        return ok
    if needs_review(stem, status):
        return warn
    if stem in auto:
        return accent
    return None


def status_counts(stems, status):
    auto, user, flagged, bad = status
    stems = list(stems)
    return {
        "total": len(stems),
        "auto": sum(1 for s in stems if s in auto),
        "flagged": sum(1 for s in stems if s in flagged),
        "flagged_reviewed": sum(1 for s in stems if s in flagged and s in user),
        "user": sum(1 for s in stems if s in user),
        "bad": sum(1 for s in stems if s in bad),
    }


def counts_text(stems, status):
    """The list's counter. "Flagged, to review" counts down as flagged
    sensors are reviewed (Save + Next) - the flag the list shows is
    "flagged and not reviewed yet", so that's the number that clears."""
    c = status_counts(stems, status)
    left = c["flagged"] - c["flagged_reviewed"]
    return (f"Flagged, to review: {left} of {c['flagged']}\n"
            f"Reviewed by you: {c['user']}/{c['total']}\n"
            f"Auto-validated: {c['auto']}/{c['total']}"
            + (f"\n({c['bad']} bad)" if c["bad"] else ""))


def legend_html(ok, warn, bad, accent, plain, columns=1):
    """What the list colours mean - shown under every validation list, in
    one column (a narrow list) or two (under a wide one, to save height)."""
    def row(colour, text):
        return (f"<span style='color:{colour};font-size:14px;'>&#9679;</span>"
                f"&nbsp;{text}")
    if columns == 1:
        return "<br>".join([
            row(warn, "Flagged - needs your review (top of the list)"),
            row(ok, "Reviewed by you (Save + Next)"),
            row(accent, "Auto-validated, not flagged"),
            row(plain, "Not processed yet"),
            row(bad, "Marked bad"),
        ])
    # the compact form - the caller gives the full wording as a tooltip
    rows = [row(warn, "Flagged, needs review"), row(ok, "Reviewed by you"),
            row(accent, "Auto-validated"), row(plain, "Not processed yet"),
            row(bad, "Marked bad")]
    cells = [rows[i:i + columns] for i in range(0, len(rows), columns)]
    body = "".join(
        "<tr>" + "".join(f"<td style='padding-right:14px;'>{c}</td>" for c in r)
        + "</tr>" for r in cells)
    return f"<table cellspacing='0' cellpadding='0'>{body}</table>"


def outstanding_flagged(stems, status):
    return [s for s in stems if needs_review(s, status)]


def next_after_save(order, saved, status):
    """Which sensor Save + Next goes to. `order` is the list as it was shown
    before the save, `status` the validation status after it.

    The sensor that followed the saved one in the list, while that one is
    still flagged; else the first flagged sensor still waiting anywhere in
    the list (one skipped further up); once none are left, simply the
    sensor that followed the saved one. None at the end of the list."""
    after = order[order.index(saved) + 1:] if saved in order else []
    if after and needs_review(after[0], status):
        return after[0]
    pending = [s for s in order if s != saved and needs_review(s, status)]
    if pending:
        return pending[0]
    return after[0] if after else None


SAVE_NEXT_KEYS = "Ctrl+V"


class _SaveNextKeyFilter(QObject):
    """Ctrl+V pressed on the list itself - covers the case the page-wide
    shortcut can't (its window isn't the active one, e.g. while the dev
    console has focus during a demo run)."""

    def __init__(self, callback, parent):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_V
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self._callback()
            return True
        return False


def install_save_next_shortcut(page, list_widget, callback):
    """Ctrl+V = Save + Next anywhere on `page` (a text box that's being
    typed in keeps Ctrl+V as paste - Qt gives it precedence), and on
    `list_widget` itself even when the page-wide shortcut can't fire."""
    shortcut = QShortcut(QKeySequence(SAVE_NEXT_KEYS), page)
    shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    shortcut.activated.connect(callback)
    key_filter = _SaveNextKeyFilter(callback, list_widget)
    list_widget.installEventFilter(key_filter)
    return shortcut


def all_validated(stems, status):
    c = status_counts(stems, status)
    return bool(c["total"]) and c["auto"] == c["total"] and (
        c["flagged"] == 0 or c["flagged_reviewed"] >= c["flagged"])


def _write_window(lib_root, stem, df, start, end, win_sec):
    """Write `<stem>_<ms>ms.csv`, dropping any window saved for this sensor
    at a different width - otherwise both would be bound into the dataset."""
    out_dir = Path(lib_root) / WIN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ms = int(round(win_sec * 1000))
    keep = f"{stem}_{ms}ms"
    pattern = re.compile(re.escape(stem) + r"_\d+ms")
    for old in out_dir.glob(f"{stem}_*ms.csv"):
        if old.stem != keep and pattern.fullmatch(old.stem):
            try:
                old.unlink()
            except OSError:
                pass
    df.iloc[start:end + 1].to_csv(out_dir / f"{keep}.csv", index=False)


def _ensure_object_cols(index_df, cols):
    for col in cols:
        if col not in index_df.columns:
            index_df[col] = ""
        index_df[col] = index_df[col].astype(object)
    return index_df


def save_window(lib_root, index_df, stem, df, nadir_idx, win_sec,
                user_validated=False, nadir_changed=False):
    """Save one sensor's ROI window and record it on `index_df` (returned -
    it may have grown a row): nadir time/value, window bounds, HIG max in
    the window, validated, flagged, and - for a human's Save + next - user
    validated / user adjusted. The caller writes the index."""
    time, pres, hig = signals(df)
    start, end = window_bounds(nadir_idx, len(df), win_sec)
    _write_window(lib_root, stem, df, start, end, win_sec)

    hig_max = (float(np.max(hig[start:end + 1]))
               if hig is not None and len(hig) else float("nan"))
    if index_df is None:
        index_df = pd.DataFrame({"file": []})
    mask = index_df["file"].astype(str) == stem
    if not mask.any():
        index_df = pd.concat([index_df, pd.DataFrame([{"file": stem}])],
                             ignore_index=True)
        mask = index_df["file"].astype(str) == stem
    index_df = _ensure_object_cols(
        index_df, (VALIDATED_COL, FLAGGED_COL, USER_VALIDATED_COL,
                   USER_ADJUSTED_COL))
    index_df.loc[mask, NADIR_T_COL] = float(time[nadir_idx])
    index_df.loc[mask, NADIR_V_COL] = (float(pres[nadir_idx])
                                       if pres is not None else float("nan"))
    index_df.loc[mask, "nadir_window_start"] = time[start]
    index_df.loc[mask, "nadir_window_end"] = time[end]
    index_df.loc[mask, HIG_WINDOW_MAX_COL] = hig_max
    index_df.loc[mask, VALIDATED_COL] = "Y"
    flagged = not np.isnan(hig_max) and hig_max < FLAG_HIG_THRESHOLD_G
    index_df.loc[mask, FLAGGED_COL] = "Y" if flagged else "N"
    if user_validated:
        index_df.loc[mask, USER_VALIDATED_COL] = "Y"
        if nadir_changed:
            index_df.loc[mask, USER_ADJUSTED_COL] = "Y"
    return index_df


def write_index(lib_root, index_df):
    path = di.index_path(lib_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    index_df.to_csv(path, index=False)


class AutoProcessThread(QThread):
    """Auto process all's per-sensor loop, off the GUI thread (a library
    on OneDrive makes it slow). Takes the sensor files and the index,
    returns the updated index; sensors a person already validated are left
    as they are."""

    progress = Signal(int, int)          # n done so far, total
    done = Signal(object, int)           # updated index_df, n newly validated

    def __init__(self, lib_root, win_sec, files, index_df, parent=None):
        super().__init__(parent)
        self._lib_root = lib_root
        self._win_sec = win_sec
        self._files = list(files)
        self._index_df = (index_df if index_df is not None
                          else pd.DataFrame({"file": []}))

    def run(self):
        index_df = self._index_df
        already = _yn_set(index_df, VALIDATED_COL)
        total = len(self._files)
        n_done = 0
        for i, f in enumerate(self._files):
            stem = f["stem"]
            if stem not in already:
                try:
                    df = pd.read_csv(f["path"], low_memory=False)
                    time, pres, _hig = signals(df)
                    nadir_idx = detect_nadir_idx(stem, df, time, pres, index_df)
                    index_df = save_window(self._lib_root, index_df, stem, df,
                                           nadir_idx, self._win_sec)
                    n_done += 1
                except Exception:
                    pass
            self.progress.emit(i + 1, total)
        self.done.emit(index_df, n_done)


def processing_review_rows(stems, index_df):
    """How validation actually went - auto vs. user, how many sensors the
    HIG check flagged, how many of those a person reviewed, how many they
    actually moved the nadir on. Fed into reports."""
    stems = list(stems)
    if not stems:
        return []
    status = validation_status(index_df)
    c = status_counts(stems, status)
    adjusted = _yn_set(index_df, USER_ADJUSTED_COL)
    return [
        ("Auto-validated", f"{c['auto']}/{c['total']}"),
        (f"Flagged for review (HIG < {FLAG_HIG_THRESHOLD_G:.0f}g)", c["flagged"]),
        ("Flagged sensors reviewed", f"{c['flagged_reviewed']}/{c['flagged']}"),
        ("User-validated (any sensor)", f"{c['user']}/{c['total']}"),
        ("Nadir moved by user", sum(1 for s in stems if s in adjusted)),
    ]


def annotation_columns(index_df):
    """The annotation variables (annotation_schema) the index actually
    has values for."""
    if index_df is None:
        return []
    return [v.name for v in asch.all_variables() if v.name in index_df.columns]


def join_annotations(df, index_df):
    """Adds each sensor's recorded annotation values (index columns) onto
    its rows of an extracted dataset, so an exported dataset is ready to
    train on, not just to predict on."""
    cols = [c for c in annotation_columns(index_df) if c not in df.columns]
    if not cols or "file" not in df.columns:
        return df
    sensors = di.sensor_rows(index_df).drop_duplicates("file", keep="last")
    sensors = sensors.set_index(sensors["file"].astype(str))
    keys = df["file"].astype(str)
    df = df.copy()
    for col in cols:
        df[col] = keys.map(sensors[col])
    return df


# older annotation spreadsheets' column names and values (e.g. the demo
# pack's annotations CSV) -> the app's annotation variables
# (annotation_schema.DEFAULT_VARIABLES)
_LEGACY_ANNOTATION_COLS = {
    "passage_type": "overall_passage_type",
    "leading_type": "leading_edge_type",
}
_PASSAGE_TYPE_MAP = {
    "no contact": "no_contact",
    "leading edge strike": "leading_edge",
    "other impeller collision": "other",
}


def import_annotations_csv(lib_root, csv_path):
    """Stamp a spreadsheet of per-sensor annotations onto the index.

    The CSV needs a `file` (or `sens_file`) column naming each sensor, plus
    any of the annotation variables - native names (overall_passage_type,
    ...) or the older spreadsheet's (passage_type, leading_type, with
    "No contact"/"Leading edge strike"/... values, mapped across). Only
    sensors already in the index are touched. Returns (n_sensors,
    [variables imported])."""
    ann = pd.read_csv(csv_path, low_memory=False)
    if "file" not in ann.columns and "sens_file" in ann.columns:
        ann = ann.rename(columns={"sens_file": "file"})
    if "file" not in ann.columns:
        raise ValueError("The CSV needs a 'file' column naming each sensor.")
    for old, new in _LEGACY_ANNOTATION_COLS.items():
        if old in ann.columns and new not in ann.columns:
            ann = ann.rename(columns={old: new})
    if "overall_passage_type" in ann.columns:
        mapped = (ann["overall_passage_type"].astype(str).str.strip()
                  .str.lower().map(_PASSAGE_TYPE_MAP))
        ann["overall_passage_type"] = mapped.fillna(ann["overall_passage_type"])
    if "concentric_pump_region" in ann.columns:
        ann["concentric_pump_region"] = (
            pd.to_numeric(ann["concentric_pump_region"], errors="coerce")
            .astype("Int64").astype(str).replace("<NA>", ""))
    names = [v.name for v in asch.all_variables() if v.name in ann.columns]
    if not names:
        raise ValueError("No annotation columns found in the CSV "
                         f"(expected any of: "
                         f"{', '.join(v.name for v in asch.all_variables())}).")

    index_df = di.read_index(lib_root)
    if index_df is None or "file" not in index_df.columns:
        raise ValueError("This library has no processed sensors yet.")
    ann = ann.drop_duplicates("file", keep="last")
    ann = ann.set_index(ann["file"].astype(str))
    keys = index_df["file"].astype(str)
    sensors = ~di.is_plan_row(index_df) & keys.isin(ann.index)
    for name in names:
        values = keys[sensors].map(ann[name]).map(
            lambda v: "" if pd.isna(v) or str(v).lower() == "nan" else str(v))
        if name not in index_df.columns:
            index_df[name] = ""
        index_df[name] = index_df[name].astype(object)
        has = values.astype(bool)
        index_df.loc[values[has].index, name] = values[has]
    write_index(lib_root, index_df)
    return int(sensors.sum()), names


def merge_into_running_dataset(lib_root, df):
    """Replace these sensors' blocks in the library's running dataset
    (`processed_sens_data/model_features.csv`, what Annotate's Save + next
    builds sensor by sensor) with `df`'s - so an export and the per-sensor
    path always agree on what's "in the dataset"."""
    path = Path(lib_root) / di.DATASET_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    stems = set(df["file"].astype(str))
    out = df
    if path.exists():
        try:
            existing = pd.read_csv(path, low_memory=False)
            existing = existing[~existing["file"].astype(str).isin(stems)]
            out = pd.concat([existing, df], ignore_index=True)
        except Exception:
            out = df
    out.to_csv(path, index=False)
    return path


class DatasetExporter(QObject):
    """Save and export: segmented extraction of every saved window (or just
    `selected` stems), plus annotation columns, written to the input data
    folder as `<name>_<timestamp>.csv`. `finished(df_or_None, path_or_None,
    message)`."""

    finished = Signal(object, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._name = "dataset"

    @property
    def running(self):
        return self._thread is not None and self._thread.isRunning()

    @property
    def thread(self):
        return self._thread

    def start(self, lib_root, name, selected=None):
        from .dataset_build import OPT_SEGMENTED, ExtractThread
        self._name = name or "dataset"
        self._lib_root = lib_root
        self._index_df = di.read_index(lib_root)
        self._thread = ExtractThread(lib_root, OPT_SEGMENTED,
                                      set(selected or ()), self._index_df,
                                      sensor_config.active())
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, n_ok, n_skip, n_rows):
        df = self._thread.result if self._thread is not None else None
        if df is None or not len(df):
            self.finished.emit(None, None, "Dataset build produced no rows.")
            return
        df = join_annotations(df, self._index_df)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = settings.get_input_data_dir()
        out_path = out_dir / f"{self._name}_{stamp}.csv"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_path, index=False)
        except Exception as e:
            self.finished.emit(None, None, f"Save failed: {e}")
            return
        # the library's own running dataset too - so Home/Deploy's "Dataset
        # built" and Annotate's "In dataset" agree with what was exported,
        # whichever mode exported it
        try:
            merge_into_running_dataset(self._lib_root, df)
        except Exception:
            pass
        self.finished.emit(
            df, out_path,
            f"Saved and exported {n_rows} row(s) ({n_ok} sensor(s)) to "
            f"{out_path.name}")
