# Bridge Result Fidelity Report

Status: living document  
Scope: masonry arch bridges under scour damage and live load  
Primary sources: `C#_Original`, `3D_bridge` v2 bundle, `results/Bridge_scour_3d_Distributed_PDelta/`,
the Python solver, and the current viewer implementation.

This report records what is already implemented, what still differs from the C#
viewer, and which gaps are worth implementing for the bridge cases. It is a
backlog and decision record, not a claim that every C# feature is required.

## 1. Executive Summary

The viewer already covers the main bridge workflow:

- deformed-shape and independent Quad playback;
- modal shapes;
- response curves and saved diagnostics;
- interface resultants, fibre contours and thrust lines;
- interface-spring stress, principal, Von Mises, local stress and strain maps;
- colour-range, palette and minimum-thrust-force controls;
- high-resolution PNG export.

The most important remaining issue is **not** the number of C# menu entries.
It is that the current Quad colour maps are still an intermediate face-aware
approximation of the C# face texture path. They now include all six physical
faces and the through-thickness interfaces, but they are not yet a
C#-parity rendering of the edge-interpolated face texture.

The second important issue is that **bridge v2/native** stress/strain maps are
final-step only, even though the native C# `.Results` database stores per-step
spring states. Native C# Quad stress fields now follow the selected step;
interface stress/phase maps still need the same treatment. For scour/live-load
studies, being able to select a load step and see the corresponding interface
stress/phase is more valuable than adding unrelated C# element types.

Other element types (frames, trusses, solids, fibres, vertices) are explicitly
out of scope for this project unless the bridge model requires them.

## 2. Current Viewer Coverage

### Model and result sources

- Native 3D bridge v2 bundle:
  `results/3D_bridge/pdelta_soft_subgrade_phase4_results.json` plus per-case
  `summary.json` and `fields.npz`.
- Native 2D bridge v2 bundle:
  `results/2d_bridge/results/manifest.json` plus `results/native/<case>.summary.json`
  and `.fields.npz` (388 nodes, 306 Quads, 555 interfaces, four pushover cases).
- Native C# `.Results` SQLite databases:
  `results/Bridge_scour_3d_Distributed_PDelta/` (new standard; `Vert`,
  `scour_1`…`scour_8`, 3,216 nodes / 2,520 Quads / 6,786 interfaces) and the
  legacy `results/benchmark/benchmark.Results` pair.
- Official self-contained `.histra` archives: static native archives such as
  `results/native_soil_15e3/native_soil_15e3.histra` (104 cases), large
  three-span imports such as `results/Scozzese_Vert.histra` (4,950 nodes,
  3,800 Quads, 10,236 interfaces), and modal-only archives such as
  `results/modal_scour_y_mode_baseline_abutments.histra` (8 cases, 30 modes
  each). The viewer extracts the embedded HRX and decodes the
  content-addressed `byte-shuffle-v1` arrays in memory. Static `.histra`
  imports return stress-map descriptors immediately and prefetch their values
  in the background after the first render. The first `.histra` stress-field
  request carries the twelve six-face corner maps; later requests are cached.
  Modal attachments stored as `<case>_values.json` + `<case>_shapes.npz` are
  projected from the solver's 7-DOF Quad order to nodal mode shapes. For
  archives with more than 1,000 Quads the lazy field payload omits the adaptive
  `quadFaceGrids`; generating the 395k grid samples for the Scozzese model took
  over three minutes and exceeded the browser import timeout. Smaller archives
  keep the grids, and `project_histra(..., include_face_grids=True)` remains
  available for the full texture path.
- Legacy wall JSON and curve-only bridge cases remain supported for comparison.

### Results available in the browser

- `Deformed shape`: node and independent Quad displacements, physical thickness,
  undeformed outline, edge display, camera presets.
- `Modal shapes`: saved modes with frequency, period, mass percentages and
  normalized shape animation.
- `Response curves`: force/displacement, reactions, energies and saved steps.
- `Stress contours`: per-fibre interface normal stress, normal strain, phase,
  normal force and sliding-link details.
- Main Quad colour fields: global stress/shear, principal stress, Von Mises,
  local interface normal/in-plane/out-of-plane stress, local strain and plastic
  fields where the source supports them.
- `Line of thrust`: funicular compression line, width-centroid grouping, plastic
  hinges and a minimum compressive-force filter.
- `PNG export`: scaled raster view with range/palette legend and caption.

### Current saved-result adapter coverage

`model-view/csharp_results.py` reads:

- `QuadStates`
- `InterfaceStates`
- `ReactionSumStates`
- `DisplModelPoints` (`Ux`, `Uy`, `Uz` only)
- `SpringStatesTmp` (final step; `SpringStates` fallback)
- `ModalValues` and `ModalShapeValues`

It does not read the remaining `.Results` tables listed in Section 5.

## 3. Highest-Priority Gap: C# Face-Texture Fidelity

### 3.1 What C# does

For a Quad face, C# builds edge tensors and evaluates the requested response
through `ComputationalElement.GetTensorPrepare`,
`ComputationalElement.AddTensorOnEdge`,
`ComputationalElement.GetValueForColorMapTextureTensor`, and
`ComputationalElement.GetValueFromTensor`.

The relevant stages are:

1. Build the local interface tensor in `Interface.GetTensorMap`:
   - `M22` from the transversal spring stress;
   - `M12` from the in-plane sliding stress;
   - `M23` from the out-of-plane sliding stress.
2. Build edge tensors at each face edge with `SetTensorOnEdge`.
3. Rotate each edge tensor to global axes.
4. Include the through-thickness/opposite-face interface as `Interface5` and
   add its contribution with `AddTensorOnEdge`.
5. Interpolate missing edges when a face does not have an interface.
6. Evaluate the requested component at the face texture grid.
7. Render a texture per face, not one colour for an entire Quad corner.

`Quad.GetTensorValue` and `Quad.GetValueForColorMapTexture*` select the face and
the corresponding `Interface5` for top, bottom and through-thickness faces.

### 3.2 What the viewer currently does

The bridge v2/native path now has an **edge-aware six-face implementation**:

- `bridge_v2._stress_fields` reads the six C# physical Quad faces and uses the
  `Quad.GetColorMapValues` edge-face mapping (top/bottom/edge/opposite faces),
  including faces 4/5 that were previously ignored;
- face corners use the adjacent C# edge tensors and add the opposite-face
  `Interface5` tensor;
- `quadFaceValues` contains four corner values per face, and the renderer paints
  top, bottom and four side faces independently;
- faces whose C# resolution `N × M` is greater than 2×2 also carry
  `quadFaceGrids`: the C# adaptive grid dimensions, edge samples from the saved
  spring grid, inverse-distance edge interpolation and `Interface5` addition;
  `mesh-viewer.js` subdivides those faces and renders per-vertex colours;
- the native `.Results` source (`csharp_results._stress_fields`) uses the same
  six-face edge/corner projection, but does not yet emit grids.

This is closer to the C# texture path but still **not byte-exact**:

- normal and shear terms of C# `AddTensorOnEdge` are superposed on the edge
  samples, but the exact reference-system/fallback form is not yet a literal
  port;
- spring-cell containment now uses an inverse-bilinear cell selection; the
  exact C# polygon/tolerance and `GetTensorByInterpolation` fallback details
  still need validation;
- native C# `.Results` does not yet emit the adaptive face grids (the benchmark
  model happens to use only 2×2 faces, so its corner path is complete for that
  dataset);
- no comparison against a C# exported texture has been done.

### 3.3 Observed bridge consequence and current status

The 3D bridge v2 mesh has 6,762 interfaces. The old four-face corner mapping:

- linked 4,548 interfaces through Quad faces 0–3;
- ignored 2,214 interfaces on faces 4/5, which are essentially Y-normal;
- produced `min = max = 0` for `Pushover_Span2_Quarter` `globalStressY`.

The edge-aware path now reports `globalStressY` over the saved snapshot (for
example, approximately -0.487 to 0.399 MPa in the current 3D bridge case), with
face textures for the long 8×2/9×2 faces. That verifies the through-thickness
contribution is present; it is not yet a byte-for-byte C# texture comparison.

### 3.4 Recommended implementation path

Recommended sequence:

1. Validate the superposed `AddTensorOnEdge` normal/shear terms against the C#
   reference-system form and complete the exact `GetTensorByInterpolation`
   edge fallback.
2. Validate the inverse-bilinear spring-cell selection against C#'s
   polygon/tolerance rules, then compare the resulting grids against C#
   reference values or exported textures.
3. Emit the same adaptive `quadFaceGrids` from native C# `.Results` when its
   faces exceed 2×2.
4. Verify global X/Y/Z, principal, Von Mises and local maps against C#
   reference values or exported C# textures.

The current implementation has the six faces, edge mapping, `Interface5`
addition and adaptive grid rendering. It must not be called exact C# texture
parity until the remaining edge-superposition and validation steps are complete.

## 4. Per-Step Stress, Strain and Phase

### Current state

Bridge v2/native maps remain final-step snapshots because the bundle stores only
the final spring stress arrays. The viewer forces those sources back to the
final step while a stress map is selected.

The native C# `.Results` source now has lazy Quad fields. The main analysis payload carries field descriptors only; selecting a stress map fetches the field values for the selected step. Per-step fields are then lazy too:

- `GET /api/results/<native-csharp-source>/fields?analysis=...&step=...`
  projects the full ordered stress/strain catalog for one saved step;
- the browser keeps a bounded cache of up to 16 `(analysis, step)` field
  payloads and fetches when a stress map is scrubbed or played;
- the final-step fields are fetched on first stress-map selection and cached;
  analysis switching without a stress map stays on the fast path.

The native C# interface contour payload is also lazy per-step:
`/api/results/<native-csharp-source>/contours?analysis=...&step=...` and the
browser-side contour cache follow the selected step. The selected-interface
detail fetch also receives the same step and displays its saved spring values.

### Available data

The native C# `.Results` file has:

- `SpringStatesTmp`: 8,919,940 rows for all public steps;
- `SpringStates`: 115,096 complete final rows;
- `InterfaceStates`: 105,710 rows;
- 132 `LiveLoad_1` steps and 6 `scour_1` steps.

### Remaining implementation

- Keep bridge v2 final-only until its exporter saves per-step spring states.
- Add the remaining C# phase/ratio menu entries. Quad global/principal stress
  and interface normal/sliding/phase contours now follow the selected C# step.

## 5. Bridge-Specific Missing Maps and Data

### 5.1 Interface maps

C# exposes:

- Transversal1 stress (`byInterfaceTransversal1`);
- Transversal2 stress;
- sliding stress;
- out-of-plane sliding stress;
- Transversal1 stress ratio (hidden in the C# UI);
- phases for Transversal1, Transversal2, sliding and out-of-plane sliding.

Current viewer:

- interface normal stress, normal strain, normal phase and normal force;
- 3-D sliding stress, out-of-plane sliding stress and sliding phase;
- sliding forces in the advanced table;
- no interface stress-ratio map;
- no Transversal2 map;
- no per-step interface phase map.

For scour/live-load bridge assessment, sliding stress and phase are relevant
because they show interface slip/opening mechanisms. This should be implemented
before low-value C# node maps.

### 5.2 Quad diagonal links

The C# menu contains:

- `QuadDiagonalSigma`
- `QuadDiagonalPhase`

The legacy `.Results` benchmark file contains 260 Quad diagonal spring states
(`ParentType=106`, `SpringPurpose=30`) at the final step. The native C# menu now
exposes `quadDiagonalSigma` and `quadDiagonalPhase`; the phase map uses the
saved diagonal-spring phase and the sigma map follows the C# interface
force/area average. Bridge v2 does not contain diagonal spring states, so the
descriptors remain disabled there.

### 5.3 Local C# X/Y maps

C# has local `X-dir` and `Y-dir` stress/strain maps. The current viewer uses
explicit normal, in-plane and out-of-plane components. This is a deliberate
readability choice, but it is not a literal reproduction of the two C# local
axis labels. The report should retain the C# parity requirement until the
face-texture path is implemented.

## 6. Other `.Results` Data Present but Unused

The `benchmark.Results` database contains:

| Table | Rows | Current use |
|---|---:|---|
| `QuadStates` | 40,300 | used |
| `InterfaceStates` | 105,710 | used |
| `SpringStatesTmp` | 8,919,940 | final step only |
| `SpringStates` | 115,096 | fallback/final only |
| `NodeCStates` | 10,850 | not used |
| `RestraintStates` | 9,300 | not used |
| `DynamicVectorsState` | 3,640 | not used |
| `DisplModelPoints` | 1,395 | translations only |
| `ModalValues` | 10 | frequency, period, mass percentage only |
| `ModalShapeValues` | 18,200 | used for `Modal_-1` |
| `FrameStates` | 0 | out of scope |
| `TrussStates` | 0 | out of scope |
| `SolidStates` | 0 | out of scope |
| `FiberStates` | 0 | out of scope |
| `FrameSectionStates` | 0 | out of scope |

Useful bridge items that are currently unused:

- `NodeCStates`/`RestraintStates`: support displacement/rotation histories,
  settlement and restraint response.
- `DisplModelPoints` `Vx/Vy/Vz`, `Ax/Ay/Az`: velocity and acceleration
  histories.
- `ModalValues` `Gamma*`, `Massa*`, `MTot*`, `UMax*`: participation factors,
  effective/total mass and modal maximum displacement.
- `ReactionSumStates` `Et`, `Ei`, `Evd`: total input/irreversible/viscous energy
  in addition to the current elastic/dissipated values.
- `SpringStates` complete final fields: tangent stiffness, contact area,
  ultimate/plastic state, energies and flags.
- `InterfaceStates` local `U1…U12`: interface relative displacement/rotation.
- `QuadStates.K`: available but not displayed.

## 7. Analysis and UI Gaps Relevant to Bridges

- **Combination selection**: the C# adapter chooses the first `Combination`
  found. A database with multiple combinations would silently show only one.
- **Control point selection**: the current control displacement uses the model
  point with maximum final displacement. C# users can select a monitored point.
- **Model-point histories**: only one control displacement is charted; there is
  no arbitrary model-point U/V/A history.
- **Analysis overlay**: one analysis at a time; no overlay of scour stages or
  live-load cases.
- **Field export**: no CSV export of the new stress/strain fields; only the PNG
  and existing curve/interface CSV exports.
- **Report tables**: no equivalent of the C# report tables such as Quad/Vertex
  stress on edges.
- **Phase maps on Quad faces**: interface phase exists on the stress pages, but
  no general Quad/interface phase field in the main colour selector.

## 8. Data Limitations That Cannot Be Fixed in the Viewer

- **Bridge v2 bundles**: only final spring stresses are exported. Per-step
  displacements and interface resultants are present, but per-step stresses,
  strains and plastic strains require a new field export. This applies to
  `3D_bridge`, `2d_bridge` and the `.histra` archive.
- **C# benchmark HRX**: 4,860 Hysteretic normal springs have serialized length
  `0`. Normal strain and plastic maps for those fibres are partial; the viewer
  must not silently fill them with guessed values.
- **ArcLength `LiveLoad_1`**: load factor is not stored in `.Results`; the UI
  continues to show `—`.
- **C# benchmark**: `Trasv_2` springs are absent, so a Transversal2 map is not
  meaningful for this particular model, even if it remains a generic C# feature.
- **Through-thickness interface `Interface5`**: the v2 bundle has the required
  interface geometry and spring data, but current map generation does not use
  it.

## 9. Explicitly Out of Scope

The following are intentionally out of scope for the bridge viewer:

- frame, truss, solid, fibre and vertex element result types;
- model editing, preparation, solving or re-analysis;
- generic C# report/Excel generation;
- design-code checks outside the bridge masonry workflow.

## 10. Deferred Implementation Backlog

Priority for the current bridge work:

1. **P0 — C# face texture fidelity**: six faces, `Interface5`, edge
   interpolation, per-face texture/per-face colours. This applies to both the
   2D and 3D bridge bundles.
2. **P0 — per-step C# `.Results` fields**: start with stress, phase and sliding
   stress for `LiveLoad_1` and `scour_1`.
3. **P1 — interface sliding/out-of-plane/phase maps** in the existing stress
   view, with per-step where data exists.
4. **P1 — restraint/node-C/model-point histories** for scour settlement and
   support response.
5. **P2 — Quad diagonal sigma/phase** for bridge models that use diagonal
   springs.
6. **P2 — modal participation/effective mass/UMax** fields and full
   control-point selection.
7. **P3 — field CSV/report-table export and analysis overlay.**

Do not implement P3 first; it does not improve the correctness of the bridge
stress maps.

## 11. Acceptance Tests for the Fidelity Work

1. For a bridge face, compare C# and viewer `globalStressX/Y/Z/XY/XZ/YZ`,
   principal and Von Mises values at selected face samples.
2. Confirm `globalStressY` is not uniformly zero when through-thickness
   interfaces carry normal stress.
3. Confirm all six Quad faces can carry distinct field values and that
   `Interface5` contributions are present.
4. Confirm per-step C# stress/phase changes between two `LiveLoad_1` steps.
5. Confirm sliding/out-of-plane stress and phase contours match the saved
   interface spring states.
6. Confirm final-step legend ranges and PNG export remain display-only and do
   not alter reader values.
7. Confirm missing Hysteretic lengths remain marked partial, not zero-filled as
   if exact.

## 12. Recheck Triggers

Re-open this report when:

- a new bridge v2 exporter includes per-step spring states;
- C# reference textures/values become available for comparison;
- the bridge workflow requires interface phase/sliding maps;
- a bridge model uses diagonal springs or Transversal2;
- scour settlement/restraint reactions become a report requirement.
