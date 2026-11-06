# Experimental GPU sparse solving

Normal CPU execution automatically uses the compiled moment-arm geometry path;
no new option is needed to benefit from that optimization. Keep using
`AnalysisSession(model)` for CPU analyses. To explicitly select hardware, the
same API accepts `linear_solver_backend="cpu"` or `linear_solver_backend="gpu"`.

The opt-in `cudss` (`gpu`) backend accelerates static stiffness factorization and linear
solves using NVIDIA cuDSS through nvmath-python. Geometry preparation, assembly,
element/spring updates and nonlinear control remain on the CPU, using the same
compiled Numba coverage requirements. Modal analysis still uses its CPU path.
The default `auto` selection is unchanged and never chooses a GPU.

This backend is experimental. CUDA execution is tested on an RTX 4060 Laptop;
model-specific accuracy and timing evidence is recorded in the
[CPU/GPU optimization report](../benchmarks/cpu-gpu-fast-mode-2026-10-26.md). Existing CPU/C#
qualification does not automatically qualify this backend or unmeasured models.

## Install and select

On a machine with a supported NVIDIA GPU and working CUDA 12 driver:

```bash
python -m pip install -e '.[gpu-cu12]'
nvidia-smi
```

For other CUDA versions, install the matching dependencies according to
[NVIDIA's installation guide](https://docs.nvidia.com/cuda/nvmath-python/latest/installation.html).
The optional dependency supports nvmath-python 0.9 through 1.x. A successful
package import alone does not prove GPU availability; backend preflight performs
a small CUDA solve. Missing packages, driver errors and numerical failures are
reported explicitly, with no CPU fallback.

```python
from histra import AnalysisSession, load_model
from histra.solver import ModelManager

model = load_model("model.hrx")
ModelManager.prepare_model(model, force=True)
session = AnalysisSession(model, linear_solver_backend="gpu")
execution = session.run("Vert")
```

Alternatively set `HISTRA_LINEAR_SOLVER=gpu` (`cudss` remains supported). Explicit per-analysis/session
backend arguments override this environment variable.

The adapter retains float64 precision and passes the original matrix as a general,
full sparse system, without symmetrization or positive-definiteness assumptions.
It reuses numerical factors for new right-hand sides and symbolic analysis when
only matrix values change. Topology changes create a new plan. Matrix resets
preserve loads, and closing the linear system releases cuDSS resources.
When the CUDA 12 wheel supplies `libcudss_mtlayer_gomp.so.0`, the adapter enables
it automatically for cuDSS's CPU planning work.

GPU execution now defaults to the deterministic cuDSS profile, which was
bit-repeatable in the measured bridge runs. Determinism does not guarantee
agreement with the CPU nonlinear path. The larger bridge remains unqualified;
CPU execution remains the default.

For controlled experiments, `HISTRA_CUDSS_MODE=refined` enables three iterative
refinement corrections, while `HISTRA_CUDSS_MODE=default` reproduces the original
non-deterministic library profile. The installed cuDSS 0.8 cannot combine native
iterative refinement with deterministic execution. Refinement did not resolve
the larger bridge's branch sensitivity, so these profiles are diagnostic
alternatives rather than automatic upgrades.

The implementation follows NVIDIA's
[stateful DirectSolver interface](https://docs.nvidia.com/cuda/nvmath-python/latest/host-apis/sparse/generated/nvmath.sparse.advanced.DirectSolver.html).
Host CSR matrices and NumPy vectors use explicit blocking CUDA execution;
reported wall times include uploads, downloads and synchronization. This first
implementation favors integration with the existing CPU runtime over keeping
the entire analysis on the device. Large systems can exhaust GPU memory.

## Compare identical sparse systems

```bash
python -m histra.tools.gpu_solver_benchmark \
  --size 10000 --repeats 5 --output outputs/gpu-matrix.json
```

The default matrix is synthetic and cannot establish structural-analysis
performance. Supply an actual SciPy sparse `.npz` and NumPy RHS `.npy` to measure
an assembled stiffness system:

```bash
python -m histra.tools.gpu_solver_benchmark \
  --matrix stiffness.npz --rhs residual.npy --cpu-backend umfpack \
  --repeats 5 --atol 1e-9 --rtol 1e-9 --output outputs/gpu-matrix.json
```

Reports separate cold startup from warmed samples and measure first
factorization/solve, reused-factor solve, and numeric refactorization/solve on
the same sparsity pattern (values scaled by 1.01). Every measured solution,
including startup and reuse/refactor phases, is checked against the CPU
reference and against its original linear equation. No sparse matrix is made
dense. CPU backends can be SuperLU or UMFPACK.

## Compare fresh static analysis histories

```bash
python -m histra.tools.gpu_analysis_benchmark model.hrx \
  --analysis Vert --cpu-backend umfpack --repeats 3 \
  --atol 1e-9 --rtol 1e-9 --output outputs/gpu-analysis.json
```

The target includes HRX-defined predecessors. Every run loads the source afresh
and prepares with `force=True` in a new spawned process. Runs are sequential
because solver state is process-wide. Each backend receives a discarded
fresh-chain warmup to populate disk caches; every worker also warms the compiled
helpers and backend before measurement. First-call loads not covered by those
helpers remain included in solve time. Measured pairs alternate execution order
across repeats. Reports record preparation,
observed solve wall time, capture overhead, and solve time excluding that
overhead. Preflight and warmup are excluded from measured solve time; regular
in-solve backend checks and host/device transfers are included.
Reports additionally include total load/prepare/solve medians and zero-tolerance
CPU-to-CPU and GPU-to-GPU repeatability checks. Total times exclude worker startup,
explicit warmup, and snapshot capture; they are not process-launch latency.

Every available step displacement, reaction, load factor, energy and residual
is compared. Committed compiled runtime snapshots are compared at their native
precision, together with exact spring phase labels. Terminal analysis outcomes,
step counts, iteration counts and equilibrium flags must agree. A reported
`passed` also requires nonempty committed histories and passing equilibrium
audits on both sides. Matching nonconverged terminal outcomes can be useful
differential evidence; a comparison pass does not imply successful completion
or qualify an unmeasured model. Private state outside the compiled snapshot
contract is not audited.

Snapshots are held in memory for both histories, so long chains can require
substantial RAM. Use `--max-steps 2` for an initial smoke test; such reports are
marked partial and do not qualify a complete response. Chains requiring custom
foundation assignments or interface-material mutations need an explicitly
authored comparison harness; the generic CLI does not infer those operations.
It rejects modal chains.

The initial envelope is componentwise
`abs(candidate-reference) <= atol + rtol*abs(reference)`, with both defaults
`1e-9`. Set `--rtol 0 --atol 1e-9` for a strictly absolute limit. Absolute
differences use each field's internal/native units, which differ between
displacements, rotations, forces and energies. Relative Linf is maximum absolute
error divided by the reference's maximum absolute value; it is undefined (JSON
`null`) for a nonzero error against an all-zero reference. Phase changes are
reported even when floating-point fields satisfy the envelope. Existing exact
routine tests and solver stopping thresholds remain unchanged.

Both commands write JSON provenance and return exit code 2 when the comparison
fails or CUDA is unavailable. Native CUDA tests can be run with:

```bash
python -m pytest -m gpu histra/tests/test_cudss_solver.py histra/tests/test_gpu_benchmarks.py
```

They skip when CUDA is unavailable. CPU-based adapter tests exercise lifecycle
and reporting contracts; they are not evidence of CUDA numerical performance.
