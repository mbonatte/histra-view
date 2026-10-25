# Wall result schema 1.1.0: inspection report

Inspected 23 October 2026. No numerical analysis was rerun and the supplied
files were not modified.

## Files and consistency

- `overturning_wall_elastic_foundation.hrx`: approximately 1.8 MB; 516 mesh
  nodes, 336 quads, 72 restraints, two load elements. Assigned quad materials
  are Masonry (120 quads) and Foundation (216). The current model-view parser
  accepts it without warnings.
- `overturning_wall_raw_output.json`: approximately 228 MB of exported geometry,
  topology, analysis histories, modal results and final element/spring states.
- `overturning_wall_raw_output.pkl`: approximately 69 MB. This revised pickle
  was inspected as opcodes; it contains no global references or object-construction
  opcodes. The viewer uses the JSON. Equivalence of this revised pickle with
  JSON was not reasserted by loading both full datasets.

The revised pickle has 13,285,412 opcodes, with no GLOBAL, STACK_GLOBAL,
REDUCE, BUILD, NEWOBJ, object-instance, extension or persistent-ID operations.
It was not executed or loaded by the viewer.

## Metadata and model identity

The export declares schema `1.1.0` and model SHA-256
`f844550755dc02f29998057513611ba477126d27acd442379fa2b04c21846fda`.
This exactly matches the supplied HRX bytes.

Declared native units are length cm, force kN, moment kN*cm, stress kN/cm^2,
rotation rad, energy kN*cm, frequency Hz and period s. The viewer validates
these declarations and converts spring stress to MPa for display (factor 10).

## Prepared model data

The output includes 2,352 global DOFs, 336 quads, 884 interfaces, five model
points and six material records. Quad records include their node IDs,
reference axes, centres, thicknesses, lengths and DOF afference mapping.
Interface records include parent elements, geometry, local axes and afference.

There are 912 exported node records, but only 516 are referenced by quads.
The other 396 records should not be treated as additional rendered mesh nodes.
The 516 used node IDs and all quad IDs/connectivity match the HRX. Coordinate
differences are at most about 4.55e-13 in native length units.

All exported quad DOF references fall within 1..2352. Every JSON Quad now has
four sine and four cosine coefficients. Recovery is standalone: no HRX geometry
is required. The viewer also obtains extrusion direction from the exported
reference axis e3. When an HRX is available, its hash is checked against the
export rather than using it as an undeclared geometry dependency.

## Analyses

| Analysis | Saved results |
| --- | --- |
| `Vert` | Initial state plus 5 committed steps; final node/model-point and element/spring states. |
| `Modal_0` | 10 converged modes; modal values and a 2352-by-10 mode-shape matrix. |
| `scour_1` | Initial state plus 5 committed steps; 24 scoured interface IDs; final node/model-point and element/spring states. |
| `Modal_1` | 10 converged modes; modal values and a 2352-by-10 mode-shape matrix. |
| `LiveLoad_1` | Initial state plus 35 committed steps; final node/model-point and element/spring states. |

All three static executions report `completed`. Every committed step is `OK`
and has `equilibrium_ok = True`. Every saved displacement vector has exactly
2352 finite entries. Inspected displacement vectors, per-step interface
resultants and dense runtime arrays contain no nonfinite numeric values.
These checks establish internal consistency, not independent validation of the
underlying numerical solution.

Static committed steps include load factor, control displacement, reactions
and balancing reactions, elastic/dissipated energy, iteration counts,
convergence measures and equilibrium diagnostics.

## What the viewer can show

| Visualization | Availability |
| --- | --- |
| Deformed mesh with step selection/playback | Yes, recover nodal or element-corner translations from each saved `u` and the matching geometry/mapping. |
| Displacement contours: Ux, Uy, Uz, magnitude | Yes, for every saved static step. |
| Force/load-factor versus control displacement | Yes; distinguish load factor from physical force and use the HRX reference load when converting. |
| Reaction and energy curves | Yes, at committed steps. Initial-step records do not contain all committed-step summary fields. |
| Model-point displacement histories | Recoverable from `u`; final values are also exported directly. |
| Modal properties and animated mode shapes | Yes, ten modes before and after scour. Animation amplitude is a display scale, not a physical response amplitude. |
| Interface forces and bending moments | All 884 interfaces at all 48 saved static states, including stage initial states. |
| Interface thrust eccentricities | Recoverable from Mz/N2 and Mx/N2 at each step, with a near-zero-force guard. |
| Spring stresses/phases | Available at the end of each of the three static stages. |
| Spring stress/phase animation throughout every step | Not saved: per-step interface resultants do not contain individual spring histories. |
| Full continuum stress tensor / principal-stress field | Not exported. Spring/interface stresses require an explicit visualization convention. |

### Verified displacement recovery

Using the existing Python `quad_node_displacement` and ordered nodal averaging
operations, with exported DOF mappings, geometry and JSON shape coefficients,
the final `u` vector of each static analysis reproduced all 516 saved nodal
displacement records with **zero discrepancy**. This checks the complete
displacement-recovery path without solving the model again.

### Final element and spring snapshots

Each static stage contains 336 quad states and 884 interface states. Across
those interfaces there are 71,604 transverse/normal fibre records, 884
in-plane sliding records and 1,768 out-of-plane sliding records.
Records include force/deformation, stiffness, positive area, and phase where
applicable. Normal fibre `cstress_force` is a force: divide by the associated
area to obtain stress. Sliding force and contact-area fields require their
own documented stress convention.

The live-load final snapshot includes hysteretic `Plastic_t`, `Plastic_c`
and `Unload_c` phases. These are constitutive phase labels, not a separately
exported scalar damage index. Full spring hysteresis loops cannot be recovered
from three stage-end snapshots.

Every static stage now has nonzero populated `status_bending_moments` and
12-component `f` vectors for all 884 interfaces. Each final-step force and
moment vector exactly matches the corresponding stage-end object snapshot.

`runtime_arrays` is populated and all inspected numeric entries are finite:

| Array | Shape |
| --- | --- |
| `quad_local_u` | 336 × 7 |
| `local_u` | 884 × 12 |
| `local_full_forces` | 884 × 12 |
| `interface_resultant_forces` | 884 × 3 |
| `interface_bending_moments` | 884 × 3 |
| `committed_hysteretic_springs` | 71604 × 9 |
| `coulomb_state` | Vert: 2652 × 38; later stages: 2628 × 38 |
| `quad_state` | 336 × 85 |

Runtime force/moment rows exactly match the object snapshots in their exported
iteration order. The viewer uses the explicit interface IDs and per-step keyed
resultants; it does not infer spring-state column meanings from array shape.

## Per-step moments and thrust convention

All six Vert, six scour_1 and 36 LiveLoad_1 saved states contain a complete
`interface_resultants` dictionary. Each of the 884 entries has three local
force components and three local bending moments; final entries match the
stage-end snapshots exactly.

The viewer uses ex = Mz/N2 and ey = Mx/N2 in cm. The C# `CalcolaRisultanti`
implementation forms these moment offsets about intrinsic (Length/2, 0).
For the exported reference system, the corresponding undeformed point is:

`reference_origin + (Length/2 + ex) * reference_e1 + ey * reference_e3`.

The positive ey sign follows the native moment convention, rather than an
assumed cross-product convention. Near-zero normal force is excluded using
max(1e-8 kN, 1e-8 × peak |N2| at that interface). Compression thrust markers
require negative N2. Tensile resultants can have a mathematical eccentricity
but are not shown as compression thrust points. The plotted trajectory follows
one interface across saved steps; it is not a structural thrust line created
by joining unrelated interfaces.

## Implementation considerations

- The JSON is sufficient for displacement recovery; the HRX is optional for
  verifying source-model identity.
- Keep each analysis stage distinct and preserve its initial state; stage
  displacement vectors include the previously accumulated state.
- Validate declared units, schema and model fingerprint before projection.
  Unsupported units must not be silently relabeled as kN/cm.
- Serve compact step/field payloads from the Python service. Avoid loading the
  entire 228 MB JSON and all spring dictionaries into the browser at startup.
- Add per-step interface/spring snapshots only if stress/phase playback is
  required. Their nonlinear histories cannot generally be inferred from `u`.

The viewer supports deformed-shape and modal playback, response curves,
per-step interface forces/moments and selected-interface thrust trajectories.
Individual spring maps remain stage-end-only and are hidden at intermediate
steps to avoid presenting a final snapshot as an intermediate result.
