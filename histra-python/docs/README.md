# Documentation

- [Current source inventory, audit corrections and remaining validation](audit/csharp_python_function_mapping_matrix.md)

## Architecture audit chapters

These earlier source-review chapters explain the implementation and its design.
Their coverage scores and release statements are historical audit claims, not
complete numerical qualification of the current package. Use [current status](STATUS.md),
the native-backed tests and identified benchmark reports for current parity scope.
The source review compares the Python DMEM implementation with C# HiStrA:

- **[Executive Summary & Architecture Review](audit/00_executive_summary.md)**: Architecture comparison, multi-chapter synthesis, historical release assessment, and expansion roadmap.
- **[Chapter 01: Master Numerical Core File-by-File Coverage Matrix](audit/01_file_coverage_matrix.md)**: Exhaustive mapping of all 117 Python production files and 426 unique C# core files across `SolverRuntime`, `MatrixManager`, `ModelLibrary`, `ModelManagement`, `Objects`, `SectionBuilderCore`, and `AdapticIO`.
- **[Chapter 02: Mathematical, Constitutive, and Algorithmic Parity of Elements, Springs, and Materials](audit/02_elements_and_materials_parity.md)**: Line-by-line mathematical audit of 7-DOF Quads, 12-DOF Interfaces, Mohr-Coulomb/Cacovic shear, axial hysteretic fiber springs, and unported element/material catalog.
- **[Chapter 03: Solvers, Numerical Algorithms, and Eigenvalue Analysis](audit/03_solvers_and_algorithms_parity.md)**: Newton-Raphson tangent rebuild policies, Crisfield/Linearized Arc-Length continuation, Line Search root-finding, modal subspace iteration with Knuth PRNG seeding (MAC > 0.9999), and the independent dual-mode `EquilibriumAudit`.
- **[Chapter 04: Mesh Preprocessing, Boundary Autonomy, and I/O Parity](audit/04_preprocessing_and_io_parity.md)**: Fresh model preparation boundary (`force=True`), 6-face coplanar contact detection, Sutherland-Hodgman polygon clipping, 2D Newton inverse bilinear mapping, streaming XML ingestion (`iterparse`), and SQLite output projections.
- **[Chapter 05: Exhaustive Catalog of Unimplemented C# Features, Algorithms, and Models](audit/05_unimplemented_features_catalog.md)**: Exhaustive catalog of 248 unported C# core files across 5 functional domains (12 elements, 7 materials, 10 springs, transient dynamics, response spectra), 3-tier fail-closed preflight guards, and 5-phase expansion roadmap.

## Start here

- [Project status](STATUS.md)
- [V1.0.0 implementation and validation plan](release/v1-implementation-plan.md)
- [V1.0.0 release checklist](release/v1-release-checklist.md)
- [V1 independent review and open findings](release/v1-independent-review.md)
- [Standalone HRX analysis](guides/standalone-analysis.md)
- [Analysis chains and interface mutation](guides/analysis-chains.md)
- [Preprocessing](guides/preprocessing.md)
- [Documentation and JSON policy](DOCUMENTATION_POLICY.md)

## Reference

- [C# to Python Feature Matrix](reference/v1-csharp-feature-matrix.md)
- [Supported Features](reference/v1-supported-features.md)
- [Data Model](reference/data-model.md)
- [Glossary](reference/glossary.md)
- [Porting Notes](reference/porting-notes.md)

## Benchmarks & Methodology

- [Dhir full static-chain parity](benchmarks/dhir-full-chain-native-parity-progress.md)
- [Dhir horizontal out-of-plane parity](benchmarks/dhir-horizontal-native-parity.md)
- [Masonry original-source audit](benchmarks/masonry-source-audit-2026-10-14.md)
- [Masonry precision-boundary audit](benchmarks/masonry-precision-audit-2026-10-16.md)
- [Solver Strategy Methodology](benchmarks/solver-strategy-methodology.md)
- [Article Models Release Gate](benchmarks/article-models-release-gate.md)
- [Wall Overturning Benchmark](benchmarks/wall_6_rows_benchmark.md)
- [Nonlinear Convergence Safety](nonlinear_convergence_safety.md)

## Investigations

- [Benchmark 3 Base-Spring Consistency & Parity (Resolved)](investigations/benchmark-3-base-spring-reference-consistency.md)

## Archive

`archive/` preserves audit deliverables, generated source inventories, patches,
old metrics, and superseded handoff reports. Archived files are historical evidence,
not current release guidance.

