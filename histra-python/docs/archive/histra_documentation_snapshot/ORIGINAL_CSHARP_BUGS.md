# Verified Original C# Bugs

## `CTestNormUnbalance.getCopy`

- File: `C#_Original/SolverRuntime/SolverRuntime.ConvergenceTest/CTestNormUnbalance.cs`
- Method: `getCopy(int iterations)`
- Defect: returns `CTestNormDispIncr` rather than a copy of `CTestNormUnbalance`.
- Intended behavior: preserve the force/unbalance convergence-test type and configuration.
- Python: corrected; not required by the selected Work-criterion benchmark.

## LoadControl unloading discretization

- File: `C#_Original/SolverRuntime/SolverRuntime.Integrator/LoadControl.cs`
- Method: increment calculation around line 137.
- Defect: `Convert.ToInt16((target-current)/discretization)` uses a signed ratio; an unloading segment can produce a negative subdivision count.
- Intended behavior: a positive finite segment count with a signed force increment.
- Python: corrected with magnitude-based subdivision and signed increment; regression tested.

## Line-search vector resize

- Files: `RegulaFalsiLineSearch.cs` and `InitialInterpolatedSearch.cs`.
- Method: `newStep`.
- Defect: when vector size differs, code assigns `x = null` and immediately calls `x.CopyFrom(dU)`, which would dereference null.
- Python: uses safe array replacement; benchmark size is constant so the C# defect is not exercised.

## Hidden InitialInterpolated methods

- File: `C#_Original/SolverRuntime/SolverRuntime.LineSearch/InitialInterpolatedSearch.cs`
- Methods: `new virtual newStep` and `new virtual search`.
- Defect: methods hide rather than override base virtual methods, risking base dispatch.
- Python: normal polymorphic overrides; not used by selected LoadControl analysis.

## Incomplete Coulomb03 database restoration

- File: `C#_Original/Objects.ElementStates/SpringStateDBclass.cs`
- Method: `SetSpring(ref Spring s, bool Envelope)` non-envelope `Coulomb03` branch.
- Defect: `CmomMin` is restored but stored `CmomMax` is omitted.
- Intended behavior: restore both committed moment extrema.
- Python: restores `CmomMax`; a lossless restart is preferred over preserving this omission.

## Regula-Falsi state/sign inconsistency

- File: `C#_Original/SolverRuntime/SolverRuntime.LineSearch/RegulaFalsiLineSearch.cs`
- Method: `search`.
- Behavior: trial updates use `(eta_j - eta_previous) * dU`, but the method finishes by putting `eta_j * dU` back into the linear-system increment after state has already accumulated trial deltas. This can make the stored increment and accumulated trial state represent different quantities.
- Python: preserves the benchmark-relevant behavior for compatibility, while complete snapshots prevent failed trials from contaminating outer state.

## Static InitialInterpolated tangent omission

- File: `C#_Original/SolverRuntime/SolverRuntime.SolutionAlgorithm/NewtonLineSearch.cs`.
- Behavior: the per-iteration tangent-update condition includes other Standard methods but omits `StandardInitialInterpolatedLineSearch`.
- Effect: the Live Load reference keeps the initial stiffness for every iteration.
- Python: preserves this compatibility behavior for committed database parity and regression tests it.

## Hidden InitialInterpolated dispatch and Work vector

- File: `C#_Original/SolverRuntime/SolverRuntime.LineSearch/InitialInterpolatedSearch.cs`.
- Defect: `new virtual` hides instead of overrides `LineSearch.search/newStep`.
- Effect: through the base reference, search is a no-op. `LS.X` remains ArcLength's combined constrained correction and is consumed by the Work convergence test.
- Python: preserves the base dispatch for this method; the intended algorithm remains constructible directly but is not used for the reference path.

## Line-load source/database skew

- C# area: Quad static line-load intrinsic-coordinate calculation (`AlignNodes`, `FindU`, `FindV`, `ComputeStaticLoadInternal`).
- Evidence: a literal source port worsens displacement agreement by approximately two orders of magnitude, while the retained float32 Newton inverse reproduces all database steps within tolerance.
- Python: follows the committed SQLite behavior and documents the deviation. This is treated as source/binary skew rather than silently asserted as a literal port.
