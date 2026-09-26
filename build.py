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
  3. What ships with the app is copied in, overwriting only files of the
     same name: the default models, the BSM presets, an example model
     dataset (input_data) and the demo pack (libraries/demo_data, from
     the repo's libraries/Testbed).

With --zip, the folder is also zipped for handing over - but only when it
holds nothing except what ships (checked before building); anything made
by using the built app is listed, never deleted. --zip-only zips the
current build without rebuilding (after tools/smoke_test.ps1, say).

Usage:
    python build.py
    python build.py --zip
    python build.py --zip-only
"""
import shutil
import subprocess
import sys
from datetime import date
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

# shipped with the app besides the models and BSM presets
DEMO_PACK = ROOT / "libraries" / "Testbed"
EXAMPLE_DATASETS = ("Pumpflow_2024_datatset1_only.csv",)


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
    """What ships with the app, copied over files of the same name only -
    anything made with the built app stays."""
    shutil.copytree(ROOT / "models", DIST / "models", dirs_exist_ok=True)
    shutil.copytree(ROOT / "input_data" / "BSM_config",
                    DIST / "input_data" / "BSM_config", dirs_exist_ok=True)
    for name in EXAMPLE_DATASETS:
        shutil.copy2(ROOT / "input_data" / name, DIST / "input_data" / name)
    if DEMO_PACK.is_dir():
        shutil.copytree(DEMO_PACK, DIST / "libraries" / "demo_data",
                        dirs_exist_ok=True)
    else:
        print(f"  no demo pack: {DEMO_PACK} not found")
    for name in ("libraries", "output_data"):
        (DIST / name).mkdir(parents=True, exist_ok=True)
        readme = ROOT / name / "readme.txt"
        if readme.exists() and not (DIST / name / "readme.txt").exists():
            shutil.copy2(readme, DIST / name / "readme.txt")


def _not_shipped():
    """Everything in dist/StrikeWorks the build doesn't put there - what
    using the built app made (libraries, outputs, deployed models,
    settings)."""
    if not DIST.exists():
        return []
    shipped = {
        None: {EXE, BUNDLE, "libraries", "models", "input_data", "output_data"},
        "libraries": {"readme.txt", "demo_data"},
        "output_data": {"readme.txt"},
        "input_data": {"BSM_config", *EXAMPLE_DATASETS},
        "models": {p.name for p in (ROOT / "models").iterdir()},
    }
    extras = []
    for folder, names in shipped.items():
        base = DIST if folder is None else DIST / folder
        if base.exists():
            extras += [p for p in base.iterdir() if p.name not in names]
    return extras


def _zip():
    name = DIST.parent / f"StrikeWorks_{date.today():%Y%m%d}"
    print(f"Zipping {DIST} ...")
    archive = shutil.make_archive(str(name), "zip", DIST.parent, DIST.name)
    print(f"Ready to hand over: {archive}")


def main():
    zip_only = "--zip-only" in sys.argv[1:]
    zip_it = zip_only or "--zip" in sys.argv[1:]
    if zip_it and _not_shipped():
        print("Not zipping - these were made by using the built app. Move "
              "them out of the folder (nothing is deleted), then run again:")
        for p in _not_shipped():
            print(f"  {p}")
        sys.exit(1)
    if zip_only:
        _zip()
        return
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "StrikeWorks.spec",
         "--noconfirm", "--distpath", str(STAGING)],
        cwd=ROOT, check=True)
    print(f"\nUpdating {DIST} (data folders are left as they are)...")
    _swap_in_program(STAGING / "StrikeWorks")
    _place_shipped_data()
    shutil.rmtree(STAGING / "StrikeWorks", ignore_errors=True)
    print(f"Build complete: {DIST}")
    if zip_it:
        _zip()


if __name__ == "__main__":
    main()
