# Compiled resultant geometry, 2026-10-26

The CPU runtime now computes cached transverse-spring moment arms in a compiled
Numba kernel. This removes a Python geometry bottleneck automatically, without
new solver options or changes to constitutive laws and convergence controls.

The kernel preserves every C# float32 cast boundary and the four-corner
accumulation order. No fastmath or reduction reassociation is enabled. The
original scalar postprocessing helper remains available as an independent
differential oracle. Geometry is packed once per runtime and cached for the
resultant/moment calculations, retaining the existing lifecycle behavior.

## Measurements

On an Intel Core i7-13650HX laptop, the complete geometry calculation for 27,372
Article Bridge 1 fibres falls from median 1.786 s to 0.00577 s, including geometry
packing and output allocation. All float32 output bits match. This is about
310x for that operation, not for the complete analysis.

Three-sample before/after SuperLU gravity screens on the same host measured:

| Model | Solve before / after | Load + prepare + solve before / after |
|---|---|---|
| Benchmark 1, 48 Quads, 20 steps | 0.772 / 0.210 s | 1.276 / 0.715 s |
| Article Bridge 1, 914 Quads, 5 steps | 3.504 / 1.707 s | 10.668 / 8.888 s |

Total measured time decreases by approximately 44% and 17%, respectively.
Measurements exclude worker startup, explicit warmup and diagnostic snapshot
capture. They are sequential same-host screens, not simultaneous paired tests
or cold process-launch latencies.

The original larger model still fails its independent equilibrium audit under
`Work`. This output-geometry optimization does not change that behavior or
qualify the model's physical equilibrium.

## Validation and provenance

Differential tests compare the compiled and scalar paths bit-for-bit on randomized
distorted interfaces and a freshly prepared model. Existing native C# reaction,
interface resultant and bending-moment comparisons remain exact. The optional
warmup helper also compiles this kernel before subsequent analyses.

[Compact CPU evidence](../../release-evidence/performance/2026-10-26-compiled-resultant-geometry.json)
records input hashes, timings, package versions and CPU-source hashes at
aggregation. Measurements used the uncommitted working tree based on
`40596c23c3d6d777a3a53d2fae9d5ea16858d9f9`; individual launch source snapshots
were not archived. Raw reports remain under ignored
`benchmark_outputs/gpu-2026-10-26/`. These are working-tree performance
measurements rather than final package certification.
