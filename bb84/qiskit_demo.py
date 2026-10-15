"""Layer 2: circuit-level BB84 rounds with Qiskit Aer (demonstration only).

``python -m bb84.qiskit_demo [--seed N] [--rounds R] [--eve]``

Each BB84 round is one qubit:

* Alice prepares ``|bit>`` with X (if bit = 1), then H if her basis is X.
* Eve (optional) measures in her basis (H, measure, H). The post-measurement
  state is her measured bit in her basis, so the re-preparation happens
  physically, through measurement collapse.
* Bob applies H if his basis is X, then measures.

Rounds are batched several qubits per circuit and run with one shot each,
with fixed simulator and transpiler seeds. No experiment depends on this
module. The statistics come from the NumPy layer (Layer 1), because circuit
simulation cannot reach the required sample sizes. This layer shows the same
protocol as genuine quantum circuits and exports a diagram for the report.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
from qiskit_aer import AerSimulator

QUBITS_PER_CIRCUIT = 8


@dataclass(frozen=True)
class CircuitRounds:
    alice_bits: np.ndarray
    alice_bases: np.ndarray
    bob_bases: np.ndarray
    bob_bits: np.ndarray
    eve_bases: np.ndarray | None
    eve_bits: np.ndarray | None


def build_circuit(
    alice_bits: np.ndarray,
    alice_bases: np.ndarray,
    bob_bases: np.ndarray,
    eve_bases: np.ndarray | None = None,
) -> QuantumCircuit:
    """One circuit carrying ``len(alice_bits)`` independent BB84 rounds."""
    n = len(alice_bits)
    q = QuantumRegister(n, "q")
    c_bob = ClassicalRegister(n, "bob")
    regs = [q]
    c_eve = None
    if eve_bases is not None:
        c_eve = ClassicalRegister(n, "eve")
        regs.append(c_eve)
    regs.append(c_bob)
    qc = QuantumCircuit(*regs)

    # Alice: encode
    for i in range(n):
        if alice_bits[i]:
            qc.x(q[i])
        if alice_bases[i]:
            qc.h(q[i])
    qc.barrier(label="Alice → channel")

    # Eve: measure in her basis; the collapsed state is her re-prepared qubit
    if eve_bases is not None:
        for i in range(n):
            if eve_bases[i]:
                qc.h(q[i])
            qc.measure(q[i], c_eve[i])
            if eve_bases[i]:
                qc.h(q[i])
        qc.barrier(label="Eve → Bob")

    # Bob: measure in his basis
    for i in range(n):
        if bob_bases[i]:
            qc.h(q[i])
        qc.measure(q[i], c_bob[i])
    return qc


def _read_register(memory: str, register_index: int, width: int, n_registers: int) -> np.ndarray:
    """Extract one classical register from a single-shot memory string.

    Qiskit prints registers in reverse declaration order, separated by spaces,
    and each register's bits most significant (highest index) first.
    """
    parts = memory.split(" ")
    if len(parts) != n_registers:
        raise ValueError(f"unexpected memory format: {memory!r}")
    reg = parts[n_registers - 1 - register_index]
    return np.array([int(b) for b in reg[::-1][:width]], dtype=np.uint8)


def run_rounds(rounds: int, seed: int = 42, with_eve: bool = False) -> CircuitRounds:
    """Run ``rounds`` circuit-level BB84 rounds on the Aer simulator."""
    rng = np.random.default_rng([seed, 99])
    a_bits = rng.integers(0, 2, rounds, dtype=np.uint8)
    a_bases = rng.integers(0, 2, rounds, dtype=np.uint8)
    b_bases = rng.integers(0, 2, rounds, dtype=np.uint8)
    e_bases = rng.integers(0, 2, rounds, dtype=np.uint8) if with_eve else None

    circuits = []
    for start in range(0, rounds, QUBITS_PER_CIRCUIT):
        sl = slice(start, min(rounds, start + QUBITS_PER_CIRCUIT))
        circuits.append(
            build_circuit(a_bits[sl], a_bases[sl], b_bases[sl], None if e_bases is None else e_bases[sl])
        )

    sim = AerSimulator(seed_simulator=seed)
    compiled = transpile(circuits, sim, seed_transpiler=seed)
    result = sim.run(compiled, shots=1, memory=True).result()

    bob_bits, eve_bits = [], []
    n_regs = 2 if with_eve else 1
    for k, qc in enumerate(circuits):
        mem = result.get_memory(k)[0]
        width = qc.num_qubits
        if with_eve:
            eve_bits.append(_read_register(mem, 0, width, n_regs))
            bob_bits.append(_read_register(mem, 1, width, n_regs))
        else:
            bob_bits.append(_read_register(mem, 0, width, n_regs))

    return CircuitRounds(
        alice_bits=a_bits,
        alice_bases=a_bases,
        bob_bases=b_bases,
        bob_bits=np.concatenate(bob_bits),
        eve_bases=e_bases,
        eve_bits=np.concatenate(eve_bits) if with_eve else None,
    )


def save_diagram(path: Path, seed: int = 42, with_eve: bool = True, n: int = 4) -> None:
    """Export a small example circuit (``n`` rounds) as a PNG for the report."""
    rng = np.random.default_rng([seed, 98])
    a_bits = rng.integers(0, 2, n, dtype=np.uint8)
    a_bases = rng.integers(0, 2, n, dtype=np.uint8)
    b_bases = rng.integers(0, 2, n, dtype=np.uint8)
    e_bases = rng.integers(0, 2, n, dtype=np.uint8) if with_eve else None
    qc = build_circuit(a_bits, a_bases, b_bases, e_bases)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = qc.draw(output="mpl", fold=-1)
    fig.savefig(path, dpi=200, bbox_inches="tight", metadata={"Software": None})


def _row(label: str, arr: np.ndarray | None, sym=None) -> str:
    if arr is None:
        return ""
    cells = "".join((sym[int(v)] if sym else str(int(v))).rjust(2) for v in arr)
    return f"  {label:<14}{cells}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Circuit-level BB84 rounds (Qiskit Aer)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rounds", type=int, default=24)
    parser.add_argument("--stats-rounds", type=int, default=800,
                        help="rounds for the QBER summary (no per-round table)")
    parser.add_argument("--figures", type=Path, default=Path("figures"))
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    basis = {0: "+", 1: "x"}
    for with_eve in (False, True):
        r = run_rounds(args.rounds, args.seed, with_eve)
        match = r.alice_bases == r.bob_bases
        print(f"\n{'With' if with_eve else 'Without'} Eve: {args.rounds} circuit-level rounds")
        print(_row("Alice bit", r.alice_bits))
        print(_row("Alice basis", r.alice_bases, basis))
        if with_eve:
            print(_row("Eve basis", r.eve_bases, basis))
            print(_row("Eve bit", r.eve_bits))
        print(_row("Bob basis", r.bob_bases, basis))
        print(_row("Bob bit", r.bob_bits))
        print(_row("Kept (sift)", match.astype(int), {0: ".", 1: "✓"}))
        a_key, b_key = r.alice_bits[match], r.bob_bits[match]
        print(f"  Sifted: {len(a_key)} bits, mismatches: {int(np.count_nonzero(a_key != b_key))}")

    print(f"\nQBER over {args.stats_rounds} circuit-level rounds:")
    for with_eve in (False, True):
        r = run_rounds(args.stats_rounds, args.seed + 1, with_eve)
        match = r.alice_bases == r.bob_bases
        q = float(np.mean(r.alice_bits[match] != r.bob_bits[match]))
        expected = "0.25" if with_eve else "0"
        print(f"  {'Eve f = 1.0' if with_eve else 'No Eve     '}: QBER = {q:.3f}"
              f"  (sifted {int(match.sum())} bits; expected {expected})")

    out = args.figures / "qiskit_bb84_circuit.png"
    save_diagram(out, args.seed, with_eve=True)
    save_diagram(args.figures / "qiskit_bb84_circuit_no_eve.png", args.seed, with_eve=False)
    print(f"\nCircuit diagrams written to {out} and {args.figures / 'qiskit_bb84_circuit_no_eve.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
