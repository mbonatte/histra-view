# Faster CPU analyses

The solver uses compiled Numba kernels and a compiled sparse linear solver.
Fresh preparation and compiled coverage checks remain mandatory. Performance
changes do not alter constitutive laws, convergence tolerances or authored
analysis strategies.

## Running one model

The high-level `run_python_solver_job(...)` API and
`python -m histra.tools.run_vert_live` automatically skip saved computational
state when loading HRX inputs. For direct sessions, use the solver loader:

```python
from histra import AnalysisSession, load_solver_model

model = load_solver_model("bridge.hrx")
session = AnalysisSession(model, equilibrium_policy="error")
result = session.run("Vert")
```

`load_solver_model` keeps structural geometry, reference axes, materials, loads,
restraints and analysis definitions. It omits saved interfaces, springs,
afference matrices and Quad displacement history, which fresh preparation
reconstructs. Use `load_model` to inspect those C# reference snapshots.
Both loaders preserve the source HRX file and require fresh preparation.

Virgin static solves construct their compiled runtime after state initialization.
Dependency checks run first; full object coverage is enforced before numerical
execution. Restarts and material mutations retain lifecycle coverage checks.
Interface fibre stiffness preparation reuses face projections across fibres with
the original C# float32 operation order.

## Faster dense result export

Dense output projects all Quad corners in NumPy batches and reuses those results
for node averaging. Geometry and afference maps are prepared once per export,
with the original C# float32 rounding and connected-Quad summation order.
The plan is rebuilt for each export so later model changes cannot leave stale
geometry or afferences in the output. Existing result schemas and array layouts
are preserved.

This accelerates `.histra`, NPZ and HDF5 field construction. Compression and
storage still contribute to total export time. Summary-only output does not
construct these dense fields. See the identified
[Scozzese export measurements](../benchmarks/scozzese-export-2026-10-27.md)
for timing and exact-array comparisons. This optimization does not change Newton
iterations, sparse factorization or convergence behavior.

## Running independent models together

`run_parallel_solver_jobs` launches independent CPU jobs in separate processes.
Each job may contain a dependent analysis chain; that chain stays sequential.
The parent only coordinates workers, avoiding shared solver runtime arrays.

```python
from histra import PythonAnalysisRequest, PythonSolverJob, run_parallel_solver_jobs

requests = (PythonAnalysisRequest("Vert", output_request=None, timeout_seconds=300),)
jobs = [PythonSolverJob(path, requests, timeout_seconds=600)
        for path in ("bridge_a.hrx", "bridge_b.hrx")]
outcomes = run_parallel_solver_jobs(jobs, max_workers=2, threads_per_worker=1)
for path, outcome in zip(("bridge_a.hrx", "bridge_b.hrx"), outcomes):
    if outcome.completed:
        print(path, outcome.result.analyses["Vert"].execution.outcome)
    else:
        print(path, outcome.error)
```

The command-line entry point runs the same API with strict equilibrium checks:

```bash
python -m histra.tools.parallel_solver_jobs bridge_a.hrx bridge_b.hrx --analysis Vert --workers 2 --threads 1 --output batch-summary.json
```

This command writes an execution summary; use the Python API when you need the
returned execution histories or projected output rows.

Results preserve input order, including individual failures. Each worker starts
with Numba and BLAS thread limits before importing numerical libraries. By default
at most two workers run; available CPU cores also cap concurrency. Optional
`memory_budget_mb` and `estimated_job_memory_mb` together reduce worker count.
These are scheduling estimates, not enforced memory limits.

Batch job deadlines include startup, loading and preparation, and a worker that
exceeds its deadline is terminated. The existing in-process API retains cooperative
cancellation. A fresh interpreter per job prevents runtime state from leaking
between models, but startup and result transfer can outweigh parallelism for tiny
jobs. The batch runner explicitly selects the CPU backend.

Use pickle-compatible output request objects defined in importable modules, or
`None` when only execution histories are needed. Keep callbacks in the existing
single-job API. The private worker transport is not an input-file format.

See the [CPU workflow measurements](../benchmarks/cpu-workflow-2026-10-26.md) for
identified models, timing methodology and numerical comparisons.

## Giving one large model a faster native runtime

`run_large_model` allocates separate thread teams to compiled element updates
and sparse-factor BLAS. It starts a fresh process so native library selection
and thread limits take effect before SuiteSparse loads. Its default sparse
backend remains CPU `auto`; authored methods and tolerances remain unchanged.

On an apt-based x86_64 Linux machine, install the optional OpenBLAS runtime once
into the active virtual environment, without changing system libraries:

```bash
python -m histra.tools.setup_openblas
python -m histra.tools.run_large_model my_model/profiling/dhir_bridge_model.hrx --output large_results
```

The default budgets are eight kernel threads and four BLAS threads, capped by
the CPUs available to the process. These are measured starting points, rather
than a promise of optimal settings on every processor. Override them with
`--kernel-threads` and `--blas-threads`. In the recorded 47,768-DOF screen,
four BLAS threads outperformed twenty. Higher CPU utilization can cost more
synchronization time than it saves.

The installer uses the distribution's `libopenblas0-pthread` package and keeps
its libraries and license files inside the virtual environment. Existing system
packages are untouched. The worker rejects an incompatible ILP64 native BLAS;
SuiteSparse requires the LP64 ABI, independently of NumPy's own BLAS ABI.
For another compatible installation, supply `--blas-directory`.

A completed run writes a `.histra` results bundle and `run_summary.json`, including
the actual loaded library paths and resource budgets. Generalized displacements
and stage snapshots are saved; full node-displacement projection is omitted.
The default one-hour deadline includes preparation, solving and export.
Cooperative cancellation/failure exports committed work as a partial bundle.
Workers reserve up to 30 seconds for that export; the hard process deadline
still applies. `run_summary.json` distinguishes partial output from completion.

The equivalent Python API is:

```python
from histra import PythonAnalysisRequest, PythonSolverJob, SolverResources, run_large_solver_job

job = PythonSolverJob(
    "bridge.hrx",
    (PythonAnalysisRequest("Vert", None, 3600),),
    timeout_seconds=3600,
    output_directory="large_results",
)
outcome = run_large_solver_job(job, resources=SolverResources(kernel_threads=8, blas_threads=4))
```

The runner also accepts explicit `--backend cholmod` or experimental
`--backend cudss`. CHOLMOD requires suitable stiffness matrices and can fall back
to LU. GPU use requires the optional cuDSS dependencies and a process with GPU
device access. Backend changes require complete response/stop validation on the
chosen model: a tiny linear-system error alone does not establish nonlinear
branch equivalence. Standard in-process and ordinary batch APIs keep their
previous native-library selection.

See the [large-model capacity measurements](../benchmarks/large-model-capacity-2026-10-26.md)
for timings, precision scope and the distinction between refactorization and
complete analysis time.

## Modal setup and CPU factorization screening

Virgin modal sessions initialize state before building their compiled runtime.
Modal stiffness scatter uses compiled loops while preserving its original COO
contribution and reduction order. See the [modal guide](modal-analysis.md) and
[Scozzese measurements](../benchmarks/scozzese-modal-cpu-2026-10-27.md).

The existing `--backend cholmod` option is a separate CPU Cholesky alternative
for symmetric positive-definite stiffness matrices. It can fall back to native
LU when definiteness is lost; record the actual factor backend when evaluating
it. The default `auto` choice remains unchanged. The Scozzese screen matched
18 accepted steps through 90% load, including strict equilibrium checks, but
does not qualify the unresolved 95% step or complete constitutive state history.
Qualify the complete response before adopting that setting for a new model.
