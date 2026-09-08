# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Dev runner - a one-click, no-UI-clicking "demo pipeline" that exercises
Advanced mode end-to-end in its own dedicated "DevTest" library: create
library > Calculator > sensor config > study design (deployment, folder
opened in Explorer) > copy source recordings in from Testbed > raw data
processing > validate (simulated) > save and export > annotation import >
model training > deploy > predict > model comparison > export report.

This is the Advanced-mode demo only - `DevRunner`. Simple mode's demo
(`simple_dev_runner.SimpleDevRunner`) is a deliberately separate,
parallel implementation: rather than a hand-rolled reimplementation of
what Simple mode does, it drives page_simple_mode.SimpleModeDialog's own
widget-bound methods directly on the app's one real
window.simple_mode_dialog instance, so it stays honest to whatever Simple
mode's real behaviour actually is. The two share only genuinely common
infrastructure - the DevTest library/fixture setup and the Qt-event-loop
waiting helpers - via `_RunnerBase` below.

Every async step (a QThread or a subprocess-backed state signal) is
turned into a plain, sequential method call via `_wait_for`/`_race`: they
push a nested `QEventLoop` that only the awaited signal (or a timeout)
can quit. The GUI stays responsive while a step runs - it just means
`run()` itself doesn't return until the whole pipeline (or a failure, or
a stop) does, which is exactly what a "click Run and watch it go" demo
button wants.

Stopping: `request_stop()` is safe to call from anywhere (a button click
during a run) - it doesn't kill anything by force, just makes the next
opportunity (between steps, or the periodic poll inside `_wait_for`/
`_race`) raise `_StoppedByUser` and unwind cleanly. A training/prediction
subprocess already in flight when stopped keeps running in the
background to completion (the app has no subprocess-kill mechanism to
call here) - the demo just stops waiting for and using its result.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal

from . import deployment_index as di
from . import report_center
from . import sensor_config
from . import settings
from .page_dataset import OPT_SEGMENTED, _ExtractThread
from .page_initiate_deployment import _README_TEXT
from .page_process import _ProcessThread

_INPUT_DATA_DIR = Path(__file__).parent.parent / "input_data"
_ANNOTATIONS_CSV = _INPUT_DATA_DIR / "Pumpflow_2024_datatset1_only_annotations.csv"
# the source CSV's own columns (verified against it directly):
# file, concentric_pump_region, passage_type, leading_type, other_type -
# human-readable values ("No contact", "Leading edge strike", ...). The
# app's *native* annotation store (annotation_schema.py DEFAULT_VARIABLES,
# what Annotate writes onto the index via deployment_index.set_row_values,
# and what report_center.py's Annotation Report reads back) uses different
# names and enum-style values: overall_passage_type/leading_edge_type/
# other_type/concentric_pump_region, with overall_passage_type restricted
# to no_contact/leading_edge/other. Mapping onto the native names (rather
# than passing the source names straight through, an earlier version's
# mistake) means one merge feeds both the training dataset *and* the real
# per-sensor annotation record - ml_train_state.py's target-column
# detection (_TARGET_PREFERENCE) already accepts overall_passage_type as
# an alternative to passage_type, so nothing downstream loses out.
_ANNOTATION_JOIN_COL = "file"
_ANNOTATION_SOURCE_COLS = [
    "passage_type", "leading_type", "other_type", "concentric_pump_region",
]
_ANNOTATION_NATIVE_COLS = [
    "overall_passage_type", "leading_edge_type", "other_type",
    "concentric_pump_region",
]
_PASSAGE_TYPE_MAP = {
    "no contact": "no_contact",
    "leading edge strike": "leading_edge",
    "other impeller collision": "other",
}

_NADIR_T_COL = "pres_min.time."
_NADIR_V_COL = "pres_min.kPa."
_VALIDATED_COL = "hstrike_processed"
_WIN_SEC = 0.2

# every long-running step (processing, export, training x2, predict) uses
# this one generous ceiling - it's a "something is actually stuck, not
# just slow" backstop, not a tuned-per-step budget. 180s used to be
# process/export's own separate limit, which a real run on a
# OneDrive-synced library blew straight through (76 files took ~210s+) -
# raising it here is one number to keep sane instead of several, and the
# Stop button is the real way to bail out of a run that's merely slow.
_LONG_TIMEOUT_MS = 1_200_000


class _RunnerError(Exception):
    """A demo-pipeline step failed in a way that should stop the run and
    be reported back to the user, rather than an unexpected bug."""


class _StoppedByUser(Exception):
    """`request_stop()` was called - not a failure, just an early exit."""


class _RunnerBase(QObject):
    """Shared infrastructure for both demo runners (Advanced's `DevRunner`
    below, Simple's `simple_dev_runner.SimpleDevRunner`): the DevTest
    library/fixture setup, and the Qt-event-loop waiting/stopping
    machinery. Subclasses implement `_run()` and may override `_label()`
    for clearer log/finish messages; everything else here is ready to use
    as-is. Owned transiently by whatever triggered it (Adjustments' "Run
    demo pipeline" button) - construct, connect `finished`, call `run()`;
    `request_stop()` cancels a run in progress."""

    finished = Signal(bool, str)   # ok, message

    LIBRARY_NAME = "DevTest"
    SOURCE_LIBRARY_NAME = "Testbed"
    SOURCE_DEPLOYMENT_NAME = "Pumpflow_2024_training"
    SOURCE_TREATMENT_NAME = "500 rpm (100%)"

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._stop_requested = False

    def _label(self):
        return "Demo pipeline"

    # ── stopping ─────────────────────────────────────────────────────────────
    def request_stop(self):
        """Safe to call any time, including mid-run from a button click -
        see the module docstring's "Stopping" section for exactly what
        this does and doesn't guarantee."""
        if not self._stop_requested:
            self._stop_requested = True
            self._log("Stop requested - stopping at the next safe point "
                       "(a training/prediction subprocess already running "
                       "will keep going in the background, but the demo "
                       "won't wait for or use its result).")

    def _check_stop(self):
        if self._stop_requested:
            raise _StoppedByUser()

    # ── logging / waiting helpers ───────────────────────────────────────────
    def _log(self, msg):
        print(f"[dev-runner] {msg}")

    def _wait_for(self, signal, timeout_ms, label, trigger):
        """Runs `trigger()` (which must eventually cause `signal` to fire)
        and blocks this call - via a nested Qt event loop, so the GUI
        keeps painting/responding - until it does, `timeout_ms` passes, or
        `request_stop()` is called. Returns the signal's emitted args."""
        loop = QEventLoop()
        box = {}

        def _capture(*args):
            box["args"] = args
            loop.quit()

        signal.connect(_capture)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        poll = QTimer()
        poll.setInterval(300)
        poll.timeout.connect(lambda: loop.quit() if self._stop_requested else None)
        poll.start()
        self._log(f"Waiting for {label}...")
        trigger()
        loop.exec()
        timer.stop()
        poll.stop()
        signal.disconnect(_capture)
        self._check_stop()
        if "args" not in box:
            raise _RunnerError(f"{label} timed out after {timeout_ms // 1000}s")
        return box["args"]

    def _race(self, ok_signal, fail_signal, timeout_ms, label, trigger):
        """Like `_wait_for`, but for the app's paired success/failure
        signal convention (cv_finished/cv_failed, run_finished/
        run_failed, ...) - whichever fires first wins."""
        loop = QEventLoop()
        box = {}

        def _ok(*args):
            box["ok"] = True
            box["args"] = args
            loop.quit()

        def _fail(*args):
            box["ok"] = False
            box["args"] = args
            loop.quit()

        ok_signal.connect(_ok)
        fail_signal.connect(_fail)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        poll = QTimer()
        poll.setInterval(300)
        poll.timeout.connect(lambda: loop.quit() if self._stop_requested else None)
        poll.start()
        self._log(f"Waiting for {label}...")
        trigger()
        loop.exec()
        timer.stop()
        poll.stop()
        ok_signal.disconnect(_ok)
        fail_signal.disconnect(_fail)
        self._check_stop()
        if "ok" not in box:
            raise _RunnerError(f"{label} timed out after {timeout_ms // 1000}s")
        if not box["ok"]:
            msg = box["args"][0] if box["args"] else "failed"
            raise _RunnerError(f"{label} failed: {msg}")
        return box["args"]

    # ── entry point ──────────────────────────────────────────────────────────
    def run(self):
        label = self._label()
        self._log(f"{label} starting.")
        try:
            self._run()
        except _StoppedByUser:
            self._log(f"{label} stopped.")
            self.finished.emit(False, "Stopped.")
            return
        except _RunnerError as e:
            self._log(f"FAILED: {e}")
            self.finished.emit(False, str(e))
            return
        except Exception as e:
            self._log(f"FAILED (unexpected): {e}")
            self.finished.emit(False, f"Unexpected error: {e}")
            return
        self._log(f"{label} finished.")
        self.finished.emit(True, f"{label} finished - see the dev console for the full log.")

    def _run(self):
        raise NotImplementedError

    # ── 0: create/select the dedicated DevTest library (shared) ─────────────
    def _step_library(self, w):
        libraries_dir = settings.get_libraries_dir()
        lib_root = libraries_dir / self.LIBRARY_NAME
        was_new = not lib_root.exists()
        lib_root.mkdir(parents=True, exist_ok=True)
        # reuses Home's own "New library" logic (page_home.py._new_library) -
        # rescans libraries_dir, adds DevTest to the combo if it just
        # appeared, and syncs session_state.library to it either way, the
        # same as picking it there by hand
        w.home_page._refresh_library_combo(select=str(lib_root))
        self._log(f"Library: '{self.LIBRARY_NAME}' "
                   f"{'created' if was_new else 'reused'} at {lib_root} "
                   "- session switched to it.")
        return lib_root

    # ── source-recording copy-in (shared) ────────────────────────────────────
    def _find_source_treatment_dir(self):
        """The folder to copy every demo recording from - confirmed with
        the user directly: Testbed's own Pumpflow_2024_training deployment,
        '500 rpm (100%)' treatment. An exact path, not a fuzzy search -
        copying from the wrong folder (e.g. some other treatment) would be
        a much harder-to-notice mistake than a clear error here."""
        libraries_dir = settings.get_libraries_dir()
        source_dir = (libraries_dir / self.SOURCE_LIBRARY_NAME / "raw_sens_data"
                      / self.SOURCE_DEPLOYMENT_NAME / self.SOURCE_TREATMENT_NAME)
        if not source_dir.is_dir() or not any(source_dir.iterdir()):
            raise _RunnerError(
                f"Raw files: source folder not found (or empty): {source_dir}")
        return source_dir

    def _copy_source_files(self, treatment_dir):
        cfg = sensor_config.active()
        exts = cfg.required_extensions or [".imp"]
        primary = exts[0]

        existing = {p.stem.upper() for p in treatment_dir.glob(f"*{primary.upper()}")}
        if existing:
            self._log(f"Raw files: {len(existing)} already present in "
                       f"{treatment_dir.name} - reusing (nothing left to copy).")
            return

        source_dir = self._find_source_treatment_dir()
        candidates = sorted(
            p for p in source_dir.glob(f"*{primary.upper()}") if p.is_file())
        if not candidates:
            candidates = sorted(
                p for p in source_dir.glob(f"*{primary.lower()}") if p.is_file())
        if not candidates:
            raise _RunnerError(
                f"Raw files: no recordings found in {source_dir} to copy.")

        # copy, not move: this whole library tree lives inside a
        # live-syncing OneDrive folder, where a delete (the second half of
        # a move) can be silently undone by OneDrive's own cloud
        # reconciliation (observed directly: files vanished from the
        # destination while reappearing at the source, unmodified) - a
        # copy only ever adds a file, so there's nothing for OneDrive to
        # contest, and it has the side benefit of leaving Testbed's pool
        # untouched for reuse
        copied = 0
        for src in candidates:
            for ext_path in list(src.parent.glob(f"{src.stem}.*")):
                shutil.copy2(str(ext_path), str(treatment_dir / ext_path.name))
            copied += 1
        self._log(f"Raw files: copied {copied} recording(s) from {source_dir} "
                   f"into {treatment_dir}.")

    def _scan_treatment_files(self, folder, cfg):
        exts = cfg.required_extensions or [".imp"]
        primary, secondary = exts[0], exts[1:]

        def files_by_stem(ext):
            suffix = ext.lstrip(".")
            out = {p.stem.upper(): p for p in folder.glob(f"*.{suffix.upper()}")}
            for p in folder.glob(f"*.{suffix.lower()}"):
                out.setdefault(p.stem.upper(), p)
            return out

        found = {ext: files_by_stem(ext) for ext in exts}
        records = []
        for stem_up, main_path in sorted(found[primary].items()):
            paths = {primary: main_path}
            for ext in secondary:
                match = found[ext].get(stem_up)
                if match is not None:
                    paths[ext] = match
            records.append(dict(stem=main_path.stem, paths=paths,
                                 complete=len(paths) == len(exts)))
        return records


class DevRunner(_RunnerBase):
    """Advanced-mode demo pipeline - see module docstring."""

    DEPLOYMENT = {
        "site": "PF TEST RIG",
        "deployment_id": "DevTest_PF",
        "pump_turbine": "FS-700",
        "type": "Axial",
    }
    TREATMENT = {
        "treatment": "500 RPM",
        "head": "3",
        "flow": "1.32",
        "point_bep": "100",
        "rpm": "500",
        "runs": 1,
    }
    BSM_CONFIG_NAME = "pumpflow_configuration"
    SENSOR_CONFIG_KEY = "rapid"

    def _label(self):
        return "Advanced demo pipeline"

    def _run(self):
        w = self.window
        lib_root = self._step_library(w)
        self._check_stop()

        self._step_calculator(w)
        self._check_stop()
        self._step_sensor_config()
        treatment_dir = self._step_deployment(lib_root)
        self._check_stop()
        stems = self._step_process(lib_root, treatment_dir)
        self._check_stop()
        self._step_validate(lib_root, stems)
        self._check_stop()
        df = self._step_export(lib_root)
        self._check_stop()
        df = self._step_annotations(df)
        self._step_populate_annotation_records(lib_root, df, stems)
        self._check_stop()

        csv_path = self._write_dataset_csv(df)
        self._step_train(w, csv_path)
        self._check_stop()
        bin_path, mc_path = self._step_deploy(w)
        self._check_stop()

        self._step_predict(w, df, bin_path, mc_path)
        self._check_stop()
        self._step_compare(w)
        self._check_stop()
        self._step_report(w)

    # ── 1: BSM Calculator ───────────────────────────────────────────────────
    def _step_calculator(self, w):
        page = w.bsm_calculator_page
        idx = page.cmb_config.findText(self.BSM_CONFIG_NAME)
        if idx < 0:
            raise _RunnerError(
                f"Calculator: BSM config '{self.BSM_CONFIG_NAME}' not found "
                f"in input_data/BSM_config/.")
        page.cmb_config.setCurrentIndex(idx)
        page._load_selected_config()
        page.calculate()
        self._log("Calculator: pumpflow configuration loaded and calculated "
                   "(scaly + eel).")

        # Study design's "Load from Blade Strike Modelling" button reads
        # calculate()'s own latest-result file and populates the
        # precision table + figure as a side effect of the spinbox value
        # changing - it's a real button click, not something calculate()
        # triggers on its own, so the report's Study design section would
        # otherwise show the tab's untouched 10% default forever
        precision = getattr(getattr(w, "prepare_page", None),
                            "tab_precision", None)
        if precision is not None and hasattr(precision, "_load_from_bsm"):
            precision._load_from_bsm()
            self._log("Study design: loaded expected strike rate from "
                       "Blade Strike Modelling.")

    # ── 2: sensor config ─────────────────────────────────────────────────────
    def _step_sensor_config(self):
        sensor_config.set_active(self.SENSOR_CONFIG_KEY)
        self._log(f"Sensor config: '{self.SENSOR_CONFIG_KEY}' set active and saved.")

    # ── 3: study design / deployment ────────────────────────────────────────
    def _step_deployment(self, lib_root):
        ident = self.DEPLOYMENT["deployment_id"]
        treatment_name = self.TREATMENT["treatment"]
        dep_dir = lib_root / "raw_sens_data" / ident
        treatment_dir = dep_dir / treatment_name

        index_df = di.read_index(lib_root)
        exists = (index_df is not None and di.DEPLOYMENT_COL in index_df.columns
                  and (index_df[di.DEPLOYMENT_COL] == ident).any())
        if exists:
            self._log(f"Study design: deployment '{ident}' already exists - reusing it.")
        else:
            path, n = di.save_plan(lib_root, dict(self.DEPLOYMENT), [dict(self.TREATMENT)])
            self._log(f"Study design: created deployment '{ident}' "
                       f"({n} row(s) written to {path.name}).")

        (treatment_dir / "VIDEO").mkdir(parents=True, exist_ok=True)
        readme = dep_dir / "readme.txt"
        if not readme.exists():
            readme.write_text(_README_TEXT, encoding="utf-8")

        self._copy_source_files(treatment_dir)

        try:
            os.startfile(dep_dir)
            self._log(f"Study design: opened {dep_dir} in Explorer.")
        except OSError as e:
            self._log(f"Study design: could not open {dep_dir} in Explorer ({e}).")
        return treatment_dir

    # ── 4: raw data processing ──────────────────────────────────────────────
    def _step_process(self, lib_root, treatment_dir):
        cfg = sensor_config.active()
        files = self._scan_treatment_files(treatment_dir, cfg)
        complete = [f for f in files if f["complete"]]
        if not complete:
            raise _RunnerError(
                f"Raw data processing: no complete recordings found in {treatment_dir}.")

        out_dir = lib_root / "processed_sens_data"
        thread = _ProcessThread(complete, out_dir, lib_root, cfg)
        done_stems = []
        log_cb = lambda text: self._log(f"process: {text.strip()}")
        processed_cb = done_stems.append
        thread.log.connect(log_cb)
        thread.processed.connect(processed_cb)
        try:
            args = self._wait_for(thread.done, _LONG_TIMEOUT_MS,
                                  "raw data processing", thread.start)
        finally:
            # `_wait_for` only ever owned/disconnects `thread.done` - these
            # two are ours, and MUST be dropped here regardless of outcome.
            # A timeout (or a stop) doesn't kill the underlying QThread -
            # it just keeps running in the background to completion (seen
            # directly: 180s was too tight for this step, and the thread's
            # own "-- Processing: ..." log lines kept arriving for another
            # ~15 files *after* this method had already raised and
            # unwound). Left connected, each of those late signals calls
            # back into this already-abandoned run - print()ing through
            # the dev console's cross-thread stdout tee while the app is
            # mid-teardown from the "failed" path - which is exactly the
            # kind of reentrancy a native crash (exit 0xC0000409) comes
            # from. Disconnecting makes any further signal a no-op.
            try:
                thread.log.disconnect(log_cb)
            except (RuntimeError, TypeError):
                pass
            try:
                thread.processed.disconnect(processed_cb)
            except (RuntimeError, TypeError):
                pass
        code = args[0]
        self._log(f"Raw data processing: {len(done_stems)}/{len(complete)} sensor(s) "
                   f"processed{'' if code == 0 else ' (with errors)'}.")

        if done_stems:
            treatment_values = dict(self.DEPLOYMENT)
            treatment_values.update(self.TREATMENT)
            di.apply_treatment(lib_root, done_stems, treatment_values)
            self._log(f"Raw data processing: stamped {len(done_stems)} file(s) "
                       f"with treatment '{self.TREATMENT['treatment']}'.")
        return done_stems

    # ── 5: validate (simulated Save+Next on every sensor) ───────────────────
    def _step_validate(self, lib_root, stems):
        if not stems:
            self._log("Validate: nothing to validate (no processed files).")
            return
        csv_dir = lib_root / "processed_sens_data" / "csv"
        win_dir = lib_root / "processed_sens_data" / "nadir_window"
        win_dir.mkdir(parents=True, exist_ok=True)
        cfg = sensor_config.active()
        fs = cfg.output_rate_hz or 2000
        half_n = int(round(_WIN_SEC / 2 * fs))
        ms = int(round(_WIN_SEC * 1000))

        index_df = di.read_index(lib_root)
        if index_df is None:
            index_df = pd.DataFrame({"file": []})
        if _VALIDATED_COL not in index_df.columns:
            index_df[_VALIDATED_COL] = ""
        index_df[_VALIDATED_COL] = index_df[_VALIDATED_COL].astype(object)

        n_done = 0
        for stem in stems:
            csv_path = csv_dir / f"{stem}.csv"
            if not csv_path.exists():
                continue
            try:
                df = pd.read_csv(csv_path, low_memory=False)
            except Exception:
                continue
            time = (df["time_s"].to_numpy(dtype=float) if "time_s" in df.columns
                    else np.arange(len(df), dtype=float))
            pres = (df["pressure_kpa"].to_numpy(dtype=float)
                    if "pressure_kpa" in df.columns else None)
            nadir_idx = (int(np.argmin(pres)) if pres is not None and len(pres)
                         else len(df) // 2)
            start = max(0, nadir_idx - half_n)
            end = min(len(df) - 1, nadir_idx + half_n)
            df.iloc[start:end + 1].to_csv(win_dir / f"{stem}_{ms}ms.csv", index=False)

            mask = index_df["file"] == stem
            if not mask.any():
                index_df = pd.concat([index_df, pd.DataFrame([{"file": stem}])],
                                      ignore_index=True)
                index_df[_VALIDATED_COL] = index_df[_VALIDATED_COL].astype(object)
                mask = index_df["file"] == stem
            index_df.loc[mask, _NADIR_T_COL] = float(time[nadir_idx])
            index_df.loc[mask, _NADIR_V_COL] = (
                float(pres[nadir_idx]) if pres is not None else float("nan"))
            index_df.loc[mask, "nadir_window_start"] = time[start]
            index_df.loc[mask, "nadir_window_end"] = time[end]
            index_df.loc[mask, _VALIDATED_COL] = "Y"
            n_done += 1

        index_path = di.index_path(lib_root)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_df.to_csv(index_path, index=False)
        self._log(f"Validate: auto-validated {n_done}/{len(stems)} sensor(s) "
                   "(simulated Save+Next).")

    # ── 6: save and export ───────────────────────────────────────────────────
    def _step_export(self, lib_root):
        index_df = di.read_index(lib_root)
        cfg = sensor_config.active()
        thread = _ExtractThread(lib_root, OPT_SEGMENTED, set(), index_df, cfg)
        self._wait_for(thread.done, _LONG_TIMEOUT_MS, "dataset export", thread.start)
        df = thread.result
        if df is None or not len(df):
            raise _RunnerError("Save and export: produced no rows.")
        self._log(f"Save and export: {len(df)} row(s) extracted.")
        return df

    # ── 7: annotation import ────────────────────────────────────────────────
    def _step_annotations(self, df):
        if not _ANNOTATIONS_CSV.exists():
            self._log(f"Annotations: {_ANNOTATIONS_CSV.name} not found - skipping.")
            return df
        ann = pd.read_csv(_ANNOTATIONS_CSV, low_memory=False)
        needed = [_ANNOTATION_JOIN_COL, *_ANNOTATION_SOURCE_COLS]
        missing = [c for c in needed if c not in ann.columns]
        if missing:
            self._log(f"Annotations: {_ANNOTATIONS_CSV.name} missing columns "
                       f"{missing} - skipping.")
            return df

        native = pd.DataFrame({_ANNOTATION_JOIN_COL: ann[_ANNOTATION_JOIN_COL]})
        native["overall_passage_type"] = (
            ann["passage_type"].astype(str).str.strip().str.lower()
            .map(_PASSAGE_TYPE_MAP))
        native["leading_edge_type"] = ann["leading_type"]
        native["other_type"] = ann["other_type"]
        native["concentric_pump_region"] = (
            pd.to_numeric(ann["concentric_pump_region"], errors="coerce")
            .astype("Int64").astype(str).replace("<NA>", pd.NA))

        merged = df.merge(native, on=_ANNOTATION_JOIN_COL, how="left")
        n_matched = int(merged["overall_passage_type"].notna().sum())
        self._log(f"Annotations: imported from {_ANNOTATIONS_CSV.name} - "
                   f"{n_matched}/{len(merged)} row(s) matched to an "
                   f"overall_passage_type (the binary target).")
        return merged

    # ── 7b: populate the app's own per-sensor annotation records ────────────
    def _step_populate_annotation_records(self, lib_root, df, stems):
        """report_center.py's Annotation Report reads two things that
        `_step_annotations` alone doesn't touch: global_sensor_index.csv's
        own annotation columns (for the per-variable value-count tables)
        and processed_sens_data/model_features.csv's "file" column (for
        the "in dataset (annotated + saved)" count - page_annotate.py's
        own _dataset_path/_load_dataset_stems). Without this, the report
        showed "0 in dataset" / "no annotation values recorded" even
        though the training dataset itself carried the values fine."""
        if not stems or not any(c in df.columns for c in _ANNOTATION_NATIVE_COLS):
            self._log("Annotations: no native annotation columns to record.")
            return

        per_file = (df[df["file"].isin(stems)]
                    .groupby("file", as_index=True).first())

        index_df = di.read_index(lib_root)
        if index_df is not None and "file" in index_df.columns:
            for col in _ANNOTATION_NATIVE_COLS:
                if col not in per_file.columns:
                    continue
                if col not in index_df.columns:
                    index_df[col] = ""
                index_df[col] = index_df[col].astype(object)
                for stem, value in per_file[col].items():
                    if pd.isna(value) or str(value).strip() == "":
                        continue
                    index_df.loc[index_df["file"] == stem, col] = str(value)
            index_path = di.index_path(lib_root)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_df.to_csv(index_path, index=False)
            self._log(f"Annotations: stamped annotation values onto "
                       f"{len(per_file)} index row(s).")

        dataset_path = lib_root / "processed_sens_data" / "model_features.csv"
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        block = df[df["file"].isin(stems)]
        if dataset_path.exists():
            try:
                existing = pd.read_csv(dataset_path, low_memory=False)
                existing = existing[~existing["file"].isin(stems)]
                block = pd.concat([existing, block], ignore_index=True)
            except Exception:
                pass
        block.to_csv(dataset_path, index=False)
        self._log(f"Annotations: {len(stems)} sensor(s) now in "
                   f"{dataset_path.name} (Annotate's own dataset).")

    def _write_dataset_csv(self, df):
        _INPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _INPUT_DATA_DIR / f"{self.DEPLOYMENT['deployment_id']}_devrun_{ts}.csv"
        df.to_csv(path, index=False)
        self._log(f"Dataset written to {path.name} ({len(df)} rows) - this session's data.")
        return path

    # ── 8: model training ────────────────────────────────────────────────────
    def _step_train(self, w, csv_path):
        state = w.ml_training_page.state
        ok, msg = state.load_dataset_csv(csv_path)
        if not ok:
            raise _RunnerError(f"Model training: {msg}")
        self._log(f"Model training: {msg} (default settings, auto-detected).")
        self._ensure_train_ready(state)

        self._race(state.cv_finished, state.cv_failed, _LONG_TIMEOUT_MS,
                   "cross-validation training", state.run_cv)
        self._log("Model training: cross-validation complete (Train model).")

        self._race(state.final_finished, state.final_failed, _LONG_TIMEOUT_MS,
                   "final model training", state.run_final)
        self._log("Model training: final model trained (Train final model).")

    def _ensure_train_ready(self, state):
        """`state.ready` after `load_dataset_csv` reflects default settings
        applied to whatever dataset just loaded - for a single-treatment
        demo dataset, the two-stage (binary + region) pipeline can
        genuinely fail its own default n-fold CV check on the region
        stage alone (too few recordings in some region class) even though
        the binary stage is fine. That's a real data-size limit, not a bug
        - so if region/multiclass checks are the *only* thing blocking
        readiness, disable that stage for this run (matches what
        "Region model" already does when off: a warning, not a failure)
        rather than aborting the whole demo. Any other failing check is
        reported in full, not guessed at or silently worked around."""
        if state.ready:
            return
        fail_labels = [label for s, label, _ in state.checks if s == "fail"]
        if fail_labels and state.train_multiclass and \
                all(label.startswith("Region") for label in fail_labels):
            self._log(
                "Model training: the region/multiclass stage can't meet "
                f"default {state.n_folds}-fold cross-validation on this "
                f"dataset ({'; '.join(fail_labels)}) - disabling it for "
                "this run (binary stage only).")
            state.train_multiclass = False
            state.validate()
        if not state.ready:
            fails = [f"{label}: {detail}" for s, label, detail in state.checks
                     if s == "fail"]
            raise _RunnerError(
                "Model training: configuration not ready - " + "; ".join(fails))

    # ── 9: deploy ─────────────────────────────────────────────────────────────
    def _step_deploy(self, w):
        state = w.ml_training_page.state
        session_state = getattr(w, "session_state", None)
        out = session_state.output_dir() if session_state is not None else None
        models_dir = (out / "models") if out is not None else settings.get_models_dir()
        version = state.suggest_version(models_dir)
        pkg, deployed = state.deploy(models_dir, version)
        self._log(f"Model training: deployed v{version} to {models_dir} "
                   f"({len(deployed)} model file(s)).")
        bin_path = next((p for p in deployed if p.name.startswith("binary")), None)
        mc_path = next((p for p in deployed if p.name.startswith("multiclass")), None)
        return bin_path, mc_path

    # ── 10: predict ───────────────────────────────────────────────────────────
    def _step_predict(self, w, df, bin_path, mc_path):
        state = w.ml_prediction_page.state
        if bin_path is not None:
            ok, msg = state.select_bin_model(bin_path)
            if not ok:
                raise _RunnerError(f"Predict: {msg}")
        ok, msg = state.select_mc_model(mc_path)
        if mc_path is not None and not ok:
            self._log(f"Predict: multiclass model not applied - {msg}")

        w.ml_prediction_page.on_dataset_ready(
            df, f"Dev runner - {self.DEPLOYMENT['deployment_id']}")
        self._log("Predict: this session's model and dataset selected.")

        self._race(state.run_finished, state.run_failed, _LONG_TIMEOUT_MS,
                   "prediction run", state.run_prediction)
        n_rows = len(state.summary) if state.summary is not None else 0
        self._log(f"Predict: complete - {n_rows} treatment row(s) in summary.")

    # ── 11: compare models ───────────────────────────────────────────────────
    def _step_compare(self, w):
        w.biological_page._refresh_comparison()
        self._log("Model comparison: refreshed against this run's BSM + prediction results.")

    # ── 12: export report of all ─────────────────────────────────────────────
    def _step_report(self, w):
        sections = report_center.all_sections(w)
        checked = {s.key for s in sections if s.available}
        if not checked:
            raise _RunnerError("Export report: no sections available to export.")
        out_dir = report_center.default_output_dir(w)
        doc_path, warnings = report_center.assemble(sections, out_dir, checked)
        for warn in warnings:
            self._log(f"Export report: warning - {warn}")
        self._log(f"Export report: {len(checked)} section(s) written to {doc_path}")
        return doc_path
