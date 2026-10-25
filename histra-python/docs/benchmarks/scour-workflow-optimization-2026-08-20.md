# Scour workflow performance pass — 2026-08-20

## Scope and acceptance rule

This pass profiled the complete `random_005` workflow:

1. load the raw HRX;
2. prepare interfaces and springs;
3. run `Vert`;
4. change 12 upstream interfaces to `Soil_removed`;
5. run `scour_1`;
6. change the 24-interface upstream set;
7. run `scour_2`.

The acceptance rule was exact numerical/engineering compatibility first. No
equation, material law, convergence test, tolerance, load step, reduction
order, or line-search decision was changed.

## Test baseline

Before this pass, the complete repository suite reported:

```text
329 passed, 4 skipped in 32.31 s
```

After the retained changes and their new regression tests:

```text
334 passed, 4 skipped in 64.64 s
334 passed, 4 skipped in 24.75 s (final warmed verification)
339 passed, 4 skipped in 83.16 s (follow-up Vert optimization pass)
```

The first elapsed pytest time includes Numba compilation/cache effects. Test
suite times are not used as application benchmarks.

## Supplied profile

The supplied Windows profile at `profiles/20260819-185703` was produced from
commit `c311eb4`. Its main stage measurements were:

| Stage | Wall time | RSS before | RSS after | Peak RSS |
|---|---:|---:|---:|---:|
| Load | 0.355 s | 82.4 MB | 108.6 MB | 108.6 MB |
| Prepare | 62.964 s | 108.7 MB | 1392.5 MB | 1392.5 MB |
| Vert | 106.546 s | 1404.3 MB | 2378.9 MB | 2692.1 MB |
| Change 0.2 | 0.352 s | 2381.0 MB | 2381.9 MB | 2386.4 MB |
| Scour 1 | 6.376 s | 2381.9 MB | 2389.8 MB | 2735.5 MB |
| Change 0.4 | 0.441 s | 2389.8 MB | 2389.9 MB | 2389.9 MB |
| Scour 2 | 6.476 s | 2389.9 MB | 2391.1 MB | 2708.8 MB |

That profile included substantial first-use Numba compilation. Several
performance commits landed after it, so a new baseline was required.

## Current baseline

The same workflow was run under Linux/WSL with Python 3.12, NumPy, SciPy,
Numba, and process RSS sampling through psutil. A cProfile run was followed by
a timing-only run so JIT compilation did not dominate the clean timing.

The timing-only baseline was:

| Stage | Wall time | RSS before | RSS after | Peak RSS |
|---|---:|---:|---:|---:|
| Load | 0.281 s | 109.7 MB | 136.1 MB | 136.1 MB |
| Prepare | 18.772 s | 136.1 MB | 1354.0 MB | 1354.0 MB |
| Resolve scour interfaces | 0.628 s | 1354.0 MB | 1354.0 MB | 1354.1 MB |
| Vert | 10.803 s | 1354.0 MB | 2109.1 MB | 2150.9 MB |
| Change 0.2 | 0.155 s | 2109.1 MB | 2102.2 MB | 2110.1 MB |
| Scour 1 | 3.797 s | 2102.2 MB | 2102.4 MB | 2455.0 MB |
| Change 0.4 | 0.183 s | 2102.4 MB | 2112.9 MB | 2112.9 MB |
| Scour 2 | 3.798 s | 2112.9 MB | 2113.5 MB | 2451.6 MB |
| **Total** | **38.417 s** | | | **2455.0 MB** |

The 0.628 s interface-resolution measurement is a sampling/startup outlier;
other identical runs measured approximately 0.004 s.

## Measured bottlenecks

The updated profile identified:

| Operation | Calls | Cumulative/self evidence |
|---|---:|---:|
| Interface spring creation | 6,786 | 21.27 s cumulative in profiled cold run |
| Combined hysteretic batch creation | 6,650 | 8.20 s cumulative, 3.34 s self |
| Float32 inverse/warping afference path | 10,104 | 3.32 s cumulative, 1.82 s inverse self |
| Full dense state synchronization to objects | 3 | 4.87 s cumulative, 4.55 s self |
| Sparse SuperLU factorization | 3 | 3.90 s |
| Element tangent computation | 3 | 3.36 s |
| Cached global stiffness scatter | 3 | 0.318 s |

The stiffness scatter topology is already precomputed. The remaining global
assembly cost is dominated by element block recomputation and sparse numeric
factorization, not rebuilding COO/CSC topology.

Deep `update_domain` instrumentation measured 144 Vert calls and 1.572 s total.
The largest measured constitutive subphase was transverse-force reduction at
about 0.411 s estimated stage total. This showed that another constitutive-law
rewrite was not the highest-value next change.

## Retained optimization 1: compiled exact float32 inverse mapping

The Python Newton loop used to recover intrinsic Quad coordinates was moved to
a Numba kernel. Every multiply, subtraction, division, float32 conversion, and
left-associated bilinear reduction remains explicit and `fastmath` is not used.
The Python implementation remains available as the authoritative fallback and
test oracle.

A focused 10,104-call benchmark measured:

```text
Python reference: 1.107278 s
Numba kernel:     0.012473 s
Speedup:          88.77x
Bit mismatches:   0
```

The regression test exercises all three dropped-coordinate orientations and
compares the two returned float32 values by their exact uint32 bit patterns.

Preparation improved from 18.772 s to 15.769 s in the first post-change full
workflow run, a 3.003 s (16.0%) reduction. A later warm repeat measured
15.420 s, a 3.352 s (17.9%) reduction from baseline.

## Retained optimization 2: selective initial-stiffness refresh

Every static analysis starts by asking for the `alfa=0` element stiffness.
Before this pass, the solver recomputed all Quad and all 6,786 interface blocks
after each material change, even though scour rebuilt only 12 or 24 interfaces.

The solver now reuses existing initial-stiffness element blocks when:

- the Quad/interface topology identity and counts are unchanged;
- the last element stiffness state was also `alfa=0`; and
- an interface was not explicitly marked dirty by spring rebuilding.

Material rebuilding records the exact affected interface keys. A nonzero-alfa
tangent evaluation invalidates reuse and forces a complete refresh on the next
initial-stiffness request. Global sparse scattering is still executed in the
same precomputed C# accumulation order.

Two post-change runs measured scour stages of:

```text
scour_1: 3.469 s, 3.607 s  (baseline 3.797 s)
scour_2: 3.515 s, 3.704 s  (baseline 3.798 s)
```

The conservative repeated-run comparison is approximately 5.0% faster for
`scour_1` and 2.5% faster for `scour_2`.

Tests cover repeated reuse, selective dirty-interface refresh, full refresh
after nonzero alfa, and exact equality of the assembled global stiffness
matrix before and after selective refresh.

## Rejected candidate

A compiled batch calculation of virgin hysteretic envelope fields was tested.
Its values matched the scalar initializer exactly, but the additional object
constructor keyword work made the same 40,500-spring microbenchmark slower:

```text
compiled-envelope construction: 0.275606 s
scalar initialization:          0.234229 s
```

The candidate was fully reverted.

## Retained optimization 3: exact antisymmetric transverse-force reduction

A follow-up investigation targeted
`HystereticBatchRuntime.update_domain`. The original cold cProfile attributed
34.273 s to this method over the five-step `Vert` analysis, but that cumulative
time included first-use Numba compilation. With the compiled cache warm, the
same cProfile reports:

```text
144 update_domain calls: 1.120 s total
mean per call:           7.78 ms
share of profiled Vert:  9.2%
```

The deep profiler was also corrected to time the fused simple transverse
target/constitutive kernel explicitly. Previously that kernel was omitted from
the phase list and incorrectly appeared inside the residual "Python dispatch"
bucket.

The largest safe arithmetic opportunity was the transverse-force reduction.
For unconstrained Quad/Quad interfaces, local components 0, 1 and 5 are exact
antisymmetric counterparts of components 3, 2 and 4. The implementation now
performs each spring-ordered reduction once and mirrors the final result.
Restraint-interface arithmetic is unchanged. Positive-zero handling is
explicit so the original independently seeded accumulators remain bit exact.

An A/B benchmark using the prepared `random_005` runtime measured 6,786
interfaces, 549,666 transverse springs and 136 constrained interfaces:

```text
original reduction median: 5.763508 ms
optimized reduction median: 4.632517 ms
kernel improvement:         19.6%
```

The local-force, normal-increment, committed-force and maximum-displacement
arrays had zero uint64 bit-pattern mismatches. The complete repository suite
after this change reported `334 passed, 4 skipped`.

## Final timing and RSS

The second warmed final run was:

| Stage | Baseline | Final | Difference |
|---|---:|---:|---:|
| Load | 0.281 s | 0.281 s | 0.000 s |
| Prepare | 18.772 s | 15.420 s | **-3.352 s (-17.9%)** |
| Vert | 10.803 s | 10.122 s | -0.681 s (run variance; solver unchanged) |
| Change 0.2 | 0.155 s | 0.823 s | GC/sampling outlier |
| Scour 1 | 3.797 s | 3.607 s | **-0.190 s (-5.0%)** |
| Change 0.4 | 0.183 s | 0.128 s | -0.055 s |
| Scour 2 | 3.798 s | 3.704 s | **-0.094 s (-2.5%)** |
| **Total** | **38.417 s** | **34.090 s** | **-4.327 s (-11.3%)** |
| **Peak RSS** | **2455.0 MB** | **2444.2 MB** | **-10.8 MB (-0.4%)** |

Total runtime is sensitive to OS scheduling, garbage collection, and native
thread-pool activity. The preparation improvement and selective stiffness
work are directly attributable and repeatable; the Vert difference is not
claimed as an optimization result.

## RAM investigation

Direct RSS and runtime-array accounting found:

```text
RSS after load:                 133.6 MB
RSS after preparation:        1403.1 MB
RSS after dense runtime:      1771.5 MB
Unique runtime NumPy arrays:   210.4 MB
```

The largest dense runtime arrays are:

| Array | Size |
|---|---:|
| Compact transverse parameters `(549666, 20)` | 83.87 MB |
| Trial state `(549666, 10)` | 41.94 MB |
| Committed state `(549666, 9)` | 37.74 MB |
| Coulomb state `(20358, 32)` | 4.97 MB |
| Targets | 4.19 MB |
| Transverse stiffness | 4.19 MB |
| Each geometry vector (`di`, `dj`, `ecc`, inverse length) | 4.19 MB |

The 549,666 compatibility spring objects dominate prepared-model memory. A
sample `SpringHysteretic` has a 648-byte shallow object plus 504 bytes of list
headers across its seven two-value lists, before accounting for referenced
objects. Removing or sharing these mutable compatibility objects would change
observable object semantics and was not attempted.

The approximately 330–350 MB peak increase during each scour solve coincides
with sparse numeric factorization/native solver temporaries. The retained
changes do not materially alter peak RAM.

## Follow-up Vert optimization pass

A later Windows timing run with 14 Numba threads measured `Vert` at 30.197 s.
Its cProfile predecessor attributed 16.993 s across 2,441 calls to
`HystereticBatchRuntime.update_domain`, so the follow-up pass targeted only
the measured dense-domain kernels. No nonlinear iteration, line-search trial,
constitutive equation, tolerance, or reduction order was changed.

The retained changes are:

1. The linear/simple transverse target calculation, spring state update and
   per-interface force reduction now execute in one per-interface Numba pass.
   Kinematic values that are constant for an interface are loaded once. Each
   spring is still evaluated in increasing index order and every interface
   force component retains its former accumulation order.
2. Linear tensile batches omit the all-zero tensile-law discriminator column.
   This changes physical parameter storage from 21 to 20 float64 columns,
   saves 4.4 MB for this model and aligns each row to 160 bytes. Exponential
   batches retain the discriminator and use the existing typed kernel.
3. Independent initial-Coulomb rows and per-interface full-force rows execute
   in parallel. Shared Soil restraint spring identity remains encoded in the
   dense indices; no shared state is duplicated.
4. Immutable local-force afferences are inverted once into a per-global-DOF
   topology. Each DOF is reduced independently, but its contribution list is
   constructed in the exact former Interface-then-Quad encounter order.
5. Interface global-to-local mapping and kinematic preparation are fused so
   each interface's 12 local increments remain cache-local. The afference sum
   within each local DOF is unchanged.

Model-scale isolated measurements were:

| Kernel | Before | After | Improvement |
|---|---:|---:|---:|
| Transverse update plus force reduction | 9.182 ms | 5.656 ms | 38.4% |
| Initial Coulomb constitutive update | 0.175 ms | 0.040 ms | 4.3x |
| Full interface force assembly | 0.170 ms | 0.017 ms | 10.2x |
| Ordered global resisting-force scatter | 0.551 ms | 0.038 ms | 14.5x |
| Interface mapping plus kinematics | 0.531 ms | 0.067 ms | 8.0x synthetic |

The final deep profile measured 549,666 transverse springs, 6,786 interfaces,
20,358 Coulomb springs and 2,520 Quads. Steady Vert `update_domain` time was:

```text
before follow-up: 8.545 ms/call
after follow-up:  6.886 ms/call
reduction:         19.4%
```

The final uninstrumented 14-thread WSL run measured:

```text
Vert before follow-up: 9.636 s
Vert after follow-up:  8.503 s
improvement:           1.133 s (11.8%)
total staged time:    34.199 s -> 31.213 s (8.7%)
```

An 8-thread run measured 8.752 s for Vert while using 20.85 CPU-seconds,
versus 30.84 CPU-seconds with 14 threads. On this host, 14 threads remains the
minimum-wall-time setting; 8 threads is the more CPU-efficient setting.

Every new path has a uint64/uint32 bit-pattern oracle covering spring trial
state, local forces, global forces, normal increments, committed forces,
maximum displacements, invalid DOFs, disabled/ruptured springs, constrained
interfaces, and exponential fallback. The complete suite reports `339 passed,
4 skipped`.

The native Windows acceptance was subsequently run twice with 14 Numba
threads, one BLAS thread, NumPy 2.5.2, SciPy 1.18.0 and Numba 0.67.0. The
second run is used as the warm comparison:

| Stage | Previous Windows 14-thread | Updated first run | Updated warm run | Warm change |
|---|---:|---:|---:|---:|
| Prepare model | 17.291 s | 15.583 s | 13.283 s | -23.2% |
| Vert | 30.197 s | 25.680 s | 21.888 s | -27.5% |
| Change materials 0.2 | 0.755 s | 1.067 s | 0.755 s | -0.1% |
| Scour 1 | 3.124 s | 4.337 s | 3.155 s | +1.0% |
| Change materials 0.4 | 0.100 s | 0.195 s | 0.104 s | +4.5% |
| Scour 2 | 3.169 s | 4.029 s | 3.164 s | -0.2% |
| All measured stages | 54.805 s | 51.058 s | 42.528 s | -22.4% |

For Vert, process CPU time fell from 342.75 to 237.05 CPU-seconds (-30.8%)
and peak RSS fell from 2139.0 to 2080.6 MiB (-58.3 MiB). The maximum peak
over the entire warm workflow was 2401.1 MiB during `scour_1`, 46.3 MiB above
the previous 2354.8 MiB maximum. That small workflow-peak increase occurs in
native sparse-factorization temporaries, not in the optimized Vert batch
arrays, and varies between runs: the two updated scour peaks were 2401.1 and
2392.9 MiB.

The native result validates a substantial speedup but does not yet meet the
sub-20-second Vert target: the best Windows measurement is 21.888 s. The
3.79-second difference between the two updated Windows Vert runs also shows
that a single timing is insufficient for small follow-up decisions. Any next
optimization should start with a fresh detailed Windows profile of the updated
code and repeated timing runs; the pre-change cProfile proportions are now
obsolete.

## Remaining measured opportunities

1. Reduce the 7.5 s combined-spring object construction cost without changing
   independent mutable spring/list semantics. The first batch-envelope attempt
   did not pass the performance gate.
2. Investigate the 5.8 s interface-contact generation path, especially convex
   clipping, with exact polygon/order regression fixtures before compiling it.
3. Investigate an API-compatible way to avoid the 4.55 s full dense-to-object
   synchronization after every chained analysis. Direct public access to
   spring state currently makes this synchronization observable.
4. Compare Windows UMFPACK and SciPy SuperLU numeric-factorization RSS and time
   using the same CSC matrix. Any solver change must first reproduce the
   established C# nonlinear branch.
5. Do not prioritize sparse topology reconstruction: it is already cached and
   measured at only 0.318 s across three assemblies in the profiled workflow.
