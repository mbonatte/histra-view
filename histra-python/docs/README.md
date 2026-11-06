# Documentation

Start with [current status](STATUS.md) for the supported boundary. Use the guides
for workflows and the reference pages for API/data conventions. Dated reports
qualify their recorded inputs and source revisions, rather than the entire package.

## Guides

- [Standalone Vert → Live Load](guides/standalone-analysis.md)
- [Analysis chains and interface mutation](guides/analysis-chains.md)
- [Faster CPU analyses and independent process jobs](guides/cpu-performance.md)
- [Fresh HRX preprocessing](guides/preprocessing.md)
- [Modal analysis](guides/modal-analysis.md)
- [C# parity diagnostics](guides/csharp-parity-diagnostics.md)
- [Experimental GPU sparse solving and CPU/GPU comparisons](guides/gpu-solving.md)
- [Nonlinear convergence and equilibrium safety](nonlinear_convergence_safety.md)
- [Development commands and reference tools](../tools/README.md)
- [Release verification and publication](release/README.md)

## Reference

- [Architecture and subsystem ownership](reference/architecture.md)
- [Supported features](reference/v1-supported-features.md)
- [C# feature matrix](reference/v1-csharp-feature-matrix.md)
- [Data model](reference/data-model.md)
- [C# SQLite results export](reference/csharp-results-export.md)
- [Single-file study bundles](reference/histra-bundle-format.md)
- [Native simulation results format](reference/native-results-format.md)
- [Glossary](reference/glossary.md)
- [Porting notes](reference/porting-notes.md)
- [Repository maintenance and retention](reference/repository-maintenance.md)
- [Documentation and generated-artifact policy](DOCUMENTATION_POLICY.md)

## Evidence and investigations

- [Benchmark catalog](benchmarks/README.md)
- [Current source inventory and audit corrections](audit/csharp_python_function_mapping_matrix.md)
- [Masonry source audit and remaining checks](benchmarks/masonry-source-audit-2026-10-14.md)
- [Masonry precision-boundary audit](benchmarks/masonry-precision-audit-2026-10-16.md)
- [Solver strategy qualification methodology](benchmarks/solver-strategy-methodology.md)
- [Article model qualification](benchmarks/article-models-release-gate.md)
- [Benchmark 3 preprocessing/material-state investigation](investigations/benchmark-3-base-spring-reference-consistency.md)
- [C# and Python branch divergence](investigations/csharp-python-branch-divergence.md)

The earlier architecture audit chapters in `audit/00_*.md` through `audit/05_*.md`
are source-review records. Their original coverage scores and release statements
must be read alongside the current audit corrections and benchmark evidence.

## Historical records

[Archive overview](archive/README.md) identifies superseded plans, old architecture
snapshots and original audit deliverables. These preserve development history and
are not current installation, release or numerical-qualification instructions.
