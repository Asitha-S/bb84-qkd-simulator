"""Quantum stage: Alice, Bob, Eve, channel, sifting (checkpoints 1 and 2)."""

import numpy as np
import pytest

from bb84 import alice, bob, eve, sifting
from bb84.runner import composed_qber, make_rng, run_quantum_stage


def _qber(stage):
    return float(np.mean(stage.alice_sifted != stage.bob_sifted))


def test_checkpoint1_clean_channel_identical_keys():
    """Checkpoint 1: no Eve, no noise, 256 qubits: byte-identical sifted keys."""
    rng = np.random.default_rng(42)
    a_bits, a_bases = alice.prepare(256, rng)
    b_bits, b_bases = bob.receive(a_bits, a_bases, rng)
    a_key, b_key = sifting.sift(a_bits, a_bases, b_bits, b_bases)
    assert a_key.tobytes() == b_key.tobytes()
    assert np.count_nonzero(a_key != b_key) == 0
    assert 0.40 <= len(a_key) / 256 <= 0.60


def test_clean_channel_large_sifted_fraction():
    stage = run_quantum_stage(50_000, 0.0, 0.0, 1.0, make_rng(42))
    assert _qber(stage) == 0.0
    assert len(stage.alice_sifted) / 50_000 == pytest.approx(0.5, abs=0.01)


@pytest.mark.parametrize("f, expected", [(1.0, 0.25), (0.5, 0.125), (0.2, 0.05)])
def test_intercept_resend_qber_matches_f_over_4(f, expected):
    """Checkpoint 2 (f = 1) and the other theory points: Q = f / 4."""
    stage = run_quantum_stage(50_000, f, 0.0, 1.0, make_rng(42, int(f * 100)))
    assert _qber(stage) == pytest.approx(expected, abs=0.01)


def test_eve_reprepares_in_her_own_basis():
    """Intercepted qubits must carry Eve's basis and measured bit."""
    rng = np.random.default_rng(1)
    bits, bases = alice.prepare(10_000, rng)
    fwd_bits, fwd_bases, intercepted = eve.intercept_resend(bits, bases, 1.0, rng)
    assert intercepted.all()
    wrong_basis = fwd_bases != bases
    assert 0.45 < wrong_basis.mean() < 0.55
    untouched_bits, untouched_bases, none = eve.intercept_resend(bits, bases, 0.0, rng)
    assert not none.any()
    assert np.array_equal(untouched_bits, bits) and np.array_equal(untouched_bases, bases)


def test_bob_measurement_rule():
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 20_000, dtype=np.uint8)
    bases = rng.integers(0, 2, 20_000, dtype=np.uint8)
    same = bob.measure(bits, bases, bases, rng)
    assert np.array_equal(same, bits)
    other = bob.measure(bits, bases, 1 - bases, rng)
    assert np.mean(other != bits) == pytest.approx(0.5, abs=0.02)


def test_noise_alone_gives_qber_p():
    stage = run_quantum_stage(50_000, 0.0, 0.05, 1.0, make_rng(42, 5))
    assert _qber(stage) == pytest.approx(0.05, abs=0.01)


def test_errors_compose_not_add():
    """Q = Q_E + Q_N - 2 Q_E Q_N: 25% + 3% gives 26.5%, not 28%."""
    assert composed_qber(0.25, 0.03) == pytest.approx(0.265)
    stage = run_quantum_stage(200_000, 1.0, 0.03, 1.0, make_rng(42, 6))
    assert _qber(stage) == pytest.approx(0.265, abs=0.005)


def test_loss_halves_sifted_length_but_not_qber():
    full = run_quantum_stage(100_000, 0.0, 0.05, 1.0, make_rng(42, 7))
    lossy = run_quantum_stage(100_000, 0.0, 0.05, 0.5, make_rng(42, 8))
    assert len(lossy.alice_sifted) / len(full.alice_sifted) == pytest.approx(0.5, abs=0.02)
    assert _qber(lossy) == pytest.approx(_qber(full), abs=0.01)


def test_disclosed_sample_removed_from_key():
    rng = np.random.default_rng(4)
    a = rng.integers(0, 2, 1000, dtype=np.uint8)
    s = sifting.disclose_sample(a, a.copy(), 200, rng)
    assert len(s.alice_sample) == 200
    assert len(s.alice_remaining) == 800
    with pytest.raises(ValueError):
        sifting.disclose_sample(a, a, 1000, rng)
