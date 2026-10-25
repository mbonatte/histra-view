# Modal analysis

## Scope

The Python solver implements the active C# HiStrA modal workflow for the
currently supported Quad/Interface computational model. It supports:

- virgin modal analyses (`InitialAnalysisKey < 0`);
- modal analyses at a committed nonlinear predecessor state;
- the C# `SubspaceIterations` algorithm;
- the C# sequential `InverseIterations` algorithm;
- mass-normalized mode shapes;
- frequencies, periods, participation coefficients, effective modal masses,
  mass percentages, directional maximum components and eigen-residuals;
- C#-compatible `ModalValues` and `ModalShapeValues` row projection.

Dynamic time-history analysis remains outside this implementation.

## C# execution path inspected

The implementation was reconstructed from the current source, principally:

- `SolverRuntime/Program.cs`
- `SolverRuntime/ModelManager.cs`
- `SolverRuntime.AnalysisProcedure/ModalAnalysis.cs`
- `SolverRuntime/Pseudovectors.cs`
- `Objects/Quad.cs`
- `ModelLibrary.MacroKernel.MacroMath/Matrix.cs`
- `SolverRuntime/CommonOperations.cs`
- `Objects.ElementStates/ModalValues.cs`
- `Objects.ElementStates/ModalShapeValues.cs`

The active sequence is:

1. `Program` calls `ModelManager.PrepareModelForAnalysis`.
2. `SetStatus` initializes a virgin model or restores the configured predecessor.
3. `PrepareK(..., alfa=1)` assembles the current tangent stiffness matrix.
4. `ModalAnalysis.Execute` calls `ModelManager.ComputeM`.
5. The requested mode count is limited to `min(NumberOfEigenModes, N - 2)`.
6. The configured modal eigensolver is executed.
7. Each mode is mass-normalized before modal quantities are evaluated.
8. `ModalValues` and one `ModalShapeValues` row per zero-based global DOF are saved.

## Mass matrix

For each Quad, C# creates an eight-node volume by offsetting the four mid-surface
nodes by `+/- normal * thickness / 2`. It integrates

```text
M_e = integral rho * V(q)^T * V(q) dV
```

with a 6 x 6 x 6 Gauss rule, where `rho = material.w / g`. C# stores both
`material.w` and `Operations.g` as `System.Single` before promoting them to
double; the promoted gravity is `980.5999755859375`. Existing local loads
contribute `abs(P[i] / g)` to the corresponding diagonal term. Python preserves
these input conversions. Direct native-routine coverage isolates the
translational mass block; exact rotational integration arithmetic remains an
audit item.

For HiStrA modal execution, the original load generator uses `(1, 1, 1)`
as the direction of direct line loads, irrespective of their static direction
or the saved analysis direction. It then multiplies each component by the
load condition's `MassInDirX/Y/Z` factors using Single arithmetic. Python
applies these factors before integration and regenerates the modal loads
rather than inheriting the static predecessor's applied loads.

A compatibility-sensitive source behavior is preserved: the HRX
`MassMatrixType` and the method's `diagonal` argument are passed through the C#
call chain, but the active Quad routine never uses them. Consequently, an HRX
that says `MassMatrixType="Lumped"` still receives the integrated consistent
Quad mass matrix. Python reports both the requested and effective types.

C# Quad mass assembly also scatters each local coefficient to all afference DOF
pairs without multiplying by the afference `Alfa` values. Python reproduces this
behavior exactly.

## `SubspaceIterations`

`Matrix.SubSpaceIteration2` is ported rather than replaced with a generic
black-box eigensolver. For `n` requested modes it uses a subspace of

```text
min(n + 8, 2*n, total_DOF)
```

vectors, initialized with the legacy .NET `System.Random(0)` sequence. Every
iteration performs:

```text
Y = M X
Z = K^-1 Y
Kr = Z^T K Z
Mr = Z^T M Z
Kr q = lambda Mr q
X = Z q
```

Convergence is based on the sum of absolute changes in the first requested
eigenvalues, divided by that sum from the first iteration and multiplied by
100. Iteration stops when this value is no greater than the HRX
`ConvergenceTolerance`. The C# routine has no iteration limit; Python adds a
1000-iteration safety limit with an explicit error.

This stopping rule is based on eigenvalue changes, not an eigen-residual. It can
therefore retain visibly larger residuals in upper modes. That behavior is
preserved for C# result parity and each Python mode exposes `residual_norm` so it
can be assessed explicitly.

## `InverseIterations`

C# 2026.1.1 uses `EigenvalueSolver.SolveByInverseIterationLegacyLike`.
Python now follows its seeded starting vectors (`System.Random(12345)`),
Euclidean deflation, Rayleigh quotient and mass normalization. The selected
linear backend is reused across iterations, with one stiffness factorization.

Both convergence gates must pass after at least two iterations:

- relative eigenvalue change <= `max(1e-12, ConvergenceTolerance / 100)`;
- `||K phi - lambda M phi|| / (||K phi|| + |lambda| ||M phi|| + 1e-30)`
  <= `ResidualVectorTolerance`.

The HRX residual tolerance defaults to 0.5. A nonpositive value selects the
C# framework fallback of 1e-6. `ModalConvergenceCriteria` is retained in
the input; the new framework applies both gates regardless of that selector.
Already converged modes are retained if a later mode exhausts its iterations.

Unit fixtures execute the unmodified C# inverse-iteration routine on small
matrices, including coupled mass and partial convergence. Full-model comparison
against C# 2026.1.1 modal `.Results` remains pending.

The `SubspaceIterations` implementation below still follows the older C#
routine. The 2026.1.1 shared subspace implementation and its additional
`SparseBlockInverseSubspace` and `InverseIterationMassOrthogonal` procedures
remain to be ported; the two additional procedures are rejected explicitly.
Full modal parity with 2026.1.1 is not yet established.

## Modal quantities

For each mass-normalized shape `phi` and direction pseudovector `e_d`:

```text
M_e,d = M e_d
M_total,d = e_d^T M e_d
Gamma_d = phi^T M e_d
M_modal,d = Gamma_d^2
MassPercent_d = 100 * M_modal,d / M_total,d
```

The directional pseudovectors reproduce C# assignment semantics: the first
entry of each Quad translational afference is assigned to the corresponding
global DOF. `Umax` is the maximum of `abs(phi[j] * e_d[j])`.

C# 2026.1.1 `InverseIterations` preserves discovery order and eigenvector sign.
Python retains that order and sign because mode numbers and signed participation
factors are observable outputs. `SubspaceIterations` retains its existing
frequency ordering and largest-component-positive archive convention.

## Python API

```python
from histra import load_model, solve_modal_analysis

model = load_model("Ersino.hrx")
analysis = model.collections.analyses[30]
result = solve_modal_analysis(model, analysis)

print(result.frequencies)
print(result.modal_values_rows())
mode_shapes = result.mode_shapes  # shape: (GDL, number_of_modes)
```

For a chained analysis loaded directly from disk:

```python
result = solve_modal_analysis(
    model,
    model.collections.analyses[21],
    results_path="Ersino.Results",
)
```

`AnalysisSession.run(...)` dispatches `AnalysisType=5` automatically and keeps
the predecessor physical state available for a later chained analysis.

## Command line

```console
python -m histra.tools.run_modal Ersino.hrx \
  --analysis Modal_-1 \
  --output modal-summary.json \
  --shapes modal-shapes.npz
```

For a modal analysis with a predecessor, also pass `--results model.Results`.

### Batch C#/Python validation

`run_modal` also accepts a directory, multiple inputs, or a wildcard. In batch
mode each HRX is paired automatically with a same-stem C# results database in
the same directory (`Bridge01.hrx` -> `Bridge01.Results`). For example on
Windows:

```console
python -m histra.tools.run_modal my_model\modal-tests\* --analysis 30
```

Passing the folder directly is equivalent and avoids shell wildcard differences:

```console
python -m histra.tools.run_modal my_model\modal-tests --analysis 30
```

For every model the runner:

1. **regenerates the computational interfaces and springs with Python by default**,
   even when the HRX was already prepared by C#;
2. executes the Python modal analysis;
3. reads all C# `ModalValues` for the selected analysis;
4. compares all stored modal summary fields with configurable `--rtol` and
   `--atol` tolerances;
5. compares `ModalShapeValues` with a sign- and scale-invariant Modal Assurance
   Criterion (MAC);
6. writes a per-model Python summary and comparison JSON;
7. writes consolidated `comparison.json` and `comparison.csv` reports.

This forced regeneration is intentional: otherwise an HRX that has already been
run by C# contains C#-generated springs, so the test would validate only the
Python eigensolver and could miss Python preprocessing errors. Use
`--preprocessing stored` when that narrower solver-only check is desired, or
`--preprocessing auto` to prepare only HRX files that are not solver-ready.

By default the reports are stored under `modal-comparison` in the common model
directory. The process exits with code 0 only when every discovered model has a
C# reference and passes. Use `--no-compare-shapes` to skip the potentially large
mode-shape database read, `--save-shapes` to retain Python NPZ mode vectors, or
`--results-dir` if the C# databases live in another directory.

The default comparison uses stricter primary tolerances for frequencies/periods
(`--frequency-rtol 1e-4`, `--frequency-atol 1e-6`) and total directional mass
(`--mass-rtol 1e-4`, `--mass-atol 1e-6`). Participation, effective-mass, mass-
percentage and maximum-component fields use a mixed `--rtol 5e-3` /
`--atol 1e-4` test because near-zero modal quantities otherwise produce
meaningless relative errors. The default mode-shape threshold is
`--min-mac 0.999`.

## C# database validation

```console
python -m histra.tools.validate_modal_results \
  Ersino.hrx Ersino.Results --analysis-key 30 \
  --output modal-validation.json
```

The validator compares every stored modal summary field and computes a
sign- and scale-invariant MAC for each corresponding mode in
`ModalShapeValues`. `GammaX/Y/Z` are compared by magnitude because the global
sign of an eigenvector is arbitrary.

## Ersino regression

The supplied Ersino model contains 14,252 active DOFs and requests ten modes for
analysis key 30. The real-file integration test verifies:

- directional total mass against C# within `3e-8` relative tolerance;
- all ten frequencies within `3e-8` relative tolerance;
- diagonal mass-weighted mode correlations above `0.9999999`;
- all 142,520 stored C# modal-shape values are represented.

Run it with:

```console
HISTRA_MODAL_HRX=/path/Ersino.hrx \
HISTRA_MODAL_RESULTS=/path/Ersino.Results \
python -m pytest -q histra/tests/test_modal_analysis.py
```

## Current boundary

The mass implementation covers the model entities currently represented by the
Python domain: Quads carry mass and Interfaces do not. Future Vertex, Solid,
Frame or Fiber collections are rejected explicitly until their C# mass routines
are ported. The code does not silently discard unsupported element masses.


The recorded [Dhir 2026.1.1 modal comparison](../benchmarks/dhir-modal-native-parity.md) covers virgin default masonry and all 20 saved modes.
