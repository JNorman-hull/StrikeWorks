# ///////////////////////////////////////////////////////////////
#
# StrikeWorks - data extraction, validation, processing and model
# development tool for underwater passive sensor devices.
#
# ///////////////////////////////////////////////////////////////
"""Wilson score interval for a binomial proportion - used by the BSM's
observed strike rate, Study design's planning (where `p` is a hypothesised
rate) and Model comparison.
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


def required_n(p, target_half, confidence=95, n_max=100000):
    """Smallest sample size whose Wilson interval half-width is at most
    `target_half` (0-1) for proportion `p` - the inverse question to
    `wilson_interval`: "how many sensors for ±5 percentage points?".
    None if even `n_max` can't get there. The half-width shrinks as n
    grows, so a binary search finds it."""
    if target_half <= 0:
        return None
    if wilson_interval(p, n_max, confidence)[2] > target_half:
        return None
    lo, hi = 1, n_max
    while lo < hi:
        mid = (lo + hi) // 2
        if wilson_interval(p, mid, confidence)[2] <= target_half:
            hi = mid
        else:
            lo = mid + 1
    return lo
