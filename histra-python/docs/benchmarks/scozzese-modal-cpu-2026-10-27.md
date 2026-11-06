# Scozzese modal execution and CPU factorization — 2026-10-27

The modal implementation now constructs its compiled runtime after initialization,
checks live coverage before numerical assembly, and uses compiled full-block
COO scatter. Local stiffness formulas, full-block contribution order, sparse
duplicate reduction and eigenvalue convergence settings are preserved.
The export improvement was committed separately as `b2a6e0b`.

## Model and measurements

`my_model/Scozzese_Bridge_3span.hrx`: 8,696 Quads and 60,872 DOFs.
Input SHA-256:
`5d62f4c6b591bd5ffbb381f1932c00997030f979ce4e97871d9ff129519cc7c7`.
Each process freshly prepared the source HRX with caching disabled. Runs were
sequential on an i7-13650HX with approximately 32 GB RAM, eight configured Numba
threads, four BLAS threads and project-local OpenBLAS. No function profiler was
used. These are individual desktop observations, not confidence intervals.

| Modal measurement | Baseline | Changed code |
|---|---:|---:|
| Fresh preparation, excluded from modal time | 46.571 s | 47.615 s |
| Modal execution including coverage audits | 38.915 s | 34.362 s |
| Stiffness assembly, included above | 4.543 s | 2.670 s |
| Actual compiled runtime constructions | 2 | 1 |
| Peak process RSS | 3,011 MiB | 2,476 MiB |

Modal execution improved 1.13× (11.7% less time); assembly improved 1.70×.
The raw CSC stiffness matrix matched bit for bit: shape, indices, offsets and
values. All 12 frequencies, mode-shape vectors and reported modal scalar values
also matched exactly. Both runs took seven subspace iterations. Matrix saving
for differential inspection occurred outside the assembly timer but inside the
modal timer in both runs.

The baseline is the pre-change source at `b2a6e0b`. The candidate has recorded
module hashes. A subsequent dependency guard retains read-only imports when
Numba is absent and explicitly rejects uncompiled production scatter; the timed
numerical kernel and assembly arithmetic are unchanged.

## Separate CPU backend screen

The virgin modal tangent was also used for an algebra-only screen with a
seeded nonzero Gaussian right-hand side (seed 20261027), three solve/refactor
samples, FP64 arithmetic and the same BLAS environment.

| Backend | Initial factor | Median numeric refactor | Median RHS solve |
|---|---:|---:|---:|
| UMFPACK/METIS | 2.216 s | 1.190 s | 0.0385 s |
| UMFPACK/AMD | 2.409 s | 2.003 s | 0.0583 s |
| CHOLMOD | 1.476 s | 0.393 s | 0.0220 s |

CHOLMOD's roughly 3× numeric-refactor advantage on this matrix does not translate
to a 3× full nonlinear speedup. The actual accepted gravity path was screened
separately with the existing optional CHOLMOD backend:

| Gravity measurement, through load factor 0.90 only | Result |
|---|---:|
| Prior timing-only UMFPACK run | 103.280 s |
| CHOLMOD screen | 81.252 s |
| Speedup | 1.27× |
| Accepted load steps | 18 |
| Maximum FP64 displacement difference | 1.603 × 10⁻¹⁵ cm |
| Support-reaction differences, all three axes | 0 |
| Maximum elastic/dissipated energy difference | 1.706 × 10⁻¹³ |
| Maximum residual-norm difference | 4.943 × 10⁻¹⁰ |
| Final available Quad/Coulomb phase mismatches | 0 |

All accepted equilibrium audits passed, Newton iteration counts matched, and
all 150 linear solves reported CHOLMOD with no LU fallback. Loading, preparation
and final snapshot saving are excluded from the gravity solve times. The prior
UMFPACK timing comes from the same day's earlier timing-only run, not a new
paired repetition; desktop/system variation can contribute to this comparison.

This remains a partial-path screen. The 95% step and full-load stopping behavior,
transverse phase history and complete FP64 constitutive history are unqualified.
No default backend or authored analysis settings were changed. There is no
matching C# `.Results` reference for this model. Use the default/native parity
configuration until the complete response is qualified for the intended model.

## Verification and artifacts

Focused checks cover exact legacy/compiled CSC scatter with asymmetric blocks,
multiple/invalid afferences, disabled blocks and cutoff values; runtime construction
after initialization; refusal before assembly when coverage fails; explicit scalar
diagnostics; and absence of silent uncompiled scatter. Existing native C# GUI
fixtures cover unloaded, loaded and material-change modal modes and quantities.

The main modal change passed the full suite: 1,091 tests and 1,467 subtests,
with 24 environment/opt-in skips. The final focused pass, including the added
optional-dependency guard, passed 48 tests with two skips. Final `make check`
(Ruff, mypy and fast tests) also passed.

Machine-readable provenance, module hashes, raw phase/timing comparisons and
scope limits are in
[`2026-10-27-scozzese-modal-cpu.json`](../../release-evidence/performance/2026-10-27-scozzese-modal-cpu.json).
The local raw matrices, modes and harness logs are retained under
`benchmark_outputs/scozzese-modal-optimization-2026-10-27/` and
`benchmark_outputs/scozzese-cpu-backend-screen-2026-10-27/`.
