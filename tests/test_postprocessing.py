"""Reconciliation and privacy amplification."""

import math

import numpy as np
import pytest
from scipy.linalg import toeplitz

from bb84.amplify import KeyMismatchError, privacy_amplify, toeplitz_hash, toeplitz_seed
from bb84.reconcile import reconcile
from bb84.security import binary_entropy, final_key_length


def _noisy_pair(n, q, seed):
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 2, n, dtype=np.uint8)
    b = a ^ (rng.random(n) < q).astype(np.uint8)
    return a, b, rng


@pytest.mark.parametrize("q", [0.01, 0.05, 0.10])
def test_reconciliation_confirms_and_reports(q):
    a, b, rng = _noisy_pair(18_000, q, 7)
    r = reconcile(a, b, q, rng)
    assert r.leakage_bits > 0
    assert r.errors_before > 0
    assert r.confirmed
    assert r.residual_error_rate == 0.0
    assert r.residual_error_bound == 2.0 ** -20
    assert r.efficiency is not None and r.efficiency > 1.0
    assert np.array_equal(r.bob_corrected, a)


def test_detect_only_confirmation_fails_at_realistic_qber():
    """Block passes alone leave hidden error pairs (the README comparison)."""
    a, b, rng = _noisy_pair(18_000, 0.05, 8)
    r = reconcile(a, b, 0.05, rng, correcting_confirmation=False)
    assert not r.confirmed
    assert r.residual_error_bound is None
    assert r.residual_errors > 0


def test_leakage_counts_every_disclosed_parity():
    a, b, rng = _noisy_pair(4_000, 0.03, 9)
    r = reconcile(a, b, 0.03, rng)
    block_bits = sum(p.leaked_bits for p in r.passes)
    assert r.leakage_bits > block_bits  # confirmation checks are counted too
    assert r.leakage_bits >= block_bits + r.confirmation_checks


def test_efficiency_uses_realised_error_rate_not_estimate():
    """Same keys, different estimates: the denominator is h(realised e), not h(Q_hat)."""
    a, b, _ = _noisy_pair(18_000, 0.02, 11)
    e = np.count_nonzero(a != b) / 18_000
    for q_hat in (0.018, 0.02, 0.023):
        r = reconcile(a, b, q_hat, np.random.default_rng(12))
        assert r.efficiency == pytest.approx(r.leakage_bits / (binary_entropy(e) * 18_000))


def test_clean_key_needs_no_correction():
    a = np.random.default_rng(1).integers(0, 2, 5000, dtype=np.uint8)
    r = reconcile(a, a.copy(), 0.0, np.random.default_rng(2))
    assert r.confirmed and r.errors_before == 0 and r.confirmation_corrections == 0
    assert r.efficiency is None


def test_privacy_amplification_raises_on_mismatched_keys():
    a = np.random.default_rng(3).integers(0, 2, 1000, dtype=np.uint8)
    b = a.copy()
    b[17] ^= 1
    with pytest.raises(KeyMismatchError):
        privacy_amplify(a, b, 0.02, np.random.default_rng(4))


def test_privacy_amplification_output_length_and_agreement():
    a = np.random.default_rng(5).integers(0, 2, 10_000, dtype=np.uint8)
    res = privacy_amplify(a, a.copy(), 0.03, np.random.default_rng(6))
    assert res.output_length == math.floor((1 - 2 * binary_entropy(0.03)) * 10_000)
    assert len(res.alice_final) == res.output_length
    assert np.array_equal(res.alice_final, res.bob_final)


def test_toeplitz_fft_matches_explicit_matrix():
    rng = np.random.default_rng(7)
    n, m = 300, 120
    key = rng.integers(0, 2, n, dtype=np.uint8)
    seed = toeplitz_seed(n, m, rng)
    T = toeplitz(seed[n - 1 :], seed[n - 1 :: -1])
    assert T.shape == (m, n)
    expected = (T.astype(np.int64) @ key.astype(np.int64)) % 2
    assert np.array_equal(toeplitz_hash(key, m, seed), expected.astype(np.uint8))


def test_leakage_not_subtracted_from_final_key():
    a, b, rng = _noisy_pair(18_000, 0.05, 10)
    rec = reconcile(a, b, 0.05, rng)
    amp = privacy_amplify(a, rec.bob_corrected, 0.05, rng)
    assert amp.output_length == final_key_length(0.05, 18_000)
    assert amp.output_length > final_key_length(0.05, 18_000) - rec.leakage_bits
