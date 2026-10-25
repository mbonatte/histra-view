# Changes Made

## Solver and elements

- Implemented C#-compatible quad volume, normal stress, and `ComputeDN` behavior.
- Implemented interface normal-force increment and area correction paths.
- Coupled `dN` into in-plane and out-of-plane Coulomb03 springs.
- Changed nonlinear element update order to interfaces before quads.
- Implemented the active C# `TwoSprings` out-of-plane stiffness branch.
- Matched float32-sensitive C# self-weight and geometry calculations.
- Completed Coulomb03 normal-stress commit/revert and yield restoration.
- Recorded convergence, residual, and increment norms per step.

## State safety

- Added `SolverStateSnapshot` for complete capture, restore, and value fingerprinting.
- Added rollback to Newton, line-search, failed step, ALS substep, and ArcLength retry flows.
- Removed trial-only attributes during restore.

## Database and restart

- Added typed metadata, quad, interface, spring, displacement, and multiplier readers.
- Documented zero-based `DynamicVectorsState.Dof` indexing.
- Added strict final committed-state restoration and chained-analysis initialization.
- Rejected incomplete intermediate spring restart with precise errors.

## Load behavior

- Added explicit errors for missing analyses, combinations, rows, gravity conditions, unsupported coefficient types, and unavailable Psi data.
- Corrected unloading discretization.

## Tests and tools

- Corrected stale package paths and actual model-size assertions.
- Added focused ComputeDN, friction coupling, commit/revert, snapshot, rollback, unloading, SQLite, restart, first-step, and step-reader tests.
- Added `tools/benchmark_csharp_sqlite.py` for machine-readable per-step comparison.

## Live Load and ArcLength integration

- Added HRX parsing for `LoadTemplate`, `LoadTemplateItem`, `LineLoadElement`, and `ModelPoint`.
- Added float32-sensitive Quad line-load integration and global assembly.
- Added explicit ArcLength selected-model-point mapping and predictor cap compatibility.
- Reproduced chained `SetFextEqualToFint` initialization.
- Reproduced C# static `alfa=0` preparation and the tangent-update omission for `StandardInitialInterpolatedLineSearch`.
- Reproduced hidden base `LineSearch` dispatch and retained ArcLength's combined correction for the Work test.
- Corrected Coulomb03 `Eun` to use the maximum negative-envelope slope.
- Added sparse LU reuse while stiffness is unchanged.
- Reduced snapshot allocation overhead and bounded cyclic-GC work during nonlinear solves.
- Extended the benchmark tool to handle ArcLength references and expected terminal max-displacement stops.
- Added `test_live_load_arc_length.py`, including an optional complete 87-step acceptance test.
