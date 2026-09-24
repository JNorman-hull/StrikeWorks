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


def locate(path, raw_dir):
    """(deployment, treatment, run) for a raw file under `raw_dir`.

    The first folder level is the deployment, the second the treatment,
    the third the run ("Run 2" -> "2"; any other name is kept as-is). No
    run level means Run 1 - there is always at least one run."""
    try:
        dirs = [d for d in Path(path).relative_to(raw_dir).parts[:-1]
                if not is_video_dir(d)]
    except ValueError:
        return UNGROUPED, UNGROUPED, DEFAULT_RUN
    deployment = dirs[0] if len(dirs) >= 1 else UNGROUPED
    treatment = dirs[1] if len(dirs) >= 2 else UNGROUPED
    run = DEFAULT_RUN
    if len(dirs) >= 3:
        run = run_label(dirs[2]) or dirs[2]
    return deployment, treatment, run


class RawTree:
    """One walk of a library's raw folder, everything the pages need from it:

      locations  stem (upper) -> (deployment, treatment, run, first file)
      files      stem (upper) -> [every file of that recording]
      videos     stem (upper) -> [<stem>_vid_*.mp4 clips, from any VIDEO folder]

    Built by `scan_tree` - a single os.walk, which on a OneDrive-synced
    library is the difference between a library opening in a second and in
    most of a minute: the pages used to rglob the tree once each and then
    list every sensor's VIDEO folder separately, thousands of directory
    listings for a big library. Plain data, so it can be built off the GUI
    thread."""

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


def video_dirs_for(raw_file, raw_dir):
    """Every VIDEO folder a recording's clips could be in: its own folder's
    first, then each parent's up to (and including) its deployment folder -
    the current per-run layout and the older per-treatment one both work."""
    out = []
    folder = Path(raw_file).parent
    try:
        depth = len(folder.relative_to(raw_dir).parts)
    except ValueError:
        return out
    for _ in range(max(depth, 0)):
        if folder.exists():
            for entry in folder.iterdir():
                if entry.is_dir() and is_video_dir(entry.name):
                    out.append(entry)
        folder = folder.parent
    return out


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
