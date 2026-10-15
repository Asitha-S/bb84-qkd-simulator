"""Alice: random bit generation, random basis choice, and encoding.

Layer 1 represents a BB84 qubit as the pair ``(bit, basis)``:

* ``basis = 0`` -> Z (rectilinear): bit 0 is |0>, bit 1 is |1>
* ``basis = 1`` -> X (diagonal):    bit 0 is |+>, bit 1 is |->

No state vectors are needed. The only physics the protocol relies on is the
measurement rule implemented in :mod:`bb84.bob`, and that rule is fully
determined by this pair.
"""

from __future__ import annotations

import numpy as np

Z_BASIS = 0
X_BASIS = 1


def random_bits(n: int, rng: np.random.Generator) -> np.ndarray:
    """Return ``n`` uniformly random bits as a ``uint8`` array."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    return rng.integers(0, 2, size=n, dtype=np.uint8)


def random_bases(n: int, rng: np.random.Generator) -> np.ndarray:
    """Return ``n`` uniformly random bases (0 = Z, 1 = X) as a ``uint8`` array."""
    return random_bits(n, rng)


def prepare(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Alice prepares ``n`` qubits.

    Returns ``(bits, bases)``. The pair at each index is the qubit Alice sends;
    these arrays also serve as her private record for sifting.
    """
    bits = random_bits(n, rng)
    bases = random_bases(n, rng)
    return bits, bases
