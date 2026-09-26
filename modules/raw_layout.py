# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The `raw_sens_data` folder layout - one definition of where a raw
recording sits and what its position means.

    raw_sens_data/<deployment>/<treatment>/Run <n>/<recording files>
                                                   VIDEO/<stem>_vid_*.mp4

Every treatment has at least one run, so Run 1 always exists once a
deployment is created (the deployment editor builds `Run 1..N` for a
treatment planned with N runs). A recording's deployment, treatment and run
are read straight off its path, which is what lets processing label a batch
spanning several treatments/runs correctly without a picker per batch.

Older libraries put files directly in the treatment folder (no run level),
and video in `<treatment>/VIDEO/` - those still read correctly: no run
folder means Run 1, and the video lookup walks up from the recording's own
folder to its deployment, so a treatment-level VIDEO folder is still found.
A level missing entirely (files directly under a deployment, or directly
under raw_sens_data) buckets as UNGROUPED rather than being dropped.

Pure pathlib - no Qt - so the index helpers can use it as freely as the
pages do.
"""
import os
import re
from pathlib import Path

RAW_DIR = Path("raw_sens_data")
PROCESSED_DIR = Path("processed_sens_data")
CSV_DIR = PROCESSED_DIR / "csv"
WINDOW_DIR = PROCESSED_DIR / "nadir_window"
INDEX_REL = PROCESSED_DIR / "index" / "global_sensor_index.csv"
DATASET_REL = PROCESSED_DIR / "model_features.csv"

#: processed sensor CSVs keep 10 significant figures: the time step and
#: every channel's resolution survive exactly, and the files are half the
#: size of pandas' full precision (and quicker to read back)
CSV_FLOAT_FORMAT = "%.10g"
# processed CSVs that aren't sensors: side files older versions wrote
_NOT_SENSOR_SUFFIXES = ("_min", "_delineated")
VIDEO_FOLDER_NAME = "VIDEO"
UNGROUPED = "(ungrouped)"
README_NAME = "readme.txt"
DEFAULT_RUN = "1"

README_TEXT = (
    "This is where raw files are stored.\n\n"
    "Each treatment has one folder per run (Run 1, Run 2, ...). Drag and "
    "drop the sensor files from each run straight into that run's folder. "
    "Video for a run goes into that run's own VIDEO subfolder.\n\n"
    "The deployment, treatment and run each file is labelled with when it "
    "is processed come from the folder it sits in."
)

_RUN_RE = re.compile(r"^\s*run[\s_-]*(\d+)\s*$", re.IGNORECASE)


def run_folder_name(run) -> str:
    """"Run 3" for run 3 (or "3")."""
    return f"Run {int(run)}"


def run_label(folder_name):
    """"3" for a folder called "Run 3" / "run_3" / "RUN-3", else None."""
    m = _RUN_RE.match(str(folder_name))
    return str(int(m.group(1))) if m else None


def is_video_dir(name) -> bool:
    return str(name).upper() == VIDEO_FOLDER_NAME


def raw_root(lib_root) -> Path:
    return Path(lib_root) / RAW_DIR


def deployment_dir(lib_root, deployment) -> Path:
    return raw_root(lib_root) / deployment


def treatment_dir(lib_root, deployment, treatment) -> Path:
    return deployment_dir(lib_root, deployment) / treatment


def run_dir(lib_root, deployment, treatment, run) -> Path:
    return treatment_dir(lib_root, deployment, treatment) / run_folder_name(run)


def in_video_dir(path, raw_dir) -> bool:
    """Whether `path` sits inside a VIDEO folder (a clip, not a recording)."""
    try:
        rel = Path(path).relative_to(raw_dir)
    except ValueError:
        return False
    return any(is_video_dir(p) for p in rel.parts[:-1])


class RawTree:
    """One walk of a library's raw folder, everything the pages need from it:

      locations  stem (upper) -> (deployment, treatment, run, first file)
      files      stem (upper) -> [every file of that recording]
      videos     stem (upper) -> [<stem>_vid_*.mp4 clips, from any VIDEO folder]

    Built by `scan_tree` in a single os.walk (one walk rather than a
    listing per folder matters on OneDrive). Plain data, so it can be
    built off the GUI thread."""

    def __init__(self):
        self.locations = {}
        self.files = {}
        self.videos = {}


def scan_tree(raw_dir, folder=None):
    """Walk `folder` (default: all of `raw_dir`), with every position read
    relative to `raw_dir` - see RawTree. A video clip is matched to its
    recording by stem (`<stem>_vid_...mp4`), wherever its VIDEO folder is."""
    tree = RawTree()
    raw_dir = Path(raw_dir)
    folder = Path(folder) if folder is not None else raw_dir
    if not folder.is_dir():
        return tree
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        try:
            rel = Path(dirpath).relative_to(raw_dir).parts
        except ValueError:
            rel = ()
        if any(is_video_dir(p) for p in rel):
            for name in filenames:
                if "_vid_" in name and name.lower().endswith(".mp4"):
                    stem = name.split("_vid_")[0].upper()
                    tree.videos.setdefault(stem, []).append(Path(dirpath) / name)
            continue
        deployment = rel[0] if len(rel) >= 1 else UNGROUPED
        treatment = rel[1] if len(rel) >= 2 else UNGROUPED
        run = (run_label(rel[2]) or rel[2]) if len(rel) >= 3 else DEFAULT_RUN
        for name in sorted(filenames):
            if name == README_NAME:
                continue
            path = Path(dirpath) / name
            stem = os.path.splitext(name)[0].upper()
            tree.files.setdefault(stem, []).append(path)
            tree.locations.setdefault(stem, (deployment, treatment, run, path))
    return tree


def has_files(folder) -> bool:
    """Whether anything but empty folders (and our own readme) is inside."""
    folder = Path(folder)
    if not folder.exists():
        return False
    return any(p.is_file() and p.name != README_NAME for p in folder.rglob("*"))


def count_files(folder) -> int:
    folder = Path(folder)
    if not folder.exists():
        return 0
    return sum(1 for p in folder.rglob("*")
               if p.is_file() and p.name != README_NAME)


def build_run_folders(lib_root, deployment, treatment, runs):
    """`Run 1..runs`, each with its VIDEO subfolder - idempotent. Returns
    the run folders that were newly created."""
    created = []
    for n in range(1, max(1, int(runs or 1)) + 1):
        folder = run_dir(lib_root, deployment, treatment, n)
        if not folder.exists():
            created.append(folder)
        (folder / VIDEO_FOLDER_NAME).mkdir(parents=True, exist_ok=True)
    return created


def extra_run_folders(lib_root, deployment, treatment, runs):
    """Run folders beyond `runs` (e.g. Run 3 once a treatment drops to 2
    runs) - what an Update would remove."""
    base = treatment_dir(lib_root, deployment, treatment)
    if not base.exists():
        return []
    out = []
    for entry in sorted(base.iterdir()):
        label = run_label(entry.name) if entry.is_dir() else None
        if label is not None and int(label) > int(runs or 1):
            out.append(entry)
    return out


def processed_csvs(lib_root):
    """Every processed sensor CSV in a library, sorted by name."""
    csv_dir = Path(lib_root) / CSV_DIR
    try:
        entries = list(os.scandir(csv_dir))
    except OSError:
        return []
    return sorted(Path(e.path) for e in entries
                  if e.is_file() and e.name.lower().endswith(".csv")
                  and not Path(e.name).stem.endswith(_NOT_SENSOR_SUFFIXES))


def video_index(lib_dir):
    """{stem: [video paths]} across every library in `lib_dir` - one
    os.walk per library's raw folder, only looking at `*_vid_*.mp4` names.

    Deduplicated by resolved path: a library folder can be reachable under
    more than one entry in the libraries directory (a case-variant name, a
    shortcut/junction, a synced duplicate), which would otherwise list the
    same physical video twice against one recording."""
    index, seen_by_stem = {}, {}
    try:
        libs = [p for p in Path(lib_dir).iterdir() if p.is_dir()]
    except OSError:
        libs = []
    for lib in libs:
        raw_dir = lib / RAW_DIR
        if not raw_dir.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(raw_dir):
            for name in filenames:
                if "_vid_" not in name or not name.lower().endswith(".mp4"):
                    continue
                video = Path(dirpath) / name
                stem = name.split("_vid_")[0]
                try:
                    key = str(video.resolve()).lower()
                except OSError:
                    key = str(video).lower()
                seen = seen_by_stem.setdefault(stem, set())
                if key in seen:
                    continue
                seen.add(key)
                index.setdefault(stem, []).append(video)
    return index
