# HiStrA Python — Second Performance Optimization Report

## Result

The corrected raw-HRX workflow now completes the 560-DOF benchmark in a median **6.117 seconds** after Numba caching:

- PrepareModel: 1.183 s
- Vert: 0.524 s
- Live Load: 4.411 s
- 38 committed Live Load steps
- 15,116 Live Load corrections
- expected configured displacement-limit stop at attempted step 39

The previous exact-preprocessing release required approximately **93.081 seconds** for the same three measured phases. This is a **15.21× speedup** and a **93.43% reduction**.

## Why the previous version was slow

The matrix is only 560×560 and its fixed sparse factorization was not the principal cost. The expensive work was repeated path-dependent element processing:

- more than 10,000 transverse spring objects updated individually;
- 405 interface Coulomb spring objects updated individually;
- 80 Quad Takeda springs updated individually;
- Python global/local transformation and force-assembly loops;
- repeated constitutive snapshots and object synchronization;
- Python preprocessing loops for fiber geometry and Quad yield search;
- repeated ArcLength reference solves despite unchanged stiffness.

## What changed

The complete supported masonry computational domain is now represented in dense numeric arrays during the nonlinear loop. A single fused Numba call performs interface kinematics, hysteretic and Coulomb updates, Quad normal-force coupling, local force generation, global resisting-force assembly, and maximum-displacement calculation.

Preprocessing now uses compiled fiber-property and Quad-yield kernels. Sparse factorizations and ArcLength reference solutions are cached while their inputs remain unchanged. Python objects remain the public model representation and are synchronized at defined boundaries rather than every correction.

## Profile after optimization

For a profiled 38-step Live Load run:

- fused compiled domain update: 2.834 s;
- sparse solve wrapper: 1.016 s;
- SuperLU solve itself: 0.846 s;
- all remaining Python orchestration and postprocessing: approximately 1.38 s combined.

The principal remaining bottleneck is now actual compiled constitutive work, not Python dispatch.

## First-run versus warm-run behavior

Numba compiles model kernels on first use. With an empty cache, measured phases totalled 21.343 s and complete wall time was 23.58 s. Later processes use the disk cache and complete in about 6.1 s.

This distinction is important when comparing against a precompiled C# executable. A fair steady-state comparison should either:

- run Python once to populate its Numba cache and time the second run; or
- include installation/AOT compilation time for both implementations.

The project does not bundle architecture-specific Numba cache binaries.

## Numerical regression

Performance changes preserve the corrected trajectory:

- locked-model first three Live Load displacement vectors are bit-for-bit identical to the pre-optimization reference;
- raw-preprocessed model retains the same 38-step iteration sequence;
- all values remain finite;
- C# terminal condition is reproduced;
- current C# comparison maximum relative displacement error: `2.69756e-4`;
- current maximum absolute DOF difference: `2.42192e-4`.

The remaining C# numerical difference predates these performance changes.

## C# timing caveat

The SQLite `.Results` database does not store nonlinear iteration counts or elapsed solve time. It is therefore not possible to prove from the database that the Python and installed C# binary perform the same number of corrections. A reliable cross-language comparison needs a timed C# run with:

- the same HRX;
- the same analysis/method settings;
- database writing either enabled for both or excluded from both;
- reported committed steps, corrections, and terminal condition.

## Verification

```text
compileall: PASS
import: PASS
140 passed
2 opt-in benchmarks skipped
0 failed
```
