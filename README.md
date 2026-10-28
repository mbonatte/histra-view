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
| `model_example.hrx` | Optional sample model; not opened automatically. |
| `results/wall_model/` | Overturning-wall input model and result inspection report. |
| `results/3D_bridge/` | Three-span masonry arch bridge input model and legacy v2 result bundle. |
| `results/2d_bridge/` | Plane masonry arch bridge; normalized native v2 results under `results/`. |
| `results/native_soil_15e3/` | Official self-contained `.histra` bridge result archive (104 cases). |
| `results/benchmark/` | Legacy native C# benchmark HRX plus `.Results` database. |
| `results/Bridge_scour_3d_Distributed_PDelta/` | New standard native C# 3D bridge scour/P-Delta HRX and `.Results` pair. |
| `MODEL_RESULTS_LAYOUT.md` | Naming and folder convention for future models and result bundles. |

## Importing results

**Import Results** is the primary workflow. Select a matching HRX model with a
native C# `.Results` database, a self-contained `.histra` archive (static or
modal-only), an RAR/ZIP archive containing the HRX and result pair, or a projected `.json` result file.
The browser uploads them to a temporary local session; the viewer projects them
read-only and registers a temporary source so analysis switching works;
imported files are session-local and are cleared when the server restarts.
The preloaded `results/` sources are optional and can be removed.

## Run the viewer

From the repository root:

```sh
npm ci --prefix model-view
python3.12 -m venv model-view/.venv
model-view/.venv/bin/python -m pip install -r model-view/requirements-preview.txt
python3 model-view/server.py
```

Open <http://127.0.0.1:8765>. The page starts blank. Use **Open HRX** to load a
model, or **Import Results** to load an HRX + `.Results` pair, `.histra` file, or
archive. No previous model or result source is loaded automatically.

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

- `results/wall_model/overturning_wall_raw_output.json`
- `results/3D_bridge/pdelta_soft_subgrade_phase4_results.json` plus its per-case
  `pdelta_scour4_soft_*.summary.json` and `.fields.npz` files
- `results/2d_bridge/results/manifest.json` plus its native per-case `.summary.json` and
  `.fields.npz` files
- `results/native_soil_15e3/native_soil_15e3.histra` (self-contained native archive)
- `results/benchmark/benchmark.Results` with `benchmark/benchmark.hrx`
- `results/Bridge_scour_3d_Distributed_PDelta/` native C# 3D scour/P-Delta
  `.hrx` and `.Results` pair

The server resolves both the legacy flat layout and the `results/` layout. Those files are intentionally not tracked because they are large generated
exports. Place them beside the corresponding `.hrx` files to enable the Results
page. The viewer validates units, schema version and the source model SHA-256
before displaying them. The bridge v2 bundles load one analysis at a time; the
Standard cases are curve-only and have no field files. The reusable naming and
folder convention is documented in
[`MODEL_RESULTS_LAYOUT.md`](MODEL_RESULTS_LAYOUT.md).

## Not tracked in this repository

- `C#_Original/`: a local decompiled export of the installed HiStrA vendor
  application, used as an implementation reference. It contains third-party and
  decompiled code and is not redistributed here.
- Raw result bundles (`*.json`, `*.pkl`, `*.npz`) and virtual environments.
- Third-party papers and the vendor manual under
  `histra-python/docs/references/`.

## License

No license has been declared for this repository.
