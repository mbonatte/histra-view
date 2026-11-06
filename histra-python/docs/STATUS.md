# Current feature status

The latest package release is **1.7.3**. Its native results schema is **2.1.0**;
package and file-format versions are independent. The
[results reference](reference/native-results-format.md) defines corrected units,
force curves, topology, named model-point histories and stage-end spring strain/plastic-state snapshots.
[Single-file bundles](reference/histra-bundle-format.md) provide lossless compressed
study storage. Optional [C# SQLite output](reference/csharp-results-export.md)
preserves the native schema for supported captured static states; new Python solves
are not guaranteed to reproduce C# values bit for bit.

This page describes capabilities and remaining limits. Exact numerical and
performance claims belong to their dated benchmark reports.

Version 1.7.3 includes an opt-in, experimental
[cuDSS GPU sparse backend](guides/gpu-solving.md) and CPU/GPU comparison tools.
[CPU/GPU optimization measurements](benchmarks/cpu-gpu-fast-mode-2026-10-26.md)
cover automatic compiled CPU geometry, deterministic CUDA tests, and selected
bridge comparisons; GPU qualification remains limited to the recorded cases.
Element updates remain on the compiled CPU backend. GPU remains opt-in.

Version 1.7.3 also includes [CPU workflow improvements](guides/cpu-performance.md):
solver-only HRX loading, one compiled initialization per virgin static solve,
reused fibre face geometry, and bounded independent CPU processes.
The single-model resource runner also supports project-local threaded BLAS,
independent kernel/BLAS budgets, and saved `.histra` results.

## Supported boundary

| Area | Current boundary |
|---|---|
| HRX loading | Supported masonry geometry and analysis definitions, locked or unlocked |
| Preparation | Fresh four-node masonry Quad and fixed line-Restraint computational model; serialized C# state is reference-only |
| Quad contacts | Full-edge, collinear partial-edge and partition/T-junction overlaps |
| Static integration | LoadControl, ArcLength and ArcLengthLinear, with supported C# control procedures |
| Mechanics | Supported masonry diagonal/transverse laws and in-plane/out-of-plane sliding paths; capability preflight enforces the boundary |
| Chained analyses | In-memory HRX dependency execution through `AnalysisSession` |
| Interface material changes | Committed analysis boundaries, with the supported history-transfer policy |
| Production backend | Compiled Numba numerical execution with lifecycle coverage enforcement |
| Modal analysis | Supported Quad mass integration, Subspace/Inverse iterations, modal quantities and mode shapes |
| Reference databases | C# SQLite result reading and supported restart/projection schemas |
| Native results | Summary JSON, NPZ or optional HDF5 fields, independent Quad corner translations and stage-end spring snapshots |

See [supported features](reference/v1-supported-features.md) and the
[C# feature matrix](reference/v1-csharp-feature-matrix.md) for individual enum,
material and element restrictions.

## Safety and execution

- A solve freshly prepares HRX models requiring Python computational objects;
  direct low-level callers must honor the same preparation boundary.
- The high-level job API defaults to strict equilibrium checks. Direct session
  calls default to warning mode unless the caller requests `equilibrium_policy="error"`.
- Work or DispRotation convergence alone does not prove physical equilibrium.
  See [convergence safety](nonlinear_convergence_safety.md).
- The strategy advisor reports guidance without changing analysis definitions.
  A recommendation needs model-specific response and equilibrium evidence.
- One solve runs per Python process. Cancellation is cooperative and cannot
  interrupt an individual native linear-system call.
- The first run can include Numba compilation; cold and warm timings differ.

## Numerical evidence

Evidence is tied to recorded inputs, source revisions, backends and checked
fields. Current reference families include:

- [Dhir full static chain](benchmarks/dhir-full-chain-native-parity-progress.md)
  and [horizontal out-of-plane chain](benchmarks/dhir-horizontal-native-parity.md).
- [Dhir modal reference](benchmarks/dhir-modal-native-parity.md) and
  [Ersino modal reference](benchmarks/ersino-modal-analysis.md).
- [Masonry wall static/reversal reference](benchmarks/masonry-wall-native-parity-2026-10-15.md)
  and [material/modal GUI reference](benchmarks/material-modal-gui-2026-10-17.md).
- [Source-audit corrections and remaining validation](audit/csharp_python_function_mapping_matrix.md),
  [masonry source audit](benchmarks/masonry-source-audit-2026-10-14.md), and
  [precision-boundary audit](benchmarks/masonry-precision-audit-2026-10-16.md).

[Snapshot reuse measurements](benchmarks/newton-snapshot-reuse-performance.md)
and [linear-library experiments](benchmarks/faster-linear-library-screen-2026-10-15.md)
are configuration-specific performance evidence. They do not replace exact
native routine regressions.

## Open limitations

- Unsupported structural domains such as Frame, Solid, Vertex and fiber systems,
  nonlinear dynamics and response-spectrum solving fail explicitly.
- The Python preprocessor implements the supported masonry subset, not every
  feature of the desktop application's preprocessor.
- Material changes inside an active load step are unsupported.
- Complete strict physical-path qualification is not implied by authored C# row
  parity. The [Article gate](benchmarks/article-models-release-gate.md) and
  [strategy methodology](benchmarks/solver-strategy-methodology.md) specify the
  necessary response, equilibrium and phase checks.
- Some C# databases omit fields required for independent validation or restart
  from every terminal state. Successful return-stage evidence is unavailable in
  some material-change reference models.
- Schema 1 exports affected by the old unit/force bugs require re-export.
  Stage-end spring arrays are snapshots, not per-step spring histories.
- Python 3.12–3.14 is the declared package range. CI targets that Linux matrix;
  platform evidence in older reports must not be read as a fresh run for every release.
- `python -m histra` inspects/assembles a model. Use
  `python -m histra.tools.run_vert_live` for the standalone nonlinear workflow.

For behavior, consult the implementation and tests; for usage, consult the
[maintained guides](README.md). Historical release plans and superseded audit
snapshots are preserved under `archive/`.
