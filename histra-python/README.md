# histra-python

An in-process Python implementation of HiStrA's Discrete Macro-Element Method
(DMEM) for supported masonry static nonlinear and modal analyses. It loads HRX
models, regenerates computational topology, runs staged analyses, and exports
native results for postprocessing.

Numerical parity is qualified for identified C# reference models and checked
fields. See [current capabilities and limitations](docs/STATUS.md) and the
[documentation index](docs/README.md).

## Install

From a checkout, using Python 3.12–3.14:

```console
python -m pip install -e .
```

Runtime dependencies and version bounds are declared in `pyproject.toml`.
`requirements.txt` is a compatibility entry point to the same package install.
Optional HDF5 export requires `h5py`; otherwise an HDF5 request falls back to NPZ
with a warning.

## Run and export an analysis

Use an analysis name present in your HRX:

```python
from histra import AnalysisSession, SimulationResults, load_model

model = load_model("bridge.hrx")
session = AnalysisSession(model, equilibrium_policy="error")
execution = session.run("Vert")
bundle = session.export_bundle("python-results/bridge.histra")

with SimulationResults.load(bundle, case_id="Vert") as results:
    displacement_mm, total_force_kN = results.get_pushover_curve()
```

A session freshly prepares serialized HRX models before solving. For a staged
model, `session.run_to("LiveLoad_1")` resolves its HRX predecessor chain and
retains committed state in memory. Apply interface-material changes only at
committed analysis boundaries. See [analysis chains](docs/guides/analysis-chains.md)
and [preprocessing](docs/guides/preprocessing.md).

Use `.histra` for one portable, losslessly compressed study file containing all
exported analyses, summary curves, dense fields and the source HRX when available.
Identical arrays are stored once across cases. Native schema 2.1.0 also exposes
committed spring strain, plastic demand and C# phase/rupture indicators with
explicit validity masks. Summary JSON also includes named model-point XYZ
displacement histories for plotting without loading dense fields. Existing
JSON/NPZ/HDF5 exports remain supported; their API defaults are preserved for compatibility.

C# SQLite `.Results` export is also available with capture enabled before solving;
see the [native export guide](docs/reference/csharp-results-export.md) for the
exactness contract and supported scope.

Convert existing exports without rerunning the solver:

```console
python -m histra.tools.pack_results python-results --output bridge.histra --model bridge.hrx
```

See the [bundle guide and specification](docs/reference/histra-bundle-format.md)
and [numerical results schema](docs/reference/native-results-format.md) for
loading cases, cleanup options, units and force conventions.

For the standalone command:

```console
python -m histra.tools.run_vert_live bridge.hrx --output-dir python-results
```

Analysis selectors and output/status details are in the
[standalone guide](docs/guides/standalone-analysis.md). `python -m histra` inspects
and assembles a model; it is not the standalone nonlinear analysis runner.

## Backend service API

Output requests are attribute containers, compatible with a caller's existing
request classes. This example requests all available reaction rows:

```python
from types import SimpleNamespace
from histra import PythonAnalysisRequest, run_python_solver_job

outputs = SimpleNamespace(
    reactions=SimpleNamespace(enabled=True, all_steps=True),
)
result = run_python_solver_job(
    "bridge.hrx",
    [PythonAnalysisRequest(name="Vert", output_request=outputs, timeout_seconds=600)],
    timeout_seconds=600,
)
```

The service loads the HRX once, resolves dependencies, preserves committed
state, supports concrete interface-material mutations between analyses, and
enforces cooperative deadlines. It projects C#-compatible model-point
translations and reactions, and supports modal summaries and mode shapes.
See the [architecture](docs/reference/architecture.md) and
[output format](docs/reference/native-results-format.md).

## Modal analysis and C# comparison

```console
python -m histra.tools.run_modal bridge.hrx --analysis 30 --output modal.json
python -m histra.tools.run_modal my_model/modal-tests --analysis 30
```

The batch runner discovers same-stem `.Results` databases for C# comparisons.
Mode-shape checks use sign-invariant MAC. See the
[modal guide](docs/guides/modal-analysis.md) and
[command catalog](tools/README.md).

## Numerical safety and supported scope

The supported structural domain is masonry Quad/Interface models. Capability
preflight rejects unsupported element types, solver/material enums, loading
paths and response-spectrum contributions. Modal eigenanalysis is supported;
nonlinear dynamics and response-spectrum solving are not.

Production numerical execution requires compiled Numba coverage. One solve
runs per Python process because runtime arrays are shared. Cancellation is
cooperative at solver checkpoints; a native linear solve cannot be interrupted
mid-call.

The backend job API uses strict equilibrium auditing by default. Direct session
calls default to warnings; the example above requests strict auditing explicitly.
Work and DispRotation convergence alone do not establish force equilibrium.
Recommendations from the strategy advisor do not change the authored analysis
and require model-specific qualification. See
[convergence safety](docs/nonlinear_convergence_safety.md).

SciPy SuperLU is the default linear backend. For branch-sensitive C# parity
checks, use `HISTRA_LINEAR_SOLVER=umfpack` and set `HISTRA_UMFPACK_LIBRARY` to
the native library. See [parity diagnostics](docs/guides/csharp-parity-diagnostics.md).

## Development and repository layout

```console
make setup
make check
.venv/bin/python -m pytest -q
```

`make check` runs lint, configured type checks and compact release tests. The
complete suite additionally exercises native fixtures; some larger benchmarks
require external models or opt-in environment variables.

| Directory | Purpose |
|---|---|
| `histra/` | Installable package, tests and retained numerical reference models |
| `docs/` | Current guides, references, dated benchmark reports and historical archive |
| `tools/` | Source-checkout reference generators, native C# diagnostics and profiling |
| `examples/` | Supplementary analytical examples, outside the production solver |
| `release-evidence/` | Compact, traceable benchmark evidence and original source data |

[Release verification](docs/release/README.md) documents packaging and publication.
[Repository maintenance](docs/reference/repository-maintenance.md) explains file
retention and cleanup decisions. The [changelog](CHANGELOG.md) records changes.
