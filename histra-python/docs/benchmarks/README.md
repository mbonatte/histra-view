# Benchmark evidence

Reports qualify their identified model, input, source revision, backend and
checked output fields. They are not general installation instructions or blanket
claims of parity for untested inputs.

| Workflow | Evidence |
|---|---|
| Full static chains | [Dhir](dhir-full-chain-native-parity-progress.md), [horizontal out-of-plane](dhir-horizontal-native-parity.md) |
| Modal analysis | [Dhir](dhir-modal-native-parity.md), [Ersino](ersino-modal-analysis.md) |
| Masonry/reversal behavior | [Native wall comparison](masonry-wall-native-parity-2026-10-15.md), [material/modal GUI reference](material-modal-gui-2026-10-17.md) |
| Native routine/source boundaries | [Masonry source audit](masonry-source-audit-2026-10-14.md), [precision audit](masonry-precision-audit-2026-10-16.md) |
| Model qualification | [Article models](article-models-release-gate.md), [solver strategy methodology](solver-strategy-methodology.md) |
| Preprocessing | [Partial-edge contacts](partial-edge-preprocessing.md), [exactness reference](preprocessing-exactness-560-dof.md) |
| Small-model output | [Live load](live-load-126-dof.md), [result database](results-database-126-dof.md) |
| Performance experiments | [Snapshot reuse](newton-snapshot-reuse-performance.md), [linear library screen](faster-linear-library-screen-2026-10-15.md), [RTX 4060 GPU screen](gpu-solving-2026-10-26.md), [CPU/GPU optimization](cpu-gpu-fast-mode-2026-10-26.md) |

[Compiled CPU resultant geometry](compiled-resultant-geometry-2026-10-26.md)
records the automatic, bit-exact geometry acceleration.
[CPU workflow improvements](cpu-workflow-2026-10-26.md) cover loading,
initialization, fibre preparation and independent process throughput.
[Large-model capacity](large-model-capacity-2026-10-26.md) records native BLAS
and GPU refactorization measurements on a 47,768-DOF system.

Other dated reports in this directory preserve earlier measurements. Retain their
original timing and numerical context. See [current status](../STATUS.md) for the
present supported boundary and [tools](../../tools/README.md) for command ownership.
