# Automatic CPU acceleration and deterministic GPU, 2026-10-26

The default CPU path is faster without new configuration. An output-geometry
bottleneck was moved into a bit-exact Numba kernel; it benefits both CPU and GPU
analyses. Explicit GPU execution now uses deterministic cuDSS by default, but
the larger bridge remains unqualified against the CPU nonlinear path.

## What changed

Profiling Article Bridge 1 identified repeated Python spring centroid calculations
as the largest measured cost outside sparse solving. The runtime now packs
interface geometry once and computes its cached moment arms through a compiled
kernel. All C# float32 cast boundaries and the four-corner accumulation order
are preserved, with no fastmath or constitutive/control changes. The existing
scalar helper remains available for differential validation and facade parity.

Normal CPU use remains `AnalysisSession(model)`. Explicit hardware choices can
use `linear_solver_backend="cpu"` or `linear_solver_backend="gpu"`; the existing
native backend names remain supported. GPU mode maps to cuDSS, with deterministic
mode enabled before symbolic analysis. CPU remains the automatic default.

## CPU measurements

Same laptop, model inputs, SuperLU baseline and fresh-process procedure as the
[initial GPU screen](gpu-solving-2026-10-26.md). Three measured samples per
configuration follow warmup. These are sequential before/after screens on the
same host, not simultaneous paired measurements.

| Model | Solve before / after | Load + prepare + solve before / after |
|---|---|---|
| Benchmark 1, 48 Quads, 20 gravity steps | 0.772 / 0.210 s | 1.276 / 0.715 s |
| Article Bridge 1, 914 Quads, 5 gravity steps | 3.504 / 1.707 s | 10.668 / 8.888 s |

Solve time improves by about 3.7x and 2.1x, respectively. Total measured model
load/preparation/analysis time decreases by about 44% and 17%. Worker startup,
explicit warmup and diagnostic snapshot capture are excluded from these totals;
they are not cold process-launch latencies. First-call kernel loading not covered
by warmup remains included.

A separate direct comparison on all 27,372 Article Bridge 1 fibres measures the
original scalar geometry at median 1.786 s and the complete compiled geometry
path, including packing and output allocation, at 0.00577 s: approximately 310x
for that operation. Every float32 output bit matches. This local acceleration
does not imply a 310x speedup of complete analyses.

The optimized scalar-to-compiled comparison passes randomized distorted geometry
tests, a freshly prepared model comparison, and exact C# reaction/resultant/moment
regressions. Both paths use the same spring geometry and material histories.

## GPU results and limits

The installed cuDSS 0.8 offers deterministic execution or native iterative
refinement, but does not support combining the two. Both profiles were measured:

| Model / GPU profile | CPU / GPU solve | CPU / GPU total | CPU/GPU qualification |
|---|---|---|---|
| Benchmark 1 / deterministic | 0.210 / 0.267 s | 0.715 / 0.814 s | Pass, absolute 1e-9 |
| Article Bridge 1 / deterministic | 1.707 / 2.047 s | 8.888 / 9.164 s | Fail |
| Article Bridge 1 / three refinement corrections | 1.681 / 1.572 s | 8.890 / 8.837 s | Fail |

Benchmark 1 has matching iterations, all checked response/runtime fields within
the strict absolute envelope, passing equilibrium audits and zero phase mismatches.
Maximum displacement-vector difference is approximately `1.02e-17` in native
units. GPU is usable for this measured case but slower than the optimized CPU.

All CPU and deterministic-GPU repeat comparisons match each backend's own state
exactly at zero tolerance, with identical behavior and zero differing phase
entries. This removes measured GPU repeat variability, but **does not** make
the CPU/GPU nonlinear paths equal: Article Bridge 1 consistently differs by
approximately `7.02e-4` in displacement-vector native units and has 2,000 differing
saved phase entries. Those entries count comparisons across saved steps, not
distinct damaged springs.

The refinement experiment uses the combined absolute/relative `1e-9` envelope.
It remains variable: two pairs diverge in the nonlinear path and one pair has
matching phases and numeric fields within that envelope. CPU repeatability is
exact; refined GPU repeats include both small floating differences and a branch
split. Refinement is retained only as an explicit diagnostic profile, not the
default GPU configuration.

Both backends still fail the original larger model's independent equilibrium
audit under `Work`. No convergence criterion, tolerance, load step, constitutive
branch or exact regression tolerance was changed to turn that into a pass.
The GPU backend remains opt-in and is not qualified for the larger full analysis.

## Validation and evidence

The focused final suite passes 103 tests plus 12 native C# subtests, including all
eight native CUDA cases. Two missing-UMFPACK-specific tests skip because UMFPACK
is available. Coverage includes material-change policy, compiled enforcement,
linear-factor reuse, native output, float32 geometry, GPU modes and benchmark
isolation. Existing small-fixture `Work` equilibrium warnings remain visible.

[Compact evidence](../../release-evidence/performance/2026-10-26-fast-cpu-deterministic-gpu.json)
records before/after timings, repeatability, error maxima, source hashes at
aggregation, package versions and raw report/log hashes. The launches used the
uncommitted working tree based on `40596c23c3d6d777a3a53d2fae9d5ea16858d9f9`;
individual launch source snapshots were not archived. This is working-tree
benchmark evidence, not final package certification.

Use the [CPU/GPU guide](../guides/gpu-solving.md) for the simple hardware selection
API and comparison commands. No GPU fallback or promotion occurs silently.
