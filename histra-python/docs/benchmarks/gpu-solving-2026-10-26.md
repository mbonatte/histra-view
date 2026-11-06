# RTX 4060 GPU sparse-solver screen, 2026-10-26

The subsequent [CPU/GPU optimization screen](cpu-gpu-fast-mode-2026-10-26.md)
records the compiled geometry optimization and the new deterministic GPU default.
The values below preserve the initial implementation's measurements.

The experimental cuDSS backend runs successfully on the user's RTX 4060 Laptop.
It improves the larger bridge's linear-system timings, but does **not** qualify
the complete larger analysis at the requested accuracy. The small bridge's
complete gravity comparison passes and is slightly slower on GPU.

## Environment and method

- Intel Core i7-13650HX, 20 logical CPUs, approximately 30 GiB system RAM.
- NVIDIA GeForce RTX 4060 Laptop, 8,188 MiB VRAM; driver 595.99.02.
- Project-local nvmath-python 1.0.0 and cuDSS 0.8.0.10, CUDA 12.9 runtime wheels.
  The system toolkit remains CUDA 12.4. The system driver was not changed.
- Tests and timings run outside the execution sandbox, which hides
  `/dev/nvidia*` and makes `nvidia-smi` fail with exit code 9 inside it.
- Float64, general/full sparse matrices, blocking CUDA execution, including
  host/device transfers. The packaged GNU OpenMP planning layer is enabled.
- Initial working-tree commit `40596c23c3d6d777a3a53d2fae9d5ea16858d9f9`, with
  uncommitted GPU implementation changes. The compact evidence records hashes
  of the relevant source files, input models and local raw reports.

The initial envelope is **absolute `1e-9`, relative zero**, in each field's
native units. This is stricter than the comparison tools' default combined
absolute/relative `1e-9` envelope. Original constitutive laws, stopping criteria
and equilibrium audits are unchanged. These measurements compare CPU and GPU;
they are not new C# `.Results` qualification.

## Identical stiffness systems

Matrices were extracted from freshly prepared, original Vert definitions.
Right-hand sides are deterministic seed-42 random vectors, rather than saved
Newton residuals. Each backend has one cold sample and five measured samples.
Times below are warmed medians, in milliseconds. New numerical factors reuse
symbolic analysis where supported; refactorization scales matrix values by 1.01.
All initial, repeated-RHS and refactored solutions and equation residuals pass
the strict absolute envelope for both CPU baselines.

| Model / CPU baseline | DOFs / nonzeros | First CPU / GPU | Refactor + solve CPU / GPU | Reused RHS CPU / GPU |
|---|---|---|---|---|
| Benchmark 1 / SuperLU | 336 / 6,144 | 2.56 / 16.35 | 2.64 / 1.97 | 0.079 / 0.499 |
| Benchmark 1 / UMFPACK | 336 / 6,144 | 7.37 / 15.52 | 1.60 / 1.29 | 0.049 / 0.287 |
| Article Bridge 1 / SuperLU | 6,398 / 157,220 | 147.76 / 55.72 | 150.54 / 7.93 | 2.698 / 0.569 |
| Article Bridge 1 / UMFPACK | 6,398 / 157,220 | 136.29 / 54.04 | 70.71 / 6.82 | 1.770 / 0.554 |

The larger system's first factorization/solve is 2.65x faster than SuperLU and
2.52x faster than UMFPACK. Maximum measured GPU solution difference across these
screens is `7.49e-15`; maximum equation residual difference is `9.55e-11`.
The small matrix pays more setup/transfer overhead than it saves.

An initial benchmark trial shared the source matrix with UMFPACK, whose numeric
refactorization updates its retained values buffer. Scaling a later trial then
modified the residual reference and subsequent samples. The harness now gives
each sample its own matrix; a native regression covers that isolation. The
table and compact evidence use only the corrected measurements.

## Complete gravity analyses

Each measured chain runs in a new spawned process and freshly prepares its HRX
with `force=True`. Discarded full-chain warmups populate disk caches. Each worker
warms compiled helpers and its backend; first-call loads not covered by those
helpers remain timed. Three measured pairs alternate execution order. Preparation,
process startup and snapshot capture are excluded from the solve medians below;
regular backend checks and transfers are included. Full runtime snapshots and
available response fields are compared after the solves.

| Model / SuperLU baseline | Committed steps | CPU / GPU solve median | Result |
|---|---|---|---|
| Benchmark 1, 48 Quads | 20 | 0.772 / 0.838 s | Pass, GPU about 8% slower |
| Article Bridge 1, 914 Quads | 5 | 3.504 / 3.247 s | Fail accuracy/equilibrium; timing does not qualify GPU |

Benchmark 1 matches all measured response/runtime fields within `1e-9`, with
matching iterations, terminal behavior, equilibrium checks and zero phase
mismatches. Maximum measured displacement-vector difference is `1.74e-17` in
native units.

Article Bridge 1 is **not qualified**:

- Two pairs have maximum displacement differences near `6.2e-14` and zero phase
  mismatches. Residual-norm differences reach approximately `1.27e-9`, while
  internal runtime differences reach approximately `3.68e-7`. The latter occur
  in large-magnitude internal states and still fail a strictly absolute `1e-9`
  envelope.
- One pair has a displacement-vector difference of `7.019e-4` in native units,
  2,000 differing phase entries across saved states, and different iteration
  behavior. Those 2,000 entries are repeated saved-state comparisons, not a count
  of distinct damaged springs. This exceeds the requested numerical limit.
- Both backends flag unsafe equilibrium under the original `Work` criterion.
  The reported completion code therefore does not establish physical equilibrium.

An earlier same-process screen also showed variable branch behavior. Fresh
processes eliminate shared solver state as a direct carryover between samples,
but did not eliminate the observed variability. Its cause remains unresolved;
the current data do not establish whether the CPU reference, GPU candidate or
both vary across runs. The adapter remains opt-in, and no solver tolerance was
weakened to turn this comparison into a pass.

## Reproduce and inspect

Use the [GPU guide](../guides/gpu-solving.md) for installation and runner commands.
The matrix CLI accepts saved SciPy matrices and NumPy RHS arrays. The static-chain
CLI regenerates each model from its source HRX.

[Compact evidence](../../release-evidence/performance/2026-10-26-gpu-comparison.json)
contains timings, precision maxima, comparison flags, package versions and
provenance. Full local reports, logs and matrix snapshots are under ignored
`benchmark_outputs/gpu-2026-10-26/`; compact evidence records their paths/hashes
but does not embed the original HRX inputs.

Final focused regression: 69 passed and two skipped. The skips are CPU tests
specific to an absent UMFPACK library; UMFPACK is present here. All four native
CUDA tests passed. Known small-fixture `Work` equilibrium warnings remain
visible and are not treated as GPU qualification.
