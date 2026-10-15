"""Demo: ``python -m bb84 [--seed N]``.

Opens with the success case (clean channel, no Eve, identical keys and a
working final key length), then shows the conditions under which that success
survives, and the conditions under which the protocol correctly refuses to
extract a key.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from .runner import DEFAULT_SEED, STATUS_EXTRACTED, PipelineConfig, format_report, run_pipeline

SCENARIOS = (
    ("1. Clean channel, no Eve: secure communication achieved",
     dict()),
    ("2. Realistic fibre noise (2%), no Eve: success survives noise",
     dict(p_noise=0.02)),
    ("3. Fibre noise (2%) plus partial intercept-resend (f = 0.2): still positive key rate",
     dict(p_noise=0.02, f_eve=0.2)),
    ("4. Full intercept-resend (f = 1.0): Eve is detected and the protocol aborts",
     dict(f_eve=1.0)),
    ("5. Heavy channel noise (13%), no Eve: aborts too, because QBER cannot say who caused the errors",
     dict(p_noise=0.13)),
    ("6. Channel loss (eta = 0.5), no noise, no Eve: shorter key, unchanged QBER",
     dict(eta=0.5)),
)


def _bits(a: np.ndarray, k: int = 48) -> str:
    return "".join(str(int(b)) for b in a[:k])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BB84 security and noise analysis demo")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--qubits", type=int, default=40_000)
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("BB84 Quantum Key Distribution: security and noise analysis")
    print(f"seed = {args.seed}, raw qubits per run = {args.qubits}\n")

    for k, (title, overrides) in enumerate(SCENARIOS):
        cfg = PipelineConfig(n_qubits=args.qubits, seed=args.seed + k, **overrides)
        res = run_pipeline(cfg)
        print("=" * 78)
        print(title)
        print("=" * 78)
        print(format_report(res))
        if res.status == STATUS_EXTRACTED and res.amplification is not None:
            amp = res.amplification
            same = np.array_equal(amp.alice_final, amp.bob_final)
            print(f"\n  Alice final key (first 48 bits): {_bits(amp.alice_final)}")
            print(f"  Bob   final key (first 48 bits): {_bits(amp.bob_final)}")
            print(f"  Keys identical: {'yes' if same else 'NO'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
