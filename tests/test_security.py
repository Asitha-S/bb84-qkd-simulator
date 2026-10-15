"""Estimation and the security decision."""

import math
import re
from pathlib import Path

import numpy as np
import pytest

from bb84 import security
from bb84.estimation import estimate_qber, wilson_interval

PACKAGE = Path(__file__).resolve().parents[1] / "bb84"

# Textbook value (Shor & Preskill, 2000), used only as a test oracle. The
# package must derive it and never hard-code it.
LITERATURE_THRESHOLD = 0.11


def test_derived_threshold_matches_literature():
    assert security.derive_threshold() == pytest.approx(LITERATURE_THRESHOLD, abs=0.005)
    assert security.key_rate(security.derive_threshold()) == pytest.approx(0.0, abs=1e-9)


def test_threshold_literal_absent_from_package():
    pattern = re.compile(r"(?<![\d.])0?\.110*(?!\d)")
    offenders = [
        f"{p.name}:{i}"
        for p in PACKAGE.glob("*.py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []


def test_key_rate_monotonically_decreasing_on_half_interval():
    q = np.linspace(0.0, 0.5, 2001)
    r = security.key_rate(q)
    assert np.all(np.diff(r) < 0)
    assert r[0] == pytest.approx(1.0)
    assert r[-1] == pytest.approx(-1.0)


def test_binary_entropy_endpoints_no_nan():
    assert security.binary_entropy(0.0) == 0.0
    assert security.binary_entropy(1.0) == 0.0
    h = security.binary_entropy(np.array([0.0, 0.5, 1.0]))
    assert not np.isnan(h).any()
    assert h[1] == pytest.approx(1.0)


def test_abort_rule_uses_rate_formula():
    t = security.derive_threshold()
    assert not security.should_abort(t - 1e-4)
    assert security.should_abort(t + 1e-4)
    assert security.should_abort(0.25)
    assert security.final_key_length(0.25, 10_000) == 0


def test_qber_above_half_aborts():
    assert security.should_abort(0.9)
    assert security.final_key_length(0.95, 10_000) == 0


def test_final_key_length_is_floor_rate_times_n():
    q, n = 0.05, 12_345
    assert security.final_key_length(q, n) == math.floor((1 - 2 * security.binary_entropy(q)) * n)


def test_wilson_interval_nondegenerate_at_zero():
    low, high = wilson_interval(0, 2000)
    assert low == 0.0
    assert high > 0.0


def test_wilson_interval_contains_point_estimate():
    est = estimate_qber(np.zeros(1000, dtype=np.uint8), np.r_[np.ones(68), np.zeros(932)].astype(np.uint8))
    assert est.qber == pytest.approx(0.068)
    assert est.ci_low < est.qber < est.ci_high


def test_qber_above_half_unclamped_formula_would_grant_key():
    """Documents why key_rate clamps at 1/2: the raw formula is +0.43 at Q = 0.95."""
    raw = 1 - 2 * security.binary_entropy(0.95)
    assert raw == pytest.approx(0.427, abs=0.001)
    assert security.key_rate(0.95) == pytest.approx(-1.0)


def test_eve_attributable_qber_inverts_composition():
    for q_e, p in [(0.05, 0.02), (0.25, 0.03), (0.0, 0.1)]:
        q = q_e + p - 2 * q_e * p
        assert security.eve_attributable_qber(q, p) == pytest.approx(q_e)


def test_eve_attributable_qber_clamped_when_sample_below_noise():
    """Q < p (a sample that under-estimates) must give Q_E = 0, not a negative value."""
    assert (0.015 - 0.02) / (1 - 2 * 0.02) < 0
    assert security.eve_attributable_qber(0.015, 0.02) == 0.0
    r = security.oracle_key_rate(0.015, 0.02)
    assert not np.isnan(r)
    assert r == pytest.approx(1 - security.binary_entropy(0.015))


def test_oracle_rate_reduces_to_conservative_without_noise():
    q = np.linspace(0, 0.15, 31)
    assert np.allclose(security.oracle_key_rate(q, 0.0), security.key_rate(q))


def test_oracle_rate_never_below_conservative():
    q = np.linspace(0, 0.15, 31)
    assert np.all(security.oracle_key_rate(q, q / 2) >= security.key_rate(q))
