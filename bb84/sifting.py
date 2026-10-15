"""Sifting (public basis comparison) and selection of the disclosed sample.

Alice and Bob announce their bases (never their bits) and keep only positions
where the bases agree, which is about 50% of the detected qubits. A random
subset of ``m`` sifted positions is then disclosed to estimate the QBER. Those
positions are public after disclosure, so they are removed from the key that
continues down the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DisclosedSample:
    """A sacrificed sample and the key that remains after removing it."""

    alice_sample: np.ndarray
    bob_sample: np.ndarray
    alice_remaining: np.ndarray
    bob_remaining: np.ndarray
    sample_positions: np.ndarray


def sift(
    alice_bits: np.ndarray,
    alice_bases: np.ndarray,
    bob_bits: np.ndarray,
    bob_bases: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Keep the positions where Alice's and Bob's bases match.

    Returns ``(alice_sifted, bob_sifted)``.
    """
    alice_bases = np.asarray(alice_bases)
    bob_bases = np.asarray(bob_bases)
    if alice_bases.shape != bob_bases.shape:
        raise ValueError("Alice and Bob must have one basis per detected qubit")
    keep = alice_bases == bob_bases
    return (
        np.asarray(alice_bits, dtype=np.uint8)[keep],
        np.asarray(bob_bits, dtype=np.uint8)[keep],
    )


def disclose_sample(
    alice_sifted: np.ndarray,
    bob_sifted: np.ndarray,
    m: int,
    rng: np.random.Generator,
) -> DisclosedSample:
    """Draw ``m`` random sifted positions for QBER estimation and remove them."""
    n = len(alice_sifted)
    if len(bob_sifted) != n:
        raise ValueError("sifted keys must have equal length")
    if not 0 < m < n:
        raise ValueError(
            f"disclosed sample size m must satisfy 0 < m < sifted length ({n}), got {m}"
        )
    positions = np.sort(rng.choice(n, size=m, replace=False))
    keep = np.ones(n, dtype=bool)
    keep[positions] = False
    return DisclosedSample(
        alice_sample=alice_sifted[positions],
        bob_sample=bob_sifted[positions],
        alice_remaining=alice_sifted[keep],
        bob_remaining=bob_sifted[keep],
        sample_positions=positions,
    )
