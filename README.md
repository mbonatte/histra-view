# HiStrA View

Read-only local browser viewer for HiStrA HRX structural models and saved
analysis results, together with the Python DMEM solver used to generate those
results and the first legacy mesh viewer.

The viewer visualises the serialized Quad mesh, materials, loads, restraints,
deformed shapes, modal shapes, response curves, interface forces and thrust
lines. It never prepares a model or runs a numerical analysis.

## Repository layout

| Path | Contents |
| --- | --- |
| `model-view/` | Current local browser service: Python HTTP server, Three.js frontend, result projections and tests. |
| `histra-python/` | Python implementation of the HiStrA/DMEM numerical solver, including preparation, constitutive laws, static/modal solvers, CLI tools and reference tests. See `histra-python/AGENTS.md` for its operating rules. |
| `view-legacy/` | First standalone Quad mesh viewer; the current renderer was adapted from it. |
| `model_example.hrx` | Default sample model opened by the viewer. |
| `wall_model/` | Overturning-wall input model and result inspection report. |
| `3D_bridge/` | Three-span masonry arch bridge input model. |

## Run the viewer

From the repository root:

```sh
npm ci --prefix model-view
python3.12 -m venv model-view/.venv
model-view/.venv/bin/python -m pip install -r model-view/requirements-preview.txt
python3 model-view/server.py
```

Open <http://127.0.0.1:8765>. The bundled `model_example.hrx` opens
automatically. Use **Open HRX** or drag a file onto the page to inspect another
model.

Python 3.10+ and a WebGL-capable browser are required. Three.js is served
locally from `model-view/node_modules`.

## Run the tests

```sh
cd model-view
npm test
```

That runs the Python projection tests and the Node/Three.js JavaScript tests.
The Python solver has its own suite:

```sh
cd histra-python
python -m pytest histra/tests -q
```

Some solver integration tests require the representative HRX/`.Results`
fixtures under `histra-python/histra/model-*` and may skip when those assets are
not installed.

## Saved result data

The **Results** page reads generated result bundles next to the input models:

- `wall_model/overturning_wall_raw_output.json`
- `3D_bridge/pdelta_soft_subgrade_phase4_results.json` plus its per-case
  `pdelta_scour4_soft_*.summary.json` and `.fields.npz` files

Those files are intentionally not tracked because they are large generated
exports. Place them beside the corresponding `.hrx` files to enable the Results
page. The viewer validates units, schema version and the source model SHA-256
before displaying them. The bridge v2 bundle loads one analysis at a time; the
Standard cases are curve-only and have no field files.

## Not tracked in this repository

- `C#_Original/`: a local decompiled export of the installed HiStrA vendor
  application, used as an implementation reference. It contains third-party and
  decompiled code and is not redistributed here.
- Raw result bundles (`*.json`, `*.pkl`, `*.npz`) and virtual environments.
- Third-party papers and the vendor manual under
  `histra-python/docs/references/`.

## License

No license has been declared for this repository.
