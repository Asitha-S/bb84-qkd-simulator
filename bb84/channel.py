"""Quantum channel: depolarizing noise and transmittance loss.

* **Noise.** Modelled by its effect on the protocol: the carried bit flips with
  probability ``p_noise``, independently of basis. This is the symmetric
  bit-error rate the model assumes in both bases. With no Eve, the sifted QBER
  is ``p_noise``. The swept range is 0-15%.
* **Loss.** Each qubit reaches Bob with probability ``eta`` (transmittance).
  Lost qubits never produce a detection, and Bob publicly announces which slots
  he detected, so Alice discards the same positions. Loss shortens the key; it
  does not raise QBER.

Detector effects are out of scope by design and are not modelled: dark counts,
afterpulsing, dead time and efficiency mismatch between detectors. A uniform
detector efficiency is not excluded: it multiplies the transmittance, so it is
absorbed into ``eta``.
"""

from __future__ import annotations

import numpy as np


def depolarize(
    carried_bits: np.ndarray,
    p_noise: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Flip each carried bit independently with probability ``p_noise``."""
    if not 0.0 <= p_noise <= 1.0:
        raise ValueError(f"p_noise must be in [0, 1], got {p_noise}")
    carried_bits = np.asarray(carried_bits, dtype=np.uint8)
    flips = (rng.random(len(carried_bits)) < p_noise).astype(np.uint8)
    return carried_bits ^ flips


def transmit(n: int, eta: float, rng: np.random.Generator) -> np.ndarray:
    """Return a boolean mask of the ``n`` qubits that reach Bob.

    Each qubit survives independently with probability ``eta``.
    """
    if not 0.0 <= eta <= 1.0:
        raise ValueError(f"transmittance eta must be in [0, 1], got {eta}")
    return rng.random(n) < eta
