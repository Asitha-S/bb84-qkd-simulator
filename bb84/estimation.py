"""QBER estimation from the disclosed sample: point estimate plus Wilson interval.

Why Wilson and not Wald: the Wald interval ``Q +/- z*sqrt(Q(1-Q)/n)`` has zero
width whenever the sample contains no errors (Q = 0). That is exactly the
clean-channel case this project has to demonstrate, and a zero-width interval
there would claim certainty from a finite sample. The Wilson score interval
keeps a positive upper bound at Q = 0, stays inside [0, 1], and has close to
nominal coverage at small ``n`` and extreme proportions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class QBEREstimate:
    errors: int
    sample_size: int
    qber: float
    ci_low: float
    ci_high: float
    confidence: float


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion ``k / n``."""
    if n <= 0:
        raise ValueError(f"sample size must be positive, got {n}")
    if not 0 <= k <= n:
        raise ValueError(f"error count must be in [0, n], got k={k}, n={n}")
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    z = norm.ppf(0.5 + confidence / 2.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    # The bounds are exactly 0 at k = 0 and exactly 1 at k = n; pin them against roundoff.
    low = 0.0 if k == 0 else max(0.0, float(centre - half))
    high = 1.0 if k == n else min(1.0, float(centre + half))
    return low, high


def estimate_qber(
    alice_sample: np.ndarray,
    bob_sample: np.ndarray,
    confidence: float = 0.95,
) -> QBEREstimate:
    """Point estimate ``Q = k/n`` and Wilson interval from a disclosed sample."""
    alice_sample = np.asarray(alice_sample)
    bob_sample = np.asarray(bob_sample)
    if alice_sample.shape != bob_sample.shape:
        raise ValueError("disclosed samples must have equal length")
    n = int(alice_sample.size)
    k = int(np.count_nonzero(alice_sample != bob_sample))
    low, high = wilson_interval(k, n, confidence)
    return QBEREstimate(
        errors=k,
        sample_size=n,
        qber=k / n,
        ci_low=low,
        ci_high=high,
        confidence=confidence,
    )
