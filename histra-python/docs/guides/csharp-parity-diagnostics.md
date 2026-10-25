# C# parity diagnostics

The nonlinear solver has an optional deterministic diagnostic stream for
comparing Python runs with a HiStrA `.Results` database. It is disabled by
default and the normal solve path does not calculate spring summaries or write
files.

## Linear solver parity

The original C# implementation calls the SuiteSparse UMFPACK `umfpack_di_*`
API, uses UMFPACK defaults, and sets control slot 5 to the symmetric strategy.
Python can now use the same native backend:

```console
set HISTRA_LINEAR_SOLVER=umfpack
set HISTRA_UMFPACK_LIBRARY=C:\path\to\umfpack.dll
pytest histra/tests
```

On Linux or macOS, point `HISTRA_UMFPACK_LIBRARY` to the corresponding native
shared library. `HISTRA_LINEAR_SOLVER=auto` selects UMFPACK when a loadable
library is found and otherwise retains SciPy SuperLU. The default is explicit
SuperLU so installing SuiteSparse cannot silently change an existing run. Use an explicit
`umfpack` selection for parity regressions so a missing native dependency fails
with an actionable error instead of silently changing the numerical backend.

The backend can also be selected per solve:

```python
code, steps = solve_static_nonlinear(
    model,
    analysis,
    combination=1,
    linear_solver_backend="umfpack",
)
```

## Routine parity and global performance validation

Original C# routines remain the source of truth for model construction,
constitutive updates and numerical control logic. Their bit-exact unit tests
stay exact. At the user's 2026-10-15 direction, global performance experiments
may use faster numerical libraries/orderings with small rounding differences
when the physical response is preserved.

Use explicit backend, precision, refinement and ordering settings in every
comparison report. The exact Dhir reference configuration uses UMFPACK,
accurate precision, refinement 2 and AMD ordering; Python's UMFPACK default
ordering is METIS. Pin AMD explicitly when reproducing that exact reference.
SuperLU and other orderings can be screened as performance candidates while
retaining identical model inputs and solver logic.

A performance screen must record the complete available load-displacement and
reaction histories, energy differences, stopping behavior and local/spring
phase differences. A matrix solve speedup alone does not qualify a nonlinear
analysis. State the numeric envelope before screening and keep the original
routine tests unchanged. Current experiments initially screen global response
with displacement rtol=1e-6 / atol=1e-8 in native model units, and energy
rtol=1e-6 / atol=1e-6 in native energy units. Global reaction vectors use
L2(error) <= 1e-5 kN + 1e-8 * max(L2(reference reaction), 1 kN). This compares
forces on a physical vector scale when an individual component is near zero;
the original resultants include Single arithmetic. The earlier componentwise
screen and its failures remain in the experiment record. These are experiment
limits, not blanket acceptance criteria for other models. An unchanged physical
failure mode and the final stopping state still require examination. The
[2026-10-15 library screen](../benchmarks/faster-linear-library-screen-2026-10-15.md)
records a concrete counterexample: fast UMFPACK stops the horizontal model
seven commits early despite extremely close response in the earlier steps.

## Deterministic event stream

```python
from histra.solver.diagnostics import DiagnosticOptions
from histra.solver.solve import solve_static_nonlinear

options = DiagnosticOptions(
    output_dir="parity/vert",
    capture_vectors=True,
    capture_matrices=False,
    capture_element_states=False,
    spring_details=True,
    flush_each_event=True,
)

code, steps = solve_static_nonlinear(
    model,
    analysis,
    combination=1,
    diagnostics=options,
    linear_solver_backend="umfpack",
)
```

`events.jsonl` records analysis, step, Newton-iteration, snapshot, restore,
commit, automatic load-step reduction, failure, and timing events. It includes
load factors, arc-length data, convergence metrics, governing residual and
correction DOFs, spring-phase counts, and stable spring identities of the form:

```text
(ParentType, ParentKey, SpringPurpose, IdLocal)
```

Enable `capture_vectors` to write displacement, correction, residual, external
load, target load and internal force arrays as compressed NPZ snapshots.
Enable `capture_matrices` to include the CSC tangent matrix. Enable
`capture_element_states` to include all spring states plus Interface and Quad
local displacement arrays.

Full element-state capture is intentionally expensive for large models. Narrow
it to selected regression runs or steps after a lightweight event-only run has
identified the first suspicious step.

## Compare with C# results

```console
python -m histra.tools.compare_csharp_results state \
  parity/vert/vectors/event_000042_step_00010_iter_00006_committed.npz \
  first-bridge.Results 1 10 --combination 1 \
  --output parity/vertical-step-10.json

python -m histra.tools.compare_csharp_results history \
  first-bridge.Results 3 parity/csharp-live-history.csv --combination 1
```

The state comparator joins springs by the stable C# database identity and
compares spring strain, stress and phase as well as Interface and Quad local
states when present.
