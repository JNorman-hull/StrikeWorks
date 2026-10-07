# EEL Tag Binary Format Specification

**Version:** 1.1.0-empirical
**Status:** Byte layout **vendor-confirmed** via the gnuplot reference ([`gnuplot-reference.md`](gnuplot-reference.md)); semantics **confirmed against the firmware source** ([`firmware-review.md`](firmware-review.md), [`data-collection-methodology.md`](data-collection-methodology.md)). Where the two disagree, the firmware is authoritative and the difference is noted.
**Validated against:** 19 deployments from 5 units, 652,190 HIG records, 850,232 IMP records (five *identifiers* from three physical instruments: `EEL-001` and `EEL-002` were renamed `EEL_001` and `EEL_002` on their cards between 2026-08-30 and 2026-09-07)
(`data/raw/20260827/` through `data/raw/20260830/`, both firmware generations)
**Last verified:** 2026-08-31

---

## 1. Scope and confidence policy

This specification describes the on-card binary format of the EEL tag as **determined from the data itself**, not as documented by the vendor. Where this document disagrees with vendor documentation, the disagreement is stated explicitly and the evidence is given — because in every case tested so far, the data was right and the documentation was wrong.

Every field carries a **confidence level**:

| Level | Meaning |
|---|---|
| `CONFIRMED` | Verified against an independent physical constraint (gravity, known duration, cross-stream agreement). Safe for publication. |
| `PLAUSIBLE` | Parses consistently with sensible range and autocorrelation, but no independent check exists yet. Publishable **with** the caveat recorded. |
| `SUSPECT` | Parses, but fails at least one physical plausibility test. Must be QC-flagged; must not be published as science without resolution. |
| `INVALID` | Demonstrably carries no independent information, or is structurally corrupt. Must never be published. |

Confidence levels are machine-readable in [`spec/eel-format.json`](../spec/eel-format.json) and enforced by the pipeline: `INVALID` fields are never written to output, and `SUSPECT` fields are written only with a QC flag of 3 or worse.

---

## 2. Deployment file set

A deployment produces up to three files sharing a base name:

```
<device-name><MMDDhhmmss>.HIG     high-rate triaxial acceleration
<device-name><MMDDhhmmss>.IMP     100 Hz IMU + environmental
<device-name><MMDD>.log           one CSV row per deployment on that date
```

**The prefix is a user-configurable device name, not a fixed string.** Two conventions are present in the reference data:

| Device name | Example file | Unit |
|---|---|---|
| `EEEEL-` | `EEEEL-0827222047.HIG` | unit 1 |
| `EEL-002` | `EEL-0020828073237.HIG` | unit 2 |

In both cases the **last 10 digits** before the extension are `MMDDhhmmss`, and everything before them is the device name. The `.log` uses the same device name followed by `MMDD` only.

> **Parsing rule.** Take the final 10 digits as the timestamp and treat the remainder as the device name. Do **not** match on a literal prefix — vendor documentation says `EEL-`, one unit writes `EEEEL-`, and another writes `EEL-002`.

The device name is the only unit identifier present anywhere in the data, and it is operator-set, so it is a convention rather than a guarantee. It does not remove the need for `instrument_serial` in the deployment metadata ([FW-007](FIRMWARE-ISSUES.md)).

> **Year is not encoded.** `MMDDhhmmss` carries month, day, hour, minute and second but **no year and no timezone**. The year survives only in an operator-chosen directory name. Recovering it is a metadata responsibility, not a parsing one — see [§7](#7-timebase-and-clock) and [`metadata-schema.md`](metadata-schema.md).

---

## 3. HIG record — high-rate accelerometer

**Record size:** 11 bytes. **Endianness:** big-endian. File size is always an exact multiple of 11 (verified: 493,988 / 832,392 / 1,254,671 bytes → 44,908 / 75,672 / 114,061 records).

| Offset | Type | Field | Confidence | Notes |
|---|---|---|---|---|
| 0 | `uint32` | `index` | `CONFIRMED` | Master-clock tick. **Not** a record counter. The stream is event-triggered. See §3.1. |
| 4 | `int16` | `ax_raw` | `CONFIRMED` | Gravity-validated |
| 6 | `int16` | `ay_raw` | `CONFIRMED` | Gravity-validated |
| 8 | `int16` | `az_raw` | `CONFIRMED` | Gravity-validated |
| 10 | `uint8` | `terminator` | `CONFIRMED` | `0x0B` in 234,641 / 234,641 records observed |

Vendor documentation types `index` as `int32`. All observed values are positive and far below 2^31, so the two readings are indistinguishable in practice; `uint32` is used here because the IMP index is documented as unsigned and the two share a clock domain (§4.2).

### 3.1 The HIG stream is event-triggered, not continuous

**This is the defining property of the instrument, and it is absent from vendor documentation.**

The HIG channel does **not** record continuously. It is armed with a **user-configured acceleration threshold** and writes only while that threshold is exceeded, plus a **pre-trigger buffer** of samples captured *before* the crossing. The index field is a free-running master-clock tick, so it preserves exactly where in real time each recorded burst belongs.

| File | Records kept | Armed window | Recorded | Duty cycle | Events |
|---|---|---|---|---|---|
| `EEEEL-0827222047.HIG` | 44,826 | 25.672 s | 8.965 s | 34.9 % | 11 |
| `EEEEL-0827222159.HIG` | 75,585 | 59.250 s | 15.117 s | 25.5 % | 21 |
| `EEEEL-0827222325.HIG` | 114,018 | 59.490 s | 22.804 s | 38.3 % | 26 |

Therefore:

```
t_seconds = index / samplerate_hz          # CORRECT
t_seconds = record_number / samplerate_hz  # WRONG - collapses the gaps between events
```

**Duty cycle is not data loss.** The 25–38 % figures above are the fraction of the armed window in which events were occurring. The instrument is working as designed; the intervals in between are periods when acceleration stayed below the trigger threshold and there was nothing worth recording.

**Independent confirmation of the trigger model.** Segment structure is not consistent with random sample loss:

- **Every segment after the first contains a large acceleration event** — peaks of 62 to 407 g, median ~200 g. Random loss would not preferentially retain high-g intervals.
- **Segment 0 is exactly 2001 samples in all three files** and its peak is only 3.4–4.3 g, far below every other segment. This is the ring buffer flushed once at record start, not a triggered event.
- **The peak sits at sample offset 100 within a segment more often than any other offset**, in all three files. That is the pre-trigger buffer: **100 samples = 20 ms at 5000 Hz**.
- Minimum segment length is ~2000 samples (0.4 s), the post-trigger window; segments extend to 9,835 samples when further triggers fire while the window is open.

### 3.2 Segment structure and the pre-trigger buffer

Each contiguous run of indices is **one triggered event**:

| File | Segments | Startup flush | Events | Event peaks | Pre-trigger |
|---|---|---|---|---|---|
| `EEEEL-0827222047.HIG` | 12 | 1 | 11 | 145.3 – 315.7 g | 100 samples (20 ms) |
| `EEEEL-0827222159.HIG` | 22 | 1 | 21 | 62.1 – 406.9 g | 100 samples (20 ms) |
| `EEEEL-0827222325.HIG` | 27 | 1 | 26 | 147.9 – 404.7 g | 100 samples (20 ms) |

#### Pre-trigger re-emission produces duplicate records

When a new trigger fires while the previous event's window is still open, the ring buffer **re-emits samples that were already written**. Those records carry an index at or below the running maximum, so the index appears to move backwards by 3–86 ticks.

**These are not corrupt.** Every re-emitted record is **byte-identical** to the record it repeats:

| File | Re-emitted records | Byte-identical | Conflicting |
|---|---|---|---|
| `EEEEL-0827222047.HIG` | 82 | **82** | 0 |
| `EEEEL-0827222159.HIG` | 87 | **87** | 0 |
| `EEEEL-0827222325.HIG` | 43 | **43** | 0 |

212 of 212 across the reference dataset. All observed backwards jumps are smaller than the 100-sample pre-trigger buffer, exactly as this mechanism predicts.

**Handling:** de-duplicate by index, keeping the first occurrence. This is lossless. The pipeline verifies that repeats really are identical and raises a **critical** error if any conflict, because a conflicting repeat would be genuine corruption rather than benign re-emission.

> **Retraction.** Versions of this document before 2026-08-28 described the gaps as dropped samples caused by SD write bandwidth, and the backwards jumps as a firmware buffer race. Both were wrong. The gaps are the intended event-trigger behaviour and the backwards jumps are benign pre-trigger re-emission. The evidence that corrected this was the vendor gnuplot reference ([`gnuplot-reference.md`](gnuplot-reference.md)) plus the segment-peak analysis above. No data was ever lost.

#### The trigger threshold is not recorded anywhere

The `.log` does not carry the configured threshold, the pre-trigger length, or the post-trigger window. Those live in a card configuration file that is not archived with the data.

This is a genuine scientific problem, tracked as [FW-010](FIRMWARE-ISSUES.md): **an event count is meaningless without the threshold that produced it.** Two deployments with 11 and 26 events are not comparable unless both were armed at the same level. The toolkit therefore bounds the threshold from the data — it must be at or below the smallest observed event peak (62.1 g in the reference set) — and flags the deployment until the true value is supplied in the deployment metadata.

**Firmware E10 (2026-09-07) supplies it.** The threshold is written into the deployment `.log` as a `Trigger` column and into the HIG header record described below, and the toolkit reads it from the record in preference to the log, because the record travels with the data. FW-010 is therefore closed for E10 deployments and remains open for everything recorded before it: an event count from an earlier file is still bounded, not known.

### The header record

Record 0 of each stream has never been a measurement, and what it holds changed with E10.

| Stream | E09 and earlier | E10 |
|---|---|---|
| `.IMP` | An all-zero record terminated `0x27` — the six-byte write past the end of `outputB` ([FW-006](FIRMWARE-ISSUES.md#fw-006), [FWR-01](firmware-review.md)). Discarded. | A well-formed 23-byte record at index 0 whose pressure field is `10000` raw — the 100.000 kPa boot datum the stream is referenced to — and whose other channels are zero. Discarded. |
| `.HIG` | Index 0 with **zero acceleration**. An accelerometer at rest reads ~1 g on some axis, so an exact (0, 0, 0) is a written zero, not a measurement; the firmware writes it in `setup()` before the first conversion. Discarded. | Index 0 whose three acceleration fields carry the deployment's configuration: `ax` = anti-alias filter in Hz (0 = disabled), `ay` = sample rate in Hz, `az` = trigger threshold in g. Discarded, and read for V-12. |

Record 0 is therefore a header in **every** build, and is never emitted in either. Until 2026-09-08 the pre-E10 one was emitted as a fabricated 0 g sample at tick 0, which is what design rule 1 forbids; removing it costs one record and one tick of index span per HIG file, and those counts are re-derived in this document's header line and in `spec/eel-format.json`.

### What the conversion writes

Because record 0 is a header, the first *data* sample of a stream does not sit at tick 0. The CSV therefore carries **two** time columns, and the difference matters:

| Column | Meaning |
|---|---|
| `tick` | The raw master-clock counter, exactly as the instrument wrote it. **Both streams count the same clock**, so a HIG row and an IMP row with the same tick are the same instant. Co-register on this column. |
| `time_s` | Seconds from the first data sample *of that stream*: `(tick - t0_tick) / samplerate`. Each stream starts at exactly `0.000000`. |

`t0_tick` is written into the CSV header block beside `header_record`, so the mapping between the two columns is recoverable from the file alone. The two streams have different first samples — HIG at tick 1, IMP at tick 50 on a 5000 Hz recording — so their `time_s` origins differ by 9.8 ms. **Subtract the tick columns, never the times**, when aligning a high-g impact against the pressure at that instant.

Both are detected **by signature, never by date**, the same rule the toolkit applies to firmware generation. The E10 HIG record matters most: decoded as acceleration it is a phantom peak of *samplerate* / 10 g — 504.1 g on a 5000 Hz file with the 640 Hz filter — which saturates `hig_max_g`, raises the saturation flag, and can be counted as a triggered event. The signature requires `ay` to equal the sample rate the `.log` declares, `ax` to be one of the firmware's filter settings and `az` to be a plausible threshold, so a genuine sample cannot meet it. Discarding record 0 also moves the first tick of the recording from 0 to 1, which the startup-flush rule allows for.

---

## 4. IMP record — IMU and environmental

**Record size:** 23 bytes. **Endianness:** big-endian. File size is always an exact multiple of 23 (all three files: 137,862 bytes → 5,994 records).

| Offset | Type | Field | Confidence | Notes |
|---|---|---|---|---|
| 0 | `uint32` | `index` | `CONFIRMED` | Master-clock tick, step = 50. See §4.2. |
| 4 | `int16` | `ax_raw` | `CONFIRMED` | Gravity-validated |
| 6 | `int16` | `ay_raw` | `CONFIRMED` | Gravity-validated |
| 8 | `int16` | `az_raw` | `CONFIRMED` | Gravity-validated. Dropout runs in one file, see FW-009 |
| 10 | `int16` | `gx_raw` | `SUSPECT` | Implausible bench noise. See §4.4. |
| 12 | `int16` | ~~`gy_raw`~~ | **`INVALID`** | **Byte-identical to offset 8. See §4.3.** |
| 14 | `int16` | `gz_raw` | `SUSPECT` | Fails autocorrelation test. See §4.4. |
| 16 | `uint16` | `pressure_raw` | `CONFIRMED` | 2 kPa offset vs log. See §4.5. |
| 18 | `int16` | `temperature_raw` | `CONFIRMED` | Smooth thermal drift, rho_1 = 0.997–0.999 |
| 20 | `int16` | `battery_raw` | `CONFIRMED` | Monotone decay, matches log to 0.01 V |
| 22 | `uint8` | `terminator` | `CONFIRMED` | `0x0B`, except record 0 (§4.1) |

### 4.1 Record 0 is a corrupt header, not data

**In all three files, record 0 is 22 zero bytes terminated with `0x27`, not `0x0B`:**

```
record 0 : 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 27
record 1 : 00 00 00 32 ff b3 08 09 00 0c ff dd 00 0c ff ff 27 0f 0a 50 01 99 0b
```

Decoded naively this yields **0 kPa, 0 °C, 0 V** at t = 0 of every file — physically impossible values that will corrupt any automatic minimum, baseline, or event detector.

**This is a bug, not a sentinel.** The firmware writes six bytes past the end of `outputB[23]` in `setup()`; the `0x27` is `highByte(10000)` landing on the terminator byte, and the intended `0x0B` is written to `outputB[28]`, outside the array ([FWR-01](firmware-review.md)). It is memory corruption whose target is build-dependent.

**Rule: record 0 of every IMP file MUST be discarded and flagged `9` (missing).** Detection is by terminator (`!= 0x0B`) plus all-zero payload, not by position, so a firmware fix will not break the parser.

### 4.2 The IMP index shares the HIG master clock

The IMP index increments by **exactly 50** at every step, never 1 — 0 → 299,650 over 5,993 steps, identical in all three files.

```
5000 Hz (HIG master) / 50 = 100 Hz (IMP rate)
299,650 ticks / 5000 Hz  = 59.93 s   <- matches HIG span and RecordTime = 1 min
```

**The IMP index is counted in HIG master-clock ticks, not IMP records.** The two streams are therefore on one common timebase and can be aligned **sample-exactly**, with no cross-correlation and no drift model:

```
t_seconds = index / samplerate_hz      # identical formula for BOTH streams
```

This is the most scientifically valuable property of the instrument, and it is undocumented. It makes the tag suitable for studies that need high-rate acceleration co-registered with pressure — e.g. relating a specific impact to the pressure nadir that caused it.

> **Open question (blocking for 2000 Hz deployments).** All test deployments used `Samplerate = 5000`. The hypothesis that the IMP step becomes 20 at 2000 Hz (preserving 100 Hz) is **untested**. Until a 2000 Hz deployment exists, the pipeline asserts `step × 100 == samplerate` and raises a hard error if violated, rather than silently producing a wrong timebase. See [`FIRMWARE-ISSUES.md`](FIRMWARE-ISSUES.md) issue **FW-005**.

### 4.3 Offset 12: a copy of `az` on gen-1 firmware, a real axis on gen-2

> **Two firmware generations are in circulation and both decode.** Generation is
> detected from the data, never assumed from a date or a filename: the fraction
> of records where bytes 12:14 equal bytes 8:10 is **1.0000** for gen-1 and
> **0.0000–0.0020** for gen-2. A file between those bands is neither, and is
> corrupt — that is the only way `V-07` fails now.
>
> | | gen-1 (to 2026-08-28) | gen-2 (from 2026-08-29) |
> |---|---|---|
> | `gy` | `INVALID`, never emitted | `CONFIRMED`, emitted |
> | `gx` / `gz` | `SUSPECT`, excluded (FW-002) | `CONFIRMED` |
> | At-rest noise | 137–222 °/s | **0.02–0.05 °/s** |
> | In-motion lag-1 | −0.019 to +0.52 | **+0.90 to +0.95** |
>
> The rest of this section describes gen-1, which is immutable and still read
> under the original rule.

The 16-bit field at offset 12, documented as gyroscope Y, is **byte-for-byte identical to the accelerometer Z field at offset 8 in 100 % of 17,979 valid records across all three files**:

```python
np.array_equal(records[:, 8:10], records[:, 12:14])   # -> True, all files
```

Its lag-1 autocorrelation matches `az` exactly (0.8326 / 0.7886 / 0.6624), as do its standard deviation, minimum and maximum, to the last digit.

**This field carries zero independent information.** It is a firmware defect ([FW-001](FIRMWARE-ISSUES.md)). Emitting it as `gy` would constitute publishing fabricated measurement data. It is therefore classified `INVALID` and **is never written to any output product**. Gyroscope Y is reported as *absent*, not as zero and not as `az`.

### 4.4 The remaining gyroscope axes are suspect

Offsets 10 and 14 are not duplicates, but they fail physical plausibility while the accelerometer in the same records reads a clean static 1 g:

| File | sigma(`gx`) raw | sigma(`gx`) at 70 mdps/LSB | rho_1(`gz`) | Verdict |
|---|---|---|---|---|
| ...222047 | 2,238 | 157 °/s | +0.518 | implausible for a resting tag |
| ...222159 | 2,902 | 203 °/s | +0.311 | implausible for a resting tag |
| ...222325 | 3,633 | 254 °/s | **−0.019** | **white noise — no physical signal** |

A gyroscope at rest should read approximately 0 °/s with noise of order 0.1 °/s. A lag-1 autocorrelation of −0.019 at 100 Hz is the signature of uncorrelated noise, not rotation. Given that offset 12 in the same block is provably corrupt, **the entire gen-1 gyroscope block (offsets 10–15) is treated as `SUSPECT`**: decoded, retained in diagnostic output, flagged `3`, and excluded from analysis-ready products.

> **Fixed in gen-2 firmware (2026-08-29).** The same measurement on the gen-2 stationary
> reference `EEL-0010829034703` gives **0.02–0.05 °/s** of noise on all three axes, and
> lag-1 in motion is **+0.90 to +0.95**. Both failure signatures are gone, and the block is
> `CONFIRMED` and emitted for gen-2 files. The table above is a record of gen-1 behaviour,
> which is immutable and still decodes under that rule.
>
> Two limits survive the fix: the scale factor is nominal (70 mdps/LSB) and not traceable
> without a rate table, and the channel **saturates at ±2000 °/s**, which real impacts
> reach — see [calibration-protocol.md §4.5](calibration-protocol.md).

### 4.5 Pressure is relative to a 100.000 kPa datum set at boot

**This is a designed baseline subtraction, not the discrepancy earlier revisions reported.**

On a battery boot, before recording starts, the firmware averages 100 pressure conversions and stores that mean as a datum. Every subsequent sample is written as

```
stored = (P_measured − P_boot_mean + 100000 + 5) / 10        # 0.01 kPa per LSB
```

So the stream is **head relative to the boot ambient, offset to 100.000 kPa** — a tag sitting still at boot reads exactly 100.00 kPa by design. The `.log` `Pressure` column carries the true absolute ambient. Both are correct; they measure different things.

| Deployment | Unit | `.log` (absolute) | Stream at start | Residual vs datum |
|---|---|---|---|---|
| EEEEL-0827222047 | 1 | 102.000 kPa | 99.960 kPa | −0.040 |
| EEEEL-0827222159 | 1 | 102.000 kPa | 100.000 kPa | +0.000 |
| EEEEL-0827222325 | 1 | 102.000 kPa | 99.990 kPa | −0.010 |
| EEL-0020828073237 | **2** | 102.000 kPa | 99.990 kPa | −0.010 |
| EEL-0020828073349 | **2** | 102.000 kPa | 100.000 kPa | +0.000 |

Five deployments on two units all start within **0.04 kPa of exactly 100.000**. Check `V-12b` asserts this.

**Consequences for analysis:**

- **Differential head** — what barotrauma work needs — is already correct in the stream, with no correction: `stream − 100.000` is the change in head since boot.
- **Absolute pressure** = `stream + (log Pressure − 100.000)`. Both files are needed; neither alone is sufficient.
- The log field is integer-truncated to whole mbar ([FWR-13](firmware-review.md)), which puts a floor of **±0.05 kPa (≈ 5 mm of water)** on any absolute reconstruction. That truncation is also why earlier revisions read the field as a stored constant — it moves, one mbar at a time.
- **The tag must be booted on land.** If it boots submerged, the datum silently becomes that depth and every later reading is relative to it. This is a field-protocol requirement, on the [field sheet](field-sheet.md).
- The re-zero is skipped on USB power, so the serial console reports absolute pressure. The two paths are not comparable.

In-band noise is excellent: sigma = 0.017–0.021 kPa, approximately **2 mm H2O**, quantisation-limited at 0.01 kPa LSB.

> **Over-range wraps to zero.** The firmware clamps with `constrain(P, 0, 65536)`, and 65536 does not fit a `uint16_t` — it becomes 0. Anything above **655.36 kPa (≈ 55 m of water)** is stored as `0.00 kPa` rather than clipped at full scale ([FWR-08](firmware-review.md)). Check `V-13` flags any raw zero as an artefact rather than a measurement.

---

## 5. Deployment `.log` file

Comma-separated, CRLF line endings, one header row, one row per deployment:

```
Filename,Time,RecordTime,Pressure,Temp,BatVoltage,Filter,Samplerate,End
EEEEL-0827222047,22:20,1,1020.00,26.00,4.08,0,5000,Time
```

| Column | Meaning | Confidence |
|---|---|---|
| `Filename` | Deployment base name; joins to `.HIG`/`.IMP` | `CONFIRMED` |
| `Time` | Start time, **`hh:mm` only — no date, no seconds, no timezone** | `CONFIRMED` |
| `RecordTime` | Requested duration in **minutes**. Written from an **uninitialised variable** when `config.txt` is absent ([FWR-09](firmware-review.md)), so a plausible-looking value may be meaningless | `PLAUSIBLE` |
| `Pressure` | Pre-deployment pressure, **kPa**. The logger writes this column with a 0.1 hPa LSB; the toolkit converts it on read, and kPa is the reference unit everywhere. Disagrees with the stream by 2 kPa (§4.5) | `SUSPECT` |
| `Temp` | Pre-deployment temperature, °C | `PLAUSIBLE` |
| `BatVoltage` | Pre-deployment battery, V. Matches stream to 0.01 V | `CONFIRMED` |
| `Filter` | **A literal `0`, always.** The firmware never writes anything else, so the column carries no information. The anti-alias bandwidth it ought to record is fixed at 2560 Hz regardless of sample rate ([FWR-14](firmware-review.md)) | `CONFIRMED` |
| `Samplerate` | HIG rate in Hz. **`2000`, `2500` or `5000`**; anything else defaults to 2000. Only 5000 appears in the reference data | `CONFIRMED` |
| `End` | Stop reason: `User` (button), `Bat` (below 3.3 V) or `Time` (duration elapsed). **A truncated row means the tag lost power** — a stronger integrity signal than anything else in the log | `CONFIRMED` |

**The log is a superset of the data.** The reference log lists 10 deployments while only 3 file pairs exist on the card. Parsers must tolerate log rows with no data, and data with no log row — the latter is fatal for HIG, which has no usable timebase without `Samplerate`.

---

## 6. Scaling to engineering units

The factors below are the **vendor-documented** values, with corrections where the data or the underlying MEMS part contradicts them. A per-unit calibration file is **specified but not yet implemented**: the schema and the protocol exist, no loader does, so these factors are what every product currently uses and `calibration_id_applied` is always `null`.

| Field | Vendor factor | **Applied factor** | Unit | Rationale |
|---|---|---|---|---|
| `ax/ay/az` (HIG) | `/10` | `/10` | g | Gravity-validated: mean `ay` = 0.918 g vs IMP 0.931 g. **Already offset-corrected in firmware** against the IMU at boot — see [calibration §5.0](calibration-protocol.md) |
| `ax/ay/az` (IMP) | `/2048` | `/2048` | g | 2048 LSB/g = ±16 g over int16 |
| `gx/gz` (IMP) | `/16` | **`× 0.070`** | °/s | Settled by the firmware source: the part is an **ST LSM6DSOTR at ±2000 dps**, and ST specifies **70 mdps/LSB** directly rather than mapping full scale onto 32768. The firmware and the vendor gnuplot both use 62.5 mdps (`/16`), which is **10.7 % low** ([FWR-05](firmware-review.md)). The earlier 16.384 estimate came from the InvenSense convention and does not apply to this part. Excluded from gen-1 products on plausibility grounds; **emitted for gen-2**, where [FW-002](FIRMWARE-ISSUES.md) is fixed. |
| `gy` | `/16` | **`× 0.070`** (gen-2) / not emitted (gen-1) | °/s | `INVALID` on gen-1, a real axis on gen-2 (§4.3) |
| `pressure` | `/10` | **`/100`** | kPa | Raw LSB is 0.01 kPa. **kPa is the reference unit for every product.** The result is **head relative to a 100.000 kPa datum set at boot**, not absolute pressure — see §4.5. |
| `temperature` | `/100` | `/100` | °C | Log-validated: 26.40 °C stream vs 26.00 °C log |
| `battery` | `/100` | `/100` | V | Log-validated to 0.01 V |

Applying vendor scaling *alone* is **not calibration**. It is a nominal unit conversion that still contains these measured errors:

- Low-g accelerometer reads **|a| = 1.0186 g** over a genuinely quiescent window
  (sigma = 0.0009 g, `EEL-0020828073349.IMP`) → a firmly measured **1.9 % scale error**
- The X axes carry a **1 LSB offset** — 0.49 mg on the accelerometer, 0.07 °/s on the
  gyroscope — because the firmware negates with `~` (which is −x−1) where it means −x
  ([FWR-07](firmware-review.md)). Systematic, and below every other error here.
- HIG shows a **−0.15 g zero-offset** on X and Z absent from the IMP accelerometer
- Pressure carries a **2 kPa** systematic offset

These are removed by the per-unit calibration in [`calibration-protocol.md`](calibration-protocol.md).

---

## 7. Timebase and clock

### 7.1 Within a deployment

Both streams: `t_seconds = index / samplerate_hz`, relative to logger start. Shared clock domain gives sample-exact cross-stream alignment (§4.2).

### 7.2 Absolute time — currently unreliable

Converting to absolute UTC requires all of:

| Component | Source | Status |
|---|---|---|
| Year | Directory name, operator convention | **not in any file** |
| Month, day | Filename `MMDD` | available |
| Hour, min, sec | Filename `hhmmss` | available |
| Timezone | — | **not recorded anywhere** |
| RTC offset vs UTC | — | **never measured** |
| RTC drift rate | — | **never characterised** |

Absolute timestamps are therefore **`SUSPECT` by construction** — currently good to roughly ±1 minute at best, with an unbounded systematic error from uncharacterised RTC drift. The remedy is procedural, not computational: see [`calibration-protocol.md` §6](calibration-protocol.md) and [`metadata-schema.md`](metadata-schema.md).

---

## 8. Validation suite

The pipeline runs these checks on every file. Failures become QC flags ([`qc-flags.md`](qc-flags.md)) — never silent corrections.

| ID | Check | On failure |
|---|---|---|
| `V-01` | File size is an exact multiple of the record size | Truncate to whole records, flag `3`, report residual bytes |
| `V-02` | Every terminator is `0x0B` | Flag offending record `4` |
| `V-03` | IMP record 0 is the zero/`0x27` header | Discard, flag `9`. **Absence is also reported** — firmware may have been fixed |
| `V-04` | HIG re-emitted records are byte-identical repeats | De-duplicate by index (lossless). **Critical error** if a repeat conflicts - that would be real corruption |
| `V-05` | IMP index step is constant and equals `samplerate/100` | **Hard error** — refuse to guess a timebase |
| `V-06` | `Samplerate` present in `.log` for every HIG file | **Hard error** — HIG has no usable timebase without it |
| `V-07` | Duplicated fraction is ~1 (gen-1) or ~0 (gen-2) | Detects which firmware wrote the file. Fails only on a *partly* duplicated file, which is neither generation and is corrupt |
| `V-08` | Static `norm(a)` within 0.9–1.1 g over any 10 s quiescent window | Flag `3`, recommend recalibration |
| `V-09` | Event-trigger structure is coherent | Report event count, duty cycle, pre-trigger length |
| `V-10` | Battery decreases monotonically within a deployment | Flag `3` |
| `V-11` | No run of >= 0.5 s with `norm(a)` < 0.3 g | Flag `3` `ACCEL_DROPOUT` — sensor fault, not free fall ([FW-009](FIRMWARE-ISSUES.md)) |
| `V-12` | Trigger threshold is present in deployment metadata | Flag `3` — event counts are not comparable without it ([FW-010](FIRMWARE-ISSUES.md)). Satisfied from the E10 HIG header record, or from the `.log`'s `Trigger` column |
| `V-14` | HIG record 0 is the E10 metadata header, not a sample | Reports its absence — the file is from E09 or earlier. Where present it is discarded and supplies `V-12` |
| `V-12b` | Stream starts at the 100.000 kPa boot datum | Flag `3` — the tag was not at the boot ambient when recording began (§4.5) |
| `V-13` | No pressure sample reads exactly zero | Flag `4` `PRESSURE_WRAPPED` — over-range wrap, not a measurement ([FWR-08](firmware-review.md)) |

> `V-07` **was** deliberately inverted: it asserted that a **known bug is still present**, which is how the toolkit detects a silent firmware change underneath it — the most dangerous failure mode for a reverse-engineered format.
>
> **It worked.** On 2026-08-29 the firmware was fixed, `V-07` failed on all three new files, and the specification was re-validated deliberately instead of drifting. It is now a *generation detector*: both generations must keep decoding, because raw data is immutable and the gen-1 deployments are permanent records. The inverted-assertion pattern is retained elsewhere — `V-03` still reports the *absence* of the zero header record, for the same reason.

---

## 9. Reproducing this specification

```bash
python tools/verify_format.py data/raw/20260827
```

Regenerates every number in this document from the raw binaries and fails loudly on disagreement. The specification and the data are not allowed to drift apart.
