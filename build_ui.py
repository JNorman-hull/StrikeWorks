# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Compile main.ui -> modules/ui_main.py.

Run this after editing main.ui (in Qt Designer or by hand). PyCharm runs it
automatically before launching the app, so normally you never call it yourself.

It also normalises main.ui first, to undo two things Qt Designer does on save
that break the toolchain:

1. Fully-scoped enums (``QFrame::Shadow::Raised``). Designer writes these, then
   pops a modal warning for every one of them the next time the file is opened
   - 110 dialogs on a file this size. The short form is equivalent and silent.

2. Empty ``<fontweight></fontweight>`` elements. uic turns these into
   ``setWeight(QFont.)``, which is a syntax error that stops the app dead.

Usage:
    python build_ui.py            compile if main.ui is newer than the output
    python build_ui.py --force    always compile
    python build_ui.py --check    report status, change nothing
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
UI_FILE = ROOT / "main.ui"
OUT_FILE = ROOT / "modules" / "ui_main.py"
QRC_FILE = ROOT / "resources.qrc"
QRC_OUT = ROOT / "modules" / "resources_rc.py"

if sys.platform == "win32":
    UIC = ROOT / ".venv" / "Scripts" / "pyside6-uic.exe"
    RCC = ROOT / ".venv" / "Scripts" / "pyside6-rcc.exe"
else:
    UIC = ROOT / ".venv" / "bin" / "pyside6-uic"
    RCC = ROOT / ".venv" / "bin" / "pyside6-rcc"

_SCOPED_ENUM = re.compile(r"<enum>([A-Za-z]+)::[A-Za-z]+::([A-Za-z]+)</enum>")

# Scoped enums inside XML attributes, e.g. alignment="Qt::AlignmentFlag::AlignTop".
# These are worse than the <enum> ones: Designer cannot parse them back, so on the
# next save it drops the attribute entirely and the layout silently changes.
_SCOPED_ATTR = re.compile(r'(\b[a-z]+=")([A-Za-z]+)::[A-Za-z]+::([A-Za-z|:]+)(")')


def _unscope_attr(m: re.Match) -> str:
    prefix, cls, value, suffix = m.groups()
    # A value may be a |-separated flag list. Every flag keeps its own class
    # prefix - "Qt::AlignLeft|AlignVCenter" is not valid .ui syntax.
    parts = [part.split("::")[-1] for part in value.split("|")]
    return "%s%s%s" % (prefix, "|".join("%s::%s" % (cls, p) for p in parts), suffix)


def normalise(path: Path) -> dict:
    """Undo Designer's save-time damage. Returns a count of what was fixed."""
    text = path.read_text(encoding="utf-8")
    original = text

    text, n_enums = _SCOPED_ENUM.subn(r"<enum>\1::\2</enum>", text)
    text, n_attrs = _SCOPED_ATTR.subn(_unscope_attr, text)

    lines = text.split("\n")
    kept = [ln for ln in lines if ln.strip() != "<fontweight></fontweight>"]
    n_weights = len(lines) - len(kept)
    text = "\n".join(kept)

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")

    return {"enums": n_enums, "attrs": n_attrs, "fontweights": n_weights}


def resources_stale() -> bool:
    """True if resources.qrc, or any file it lists, is newer than the output.

    Images and icons are compiled into modules/resources_rc.py. Replacing a PNG
    on disk has no effect on the running app until this is rebuilt, because Qt
    loads them from the ':/...' resource system, not the filesystem.
    """
    if not QRC_FILE.exists():
        return False
    if not QRC_OUT.exists():
        return True

    out_mtime = QRC_OUT.stat().st_mtime
    if QRC_FILE.stat().st_mtime > out_mtime:
        return True

    try:
        import xml.etree.ElementTree as ET
        for node in ET.parse(QRC_FILE).iter("file"):
            asset = ROOT / (node.text or "").strip()
            if asset.exists() and asset.stat().st_mtime > out_mtime:
                return True
    except Exception:
        # If the .qrc cannot be parsed, rebuild rather than silently skip.
        return True
    return False


def compile_resources() -> int:
    if not RCC.exists():
        print(f"ERROR: {RCC} not found - is the virtualenv set up?")
        return 1
    result = subprocess.run(
        [str(RCC), str(QRC_FILE), "-o", str(QRC_OUT)],
        capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: pyside6-rcc failed")
        print(result.stderr.strip())
        return result.returncode
    print(f"Built {QRC_OUT.relative_to(ROOT)} from {QRC_FILE.name}")
    return 0


def compile_ui() -> int:
    if not UIC.exists():
        print(f"ERROR: {UIC} not found - is the virtualenv set up?")
        return 1

    result = subprocess.run(
        [str(UIC), str(UI_FILE), "-o", str(OUT_FILE)],
        capture_output=True, text=True)

    if result.returncode != 0:
        print("ERROR: pyside6-uic failed")
        print(result.stderr.strip())
        return result.returncode

    # Fail loudly rather than shipping a file that cannot be imported.
    try:
        compile(OUT_FILE.read_text(encoding="utf-8"), str(OUT_FILE), "exec")
    except SyntaxError as e:
        print(f"ERROR: generated file has a syntax error at line {e.lineno}: {e.msg}")
        print("       main.ui probably contains a property uic cannot translate.")
        return 1

    return 0


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    check_only = "--check" in args

    if not UI_FILE.exists():
        print(f"ERROR: {UI_FILE} not found")
        return 1

    stale = (not OUT_FILE.exists()
             or UI_FILE.stat().st_mtime > OUT_FILE.stat().st_mtime)

    if check_only:
        print("ui        : %s" % ("STALE" if stale else "up to date"))
        print("resources : %s" % ("STALE" if resources_stale() else "up to date"))
        return 0

    # Icons and images first - the UI references them.
    if force or resources_stale():
        rc = compile_resources()
        if rc != 0:
            return rc

    fixed = normalise(UI_FILE)
    if fixed["enums"]:
        print(f"  normalised {fixed['enums']} scoped enum(s) in main.ui")
    if fixed["attrs"]:
        print(f"  normalised {fixed['attrs']} scoped enum attribute(s) "
              f"(Designer would have dropped these)")
    if fixed["fontweights"]:
        print(f"  removed {fixed['fontweights']} empty <fontweight> element(s)")

    # normalise() may have just touched main.ui, so re-check staleness
    stale = stale or bool(fixed["enums"] or fixed["attrs"] or fixed["fontweights"])

    if not (stale or force):
        print("UI up to date.")
        return 0

    rc = compile_ui()
    if rc == 0:
        print(f"Built {OUT_FILE.relative_to(ROOT)} from {UI_FILE.name}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
