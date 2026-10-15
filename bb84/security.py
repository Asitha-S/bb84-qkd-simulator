"""Security decision: binary entropy, key rate, derived threshold, abort rule.

Every reported security quantity comes from one formula:

    h(x)      = -x log2 x - (1 - x) log2(1 - x)     binary entropy, h(0) = h(1) = 0
    r(Q)      = 1 - 2 h(Q)                          secret-key fraction (Shor & Preskill, 2000)
    threshold = the Q in (0, 1/2) where r(Q) = 0    solved by bisection at runtime
    abort     = r(Q) <= 0                           the same formula, no separate constant
    final_key_length = floor(r(Q) * n)

Stated model
------------
Asymptotic regime, one-way post-processing, collective attacks, ideal
single-photon source, and the same QBER in both bases.

The two ``h(Q)`` terms in ``r(Q)`` already account for both post-processing
costs: one for the information disclosed during error correction, one for the
compression applied by privacy amplification. The parity bits actually
disclosed by :mod:`bb84.reconcile` are therefore **not** subtracted again.
Doing so would count error correction twice. Measured leakage is a diagnostic
only.

The threshold depends on these assumptions and is not a universal BB84
constant. With two-way post-processing (advantage distillation) the tolerable
QBER rises to about 18.9-20%. Finite-key effects would lower the extractable
length further. Both are out of scope here.

QBER above 1/2 (deliberate clamp)
---------------------------------
``h`` is symmetric, ``h(Q) = h(1 - Q)``, so the unclamped ``1 - 2h(Q)`` turns
positive again above ``1 - threshold`` (about Q = 0.89). It reaches +0.43 at
Q = 0.95. Evaluated naively, a disclosed sample in which nearly every bit
disagrees would be granted a key. That mirrored branch would only be valid if
Bob inverted his whole key, which this pipeline never does. :func:`key_rate`
therefore evaluates the formula at ``min(Q, 1/2)``, so any QBER at or above
1/2 gives ``r = -1`` and an abort. This is a restriction of the formula to
its domain, not a second threshold constant. The case arises in practice only
from very small or adversarial samples, and
``tests/test_security.py::test_qber_above_half_aborts`` covers it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np


def binary_entropy(x):
    """Binary entropy ``h(x)`` in bits; ``h(0) = h(1) = 0`` with no NaN.

    Accepts a scalar or an array and returns the same kind.
    """
    arr = np.asarray(x, dtype=float)
    if np.any((arr < 0.0) | (arr > 1.0)):
        raise ValueError("binary entropy is defined on [0, 1]")
    interior = (arr > 0.0) & (arr < 1.0)
    safe = np.where(interior, arr, 0.5)  # any interior value; result masked below
    h = -safe * np.log2(safe) - (1.0 - safe) * np.log2(1.0 - safe)
    out = np.where(interior, h, 0.0)
    return float(out) if out.ndim == 0 else out


def key_rate(qber):
    """Asymptotic one-way secret-key fraction ``r(Q) = 1 - 2 h(Q)``."""
    q = np.minimum(np.asarray(qber, dtype=float), 0.5)
    r = 1.0 - 2.0 * binary_entropy(q)
    return float(r) if np.ndim(r) == 0 else r


@lru_cache(maxsize=None)
def derive_threshold(tol: float = 1e-12) -> float:
    """Solve ``r(Q) = 0`` on (0, 1/2) by bisection.

    ``r(0) = 1 > 0`` and ``r(1/2) = -1 < 0``, and ``r`` is strictly decreasing
    on that interval, so the root is unique.
    """
    lo, hi = 0.0, 0.5
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if key_rate(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def should_abort(qber: float) -> bool:
    """Abort if the key rate at the estimated QBER is not positive."""
    return key_rate(qber) <= 0.0


def final_key_length(qber: float, n: int) -> int:
    """``floor(r(Q) * n)``, or 0 when the protocol aborts.

    This is the estimated final key length under the assumptions of the
    implemented model (see the module docstring).
    """
    if n < 0:
        raise ValueError(f"key length must be non-negative, got {n}")
    if should_abort(qber):
        return 0
    return math.floor(key_rate(qber) * n)


@dataclass(frozen=True)
class SecurityDecision:
    qber: float
    key_rate: float
    threshold: float
    abort: bool


def decide(qber: float) -> SecurityDecision:
    """Apply the abort rule to an estimated QBER."""
    return SecurityDecision(
        qber=qber,
        key_rate=key_rate(qber),
        threshold=derive_threshold(),
        abort=should_abort(qber),
    )


def eve_attributable_qber(qber_total, p_noise):
    """SIMULATOR-ONLY: the part of an observed QBER attributable to Eve.

    Inverts the composition rule ``Q = Q_E + p - 2 Q_E p`` to get
    ``Q_E = (Q - p) / (1 - 2p)``, clamped to ``[0, 1/2]``. The lower clamp
    matters: a sample that under-estimates the QBER can give ``Q < p``, for
    example Q = 1.5% with p = 2%. That makes ``Q_E`` negative, and ``h`` is
    undefined there.
    """
    p = np.asarray(p_noise, dtype=float)
    if np.any((p < 0.0) | (p >= 0.5)):
        raise ValueError("noise level must be in [0, 1/2) to separate it from Eve")
    q_eve = (np.asarray(qber_total, dtype=float) - p) / (1.0 - 2.0 * p)
    q_eve = np.clip(q_eve, 0.0, 0.5)
    return float(q_eve) if np.ndim(q_eve) == 0 else q_eve


def oracle_key_rate(qber_total, p_noise):
    """SIMULATOR-ONLY rate when channel noise is known and separated from Eve.

    ``r_oracle = 1 - h(Q) - h(Q_E)``, with ``Q_E`` from
    :func:`eve_attributable_qber`. Error correction still has to fix every
    observed error (``h(Q)``), but privacy amplification only removes the
    information tied to Eve-induced errors (``h(Q_E)``). With ``p = 0``,
    ``Q_E = Q`` and the conservative ``1 - 2h(Q)`` is recovered.

    This is a measurement device, not a protocol capability. It relies on the
    simulator's knowledge of the true noise level. Alice and Bob cannot
    separate noise from eavesdropping in a real deployment (Fiorini et al.,
    2024), so the protocol must use :func:`key_rate`, which attributes every
    error to Eve.
    """
    q_total = np.minimum(np.asarray(qber_total, dtype=float), 0.5)
    q_eve = eve_attributable_qber(q_total, p_noise)
    r = 1.0 - binary_entropy(q_total) - binary_entropy(q_eve)
    return float(r) if np.ndim(r) == 0 else r
