# Complete Solver Flow

## Common initialization

1. Parse the HRX and select the analysis/combination.
2. Virgin analyses clear supported global/local state.
3. Chained analyses require a `.Results` database and restore the predecessor's complete final state.
4. For chained static analysis, form committed resisting forces and set the new baseline external vector to their negative (`SetFextEqualToFint`).
5. Generate the selected new load vector; missing or unsupported load metadata raises explicitly.
6. Assemble initial stiffness with `alfa=0`, matching C# static preparation.

## LoadControl path

LoadControl advances the load function, forms residuals, solves Modified/Standard Newton increments, updates interfaces before quads, performs configured line search, tests convergence, and commits or restores a complete pre-step snapshot.

## Live Load ArcLength path

1. Select the active model-point DOF(s); the benchmark selects Quad 9 Z, global DOF 58.
2. Solve the fixed initial stiffness against the Live Load reference vector.
3. Form the predictor radius and cap the predictor load increment at the configured C# value.
4. Apply the predictor and update the nonlinear domain.
5. At each iteration, solve residual and reference-load directions, enforce the quadratic ArcLength constraint, and store the combined correction in `LS.X`.
6. Preserve the C# hidden InitialInterpolated base search: no additional line-search trial is performed.
7. Evaluate the absolute Work criterion using the combined ArcLength correction.
8. Commit on convergence. On failure or maximum displacement, restore the complete pre-step snapshot.
9. Continue through C# committed steps 1–87. Attempted step 88 reaches max U and terminates with code `-3` without a commit.

Snapshot state includes global vectors, linear-system vectors/matrices, external/P-Delta vectors, integrator/convergence/search state, local element state, and every spring attribute. Cyclic garbage collection is suspended only during the synchronous solve and restored on every exit; reference counting releases bounded snapshots normally.
