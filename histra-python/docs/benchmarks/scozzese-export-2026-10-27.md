# Scozzese Bridge displacement export — 2026-10-27

Dense result export now computes Quad corner displacements in batches and reuses
them for ordered node averaging. This removes repeated per-corner Python/NumPy
calls while preserving the C# float32 boundaries, output shapes and field bits.
The scalar projection remains the independent reference and its API is unchanged.

## Input and method

`my_model/Scozzese_Bridge_3span.hrx` freshly prepares to 8,696 Quads, 60,872 DOFs
and 23,950 interfaces. Its SHA-256 is
`5d62f4c6b591bd5ffbb381f1932c00997030f979ce4e97871d9ff129519cc7c7`.
The export replay uses the saved initial state plus 18 accepted gravity states
through load factor 0.90, FP64 displacement history and stored interface forces
and moments. The reference exporter comes from release commit `c8c20fb`.

Runs were sequential on an i7-13650HX (14 physical / 20 logical cores), with
approximately 32 GB RAM, eight configured Numba threads and four BLAS threads.
These export measurements use no function profiler. Loading, fresh preprocessing
and nonlinear solving are excluded from export times. Baseline and final candidate
used separate freshly prepared processes. These are individual desktop runs,
not statistical confidence intervals or a full-analysis speedup claim.

## Results

| Phase | Original | Batched | Speedup |
|---|---:|---:|---:|
| Dense field construction | 45.497 s | 0.426 s | 106.7× |
| Complete `.histra` export | 55.837 s | 10.369 s | 5.39× |

Dense construction is included in full export; the rows must not be added.
Most remaining export time is serialization, compression and verification.
The earlier 118-second export profile included function-profiler overhead and
is not used as the baseline here.

All 36 arrays in the reconstructed old/new exports matched byte for byte,
including shape and dtype. Separately, `fields/U`, `fields/quad_displacements`
and `fields/node_displacements` matched the original saved solver bundle exactly.
Snapshot node counts and the existing packed node-row convention are preserved.

Native C# binary projection fixtures and differential tests cover float32
boundaries, ordered multi-entry afferences, unsorted shared-Quad contributions,
distortion-denominator guards, missing-step output and saved snapshot row counts.
The existing NPZ and bundle export tests cover integration. The optional HDF5
test is skipped when `h5py` is absent; the field builder is shared across formats.

The final candidate passed `make check` and the full suite: 1,083 tests and
1,467 subtests passed, with 24 environment/opt-in skips.

## Scope

Only output construction changes. Material formulas, numerical solver paths,
equilibrium checks, convergence settings and preprocessing are unchanged.
The original gravity analysis stalled while attempting load factor 0.95; this
export optimization does not resolve that convergence problem. It does not
qualify CPU/GPU parity or absolute 1e-9 solution accuracy.

Machine-readable provenance, source hashes, timing components and exact field
comparisons are retained in
[`2026-10-27-scozzese-export.json`](../../release-evidence/performance/2026-10-27-scozzese-export.json).
The local raw bundles, replay harnesses and logs are under
`benchmark_outputs/scozzese-export-optimization-2026-10-27/`.
