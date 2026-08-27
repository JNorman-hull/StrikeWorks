# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Wilson score interval for a binomial proportion.

Same formula the old MVP app uses to bound its observed strike/contact
probability (`bsm/core/model.py`'s `wilson_lo`/`wilson_hi`, inside the full
CEN 2025 geometric model), lifted out here as a small standalone function -
Setup and deploy > Study design uses it for sample-size *planning* rather
than analysing an already-collected passage: `p` there is a hypothesised
strike rate rather than an observed one, but the interval math is the same
either way, so the caller decides what `p` means.
"""
import math

# two-sided z for common confidence levels
Z_FOR_CONFIDENCE = {90: 1.6448536269514722, 95: 1.959963984540054,
                    99: 2.5758293035489004}


def wilson_interval(p, n, confidence=95):
    """(lo, hi, half_width) for proportion `p` (0-1) from `n` trials, or
    None if `n` <= 0. `half_width` is the precision a study with this `n`
    and `p` would achieve - the number to eyeball when choosing effort."""
    if n <= 0:
        return None
    p = min(1.0, max(0.0, p))
    z = Z_FOR_CONFIDENCE.get(confidence, Z_FOR_CONFIDENCE[95])
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    return lo, hi, (hi - lo) / 2
