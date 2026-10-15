"""End-to-end pipeline, parameter sweeps and batch trials.

Every function takes a ``seed`` (default 42). Random streams are derived as
``np.random.default_rng([seed, *keys])``, so each experiment, sweep point and
trial has its own independent but reproducible stream. Two runs with the same
seed produce identical output.

Reported key lengths are estimated final key lengths under the assumptions of
the implemented model (see :mod:`bb84.security`).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import alice, bob, channel, eve, sifting
from .amplify import AmplificationResult, privacy_amplify
from .estimation import QBEREstimate, estimate_qber
from .reconcile import (
    DEFAULT_CONFIRMATION_STREAK,
    DEFAULT_PASSES,
    ReconciliationResult,
    reconcile,
)
from .security import (
    SecurityDecision,
    decide,
    derive_threshold,
    final_key_length,
    oracle_key_rate,
)

DEFAULT_SEED = 42

STATUS_EXTRACTED = "extracted"
STATUS_ABORT = "abort"
STATUS_RECONCILIATION_INCOMPLETE = "reconciliation_incomplete"

MODEL_ASSUMPTIONS = (
    "asymptotic regime, one-way post-processing, collective attacks, "
    "ideal single-photon source, symmetric QBER in both bases"
)


def make_rng(seed: int, *keys: int) -> np.random.Generator:
    """Independent, reproducible stream for ``(seed, *keys)``."""
    return np.random.default_rng([seed, *keys])


# --------------------------------------------------------------------------
# Quantum stage: Alice -> Eve -> channel -> Bob -> sifting
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class QuantumStage:
    raw_qubits: int
    received_qubits: int
    alice_sifted: np.ndarray
    bob_sifted: np.ndarray


def run_quantum_stage(
    n_qubits: int,
    f_eve: float,
    p_noise: float,
    eta: float,
    rng: np.random.Generator,
) -> QuantumStage:
    """Prepare, (optionally) intercept, transmit, measure and sift."""
    a_bits, a_bases = alice.prepare(n_qubits, rng)
    bits, bases, _ = eve.intercept_resend(a_bits, a_bases, f_eve, rng)
    bits = channel.depolarize(bits, p_noise, rng)
    received = channel.transmit(n_qubits, eta, rng)
    # Bob announces which slots produced a detection; both sides keep only those.
    b_bits, b_bases = bob.receive(bits[received], bases[received], rng)
    a_key, b_key = sifting.sift(a_bits[received], a_bases[received], b_bits, b_bases)
    return QuantumStage(n_qubits, int(received.sum()), a_key, b_key)


def simulate_sifted_qber(
    sifted_bits: int,
    f_eve: float,
    p_noise: float,
    rng: np.random.Generator,
    eta: float = 1.0,
) -> float:
    """Simulator-level QBER over exactly ``sifted_bits`` sifted positions."""
    # Sifting keeps ~eta/2 of the raw stream; 2.2x headroom makes a shortfall
    # (more than 10 standard deviations at these sizes) effectively impossible.
    n_raw = math.ceil(2.2 * sifted_bits / eta)
    stage = run_quantum_stage(n_raw, f_eve, p_noise, eta, rng)
    if len(stage.alice_sifted) < sifted_bits:
        raise RuntimeError("sifted key shorter than requested; increase headroom")
    a = stage.alice_sifted[:sifted_bits]
    b = stage.bob_sifted[:sifted_bits]
    return float(np.count_nonzero(a != b)) / sifted_bits


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineConfig:
    n_qubits: int = 40_000
    f_eve: float = 0.0
    p_noise: float = 0.0
    eta: float = 1.0
    sample_size: int = 2000
    confidence: float = 0.95
    passes: int = DEFAULT_PASSES
    confirmation_streak: int = DEFAULT_CONFIRMATION_STREAK
    seed: int = DEFAULT_SEED


@dataclass
class PipelineResult:
    config: PipelineConfig
    raw_qubits: int
    received_qubits: int
    sifted_length: int
    true_sifted_qber: float  # simulator-side diagnostic, unknown to Alice and Bob
    estimate: QBEREstimate
    decision: SecurityDecision
    key_length_after_sample: int
    reconciliation: ReconciliationResult | None = None
    amplification: AmplificationResult | None = None
    status: str = STATUS_ABORT
    final_key_length: int = 0


def run_pipeline(config: PipelineConfig = PipelineConfig()) -> PipelineResult:
    """Run the full BB84 pipeline once and return every intermediate quantity.

    Order: quantum stage -> sifting -> QBER estimation -> abort decision ->
    reconciliation -> privacy amplification. Reconciliation must come before
    amplification, because hashing keys that still differ gives unrelated outputs.
    """
    rng = make_rng(config.seed)
    stage = run_quantum_stage(config.n_qubits, config.f_eve, config.p_noise, config.eta, rng)
    sifted_length = len(stage.alice_sifted)
    true_qber = (
        float(np.count_nonzero(stage.alice_sifted != stage.bob_sifted)) / sifted_length
        if sifted_length
        else 0.0
    )

    sample = sifting.disclose_sample(stage.alice_sifted, stage.bob_sifted, config.sample_size, rng)
    estimate = estimate_qber(sample.alice_sample, sample.bob_sample, config.confidence)
    decision = decide(estimate.qber)

    result = PipelineResult(
        config=config,
        raw_qubits=stage.raw_qubits,
        received_qubits=stage.received_qubits,
        sifted_length=sifted_length,
        true_sifted_qber=true_qber,
        estimate=estimate,
        decision=decision,
        key_length_after_sample=len(sample.alice_remaining),
    )
    if decision.abort:
        result.status = STATUS_ABORT
        return result

    rec = reconcile(
        sample.alice_remaining,
        sample.bob_remaining,
        estimate.qber,
        rng,
        passes=config.passes,
        confirmation_streak=config.confirmation_streak,
    )
    result.reconciliation = rec
    if not rec.confirmed:
        result.status = STATUS_RECONCILIATION_INCOMPLETE
        return result

    amp = privacy_amplify(sample.alice_remaining, rec.bob_corrected, estimate.qber, rng)
    result.amplification = amp
    result.status = STATUS_EXTRACTED
    result.final_key_length = amp.output_length
    return result


def _pct(x: float) -> str:
    return f"{100.0 * x:.2f}%"


def format_report(result: PipelineResult) -> str:
    """Render the itemised report described in the project brief (section 5.1)."""
    est = result.estimate
    conf = round(100 * est.confidence)
    lines = [
        f"Sifted key length:             {result.sifted_length} bits",
        f"Estimated QBER:                {100 * est.qber:.1f}%  "
        f"({conf}% CI {100 * est.ci_low:.1f}–{100 * est.ci_high:.1f}%, sample n={est.sample_size})",
        f"Security threshold (derived):  {_pct(result.decision.threshold)}",
    ]
    if result.status == STATUS_ABORT:
        lines.append("Status:                        ⚠ ABORT — insufficient security margin")
    elif result.status == STATUS_RECONCILIATION_INCOMPLETE:
        lines.append("Status:                        ⚠ Reconciliation incomplete — no key extracted")
    else:
        lines.append("Status:                        ✓ Key extraction permitted")

    rec = result.reconciliation
    if rec is not None:
        eff = f"efficiency f = {rec.efficiency:.2f}" if rec.efficiency is not None else (
            "efficiency f = n/a, no errors to correct"
        )
        lines.append(f"Reconciliation leakage:        {rec.leakage_bits} bits  ({eff})")
        bound = (
            f"P(residual error) ≤ 2^-{result.config.confirmation_streak}"
            if rec.confirmed
            else "confirmation failed"
        )
        lines.append(f"Residual error rate:           {_pct(rec.residual_error_rate)}  ({bound})")
    lines.append(f"Estimated final key length:    {result.final_key_length} bits")
    lines.append(f"  (under the assumptions of the implemented model: {MODEL_ASSUMPTIONS})")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Experiments (the data behind the six charts)
# --------------------------------------------------------------------------


def experiment_qber_vs_eve(
    fractions: np.ndarray | None = None,
    trials: int = 50,
    sifted_bits: int = 10_000,
    seed: int = DEFAULT_SEED,
) -> dict[str, np.ndarray]:
    """Experiment 1: QBER against interception fraction ``f`` (noiseless)."""
    if fractions is None:
        fractions = np.round(np.arange(0.0, 1.0 + 1e-9, 0.05), 2)
    q = np.array(
        [
            [simulate_sifted_qber(sifted_bits, f, 0.0, make_rng(seed, 1, i, t)) for t in range(trials)]
            for i, f in enumerate(fractions)
        ]
    )
    return {
        "f_eve": fractions,
        "qber_mean": q.mean(axis=1),
        "qber_std": q.std(axis=1, ddof=1),
        "qber_theory": fractions / 4.0,
    }


def experiment_qber_vs_noise(
    noise: np.ndarray | None = None,
    trials: int = 50,
    sifted_bits: int = 10_000,
    seed: int = DEFAULT_SEED,
) -> dict[str, np.ndarray]:
    """Experiment 2: QBER against channel noise with no Eve (the control case)."""
    if noise is None:
        noise = np.round(np.arange(0.0, 0.15 + 1e-9, 0.005), 3)
    q = np.array(
        [
            [simulate_sifted_qber(sifted_bits, 0.0, p, make_rng(seed, 2, i, t)) for t in range(trials)]
            for i, p in enumerate(noise)
        ]
    )
    return {
        "p_noise": noise,
        "qber_mean": q.mean(axis=1),
        "qber_std": q.std(axis=1, ddof=1),
        "qber_theory": noise.copy(),
    }


def composed_qber(q_eve, q_noise):
    """Combined QBER from independent Eve and noise errors: ``Q_E + Q_N - 2 Q_E Q_N``.

    Errors compose like XOR, not addition. Two flips cancel. Example: 25% from
    full intercept-resend plus 3% noise gives 0.25 + 0.03 - 2(0.25)(0.03) =
    26.5%, not 28%.
    """
    q_eve = np.asarray(q_eve, dtype=float)
    q_noise = np.asarray(q_noise, dtype=float)
    return q_eve + q_noise - 2.0 * q_eve * q_noise


def experiment_combined(
    noise: np.ndarray | None = None,
    eve_fractions: tuple[float, ...] = (0.0, 0.2, 1.0),
    trials: int = 50,
    sifted_bits: int = 10_000,
    seed: int = DEFAULT_SEED,
) -> dict[str, np.ndarray]:
    """Experiment 3: noise sweep with Eve off and on; threshold for overlay."""
    if noise is None:
        noise = np.round(np.arange(0.0, 0.15 + 1e-9, 0.005), 3)
    out: dict[str, np.ndarray] = {"p_noise": noise}
    for j, f in enumerate(eve_fractions):
        q = np.array(
            [
                [simulate_sifted_qber(sifted_bits, f, p, make_rng(seed, 3, j, i, t)) for t in range(trials)]
                for i, p in enumerate(noise)
            ]
        )
        tag = f"f{f:.2f}"
        out[f"qber_mean_{tag}"] = q.mean(axis=1)
        out[f"qber_std_{tag}"] = q.std(axis=1, ddof=1)
        out[f"qber_theory_{tag}"] = composed_qber(f / 4.0, noise)
    out["threshold"] = np.full(len(noise), derive_threshold())
    return out


def experiment_sample_size(
    sample_sizes: np.ndarray | None = None,
    true_qbers: tuple[float, ...] = (0.0, 0.02, 0.05),
    sifted_length: int = 20_000,
    trials: int = 50,
    confidence: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> dict[str, np.ndarray]:
    """Experiment 4: Wilson CI width and remaining key against disclosed sample size.

    For each true QBER (channel noise, no Eve) and sample size ``m``, a sifted
    key of ``sifted_length`` bits is simulated and ``m`` bits are disclosed.
    Reported per ``(Q, m)``, averaged over trials:

    * the Wilson interval width;
    * the key length at the point estimate, ``floor(r(Q_hat)(N - m))``;
    * an illustrative conservative variant evaluated at the Wilson upper bound.
      This is not the pipeline's decision rule, which uses the point estimate.
      It shows why both very small and very large samples cost key.
    """
    if sample_sizes is None:
        sample_sizes = np.array([25, 50, 100, 200, 400, 700, 1000, 2000, 4000, 7000, 10_000, 15_000])
    out: dict[str, np.ndarray] = {"sample_size": sample_sizes}
    for j, q_true in enumerate(true_qbers):
        widths = np.zeros((len(sample_sizes), trials))
        keys_point = np.zeros_like(widths)
        keys_upper = np.zeros_like(widths)
        for t in range(trials):
            rng = make_rng(seed, 4, j, t)
            n_raw = math.ceil(2.2 * sifted_length)
            stage = run_quantum_stage(n_raw, 0.0, q_true, 1.0, rng)
            a = stage.alice_sifted[:sifted_length]
            b = stage.bob_sifted[:sifted_length]
            for i, m in enumerate(sample_sizes):
                s = sifting.disclose_sample(a, b, int(m), rng)
                est = estimate_qber(s.alice_sample, s.bob_sample, confidence)
                widths[i, t] = est.ci_high - est.ci_low
                remaining = sifted_length - int(m)
                keys_point[i, t] = final_key_length(est.qber, remaining)
                keys_upper[i, t] = final_key_length(est.ci_high, remaining)
        tag = f"q{q_true:.3f}"
        out[f"ci_width_{tag}"] = widths.mean(axis=1)
        out[f"key_point_{tag}"] = keys_point.mean(axis=1)
        out[f"key_upper_{tag}"] = keys_upper.mean(axis=1)
    return out


SURVIVAL_SCENARIOS: tuple[tuple[str, PipelineConfig], ...] = (
    ("Clean channel,\nno Eve", PipelineConfig()),
    ("Fibre noise 2%,\nno Eve", PipelineConfig(p_noise=0.02)),
    ("Noise 2% +\nEve f = 0.2", PipelineConfig(p_noise=0.02, f_eve=0.2)),
    ("Full intercept-\nresend f = 1", PipelineConfig(f_eve=1.0)),
)


def experiment_key_survival(seed: int = DEFAULT_SEED) -> list[dict]:
    """Experiment 5: key length at each pipeline stage for several scenarios."""
    rows = []
    for k, (label, cfg) in enumerate(SURVIVAL_SCENARIOS):
        cfg = PipelineConfig(**{**cfg.__dict__, "seed": seed + 1000 * k})
        res = run_pipeline(cfg)
        reconciled = res.reconciliation.key_length if res.reconciliation and res.reconciliation.confirmed else 0
        rows.append(
            {
                "scenario": label.replace("-\n", "-").replace("\n", " "),
                "label": label,
                "raw": res.raw_qubits,
                "sifted": res.sifted_length,
                "reconciled": reconciled,
                "amplified": res.final_key_length,
                "qber_estimate": res.estimate.qber,
                "leakage_bits": res.reconciliation.leakage_bits if res.reconciliation else 0,
                "status": res.status,
            }
        )
    return rows


def experiment_attribution(
    noise: np.ndarray | None = None,
    eve_fractions: tuple[float, ...] = (0.0, 0.2),
    sifted_length: int = 20_000,
    sample_size: int = 2000,
    trials: int = 20,
    seed: int = DEFAULT_SEED,
) -> dict[str, np.ndarray]:
    """Experiment 6: conservative versus ORACLE attribution of errors.

    * Conservative (the protocol): every observed error is attributed to Eve,
      giving ``floor((1 - 2h(Q_hat)) n)``.
    * Oracle (simulator only): the simulator's known noise ``p`` is separated
      out. ``Q_E = max(0, (Q_hat - p) / (1 - 2p))`` inverts the composition
      rule, and the oracle rate ``1 - h(Q_hat) - h(Q_E)`` is used (see
      :func:`bb84.security.oracle_key_rate`).

    The oracle is a measurement device, not a protocol capability. It uses
    information only the simulator has. Alice and Bob cannot separate noise
    from eavesdropping in a real deployment, so the oracle curve shows how much
    key the conservative rule costs, not a key they could actually extract.
    """
    if noise is None:
        noise = np.round(np.arange(0.0, 0.15 + 1e-9, 0.005), 3)
    out: dict[str, np.ndarray] = {"p_noise": noise}
    remaining = sifted_length - sample_size
    for j, f in enumerate(eve_fractions):
        cons = np.zeros((len(noise), trials))
        orac = np.zeros_like(cons)
        for i, p in enumerate(noise):
            for t in range(trials):
                rng = make_rng(seed, 6, j, i, t)
                n_raw = math.ceil(2.2 * sifted_length)
                stage = run_quantum_stage(n_raw, f, p, 1.0, rng)
                s = sifting.disclose_sample(
                    stage.alice_sifted[:sifted_length], stage.bob_sifted[:sifted_length], sample_size, rng
                )
                q_hat = estimate_qber(s.alice_sample, s.bob_sample).qber
                cons[i, t] = final_key_length(q_hat, remaining)
                r_or = oracle_key_rate(q_hat, p)
                orac[i, t] = math.floor(r_or * remaining) if r_or > 0 else 0
        tag = f"f{f:.2f}"
        out[f"conservative_{tag}"] = cons.mean(axis=1)
        out[f"oracle_{tag}"] = orac.mean(axis=1)
    return out


def experiment_reconciliation_comparison(
    qbers: tuple[float, ...] = (0.01, 0.02, 0.05, 0.068, 0.10),
    key_length: int = 18_000,
    trials: int = 100,
    passes: int = DEFAULT_PASSES,
    seed: int = DEFAULT_SEED,
) -> list[dict]:
    """Detect-only versus correcting confirmation after the same block passes.

    For each QBER, ``trials`` key pairs with i.i.d. errors are reconciled with
    the same number of block passes, then either:

    * detect-only: 20 random-subset checks with no correction, failing on any
      mismatch; or
    * correcting (the pipeline default): bisect and correct on a mismatch,
      ending on 20 consecutive agreeing checks.
    """
    rows = []
    for j, q in enumerate(qbers):
        for mode, correcting in (("detect-only", False), ("correcting", True)):
            confirmed = residual_runs = 0
            effs = []
            for t in range(trials):
                rng = make_rng(seed, 7, j, t)
                a = rng.integers(0, 2, key_length, dtype=np.uint8)
                b = a ^ (rng.random(key_length) < q).astype(np.uint8)
                r = reconcile(a, b, q, rng, passes=passes, correcting_confirmation=correcting)
                confirmed += r.confirmed
                residual_runs += r.residual_errors > 0
                effs.append(r.efficiency)
            rows.append(
                {
                    "qber": q,
                    "mode": mode,
                    "passes": passes,
                    "trials": trials,
                    "confirmed": confirmed,
                    "runs_with_residual_errors": residual_runs,
                    "mean_efficiency": float(np.mean(effs)),
                }
            )
    return rows


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------


def write_columns_csv(path: Path, data: dict[str, np.ndarray]) -> None:
    """Write equal-length columns to CSV (the table view for a chart)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = [k for k, v in data.items() if np.ndim(v) == 1]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        for row in zip(*(data[k] for k in keys)):
            w.writerow([f"{v:.6g}" if isinstance(v, (float, np.floating)) else v for v in row])


def write_rows_csv(path: Path, rows: list[dict], exclude: tuple[str, ...] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = [k for k in rows[0] if k not in exclude]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: (f"{row[k]:.6g}" if isinstance(row[k], float) else row[k]) for k in keys})

