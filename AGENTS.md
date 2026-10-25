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
- Do not commit `.venv/`, `node_modules/`, `__pycache__/`, raw result JSON/PKL
  bundles, or build output. Root `.gitignore` covers these.
- The raw result bundles required by the Results page are intentionally absent
  from Git; keep them locally next to their HRX files when testing.
- Do not present an intermediate result snapshot as a saved final state, and do
  not run a new numerical solve merely to populate the viewer.

## Viewer implementation notes

- `model-view/static/thrust-line.js` computes the funicular thrust line and
  plastic hinges. Width grouping must use the **undeformed** mesh nodes from
  `mesh.nodes`; the deformed node map is only for drawing playback positions.
  Collinear, touching joint interfaces across through-thickness columns are
  merged into one section resultant.
- The saved-result payload is projected in `result_preview.py` and cached by the
  server keyed on source-file timestamps. Clear that cache only by changing the
  source files or restarting the server.
- Keep source units explicit. HRX geometry and load values are native units;
  material-property conversions are display-only.
- The viewer is read-only: opening a model must not prepare it, run an analysis,
  or write to the source files.
- Add focused regression tests for numerical projection, picking and rendering
  changes. `model-view/tests/thrust-line.test.js` covers the thrust-line cases.

## General rules

- Prefer small, focused changes that match the existing module structure and
  naming conventions.
- Preserve C# parity and saved-result semantics; do not silently relabel,
  interpolate or recompute values.
- Keep generated artifacts and third-party material out of commits.
- Run the relevant test suite before committing.
