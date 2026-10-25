# HiStrA Python/C# Integration Audit Summary

## Current result

The Python solver now follows both numerical references supplied with the 126-DOF model package:

- **Vert**, analysis 1, LoadControl: all five steps execute; step 1 is roundoff-exact, while steps 2–5 retain the previously documented global-path discrepancy.
- **LiveLoad_1**, analysis 22, ArcLength chained from Vert: all 87 C# committed steps reproduce within the `1e-4` relative displacement tolerance, followed by the same maximum-displacement stop at attempted step 88.

### Live Load acceptance

| Measure | Result |
|---|---:|
| Committed step order | exact, 1–87 |
| Maximum relative displacement error | 9.142238e-05 |
| Maximum absolute DOF difference | 1.905500e-05 |
| Steps exceeding 1e-4 | 0 |
| Non-finite values | 0 |
| Terminal behavior | step 88, max U 1.000006, code -3 |

Full equivalence is claimed only for the Live Load committed-step acceptance defined above. The C# database does not persist ArcLength multipliers per step, so multiplier error cannot be independently evaluated from SQLite.

## Live Load corrections

- Parsed model points, load templates/items, and line-load elements.
- Generated the assigned Quad line load with float32-sensitive C# conventions.
- Implemented model-point ArcLength DOF selection and predictor cap behavior.
- Restored chained analyses from complete C# state and reproduced `SetFextEqualToFint` baseline equilibrium.
- Reproduced static initial-stiffness preparation and the C# tangent-update omission for `StandardInitialInterpolatedLineSearch`.
- Reproduced hidden base-line-search dispatch and preserved the ArcLength combined work-test vector.
- Corrected Coulomb03 negative-envelope `Eun` selection to the C# `max` behavior.
- Added bounded snapshot copying, solver-scoped cyclic-GC suspension, and sparse factorization reuse.
- Added focused and optional full Live Load regression tests.

See `histra_documentation/LIVE_LOAD_INTEGRATION.md` and the machine-readable benchmark metrics for step-by-step evidence.

## Performance optimization

The complete virgin `Vert -> LiveLoad_1` workflow was function-profiled. The
previous 267.46-second runtime was dominated by 21.6 million scalar hysteretic
spring calls and repeated immutable geometry/topology work; sparse solves were
not the bottleneck. A compiled dense hysteretic runtime, compiled local/global
maps, cached Quad/interface topology, and compact snapshot state reduce the
same run to 13.10 seconds warm and 15.83 seconds with an empty JIT cache. The
full opt-in suite passes with 132 tests, and final displacement/reaction outputs
remain equal to the previous solver to roundoff. See `../PERFORMANCE_PROFILE.md`.

## Exact raw-model preprocessing alignment

The 560-DOF benchmark exposed several path-sensitive C# preprocessing rules.
The current release ports them and restores the same 38-step Live Load trajectory
as the software-generated model. See `../PREPROCESSING_EXACTNESS_REPORT.md` and
`../PREPROCESSING_EXACTNESS_METRICS.json`.
