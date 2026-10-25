# Audit Report

## Scope and source of truth

The audit used:

- Python source at the project root.
- Original C# source under `C#_Original/`.
- Tests under `tests/`.
- Model `model-output/model.hrx`.
- Reference database `model-output/model.Results`.
- Existing reports and patches as leads only, not as numerical authority.

The C# SQLite database is the primary committed numerical reference. JSON and HRX-embedded displacement values were not treated as independent benchmarks.

## Package inventory

The actual model contains 126 global DOFs, 28 nodes, 18 quads, and 29 interfaces. The active spring population is 2,349 hysteretic transverse springs plus 105 `SpringCoulomb03` sliding springs. The HRX contains analyses 1 and 21–32, load combinations 1–11 and 15, load conditions 1–11, and load functions 1–32.

The database contains only analysis key 1, database combination 1, committed steps 0–5. Analysis 1 is named `Vert` and uses:

- HRX load-combination key 6, row/database combination 1.
- `LoadControl`.
- `ModifiedRegulaFalsiLineSearch`.
- absolute `Work` convergence tolerance 1e-4.
- maximum 1,000 iterations.
- load function 0.0 to 1.0 in increments of 0.2.
- no P-Delta and no ALS.
- virgin initialization (`InitialAnalysisKey = -100`).

## Clean baseline

- All Python modules compiled and the package imported.
- Untouched suite: 84 passed and 12 failed. The failures were stale path/model assertions, not twelve independent solver defects.
- With only a path compatibility aid: 94 passed and 2 stale model-size assertions failed.
- Untouched benchmark: step 1 committed, then step 2 exceeded 120 seconds without committing.
- Untouched step-1 relative displacement error: 2.214e-3.
- Untouched step-1 maximum absolute DOF error: 9.013e-6.

## Final measured state

- Full suite: 113 passed, 1 skipped.
- The skip is the opt-in long full-analysis acceptance test; the benchmark itself was run separately and recorded in JSON.
- Full analysis completes all five C# step numbers in order with exact load factors and finite values.
- Step 1 meets the 1e-4 displacement criterion by a wide margin.
- Steps 2–5 do not meet it; full equivalence is not claimed.

## Evidence narrowing the remaining discrepancy

1. Python's complete committed step-1 displacement, element, and spring state matches C# to roughly 1e-12 or better.
2. Applying exact C# step-2 strains to that state reproduces all 2,349 hysteretic spring forces and phases; maximum force difference was about 2.8e-15.
3. Applying exact C# step-2 strains and `dN` values reproduces all 105 Coulomb forces and phases; differences were below 1e-13.
4. The exact C# step-2 committed state has a substantial force residual when reassembled, which is consistent with C# committing on its absolute Work criterion rather than residual norm.
5. Alternative SuperLU ordering and pivot options and tested line-search sign variants did not move Python to the C# step-2 branch.
6. The SQLite database has no per-iteration state, so the exact first differing trial cannot be read from it.

The unresolved boundary is the global Newton/Regula-Falsi execution path beginning in step 2, potentially including native UMFPACK numerical behavior or source/binary version skew.
