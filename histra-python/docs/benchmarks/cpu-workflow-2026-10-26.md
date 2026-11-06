# CPU workflow improvements — 2026-10-26

The working tree adds solver-only HRX loading, a single compiled runtime build
for virgin static solves, shared face projections during fibre preparation, and
bounded independent CPU job processes. See the [CPU guide](../guides/cpu-performance.md)
for use. The full HRX reference loader and lifecycle coverage enforcement remain
available; constitutive formulas and convergence tolerances are unchanged.

## Scope and methodology

Baseline: CPU commit `8745cc836ee60cda9fe53bdda40947e65a311b99`, exported with
`git archive` to a separate source tree. Candidate: the working tree identified
by file hashes in the [machine-readable evidence](../../release-evidence/performance/2026-10-26-cpu-workflow.json).
Both use the same virtual environment, UMFPACK fast precision and original HRX
inputs. The solver selects its normal automatic Numba thread policy.

Each single-model timing is the median of three warm runs after one startup run.
The reported total includes HRX loading, fresh preparation and the session solve;
it excludes process import and post-solve audit-array serialization. Phase
medians need not sum to the total median. Cold compilation is not a speed claim.

The baseline uses `load_model`; the candidate uses `load_solver_model`.
Both run the complete authored Vert analysis. Equilibrium auditing is disabled
for these trajectory comparisons in both variants, preserving authored Work
stopping behavior. In particular, Article Bridge 1's known equilibrium failure
is not resolved or qualified by these performance measurements. Production job
APIs and the new command-line runner retain strict equilibrium checks.

## Single-model measurements

| Model | Quads / DOFs / Vert steps | Before total | After total | Wall-time reduction |
|---|---|---:|---:|---:|
| Benchmark 1 virgin bridge | 48 / 336 / 20 | 0.551 s | 0.425 s | 22.9% |
| Article Bridge 1 | 914 / 6,398 / 5 | 9.113 s | 6.705 s | 26.4% |

Article Bridge 1 phase medians:

| Phase | Before | After |
|---|---:|---:|
| HRX load | 2.647 s | 1.252 s |
| Fresh preparation | 4.876 s | 4.126 s |
| Session solve | 1.591 s | 1.296 s |

The small virgin HRX contains little saved state; most of its benefit comes
from preparation and runtime initialization. The larger saved model also
benefits from skipping serialized interfaces/springs and saved Quad state.

## Numerical evidence

Compared by dtype, shape and exact array bytes:

- Benchmark 1: 211 captured fields, 200,904 values, zero differences.
- Article Bridge 1: 61 captured fields, 963,232 values, zero differences.

Captured fields cover every returned step's displacement, load factor,
reactions, iteration count, residual/convergence error and energies when present,
plus the final complete compiled runtime snapshot, including constitutive
history and phases. Step counts and exit codes also match. This establishes
unchanged responses on these two inputs relative to the CPU baseline, rather
than blanket bit-exact parity with the C# global solver.

Native C# fibre fixtures independently validate coefficient, area, length and
stiffness behavior. The new batch-versus-uncached-cell differential test checks
all stiffness output bits. Fresh full-loader and solver-loader paths also
produce identical responses and runtime snapshots in regression tests.

## Independent process throughput

Two complete Article Bridge 1 Vert jobs, one Numba/BLAS thread per process:

| Scheduling | Total wall time |
|---|---:|
| One worker, two fresh processes sequentially | 16.057 s |
| Two workers, two fresh processes concurrently | 8.155 s |

Observed throughput improvement: **1.97×**. This is one measurement per scheduling
configuration, including interpreter startup, loading, solving and result
transfer. Both jobs' recorded response histories are bit-exact between modes.
No speedup is implied for one dependent analysis chain or for small jobs dominated
by process startup. Memory estimates can cap concurrent workers.

## Verification and reproduction

The focused CPU regression run passed 119 tests and 172 native fixture subtests;
four optional/environment-specific checks were skipped. Coverage includes
preprocessing, loading, backend enforcement, initialization count, restart,
modal analysis, interface material mutation, process isolation, ordered failure
reporting and hard worker deadlines. Source inputs remained unchanged.
The shared CPU/GPU backend test group additionally passed 25 tests; eight CUDA
hardware checks were skipped in the sandbox. The batch CLI smoke run completed
two Benchmark 1 jobs with strict equilibrium auditing enabled.

The timing harness can target a separate exported source tree:

```bash
python histra/tools/cpu_workflow_benchmark.py my_model/Article_Models_Benchmark/Bridge_1.hrx --source-root /tmp/histra-cpu-baseline-8745cc8 --output benchmark_outputs/cpu-before.json
python -m histra.tools.cpu_workflow_benchmark my_model/Article_Models_Benchmark/Bridge_1.hrx --source-root . --fast --output benchmark_outputs/cpu-after.json
```

Each command writes phase timing JSON and adjacent NPZ history/state arrays.
Use the same interpreter and model hash for comparisons. Private model paths
are recorded in the evidence; the model inputs and generated NPZ files remain
in ignored workspace directories.
