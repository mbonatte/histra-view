# Large-model hardware capacity — 2026-10-26

The single-model runner now supports project-local threaded BLAS, separate kernel
and BLAS budgets, explicit GPU selection, results bundles, and partial exports
when cooperative cancellation/failure returns. See the
[CPU performance guide](../guides/cpu-performance.md) for commands.

## Machine and bottleneck

Machine: Intel Core i7-13650HX, 14 physical cores / 20 logical CPUs, 32 GiB RAM,
GeForce RTX 4060 Laptop with 8,188 MiB VRAM, driver 595.99.02.
The host GPU is available to a device-enabled process; a restricted sandbox
cannot initialize CUDA on this machine.

The system UMFPACK/CHOLMOD libraries link to the reference BLAS library at
`/usr/lib/x86_64-linux-gnu/blas/libblas.so.3.12.1`. NumPy and SciPy have their own
optimized BLAS builds; those do not replace SuiteSparse's native BLAS dependency.
Ubuntu `libopenblas0-pthread` 0.3.32+ds-5 was extracted into `.venv/native/openblas`.
No system package or alternative was changed. The launcher sets the child
library path before import and verifies LP64 compatibility.

## Repeated matrix benchmark

Freshly prepared Dhir bridge: 6,824 Quads, 47,768 DOFs, 18,250 interfaces and
164,250 transverse springs. The captured virgin stiffness has 1,225,460 nonzeros.
The initial stiffness-check solve has a zero RHS, so precision screening instead
uses a nonzero Gaussian RHS from NumPy seed `20261026`. This is a matrix screen,
not a physical load-history qualification.

Each configuration creates three new factorization objects in one process.
The table reports medians; individual samples, file hashes, native library paths
and hardware/source provenance are in the
[machine-readable evidence](../../release-evidence/performance/2026-10-26-large-model-capacity.json).
Final matrix screens ran without concurrent nonlinear validation jobs.

| Operation | System CPU UMFPACK | OpenBLAS CPU UMFPACK, 4 threads | Deterministic GPU cuDSS |
|---|---:|---:|---:|
| Initial factorization and solve | 3.596 s | 1.553 s | 0.464 s |
| Reuse existing factors for RHS | 0.0868 s | 0.0883 s | 0.00450 s |
| Same-pattern numeric refactor and solve | 2.907 s | 0.867 s | 0.160 s |

Numeric refactorization improved **3.35× on CPU** and **18.18× on GPU** relative
to the system CPU library. This does not imply the same speedup for an entire
analysis. UMFPACK uses its accurate refinement setting in this screen. cuDSS uses
deterministic FP64 mode. All candidates' maximum solution differences from the
reference were below 2e-14; recorded matrix residuals were below 1e-9.

A separate single-sample CPU thread screen compared 1, 2, 4, 6, 12 and 20 BLAS
threads. Twenty threads took 5.494 s for initial factorization, versus 1.626 s
with four. Full CPU utilization is not a reliable performance objective on this
hybrid laptop. Eight kernel threads and four BLAS threads are starting budgets,
not a universal optimum. CHOLMOD was also screened, but remains an explicit
choice because matrix definiteness and nonlinear response require validation.

## Nonlinear precision and execution

Complete original-CPU versus OpenBLAS-CPU Vert histories:

- Benchmark 1, 20 commits: maximum global displacement difference 2.95e-17.
- Article Bridge 1, 5 commits: maximum global displacement difference 4.22e-15.

All captured step response fields and final compiled runtime snapshot fields
were within 1e-9 absolute difference. Final transverse, Coulomb and Quad phase
labels matched exactly. These two trajectory screens retain the earlier
benchmark harness's `equilibrium_policy="off"`; Article Bridge 1's known Work
convergence audit failure is not resolved by changing BLAS.

Dhir first committed load step, OpenBLAS CPU versus deterministic GPU:

- Both commit at load factor 0.1 and pass strict independent equilibrium checks.
- Maximum global displacement difference: 6.94e-17.
- All captured response and final runtime fields are within 1e-9 absolute;
  checked phase labels match exactly.

This Dhir check is explicitly **partial**, limited to one committed public step.
Its observed CPU/GPU solve times are retained as diagnostics, not a fair full-run
speed comparison; rejected-trial/retry behavior and startup conditions differed.

The unmodified full Dhir Vert analysis was subsequently attempted on CPU and GPU
with strict equilibrium auditing and a 600-second hard deadline per process.
Both reached public commits at load factors 0.1 and 0.2, then timed out while
attempting the next step after repeated displacement-limit retries and automatic
step reductions. These validation jobs ran concurrently, so their elapsed times
are not a backend performance benchmark. **Neither completed the full history.**
There is no full-Dhir GPU precision qualification or end-to-end speed claim.
The remaining limitation is nonlinear convergence as well as computational cost;
no tolerance, displacement limit or authored method was changed to hide it.

## Runner and verification

The runner uses one isolated process for a model's full dependency chain, with
thread budgets applied before native imports. Strict equilibrium and compiled
coverage enforcement remain enabled. Output bundles omit full node-displacement
projection and include generalized displacements and stage snapshots.
The CLI records actual native library paths. Regular in-process and ordinary
batch APIs preserve their prior native-library selection.

The first CLI smoke test completed Benchmark 1 Vert with strict equilibrium
checks and saved a verified `.histra` bundle. The regression group passed 129
tests and 172 native fixture subtests, with four optional checks skipped.
Shared CPU/GPU tests additionally passed 25 tests; eight CUDA checks were skipped
inside the restricted sandbox. Device-enabled matrix and Dhir step runs were
executed separately on the real GPU.

Cancellation regression verifies that committed work is exported as a partial
bundle before a cooperative cancellation exception reaches the caller. Large
workers reserve up to 30 seconds of their hard deadline for this export. A
native call that overruns the hard deadline can still prevent partial export.
The two full-Dhir attempts above used the earlier hard-timeout path and did not
produce complete bundles.

Reproduce a matrix phase screen using saved matrix/RHS arrays:

```bash
python -m histra.tools.native_capacity_benchmark matrix.npz rhs.npy --backend umfpack --output cpu.json
python -m histra.tools.native_capacity_benchmark matrix.npz rhs.npy --backend cudss --output gpu.json
```

For threaded native CPU BLAS, set `LD_LIBRARY_PATH` to the installed LP64 runtime
and `OPENBLAS_NUM_THREADS=4` before launching the benchmark process. The tool
rejects a zero RHS to prevent trivial precision tests. Model inputs, raw matrices,
RHS vectors and output NPZ data remain in ignored workspace directories.
