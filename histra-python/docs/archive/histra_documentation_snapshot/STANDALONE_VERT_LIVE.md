# Standalone virgin-HRX Vert → Live Load workflow

## Objective

Run a model that has never been analyzed without relying on a C# SQLite
`.Results` database:

1. load the HRX;
2. automatically preprocess it when computational objects are absent;
3. reset it to the virgin state;
4. solve `Vert`;
5. preserve the complete committed global and constitutive state in memory;
6. initialize the chained Live Load analysis from that state;
7. solve Live Load;
8. export global node translations and total support reactions.

The public launcher is:

```bash
python run_vert_live.py model.HRX --output-dir python-results
```


## Unlocked HRX preprocessing

When the HRX has `IsLocked=false`, `GDL=0`, or lacks generated springs and
interfaces, `solve_static_nonlinear` invokes the translated
`ModelManager.PrepareModel` stage automatically. The validated path supports
four-node masonry Quads, exact complete shared edges, and fixed line
restraints. The generated model remains in memory and is passed directly from
Vert to Live Load. See `PREPROCESSING.md`.

## In-memory chaining

`solve_static_nonlinear(..., restart_from_current_state=True)` accepts the final
Vert global displacement vector while the model's quads, interfaces, and every
spring remain at their just-committed Vert state. The chained baseline external
force is initialized from the current resisting force, matching the C#
`SetFextEqualToFint` behavior. No result database is opened.

The Live analysis is rejected if its `InitialAnalysisKey` does not equal the
selected Vert key.

## Displacement output

`postprocessing.compute_node_displacements` reconstructs each node's global
translation from connected Quad generalized coordinates, including rigid-body
rotation and U6 warping contributions. Predictions from multiple connected
Quads are averaged in the same way as the C# response operation.

CSV output contains `ux`, `uy`, and `uz` in global X, Y, and Z directions for
every model node and every committed step, plus final-only CSVs for convenient
comparison.

## Reaction output

`postprocessing.compute_total_reaction` sums the resultants of constrained
interfaces and rotates them to global coordinates. The exporter provides three
views:

- `histra_reaction_sum_*`: C# `ReactionSum R1/R2/R3` sign convention;
- `total_support_reaction_*`: its negative, the conventional support-on-
  structure force;
- `incremental_support_reaction_*`: support reaction minus analysis step 0.

For Live Load, the incremental vector excludes the inherited Vert reaction.

## Measured validation

A complete virgin-HRX run of the supplied `model-live/model.hrx` was executed
without reading a `.Results` database:

- optimized elapsed time in the audit container: approximately `13.10 s` with a warm JIT cache;
- Vert: 5 committed steps, exact reference ordering;
- Live Load: 87 committed steps, exact reference ordering;
- attempted Live step 88 reached model-wide displacement `1.0000059183` and
  stopped at the configured `maxU=1.0`;
- no NaN or infinite values were exported.

User-facing CSV validation against the C# SQLite database:

- Vert node X/Y/Z maximum relative vector error: `3.173e-14`;
- Vert node maximum absolute component error: `1.915e-15`;
- Vert reaction maximum absolute component error: `1.776e-15`;
- Live node X/Y/Z maximum relative vector error: `1.562e-4`;
- Live node maximum absolute component error: `3.140e-5`;
- Live reaction maximum relative error: `1.060e-4`;
- Live reaction maximum absolute component error: `3.164e-2`.

The final Python support reaction is `(0, -2.13e-14, 303.2515488)` and the C#
reference is `(0, -2.13e-14, 303.2748795)` in conventional support-reaction
sign. The Python final Live-only incremental support reaction is
`(0, -7.11e-15, 88.5083618)`.

The previously validated generalized-DOF benchmark remains within
`9.142e-5` relative displacement error. Reconstructed node translations can
have a slightly larger relative ratio because the rigid-body/warping transform
combines several small generalized values; the maximum absolute component
difference is reported above.

## Termination diagnostics

The step CSV distinguishes the selected graph/control displacement from the
model-wide maximum element displacement. A `-3` convergence result is classified
as a successful configured limit only when `max_element_displacement >= maxU`;
the monitored graph value may be close to zero and is not used for that test.

## Output persistence

`solver.log` is append-written throughout execution. Vert CSV files are written
immediately after Vert commits, before the longer Live Load solve begins.
