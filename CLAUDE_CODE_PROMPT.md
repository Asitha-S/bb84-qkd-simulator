# Implementation brief — paste this whole file into Claude Code

You are implementing a frozen, research-validated project plan. Everything you need is in this document. The methodology is settled — implement exactly what is specified, and raise an objection rather than silently deviating.

---

# PART 1 — CONTEXT

## 1.1 What this is

A college mini-project for AQVH911, Amaravati Quantum Valley Hackathon 2025. Team of three. The methodology review has already been prepared; this is the build.

**Problem statement (verbatim):**
> Develop a basic simulator for Quantum Key Distribution (BB84 Protocol) to show how secure communication can be achieved using quantum principles.

**Theme:** QKD Demonstration Simulator · **Category:** Hardware/Software

**Project title:** A Security and Noise Analysis Framework for BB84 Quantum Key Distribution

## 1.2 What BB84 is (so you implement the physics, not a cartoon of it)

Alice sends Bob a stream of qubits. For each one she picks a random bit and a random **basis** — rectilinear (Z) or diagonal (X). Bob doesn't know her basis, so he guesses randomly and measures.

The governing rule: **if Bob measures in the same basis the qubit currently carries, he recovers the bit deterministically. If he measures in the other basis, he gets a uniformly random result.**

Afterwards they publicly compare *which bases they used* — never the bit values — and keep only the positions where the bases matched. That's **sifting**, and it retains ~50% of the stream.

An eavesdropper (Eve) must also guess a basis. When she guesses wrong she gets a random result, and critically, **the qubit she forwards to Bob now carries her wrong state**. That disturbance shows up as disagreement between Alice's and Bob's sifted keys. Alice and Bob sacrifice a random sample, compare it publicly, and measure the **QBER** (quantum bit error rate). Full intercept-resend gives QBER = 25%.

## 1.3 Positioning — enforce this in all generated text

This project is **integration of established techniques, not novel research**. Every component is from the literature:

- BB84 — Bennett & Brassard (1984)
- Key-rate bound `r = 1 − 2h(Q)` and the ~11% threshold — Shor & Preskill (2000), *Phys. Rev. Lett.* 85, 441
- BBBSS reconciliation — Bennett, Bessette, Brassard, Salvail & Smolin (1992), *J. Cryptol.* 5, 3
- Toeplitz privacy amplification / Leftover Hash Lemma with quantum side information — Tomamichel, Schaffner, Smith & Renner (2011), *IEEE Trans. Inf. Theory* 57, 5524
- Noise-vs-Eve attribution is **known to be infeasible** — Fiorini, Pagano, Garroppo & Osele (2024), *Future Internet* 16(8), 275

**Never generate a comment, docstring, README line or printed string claiming novelty, discovery, or "we show that…" about anything in that list.** The contribution is a complete, reproducible, end-to-end pipeline at student scale — closing an implementation gap, not a research gap.

## 1.4 The question the project answers

> How does BB84 behave under realistic channel noise and eavesdropping, and how does that affect QBER, the security decision, reconciliation, and the final extractable key?

A basic simulator shows Eve raises QBER in a perfect channel. Real channels produce errors with no Eve present. This project models both, applies a derived security decision, runs the full post-processing chain, and reports a numerical key length.

## 1.5 Compliance guardrail — do not skip

The problem statement asks us to show how secure communication **can be achieved**. Much of this project concerns when it **cannot** be — aborts, ambiguity, sacrificed key material.

**The demo and the README must open with the success case:** clean channel, no Eve, Alice and Bob holding an identical key, a working final key length. Everything else is presented as the conditions under which that success survives. Never lead with an abort.

---

# PART 2 — ARCHITECTURE

## 2.1 Two layers, deliberately separate

**Layer 1 (primary) — plain probabilistic Python.** NumPy only. **Must not import Qiskit.** Runs every experiment; must scale to 10⁵ qubits × 50 trials in reasonable time. BB84 is simple enough that circuit simulation adds nothing to correctness and is far too slow for the statistics.

**Layer 2 (secondary) — Qiskit circuits.** Representative BB84 rounds at circuit level, for demonstration and report diagrams. Build after Layer 1 is complete and tested.

Justification to put in the README: statistical experiments need sample sizes circuit simulation cannot reach; the hackathon category (Hardware/Software) and the capstone context require a genuine quantum implementation. Two layers, two purposes.

## 2.2 Pipeline

```
Alice: random bits + random bases
        ↓  encode
   [ Eve: intercept-resend, probability f ]
        ↓
   [ Channel: depolarizing noise + transmittance loss ]
        ↓
Bob: random bases + measure
        ↓
   Sifting (public basis comparison)
        ↓
   QBER estimation (disclosed sample + Wilson CI)
        ↓
   ABORT DECISION          ← explicit step, explicit output
        ↓
   Error reconciliation    ← MUST precede the next step
        ↓
   Privacy amplification (Toeplitz hash)
        ↓
   Estimated final key length
```

**Ordering is load-bearing.** Reconciliation must precede privacy amplification. After sifting, Alice's and Bob's keys still disagree at the QBER rate. Toeplitz hashing *amplifies* differences — hashing two keys that differ in one bit yields two unrelated outputs. Reconciliation makes them identical first.

## 2.3 Module layout

| Module | Responsibility |
|---|---|
| `alice.py` | bit generation, basis choice, encoding |
| `bob.py` | basis choice, measurement |
| `eve.py` | fractional intercept-resend |
| `channel.py` | depolarizing noise, transmittance loss |
| `sifting.py` | basis reconciliation, disclosed-sample selection |
| `estimation.py` | QBER point estimate + Wilson confidence interval |
| `security.py` | entropy, key rate, derived threshold, abort decision |
| `reconcile.py` | BBBSS block-parity + binary-search localization, leakage tracking |
| `amplify.py` | Toeplitz hashing, compression sizing |
| `runner.py` | parameter sweeps, batch trials, seeding |
| `plots.py` | the six experiment charts |
| `qiskit_demo.py` | circuit-level BB84 rounds (Layer 2) |

---

# PART 3 — BUILD ORDER AND CHECKPOINTS

Build so there is always a *working project*, never a pile of disconnected modules. Verify each checkpoint before continuing.

1. `alice.py` + `bob.py`
2. `sifting.py`
3. **CHECKPOINT 1 — clean channel, no Eve, no noise, 256 qubits.** Alice's and Bob's sifted keys must be byte-identical. Sifted length ≈ 50% of raw. **This checkpoint alone satisfies the problem statement.** Stop and verify.
4. `eve.py`
5. **CHECKPOINT 2 — full intercept-resend (f = 1.0), noiseless, n = 50,000.** Measured QBER must be 0.25 ± 0.01.
6. `channel.py`
7. `estimation.py`
8. `security.py`
9. `reconcile.py`
10. `amplify.py`
11. **CHECKPOINT 3 — full pipeline end-to-end**, producing the itemised report in §5.1.
12. `runner.py` + `plots.py` — the six experiments
13. `qiskit_demo.py`

If work stalls at any step from 4 onward, everything before it remains a complete, demonstrable project.

---

# PART 4 — MODULE SPECIFICATIONS

## 4.1 `alice.py`
Generate `n` random bits and `n` random bases (0 = Z/rectilinear, 1 = X/diagonal). Represent a qubit as `(bit, basis)` — no state vectors needed in Layer 1.

## 4.2 `bob.py`
Generate `n` random measurement bases. Apply the measurement rule from §1.2: basis match → deterministic recovery of the carried bit; basis mismatch → uniform random bit.

## 4.3 `eve.py`
Fractional intercept-resend with interception probability `f ∈ [0, 1]`.

For each intercepted qubit: Eve picks a random basis, measures using the same rule as Bob, and **re-prepares the qubit as `(her_measured_bit, her_basis)`** before forwarding it. Non-intercepted qubits pass through untouched.

⚠ **The re-preparation is the whole mechanism.** A simulator where Eve measures but forwards the original qubit will show no disturbance and is the single most common BB84 implementation bug. Verify against the theoretical baseline:

**Q = f / 4**

(f=1.0 → 0.25; f=0.5 → 0.125; f=0.2 → 0.05.)

## 4.4 `channel.py`
- **Depolarizing noise:** flip the carried bit with probability `p_noise`. Parameterise over 0–0.15.
- **Transmittance loss:** drop qubits with probability `1 − η`. **Loss reduces key length only — it must not raise QBER.** Detector dark counts are explicitly out of scope; do not implement them.

## 4.5 `sifting.py`
Keep positions where Alice's and Bob's bases match. Then draw a random disclosed sample of size `m` from the sifted key for QBER estimation; those positions are consumed and removed from the key that continues down the pipeline.

## 4.6 `estimation.py`
QBER point estimate `Q̂ = k/n`, plus a **Wilson score confidence interval** (default 95%).

**Use Wilson, not Wald.** Wald degenerates to a zero-width interval at Q = 0 — which is precisely the clean-channel case this project must demonstrate. This is a deliberate methodological choice; record the reason in the module docstring.

## 4.7 `security.py` — read this section twice

Implement the consistency chain as a single derivation. Every reported value traces back to one formula.

```python
h(x)      = -x*log2(x) - (1-x)*log2(1-x)   # binary entropy; h(0) = h(1) = 0
r(Q)      = 1 - 2*h(Q)                      # asymptotic one-way secret-key fraction
threshold = the Q at which r(Q) == 0        # solve numerically by bisection
abort     = (r(Q) <= 0)                     # same formula, no separate constant
final_key_length = floor(r(Q) * sifted_key_length)
```

**Hard constraints:**

1. **The threshold must be computed numerically at runtime by bisection on `r(Q) = 0`. The literal `0.11` must never appear in the code.** A reviewer will ask where the number comes from; the answer must be "the rate equation," not "a textbook."
2. **Do NOT subtract reconciliation leakage from the final key length.** `r = 1 − 2h(Q)` already contains two `h(Q)` terms — one for the information sacrificed to error correction, one for privacy amplification. Subtracting measured parity bits again double-counts. Leakage is a **diagnostic only**.
3. Record the stated model in the module docstring: *asymptotic regime, one-way post-processing, collective attacks, ideal single-photon source, symmetric QBER in both bases.*
4. The threshold is a property of these assumptions, not a universal BB84 constant. Two-way post-processing raises it to ~18.9–20%. Note this in the docstring.

## 4.8 `reconcile.py`
BBBSS-style single-pass block-parity reconciliation with binary-search error localization (Bennett et al., 1992 — the predecessor to Cascade).

- Block size ≈ `0.73 / Q`, clamped to a sensible minimum and to the key length.
- Compare block parities publicly. For each block with mismatched parity, binary-search within it to locate and flip one error.
- **Count every disclosed parity bit** as measured leakage.
- **Report the residual error rate** after reconciliation. Be honest about the limitation: blocks containing an even number of errors pass undetected, so single-pass leaves residual errors. Do not claim it corrects all errors.
- Report the **reconciliation efficiency factor**: `measured_leakage / (h(Q) * n)`.

**Do not implement full Cascade.** It is explicitly out of scope (cite Elkouss, Martinez-Mateo & Martin, 2011, on its high interactivity and suboptimal efficiency).

## 4.9 `amplify.py`
Toeplitz-matrix universal hashing. Input: reconciled key of length `n`. Output length: `floor(r(Q) * n)`.

**Precondition — assert it:** Alice's and Bob's keys must be identical before hashing. If they differ, **fail loudly** with a clear error rather than producing garbage. Hashing amplifies differences.

Generate the Toeplitz matrix from a public random seed; the seed is public by design under the Leftover Hash Lemma.

## 4.10 `runner.py`
Parameter sweeps and batch trials. **Fixed random seed, configurable, defaulting to 42.** Every experiment must be exactly reproducible — two runs with the same seed produce byte-identical output.

## 4.11 `qiskit_demo.py` (Layer 2)
Circuit-level BB84 for a small number of rounds using Qiskit Aer. Hadamard for X-basis preparation, basis-dependent measurement, optional Eve layer. Export a circuit diagram for the report. Demonstration only — no experiment depends on it.

---

# PART 5 — OUTPUT, EXPERIMENTS, TESTS

## 5.1 Required output format

```
Sifted key length:             N bits
Estimated QBER:                6.8%  (95% CI 6.4–7.2%, sample n=2000)
Security threshold (derived):  11.00%
Status:                        ✓ Key extraction permitted
Reconciliation leakage:        X bits  (efficiency f = 1.23)
Residual error rate:           0.00%
Estimated final key length:    Y bits
```

Abort case:
```
Estimated QBER:                13.2%
Security threshold (derived):  11.00%
Status:                        ⚠ ABORT — insufficient security margin
Estimated final key length:    0 bits
```

**Wording rule, enforced in code, comments, README and printed strings:** never "secure key" unqualified. Always *"estimated final key length under the assumptions of the implemented model."* An abort is a legitimate result, not a failure.

## 5.2 The six experiments (`plots.py`)

**1. QBER vs Eve interception fraction.** Sweep f ∈ [0, 1] in 0.05 steps, 50 trials × ≥10,000 sifted bits. Overlay the theoretical line Q = f/4. Expected: close agreement throughout.

**2. QBER vs channel noise, Eve absent.** The control case — errors with no adversary. Mark the realistic fibre band (<2%, per Gobby, Yuan & Shields 2004) so the swept range is justified by measurement rather than convenience.

**3. Combined noise + Eve, with the derived threshold marked.** *Headline chart.* Sweep 0–15%, overlay Eve-on and Eve-off, draw the threshold line. Shows the region where the two are indistinguishable and the key rate is still positive.

⚠ **Compose errors correctly — they do not add linearly:**
```
Q ≈ Q_E + Q_N − 2·Q_E·Q_N
```
So 25% from Eve plus 3% noise is ~27.25%, not 28%.

**4. QBER estimate confidence vs sample size.** Wilson interval width against disclosed sample size m. Shows the tradeoff: sacrifice too few bits and the estimate is unreliable; too many and the key is gone.

**5. Key survival through the pipeline.** Bar chart: raw → sifted → reconciled → amplified. This is the clearest visual differentiator from a basic simulator.

**6. Conservative vs oracle attribution.** Final key length when all observed errors are conservatively attributed to Eve, versus when the simulator's known noise is separated out.

⚠ **The oracle case uses information only the simulator has.** Label it in the chart, the docstring and the README as a *measurement device, not a protocol capability*. Alice and Bob cannot perform this separation in a real deployment; presenting it otherwise would claim the protocol can distinguish noise from eavesdropping, which it cannot.

## 5.3 Tests (pytest)

| Test | Expected |
|---|---|
| Clean channel, no Eve, no noise | QBER = 0; sifted keys byte-identical; sifted length ≈ n/2 |
| f = 1.0, noiseless | QBER = 0.25 ± 0.01 |
| f = 0.5, noiseless | QBER = 0.125 ± 0.01 |
| f = 0.2, noiseless | QBER = 0.05 ± 0.01 |
| Derived threshold | 0.11 ± 0.005 |
| `r(Q)` on [0, 0.5] | monotonically decreasing |
| `h(0)`, `h(1)` | 0.0, no NaN |
| Reconciliation | leakage > 0; residual error rate reported |
| Privacy amplification | raises on mismatched input keys |
| Loss at η = 0.5 | sifted length halves; QBER unchanged |
| Fixed seed, two runs | identical output |

## 5.4 Deliverables

- Working package with the module layout in §2.3
- `requirements.txt` — numpy, scipy, matplotlib, pytest, qiskit, qiskit-aer
- `README.md` — how to run; what each experiment shows; the stated model assumptions; the success case first (§1.5)
- All six charts saved as publication-quality PNG
- Passing test suite

---

# PART 6 — THE EIGHT THINGS MOST LIKELY TO BE WRONG

1. **Eve must re-prepare** the qubit in her own basis, not measure and forward the original.
2. **Reconciliation strictly precedes privacy amplification.**
3. **Leakage is a diagnostic — never subtracted** from the final key length.
4. **The threshold is derived numerically**; `0.11` never appears as a literal.
5. **Wilson interval, not Wald** (Wald degenerates at Q = 0).
6. **QBER composition is `Q_E + Q_N − 2·Q_E·Q_N`**, not addition.
7. **Loss reduces length only**; it does not raise QBER.
8. **Layer 1 must not import Qiskit.**

Ask before deviating from any of these.

---

# PART 7 — OUT OF SCOPE

Do not implement, and state each as a deliberate exclusion in the README:

- **Finite-key analysis** → we work in the asymptotic regime (cite Tomamichel, Lim, Gisin & Renner, 2012)
- **Full Cascade** → high interactivity, suboptimal efficiency (cite Elkouss et al., 2011)
- **Decoy states / weak coherent sources** → photon-number-splitting out of scope (cite Brassard, Lütkenhaus, Mor & Sanders, 2000)
- **Detector dark counts**
- **Optimal cloning attacks**
- **Other QKD protocols** (B92, E91, six-state) — the problem statement specifies BB84
- **Streamlit dashboard** — only if everything above is complete and tested
