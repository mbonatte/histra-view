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
  exceed the 3,216 Quad nodes, so use `mesh/interfaces[*].points` /
  `interface_node_xyz`, not only the mesh node map.
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
  `M23` the out-of-plane sliding stress; the tensor is rotated to global axes
  and the invariant is evaluated per Quad corner. The v2 bundle stores spring
  stresses only at the final stage end, so the map is final-step only and the
  UI disables playback in that mode. Do not present it as a continuum stress
  tensor or as available at intermediate steps.
- The saved-result payload is projected in `result_preview.py`/`bridge_v2.py`
  and cached by the server keyed on every referenced file's timestamp. Clear
  that cache only by changing the source files or restarting the server.
- Keep source units explicit. HRX geometry and load values are native units;
  material-property conversions are display-only. Bridge results are
  cm/kN/kN·cm; do not label them mm.
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
