# C# versus Python Comparison

## Behaviors now aligned

| Area | C# reference | Corrected Python |
|---|---|---|
| Element update order | Interfaces, then quads | Same |
| Quad normal force | `Quad.ComputeDN` from connected transverse springs | Same required call chain |
| Interface normal force | Sum transverse spring force increments | Same |
| Coulomb capacity | Cohesion/friction coupled to current normal force | Same state transition under identical inputs |
| Out-of-plane interface stiffness | `CheckTorsionalModel()` always returns `TwoSprings` | Same active matrix branch |
| Load geometry arithmetic | Uses `Vector3`/single precision in key paths | Float32-compatible benchmark path |
| Virgin initialization | Clears serialized solved state | Same |
| Final restart | Global plus complete local constitutive history | Same, with strict validation |
| Failed nonlinear trials | Must be reversible | Complete snapshots and rollback |

## Earliest remaining divergence

Step 1 is effectively exact. The first material committed displacement difference is step 2. The spring laws are not the first differing quantity when supplied the exact C# step-2 inputs:

- 2,349 hysteretic springs: force and phase match; maximum force error about 2.8e-15.
- 105 Coulomb03 springs: force and phase match; force errors below 1e-13.

Python nevertheless reaches different step-2 strains through its global iterative path. The C# database only stores committed state, not each Newton/line-search trial. Therefore the first differing iteration cannot be identified directly without either instrumenting a runnable C# build or obtaining a per-iteration trace from the reference binary.

## Convergence interpretation

The benchmark uses absolute Work tolerance 1e-4. A committed state can have a large residual norm while satisfying the work test. At the exact C# step-2 state, Python's matched element laws assemble a residual norm of about 129.2. Python's own step-2 state commits at work error 9.806e-5 and residual norm 138.0. This confirms that residual minimization alone cannot be used to tune the path.

## Compatibility-sensitive C# behavior

The translated Regula-Falsi path preserves the observed C# trial/sign behavior needed for compatibility. Separate verified C# defects are documented in `ORIGINAL_CSHARP_BUGS.md`; Python corrects defects where compatibility is not required by this benchmark.
