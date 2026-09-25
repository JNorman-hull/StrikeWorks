#!/usr/bin/env python
# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Builds the packaged app into dist/StrikeWorks without touching its data.

PyInstaller empties its output folder before every build, and the packaged
app keeps its data folders (libraries, input_data, output_data, models)
next to StrikeWorks.exe - so building straight into dist/StrikeWorks
deletes whatever was made with the built app. Instead:

  1. PyInstaller builds into build/staging/StrikeWorks.
  2. Only the program - StrikeWorks.exe and _internal/ - is swapped into
     dist/StrikeWorks. Nothing else there is deleted.
  3. The shipped models and BSM presets are copied in (overwriting only
     files of the same name), and any missing data folder is created.

Usage:
    python build.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist" / "StrikeWorks"
STAGING = ROOT / "build" / "staging"
EXE = "StrikeWorks.exe"
BUNDLE = "_internal"

# folders builds before the app_root() fix wrote at run time inside
# _internal - moved next to the exe (where the app now looks) rather than
# deleted with the old bundle
RUNTIME_FOLDERS = ("training_runs", "bsm_results")


def _merge_move(src, dst):
    """Move `src` to `dst`, keeping anything already at `dst`."""
    if not dst.exists():
        shutil.move(str(src), str(dst))
        return
    for child in src.iterdir():
        _merge_move(child, dst / child.name)
    src.rmdir()


def _swap_in_program(built):
    """Replace the exe and the bundle. Fails before deleting anything if
    the app is running (its files are locked)."""
    DIST.mkdir(parents=True, exist_ok=True)
    old_bundle = DIST / BUNDLE
    if old_bundle.exists():
        for name in RUNTIME_FOLDERS:
            if (old_bundle / name).exists():
                _merge_move(old_bundle / name, DIST / name)
                print(f"  kept {name}/ (moved out of {BUNDLE}/)")
        retired = DIST / (BUNDLE + ".old")
        if retired.exists():
            shutil.rmtree(retired)
        try:
            old_bundle.rename(retired)
        except OSError as e:
            sys.exit(f"Can't replace {old_bundle} - is StrikeWorks running? ({e})")
    else:
        retired = None
    try:
        (built / EXE).replace(DIST / EXE)
    except OSError as e:
        if retired is not None:
            retired.rename(old_bundle)
        sys.exit(f"Can't replace {DIST / EXE} - is StrikeWorks running? ({e})")
    shutil.move(str(built / BUNDLE), str(DIST / BUNDLE))
    if retired is not None:
        shutil.rmtree(retired)


def _place_shipped_data():
    """Shipped models and BSM presets, copied over files of the same name
    only - models deployed with the built app stay."""
    shutil.copytree(ROOT / "models", DIST / "models", dirs_exist_ok=True)
    shutil.copytree(ROOT / "input_data" / "BSM_config",
                    DIST / "input_data" / "BSM_config", dirs_exist_ok=True)
    for name in ("libraries", "output_data"):
        (DIST / name).mkdir(parents=True, exist_ok=True)
        readme = ROOT / name / "readme.txt"
        if readme.exists() and not (DIST / name / "readme.txt").exists():
            shutil.copy2(readme, DIST / name / "readme.txt")


def main():
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "StrikeWorks.spec",
         "--noconfirm", "--distpath", str(STAGING)],
        cwd=ROOT, check=True)
    print(f"\nUpdating {DIST} (data folders are left as they are)...")
    _swap_in_program(STAGING / "StrikeWorks")
    _place_shipped_data()
    shutil.rmtree(STAGING / "StrikeWorks", ignore_errors=True)
    print(f"Build complete: {DIST}")


if __name__ == "__main__":
    main()
