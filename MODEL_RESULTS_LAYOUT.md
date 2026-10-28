# Model and Result Data Layout

This document defines the layout for new HiStrA models and saved result sets so
the browser can add them without ad-hoc path handling.

The existing result folders now live under `results/` (for example
`results/3D_bridge/`, `results/wall_model/` and `results/benchmark/`). The viewer
resolves both this layout and the older flat layout. Preloaded datasets are
optional: **Import Results** accepts an HRX plus `.Results`, a self-contained
`.histra`, an RAR/ZIP archive, or a projected `.json` and streams it into a
temporary import session. Imported files are registered as a temporary source for the session and are
cleared on server restart. Do not move a folder just to match this convention; migrate a
folder only when its result source is intentionally reworked.

## 1. Proposed layout

Use one folder per model/case set:

```text
<dataset-id>/
  README.md
  <Model>.hrx                         canonical HRX input
  results/
    manifest.json                     normalized viewer manifest
    simulation_results.json           optional derived post-processing
    native/                           producer-native raw outputs
      <Model>_<Case>.summary.json
      <Model>_<Case>.fields.npz
      <Model>_<Case>_final.vtu
      <Model>_<Case>_peak.vtu
      <producer>.session.json
    csharp/                           optional native C# results
      <Model>.Results
      <Model>.hrx                     optional exact producer copy
```

Rules:

- `<dataset-id>` is lowercase ASCII with underscores, for example
  `2d_bridge`, `3d_bridge`, `benchmark`, `bridge_scour_3d_distributed_pdelta`.
- The canonical model stays at the dataset root. Use the original model name
  when practical; do not rename files just to make a display title.
- Generated result files live under `results/`, never beside the canonical
  model except in a documented legacy layout.
- Paths in `manifest.json` are relative to the manifest itself and must not be
  absolute.
- Raw result files are generated data and should normally be ignored by Git.
  The small `manifest.json` and `README.md` are the reviewable artefacts.
- Case IDs are stable and equal to the analysis names used in the viewer. Do
  not rename them between regenerations without updating the manifest.
- Keep the model SHA-256 in both the manifest and the C#/native summaries. The
  viewer must fail closed when they disagree.

## 2. Bridge v2 manifest

New bridge-native bundles should provide a normalized `results/manifest.json`.
The adapter accepts the existing aggregate v2 format and this normalized form:

```json
{
  "schema_version": "2.0.0",
  "format": "bridge-v2-normalized",
  "units": {
    "length": "cm",
    "displacement": "cm",
    "force": "kN",
    "moment": "kN*cm",
    "stress": "MPa",
    "rotation": "rad"
  },
  "metadata": {
    "title": "2D Bridge · interface-distributed masonry arch",
    "model_file": "Bridge.hrx",
    "models": {
      "P_Delta": {
        "file": "Bridge.hrx",
        "sha256": "<64 hex characters>"
      }
    }
  },
  "baseline_case": {
    "summary": "native/Bridge_Initial_state.summary.json",
    "fields": "native/Bridge_Initial_state.fields.npz"
  },
  "default_case": "Pushover_Span2_Quarter",
  "cases": {
    "Pushover_Span2_Quarter": {
      "id": "Pushover_Span2_Quarter",
      "analysis_name": "Pushover_Span2_Quarter",
      "curve_only": false
    }
  },
  "files": {
    "Pushover_Span2_Quarter": {
      "summary": "native/Bridge_Pushover_Span2_Quarter.summary.json",
      "fields": "native/Bridge_Pushover_Span2_Quarter.fields.npz"
    }
  },
  "source": {
    "kind": "native-v2-session",
    "session": "native/bridge_intact_4loads.session.json"
  }
}
```

`baseline_case` may be omitted only if there is no initial/baseline case.
`default_case` is optional; without it the adapter prefers
`Pushover_Span2_Quarter`.

## 3. C# `.Results` sources

For a native C# result database, keep the HRX and database together:

```text
<dataset-id>/
  README.md
  <Model>.hrx
  results/
    csharp/
      <Model>.Results
```

The viewer's C# adapter finds the HRX by a relative source entry, not by
inferring through the database. Add a source registration in
`model-view/server.py` with the model and `.Results` paths.

C# `.Results` files are large; they remain local and are not committed.

## 3.1 Self-contained `.histra` archives

A native `.histra` archive is also a valid single-file dataset. It contains:

```text
manifest.json
models/<sha256>.hrx
objects/<sha256>.bin
```

The manifest declares `format: "histra-results"`, `schema_version: "1.0.0"`,
`array_encoding: "byte-shuffle-v1"` and a case map. Keep it in a dataset folder:

```text
<dataset-id>/
  README.md
  <dataset-id>.histra
```

The viewer checks the embedded HRX SHA-256, decodes arrays in memory and never
rewrites the archive. Archives are generated result data and are ignored by Git.

## 4. File naming

Preferred names:

| Kind | Pattern | Example |
| --- | --- | --- |
| Canonical model | `<Model>.hrx` | `Bridge.hrx` |
| Native case summary | `<Model>_<Case>.summary.json` | `Bridge_Pushover_Span2_Quarter.summary.json` |
| Native case fields | `<Model>_<Case>.fields.npz` | `Bridge_Pushover_Span2_Quarter.fields.npz` |
| VTU peak | `<Model>_<Case>_peak.vtu` | `Bridge_Pushover_Span2_Quarter_peak.vtu` |
| VTU final | `<Model>_<Case>_final.vtu` | `Bridge_Pushover_Span2_Quarter_final.vtu` |
| Producer session | `<producer>.session.json` | `bridge_intact_4loads.session.json` |
| C# database | `<Model>.Results` | `Bridge.Results` |
| Native archive | `<dataset-id>.histra` | `native_soil_15e3.histra` |

The native archive is preferred over the older bridge-v2 folders when both are
present; its case IDs are the viewer analysis names.

Use underscores in case IDs and filenames. The preferred form prefixes each
producer file with the model name to avoid collisions when several models share
one results directory; a bare `<Case>.summary.json` is acceptable only when the
directory is dedicated to one model. Avoid spaces, version suffixes in case IDs,
and ambiguous names such as `results.json` or `fields.npz`. The manifest case
keys and `analysis_name` values stay identical across producers.

## 5. Adding a new source

1. Create `<dataset-id>/` with `README.md` and the canonical HRX.
2. Put producer output under `results/<producer>/`.
3. Create `results/manifest.json` with relative paths and the model SHA-256.
4. Add a `RESULT_SOURCES` entry in `model-view/server.py`:

   ```python
   "bridge2d": {
       "label": "2D Bridge",
       "folder": "2d_bridge",
       "model": "Bridge.hrx",
       "output": "results/manifest.json",
   }
   ```

5. If the format is new, add a projection module and dispatch it from
   `result_preview.py`; do not overload an unrelated adapter.
6. Add a focused test with `@skipUnless` for the local result files.
7. Verify `/api/results/catalog`, the default analysis, deformed shape,
   response curves, contours and export.
8. Record known data limitations in the dataset README and, for bridge work, in
   `model-view/RESULTS_FIDELITY.md`.

## 6. Current sources

| Source | Layout | Adapter |
| --- | --- | --- |
| `native_soil` | `results/native_soil_15e3/native_soil_15e3.histra` | `histra_results.py` |
| `bridge` | Legacy aggregate v2 at `results/3D_bridge/` | `bridge_v2.py` |
| `bridge2d` | Normalized manifest at `results/2d_bridge/results/manifest.json` | `bridge_v2.py` |
| `benchmark` | Legacy flat HRX + C# `.Results` at `results/benchmark/` | `csharp_results.py` |
| `bridge_scour` | New native C# 3D scour/P-Delta pair at `results/Bridge_scour_3d_Distributed_PDelta/` | `csharp_results.py` |
| `wall` | Legacy wall JSON at `results/wall_model/` | `result_preview.py` |

## 7. Git policy

Track:

- the canonical HRX when it is small enough for the repository;
- dataset `README.md`;
- normalized `results/manifest.json`;
- source code and tests.

Ignore:

- `*.fields.npz`, `*.vtu`, large `*.Results`, producer `.session.json`,
  summaries and derived `simulation_results.json` unless a specific small
  fixture is deliberately reviewed.
