# Dhir 2026.1.1: original C# routine oracles

The audit starts from fresh Python geometry and applies user material selections
as metadata. Saved C# interfaces, springs, afferences and histories are references
only. Step 0 is an initial snapshot, never a committed step.

## Native geometry evidence

The installed 2026.1.1 `ModelLibrary.dll`, `UtilityLibrary.dll` and `XNALibrary.dll`
were loaded in Windows PowerShell. The original `Interface.GetSpringCoordinate`,
`Quad.GetFiberProperties` and `Quad.GetFiberStiffness` methods were called directly.
Two Dhir interfaces (1793 and 4401), both parent Quads and all nine cells per
parent provide 36 fibre oracles and 18 cell polygons in the tracked JSON fixtures.
Inputs are supplied explicitly; no saved C# objects enter a Python solve.

C# builds local Vector2 cells, transforms them to global coordinates with float
arithmetic, and finds fibre coordinates using projected edge intersections.
Python's previous global interpolation/Newton inverse mapping is a different
calculation path. `csharp_fibre_geometry.py` contains the native-tested port.
Coefficients, projected areas and lengths match exactly in the 36 cases;
stiffness uses an absolute assertion of 1e-10. Cell coordinates match exactly
in scalar, compiled and fallback paths.

The original IL was also inspected: coefficient arithmetic is float before
`conv.r8`. Decompiled C# incorrectly suggests inner double casts in coefficients
0 and 2. Native method outputs are the regression oracle for this detail.

Production now uses the native geometry and fibre routines. Correcting upstream
Quad faces, contact containment and authored tolerances resolved the earlier
model-output regression without weakening its assertion. The subsequent Vert
audit also corrected sliding distances, masonry modulus rounding and shear-DOF
coordinate mapping. See [the current Vert audit](dhir-vert-native-parity.md) for
all ten committed steps and remaining detailed-history differences.

## Native energy evidence and implemented fix

Eight direct calls to original C# `Spring.ComputeEnergy` cover compression,
tension, unloading, constant stress and stress reversal. C# computes signed
trial-to-commit increments:

`dEel = sign(Ftrial-Fcommit) * (Ftrial^2-Fcommit^2)/(2*K)`

`dEtot = 0.5*(Fcommit+Ftrial)*(Utrial-Ucommit)`

`dEd = dEtot-dEel`

Python previously accumulated stored `0.5*K*U^2` values and returned zero plastic
energy. The scalar spring and dense compiled paths now implement the original
increment formula, including Quad diagonals and all three interface spring
groups. Aggregation follows C# Quad-first and per-interface ordering. Negative
reported elastic/plastic increments preserve C# output conventions; they do not
by themselves establish a physical interpretation or equilibrium acceptance.

## Output coverage and remaining work

The Dhir database has 11 populated tables: SpringStatesTmp, SpringStates,
InterfaceStates, QuadStates, NodeCStates, RestraintStates, DisplModelPoints,
DynamicVectorsState, ReactionSumStates, ModalShapeValues and ModalValues.
Empty tables are inventoried separately. Detailed SpringStates history exists
only at final Vert and UDL snapshots; temporary spring rows cover every saved
step. Missing reference snapshots are reported explicitly, never substituted
with another step. Python state is archived even when C# has no matching step.

The static audit now includes each available spring field, interface displacement,
force and moment, Quad displacement/stiffness, NodeC and restraint displacement,
model-point translation/velocity/acceleration, global displacement/velocity and
reaction/energy field. Modal quantities and every modal shape coordinate have
separate comparisons. Full parity remains unresolved: initial capacities,
nonlinear histories and terminal step count require further original-source
tracing. The earlier repeated-interface registration finding does not explain
the global Dhir pushover difference.
