# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Reader for the EEL tag (Micro-EEL) - its .HIG/.IMP pair onto the same
processed-CSV shape the RAPID parser writes, so everything downstream
(validation, datasets, training, prediction) works unchanged.

Follows the EEL Tag Binary Format Specification (v1.1.0-empirical,
format-specification.md shipped alongside the first EEL library):

  .HIG   11-byte big-endian records: uint32 tick, int16 ax/ay/az (/10 = g),
         uint8 terminator 0x0B. Event-triggered - the tick is a master-clock
         counter, not a record number, so time = tick / samplerate and the
         gaps between events are real. Record 0 is a header (all-zero before
         firmware E10; E10 carries filter / sample rate / trigger threshold
         in ax/ay/az) and is never a sample. Re-emitted pre-trigger records
         repeat an earlier tick byte for byte and are dropped, keeping the
         first; a repeat that differs is corruption and stops the file.
  .IMP   23-byte big-endian records: uint32 tick (step = samplerate / 100),
         int16 ax/ay/az (/2048 = g), gx/gy/gz (x 0.070 = deg/s), uint16
         pressure (/100 = kPa, relative to a 100.000 kPa datum set at boot),
         int16 temperature (/100 = C), battery (/100 = V), terminator 0x0B.
         Record 0 is a header (zero payload, terminator 0x27 before E10;
         pressure 10000 and the rest zero from E10) and is discarded.

Both streams count the same master clock, so they co-register exactly -
no cross-correlation or drift model. The sample rate lives in the
deployment's .log (`Samplerate`), read when it's beside the files; without
one, the configuration's timestamp clock is used.

Channel names and units match RAPID's, so a dataset mixes both devices:
higacc_*_g (g), inacc_*_ms (m/s2 - EEL's g x 9.80665), rot_*_degs (deg/s),
pressure_kpa, temp_c, battery_v.

Firmware generation (spec 4.3) is detected from the data: on gen-1 the
gyroscope Y field is a copy of accelerometer Z and the whole gyro block
fails plausibility, so the rot_* channels are written as 0 with a warning
rather than published; gen-2 gyros are real and written as measured.
Every rule applied is reported in the sensor's index messages.
"""
import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from . import rapid_functions as rf

G = 9.80665
TERMINATOR = 0x0B

HIG_DTYPE = np.dtype([("tick", ">u4"), ("ax", ">i2"), ("ay", ">i2"),
                      ("az", ">i2"), ("term", "u1")])
IMP_DTYPE = np.dtype([("tick", ">u4"), ("ax", ">i2"), ("ay", ">i2"),
                      ("az", ">i2"), ("gx", ">i2"), ("gy", ">i2"),
                      ("gz", ">i2"), ("p", ">u2"), ("t", ">i2"),
                      ("b", ">i2"), ("term", "u1")])

HIG_SCALE_G = 0.1          # raw / 10
IMP_SCALE_G = 1 / 2048.0   # raw / 2048
GYRO_SCALE_DEGS = 0.070    # ST LSM6DSO at +/-2000 dps: 70 mdps/LSB
PRESSURE_SCALE_KPA = 0.01  # 0.01 kPa per LSB
TEMP_SCALE_C = 0.01
BATTERY_SCALE_V = 0.01
VALID_SAMPLERATES = (2000, 2500, 5000)

# the device name is everything before the last ten digits (MMDDhhmmss) -
# "EEL-0010829034703" is device "EEL-001" on 29/08 at 03:47:03
FILENAME_PATTERN = r"^(.+?)-?(\d{4})(\d{6})$"


class EelFormatError(ValueError):
    """A file the specification says must not be guessed at."""


def _records(path, dtype):
    """(structured records, residual bytes) - V-01: a file that isn't a
    whole number of records is truncated to whole records and reported."""
    raw = np.fromfile(path, dtype=np.uint8)
    n = raw.size // dtype.itemsize
    residual = raw.size - n * dtype.itemsize
    return np.frombuffer(raw[:n * dtype.itemsize].tobytes(), dtype=dtype), residual


def samplerate_from_log(hig_path):
    """`Samplerate` for this deployment from its .log (spec 5), or None.

    The log is `<device><MMDD>.log` beside the data - one row per deployment
    that day, joined on `Filename`. It's a superset of the data (rows with
    no files are normal), so any log in the folder whose row matches is
    used."""
    stem = Path(hig_path).stem
    for log in Path(hig_path).parent.glob("*.log"):
        try:
            with open(log, newline="", encoding="utf-8", errors="ignore") as fh:
                for row in csv.DictReader(fh):
                    if str(row.get("Filename", "")).strip() == stem:
                        rate = int(float(row.get("Samplerate", "") or 0))
                        return rate if rate > 0 else None
        except Exception:
            continue
    return None


def _event_note(rec, samplerate):
    """V-09: the HIG stream's triggered events. Each contiguous run of
    ticks is one burst; the first, starting at the very start of the
    recording, is the ring-buffer flush written at record start, not an
    event (spec 3.1). A recording with nothing else in it - a bench test,
    or a passage that never crossed the trigger threshold - is said so
    plainly, since its processed signal then has nothing to show."""
    if not len(rec):
        return "HIG: no records"
    ticks = rec["tick"].astype(np.int64)
    breaks = np.where(np.diff(ticks) != 1)[0] + 1
    segments = np.split(np.arange(len(ticks)), breaks)
    g = np.sqrt(rec["ax"].astype(float) ** 2 + rec["ay"].astype(float) ** 2
                + rec["az"].astype(float) ** 2) * HIG_SCALE_G
    if ticks[0] <= 1:
        segments = segments[1:]          # the startup flush
    if not segments:
        return ("HIG: no triggered events - only the startup flush, so "
                "nothing to analyse in this recording")
    peaks = [g[s].max() for s in segments]
    recorded = sum(len(s) for s in segments) / float(samplerate)
    return (f"HIG: {len(segments)} triggered event(s), peaks "
            f"{min(peaks):.0f}-{max(peaks):.0f} g, {recorded:.1f} s recorded")


def read_hig(path, samplerate):
    """The .HIG stream as (DataFrame[tick, time_s, higacc_x/y/z_g], notes)."""
    rec, residual = _records(path, HIG_DTYPE)
    notes = []
    if residual:
        notes.append(f"HIG: {residual} trailing byte(s) - truncated to whole "
                     "records")
    if len(rec) and rec["tick"][0] == 0:
        h = rec[0]
        if h["ax"] == 0 and h["ay"] == 0 and h["az"] == 0:
            notes.append("HIG: header record discarded (pre-E10)")
            rec = rec[1:]
        elif int(h["ay"]) == int(samplerate):
            notes.append(f"HIG: E10 header discarded - filter {int(h['ax'])} Hz, "
                         f"trigger threshold {int(h['az'])} g")
            rec = rec[1:]
    bad_term = int(np.sum(rec["term"] != TERMINATOR))
    if bad_term:
        notes.append(f"HIG: {bad_term} record(s) without the 0x0B terminator")

    # re-emitted pre-trigger records: keep the first of each tick, after
    # checking every repeat is byte-identical to it (V-04)
    ticks = rec["tick"].astype(np.int64)
    order = np.lexsort((np.arange(len(ticks)), ticks))
    sorted_ticks = ticks[order]
    first = np.r_[True, sorted_ticks[1:] != sorted_ticks[:-1]]
    n_dup = int(np.sum(~first))
    if n_dup:
        group_first = order[np.maximum.accumulate(
            np.where(first, np.arange(len(order)), 0))]
        dups = order[~first]
        payload = np.stack([rec["ax"], rec["ay"], rec["az"]], axis=1)
        if not np.array_equal(payload[dups], payload[group_first[~first]]):
            raise EelFormatError(
                f"{Path(path).name}: a re-emitted HIG record differs from the "
                "one it repeats - real corruption, not pre-trigger re-emission.")
        notes.append(f"HIG: {n_dup} re-emitted pre-trigger record(s) removed")
    keep = np.sort(order[first])
    rec = rec[keep]
    notes.append(_event_note(rec, samplerate))

    df = pd.DataFrame({
        "tick": rec["tick"].astype(np.int64),
        "higacc_x_g": np.round(rec["ax"] * HIG_SCALE_G, 1),
        "higacc_y_g": np.round(rec["ay"] * HIG_SCALE_G, 1),
        "higacc_z_g": np.round(rec["az"] * HIG_SCALE_G, 1),
    })
    df.insert(1, "time_s", df["tick"] / float(samplerate))
    return df, notes


def read_imp(path, samplerate):
    """The .IMP stream as (DataFrame[tick, time_s, inacc/rot/pressure/
    temp/battery], notes)."""
    rec, residual = _records(path, IMP_DTYPE)
    notes = []
    if residual:
        notes.append(f"IMP: {residual} trailing byte(s) - truncated to whole "
                     "records")
    if len(rec) and rec["tick"][0] == 0:
        h = rec[0]
        channels_zero = all(int(h[c]) == 0 for c in ("ax", "ay", "az", "gx", "gy", "gz"))
        if h["term"] != TERMINATOR or channels_zero:
            notes.append("IMP: header record discarded")
            rec = rec[1:]
    if not len(rec):
        raise EelFormatError(f"{Path(path).name}: no IMP data records.")
    bad_term = int(np.sum(rec["term"] != TERMINATOR))
    if bad_term:
        notes.append(f"IMP: {bad_term} record(s) without the 0x0B terminator")

    # V-05: the IMP tick step is samplerate / 100 - a file that disagrees
    # has no timebase that can be trusted, so it isn't guessed at
    steps = np.unique(np.diff(rec["tick"].astype(np.int64)))
    expected = int(round(samplerate / 100.0))
    if len(steps) and (len(steps) != 1 or steps[0] != expected):
        raise EelFormatError(
            f"{Path(path).name}: IMP tick step {steps.tolist()} doesn't match "
            f"the {samplerate:g} Hz sample rate (expected {expected}) - check "
            "the sensor configuration's timestamp clock or the deployment .log.")

    # V-07: firmware generation from the gyro Y field
    dup_fraction = float(np.mean(rec["gy"] == rec["az"]))
    gyro_ok = dup_fraction <= 0.01
    if dup_fraction >= 0.99:
        notes.append("IMP: gen-1 firmware - gyroscope block not usable, rot "
                     "channels written as 0")
    elif not gyro_ok:
        notes.append(f"IMP: gyroscope Y partly duplicates accelerometer Z "
                     f"({dup_fraction:.0%}) - neither firmware generation, "
                     "rot channels written as 0")
    else:
        notes.append("IMP: gen-2 firmware")

    pressure = rec["p"].astype(float) * PRESSURE_SCALE_KPA
    wrapped = rec["p"] == 0
    if wrapped.any():
        # V-13: over-range wraps to 0 - an artefact, not a reading
        notes.append(f"IMP: {int(wrapped.sum())} over-range pressure "
                     "sample(s) (wrapped to 0) removed")
        pressure[wrapped] = np.nan
        pressure = pd.Series(pressure).interpolate(limit_direction="both").to_numpy()

    gyro = (lambda c: np.round(rec[c] * GYRO_SCALE_DEGS, 3)) if gyro_ok else \
        (lambda c: np.zeros(len(rec)))
    df = pd.DataFrame({
        "tick": rec["tick"].astype(np.int64),
        "inacc_x_ms": np.round(rec["ax"] * IMP_SCALE_G * G, 3),
        "inacc_y_ms": np.round(rec["ay"] * IMP_SCALE_G * G, 3),
        "inacc_z_ms": np.round(rec["az"] * IMP_SCALE_G * G, 3),
        "rot_x_degs": gyro("gx"),
        "rot_y_degs": gyro("gy"),
        "rot_z_degs": gyro("gz"),
        "pressure_kpa": np.round(pressure, 2),
        "temp_c": np.round(rec["t"] * TEMP_SCALE_C, 2),
        "battery_v": np.round(rec["b"] * BATTERY_SCALE_V, 2),
    })
    df.insert(1, "time_s", df["tick"] / float(samplerate))
    return df, notes


def _on_grid(imp, hig, out_rate, imp_method="linear", hig_method="nearest"):
    """Both streams on one uniform grid (the same shape RAPID's processed
    CSV has): IMP interpolated up to it, HIG samples placed in their nearest
    slot with the unrecorded stretches at 0. The grid spans both streams -
    HIG starts at tick 1 but IMP only at its first 100 Hz tick, and those
    first milliseconds of HIG are kept, with IMP held at its edge value."""
    step = 1.0 / float(out_rate)
    start = min(imp["time_s"].min(), hig["time_s"].min() if len(hig) else np.inf)
    end = max(imp["time_s"].max(), hig["time_s"].max() if len(hig) else -np.inf)
    times = np.round(np.arange(start, end + step / 2, step), 9)
    out = pd.DataFrame({"time_s": times})

    hig_cols = [c for c in hig.columns if c not in ("tick", "time_s")]
    inside = hig[(hig["time_s"] >= start - step / 2)
                 & (hig["time_s"] <= end + step / 2)]
    for col in hig_cols:
        out[col] = 0.0
    if len(inside):
        if hig_method == "nearest":
            slots = np.clip(np.rint((inside["time_s"].to_numpy() - start) / step)
                            .astype(np.int64), 0, len(out) - 1)
            for col in hig_cols:
                out.loc[slots, col] = inside[col].to_numpy()
        else:
            for col in hig_cols:
                f = interp1d(inside["time_s"], inside[col], kind=hig_method,
                             bounds_error=False, fill_value=0.0)
                out[col] = f(times)

    for col in [c for c in imp.columns if c not in ("tick", "time_s")]:
        values = imp[col].to_numpy()
        f = interp1d(imp["time_s"], values, kind=imp_method,
                     bounds_error=False, fill_value=(values[0], values[-1]))
        out[col] = f(times)
    return out


def process_eel(paths, out_dir, config):
    """The EEL parser - `sensor_config.PARSERS["eel_imp_hig"]`."""
    hig_path, imp_path = Path(paths[".hig"]), Path(paths[".imp"])
    rate = samplerate_from_log(hig_path)
    notes = []
    configured = float(config.timebase_hz) if config is not None else 5000.0
    if rate is None:
        rate = configured
        notes.append(f"No deployment .log beside the files - {rate:g} Hz "
                     "sample rate from the sensor configuration")
    elif rate != configured:
        notes.append(f"Sample rate {rate} Hz from the deployment .log "
                     f"(configuration says {configured:g} Hz)")
    if int(rate) not in VALID_SAMPLERATES:
        notes.append(f"Unusual sample rate {rate:g} Hz (the tag writes 2000, "
                     "2500 or 5000)")

    hig, hig_notes = read_hig(hig_path, rate)
    imp, imp_notes = read_imp(imp_path, rate)
    notes += hig_notes + imp_notes

    out_rate = float(config.output_rate_hz) if config is not None else rate
    combined = _on_grid(
        imp, hig, out_rate,
        imp_method=config.method(".imp", "linear") if config else "linear",
        hig_method=config.method(".hig", "nearest") if config else "nearest")

    combined, summary = rf.post_process_combined(
        combined, fs=out_rate,
        magnitudes=(config.magnitudes if config is not None else None),
        nadir_method=(config.nadir_method if config is not None else None))
    msg = summary.get("messages", "")
    summary["messages"] = "; ".join(
        ([msg] if msg and msg != "No warnings" else []) + ["EEL: " + n for n in notes])

    stem = imp_path.stem
    csv_dir = Path(out_dir) / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    combined.to_csv(csv_dir / f"{stem}.csv", index=False)

    file_info = rf.parse_filename_info(stem, config=config)
    rf.append_to_sensor_index({**file_info, **summary, "file": stem}, out_dir)
    return combined, {**file_info, **summary}


def device_and_time(stem):
    """(device name, MMDD, hhmmss) per the spec's parsing rule, or None."""
    m = re.match(FILENAME_PATTERN, stem)
    return m.groups() if m else None
