"""End-to-end pipeline, reproducibility and layer separation."""

import subprocess
import sys
from pathlib import Path

import numpy as np

from bb84 import runner
from bb84.runner import PipelineConfig, format_report, run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def test_success_case_extracts_identical_key():
    res = run_pipeline(PipelineConfig())
    assert res.status == runner.STATUS_EXTRACTED
    assert res.estimate.qber == 0.0
    assert res.final_key_length > 0
    assert np.array_equal(res.amplification.alice_final, res.amplification.bob_final)
    assert "✓ Key extraction permitted" in format_report(res)


def test_full_intercept_aborts():
    res = run_pipeline(PipelineConfig(f_eve=1.0))
    assert res.status == runner.STATUS_ABORT
    assert res.final_key_length == 0
    assert res.reconciliation is None
    assert "ABORT" in format_report(res)


def test_realistic_noise_with_partial_eve_extracts_key():
    res = run_pipeline(PipelineConfig(p_noise=0.02, f_eve=0.2))
    assert res.status == runner.STATUS_EXTRACTED
    assert res.reconciliation.confirmed
    assert res.final_key_length > 0


def test_report_wording_never_says_secure_key_unqualified():
    for cfg in (PipelineConfig(), PipelineConfig(f_eve=1.0)):
        text = format_report(run_pipeline(cfg)).lower()
        assert "secure key" not in text
        assert "under the assumptions of the implemented model" in text


def test_fixed_seed_reproducible():
    cfg = PipelineConfig(p_noise=0.03, f_eve=0.1, seed=7)
    a, b = run_pipeline(cfg), run_pipeline(cfg)
    assert format_report(a) == format_report(b)
    assert a.amplification.alice_final.tobytes() == b.amplification.alice_final.tobytes()
    assert a.amplification.seed.tobytes() == b.amplification.seed.tobytes()


def test_experiments_reproducible():
    kw = dict(trials=3, sifted_bits=2000, seed=42)
    e1, e2 = runner.experiment_qber_vs_eve(**kw), runner.experiment_qber_vs_eve(**kw)
    for k in e1:
        assert np.array_equal(e1[k], e2[k])
    other = runner.experiment_qber_vs_eve(trials=3, sifted_bits=2000, seed=43)
    assert not np.array_equal(e1["qber_mean"], other["qber_mean"])


def test_layer1_does_not_import_qiskit():
    code = (
        "import sys; import bb84.runner, bb84.plots, bb84.__main__; "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('qiskit', 'qiskit_aer')); "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    layer1 = [p for p in (ROOT / "bb84").glob("*.py") if p.name != "qiskit_demo.py"]
    assert not [p.name for p in layer1 if "qiskit" in p.read_text(encoding="utf-8").replace(
        "qiskit_demo", "")]
