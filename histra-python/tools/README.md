# Commands, diagnostics and reference-generation tools

Installed commands live in `histra.tools` and use
`python -m histra.tools.<module>`. This directory contains checkout-only tools;
it is not included in the installed package. A script without an internal caller
can still be an intentional manual command or fixture regeneration recipe.

## Installed command catalog

Run a module with `--help` for its actual arguments.

| Module | Purpose |
|---|---|
| `run_vert_live` | Standalone Vert and chained Live Load analysis |
| `run_modal` | Single/batch modal analysis and optional C# comparison |
| `validate_modal_results` | Compare saved modal output with a C# result database |
| `compare_csharp_results` | Compare deterministic parity snapshots and C# results |
| `benchmark_csharp_sqlite` | Compare committed nonlinear steps against C# SQLite |
| `benchmark_preprocessing` | Compare freshly generated topology with serialized C# reference geometry |
| `article_models_benchmark` | Canonical Article-model qualification harness |
| `interface_chain_benchmark` | Interface-mutation chain qualification |
| `strategy_benchmark` | Model-specific nonlinear solver-strategy qualification |
| `linear_solver_benchmark` | Sparse linear-backend experiments |
| `cpu_workflow_benchmark` | Compare CPU loading, preparation and solve phases with exact history/state arrays |
| `run_large_model` | One model with separate kernel/BLAS thread teams and a results bundle |
| `setup_openblas` | Install optional project-local LP64 OpenBLAS without changing system packages |
| `native_capacity_benchmark` | Measure FP64 factorization, RHS reuse and numeric refactorization |
| `parallel_solver_jobs` | Run independent CPU model jobs with bounded workers and strict equilibrium checks |
| `pack_results` | Convert native NPZ/HDF5/JSON exports to one verified `.histra` study bundle |
| `release_manifest` | Generate archive SHA-256 checksums |
| `run_benchmark_full_comparison` | Fixture-specific Vert/Soil/scour/Live Load comparison |
| `run_five_scour_comparison` | Recorded five-model scour comparison |
| `run_six_soil_vert_comparison` | Recorded pier-Soil/Vert batch comparison |

The last three comparisons contain model-specific geometry/material selectors;
they are not generic material-assignment tools. Use the session API to define
mutations for a different model.

Console aliases `histra-article-benchmark` and `histra-strategy-benchmark` are
registered in `pyproject.toml`.

## Checkout-only tools

| Location | Retained role |
|---|---|
| `benchmarks/build_*_reference_model*.py` | Reproduce native-reference model inputs |
| `benchmarks/export_*_reference.py` | Export identified C# observations into regression fixtures |
| `benchmarks/export_csharp_spring_response_reference.py` | Run original C# response getter bodies in a controlled .NET harness |
| `benchmarks/masonry_spring_*.py` | Spring reference inputs and fingerprints |
| `benchmarks/probe_native_test_sensitivity.py` | Check whether native-backed tests detect controlled perturbations |
| `benchmarks/build_source_audit_inventory.py` | Refresh tracked AST/source hashes and native evidence bindings |
| `csharp-diagnostics/` | Windows/native C# construction, arithmetic, state and whole-analysis oracles |
| `profiling/profile_scour_workflow.py` | Instrument the recorded `random_005` Vert/scour workload |

Native generators require the identified C# application/source and model assets.
Read their arguments before running them, use separate output directories, and
preserve original input/reference files. See the
[native diagnostics instructions](csharp-diagnostics/README.md) and
[parity guide](../docs/guides/csharp-parity-diagnostics.md).

The source inventory can be regenerated with:

```console
python tools/benchmarks/build_source_audit_inventory.py --source-root C#_Original/source --output docs/audit/csharp-python-source-inventory.json
```

Regenerate it when its inventoried numerical/model sources change; it is an
inventory, not proof of numerical equivalence.

For the historical scour profiler, run from the checkout root:

```console
python -m tools.profiling.profile_scour_workflow --help
python -m tools.profiling.profile_scour_workflow --model path/to/random_005.hrx --no-svg
```

The required model must match the geometry/material assumptions documented in
the script. `psutil` is optional for memory/CPU sampling; SVG output additionally
requires `gprof2dot` and Graphviz. The profiler is model-specific development
instrumentation and does not change production solver defaults.

`bin/setup` is a symlink to `scripts/setup.sh`; both install the
same development environment used by `make setup`.
