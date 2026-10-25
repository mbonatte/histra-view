# SQLite Results and Restart Behavior

## Benchmark schema interpretation

All relevant rows use `AnalysisKey = 1`, `Combination = 1`, and steps 0–5.

- `DynamicVectorsState` — 126 final-step rows; `Dof` is zero-based; columns `U` and `V` are global vectors.
- `QuadStates` — 18 rows per step; `ParentKey` is quad key; `U1..U7` are local generalized displacements; `K` is stored scalar stiffness/state.
- `InterfaceStates` — 29 rows per step; `ParentKey` is interface key; `U1..U12` are local generalized displacements. Force/moment resultants are serialization/postprocessing fields and are not treated as constitutive restart inputs.
- `SpringStatesTmp` — 2,454 rows per step, compact fields only. It lacks tangent and much of the committed history needed for reversible nonlinear continuation.
- `SpringStates` — 2,454 complete final-step rows, including force, tangent, phase, limits, plastic offsets, normal force, energy, and model-specific history.
- `ReactionSumStates` — one row per step with reaction and energy summaries.

## Global displacement reconstruction

Step 5 can be read directly from `DynamicVectorsState`. Earlier global vectors are reconstructed by applying quad/interface afference mappings to local state. Multiple contributions to a DOF are checked for consistency. Indexing conversions are explicit: HRX afference GDL values are one-based; SQLite dynamic DOF indices are zero-based; NumPy vectors are zero-based.

## Restart rules

A lossless restart requires:

1. the selected analysis/combination final committed step,
2. a complete global displacement/velocity vector,
3. all expected quad and interface local states,
4. all expected complete spring rows and identifiers,
5. consistent model and database key mappings.

Python restores the final complete state only. It refuses intermediate compact restart with a `ResultsStateError` rather than silently filling missing history with zeros. For chained analyses, `InitialAnalysisKey` and `InitialCombinationAnalysisKey` select the prerequisite. Missing databases or incomplete state fail with precise messages.

## Live Load chained analysis

Analysis 22 declares `InitialAnalysisKey=1` and `InitialCombinationAnalysisKey=1`. Python restores the complete final Vert step (global vectors, 18 quads, 29 interfaces, and all 2,454 complete spring histories). It then follows the C# chained initialization behavior: assemble committed resisting forces and set the new baseline external vector to their negative. The predecessor gravity vector is not regenerated. The new Live Load reference vector is applied incrementally by ArcLength from this self-equilibrated baseline.

Analysis 22 stores compact public spring states for steps 0–87 but no complete final restart tables because it terminates at the maximum-displacement condition rather than completing. Therefore analysis 22 itself is not accepted as a lossless predecessor for another chained analysis.
