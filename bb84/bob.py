"""Bob: random measurement-basis choice and the BB84 measurement rule.

The measurement rule (also used by Eve):

* measuring in the basis the qubit currently carries recovers its bit
  deterministically;
* measuring in the other basis yields a uniformly random bit.
"""

from __future__ import annotations

import numpy as np

from .alice import random_bases


def measure(
    carried_bits: np.ndarray,
    carried_bases: np.ndarray,
    measurement_bases: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Measure qubits ``(carried_bits, carried_bases)`` in ``measurement_bases``.

    A random bit is drawn for every position (so the number of random draws
    does not depend on the data) and used only where the bases differ.
    """
    carried_bits = np.asarray(carried_bits, dtype=np.uint8)
    carried_bases = np.asarray(carried_bases, dtype=np.uint8)
    measurement_bases = np.asarray(measurement_bases, dtype=np.uint8)
    if not (carried_bits.shape == carried_bases.shape == measurement_bases.shape):
        raise ValueError("bit, basis and measurement-basis arrays must have equal shape")

    random_outcomes = rng.integers(0, 2, size=carried_bits.shape, dtype=np.uint8)
    match = carried_bases == measurement_bases
    return np.where(match, carried_bits, random_outcomes).astype(np.uint8)


def receive(
    carried_bits: np.ndarray,
    carried_bases: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Bob picks a random basis for each arriving qubit and measures it.

    Returns ``(bob_bits, bob_bases)``.
    """
    bob_bases = random_bases(len(carried_bits), rng)
    bob_bits = measure(carried_bits, carried_bases, bob_bases, rng)
    return bob_bits, bob_bases
