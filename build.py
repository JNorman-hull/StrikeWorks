#!/usr/bin/env python
# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Builds the packaged StrikeWorks executable end to end:

  1. Runs PyInstaller against StrikeWorks.spec.
  2. Copies the resources that need to live *next to* StrikeWorks.exe -
     not PyInstaller's own _internal/ folder, which is where `datas`
     entries in the spec land and which nothing in the app actually
     looks in for these: models/ (the shipped binary1/multiclass1 pair)
     and input_data/BSM_config/ (the bundled BSM presets). Both are
     looked up via settings.app_root() (modules/settings.py), which
     resolves to Path(sys.executable).parent once frozen - i.e. right
     alongside the .exe, where a real user would expect to find (and
     could replace) them.
  3. Creates libraries/ and output_data/ next to the .exe too, empty
     apart from the same short readme.txt already sitting in the source
     tree's own placeholder folders. (input_data/ itself already exists
     once step 2 copies BSM_config/ into it.) main.py's own
     _ensure_default_folders() does this same creation on every launch
     regardless, so this step only matters for never-yet-run installs.

Usage:
    python build.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist" / "StrikeWorks"


def main():
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "StrikeWorks.spec", "--noconfirm"],
        cwd=ROOT, check=True)

    print("\nPlacing default data folders next to StrikeWorks.exe...")

    models_dst = DIST / "models"
    if models_dst.exists():
        shutil.rmtree(models_dst)
    shutil.copytree(ROOT / "models", models_dst)

    bsm_dst = DIST / "input_data" / "BSM_config"
    bsm_dst.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "input_data" / "BSM_config").glob("*"):
        if f.is_file():
            shutil.copy2(f, bsm_dst / f.name)

    for name in ("libraries", "output_data"):
        dst = DIST / name
        dst.mkdir(parents=True, exist_ok=True)
        for f in (ROOT / name).glob("*"):
            if f.is_file():
                shutil.copy2(f, dst / f.name)

    print(f"Build complete: {DIST}")


if __name__ == "__main__":
    main()
