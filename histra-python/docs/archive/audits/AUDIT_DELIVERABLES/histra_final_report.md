# HiStrA Python/C# Integration — Final Report

## Outcome

The corrected Python project now executes the complete five-step C# LoadControl benchmark represented by `model-output/model.Results`. It commits steps 1–5 in the exact order at load factors 0.2, 0.4, 0.6, 0.8, and 1.0, with no NaN or infinite values. The measured full-run time was 34.45 seconds.

Full numerical equivalence is **not achieved**. Step 1 matches the C# committed displacement vector to roundoff, but steps 2–5 follow a different nonlinear path and exceed the requested relative displacement tolerance.

## Baseline status

- Python compile: passed.
- Package import: passed.
- Untouched tests: 84 passed, 12 failed. The failures were stale path/model assertions referring to a different package revision.
- Untouched benchmark: committed step 1, then did not commit step 2 within 120 seconds.
- Untouched step-1 relative displacement error: 2.214e-3.
- Untouched step-1 maximum absolute DOF error: 9.013e-6.

## Final status

- Python compile: passed.
- Package import: passed.
- Tests: 114 passed, 1 skipped, 0 failed, 0 warnings.
- The skip is the opt-in long full-analysis acceptance test; the full benchmark was run separately and recorded in JSON.
- Complete Python analysis: completed, code 0, five committed steps.

## C# analysis selected

- Analysis key: 1.
- Name: `Vert`.
- Database combination: 1.
- HRX load-combination key: 6, row 1.
- Integrator: `LoadControl`.
- Algorithm: `ModifiedRegulaFalsiLineSearch`.
- Convergence: absolute Work, tolerance 1e-4, maximum 1,000 iterations.
- Load function: 0.0 to 1.0 in increments of 0.2.
- P-Delta: none.
- ALS: disabled.
- Initialization: virgin (`InitialAnalysisKey = -100`).

The uploaded benchmark is a 126-DOF model with 28 nodes, 18 quads, 29 interfaces, 2,349 hysteretic springs, and 105 Coulomb03 springs. Prior package reports describing a 2,142-DOF model were stale.

## Numerical results

| Step | Load factor | Iterations | Work error | Residual norm | Relative displacement error | Maximum absolute DOF error | Result |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 0.2 | 3 | 8.474e-5 | 67.053 | 1.311e-14 | 6.365e-17 | Accepted |
| 2 | 0.4 | 11 | 9.806e-5 | 138.027 | 5.930e-2 | 7.257e-4 | Rejected |
| 3 | 0.6 | 16 | 9.901e-5 | 182.577 | 1.799e-1 | 3.338e-3 | Rejected |
| 4 | 0.8 | 7 | 6.155e-5 | 264.305 | 1.915e-1 | 4.313e-3 | Rejected |
| 5 | 1.0 | 38 | 8.777e-5 | 217.032 | 1.153e-1 | 5.408e-3 | Rejected |

All load-factor errors are below 1e-15. Step count and ordering are exact.

## Code changed

- Ported C# `Quad.ComputeDN`, quad volume, normal-stress, and normal-force bookkeeping.
- Added interface normal-force calculation and coupling into in-plane/out-of-plane Coulomb03 springs.
- Matched C# interface-before-quad nonlinear update order.
- Implemented the active C# `TwoSprings` out-of-plane interface stiffness branch.
- Matched float32-sensitive C# geometry and self-weight calculations.
- Completed Coulomb03 normal-stress/yield commit and revert behavior.
- Added full solver-state snapshots and rollback for Newton, line search, failed steps, ALS substeps, and ArcLength retries.
- Added typed SQLite metadata/global/quad/interface/spring readers.
- Added strict complete final-state restart and chained-analysis initialization.
- Added explicit errors for missing/unsupported load metadata and corrected unloading discretization.
- Added a reproducible benchmark command and focused integration tests.
- Updated all requested audit, architecture, comparison, benchmark, restart, feature, issue, testing, limitation, and remediation documentation.

## Direct evidence about the remaining blocker

The complete Python committed step-1 state matches the C# database, including all 2,454 spring histories, to approximately 1e-12 or better. Starting from that state:

- Applying exact C# step-2 strains to all 2,349 hysteretic springs reproduces C# force and phase; maximum force difference is about 2.8e-15.
- Applying exact C# step-2 strains and normal-force increments to all 105 Coulomb03 springs reproduces C# force and phase; errors are below 1e-13.

Therefore the remaining discrepancy is not the constitutive transition under identical input. It lies in the global step-2 Newton/Regula-Falsi numerical path, or in a difference between the supplied decompiled source and the C# binary that generated the database. The SQLite database contains committed states but no per-iteration vectors, and the audit environment does not contain a runnable original C# native UMFPACK stack. That prevents a direct trial-by-trial comparison at the remaining boundary.

## Verified C# defects

- `CTestNormUnbalance.getCopy` returns the wrong convergence-test class.
- LoadControl unloading subdivision uses a signed Int16 ratio that can produce invalid negative counts.
- Regula-Falsi and InitialInterpolated vector resize paths null a vector before copying into it.
- InitialInterpolated methods hide rather than override the base methods.
- `SpringStateDBclass.SetSpring` omits stored `CmomMax` in non-envelope Coulomb03 restoration.
- Regula-Falsi can leave the stored increment inconsistent with the trial state accumulated through delta-eta updates; Python preserves benchmark-relevant behavior but protects failed paths with complete snapshots.

## Remaining limitations

- Steps 2–5 do not meet C# displacement parity.
- Intermediate restart is rejected because `SpringStatesTmp` lacks complete constitutive history.
- Non-gravity applied-load object families, P-Delta, modal/dynamic analysis, and accepted ArcLength parity remain unsupported or unvalidated.
- Python does not yet write a complete C#-compatible `.Results` database.

## Exact commands

Run from the directory containing the `histra` folder:

```bash
python -m compileall -q histra
python -c "import histra; print('import ok')"
python -m pytest -q
python -m histra.tools.benchmark_csharp_sqlite \
  --hrx histra/model-output/model.hrx \
  --results histra/model-output/model.Results \
  --analysis 1 --combination 1 \
  --output histra_benchmark_metrics.json
```
