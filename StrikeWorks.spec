# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for StrikeWorks. Build with:
    pyinstaller StrikeWorks.spec

One executable, two roles - see main.py's own dispatch at the top of the
file and modules/worker_launch.py: normally it launches the GUI;
invoked as "StrikeWorks.exe --worker predict ..." / "--worker train ..."
(which ml_state.py / ml_train_state.py build themselves via
worker_launch.worker_command() once sys.frozen is True) it runs the
matching worker's main() instead and exits - no GUI import happens on
that path at all.

--onedir, not --onefile: numba JIT-compiles and caches to disk on first
run; a --onefile bundle re-extracts itself to a fresh temp dir on every
launch, which would defeat that cache and slow down every single
prediction/training run (the worker subprocess is its own launch of this
same exe) rather than just app startup.
"""
from PyInstaller.utils.hooks import (
    collect_data_files, collect_submodules, copy_metadata,
)

datas = [
    # images/ is looked up __file__-relative by the modules that use it
    # (page_simple_mode.py, main.py's splash) - both live inside
    # PyInstaller's own _internal/ once frozen, so bundling it there via
    # `datas` (which only ever reaches _internal/, never next to the
    # .exe) matches exactly how those lookups resolve.
    ("images", "images"),
    ("icon.ico", "."),
    # models/ and input_data/BSM_config/ are NOT listed here - both are
    # looked up via settings.app_root(), which resolves to
    # Path(sys.executable).parent when frozen (next to StrikeWorks.exe,
    # not _internal/, since that's where a real user would expect to
    # find/replace them). `datas` can't place anything there, so
    # build.py copies them into dist/StrikeWorks/ itself as a step after
    # this spec runs - see that script for exactly what goes where.
]
datas += collect_data_files("sktime")
# sktime's soft-dependency checks (skbase._check_estimator_deps) look up
# installed package versions via importlib.metadata, which needs each
# package's .dist-info folder - PyInstaller doesn't bundle that by
# default, so those lookups silently fail and skbase concludes the dep
# "isn't present", filtering every mtype check out of sktime's registry
# (observed directly: this is what turned into "no check defined for
# mtype pd.Series, scitype Series" even after the registry's own
# pkgutil-walk directory was fixed via module_collection_mode below).
for _pkg in ("sktime", "scikit-base", "scikit-learn", "numpy", "pandas",
            "scipy", "joblib", "numba", "llvmlite"):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

hiddenimports = (
    collect_submodules("sklearn")
    + collect_submodules("sktime")
    + collect_submodules("numba")
    + ["numba.core.typing.cffi_utils"]
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    # sktime's mtype/estimator registries are populated by
    # pkgutil.walk_packages() over sktime.datatypes.__path__ *at runtime*
    # (sktime/utils/retrieval.py) - that needs a real, walkable directory
    # on disk, not module code sealed inside PyInstaller's zipped PYZ
    # archive. "py" collection mode extracts these two packages as loose
    # source files in the build output instead, so the walk finds them.
    # (confirmed by reproducing the failure: a frozen prediction run
    # raised "no check defined for mtype pd.Series, scitype Series" -
    # exactly a registry that came back empty.)
    module_collection_mode={
        "sktime": "py",
        "skbase": "py",
    },
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StrikeWorks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StrikeWorks",
)
