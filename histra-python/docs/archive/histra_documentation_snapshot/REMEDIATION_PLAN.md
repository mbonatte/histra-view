# Remediation Plan

## Highest-value next evidence

1. Build or obtain a runnable C# reference binary matching `model.Results`.
2. Instrument both implementations at every step-2 Newton and Regula-Falsi trial with load multiplier, Work scalar, residual/increment norms, selected global DOFs, selected interface/quad local displacements, `dN`, normal stress, friction capacity, force, tangent, and phase.
3. Confirm the exact native linear-solver backend, ordering, scaling, and pivot settings used to create the database.
4. Compare the first step-2 trial vector before any constitutive update. If it differs, focus on linear solve/factorization; if it matches, compare update/line-search trial state sequentially.
5. Verify that the supplied decompiled C# source is byte-version-compatible with the executable that generated the database.

## After LoadControl parity

1. Add per-step complete Python result writing for independent restart tests.
2. Port only load object families actually used by the next selected analysis, including Psi/template data.
3. Validate chained LoadControl analyses using final complete prerequisite state.
4. Select one ArcLength analysis and repeat the same committed/per-iteration methodology.
5. Implement P-Delta only when a selected reference analysis enables it.

Tolerance changes or branch-specific tuning should not be used to hide the current discrepancy.
