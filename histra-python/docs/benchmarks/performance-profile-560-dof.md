# HiStrA Python Performance Profile — 560-DOF Benchmark

## Scope

This profile uses the corrected 560-DOF masonry model and preserves the C#-compatible nonlinear path:

- 80 Quads
- 135 interfaces
- 10,935 transverse hysteretic springs
- 135 in-plane Coulomb springs
- 270 out-of-plane Coulomb springs
- 5 committed Vert steps
- 38 committed Live Load ArcLength steps
- 15,116 Live Load Newton/ArcLength corrections
- attempted step 39 stops at the configured maximum-displacement limit

The SQLite database stores committed states but does not store nonlinear iteration counts. Therefore, the Python iteration sequence cannot be asserted to equal the internal sequence of the installed C# binary solely from the database.

## Before and after

The prior exact-preprocessing release measured:

| Phase | Previous release |
|---|---:|
| PrepareModel | 20.6779 s |
| Vert | 2.1544 s |
| Live Load | 70.2489 s |
| Total | 93.0812 s |

Three warm runs of the optimized release measured:

| Run | PrepareModel | Vert | Live Load | Total |
|---:|---:|---:|---:|---:|
| 1 | 1.1968 s | 0.5331 s | 4.5299 s | 6.2597 s |
| 2 | 1.1830 s | 0.5228 s | 4.4113 s | 6.1171 s |
| 3 | 1.1742 s | 0.5241 s | 4.3802 s | 6.0785 s |
| **Median** | **1.1830 s** | **0.5241 s** | **4.4113 s** | **6.1171 s** |

Overall warm improvement:

- **15.21× faster**
- **93.43% runtime reduction**
- PrepareModel: 17.48× faster
- Vert: 4.11× faster
- Live Load: 15.92× faster

A run with an empty Numba cache measured:

- PrepareModel: 4.8767 s
- Vert: 11.7946 s
- Live Load: 4.6717 s
- measured phases: 21.3431 s
- complete process wall time: 23.58 s

The first-run difference is Numba compilation. Subsequent processes load the compiled kernels from Numba's disk cache.

## Final Live Load profile

The final cProfile run covers the 38-step Live Load solve only. Profiling overhead increased elapsed time to 5.228 s.

| Hotspot | Cumulative/self time | Approx. share |
|---|---:|---:|
| Fused Numba domain update | 2.834 s | 54.2% |
| Sparse solves, including wrapper | 1.016 s | 19.4% |
| SuperLU triangular solves | 0.846 s | 16.2% |
| Initial tangent assembly | 0.233 s | 4.5% |
| Residual assembly | 0.120 s | 2.3% |
| Load application | 0.105 s | 2.0% |
| Reaction postprocessing | 0.078 s | 1.5% |
| Final object synchronization | 0.060 s | 1.1% |
| Snapshot capture | 0.018 s | 0.3% |

The solver now performs about 2.52 million Python calls under profiling. The dominant work is inside compiled machine code, not Python object dispatch.

## Final PrepareModel profile

The final profiled PrepareModel run took 1.725 s, including approximately 0.219 s loading/compiling Numba overloads in the new process. The largest remaining groups were:

| Hotspot | Cumulative time |
|---|---:|
| Create 135 interface spring groups | 1.381 s |
| Bilinear cell vertex calculations | 0.361 s |
| Configure hysteretic springs | 0.360 s |
| Combine hysteretic springs | 0.337 s |
| Generate 80 Quad nonlinear springs | 0.259 s |
| Quad nonlinear-property search | 0.243 s |

The previous 100×100 Python yield search and repeated 3-D fiber stiffness calculations are now compiled.

## Optimizations implemented

### Nonlinear solve

- One fused Numba domain-update boundary per correction.
- Dense batched state for 10,935 transverse hysteretic springs.
- Specialized zero-pinching/zero-damage hysteretic kernel for the generated masonry fibers.
- Dense batched state for all 405 interface Coulomb springs.
- Dense batched state for all 80 Quad diagonal Takeda/Coulomb springs.
- Compiled global-to-local displacement transformations.
- Compiled Quad normal-force aggregation.
- Compiled interface and Quad local-force generation.
- Compiled local-to-global resisting-force assembly.
- Cached global resisting vector reused by the residual calculation.
- Cached maximum element displacement.
- Dense elastic-energy calculation.
- Dense commit/revert snapshots for managed spring families.
- Deferred synchronization from dense arrays back to Python objects.
- Selective synchronization for reaction postprocessing.
- Reused sparse factorization for unchanged stiffness matrices.
- Reused the ArcLength reference-load displacement while K and the reference vector remain unchanged.

### Preprocessing

- Compiled batch fiber stiffness calculation.
- Compiled Quad 100×100 nonlinear yield search.
- Cached immutable geometry, norms, interface mappings, and areas.
- Replaced repeated general inversions with the required analytic 2×2 inverse.

## Experiments rejected

### Parallel Numba loops

`prange` was tested with multiple thread counts. It was slower because each nonlinear correction contains only about 10,935 independent fiber updates, while the analysis performs 15,116 sequential corrections. Thread-pool scheduling and synchronization occurred thousands of times and outweighed the parallel work.

### Updated tangent Newton

Changing the C#-compatibility method to an updated-tangent Newton method reduced some local costs but changed the ArcLength branch and exceeded the displacement limit during the first Live Load step. It is not a valid performance optimization when reference compatibility is required.

### Fast-math or float32

These were not enabled. The analysis is branch-sensitive, and small floating-point changes have previously altered constitutive phases and committed trajectories.

## Remaining bottleneck

The remaining dominant cost is the fused constitutive/kinematic update, at about 2.83 profiled seconds for 15,156 calls. Each call still evaluates the full trial state of more than 11,000 path-dependent springs. This is real nonlinear constitutive work rather than Python overhead.

The sparse solve is already only about 0.85 profiled seconds for the complete Live Load analysis. Replacing SuperLU would have limited overall impact unless the constitutive kernel is reduced further.

Potential future work, ordered by likely benefit and risk:

1. Interface-level elastic aggregation with an active nonlinear fiber set.
2. Native compiled extension using C++/Rust/Cython to remove Numba first-run compilation.
3. Profile-guided SIMD layout changes inside the fused constitutive kernel.
4. A separately validated fast solver mode using a different tangent/update strategy, explicitly not C#-compatibility mode.

## Reproduce the profile

Warm standalone timing:

```bash
python run_vert_live.py model.HRX --output-dir python-results --quiet
```

Live profile:

```bash
python -m cProfile -o live.prof \
  run_vert_live.py model.HRX --output-dir profile-results --quiet
python -m pstats live.prof
```

Force an empty Numba cache:

```bash
NUMBA_CACHE_DIR=/path/to/empty-cache \
python run_vert_live.py model.HRX --output-dir cold-results --quiet
```

Disable the compiled spring backend for diagnosis:

```bash
HISTRA_DISABLE_COMPILED_SPRINGS=1 \
python run_vert_live.py model.HRX --output-dir scalar-results --quiet
```
