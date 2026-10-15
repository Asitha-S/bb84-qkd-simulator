"""Error reconciliation: multi-pass block parity, then random-subset confirmation.

Method: multi-pass block-parity reconciliation with binary-search error
localization (Bennett, Bessette, Brassard, Salvail & Smolin, 1992, *J.
Cryptol.* 5, 3), followed by a BICONF-style random-subset confirmation phase
with bisection correction, terminated on a streak of 20 consecutive successful
checks. Random-subset confirmation follows BICONF, the final stage of the
modified Cascade of Sugimoto & Yamazaki (2000), as described by
Martinez-Mateo, Pacher, Peev, Ciurana & Martin (2014). Ending on a
consecutive streak is this project's own strengthening. The published versions
use a fixed number of checks.

Bob corrects his key towards Alice's.

* **Pass 1.** Block size ``k1 ~ 0.73 / Q``, clamped to a minimum and to the
  key length. Block parities are compared publicly. In each block whose parity
  differs, a binary search (one disclosed parity per halving) locates one
  error, and Bob flips it.
* **Later passes.** A fresh public random permutation, then the block size is
  doubled and the procedure repeats. The permutation separates error pairs
  that cancelled within one block of the previous pass.
* **Confirmation.** Compare the parity of a random public subset, where each
  position is included with probability 1/2. If it differs, bisect that subset
  to locate and correct one error, and reset the streak. Stop once ``v``
  consecutive checks agree, or report failure at a cap.

Why the streak gives a clean bound: for any non-zero error pattern, exactly
half of all subsets have odd overlap with it. Each check therefore catches a
remaining error with probability exactly 1/2, independently of the other
checks. If the final ``v`` checks all agreed and no correction happened among
them, then ``P(residual error) <= 2**-v``. A fixed total count gives no such
statement, because a correction among the last checks would invalidate it.

Limitation: a block holding an even number of errors has matching parities
and hides them. This is why the block passes alone are not enough and the
confirmation phase exists. Cascade's backtracking (reusing earlier passes'
parities to find more errors) is not implemented. Full Cascade is out of
scope; see Elkouss, Martinez-Mateo & Martin (2011).

Leakage: every disclosed parity bit is counted, including block parities,
binary-search halvings, confirmation checks and their bisections. This is a
diagnostic only. It is not subtracted from the final key length, because
``r(Q) = 1 - 2h(Q)`` already pays for error correction (see
:mod:`bb84.security`).

Efficiency convention: ``f = leakage / (n * h(e))``, where ``e`` is the
realised error rate of the key entering reconciliation (errors / n). This is
the standard definition, and like the residual error rate it is a
simulator-side diagnostic. Using the sampled estimate ``Q_hat`` instead would
mix estimation error into the efficiency. For example, a sample that
under-estimates 2.13% as 1.80% would inflate f from 1.29 to 1.48. The
estimate still sets the first block size, so a poor estimate does cost
efficiency through a mis-sized block. That cost is real and is measured.

In the simulation, comparing Alice's and Bob's announced parities of a set of
positions is computed as the parity of ``alice XOR bob`` over that set. The two
are equivalent, and each comparison counts as one disclosed bit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .security import binary_entropy

BLOCK_SIZE_CONSTANT = 0.73
MIN_BLOCK_SIZE = 4
DEFAULT_PASSES = 4
DEFAULT_CONFIRMATION_STREAK = 20
DEFAULT_MAX_CONFIRMATION_CHECKS = 2000


@dataclass(frozen=True)
class PassStats:
    block_size: int
    blocks: int
    mismatched_blocks: int
    leaked_bits: int
    errors_after: int  # simulator-side diagnostic


@dataclass(frozen=True)
class ReconciliationResult:
    bob_corrected: np.ndarray
    key_length: int
    errors_before: int
    residual_errors: int  # simulator-side diagnostic
    residual_error_rate: float  # simulator-side diagnostic
    leakage_bits: int
    efficiency: float | None  # leakage / (n h(e)), e = realised error rate; None if e = 0
    confirmed: bool
    confirmation_checks: int
    confirmation_corrections: int
    residual_error_bound: float | None  # 2**-v when confirmed, else None
    passes: list[PassStats] = field(default_factory=list)


def initial_block_size(qber: float, key_length: int, min_block: int = MIN_BLOCK_SIZE) -> int:
    """``k1 ~ 0.73 / Q``, clamped to ``[min_block, key_length]``."""
    if key_length <= 0:
        return 0
    if qber <= 0.0:
        return key_length
    k = int(round(BLOCK_SIZE_CONSTANT / qber))
    return max(1, min(key_length, max(min_block, k)))


def _locate_error(diff: np.ndarray, positions: np.ndarray) -> tuple[int, int]:
    """Binary-search ``positions`` (odd error parity) for one error.

    Returns ``(error_position, parity_bits_disclosed)``.
    """
    leaked = 0
    while len(positions) > 1:
        half = len(positions) // 2
        left = positions[:half]
        leaked += 1
        if int(diff[left].sum()) & 1:
            positions = left
        else:
            positions = positions[half:]
    return int(positions[0]), leaked


def _block_pass(diff: np.ndarray, order: np.ndarray, block_size: int) -> tuple[int, int, int]:
    """One block-parity pass over ``order``. Updates ``diff`` in place.

    Returns ``(blocks, mismatched_blocks, leaked_bits)``.
    """
    starts = np.arange(0, len(order), block_size)
    block_parity = np.add.reduceat(diff[order].astype(np.int64), starts) & 1
    leaked = len(starts)
    mismatched = np.flatnonzero(block_parity)
    for b in mismatched:
        block = order[starts[b] : starts[b] + block_size]
        pos, bits = _locate_error(diff, block)
        diff[pos] ^= 1
        leaked += bits
    return len(starts), len(mismatched), leaked


def _confirm(
    diff: np.ndarray,
    rng: np.random.Generator,
    streak_target: int,
    max_checks: int,
    correct: bool,
) -> tuple[bool, int, int, int]:
    """Random-subset parity confirmation. Updates ``diff`` in place if correcting.

    With ``correct=True``: bisect each mismatching subset, correct one error and
    reset the streak; succeed on ``streak_target`` consecutive agreements.
    With ``correct=False``: run exactly ``streak_target`` detect-only checks
    and fail on any mismatch. That mode exists only to reproduce the
    comparison in the README.

    Returns ``(confirmed, checks, corrections, leaked_bits)``.
    """
    n = len(diff)
    if streak_target == 0:
        return True, 0, 0, 0
    checks = corrections = leaked = streak = 0
    while streak < streak_target and checks < max_checks:
        subset = np.flatnonzero(rng.random(n) < 0.5)
        checks += 1
        leaked += 1
        if int(diff[subset].sum()) & 1:
            if not correct:
                return False, checks, corrections, leaked
            pos, bits = _locate_error(diff, subset)
            diff[pos] ^= 1
            leaked += bits
            corrections += 1
            streak = 0
        else:
            streak += 1
    return streak >= streak_target, checks, corrections, leaked


def reconcile(
    alice_key: np.ndarray,
    bob_key: np.ndarray,
    qber_estimate: float,
    rng: np.random.Generator,
    passes: int = DEFAULT_PASSES,
    confirmation_streak: int = DEFAULT_CONFIRMATION_STREAK,
    max_confirmation_checks: int = DEFAULT_MAX_CONFIRMATION_CHECKS,
    min_block: int = MIN_BLOCK_SIZE,
    correcting_confirmation: bool = True,
) -> ReconciliationResult:
    """Reconcile Bob's key to Alice's.

    ``qber_estimate`` is the estimated QBER from the disclosed sample. It sets
    the first block size, because the estimate is all the protocol knows. The
    efficiency is measured against the realised error rate (see the module
    docstring).
    """
    alice_key = np.asarray(alice_key, dtype=np.uint8)
    bob_key = np.asarray(bob_key, dtype=np.uint8)
    if alice_key.shape != bob_key.shape:
        raise ValueError("keys to reconcile must have equal length")
    if passes < 1:
        raise ValueError(f"at least one pass is required, got {passes}")
    if confirmation_streak < 0:
        raise ValueError(f"confirmation_streak must be non-negative, got {confirmation_streak}")

    n = len(alice_key)
    diff = alice_key ^ bob_key  # 1 where Bob's bit is wrong (simulator view)
    errors_before = int(diff.sum())
    leakage = 0
    stats: list[PassStats] = []

    confirmed, checks, corrections = True, 0, 0
    if n > 0:
        block_size = initial_block_size(qber_estimate, n, min_block)
        for i in range(passes):
            order = np.arange(n) if i == 0 else rng.permutation(n)
            blocks, mismatched, leaked = _block_pass(diff, order, block_size)
            leakage += leaked
            stats.append(PassStats(block_size, blocks, mismatched, leaked, int(diff.sum())))
            block_size = min(n, block_size * 2)

        confirmed, checks, corrections, leaked = _confirm(
            diff, rng, confirmation_streak, max_confirmation_checks, correcting_confirmation
        )
        leakage += leaked

    residual = int(diff.sum())
    h = binary_entropy(min(errors_before / n, 0.5)) if n else 0.0
    return ReconciliationResult(
        bob_corrected=(alice_key ^ diff).astype(np.uint8),
        key_length=n,
        errors_before=errors_before,
        residual_errors=residual,
        residual_error_rate=residual / n if n else 0.0,
        leakage_bits=leakage,
        efficiency=leakage / (h * n) if h > 0.0 and n > 0 else None,
        confirmed=confirmed,
        confirmation_checks=checks,
        confirmation_corrections=corrections,
        residual_error_bound=math.ldexp(1.0, -confirmation_streak) if confirmed else None,
        passes=stats,
    )
