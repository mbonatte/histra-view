# Benchmark Results

## Final full run

Completion code: 0. Runtime: 34.450 seconds. Committed steps: 1, 2, 3, 4, 5. All values finite.

| Step | LF | Iter. | Work error | Residual norm | Increment norm | Relative U error | Max abs U error |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.2 | 3 | 8.474e-5 | 6.705e1 | 1.454e-4 | 1.311e-14 | 6.365e-17 |
| 2 | 0.4 | 11 | 9.806e-5 | 1.380e2 | 2.130e-4 | 5.930e-2 | 7.257e-4 |
| 3 | 0.6 | 16 | 9.901e-5 | 1.826e2 | 1.494e-3 | 1.799e-1 | 3.338e-3 |
| 4 | 0.8 | 7 | 6.155e-5 | 2.643e2 | 4.238e-4 | 1.915e-1 | 4.313e-3 |
| 5 | 1.0 | 38 | 8.777e-5 | 2.170e2 | 3.762e-5 | 1.153e-1 | 5.408e-3 |

All load-factor errors are within 1e-15. Step ordering is exact. Only step 1 satisfies the displacement criterion.

## Improvement over baseline

The untouched solver stalled during step 2 after committing step 1 with relative error 2.214e-3. The corrected solver completes all steps, and step 1 is reduced to roundoff-level error. Normal-force coupling and the correct out-of-plane interface stiffness were necessary to move the divergence from the initial response and permit the full run.

## Live Load ArcLength benchmark

Analysis 22 (`LiveLoad_1`) chains from analysis 1 (`Vert`) and uses one assigned line load. Python commits the same 87 public C# steps and reaches the same configured maximum-displacement stop on attempted step 88.

- maximum relative displacement error: `9.142238482844599e-05` at step 3
- maximum absolute DOF difference: `1.9055000020862245e-05` at step 76
- no committed step exceeds the `1e-4` relative criterion
- all values finite
- terminal event: code `-3`, maximum displacement `1.000006`

ArcLength load multipliers are recorded by Python but are not independently stored in the C# SQLite public-step tables, so no C# multiplier-error assertion is made.
