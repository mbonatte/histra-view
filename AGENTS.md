# AGENTS.md

Repository-level operating notes for coding agents working on HiStrA View.

## Project map

- `model-view/` is the deliverable: a read-only local browser service for HRX
  models and saved results. It has a Python projection server (`server.py`,
  `result_preview.py`, `hrx_model.py`) and a Three.js frontend under `static/`.
- `histra-python/` is the Python DMEM solver. Its own rules and numerical
  invariants are in `histra-python/AGENTS.md`; read that file before changing
  solver code.
- `view-legacy/` is the first viewer and the source of the current renderer.
- `C#_Original/` is a local decompiled reference only. It is not tracked in the
  repository. Do not copy vendor or third-party source into tracked files.

## Commands

```sh
# Viewer server (from model-view/)
npm start

# Viewer Python + JavaScript tests (from model-view/)
npm test

# Python solver tests (from histra-python/)
python -m pytest histra/tests -q
```

The viewer server requires `model-view/.venv`; setup is documented in
`model-view/README.md`.

## Data boundaries

- Treat HRX models and `.Results` databases as read-only inputs.
- Do not commit `.venv/`, `node_modules/`, `__pycache__/`, raw result JSON/PKL/NPZ
  bundles, or build output. Root `.gitignore` covers these.
- The raw result bundles required by the Results page are intentionally absent
  from Git; keep them locally next to their HRX files when testing.
- Do not present an intermediate result snapshot as a saved final state, and do
  not run a new numerical solve merely to populate the viewer.

## Viewer implementation notes

- `model-view/bridge_v2.py` projects the native bridge v2.0.0 bundle. It serves
  one analysis per request; `analysisCatalog`/`defaultAnalysis` drive lazy
  switching in `results.js`. Standard cases are curve-only. Interface nodes can
  exceed the Quad nodes, so use `mesh/interfaces[*].points` /
  `interface_node_xyz`, not only the mesh node map. The adapter supports both
  the legacy `3D_bridge` aggregate and normalized `results/manifest.json`
  bundles; mesh node/Quad/interface counts must come from the bundle, not a
  fixed bridge size.
- `MODEL_RESULTS_LAYOUT.md` defines the naming and folder convention for new
  models. The `2d_bridge/` source is the reference layout: canonical HRX at the
  dataset root, normalized manifest under `results/`, and producer-native
  outputs under `results/native/`.
- `model-view/histra_results.py` projects the official self-contained
  `native_soil_15e3.histra` archive. It reads the ZIP manifest, extracts the
  embedded HRX in memory, and decodes `byte-shuffle-v1` arrays from the
  content-addressed object store. Static and modal-only `.histra` schemas are
  supported; modal archives use their modal node list plus the HRX Quad mesh.
  The archive is read-only. It is not auto-loaded; import it explicitly.
- `model-view/csharp_results.py` projects a native C# `.Results` SQLite database
  beside its HRX. The primary current dataset is
  `results/Bridge_scour_3d_Distributed_PDelta/`; the older `results/benchmark/`
  pair is retained for comparison. It reads committed `QuadStates`, `InterfaceStates`,
  `SpringStatesTmp`, model-point and modal tables directly and never prepares or
  solves. Static shapes use the C# local Quad vertex kinematics; nodal values
  use the same shared-node averaging convention. `LoadControl` load factors are
  reconstructed from the HRX load function; `ArcLength` load factors are not
  stored and remain null.
- `model-view/RESULTS_FIDELITY.md` records the bridge-focused C# parity gaps,
  data limitations and deferred implementation backlog. Keep it updated when
  changing the face-texture path or per-step result loading.
- `model-view/result_fields.py` defines the shared `stressFields` menu and units.
  The payload mirrors the C# result menu: global tensor components, principal
  and Von Mises stress, and local interface normal/shear components. Strain and
  plastic fields are included only when the source stores the required spring
  length/state; unavailable maps stay in the list as disabled descriptors. Do
  not relabel a partial map as complete. Palette and explicit/auto colour-range
  controls are display-only and must not alter saved values. Thrust-line
  filtering uses the compressive normal resultant magnitude in kN and is applied
  to both segments and hinges.
- `model-view/static/export-image.js` captures the current WebGL view at high
  resolution for reports. Keep `preserveDrawingBuffer` enabled on the renderer,
  restore the renderer/camera/background after export, and do not claim PDF is
  vector output: the 3D view is raster.
- `model-view/static/thrust-line.js` computes the funicular thrust line and
  plastic hinges. Width grouping must use the **undeformed** mesh nodes from
  `mesh.nodes`; the deformed node map is only for drawing playback positions.
  Collinear, touching joint interfaces across through-thickness columns are
  merged into one section resultant. Interface points are the fallback for
  interface-only nodes.
- Bridge thrust pairs must be built from `quad_interface_keys` plus
  `quad_face_interface_offsets`: only pair opposite faces when each face has
  exactly one interface. That reproduces the 3,752-pair topology.
- The bridge Von Mises map follows the C# interface tensor construction:
  local `M22` is the normal spring stress, `M12` the in-plane sliding stress and
  `M23` the out-of-plane sliding stress; the tensor is rotated to global axes.
  Bridge v2/native fields now carry `quadFaceValues` for all six physical Quad
  faces and, where the C# adaptive grid is larger than 2×2, `quadFaceGrids`;
  the renderer uses `quad.faceColors`/`quad.faceGrids`. Native C# `.Results`
  carries the six-face corner path. This includes the previously ignored
  through-thickness faces, but it is not yet byte-exact C# texture parity:
  the exact `AddTensorOnEdge` reference-system form, spring-cell tolerance and
  edge fallback remain to be validated. The v2 bundle stores spring stresses
  only at the final stage end, so bridge v2/native maps are final-step only and
  the UI disables playback in that mode. Native C# `.Results` supports lazy
  per-step Quad fields through `/api/results/<native-csharp-source>/fields`; the
  native C# `/contours` and `/interface` endpoints accept the same `step` query. Do not
  present the bridge bundle as a continuum stress tensor or as available at
  intermediate steps.
- The saved-result payload is projected in `result_preview.py`/`bridge_v2.py`
  and cached by the server keyed on every referenced file's timestamp. Clear
  that cache only by changing the source files or restarting the server.
- Keep source units explicit. HRX geometry and load values are native units;
  material-property conversions are display-only. Bridge results are
  cm/kN/kN·cm; do not label them mm.
- **Import Results** is the primary user workflow; preloaded `results/` sources
  are optional. The server streams HRX/`.Results`/archive files into a temporary import
  session, projects them read-only, and registers the imported dataset as a
  temporary source so analysis switching and per-step fields work. Import
  accepts an HRX plus `.Results`, a self-contained `.histra`, an RAR/ZIP
  archive, or a JSON projection. Keep the temporary import path out of Git.
- The viewer is read-only: opening a model must not prepare it, run an analysis,
  or write to the source files.
- Add focused regression tests for numerical projection, picking and rendering
  changes. `model-view/tests/test_bridge_v2.py` covers the bridge adapter and
  `model-view/tests/thrust-line.test.js` covers the thrust-line cases.

## General rules

- Prefer small, focused changes that match the existing module structure and
  naming conventions.
- Preserve C# parity and saved-result semantics; do not silently relabel,
  interpolate or recompute values.
- Keep generated artifacts and third-party material out of commits.
- Run the relevant test suite before committing.
