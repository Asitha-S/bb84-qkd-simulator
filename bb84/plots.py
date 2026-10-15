"""The six experiment charts: ``python -m bb84.plots [--seed N] [--quick]``.

Each chart is saved as a 300-dpi PNG under ``figures/``. Its data (the table
view) is saved as CSV under ``results/``. The detect-only versus correcting
reconciliation comparison quoted in the README is also written to
``results/reconciliation_comparison.csv``.

All key lengths are estimated final key lengths under the assumptions of the
implemented model (see :mod:`bb84.security`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

from . import runner  # noqa: E402
from .security import derive_threshold  # noqa: E402

# Palette: validated categorical slots 1-3 (light mode, all-pairs), chart chrome, status.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_WASH = "#cde2fb"
CRITICAL = "#d03b3b"
GOOD = "#0ca30c"

FIGSIZE = (7.2, 4.4)


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlepad": 10,
            "axes.labelcolor": INK_2,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "grid.linestyle": "-",
            "axes.axisbelow": True,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": INK_2,
            "ytick.labelcolor": INK_2,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "lines.linewidth": 1.6,
            "lines.solid_capstyle": "round",
            "lines.solid_joinstyle": "round",
            "text.color": INK,
            "svg.hashsalt": "bb84",
        }
    )


def _pct_axis(ax, axis: str = "y", decimals: int | None = 0) -> None:
    fmt = PercentFormatter(xmax=1.0, decimals=decimals)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def _bits_axis(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:g}K" if v >= 1000 else f"{v:.0f}"))


def _footnote(fig, text: str) -> None:
    fig.text(0.01, -0.02, text, fontsize=7.5, color=MUTED, ha="left", va="top")


def _points(ax, x, y, yerr, color, label):
    ax.errorbar(
        x, y, yerr=yerr, fmt="o", ms=5.5, color=color, mec=SURFACE, mew=1.2,
        ecolor=color, elinewidth=1.0, capsize=0, label=label, zorder=3,
    )


def _threshold_line(ax, threshold: float, x_text: float, label: str | None = None) -> None:
    ax.axhline(threshold, color=INK, lw=1.0, ls=(0, (5, 3)), zorder=2)
    ax.text(
        x_text, threshold, label or f"Derived threshold r(Q) = 0 → {100 * threshold:.2f}%",
        color=INK, fontsize=8.5, va="bottom", ha="left",
    )


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


# --------------------------------------------------------------------------


def plot_qber_vs_eve(data: dict, path: Path) -> None:
    """Experiment 1: QBER against interception fraction, with Q = f/4."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    f = data["f_eve"]
    ax.plot(f, data["qber_theory"], color=INK_2, lw=1.0, label="Theory  Q = f / 4", zorder=2)
    _points(ax, f, data["qber_mean"], data["qber_std"], BLUE, "Simulated (mean ± 1 s.d., 50 trials)")
    ax.annotate(
        f"f = 1: {100 * data['qber_mean'][-1]:.2f}% (theory 25%)",
        xy=(f[-1], data["qber_mean"][-1]), xytext=(-12, 10), textcoords="offset points",
        ha="right", fontsize=8.5, color=INK_2,
    )
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(0, 0.28)
    _pct_axis(ax)
    ax.set_xlabel("Eve's interception fraction f")
    ax.set_ylabel("QBER on sifted key")
    ax.set_title("1 · QBER rises linearly with intercept-resend fraction")
    ax.legend(loc="upper left")
    _footnote(fig, "Noiseless channel, 10,000 sifted bits per trial. Error bars are ±1 standard deviation across trials.")
    _save(fig, path)


def plot_qber_vs_noise(data: dict, path: Path, threshold: float) -> None:
    """Experiment 2: QBER against channel noise with no Eve (the control)."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    p = data["p_noise"]
    ax.axvspan(0, 0.02, color=BLUE_WASH, alpha=0.55, lw=0, zorder=0)
    ax.text(0.001, 0.142, "Realistic fibre\nQBER < 2%\n(Gobby, Yuan &\nShields 2004)",
            fontsize=8, color=INK_2, va="top")
    ax.plot(p, data["qber_theory"], color=INK_2, lw=1.0, label="Theory  Q = p", zorder=2)
    _points(ax, p, data["qber_mean"], data["qber_std"], BLUE, "Simulated, no Eve (mean ± 1 s.d.)")
    _threshold_line(ax, threshold, 0.031)
    ax.set_xlim(0, 0.152)
    ax.set_ylim(0, 0.155)
    _pct_axis(ax)
    _pct_axis(ax, "x")
    ax.set_xlabel("Channel noise p (bit-flip probability)")
    ax.set_ylabel("QBER on sifted key")
    ax.set_title("2 · Errors without an adversary: noise alone produces QBER")
    ax.legend(loc="lower right")
    _footnote(fig, "No eavesdropper. Noise above about 11% triggers an abort even though Eve is absent.")
    _save(fig, path)


def plot_combined(data: dict, path: Path, threshold: float) -> None:
    """Experiment 3 (headline): noise plus Eve, with the derived threshold."""
    fig, ax = plt.subplots(figsize=(7.6, 4.9))
    p = data["p_noise"]
    ax.axhspan(0, threshold, color=BLUE_WASH, alpha=0.35, lw=0, zorder=0)
    series = (("f0.00", BLUE, "Eve off (noise only)"),
              ("f0.20", ORANGE, "Eve on, f = 0.2"),
              ("f1.00", AQUA, "Eve on, f = 1.0 (full intercept)"))
    for tag, color, label in series:
        ax.plot(p, data[f"qber_theory_{tag}"], color=color, lw=1.0, alpha=0.9, zorder=2)
        _points(ax, p, data[f"qber_mean_{tag}"], data[f"qber_std_{tag}"], color, label)
    _threshold_line(ax, threshold, 0.003)
    ax.text(0.149, 0.006, "Shaded: QBER below threshold, r(Q) > 0, key extraction permitted",
            fontsize=8, color=INK_2, ha="right", va="bottom")

    # Indistinguishability: same QBER from two different causes.
    q_same = float(runner.composed_qber(0.05, 0.02))
    ax.plot([0.02, q_same], [q_same, q_same], color=INK, lw=0.8, zorder=4)
    for x in (0.02, q_same):
        ax.plot(x, q_same, "o", ms=6, mfc=SURFACE, mec=INK, mew=1.2, zorder=5)
    ax.annotate(
        f"Same QBER ≈ {100 * q_same:.1f}%: noise 2% + Eve f = 0.2,\n"
        f"or noise {100 * q_same:.1f}% and no Eve.\n"
        "QBER alone cannot tell them apart.",
        xy=(0.06, q_same), xytext=(0.088, 0.03), fontsize=8, color=INK,
        arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.8),
    )
    q_ex = float(runner.composed_qber(0.25, 0.03))
    ax.annotate(
        f"25% + 3% composes to {100 * q_ex:.1f}%, not 28%\nQ = Q_E + Q_N − 2·Q_E·Q_N",
        xy=(0.03, q_ex), xytext=(0.045, 0.215), fontsize=8, color=INK,
        arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.8),
    )
    ax.set_xlim(0, 0.152)
    ax.set_ylim(0, 0.33)
    _pct_axis(ax)
    _pct_axis(ax, "x")
    ax.set_xlabel("Channel noise p")
    ax.set_ylabel("QBER on sifted key")
    ax.set_title("3 · Noise and eavesdropping combined, against the derived threshold")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.0), ncols=1)
    _footnote(fig, "Markers: simulated mean ± 1 s.d. (50 trials × 10,000 sifted bits). "
                   "Thin lines: composition rule Q = Q_E + Q_N − 2·Q_E·Q_N with Q_E = f/4.")
    _save(fig, path)


def plot_sample_size(data: dict, path: Path, sifted_length: int) -> None:
    """Experiment 4: estimate confidence against disclosed sample size."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 4.2), gridspec_kw={"wspace": 0.28})
    m = data["sample_size"]
    for (q, color) in ((0.0, BLUE), (0.02, ORANGE), (0.05, AQUA)):
        tag = f"q{q:.3f}"
        ax1.plot(m, data[f"ci_width_{tag}"], "-o", color=color, ms=4.5, mec=SURFACE, mew=1.0,
                 label=f"True QBER {100 * q:.0f}%")
    ax1.set_xscale("log")
    _pct_axis(ax1, decimals=None)
    ax1.set_xlabel("Disclosed sample size m (log scale)")
    ax1.set_ylabel("95% Wilson interval width")
    ax1.set_title("4a · Estimate uncertainty vs sample size")
    ax1.legend(loc="upper right")

    tag = "q0.050"
    kp, ku = data[f"key_point_{tag}"], data[f"key_upper_{tag}"]
    ax2.plot(m, kp, "-o", color=AQUA, ms=4.5, mec=SURFACE, mew=1.0, label="Rate at point estimate (pipeline rule)")
    ax2.plot(m, ku, "--o", color=AQUA, ms=4.5, mec=SURFACE, mew=1.0, alpha=0.75,
             label="Rate at Wilson upper bound (illustrative)")
    best = int(np.argmax(ku))
    ax2.vlines(m[best], 0, ku[best], color=MUTED, lw=0.8, zorder=1)
    ax2.text(m[best] * 1.08, ku[best] * 0.04, f"best m ≈ {int(m[best]):,}\n(upper-bound rule)",
             fontsize=8, color=INK, ha="left", va="bottom")
    ax2.set_xscale("log")
    _bits_axis(ax2)
    ax2.set_ylim(0, max(kp.max(), ku.max()) * 1.25)
    ax2.set_xlabel("Disclosed sample size m (log scale)")
    ax2.set_ylabel("Estimated final key length (bits)")
    ax2.set_title("4b · Key remaining vs sample size (true QBER 5%)")
    ax2.legend(loc="upper right")
    _footnote(fig, f"Sifted key of {sifted_length:,} bits, 50 trials per point. The upper-bound curve is "
                   "illustrative only; the pipeline's decision uses the point estimate.")
    _save(fig, path)


def plot_key_survival(rows: list[dict], path: Path) -> None:
    """Experiment 5: key length through raw -> sifted -> reconciled -> amplified."""
    stages = ("raw", "sifted", "reconciled", "amplified")
    names = ("Raw", "Sifted", "Reconciled", "Amplified")
    fig, axes = plt.subplots(1, len(rows), figsize=(10.4, 4.3), sharey=True, gridspec_kw={"wspace": 0.12})
    ymax = max(r["raw"] for r in rows) * 1.15
    for ax, row in zip(axes, rows):
        vals = [row[s] for s in stages]
        x = np.arange(len(stages))
        ax.bar(x, vals, width=0.62, color=BLUE, edgecolor=SURFACE, linewidth=1.0, zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + ymax * 0.012, f"{v / 1000:.1f}K" if v >= 1000 else f"{v}",
                    ha="center", va="bottom", fontsize=8, color=INK_2)
        ax.set_xticks(x, names, rotation=35, ha="right", rotation_mode="anchor", fontsize=8)
        ax.set_ylim(0, ymax)
        ax.grid(axis="x", visible=False)
        ax.set_title(row["label"], fontsize=9, fontweight="normal", loc="center")
        q = row["qber_estimate"]
        if row["status"] == runner.STATUS_ABORT:
            msg, color = f"⚠ ABORT\nQBER {100 * q:.1f}%", CRITICAL
        else:
            msg, color = f"✓ QBER {100 * q:.1f}%\nleakage {row['leakage_bits']:,} bits", INK_2
        ax.text(2.5, ymax * 0.72, msg, ha="center", fontsize=8, color=color)
    _bits_axis(axes[0])
    axes[0].set_ylabel("Key length (bits)")
    fig.suptitle("5 · Key survival through the pipeline", x=0.125, ha="left",
                 fontsize=11, fontweight="bold", y=1.02)
    _footnote(fig, "Reconciled = sifted key minus the 2,000 disclosed bits, after reconciliation is confirmed. "
                   "Leakage is a diagnostic and is not subtracted. Amplified = floor(r(Q)·n).")
    _save(fig, path)


def plot_attribution(data: dict, path: Path, threshold: float) -> None:
    """Experiment 6: conservative attribution versus a simulator-only oracle."""
    fig, ax = plt.subplots(figsize=(7.6, 4.7))
    p = data["p_noise"]
    for tag, color, name in (("f0.00", BLUE, "no Eve"), ("f0.20", ORANGE, "Eve f = 0.2")):
        cons, orac = data[f"conservative_{tag}"], data[f"oracle_{tag}"]
        ax.fill_between(p, cons, orac, color=color, alpha=0.10, lw=0, zorder=1)
        ax.plot(p, cons, "-", color=color, label=f"Conservative, all errors attributed to Eve ({name})", zorder=3)
        ax.plot(p, orac, "--", color=color, label=f"Oracle, known noise removed ({name})", zorder=3)
    ax.axvline(threshold, color=MUTED, lw=0.8, zorder=2)
    ax.text(threshold + 0.0015, 0.62, "noise-only\nthreshold", transform=ax.get_xaxis_transform(),
            fontsize=7.5, color=INK_2, va="top")
    ax.text(
        0.0, 1.015,
        "Oracle = measurement device, not a protocol capability: it uses the simulator's known noise.\n"
        "Alice and Bob cannot separate noise from eavesdropping in a real deployment.",
        transform=ax.transAxes, ha="left", va="bottom", fontsize=8, color=CRITICAL,
    )
    _pct_axis(ax, "x")
    _bits_axis(ax)
    ax.set_xlim(0, 0.152)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Channel noise p")
    ax.set_ylabel("Estimated final key length (bits)")
    ax.set_title("6 · Conservative vs oracle attribution of errors", pad=34)
    ax.legend(loc="upper right", fontsize=7.8)
    _footnote(fig, "18,000-bit key after a 2,000-bit sample. Conservative: 1 − 2h(Q). "
                   "Oracle: 1 − h(Q) − h(Q_E), Q_E = max(0, (Q − p)/(1 − 2p)). Shaded: key the conservative rule gives up.")
    _save(fig, path)


# --------------------------------------------------------------------------


def run_all(seed: int, figures: Path, results: Path, quick: bool = False) -> None:
    _style()
    threshold = derive_threshold()
    trials = 8 if quick else 50
    sifted = 4000 if quick else 10_000

    print("Experiment 1: QBER vs Eve interception fraction")
    d1 = runner.experiment_qber_vs_eve(trials=trials, sifted_bits=sifted, seed=seed)
    runner.write_columns_csv(results / "exp1_qber_vs_eve.csv", d1)
    plot_qber_vs_eve(d1, figures / "exp1_qber_vs_eve.png")

    print("Experiment 2: QBER vs channel noise (no Eve)")
    d2 = runner.experiment_qber_vs_noise(trials=trials, sifted_bits=sifted, seed=seed)
    runner.write_columns_csv(results / "exp2_qber_vs_noise.csv", d2)
    plot_qber_vs_noise(d2, figures / "exp2_qber_vs_noise.png", threshold)

    print("Experiment 3: combined noise + Eve with derived threshold")
    d3 = runner.experiment_combined(trials=trials, sifted_bits=sifted, seed=seed)
    runner.write_columns_csv(results / "exp3_combined.csv", d3)
    plot_combined(d3, figures / "exp3_combined_threshold.png", threshold)

    print("Experiment 4: QBER estimate confidence vs sample size")
    sifted4 = 20_000
    d4 = runner.experiment_sample_size(sifted_length=sifted4, trials=trials, seed=seed)
    runner.write_columns_csv(results / "exp4_sample_size.csv", d4)
    plot_sample_size(d4, figures / "exp4_sample_size.png", sifted4)

    print("Experiment 5: key survival through the pipeline")
    d5 = runner.experiment_key_survival(seed=seed)
    runner.write_rows_csv(results / "exp5_key_survival.csv", d5, exclude=("label",))
    plot_key_survival(d5, figures / "exp5_key_survival.png")

    print("Experiment 6: conservative vs oracle attribution")
    d6 = runner.experiment_attribution(trials=5 if quick else 20, seed=seed)
    runner.write_columns_csv(results / "exp6_attribution.csv", d6)
    plot_attribution(d6, figures / "exp6_attribution.png", threshold)

    print("Reconciliation comparison: detect-only vs correcting confirmation")
    rc = runner.experiment_reconciliation_comparison(trials=10 if quick else 100, seed=seed)
    runner.write_rows_csv(results / "reconciliation_comparison.csv", rc)
    print(f"  {'QBER':>6}  {'mode':<12} {'confirmed':>10}  {'residual runs':>13}  {'efficiency':>10}")
    for r in rc:
        print(f"  {100 * r['qber']:5.1f}%  {r['mode']:<12} {r['confirmed']:>4}/{r['trials']:<5}"
              f"  {r['runs_with_residual_errors']:>13}  {r['mean_efficiency']:>10.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the six BB84 experiments and save charts")
    parser.add_argument("--seed", type=int, default=runner.DEFAULT_SEED)
    parser.add_argument("--figures", type=Path, default=Path("figures"))
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--quick", action="store_true", help="fewer trials, for a fast smoke run")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    run_all(args.seed, args.figures, args.results, args.quick)
    print(f"Charts written to {args.figures}/, data to {args.results}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
