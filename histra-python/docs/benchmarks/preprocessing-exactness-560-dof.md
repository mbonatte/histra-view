# Exact C# preprocessing alignment report

## Outcome

The C# preprocessing rules that controlled the alternate nonlinear branch have
been ported exactly for the supplied masonry Quad/Interface topology. The
Python-regenerated model now follows the same 38-step Live Load trajectory as
the HiStrA software-generated computational model. Before these corrections,
the same unlocked model followed a different 93-step trajectory.

No article or PhD supplementary material was required for these corrections:
the decisive rules were explicit in the supplied C# source.

## Measured before and after

| Metric | Earlier Python preprocessing | Corrected preprocessing |
|---|---:|---:|
| Live Load committed trajectory | 93 steps | **38 steps** |
| Step 1 relative displacement error vs C# | `2.7445e-1` | **`1.0889e-4`** |
| Step 38 relative displacement error vs C# | `4.8079e-1` | **`1.2450e-4`** |
| Maximum relative error over C# steps 1–38 | `7.9997e-1` | **`2.7018e-4`** |
| Maximum absolute DOF difference | `1.00064` | **`2.41998e-4`** |
| Maximum reaction-component difference | `59.2599` | **`0.0316010`** |

The complete regenerated-model benchmark committed all 38 C# reference steps.
Its Live Load iteration sequence also matches the locked-model Python reference,
including 208 iterations at step 1, 382 at step 2, 409 at step 21, and 482 at
step 38.

The five-step Vert predecessor is now especially close:

- exact step order and iteration counts: `[5, 10, 7, 23, 2]`;
- relative displacement error: `5.0223e-7`;
- maximum absolute DOF difference: `2.6214e-8`.

## Source-level differences corrected

### 1. Quad diagonal friction geometry

**C# reference:** `Objects/Quad.cs`, property `cosAlfa` around line 1022.

C# uses a law-of-cosines expression based on `Length[0]`, `Length[1]`, and
`Diago[0]`. The previous Python formula used `Length[0] / Diago[1]`. For
several distorted Quads, C# produces a negative value while Python produced a
positive value. That reversed the normal-force/friction coupling of their
diagonal Coulomb springs.

Python now ports the C# expression literally in `Quad.cos_alfa`.

### 2. Quad nonlinear diagonal yield search

**C# reference:** `Objects/Quad.cs`, `SetNonLinearProperties` around line 4206.

The prior Python implementation simplified the two-direction 100×100 principal
stress search into a symmetric calculation. C# instead:

- evaluates both opposite unit diagonal deformations;
- retains extrema cumulatively between the two passes;
- uses a negative fourth warping term in this method, despite a different sign
  in another projection path;
- returns independently scaled positive and negative diagonal limits.

Python now preserves those source-level details for compatibility. The sign
asymmetry is documented as an observable C# quirk rather than silently
“corrected.”

### 3. Diagonal orthotropy and ElastoPlastic strength selection

**C# reference:** `Objects/Quad.cs` around lines 2242–2276 and the relevant
`ConstitutiveLaw*.PropOrthotropyParameter` methods.

Python now reproduces the diagonal orthotropic combination. When the vertical
flexural law is `ElastoPlastic`, C# uses the vertical compressive strength for
the diagonal search. Other material paths retain the cohesion-derived cap.
The ElastoPlastic tensile ultimate-strain asymmetry in the supplied source is
also preserved.

### 4. `System.Single` material semantics

The C# `MasonryMaterial` numerical fields are `float`. XML values are therefore
rounded to single precision before constitutive constructors consume them as
doubles. Python previously retained the decimal as binary64. The difference was
only around `1e-8` in some capacities, but that was sufficient to select a
different zero-capacity sliding phase.

Material values in preprocessing are now rounded through `numpy.float32` before
promotion to Python `float`.

### 5. In-plane Coulomb spring combination

**C# reference:**
`ModelManagement.ComputationalElementsOperations/SpringOperations.cs`,
`CombinationSpring(SpringCoulomb03, SpringCoulomb03, bool)` around line 805.

This was the final branch-controlling defect. C# combines the temporary
springs' actual computed hardening modulus `H`. Python used
`K * PlasticStiffnessRatio`. In this constructor path the material hardening
ratio can be zero while the serialized property remains at the class default
`1e-4`. Python therefore invented a softening branch that C# never created.

Using `sp1.h` and `sp2.h` restores the same committed Vert phase for the 12
interface sliders that controlled Live Load step 2.

## Remaining numerical difference

The corrected regenerated model and the C#-locked model follow effectively the
same Python trajectory: their first 20 Live Load displacement vectors differ by
less than approximately `8.43e-7` relative. Both Python paths retain the same
small discrepancy against the C# SQLite result:

- maximum relative displacement error: `2.7018e-4` at step 5;
- maximum absolute DOF difference: `2.41998e-4` at step 38;
- maximum reaction-component difference: `0.0316010` at step 23.

Therefore, the large raw-preprocessing divergence is resolved. The remaining
error is in solver/source-binary numerical compatibility rather than
`PrepareModel`. Full `<=1e-4` equivalence for every Live Load step is not yet
claimed.

## Model-data note

The first uploaded unlocked `new_model.hrx` omits the row-1 coefficient for load
condition 11 in custom combination 15. It can run Vert after preprocessing but
cannot independently run `LiveLoad_1` until that coefficient is added. The
later software-run archive contains the corrected combination and was used as
the C# numerical reference.

## Verification

```text
compileall: PASS
import: PASS
140 passed, 2 skipped, 0 failed
```

Focused regressions now cover the distorted-Quad `cosAlfa` value, literal
diagonal yield search, regenerated diagonal envelopes, and use of actual
Coulomb hardening modulus during two-sided spring combination.
