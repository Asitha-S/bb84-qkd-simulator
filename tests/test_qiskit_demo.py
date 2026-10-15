"""Layer 2 smoke tests (skipped if Qiskit is not installed)."""

import numpy as np
import pytest

pytest.importorskip("qiskit")
pytest.importorskip("qiskit_aer")

from bb84.qiskit_demo import run_rounds  # noqa: E402


def test_circuit_rounds_without_eve_agree_on_sifted_key():
    r = run_rounds(64, seed=42, with_eve=False)
    match = r.alice_bases == r.bob_bases
    assert np.array_equal(r.alice_bits[match], r.bob_bits[match])


def test_circuit_rounds_with_eve_disturb_the_key():
    r = run_rounds(400, seed=42, with_eve=True)
    match = r.alice_bases == r.bob_bases
    qber = np.mean(r.alice_bits[match] != r.bob_bits[match])
    assert 0.15 < qber < 0.35
