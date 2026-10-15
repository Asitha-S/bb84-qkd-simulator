"""Eve: fractional intercept-resend attack.

Each qubit is intercepted independently with probability ``f``. For an
intercepted qubit Eve picks a random basis, measures with the same rule as Bob
(:func:`bb84.bob.measure`), and then **re-prepares** the qubit as
``(her_measured_bit, her_basis)`` before forwarding it. Non-intercepted qubits
pass through untouched.

The re-preparation is what disturbs the channel. When Eve's basis matches
Alice's, she forwards the correct state. When it does not (probability 1/2),
she forwards a state in the wrong basis, and Bob's sifted bit is then random
(wrong with probability 1/2). The expected QBER is therefore

    Q = f * 1/2 * 1/2 = f / 4.
"""

from __future__ import annotations

import numpy as np

from .alice import random_bases
from .bob import measure


def intercept_resend(
    carried_bits: np.ndarray,
    carried_bases: np.ndarray,
    f: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply intercept-resend with interception probability ``f``.

    Returns ``(forwarded_bits, forwarded_bases, intercepted_mask)``. The
    forwarded qubits are what continues down the channel to Bob.
    """
    if not 0.0 <= f <= 1.0:
        raise ValueError(f"interception probability f must be in [0, 1], got {f}")
    carried_bits = np.asarray(carried_bits, dtype=np.uint8)
    carried_bases = np.asarray(carried_bases, dtype=np.uint8)
    n = len(carried_bits)

    intercepted = rng.random(n) < f
    eve_bases = random_bases(n, rng)
    eve_bits = measure(carried_bits, carried_bases, eve_bases, rng)

    # Re-preparation: an intercepted qubit now carries Eve's bit in Eve's basis.
    forwarded_bits = np.where(intercepted, eve_bits, carried_bits).astype(np.uint8)
    forwarded_bases = np.where(intercepted, eve_bases, carried_bases).astype(np.uint8)
    return forwarded_bits, forwarded_bases, intercepted
