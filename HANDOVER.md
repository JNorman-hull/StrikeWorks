# Handing over StrikeWorks

## What there is

| Item | Where | Notes |
|---|---|---|
| Source, tests, docs, default models, BSM presets, example datasets | GitHub `JNorman-hull/StrikeWorks`, branch `main` | `README.md` (how it works, how to build), `ROADMAP.md` (open work, hidden pages), `REFACTOR_PLAN.md` (the September 2026 clean-up) |
| The packaged app | `dist/StrikeWorks_<date>.zip` (made by `build.py --zip`) | Self-contained: unzip anywhere and run `StrikeWorks.exe` |
| Demo pack source | `libraries/Testbed` (42 MB, not in git) | The raw recordings and annotations the demos start from; the build copies it to `libraries/demo_data` |
| RAPID sensor recordings | OneDrive: `FSE Hull International Fisheries Institute - Documents\REDEEM 2.0\HS_JOSH_NORMAN\RAPID_libraries` | The real libraries; not in git or the build |
| LosslessCut (video review) | https://github.com/mifi/lossless-cut | Not in git or the build (900 MB); see README, "Development" |

## Checking the packaged app (about 10 minutes)

Everything below stays inside the unzipped folder: it starts on its own
`libraries`, `models`, `input_data` and `output_data`, and keeps its
settings in `settings.json` beside the exe.

1. Unzip, run `StrikeWorks.exe`. Simple mode opens.
2. **Settings** (top right) > Dev mode > **Show console**.
3. Pick **Simple mode (no training)**, **Run demo**. It builds a
   `StrikeWorks_demo` library from `libraries/demo_data`, processes and
   validates the recordings, exports a dataset to `input_data`, predicts it
   with the default models and writes
   `libraries/StrikeWorks_demo/StrikeWorks_user_output/BladeStrike_Analysis_<run>/report.html`.
4. Pick **Advanced (full workflow, trains a model)**, **Run demo**. It
   trains and deploys a model (into the demo library's
   `StrikeWorks_user_output/models`), predicts the dataset with the default
   models and writes a full report to `.../StrikeWorks_user_output/Report_<time>/`.
5. Predicting an existing dataset: close Simple mode with **Development
   toolkit**, then Model prediction > Predict > load
   `input_data/Pumpflow_2024_datatset1_only.csv` > Run.

The same check runs unattended from the repo: `powershell -File
tools\smoke_test.ps1 -Demos` (on a temporary copy of `dist\StrikeWorks`).

## Shelving checklist

1. **Push `main` and tag it.**
   ```
   git push origin main
   git tag -a v1.0 -m "Handover build"
   git push origin v1.0
   git branch -d cleanup-2026-09
   ```
2. **Keep the demo pack with the code** - either commit it (a clone can
   then rebuild the zip and run the demo tests):
   ```
   (add  !/libraries/Testbed/  to .gitignore, under /libraries/*)
   git add .gitignore libraries/Testbed
   git commit -m "Demo pack"
   ```
   or hand `libraries/Testbed` over alongside the zip.
3. **Publish the zip**: attach `dist/StrikeWorks_<date>.zip` to the `v1.0`
   GitHub release, or put it on the shared OneDrive.
4. **Give access**: add your colleague to the GitHub repository and share
   the RAPID_libraries OneDrive folder.
5. **Tidy your own machine** (none of this is part of the handover; delete
   or archive as you like):
   - `dist/_kept_from_previous_build_*` - data made with earlier builds (a
     copy of the Eel sensor November 2026 library, a 2.3 GB demo library,
     old reports and training runs);
   - `input_data/DevTest_PF_*.csv`, `training_runs/`, `output_data/`,
     `bsm_results/` - outputs of demo and test runs (git ignores them);
   - `build/` - PyInstaller's working folder;
   - your settings (`%APPDATA%\StrikeWorks\settings.json` and the older
     `~\.hifistrike_settings.json`, `~\.strikeworks_sensors.json`,
     `~\.strikeworks_annotations.json`) hold your own folder paths.
6. **Point your colleague at the open work**: `ROADMAP.md`, and the
   bundle-size items at the end of `REFACTOR_PLAN.md`.

## For your colleague: working from source

```
git clone https://github.com/JNorman-hull/StrikeWorks
cd StrikeWorks
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe main.py
```

- Tests: `.venv\Scripts\python.exe -m unittest discover -s tests`
  (`set STRIKEWORKS_E2E=1` first to include both demos; needs
  `libraries/Testbed`).
- PyCharm: interpreter `.venv`, run configuration `main.py` with
  `build_ui.py` as a before-launch step (it regenerates `modules/ui_main.py`
  from `main.ui`).
- New release: `build.py`, then `tools\smoke_test.ps1 -Demos`, then
  `build.py --zip-only`.
