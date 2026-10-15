"""Privacy amplification by Toeplitz-matrix universal hashing.

Input: a reconciled key of length ``n``. Output: ``floor(r(Q) * n)`` bits,
where ``r(Q) = 1 - 2h(Q)`` (see :mod:`bb84.security`). The Toeplitz family is
2-universal, so the Leftover Hash Lemma with quantum side information
(Tomamichel, Schaffner, Smith & Renner, 2011) applies. The matrix is
generated from a public random seed of ``m + n - 1`` bits. The seed is public
by design, because the lemma's guarantee holds when the adversary knows the
hash function.

Precondition: Alice's and Bob's keys must be identical before hashing. Hashing
amplifies differences, so two keys that differ in one bit hash to unrelated
outputs. Mismatched input raises :class:`KeyMismatchError` instead of
producing unrelated keys silently. This is why reconciliation must come
before amplification.

The ``m x n`` matrix-vector product over GF(2) is a slice of a linear
convolution, ``y_i = sum_j t[i - j + n - 1] x_j``. It is computed by FFT and
reduced mod 2. All intermediate sums are integers at most ``n``, which float64
FFT rounding recovers exactly at these sizes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import fftconvolve

from .security import final_key_length


class KeyMismatchError(ValueError):
    """Alice's and Bob's keys differ at the input to privacy amplification."""


@dataclass(frozen=True)
class AmplificationResult:
    alice_final: np.ndarray
    bob_final: np.ndarray
    input_length: int
    output_length: int
    seed: np.ndarray


def toeplitz_seed(n: int, m: int, rng: np.random.Generator) -> np.ndarray:
    """Public random seed (``m + n - 1`` bits) defining an ``m x n`` Toeplitz matrix."""
    if m <= 0 or n <= 0:
        return np.zeros(0, dtype=np.uint8)
    return rng.integers(0, 2, size=m + n - 1, dtype=np.uint8)


def toeplitz_hash(key: np.ndarray, m: int, seed: np.ndarray) -> np.ndarray:
    """Compute ``T @ key mod 2`` for the ``m x n`` Toeplitz matrix ``T`` defined by ``seed``.

    ``T[i, j] = seed[i - j + n - 1]``: the first column is ``seed[n-1:]`` and
    the first row is ``seed[n-1::-1]``.
    """
    key = np.asarray(key, dtype=np.uint8)
    n = len(key)
    if m <= 0 or n == 0:
        return np.zeros(0, dtype=np.uint8)
    if m > n:
        raise ValueError(f"output length {m} exceeds input length {n}")
    if len(seed) != m + n - 1:
        raise ValueError(f"seed must have {m + n - 1} bits, got {len(seed)}")
    conv = fftconvolve(seed.astype(np.float64), key.astype(np.float64))
    return (np.rint(conv[n - 1 : n - 1 + m]).astype(np.int64) & 1).astype(np.uint8)


def privacy_amplify(
    alice_key: np.ndarray,
    bob_key: np.ndarray,
    qber_estimate: float,
    rng: np.random.Generator,
) -> AmplificationResult:
    """Compress identical reconciled keys to ``floor(r(Q) * n)`` bits."""
    alice_key = np.asarray(alice_key, dtype=np.uint8)
    bob_key = np.asarray(bob_key, dtype=np.uint8)
    if alice_key.shape != bob_key.shape or not np.array_equal(alice_key, bob_key):
        mismatches = (
            int(np.count_nonzero(alice_key != bob_key))
            if alice_key.shape == bob_key.shape
            else "length differs"
        )
        raise KeyMismatchError(
            "privacy amplification requires identical keys; reconciliation must "
            f"precede it (mismatched positions: {mismatches})"
        )
    n = len(alice_key)
    m = final_key_length(qber_estimate, n)
    seed = toeplitz_seed(n, m, rng)
    alice_final = toeplitz_hash(alice_key, m, seed)
    bob_final = toeplitz_hash(bob_key, m, seed)
    return AmplificationResult(alice_final, bob_final, n, m, seed)
