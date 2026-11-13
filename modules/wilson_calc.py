"""Wilson score interval for a binomial proportion - the one interval every
count in the app is given with: the BSM's observed strike rate, Study
design's planning (where `p` is a hypothesised rate), Model comparison, the
prediction summary, HIG peak analysis and the training metrics.

No Qt and no package imports: the workers import it too.
"""
import math

# two-sided z; 95 % is 1.96 everywhere in the app
Z_FOR_CONFIDENCE = {90: 1.6448536269514722, 95: 1.96,
                    99: 2.5758293035489004}


def _limits(p, n, z):
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson_interval(p, n, confidence=95):
    """(lo, hi, half_width) for proportion `p` (0-1) from `n` trials, or
    None if `n` <= 0. `half_width` is the precision a study with this `n`
    and `p` would achieve - the number to eyeball when choosing effort."""
    if n <= 0:
        return None
    p = min(1.0, max(0.0, p))
    z = Z_FOR_CONFIDENCE.get(confidence, Z_FOR_CONFIDENCE[95])
    lo, hi = _limits(p, n, z)
    return lo, hi, (hi - lo) / 2


def wilson_ci(k, n):
    """(proportion, lower, upper) at 95 % for `k` of `n`; zeros when `n`
    is 0."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    lo, hi = _limits(p, n, Z_FOR_CONFIDENCE[95])
    return p, lo, hi


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
