# HiStrA model view

Read-only local browser service for the serialized HRX Quad model. Mesh inspection
is independent of the Python numerical runtime; material previews use its spring
laws in an isolated worker. Opening a model never prepares it or runs an analysis.
The original C# export, solver, and legacy viewer remain untouched.

## Run

From this repository's root:

```sh
npm ci --prefix model-view
python3.12 -m venv model-view/.venv
model-view/.venv/bin/python -m pip install -r model-view/requirements-preview.txt
python3 model-view/server.py
```

Open http://127.0.0.1:8765. The bundled `model_example.hrx` opens automatically.
Choose **Open HRX** or drag a file onto the page to inspect another model. Uploads
are processed locally in memory and are not saved. Python 3.10+ and a WebGL-capable
browser are required; Three.js is served locally after installation.

Alternate initial model / port:

```sh
python3 model-view/server.py --model /absolute/path/to/model.hrx --port 8766
```

## Included

- Orbit, pan, zoom, camera presets, fit (`F`), and clear selection (`Escape`).
- Quad mesh with physical per-corner thickness and normals, edges, nodes, opacity,
  layer filtering, and material visibility.
- HRX material colors, names, assignments, mechanical properties, and raw attributes.
- Assigned point, line, and area **force** loads, condition filtering, signed
  direction, proportional arrow lengths, and numeric inspection. Local directions
  follow the target element's reference system, as in C# `LoadTemplateItem.Dir`.
- Restraint geometry, selectable location markers, six local mechanical DOFs,
  stiffness attributes, and reference axes. Generated restraints replace their
  parent geometry definitions to avoid duplicate markers.
- Mesh, material, load, and restraint picking; searchable entity lists.
- **Material properties** workspace page, linked from the header and material
  inspector. Lists only masonry material templates (including unassigned definitions) with
  search and an assigned-only filter. Masonry uses the C# editor's Rocking, Shear,
  and Sliding mechanism groups, local-direction columns, and original reference
  diagrams. General properties include reference ranges and saved corrective
  coefficients; **All properties** preserves the exact serialized definition.
- Material units switch between MPa/N/mm/kN/m³, SI engineering units, and the
  C# kN/cm base representation. A Unit column identifies dimensional properties;
  ratios remain dimensionless and raw attributes remain unchanged.
- Calculated hysteresis previews for rocking, shear, and sliding use independent
  virgin Python springs. Choose strain amplitude, cycles, strain history, and
  applicable local direction; hover for values or export the samples as CSV.
- **Results** page: saved wall deformed-shape playback, static analysis/step
  selection, deformation scale (including actual size and auto scale), undeformed
  outline, edges, physical extrusion and camera presets. Thickness orientation
  follows the displayed Quad plane. Displays actual control displacement,
  maximum nodal displacement and load factor alongside the scaled drawing.
  A linked force–displacement preview appears beside the 3D view on wide screens.
- **Line of thrust & plastic hinges**: toggle **Line of thrust** in the Deformed
  shape view to render the funicular compression trajectory across opposite Quad
  interfaces (`DrawCurvaPressioni` parity) and mark **Plastic hinges** (red dots)
  where eccentricity reaches the section limit ($|e_x| / (L/2) \ge 0.85$). Filter
  between structural blocks (arches, piers & foundations), all blocks, or individual
  materials. Updates dynamically across steps and deformation scales. **Width
  centroid line** (default) collapses the parallel width slices and adjacent
  through-thickness columns into one section-resultant line; turn it off to inspect
  the per-slice C#-parity segments.
- **Modal shapes**: ten modes each for `Modal_0` and `Modal_1`, with frequency,
  period, effective mass percentages and normalized shape animation. Amplitude
  is an explicit visualization setting; animation uses a two-second display
  cycle rather than the high physical frequencies.
- **Response curves**: added vertical force, load factor, three HiStrA reaction
  components and elastic/dissipated energies versus control displacement or
  saved step, with step picking and CSV export. Missing initial energies are
  excluded; signed saved energy values are preserved.
- **Stress contours**: click an actual interface surface in the 3D view to
  inspect its normal spring stress contour in MPa. Restraint interfaces are the
  default; choose **All interfaces in the model** for all 884 interfaces, or
  **Selected interface only** to isolate and zoom in. The 3D faces and the
  selected physical fibre map share one symmetric compression/tension scale.
  Hover a cell for saved stress, force and phase. Constitutive phase coloring
  is also available. Cells use the C#-parity native interface geometry.
  Stress and phase are final-step snapshots, not interpolated histories or
  continuum stresses inside the quads. Intermediate steps hide these snapshots
  and offer a final-step shortcut. Normal force N2 can be played at every saved
  step; it is explicitly a resultant painted uniformly over each interface.
  A collapsed ID finder replaces the selection table. Forces, moments, thrust
  history, sliding-link values and CSV exports are in a separate disclosure.
  Normal stress is fibre force divided by area, converted from kN/cm² to MPa;
  sliding stress is nominal force divided by gross area.
- JSON API: `GET /api/model/example`, `POST /api/model` (raw HRX bytes, max 32 MiB),
  `GET /api/health`, `POST /api/material/preview` (JSON with saved material
  `attributes`, `mechanism`, `direction`, `cycles`, optional `amplitude`, and
  `history`: `cyclic` or `monotonic`).
  `GET /api/results/wall` returns the compact wall displacement projection.
  `GET /api/results/wall/interface?analysis=LiveLoad_1&key=813` returns one
  stage-end interface's spring details. Recent detail responses are cached.
  `GET /api/results/wall/contours?analysis=LiveLoad_1` returns cached stage-end
  fibre contours for all interfaces, with packed little-endian float32 geometry,
  stress, force, area and displacement arrays, plus phase codes and interface
  cell ranges. Only this contour data is requested when the stress view opens.

## Saved wall results

The Results page reads `wall_model/overturning_wall_raw_output.json` (schema
1.1.0). It validates explicit units and source model SHA-256. The matching
`overturning_wall_elastic_foundation.hrx` is optional: when present, its hash
must match. Geometry and shape coefficients come from JSON. It is tied to this supplied wall
bundle, independently of the model opened in the model/materials pages.
The server uses the preview Python environment to recover all saved static
steps once, then caches the compact response until either source file changes.
Geometry, recovered static/modal translations and summary tables reach the
browser; stage-end contour arrays load on demand and additional spring details
load for the selected interface. Pickles are not
loaded by the service.

Recovery calls the existing Python/C#-parity nodal displacement operation with
the exported prepared-model afference and standalone JSON sine/cosine coefficients.
The final recovered nodes are checked against each analysis's saved nodal
table. No preparation or numerical solve runs. Geometry compatibility is
validated before showing results. The current bundle uses cm and kN.

Shared-node displacements are averaged as in the C# output. Physical thickness
can be toggled; separate element-side discontinuities and a continuum stress
tensor field are not shown. Static playback advances saved steps,
not physical time; stage initial deformation is retained. The default drawing
scale is 10×. Numeric result values remain unscaled, and load factor is not
labeled as an applied force. For this vertically loaded wall, added force uses
`initial reaction_z - equilibrium_expected_reaction_z` (or the saved reaction
when no expected value is present), downward positive and relative to the
selected stage's initial load. It is an equilibrium-derived force and can
reflect small differences between saved initial reactions and external load.
The live reference load is approximately 0.44 kN per unit load factor.

Per-step interface resultants now include forces and bending moments. Final
snapshots also include populated local `f` vectors and dense runtime arrays.
The viewer uses explicit interface IDs and an ordered compact six-component
force/moment table for each step. Spring snapshots are still available only at
the three static stage ends and cannot animate individual spring stresses or
phases through intermediate steps. Constitutive phase labels are not relabeled
as a scalar damage variable.

Selected-interface eccentricities are ex = Mz/N2 and ey = Mx/N2, in cm.
Compression thrust points use the native intrinsic origin at (Length/2, 0),
with positive ey along reference_e3. The normal-force guard is max(1e-8 kN,
1e-8 times that interface's peak |N2|); tensile and ill-conditioned resultants
are excluded from compression thrust markers. The thrust path follows one
interface across steps, not a connection between arbitrary interfaces.

## Current boundary

This version displays **serialized Quad geometry**, with geometry coordinates and
load values in **HRX native units**. Material property units use the C# base
definitions (force kN, length cm) and are converted only for display. Other element
families are reported in model notes. It does not generate a missing mesh.

Loads come from `LoadElement` definitions and direct Quad template assignments.
Unassigned template definitions are not loads. Self-weight, vehicle positions,
fill/earth-pressure calculations, generated bridge load patches, moments, and
analysis combination factors are not evaluated. Unsupported assigned loads are
listed and reported, not rendered with guessed directions. Saved displacement
results are available separately on the Results page for the supplied wall.

Load and restraint overlays have independent visibility controls and remain visible
when materials or layers are hidden, allowing inspection through the mesh.

## Validate

```sh
model-view/.venv/bin/python -m unittest discover -s model-view/tests -v
node --check model-view/static/app.js
node --check model-view/static/model-overlays.js
node --check model-view/static/mesh-viewer.js
node --test model-view/tests/material-properties.test.js
node model-view/tests/camera-rendering.test.js
node model-view/tests/material-units.test.js
node model-view/tests/deformation.test.js
node model-view/tests/result-charts.test.js
node model-view/tests/interface-resultants.test.js
node --test model-view/tests/stress-data.test.js model-view/tests/interface-picking.test.js model-view/tests/thrust-line.test.js
```

The mesh renderer is adapted from `view-legacy/viewer-core.js`. Interpretation was
checked against C# `ModelDrawer`, `Quad`, `LoadTemplateItem`, and restraint definitions.
Material grouping and diagram selection follow `MasonryMaterialUserControl.xaml`
and `MasonryMaterialUserControl.InitAdvancedMode`. Diagrams are schematic assets
from the supplied C# export. Separately, the calculated hysteresis preview uses
the Python constitutive laws and spring factories, following the C# unit-coupon
preview convention. The worker runs in a bounded subprocess, with fresh state
for every request. It never prepares or solves the structural model. Shear and
sliding previews have zero applied normal stress, so they do not represent a
specific loaded interface. Fracture-energy coupon scaling follows the C# preview
(energy divided by 100 for rocking/sliding). No design values or correction
coefficients are recomputed.
