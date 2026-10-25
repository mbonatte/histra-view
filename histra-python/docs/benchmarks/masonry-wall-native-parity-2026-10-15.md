# Four masonry walls: native comparison, 2026-10-15

The four fresh wall inputs now have user-generated HiStrA 2026.1.1 references.
Python rebuilds each computational model from the original unrun HRX; native
HRB metadata and Results are read-only references. Every case has 10 committed
Vert steps and 32 reversal steps in each of two combinations: 296 unique static
commits and 100,640 spring records. Step zero is excluded from those counts.

**2026-10-16 resolution:** all four cases now match every available checked
static field exactly, including the isotropic and zero-friction phases and
private histories. The initial-discrepancy section below records the earlier
investigation; the envelope-tangent correction resolves it.

## Modal line-load correction

The first comparison exposed missing modal direction and mass-factor handling
in Python's direct line-load generator. Original
`ModelLoadOperations.GenerateLoadsForceAnalysis` forces modal direction to
`(1,1,1)` for HiStrA. `Quad.ComputeLineLoad` then calls
`LoadTemplateManager.ComputeMassNodalForce`, multiplying each component by its
load condition's Single `MassInDirX/Y/Z` factor before integration.

The previous Python path used the static load direction and omitted those
factors. On these inputs, its total X/Y mass was 0.00913726 instead of the
native 0.07032429, materially changing frequencies. The corrected path matches
all 224 target load entries exported by the original routines across two mass
factor settings and four analyses, including ordinary static loads. Portable
tests also cover both saved values of IsSeismic.

All eight modal comparisons now reproduce the saved mode count. C# itself
stopped at the iteration limit before all six requested modes:

| Case | Virgin modes | Modes after reversal |
|---|---:|---:|
| Isotropic | 4 | 5 |
| Orthotropic | 4 | 4 |
| Elastic transverse | 4 | 5 |
| Zero friction | 4 | 4 |

Maximum relative frequency difference is 2.90e-14; minimum shape MAC is
0.9999999999999998. All three total directional masses match exactly.
Native values and shapes, with input/Results hashes, are recorded in
`histra/tests/fixtures/masonry-wall-modal-2026.1.1.json`. Tests solve from fresh
Python geometry, including Vert and reversal before the chained modal case.
Original routine bit-equality tests retain their existing strict assertions.

## Initial static discrepancies, resolved 2026-10-16

Orthotropic and elastic-transverse cases match all checked numeric and phase
outputs exactly after the restraint-area correction below. Isotropic and zero-friction cases have
near-roundoff force/displacement differences but also different phase and
private history fields; those are not waived as a parity pass. Some private
diagonal history differences are large despite negligible current force.

The actual compiled initial stiffness matrix, including its sparse pattern,
matches a fresh original C# assembly exactly on the isotropic case. The first
native linear solve also matches Python exactly. Replaying all ten recorded
Python Newton increments through original `updateDomain`, `GetResistingForce`,
`Commit`, and `SpringStateDBclass.SetFromSpring` matches every compared spring
field exactly on all four walls: 13,600 spring records, excluding unpopulated
energies. This is a controlled routine replay, not an independent C# nonlinear
solve. Both implementations differ from the UI's
saved first-step values in 13 spring displacements/forces, by at most 1.04e-25
displacement and 4.14e-22 kN. This isolates that first difference upstream of
the constitutive update; it does not yet explain all later histories.

Each native database contains 28 identical duplicate DynamicVectorsState rows
at reversal combination 1 step 32. The final audit collapses only identical
key/value rows; conflicting duplicate values would still fail identity checks.
Native NULL spring energies and absent private
histories at intermediate steps are unavailable measurements, not passes.

## Restraint spring area correction

The terminal private-history audit found a 5.42e-6 area difference on 81
elastic foundation transverse springs. Original
`SpringOperations.SetInterfaceTrasvSpring` sets restraint area using
`Operations.Area(Vector3[], true)`, which projects to a local plane and
accumulates polygon area in Single arithmetic. Python previously used a
double-precision Newell area. Both scalar and compiled batch preparation now
use the original calculation. Stiffness and force histories on this elastic
reference are unchanged. Native fixture tests check 81 actual wall cells and
12 rotated/skew cells bit-for-bit on Windows and Linux; an integration test
checks the generated foundation springs.

The reviewed v1.6.0 packages predate this correction. They must be rebuilt
before they can include it. The remote Article-model regression remains open.

## Initial envelope-tangent correction, 2026-10-16

The original complete nonlinear solver was invoked directly, starting from the
unrun isotropic HRX. Its saved Vert records reproduce the user's UI results
exactly. An isolated trace-helper build also reproduces all 4,251 native rows,
excluding surrogate IDs, while exporting complete Newton matrices, residuals
and increments.

The first actual current-tangent matrix differed in 40 entries, by at most
2.86491e-11. The earlier initial-stiffness comparison used alpha=0 and therefore
could not expose this difference. The first RHS was already exact. The dense
Python batch initialization replaced the fresh spring tangent with nominal K.
Original `SpringHysteretic.revertToStart` retains envelope E1p, whose calculation
Fy/(Fy/K) can differ from K in the last bits. Both numeric-fibre and scalar-object
imports now retain that original tangent. No constitutive formula or phase
comparison was relaxed.

After correction, all ten isotropic Vert matrices, RHS vectors and increments
match the full original execution exactly. Eight fresh wall chains then match
all checked available numeric/categorical outputs at 296 unique committed
states: 100,640 spring records, including every available terminal private
history. Native reference hashes remain unchanged. NULL energies and absent
intermediate private/global fields remain unavailable measurements.

`test_native_virgin_tangent` compares the first native current-tangent matrix
for numeric fibres and scalar spring objects on both platforms, without needing
the native solver library. `test_masonry_static_native_history` checks exact
fingerprints of every available committed spring field on all four walls using
the native UMFPACK configuration. Both fixtures originate solely from original
C# output; Python still reconstructs all computational objects from geometry.
