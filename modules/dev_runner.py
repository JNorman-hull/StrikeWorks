# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Demo runners - one-click, unattended walkthroughs of the real app,
started from the Dev console (dev_console.py). Both drive the app's own
pages and widgets exactly as a person clicking through would, so a demo is
an honest test of the workflow rather than a separate copy of it:

  Simple demo    - Simple mode's wizard (window.simple_mode_dialog):
                   library > deployment (DeploymentEditor) > copy the demo
                   recordings in > process (FileInventory) > Auto process
                   all > Save and export > predict (the deployed default
                   model) > download the report.
  Advanced demo  - the full app's pages: library > BSM Calculator > Study
                   design (strike rate from the Calculator, sample size) >
                   Create and edit deployment (the same DeploymentEditor) >
                   copy in > Raw data processing (the same FileInventory) >
                   Annotate (Auto process all, Import annotations CSV, Save
                   and export) > Train > Deploy > Predict > Model comparison
                   > report.

Where the demo's data comes from - the demo pack
------------------------------------------------
A folder shaped like a library, shipped to users separately and dropped
into their libraries folder:

    demo_data/
      raw_sens_data/<deployment>/<treatment>/[Run <n>/]<recordings>
                                            [VIDEO/<stem>_vid_*.mp4]
      *annotations*.csv        per-sensor annotations (Advanced demo)
      demo.json                optional - see DemoSource

Found (first match) at `<libraries folder>/demo_data`, then the app's own
`libraries/demo_data`, then the older `Testbed` name (the app's own copy
first) (`settings.DEMO_DATA_NAME`; `demo_data` is never listed as a library). The
deployment, treatment and run names come from its folders; each
recording is *copied* (never moved) into the demo library, which is
created inside the user's configured libraries folder - so the demo's
output sits wherever their libraries do (a OneDrive folder stays on
OneDrive).

Waiting: every async step (a QThread or a subprocess-backed state signal)
becomes a sequential call via `_wait_for`/`_race`/`_wait_until`, which run
a nested QEventLoop until the step signals, times out, or `request_stop()`
is called - the GUI keeps painting throughout. Stop takes effect at the
next safe point; a training/prediction subprocess already running finishes
in the background, the demo just stops waiting for it.
"""
import json
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from . import deployment_index as di
from . import raw_layout, report_center, sensor_config, settings
from .edition import simple_only

DEMO_LIBRARY_NAME = "StrikeWorks_demo"
_FALLBACK_ANNOTATIONS = (settings.app_root() / "input_data"
                         / "Pumpflow_2024_datatset1_only_annotations.csv")

# defaults for a demo pack without a demo.json - the Pumpflow 2024 test
# rig the shipped demo recordings come from
_DEFAULT_DEPLOYMENT = {"site": "PF TEST RIG", "pump_turbine": "FS-700",
                       "type": "Axial"}
_DEFAULT_CONDITIONS = {"head": "3", "flow": "1.32", "point_bep": "100"}
_DEFAULT_BSM_CONFIG = "pumpflow_configuration"
_STUDY_TARGET_PRECISION_PP = 10.0

# one generous ceiling for every long step - a "something is actually
# stuck" backstop, not a per-step budget (76 files over OneDrive took
# 13 min in September's runs); Stop is the way out of a merely slow run
_LONG_TIMEOUT_MS = 1_800_000


class _RunnerError(Exception):
    """A demo step failed in a way that should stop the run and be reported."""


class _StoppedByUser(Exception):
    """`request_stop()` was called - not a failure, just an early exit."""


# ── the demo pack ────────────────────────────────────────────────────────────
class DemoSource:
    """The demo pack's contents: one deployment (the first under its
    raw_sens_data), its treatments and runs, their recording folders, the
    annotations CSV, and the details a deployment needs.

    demo.json (all optional):
        {"deployment": {"site": ..., "pump_turbine": ..., "type": ...},
         "treatments": {"500 RPM": {"head": "3", "flow": "1.32",
                                    "point_bep": "100", "rpm": "500"}},
         "sensor": "rapid", "bsm_config": "pumpflow_configuration"}
    """

    def __init__(self, root):
        self.root = Path(root)
        raw = self.root / raw_layout.RAW_DIR
        deps = [p for p in sorted(raw.iterdir())
                if p.is_dir() and not raw_layout.is_video_dir(p.name)]
        if not deps:
            raise _RunnerError(f"Demo pack has no deployment folder: {raw}")
        self.deployment_dir = deps[0]
        self.extra_deployments = [p.name for p in deps[1:]]
        manifest = {}
        if (self.root / "demo.json").exists():
            try:
                manifest = json.loads((self.root / "demo.json").read_text(
                    encoding="utf-8"))
            except Exception as e:
                raise _RunnerError(f"demo.json could not be read: {e}")
        self.sensor = manifest.get("sensor") or sensor_config.DEFAULT_KEY
        self.bsm_config = manifest.get("bsm_config") or _DEFAULT_BSM_CONFIG
        self.deployment = {**_DEFAULT_DEPLOYMENT,
                           **manifest.get("deployment", {}),
                           di.DEPLOYMENT_COL: self.deployment_dir.name}
        conditions = manifest.get("treatments", {})

        cfg = sensor_config.get(self.sensor) or sensor_config.active()
        primary = (cfg.required_extensions or [".imp"])[0].lstrip(".").lower()
        self.treatments = []          # [{treatment, head, ..., runs}]
        self.treatment_dirs = {}      # name -> source folder
        self.n_recordings = 0
        for tdir in sorted(self.deployment_dir.iterdir()):
            if not tdir.is_dir() or raw_layout.is_video_dir(tdir.name):
                continue
            runs = [int(raw_layout.run_label(p.name)) for p in tdir.iterdir()
                    if p.is_dir() and raw_layout.run_label(p.name)]
            n = sum(1 for p in tdir.rglob("*")
                    if p.is_file() and p.suffix.lstrip(".").lower() == primary
                    and not raw_layout.in_video_dir(p, raw))
            if not n:
                continue
            rpm = re.search(r"(\d+(?:\.\d+)?)\s*rpm", tdir.name, re.IGNORECASE)
            values = {di.TREATMENT_COL: tdir.name, **_DEFAULT_CONDITIONS,
                      "rpm": rpm.group(1) if rpm else "",
                      **conditions.get(tdir.name, {}),
                      "runs": max(runs) if runs else 1}
            self.treatments.append(values)
            self.treatment_dirs[tdir.name] = tdir
            self.n_recordings += n
        if not self.treatments:
            raise _RunnerError(
                f"Demo pack has no recordings under {self.deployment_dir}")
        found = sorted(self.root.glob("*annotation*.csv"))
        self.annotations_csv = (found[0] if found else
                                _FALLBACK_ANNOTATIONS
                                if _FALLBACK_ANNOTATIONS.exists() else None)

    @property
    def deployment_id(self):
        return self.deployment[di.DEPLOYMENT_COL]

    @staticmethod
    def find():
        """The demo pack folder, or None: `demo_data` in the libraries
        folder, then in the app's own libraries/; failing that the older
        `Testbed` name - the app's own copy first, since a libraries folder
        can hold a real working library that happens to be called Testbed."""
        libs, app_libs = settings.get_libraries_dir(), settings.app_root() / "libraries"
        candidates = [libs / settings.DEMO_DATA_NAME, app_libs / settings.DEMO_DATA_NAME,
                      app_libs / "Testbed", libs / "Testbed"]
        for folder in candidates:
            if (Path(folder) / raw_layout.RAW_DIR).is_dir():
                return Path(folder)
        return None


# ── shared runner machinery ─────────────────────────────────────────────────
class _RunnerBase(QObject):
    """Construct, connect `finished`, call `run()`; `request_stop()` cancels."""

    finished = Signal(bool, str)   # ok, message

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._stop_requested = False
        self.source = None
        self.lib_root = None

    def _label(self):
        return "Demo"

    # ── stopping ─────────────────────────────────────────────────────────────
    def request_stop(self):
        if not self._stop_requested:
            self._stop_requested = True
            self._log("Stop requested - stopping at the next safe point (a "
                      "training/prediction subprocess already running will "
                      "finish in the background, but the demo won't wait "
                      "for or use its result).")

    def _check_stop(self):
        QApplication.processEvents()
        if self._stop_requested:
            raise _StoppedByUser()

    # ── logging / waiting ────────────────────────────────────────────────────
    def _log(self, msg):
        print(f"[demo] {msg}")

    def _loop(self, timeout_ms, box, quit_when=None):
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        poll = QTimer()
        poll.setInterval(200)
        poll.timeout.connect(
            lambda: loop.quit() if self._stop_requested
            or (quit_when is not None and quit_when()) else None)
        poll.start()
        box["loop"] = loop
        loop.exec()
        timer.stop()
        poll.stop()

    def _wait_for(self, signal, timeout_ms, label, trigger):
        """Connects to `signal`, runs `trigger()` (which must eventually
        make it fire), and waits. Returns the signal's args."""
        box = {}

        def _capture(*args):
            box["args"] = args
            if "loop" in box:
                box["loop"].quit()

        signal.connect(_capture)
        self._log(f"Waiting for {label}...")
        try:
            trigger()
            if "args" not in box:
                self._loop(timeout_ms, box)
        finally:
            try:
                signal.disconnect(_capture)
            except (RuntimeError, TypeError):
                pass
        self._check_stop()
        if "args" not in box:
            raise _RunnerError(f"{label} timed out after {timeout_ms // 1000}s")
        return box["args"]

    def _race(self, ok_signal, fail_signal, timeout_ms, label, trigger):
        """`_wait_for` for the app's paired success/failure signals
        (cv_finished/cv_failed, run_finished/run_failed, ...)."""
        box = {}

        def _ok(*args):
            box.update(ok=True, args=args)
            if "loop" in box:
                box["loop"].quit()

        def _fail(*args):
            box.update(ok=False, args=args)
            if "loop" in box:
                box["loop"].quit()

        ok_signal.connect(_ok)
        fail_signal.connect(_fail)
        self._log(f"Waiting for {label}...")
        try:
            trigger()
            if "ok" not in box:
                self._loop(timeout_ms, box)
        finally:
            for sig, slot in ((ok_signal, _ok), (fail_signal, _fail)):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self._check_stop()
        if "ok" not in box:
            raise _RunnerError(f"{label} timed out after {timeout_ms // 1000}s")
        if not box["ok"]:
            msg = box["args"][0] if box["args"] else "failed"
            raise _RunnerError(f"{label} failed: {str(msg).splitlines()[-1]}")
        return box["args"]

    def _wait_thread(self, thread, label):
        """Waits for a QThread a page started itself (Auto process all) to
        finish *and* for its queued `done` to reach the page - polling,
        since the thread may already be done by the time we get it back."""
        self._log(f"Waiting for {label}...")
        box = {}
        if thread.isRunning():
            self._loop(_LONG_TIMEOUT_MS, box, quit_when=thread.isFinished)
        for _ in range(5):
            QApplication.processEvents()
        self._check_stop()
        if not thread.isFinished():
            raise _RunnerError(f"{label} timed out")

    @staticmethod
    @contextmanager
    def _headless_dialogs(existing_directory=None):
        """The app's own OK-only info/warning/critical pop-ups and the one
        folder picker (download report) - fine for a person, a hang for an
        unattended demo - suppressed around just the call that can raise
        one, then restored."""
        orig = (QMessageBox.information, QMessageBox.warning,
                QMessageBox.critical, QMessageBox.question,
                QFileDialog.getExistingDirectory)
        noop = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        QMessageBox.information = noop
        QMessageBox.warning = noop
        QMessageBox.critical = noop
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)
        if existing_directory is not None:
            QFileDialog.getExistingDirectory = staticmethod(
                lambda *a, **k: existing_directory)
        try:
            yield
        finally:
            (QMessageBox.information, QMessageBox.warning,
             QMessageBox.critical, QMessageBox.question,
             QFileDialog.getExistingDirectory) = orig

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
            import traceback
            traceback.print_exc()
            self._log(f"FAILED (unexpected): {e}")
            self.finished.emit(False, f"Unexpected error: {e}")
            return
        self._log(f"{label} finished.")
        self.finished.emit(True, f"{label} finished - see the console log above.")

    def _run(self):
        raise NotImplementedError

    # ── steps both demos share ──────────────────────────────────────────────
    def _step_source(self):
        folder = DemoSource.find()
        if folder is None:
            raise _RunnerError(
                "No demo pack found - put the 'demo_data' folder into the "
                f"libraries folder ({settings.get_libraries_dir()}).")
        self.source = DemoSource(folder)
        s = self.source
        self._log(f"Demo pack: {folder} - deployment '{s.deployment_id}', "
                  f"{len(s.treatments)} treatment(s) "
                  f"({', '.join(t[di.TREATMENT_COL] for t in s.treatments)}), "
                  f"{s.n_recordings} recording(s); annotations: "
                  f"{s.annotations_csv.name if s.annotations_csv else 'none'}.")
        if s.extra_deployments:
            self._log("Only the first deployment is used - also found: "
                      + ", ".join(s.extra_deployments))

    def _step_library(self):
        lib_root = settings.get_libraries_dir() / DEMO_LIBRARY_NAME
        was_new = not lib_root.exists()
        lib_root.mkdir(parents=True, exist_ok=True)
        # Home's own library logic - rescans, selects it, and switches the
        # session library to it, same as picking it there by hand
        self.window.home_page._refresh_library_combo(select=str(lib_root))
        self.lib_root = lib_root
        self._log(f"Library: '{DEMO_LIBRARY_NAME}' "
                  f"{'created' if was_new else 'reused'} at {lib_root} - "
                  "session switched to it.")

    def _step_deployment(self, editor):
        """The deployment editor, as a person would use it: pick the demo
        deployment if it's already there (else New deployment…), fill in
        its details, sensor and treatments, then Create (a new one) or
        Update (an existing one that changed)."""
        from .deployment_editor import NEW_DEPLOYMENT
        s = self.source
        editor.refresh()
        exists = editor.cmb_deployment.findData(s.deployment_id) >= 0
        editor.select_deployment(s.deployment_id if exists else NEW_DEPLOYMENT)
        for column, edit in editor.dep_edits.items():
            if column in s.deployment:
                edit.setText(s.deployment[column])
        editor.set_sensor(s.sensor)
        for t in s.treatments:
            editor.upsert_treatment(dict(t))
        folder_missing = not editor.deployment_dir().exists()
        if editor.has_unsaved() or folder_missing:
            with self._headless_dialogs():
                ok = editor.apply(open_folder=False)
            if not ok:
                raise _RunnerError("Deployment: could not be saved.")
            self._log(f"Deployment: '{s.deployment_id}' "
                      f"{'updated' if exists else 'created'} - one folder per "
                      "treatment, Run 1..N inside each.")
        else:
            self._log(f"Deployment: '{s.deployment_id}' already set up - "
                      "nothing to change.")

    def _step_copy_in(self):
        """Stands in for the user dragging their field files into each run
        folder: copies (never moves) every file from the demo pack into
        the matching run folder; files already there are skipped."""
        s = self.source
        n_copied = n_present = 0
        for name, src_dir in s.treatment_dirs.items():
            for f in sorted(src_dir.rglob("*")):
                if not f.is_file() or f.name == raw_layout.README_NAME:
                    continue
                rel = f.relative_to(src_dir)
                run = raw_layout.run_label(rel.parts[0]) if len(rel.parts) > 1 else None
                if run is not None:
                    rel = Path(*rel.parts[1:])
                target = raw_layout.run_dir(self.lib_root, s.deployment_id,
                                            name, run or 1) / rel
                if target.exists():
                    n_present += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(target))
                n_copied += 1
            self._check_stop()
        self._log(f"Raw files: copied {n_copied} file(s) into the run folders"
                  + (f" ({n_present} already there)" if n_present else "")
                  + ".")

    def _step_process(self, inventory):
        inventory.refresh(block=True)
        files = [f for f in inventory.files if f["complete"]]
        if not files:
            raise _RunnerError("Process: no complete recordings found.")
        inventory.select_all()
        box = self._wait_for(inventory.processing_done, _LONG_TIMEOUT_MS,
                             f"processing {len(files)} recording(s)",
                             inventory.process_selected)
        code, stems = box
        self._log(f"Process: {len(stems)}/{len(files)} processed"
                  f"{'' if code == 0 else ' (with errors)'} and labelled "
                  "from their folders.")
        if not stems:
            raise _RunnerError("Process: nothing was processed.")

    def _reset_validation_state(self):
        """The demo library is reused between runs, and Auto process all
        leaves already-validated sensors alone - so a second run would
        inherit the first run's flags and reviews. Clearing them here
        (the demo's own library only) makes every run validate, flag and
        review from scratch."""
        from . import validation_core as vc
        index_df = di.read_index(self.lib_root)
        if index_df is None:
            return
        cols = [c for c in (vc.VALIDATED_COL, vc.USER_VALIDATED_COL,
                            vc.FLAGGED_COL, vc.USER_ADJUSTED_COL,
                            vc.HIG_WINDOW_MAX_COL) if c in index_df.columns]
        if not cols:
            return
        index_df = index_df.drop(columns=cols)
        vc.write_index(self.lib_root, index_df)
        self._log("Validate: the demo library's previous validation state "
                  "cleared, so this run starts from scratch.")


# ═════════════════════════════════════════════════════════════════════════════
class SimpleDemoRunner(_RunnerBase):
    """Simple mode's wizard, end to end - no training."""

    def _label(self):
        return "Simple demo"

    def _page(self, dlg, index):
        dlg.stack.setCurrentIndex(index)
        dlg._sync_step_highlight()
        QApplication.processEvents()

    def _run(self):
        w = self.window
        dlg = w.simple_mode_dialog
        self._step_source()
        self._check_stop()
        if not dlg.isVisible():
            dlg.show()
        dlg.raise_()
        self._step_library()
        self._check_stop()

        self._page(dlg, 1)
        self._step_deployment(dlg.editor)
        self._check_stop()
        self._step_copy_in()

        self._page(dlg, 2)
        dlg._refresh_process_inventory()
        self._step_process(dlg.inventory)
        self._check_stop()

        self._page(dlg, 3)
        self._reset_validation_state()
        dlg._refresh_validate_step()
        thread = dlg._auto_process_all()
        if thread is None:
            raise _RunnerError("Validate: no processed sensors to validate.")
        self._wait_thread(thread, "Auto process all")
        QApplication.processEvents()
        self._log(f"Validate: {dlg.lbl_all_validated.text()}")
        self._step_review_flagged(dlg)
        self._check_stop()

        df, path, msg = self._wait_for(dlg._exporter.finished, _LONG_TIMEOUT_MS,
                                       "Save and export", dlg._save_and_export)
        if df is None:
            raise _RunnerError(f"Save and export: {msg}")
        self._log(f"Save and export: {msg}")
        self._check_stop()

        self._page(dlg, 4)
        state = w.ml_prediction_page.state
        dlg._refresh_predict_step()
        if state.bin_model_path is None:
            raise _RunnerError("Predict: no deployed model found (models "
                               "folder / Settings' default model).")
        model = state.bin_model_path.name + (
            f" + {state.mc_model_path.name}" if state.mc_model_path else "")
        self._log(f"Predict: model {model} (Simple mode's own default).")
        self._race(state.run_finished, state.run_failed, _LONG_TIMEOUT_MS,
                   "prediction run", dlg._run_predict)
        n_rows = len(state.summary) if state.summary is not None else 0
        self._log(f"Predict: complete - {n_rows} treatment row(s).")
        self._check_stop()

        self._page(dlg, 5)
        dlg._refresh_report_step()
        self._page(dlg, 6)
        out_dir = w.session_state.output_dir(create=True)
        expected = out_dir / f"BladeStrike_Analysis_{state.run_id}" / "report.html"
        with self._headless_dialogs(existing_directory=str(out_dir)):
            dlg._download_report()
        if not expected.exists():
            raise _RunnerError(f"Report: expected output not found at {expected}.")
        self._log(f"Report: downloaded to {expected.parent}.")

    # ── Validate: review the flagged sensors, checking each step ─────────────
    def _check(self, ok, what):
        self._log(f"Validate check {'PASS' if ok else 'FAIL'}: {what}")
        return ok

    def _step_review_flagged(self, dlg):
        """What a person does after Auto process all, done with the keys
        they'd use - and checked at every step: the flagged sensors are
        the top of the list (orange), the arrow keys load the sensor they
        move to, and Save + Next (Ctrl+V) clears each flag (the sensor
        turns green and leaves the flagged group) and moves on to the next
        flagged sensor, until none are left."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor
        from PySide6.QtTest import QTest
        from . import validation_core as vc
        from .theme import OK, WARN

        lst = dlg.validate_list

        def order():
            return [lst.item(i).text() for i in range(lst.count())]

        def colour_of(stem):
            items = lst.findItems(stem, Qt.MatchFlag.MatchExactly)
            return items[0].foreground().color() if items else None

        status = dlg._validation_status()
        pending = [s for s in order() if vc.needs_review(s, status)]
        n = len(pending)
        if not n:
            self._log("Validate: Auto process all flagged no sensors in this "
                      "demo data - nothing to review.")
            return
        self._log(f"Validate: reviewing the {n} flagged sensor(s) as a "
                  "person would - arrow keys, then Save + Next (Ctrl+V) on "
                  "each without moving its nadir.")
        fails = 0
        top = order()[:n]
        fails += not self._check(
            top == pending and all(colour_of(s) == QColor(WARN) for s in top),
            f"the {n} flagged sensors are the top {n} of the list, in orange")

        # arrow keys: the highlighted sensor is the one loaded
        lst.setFocus()
        lst.setCurrentRow(0)
        QTest.keyClick(lst, Qt.Key.Key_Down)
        QApplication.processEvents()
        down_ok = dlg._cur_validate_stem == order()[1]
        QTest.keyClick(lst, Qt.Key.Key_Up)
        QApplication.processEvents()
        fails += not self._check(
            down_ok and dlg._cur_validate_stem == order()[0],
            "Down/Up arrow keys load the sensor they move to")

        # Save + Next (Ctrl+V) through every flagged sensor
        moved_ok = cleared_ok = 0
        for i in range(n):
            self._check_stop()
            stem = dlg._cur_validate_stem
            QTest.keyClick(lst, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
            QApplication.processEvents()
            status = dlg._validation_status()
            if (not vc.needs_review(stem, status) and stem in status[1]
                    and colour_of(stem) == QColor(OK)
                    and stem not in order()[:n - i - 1]):
                cleared_ok += 1
            expected = pending[i + 1] if i + 1 < n else None
            if expected is None or dlg._cur_validate_stem == expected:
                moved_ok += 1
        fails += not self._check(
            cleared_ok == n,
            f"Save + Next (Ctrl+V) cleared {cleared_ok}/{n} flags - each "
            "sensor turned green and left the flagged group")
        fails += not self._check(
            moved_ok == n,
            f"Save + Next moved on to the next flagged sensor {moved_ok}/{n} "
            "times")
        status = dlg._validation_status()
        stems = [f["stem"] for f in dlg._validate_files]
        left = len(vc.outstanding_flagged(stems, status))
        counter = dlg.lbl_validated_count.text().splitlines()[0]
        fails += not self._check(
            left == 0 and counter == f"Flagged for review: 0/{len(stems)} sensors",
            f"no flags left to review (counter reads '{counter}')")
        fails += not self._check(
            vc.all_validated(stems, status),
            "every sensor validated (auto or reviewed)")
        self._log("Validate: review checks "
                  + ("all passed." if not fails else f"- {fails} FAILED."))


# ═════════════════════════════════════════════════════════════════════════════
class AdvancedDemoRunner(_RunnerBase):
    """The full app's pages, end to end - including training a new model."""

    def _label(self):
        return "Advanced demo"

    def _go(self, btn_name):
        self.window.navigate_to(btn_name)
        QApplication.processEvents()

    def _run(self):
        w = self.window
        self._step_source()
        self._check_stop()
        dlg = w.simple_mode_dialog
        if dlg.isVisible():
            # the full app's own door from Simple mode
            dlg._go_development_toolkit()
        elif not w.isVisible():
            w.show()
        w.home_page._go_advanced()
        self._step_library()
        self._check_stop()

        self._step_calculator()
        self._check_stop()
        self._step_study_design()

        self._go("btn_initiate_deployment")
        self._step_deployment(w.deployment_page.editor)
        self._check_stop()
        self._step_copy_in()

        self._go("btn_process")
        page = w.process_page
        page.lib_selector.rescan(wait=True)
        # every deployment/treatment/run - the filters' "All" entries
        for cmb in (page.lib_selector.cmb_deployment,
                    page.lib_selector.cmb_treatment, page.lib_selector.cmb_run):
            cmb.setCurrentIndex(0)
        self._step_process(page.inventory)
        self._check_stop()

        df, csv_path = self._step_annotate()
        self._check_stop()
        self._step_train(csv_path)
        self._check_stop()
        self._step_deploy()
        self._check_stop()
        self._step_predict(df)
        self._check_stop()
        self._step_compare()
        self._step_report()

    # ── BSM Calculator → Study design ────────────────────────────────────────
    def _step_calculator(self):
        self._go("btn_bsm_calculator")
        page = self.window.bsm_calculator_page
        name = self.source.bsm_config
        idx = page.cmb_config.findText(name)
        if idx < 0:
            raise _RunnerError(f"Calculator: BSM config '{name}' not found in "
                               "input_data/BSM_config/.")
        page.cmb_config.setCurrentIndex(idx)
        page._load_selected_config()
        with self._headless_dialogs():
            page.calculate()
        self._log(f"Calculator: '{name}' loaded and calculated (scaly + eel).")

    def _step_study_design(self):
        """The blade strike estimate sets the expected strike rate; the
        sample-size helper then says how many sensors a ±10 pp estimate
        needs, and the planned N is what this demo actually deploys."""
        self._go("btn_study_design")
        precision = getattr(self.window.setup_page, "tab_precision", None)
        if precision is None:
            self._log("Study design: page not available - skipped.")
            return
        precision._load_from_bsm()
        precision.spin_target.setValue(_STUDY_TARGET_PRECISION_PP)
        needed = getattr(precision, "_required_n", None)
        precision.spin_n.setValue(self.source.n_recordings)
        self._log(f"Study design: expected strike rate "
                  f"{precision.spin_rate.value():.1f}% (from the Calculator); "
                  f"±{_STUDY_TARGET_PRECISION_PP:.0f} pp needs N = {needed}; "
                  f"planned N = {self.source.n_recordings} → "
                  f"{' '.join(precision.result_text().split())}")

    # ── Annotate: validate, annotate, export ─────────────────────────────────
    def _step_annotate(self):
        self._go("btn_annotate")
        page = self.window.annotation_page
        sel = page.lib_selector
        sel.rescan(wait=True)
        for cmb in (sel.cmb_deployment, sel.cmb_treatment, sel.cmb_run):
            cmb.setCurrentIndex(0)
        self._reset_validation_state()
        page._load_index()
        page._populate_sensor_table()

        thread = page._auto_process_all()
        if thread is None:
            raise _RunnerError("Annotate: no processed sensors listed.")
        self._wait_thread(thread, "Auto process all")
        self._log(f"Annotate: {page.lbl_validate_status.text()}")

        if self.source.annotations_csv is not None:
            with self._headless_dialogs():
                n = page._import_annotations(str(self.source.annotations_csv))
            self._log(f"Annotate: {page.lbl_validate_status.text()}"
                      if n else "Annotate: annotation import failed.")
        else:
            self._log("Annotate: no annotations CSV in the demo pack - "
                      "training needs one, so it will likely fail.")

        with self._headless_dialogs():
            df, path, msg = self._wait_for(
                page._exporter.finished, _LONG_TIMEOUT_MS, "Save and export",
                page._save_and_export)
        if df is None:
            raise _RunnerError(f"Save and export: {msg}")
        self._log(f"Save and export: {msg} - passed to Model prediction.")
        return df, path

    # ── Model training ───────────────────────────────────────────────────────
    def _step_train(self, csv_path):
        self._go("btn_ml_training")
        state = self.window.ml_training_page.state
        ok, msg = state.load_dataset_csv(csv_path)
        if not ok:
            raise _RunnerError(f"Model training: {msg}")
        self._log(f"Model training: {msg} (default settings).")
        self._ensure_train_ready(state)
        self._race(state.cv_finished, state.cv_failed, _LONG_TIMEOUT_MS,
                   "cross-validation training", state.run_cv)
        self._log("Model training: cross-validation complete.")
        self._race(state.final_finished, state.final_failed, _LONG_TIMEOUT_MS,
                   "final model training", state.run_final)
        self._log("Model training: final model trained.")

    def _ensure_train_ready(self, state):
        """A single-treatment demo dataset can genuinely fail the region
        (multiclass) stage's default n-fold check - too few recordings in
        some region - while the binary stage is fine. If that's the *only*
        thing blocking, drop the region stage for this run (what "Region
        model" off already does); anything else is reported in full."""
        if state.ready:
            return
        fails = [label for s, label, _ in state.checks if s == "fail"]
        if fails and state.train_multiclass and all(
                label.startswith("Region") for label in fails):
            self._log("Model training: the region stage can't meet default "
                      f"{state.n_folds}-fold CV on this dataset "
                      f"({'; '.join(fails)}) - binary stage only.")
            state.train_multiclass = False
            state.validate()
        if not state.ready:
            detail = [f"{label}: {d}" for s, label, d in state.checks if s == "fail"]
            raise _RunnerError("Model training: not ready - " + "; ".join(detail))

    def _step_deploy(self):
        self._go("btn_deploy_train")
        state = self.window.ml_training_page.state
        out = self.window.session_state.output_dir()
        models_dir = (out / "models") if out is not None else settings.get_models_dir()
        version = state.suggest_version(models_dir)
        _pkg, deployed = state.deploy(models_dir, version)
        self._log(f"Deploy: v{version} to {models_dir} "
                  f"({len(deployed)} model file(s)).")

    # ── Model prediction ─────────────────────────────────────────────────────
    def _step_predict(self, df):
        """The dataset just exported, predicted with the models folder's
        default models (the ones shipped with the app) - the model the demo
        just trained is only a demonstration of training."""
        self._go("btn_ml_prediction")
        page = self.window.ml_prediction_page
        state = page.state
        state.use_default_models()
        if state.bin_model_path is None:
            raise _RunnerError("Predict: no models in the models folder "
                               f"({settings.get_models_dir()}).")
        if state.dataset_df is None:
            page.on_dataset_ready(df, "Demo - Annotate export")
        model = state.bin_model_path.name + (
            f" + {state.mc_model_path.name}" if state.mc_model_path else "")
        self._log(f"Predict: the default models ({model}) + the dataset "
                  "just exported.")
        self._race(state.run_finished, state.run_failed, _LONG_TIMEOUT_MS,
                   "prediction run", state.run_prediction)
        n_rows = len(state.summary) if state.summary is not None else 0
        self._log(f"Predict: complete - {n_rows} treatment row(s).")

    def _step_compare(self):
        self._go("btn_biological")
        self.window.model_comparison_page._refresh_comparison()
        self._log("Model comparison: refreshed against the BSM estimate.")

    def _step_report(self):
        sections = report_center.all_sections(self.window)
        checked = {s.key for s in sections if s.available}
        if not checked:
            raise _RunnerError("Report: no sections available.")
        out_dir = report_center.default_output_dir(self.window)
        doc_path, warnings = report_center.assemble(sections, out_dir, checked)
        for warn in warnings:
            self._log(f"Report: warning - {warn}")
        self._log(f"Report: {len(checked)} section(s) written to {doc_path}")


RUNNERS = {"simple": SimpleDemoRunner, "advanced": AdvancedDemoRunner}


def available_demos():
    """The demos this edition offers - the Simple edition only has Simple
    mode, so only its demo."""
    return ["simple"] if simple_only() else list(RUNNERS)


def run_headless(window, mode):
    """Run one demo to the end, for `StrikeWorks --demo <mode>` and the
    tests. Returns (passed, message)."""
    if mode not in available_demos():
        return False, f"the {mode} demo isn't available in this edition"
    result = {}
    runner = RUNNERS[mode](window)
    runner.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
    runner.run()
    return bool(result.get("ok")), result.get("msg", "")
