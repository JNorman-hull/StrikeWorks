# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Simple-mode demo runner - a one-click, no-UI-clicking walkthrough of
the REAL Simple mode wizard (page_simple_mode.SimpleModeDialog), not a
hand-rolled reimplementation of what it does. It drives the app's one
real `window.simple_mode_dialog` instance's own widget-bound methods, in
the same order a person clicking through it would:

    new library > new deployment > copy files in > process >
    validate all (Auto process all) > save the dataset >
    predict from this dataset > Download StrikeWorks report

This is deliberately a separate, parallel implementation from the
Advanced demo (`dev_runner.DevRunner`) - see that module's docstring.
Sharing `SimpleModeDialog` itself with a manual session is what makes
this honest: if Simple mode's real behaviour changes, this changes with
it, rather than silently drifting out of sync with its own copy of the
logic. The two costs of driving the real dialog: (1) a couple of its
methods start a QThread themselves with no way to hook in beforehand, so
this grabs the thread attribute immediately after calling them rather
than passing the call itself as `_wait_for`'s trigger (the same-thread,
same-call-stack window between "thread started" and "we start waiting on
it" is far too short for the thread to have already finished and emitted
in it); (2) a couple of its methods pop a plain OK-only QMessageBox or a
QFileDialog folder picker - fine for a human, a hang for automation - so
`_headless_dialogs()` narrowly suppresses those for just the call that
needs it.
"""
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from .dev_runner import _LONG_TIMEOUT_MS, _RunnerBase, _RunnerError


class SimpleDevRunner(_RunnerBase):
    """Drives window.simple_mode_dialog end to end. Uses the same DevTest
    library as the Advanced demo (LIBRARY_NAME/SOURCE_* inherited from
    _RunnerBase) but its own deployment identity, so the two demos never
    collide inside it."""

    DEPLOYMENT = {
        "site": "PF TEST RIG",
        "deployment_id": "DevTest_PF_Simple",
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
    SENSOR_CONFIG_KEY = "rapid"

    def _label(self):
        return "Simple demo pipeline"

    def _run(self):
        w = self.window
        lib_root = self._step_library(w)
        self._check_stop()

        dlg = w.simple_mode_dialog
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.stack.setCurrentIndex(0)
        dlg._sync_step_highlight()

        idx = dlg.cmb_sensor.findData(self.SENSOR_CONFIG_KEY)
        if idx >= 0:
            dlg.cmb_sensor.setCurrentIndex(idx)
        self._log(f"Sensor config: '{self.SENSOR_CONFIG_KEY}' set active.")

        treatment_dir = self._step_deployment(dlg, lib_root)
        self._check_stop()
        self._step_process(dlg)
        self._check_stop()
        self._step_validate_all(dlg)
        self._check_stop()
        self._step_save_export(dlg)
        self._check_stop()
        self._step_predict(dlg)
        self._check_stop()
        self._step_download_report(dlg)

    # ── suppressing the dialog's own blocking popups ────────────────────────
    @staticmethod
    @contextmanager
    def _headless_dialogs(existing_directory=None):
        """Simple mode's own methods pop plain OK-only info/warning/
        critical dialogs on success/failure, and one blocking folder
        picker (Download StrikeWorks report) - all fine for a human
        clicking through, all a hang for an unattended demo. Narrowly
        scoped around just the call that can raise one and restored
        immediately after, so nothing else in the app is affected."""
        orig_info, orig_warn, orig_crit = (
            QMessageBox.information, QMessageBox.warning, QMessageBox.critical)
        orig_get_dir = QFileDialog.getExistingDirectory
        noop = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        QMessageBox.information = noop
        QMessageBox.warning = noop
        QMessageBox.critical = noop
        if existing_directory is not None:
            QFileDialog.getExistingDirectory = staticmethod(
                lambda *a, **k: existing_directory)
        try:
            yield
        finally:
            QMessageBox.information = orig_info
            QMessageBox.warning = orig_warn
            QMessageBox.critical = orig_crit
            QFileDialog.getExistingDirectory = orig_get_dir

    # ── 1: deployment (new deployment > copy files in) ──────────────────────
    def _step_deployment(self, dlg, lib_root):
        from .page_simple_mode import _NEW_DEPLOYMENT

        dlg._refresh_deployment_step()   # syncs dlg._lib_root, repopulates cmb_deployment
        idx = dlg.cmb_deployment.findData(_NEW_DEPLOYMENT)
        dlg.cmb_deployment.setCurrentIndex(max(0, idx))   # -> _show_deployment(_NEW_DEPLOYMENT)

        ident = self.DEPLOYMENT["deployment_id"]
        for column, edit in dlg.dep_edits.items():
            edit.setText(self.DEPLOYMENT.get(column, ""))
        dlg._clear_treatments()
        dlg._add_treatment(dict(self.TREATMENT))

        with self._headless_dialogs():
            dlg._create_and_open_folder()
        self._log(f"Deployment: '{ident}' folder created/reused and opened "
                   "in Explorer.")

        treatment_dir = (lib_root / "raw_sens_data" / ident
                         / self.TREATMENT["treatment"])
        self._copy_source_files(treatment_dir)
        return treatment_dir

    # ── 2: process ────────────────────────────────────────────────────────
    def _step_process(self, dlg):
        dlg._refresh_process_inventory()
        if not dlg._process_files:
            raise _RunnerError(
                "Process: no raw recordings found in the deployment folder.")
        dlg.tbl_inventory.selectAll()
        dlg._process_selected()
        thread = dlg._process_thread
        if thread is None:
            raise _RunnerError("Process: no complete recordings to process.")
        # dlg._on_process_log (connected inside _run_process) only updates
        # a QLabel - this is what actually gets each "-- Processing: ..."
        # line into the dev console, same as the Advanced demo does
        log_cb = lambda text: self._log(f"process: {text.strip()}")
        thread.log.connect(log_cb)
        try:
            self._wait_for(thread.done, _LONG_TIMEOUT_MS, "raw data processing",
                           lambda: None)
        finally:
            # thread.done isn't disconnected here (dlg._on_process_done,
            # connected inside _run_process, still needs it to stamp
            # treatments/refresh the inventory on a timeout/stop too) -
            # only drop the extra connection this method itself made, same
            # reasoning as dev_runner.py's own _step_process
            try:
                thread.log.disconnect(log_cb)
            except (RuntimeError, TypeError):
                pass
        self._log(f"Process: {dlg.lbl_process_status.text() or 'done'} "
                   f"({len(dlg._process_batch_done)} sensor(s)).")

    # ── 3: validate all (Auto process all) ──────────────────────────────────
    def _step_validate_all(self, dlg):
        dlg._refresh_validate_step()
        if not dlg._validate_files:
            raise _RunnerError("Validate: no processed sensors found.")
        dlg._auto_process_all()
        self._log(f"Validate: {dlg.lbl_all_validated.text()}")

    # ── 4: save the dataset ──────────────────────────────────────────────────
    def _step_save_export(self, dlg):
        dlg._save_and_export()
        thread = dlg._extract_thread
        if thread is None:
            raise _RunnerError("Save and export: did not start.")
        self._wait_for(thread.done, _LONG_TIMEOUT_MS, "dataset export",
                       lambda: None)
        if dlg._built_dataset_path is None:
            raise _RunnerError(
                f"Save and export: {dlg.lbl_all_validated.text() or 'failed'}")
        self._log(f"Save and export: {dlg.lbl_all_validated.text()}")

    # ── 5: predict from this dataset ─────────────────────────────────────────
    def _step_predict(self, dlg):
        state = self.window.ml_prediction_page.state
        dlg._refresh_predict_step()   # _auto_select_model + dataset card
        if state.dataset_df is None:
            raise _RunnerError("Predict: no dataset loaded.")
        model_desc = getattr(state.bin_model_path, "name", "none")
        if state.mc_model_path is not None:
            model_desc += f" + {state.mc_model_path.name}"
        self._log(f"Predict: model {model_desc} selected "
                   "(Simple mode's own auto-select rule).")
        self._race(state.run_finished, state.run_failed, _LONG_TIMEOUT_MS,
                   "prediction run", dlg._run_predict)
        n_rows = len(state.summary) if state.summary is not None else 0
        self._log(f"Predict: complete - {n_rows} treatment row(s) in summary.")

    # ── 6: download the report ───────────────────────────────────────────────
    def _step_download_report(self, dlg):
        w = self.window
        state = w.ml_prediction_page.state
        if state.summary is None or state.run_id is None:
            raise _RunnerError("Report: no completed prediction to report on.")
        session_state = getattr(w, "session_state", None)
        out_dir = (session_state.output_dir(create=True)
                   if session_state is not None and session_state.library
                   else Path.cwd())

        dlg.stack.setCurrentIndex(5)
        dlg._sync_step_highlight()
        dlg._refresh_report_step()
        dlg.stack.setCurrentIndex(6)
        dlg._sync_step_highlight()

        expected = out_dir / f"BladeStrike_Analysis_{state.run_id}" / "report.html"
        with self._headless_dialogs(existing_directory=str(out_dir)):
            dlg._download_report()
        if not expected.exists():
            raise _RunnerError(
                f"Report: expected output not found at {expected} - "
                "the download step may have failed.")
        self._log(f"Report: downloaded via 'Download StrikeWorks report' "
                   f"to {expected.parent}.")
