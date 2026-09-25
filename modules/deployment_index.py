# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""The deployment plan, and the rows it puts in the sensor index.

A study is planned before any sensor is wetted: a site, a deployment, the
machine, and then one set of conditions per treatment (head, flow, BEP,
RPM) with the number of runs that treatment gets. The Prepare page's Study
design tab collects that and writes it into the library's
``global_sensor_index.csv`` - one row per treatment *per run* - so that
processing can stamp a batch of sensors with the treatment and run they
were recorded under, instead of that metadata being typed in per file.

Several deployments in one library
----------------------------------
A library is not one site. Plan rows carry their own site, deployment ID,
machine and type, so a library holds as many deployments as it needs;
``deployments()`` lists them and the Study design tab edits one at a time.
Saving replaces only the rows of the deployment being edited.

Plan rows and sensor rows share one file
----------------------------------------
A plan row is a real row of the index with ``file`` set to ``label_pad``.
Nothing else produces a sensor called that, so plan rows are easy to keep
out of the way: ``sensor_rows()`` drops them, and every page that lists or
counts sensors uses it. They are deliberately *not* dropped when a page
rewrites the whole index - that would delete the plan.

A library processed before any of this existed has no plan rows, but its
sensor rows still carry whatever conditions were typed in. So
``deployments()`` and ``treatments()`` fall back to reading those, and an
existing library opens with its real deployments already filled in.

The columns come from ``index_schema``, which the parser also uses, so plan
rows and sensor rows always align.
"""
from pathlib import Path

import pandas as pd

from PySide6.QtCore import QObject, Signal

from . import index_schema
from .raw_layout import UNGROUPED

INDEX_REL = Path("processed_sens_data") / "index" / "global_sensor_index.csv"
#: the library's running annotated dataset (Annotate's Save + next) - it
#: carries deployment_id/treatment/run too, so a relabel follows into it
DATASET_REL = Path("processed_sens_data") / "model_features.csv"

#: value in the `file` column that marks a row as plan, not sensor
PAD_FILE = "label_pad"

FILE_COL = "file"
TREATMENT_COL = "treatment"
RUN_COL = "run"
DEPLOYMENT_COL = "deployment_id"

#: set to Y on a sensor once it carries deployment information
DEPLOYMENT_FLAG_COL = "deployment_info"

#: set to Y on a sensor manually flagged bad (Annotate's "no annotations" /
#: bad-sensor checkbox) - the single definition every list of sensors that
#: shows bad/good status (Annotate, Export animations, ...) reads
BAD_SENS_COL = "bad_sens"

# what the Study design tab collects, and the index column each lands in
DEPLOYMENT_FIELDS = [
    ("site", "Site"),
    ("deployment_id", "Deployment ID"),
    ("pump_turbine", "Pump / turbine model"),
    ("type", "Pump / turbine type"),
]

# per treatment. `run` is not here: it is a count in the tab, and one row
# per run in the file
TREATMENT_FIELDS = [
    ("treatment", "Treatment"),
    ("head", "Head"),
    ("flow", "Flow"),
    ("point_bep", "BEP (%)"),
    ("rpm", "RPM"),
]

DEPLOYMENT_COLUMNS = [c for c, _ in DEPLOYMENT_FIELDS]
TREATMENT_COLUMNS = [c for c, _ in TREATMENT_FIELDS]

#: which sensor configuration (sensor_config.py key) a deployment was
#: planned for - held on its plan rows and stamped onto its sensors, so
#: reopening a deployment restores its sensor and downstream stages can
#: follow it. Not an index_schema column: the parser's own output stays
#: exactly the MVP's, this only appears once a plan records one.
SENSOR_CONFIG_COL = "sensor_config"

#: every column a treatment carries onto a sensor when one is assigned
STAMPED_COLUMNS = (DEPLOYMENT_COLUMNS + TREATMENT_COLUMNS
                   + [RUN_COL, SENSOR_CONFIG_COL])

MAX_RUNS = 100


class _Notifier(QObject):
    """Emits when a library's plan is written, so pages can re-read it."""
    plan_saved = Signal(str)       # library root


notifier = _Notifier()


# ── reading ──────────────────────────────────────────────────────────────────
def index_path(root) -> Path:
    return Path(root) / INDEX_REL


def read_index(root):
    """The whole index - plan rows included. None when there is not one."""
    path = index_path(root)
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None


def is_plan_row(df):
    """Boolean mask of the plan rows in `df`."""
    if df is None or FILE_COL not in df.columns:
        return None
    return df[FILE_COL].astype(str).str.strip().str.lower() == PAD_FILE


def is_bad(df, stem: str) -> bool:
    """Whether `stem` is flagged bad in the index `df` (may be None)."""
    if df is None or FILE_COL not in df.columns or BAD_SENS_COL not in df.columns:
        return False
    row = df[df[FILE_COL] == stem]
    if row.empty:
        return False
    return str(row[BAD_SENS_COL].iloc[0]).strip().upper() == "Y"


def sensor_rows(df):
    """`df` without its plan rows - what every sensor listing wants."""
    mask = is_plan_row(df)
    if mask is None:
        return df
    return df[~mask].copy()


def plan_rows(df):
    """Just the plan rows."""
    mask = is_plan_row(df)
    if mask is None:
        return df.iloc[0:0].copy() if df is not None else None
    return df[mask].copy()


def _clean(value):
    """A cell as text, with the index's several spellings of empty removed."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "na", "none") else text


def _row_values(row, cols):
    return {c: _clean(row.get(c, "")) for c in cols}


def _plan_or_sensor_rows(root, df=None):
    """Plan rows if the library has them, else its processed sensor rows.

    A library planned in StrikeWorks has plan rows. One processed before
    this existed does not, but its sensors still carry the conditions, so
    reading those back is how an existing library opens with its
    deployments already filled in. `df` - the index, if the caller has
    already read it.
    """
    if df is None:
        df = read_index(root)
    if df is None:
        return None
    planned = plan_rows(df)
    if planned is not None and not planned.empty:
        return planned
    return sensor_rows(df)


def deployments(root, df=None):
    """Every deployment in a library, as {column: value}.

    Distinct combinations of site / deployment ID / machine / type, in the
    order they appear. `df` - the index, if the caller has already read it.
    """
    rows = _plan_or_sensor_rows(root, df)
    if rows is None or rows.empty:
        return []
    out, seen = [], set()
    for _, row in rows.iterrows():
        entry = _row_values(row, DEPLOYMENT_COLUMNS)
        if not any(entry.values()):
            continue
        key = tuple(entry[c] for c in DEPLOYMENT_COLUMNS)
        if key in seen:
            continue
        seen.add(key)
        entry[SENSOR_CONFIG_COL] = _clean(row.get(SENSOR_CONFIG_COL, ""))
        out.append(entry)
    return out


def describe_deployment(deployment) -> str:
    """One-line label for a deployment picker."""
    ident = deployment.get(DEPLOYMENT_COL, "").strip()
    site = deployment.get("site", "").strip()
    if ident and site:
        return f"{ident}  ({site})"
    return ident or site or "(unnamed deployment)"


def treatments(root, deployment_id=None, df=None):
    """The treatments in a library, or in one deployment.

    Each entry carries its deployment fields, its conditions, and ``runs``:
    how many runs are planned for it. `df` - the index, if already read.
    """
    rows = _plan_or_sensor_rows(root, df)
    if rows is None or rows.empty:
        return []

    grouped, order = {}, []
    for _, row in rows.iterrows():
        name = _clean(row.get(TREATMENT_COL, ""))
        if not name:
            continue
        ident = _clean(row.get(DEPLOYMENT_COL, ""))
        if deployment_id is not None and ident != str(deployment_id).strip():
            continue
        key = (ident, name)
        if key not in grouped:
            entry = _row_values(row, DEPLOYMENT_COLUMNS + TREATMENT_COLUMNS
                                + [SENSOR_CONFIG_COL])
            entry["runs"] = set()
            grouped[key] = entry
            order.append(key)
        run = _clean(row.get(RUN_COL, ""))
        if run:
            grouped[key]["runs"].add(run)

    out = []
    for key in order:
        entry = grouped[key]
        entry["runs"] = _run_count(entry["runs"])
        out.append(entry)
    return out


def _run_count(runs):
    """How many runs a treatment has, from the run labels seen."""
    numbers = []
    for run in runs:
        try:
            numbers.append(int(float(run)))
        except (TypeError, ValueError):
            pass
    if numbers:
        return max(max(numbers), len(runs))
    return len(runs) or 1


def _run_sort_key(run):
    """Numeric runs in numeric order, anything else after them by name."""
    try:
        return (0, int(float(run)), "")
    except (TypeError, ValueError):
        return (1, 0, str(run))


def describe(treatment) -> str:
    """One-line label for a treatment, for a picker or a log."""
    name = treatment.get(TREATMENT_COL, "").strip() or "(unnamed)"
    bits = []
    for col, label in TREATMENT_FIELDS:
        if col == TREATMENT_COL:
            continue
        val = str(treatment.get(col, "")).strip()
        if val:
            bits.append(f"{label} {val}")
    runs = treatment.get("runs")
    if runs:
        bits.append(f"{runs} run(s)")
    return f"{name} - {', '.join(bits)}" if bits else name


# ── writing ──────────────────────────────────────────────────────────────────
def columns():
    """The index's column list (the app's schema)."""
    return index_schema.columns()


def _conform(df):
    """Give `df` every schema column, adding any it lacks."""
    defaults = index_schema.defaults()
    for col in index_schema.columns():
        if col not in df.columns:
            df[col] = defaults.get(col, "")
    return df


def save_plan(root, deployment, treatments_in, sensor_key=None):
    """Write one deployment's plan into the library's index.

    One row per treatment per run. Sensor rows are left exactly as they
    are, and so are the plan rows of *other* deployments - a library holds
    as many deployments as it needs.

    Each entry in `treatments_in` is {column: value} plus ``runs``, a count.
    `sensor_key` records the sensor configuration the deployment uses
    (``SENSOR_CONFIG_COL``); None keeps whatever `deployment` carries.
    Returns (path, n_rows_written).
    """
    root = Path(root)
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    cols = columns()
    defaults = index_schema.defaults()
    ident = str(deployment.get(DEPLOYMENT_COL, "")).strip()
    sensor_key = sensor_key or deployment.get(SENSOR_CONFIG_COL, "") or ""

    rows = []
    for treatment in treatments_in:
        try:
            n_runs = max(1, min(MAX_RUNS, int(treatment.get("runs", 1) or 1)))
        except (TypeError, ValueError):
            n_runs = 1
        for run in range(1, n_runs + 1):
            row = {c: defaults.get(c, "") for c in cols}
            row[FILE_COL] = PAD_FILE
            for col, value in {**deployment, **treatment}.items():
                if col in row:
                    row[col] = value
            row[RUN_COL] = run
            row[SENSOR_CONFIG_COL] = sensor_key
            rows.append(row)
    new = pd.DataFrame(rows, columns=cols + [SENSOR_CONFIG_COL])

    existing = read_index(root)
    if existing is None:
        out = new
    else:
        existing = _conform(existing)
        planned = is_plan_row(existing)
        same = (existing[DEPLOYMENT_COL].map(_clean) == ident
                if DEPLOYMENT_COL in existing.columns
                else pd.Series(False, index=existing.index))
        keep = existing[~(planned & same)].copy()
        out = _conform(pd.concat([new, keep], ignore_index=True))

    out.to_csv(path, index=False)
    notifier.plan_saved.emit(str(root))
    return path, len(new)


def apply_treatment(root, files, treatment, run=None):
    """Stamp a treatment - and optionally a run - onto the rows of `files`.

    Called after processing, so a batch of sensors carries the conditions it
    was recorded under. Also flips ``deployment_info`` to Y, which is what
    marks a sensor as having its deployment information filled in.

    Returns the number of rows changed.
    """
    df = read_index(root)
    if df is None or FILE_COL not in df.columns or not files:
        return 0

    wanted = {str(f) for f in files}
    mask = df[FILE_COL].astype(str).isin(wanted)
    n = int(mask.sum())
    if not n:
        return 0

    values = {c: str(treatment.get(c, "")).strip() for c in STAMPED_COLUMNS}
    if run is not None:
        values[RUN_COL] = str(run).strip()
    values[DEPLOYMENT_FLAG_COL] = "Y"

    for col, value in values.items():
        if not value:
            continue
        if col not in df.columns:
            df[col] = index_schema.defaults().get(col, "")
        # a column read back as float (head, flow, rpm...) will not take a
        # string in place, so widen it first rather than lose the value
        df[col] = df[col].astype(object)
        df.loc[mask, col] = value

    df.to_csv(index_path(root), index=False)
    return n


def set_row_values(root, file, values: dict) -> int:
    """Write `values` onto the index row for `file`.

    The generic form of what `apply_treatment` does for a treatment/run
    batch: mask by file, widen any numeric column to take a string, write,
    save. Used for one recording at a time (Annotate's annotation entry and
    manual `bad_sens` flag), so unlike `apply_treatment` it targets a single
    file rather than a batch. A column `values` names that the index does
    not have yet is added, defaulting to "" for every other row - annotation
    columns are not part of `index_schema.SCHEMA`, so they only appear once
    something is actually recorded.

    Returns the number of rows changed (0 if the file has no index row -
    this never creates one; a recording must already be processed).
    """
    df = read_index(root)
    if df is None or FILE_COL not in df.columns:
        return 0

    mask = df[FILE_COL].astype(str) == str(file)
    n = int(mask.sum())
    if not n:
        return 0

    for col, value in values.items():
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)
        df.loc[mask, col] = value

    df.to_csv(index_path(root), index=False)
    return n


# ── relabelling (deployment editor's Update) ─────────────────────────────────
def _relabel_frame(df, where, values):
    """Set `values` on every row of `df` matching all of `where` (compared
    as cleaned text). Returns the number of rows changed."""
    if df is None:
        return 0
    mask = pd.Series(True, index=df.index)
    for col, want in where.items():
        if col not in df.columns:
            return 0
        mask &= df[col].map(_clean) == str(want).strip()
    n = int(mask.sum())
    if not n:
        return 0
    for col, value in values.items():
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)
        df.loc[mask, col] = value
    return n


def relabel(root, where, values):
    """Relabel index rows (plan and sensor alike) matching `where`, and the
    same rows of the library's running dataset (``DATASET_REL``) - so a
    renamed deployment/treatment follows through everything already
    processed or annotated under the old name. Returns index rows changed."""
    n = 0
    df = read_index(root)
    if df is not None:
        n = _relabel_frame(df, where, values)
        if n:
            df.to_csv(index_path(root), index=False)
    dataset = Path(root) / DATASET_REL
    if dataset.exists():
        try:
            ds = pd.read_csv(dataset, low_memory=False)
            if _relabel_frame(ds, where, values):
                ds.to_csv(dataset, index=False)
        except Exception:
            pass
    return n


def rename_deployment(root, old, new):
    return relabel(root, {DEPLOYMENT_COL: old}, {DEPLOYMENT_COL: new})


def rename_treatment(root, deployment_id, old, new):
    return relabel(root, {DEPLOYMENT_COL: deployment_id, TREATMENT_COL: old},
                   {TREATMENT_COL: new})


def restamp_deployment(root, deployment_id):
    """Re-apply one deployment's saved plan to its already-processed
    sensors: deployment fields, each sensor's treatment conditions (by
    treatment name) and the sensor configuration. Runs are left alone - a
    sensor's run comes from where its file sits. Returns rows changed."""
    df = read_index(root)
    if df is None or FILE_COL not in df.columns or DEPLOYMENT_COL not in df.columns:
        return 0
    plan = {t[TREATMENT_COL]: t for t in treatments(root, deployment_id)}
    if not plan:
        return 0
    sensors = ~is_plan_row(df) & (df[DEPLOYMENT_COL].map(_clean)
                                  == str(deployment_id).strip())
    if TREATMENT_COL not in df.columns:
        return 0
    n = 0
    cols = DEPLOYMENT_COLUMNS + TREATMENT_COLUMNS + [SENSOR_CONFIG_COL]
    for name, t in plan.items():
        mask = sensors & (df[TREATMENT_COL].map(_clean) == name)
        if not mask.any():
            continue
        n += int(mask.sum())
        for col in cols:
            value = str(t.get(col, "")).strip()
            if not value:
                continue
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].astype(object)
            df.loc[mask, col] = value
    if n:
        df.to_csv(index_path(root), index=False)
    return n


def stamp_by_location(root, located):
    """Label freshly processed recordings from where their raw files sit.

    `located` is [{"stem", "deployment", "treatment", "run"}, ...] (see
    raw_layout.locate). Each (deployment, treatment, run) group is stamped
    with that deployment's saved plan - its deployment fields and the
    treatment's conditions - plus the run from the folder; a deployment or
    treatment with no saved plan still gets its name and run, so nothing
    processed is ever left unlabelled. Returns rows changed."""
    groups = {}
    for f in located:
        key = (f.get("deployment", UNGROUPED), f.get("treatment", UNGROUPED),
               f.get("run") or "1")
        groups.setdefault(key, []).append(f["stem"])

    dep_entries, plans = {}, {}
    n = 0
    for (dep, treat, run), stems in groups.items():
        if not dep or dep == UNGROUPED:
            continue   # loose in raw_sens_data itself - nothing to label with
        if dep not in dep_entries:
            dep_entries[dep] = next(
                (d for d in deployments(root)
                 if d.get(DEPLOYMENT_COL, "") == dep), {})
            plans[dep] = {t[TREATMENT_COL]: t for t in treatments(root, dep)}
        values = dict(dep_entries[dep])
        values[DEPLOYMENT_COL] = dep
        if treat and treat != UNGROUPED:
            values.update(plans[dep].get(treat, {}))
            values[TREATMENT_COL] = treat
        n += apply_treatment(root, stems, values, run=run)
    return n
