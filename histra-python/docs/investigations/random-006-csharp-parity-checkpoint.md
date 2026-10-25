# random_006 C# / Python Vert parity checkpoint

## Scope

This checkpoint concerns the sixth job in `temp-six-jobs`.  The directory is
named `random_006`, but its model file is `random_005_copy_1.hrx`.  That HRX was
prepared and mutated by C#, contains 6,786 interfaces and 17,640 active DOFs,
and has all 120 pier-restraint interfaces already assigned to material 146
(`Soil`).  Running this file directly avoids mixing preprocessing differences
with nonlinear-solver differences.

The reference phase is the five-step `Vert` analysis only.  No scour material
mutation is applied in this comparison.

## ModelPoint and control-node check

`Vert` has:

- `IntegrationMethod = LoadControl`;
- `MasterPoint = 1`;
- direction `(0, 0, -1)`;
- `ModelPoint 1 = Quad 61, vertex 2`.

ModelPoint 1 is a specific model point, not a global node.  The preparation log
also added ModelPoints 8--28, each referring to a specific Node (for example,
ModelPoint 8 refers to Node 1035).

Neither set controls the Vert equilibrium equations.  In the original C#
source, `GetDofForMaxDisplacement` returns `-1` whenever `MasterPoint != -10`.
`LoadControl.NewStep` receives that value but does not use it.  The master point
is subsequently read by `GetValueGraphAnalysis` for graph/output displacement.
Both solvers solve the complete 17,640-DOF global system, and the `Work`
criterion uses the complete global correction and residual vectors.

## Exact-prepared global comparison

Using native UMFPACK 5.7.9 with strategy 3 (`Symmetric`), Python produces:

| Step | Python R2 (kN) | C# R2 (kN) | Python iterations |
|---:|---:|---:|---:|
| 1 | -1.426333256e-7 | -1.427270035e-7 | 2 |
| 2 | +0.0302919525 | +0.0900118605 | 27 |
| 3 | -10.554340642 | +4.111492960 | 23 |
| 4 | -5.414295222 | -17.636469472 | 10 |
| 5 | -20.023178473 | -6.923913916 | 14 |

The final maximum absolute global displacement difference is
`4.218189650835323e-4` at zero-based DOF 13,643.  Vertical reaction R3 remains
essentially coincident.

## First divergent committed step

The complete spring population was compared at every committed step using the
stable identity `(ParentType, ParentKey, SpringPurpose, IdLocal)`.

At step 1:

- all 572,544 spring identities agree;
- spring phase mismatches: 0;
- maximum spring-displacement difference: `3.1575e-13`;
- RMS spring-displacement difference: `6.4528e-15`;
- maximum spring-force difference: `2.8439e-9`;
- maximum interface-local-displacement difference: `1.5717e-13`.

At step 2:

- spring phase mismatches: 13,204;
- maximum spring-displacement difference: `5.4203e-4`;
- RMS spring-displacement difference: `4.6548e-5`;
- maximum spring-force difference: `9.6306e-2`;
- maximum interface-local-displacement difference: `6.4805e-4`.

The equilibrium branch therefore separates inside the Newton/Regula-Falsi
iterations of Vert step 2.  It is not a gradual final-step reporting error.

## Which springs first differ

The 13,204 step-2 phase mismatches are:

| Parent type | Purpose | Meaning | Count |
|---:|---:|---|---:|
| 102 | 1 | ordinary Interface transverse springs | 13,126 |
| 106 | 30 | Quad diagonal springs | 78 |

There are no purpose-11 or purpose-21 phase mismatches at this first divergent
commit.  In particular, the Soil out-of-plane shared-spring path does not
initiate this remaining branch split.

The largest phase-discrepant displacements occur on ordinary Quad--Quad
interface 4956 and neighboring interfaces.  Interface 4956 is between Quads
1752 and 1786, has material 0, and is centered approximately at
`(x=162.8, y=-126, z=55.5)`.  It is not a pier-restraint Soil interface.

## C# call-sequence corrections tested

Two additional literal C# call-sequence differences were corrected:

1. UMFPACK symbolic factorization now receives the zero-valued `Ax` array,
   because C# calls it after mapping the sparse mask but before assembling K.
2. After initial tangent assembly, Python now performs the C# lability-check
   solve with `B[0] = 1` and then clears the displacement vector before the
   physical solve.

Both changes are valid compatibility improvements, but neither changes any
step, iteration count, reaction, or displacement in this random_006 run.

The following focused tests pass after the changes:

```text
31 passed
```

## Hypotheses excluded by controlled runs

- wrong Vert control ModelPoint or node;
- applying Soil to the wrong number of pier interfaces;
- the corrected shared out-of-plane Soil spring identity;
- merely switching from SuperLU to UMFPACK;
- UMFPACK 6 versus the archived UMFPACK 5.7.9 Linux library;
- zero-valued versus populated `Ax` during symbolic factorization;
- omission of the C# initial `B[0] = 1` lability-check solve;
- skipping the full C# Regula-Falsi endpoint-update sequence;
- NumPy/BLAS dot-product reduction order in the Work and line-search products;
- final reaction post-processing as the source of R2.

## Remaining proof boundary

The current evidence narrows the first causative difference to the numerical
trajectory at the start of step 2: the assembled residual/initial stiffness
and native sparse solve produce an extremely small perturbation after an
effectively identical step-1 state, and Regula-Falsi amplifies it into a
different transverse-spring branch before step 2 commits.

It is not yet proven whether the final last-bit difference is in an assembled
K/P entry or in the deployed Windows `libumfpack` binary.  The source archive
contains the P/Invoke declaration (`DllImport("libumfpack")`) but does not
contain or identify the native DLL version/build.  Linux UMFPACK 5.7.9 and 6.x
produce the same Python branch for this model.

To close that boundary without guessing, the next comparison needs one of:

1. the exact `libumfpack.dll` and its dependent native libraries from the C#
   solver deployment; or
2. a C# step-2 Newton trace containing K (`Ap`, `Ai`, `Ax`), B, solved X,
   `s0`, `s1`, every Regula-Falsi eta, and the resulting residual.

Changing tolerances, adding an arbitrary lateral perturbation, or forcing the
known C# final R2 would hide the branch sensitivity and is not an acceptable
parity fix.
