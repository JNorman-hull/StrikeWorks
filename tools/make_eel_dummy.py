"""Dummy EEL tag recordings, for testing StrikeWorks end to end without a tag.

Writes a library of made-up recordings at each sample rate the tag offers
(2000, 2500 and 5000 Hz), laid out as a real deployment:

    <library>/raw_sens_data/DUMMY_EEL/<rate> Hz/Run 1/EEL_001-MMDDhhmmss.HIG/.IMP
    <library>/dummy_annotations.csv     the known label of every recording

The files follow the EEL Tag Binary Format Specification (E10 firmware,
gen-2): a HIG header holding filter / sample rate / trigger, a 2000-sample
start-up burst, triggered events with a 100-sample pre-trigger and re-emitted
records, and a continuous 100 Hz IMP stream with a pressure dip at the nadir.
Every recording has several HIG spikes - collisions and shears, some inside
the 200 ms nadir window and some outside it.

None of this is real data: a model trained on it only shows the pipeline
runs. To use the library, run this, point Settings > libraries folder at the
folder holding it, process it, then import dummy_annotations.csv on
Validate and annotate.

    .venv\\Scripts\\python.exe tools\\make_eel_dummy.py
    .venv\\Scripts\\python.exe tools\\make_eel_dummy.py --out D:\\somewhere\\EEL_Dummy --count 10
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RATES = (2000, 2500, 5000)
DEFAULT_OUT = ROOT / "libraries" / "EEL_Dummy"
LABELS_NAME = "dummy_annotations.csv"
DEVICE = "EEL_001"
DEPLOYMENT = {"site": "DUMMY", "deployment_id": "DUMMY_EEL", "pump_turbine": "DUMMY",
              "type": "Axial flow"}
CONDITIONS = {"rpm": 400, "head": 3, "flow": 1, "point_bep": 90}

DURATION_S = 12.0
NADIR_S = 6.0

# The format, written out from the specification rather than imported from
# the reader, so a mistake in the reader shows up instead of being copied here.
HIG = np.dtype([("tick", ">u4"), ("ax", ">i2"), ("ay", ">i2"), ("az", ">i2"), ("term", "u1")])
IMP = np.dtype([("tick", ">u4"), ("ax", ">i2"), ("ay", ">i2"), ("az", ">i2"),
                ("gx", ">i2"), ("gy", ">i2"), ("gz", ">i2"),
                ("p", ">u2"), ("t", ">i2"), ("b", ">i2"), ("term", "u1")])
TERMINATOR = 0x0B
FILTER_HZ = 640
TRIGGER_G = 60
FLUSH_SAMPLES = 2000
PRE_TRIGGER = 100
POST_TRIGGER = 2000
REEMITTED = 20
HIG_LSB_PER_G = 10
IMP_LSB_PER_G = 2048
PRESSURE_DATUM = 10000      # 100.00 kPa at 0.01 kPa per LSB

COLLISION, SHEAR = "collision", "shear"

# One recording of each kind, in turn. Spikes are (time s, peak g, shape);
# the largest sits beside the nadir, because that is where the nadir search
# looks. no_contact's stay under the 95 g the HIG peak analysis counts from.
KINDS = (
    {"labels": {"passage_type": "leading_edge", "leading_type": "direct",
                "concentric_pump_region": "2", "strike_location": "1",
                "approach_orientation": "1"},
     "spikes": ((3.0, 120, COLLISION), (NADIR_S + 0.02, 450, COLLISION),
                (NADIR_S + 0.06, 190, SHEAR), (9.5, 210, COLLISION))},
    {"labels": {"passage_type": "other", "other_type": "hub_1",
                "concentric_pump_region": "3", "strike_location": "2",
                "approach_orientation": "2"},
     "spikes": ((2.5, 110, COLLISION), (NADIR_S - 0.03, 260, COLLISION),
                (8.8, 130, SHEAR))},
    {"labels": {"passage_type": "no_contact"},
     "spikes": ((3.5, 70, COLLISION), (NADIR_S + 0.03, 85, COLLISION),
                (8.0, 65, COLLISION))},
)


def stem_for(rate, number):
    """`EEL_001-MMDDhhmmss`, the final sensor's name: a different hour per
    rate and a different minute per recording, so no two share a name."""
    return f"{DEVICE}-1105{10 + RATES.index(rate):02d}{number:02d}00"


def _pulse(ticks, centre, width_ticks):
    return np.exp(-(((ticks - centre) / width_ticks) ** 2))


def _spike_g(ticks, rate, peak_tick, peak_g, shape):
    """A spike's magnitude in g on `ticks`. A collision is one narrow pulse.
    A shear is a sharp top on a broad shoulder: it stays above 70 % of its
    height for longer than the 7.5 ms that separates the two, and still
    stands out enough to be found as a peak."""
    if shape == COLLISION:
        return peak_g * _pulse(ticks, peak_tick, 0.0015 * rate)
    return (0.8 * peak_g * _pulse(ticks, peak_tick, 0.012 * rate)
            + 0.2 * peak_g * _pulse(ticks, peak_tick, 0.0006 * rate))


def _hig_order(peak_ticks, last_tick):
    """The ticks a HIG file holds, in the order they are written: the
    start-up burst, then each trigger's pre-trigger and post-trigger window.
    A trigger while a window is still open extends it and re-emits a few
    records the stream has just written (spec section 3.2)."""
    order = list(range(1, FLUSH_SAMPLES + 1))
    written = until = FLUSH_SAMPLES
    for peak in sorted(peak_ticks):
        if peak - PRE_TRIGGER > until:
            order += range(written + 1, until + 1)
            order += range(peak - PRE_TRIGGER, peak + 1)
        else:
            order += range(written + 1, peak + 1)
            order += range(peak - REEMITTED + 1, peak + 1)
        written = peak
        until = min(peak + POST_TRIGGER, last_tick)
    order += range(written + 1, until + 1)
    return np.array(order, dtype=np.int64)


def _hig_records(rate, spikes, rng):
    last_tick = int(DURATION_S * rate)
    # one signal per tick, so a re-emitted record repeats its first byte for byte
    every_tick = np.arange(last_tick + 1, dtype=float)
    g = np.zeros(last_tick + 1)
    for time_s, peak_g, shape in spikes:
        g += _spike_g(every_tick, rate, round(time_s * rate), peak_g, shape)
    direction = np.array([0.8, 0.5, 0.33])
    direction = direction / np.linalg.norm(direction)
    axes = {}
    for name, unit, resting in zip(("ax", "ay", "az"), direction, (0.0, -1.0, 0.1)):
        noise = rng.integers(-8, 9, last_tick + 1)
        axes[name] = np.rint((g * unit + resting) * HIG_LSB_PER_G + noise).astype(np.int16)

    order = _hig_order([round(s[0] * rate) for s in spikes], last_tick)
    rec = np.zeros(len(order) + 1, dtype=HIG)
    # record 0 is the E10 header: filter, sample rate and trigger, not a sample
    rec[0] = (0, FILTER_HZ, rate, TRIGGER_G, TERMINATOR)
    rec["tick"][1:] = order
    for name, values in axes.items():
        rec[name][1:] = values[order]
    rec["term"] = TERMINATOR
    return rec


def _imp_records(rate, spikes, rng, dip_kpa):
    step = rate // 100
    ticks = np.arange(step, int(DURATION_S * rate) + 1, step)
    time_s = ticks / rate
    n = len(ticks)
    disturbance = np.zeros(n)
    for spike_s, peak_g, _shape in spikes:
        disturbance += min(peak_g / 40.0, 12.0) * np.exp(-(((time_s - spike_s) / 0.02) ** 2))

    rec = np.zeros(n + 1, dtype=IMP)
    # record 0 is the E10 header: the boot datum, everything else zero
    rec[0] = (0, 0, 0, 0, 0, 0, 0, PRESSURE_DATUM, 0, 0, TERMINATOR)
    body = rec[1:]
    body["tick"] = ticks
    # resting tilted, so az (near +0.15 g) can't copy the gyro Y of gen-1 firmware
    body["ax"] = np.rint(disturbance * IMP_LSB_PER_G * 0.6) + rng.integers(-20, 21, n)
    body["ay"] = -2030 + rng.integers(-20, 21, n)
    body["az"] = 300 + np.rint(disturbance * IMP_LSB_PER_G * 0.4) + rng.integers(-20, 21, n)
    for name, gain in (("gx", 1.0), ("gy", -0.7), ("gz", 0.4)):
        body[name] = np.rint(disturbance * 400 * gain) + rng.integers(-5, 6, n)
    dip = dip_kpa * 100 * np.exp(-(((time_s - NADIR_S) / 0.05) ** 2))
    body["p"] = PRESSURE_DATUM - np.rint(dip) + rng.integers(-2, 3, n)
    body["t"] = 2650 + np.rint(np.linspace(0, 12, n))
    body["b"] = 410 - np.rint(np.linspace(0, 1, n))
    body["term"] = TERMINATOR
    return rec


def write_recording(folder, rate, number):
    """One recording's .HIG and .IMP in `folder`, the same every time for a
    given rate and number. Returns (stem, its labels)."""
    kind = KINDS[number % len(KINDS)]
    rng = np.random.default_rng(rate * 1000 + number)
    # no two alike, but each spike stays on its side of the thresholds it tests
    spikes = [(time_s + rng.uniform(-0.002, 0.002), peak_g * rng.uniform(0.97, 1.03), shape)
              for time_s, peak_g, shape in kind["spikes"]]
    stem = stem_for(rate, number)
    folder.mkdir(parents=True, exist_ok=True)
    _hig_records(rate, spikes, rng).tofile(folder / f"{stem}.HIG")
    _imp_records(rate, spikes, rng, rng.uniform(22, 28)).tofile(folder / f"{stem}.IMP")
    return stem, kind["labels"]


def make_library(out=DEFAULT_OUT, count=3, rates=RATES):
    """Write the library: `count` recordings per rate, its deployment plan
    and its annotations. Returns the annotations as a DataFrame. Refuses a
    folder holding anything but an earlier dummy library."""
    from modules import deployment_index as di
    from modules import raw_layout

    out = Path(out)
    if out.exists() and any(out.iterdir()) and not (out / LABELS_NAME).exists():
        raise SystemExit(f"{out} already holds something else - choose another folder.")

    dep = DEPLOYMENT["deployment_id"]
    treatments = [{**CONDITIONS, "treatment": f"{rate} Hz", "runs": 1} for rate in rates]
    raw_layout.raw_root(out).mkdir(parents=True, exist_ok=True)
    di.save_plan(out, DEPLOYMENT, treatments, sensor_key="micro_eel")

    rows = []
    for rate in rates:
        treatment = f"{rate} Hz"
        raw_layout.build_run_folders(out, dep, treatment, 1)
        folder = raw_layout.run_dir(out, dep, treatment, 1)
        for number in range(count):
            stem, labels = write_recording(folder, rate, number)
            rows.append({"file": stem, **labels})
    labels = pd.DataFrame(rows)
    labels.to_csv(out / LABELS_NAME, index=False)
    return labels


def main():
    ap = argparse.ArgumentParser(description="Write a library of dummy EEL tag recordings.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="library folder to write")
    ap.add_argument("--count", type=int, default=3, help="recordings per sample rate")
    args = ap.parse_args()
    labels = make_library(args.out, args.count)
    print(f"Wrote {len(labels)} recording(s) ({args.count} each at "
          f"{', '.join(map(str, RATES))} Hz) to {args.out}")


if __name__ == "__main__":
    main()
