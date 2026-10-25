# `wall_6_rows_run` C# / Python benchmark and overturning diagnosis

## Scope

This benchmark uses:

- source model: `my_model/overturning_wall/wall_6_rows.hrx`;
- C# prepared model: `my_model/overturning_wall/wall_6_rows_run.hrx`;
- C# results: `my_model/overturning_wall/wall_6_rows_run.Results`;
- analyses: five-step `Vert`, five-step zero-multiplier `scour_1`, then
  displacement-controlled `LiveLoad_1`;
- scour: foundation restraint interfaces 849--884 changed from material 146
  (`Soil`) to 147 (`Soil_removed`). Interfaces 813--848 remain `Soil`.

The C# live analysis contains 224 committed steps. It was stopped while
attempting step 225.

## Python parity correction

The wall exposed two related compatibility defects.

First, Python ignored the masonry material switches `scorrhor`, `scorrvert`
and `scorrDir3` while generating interface sliding laws. It always created a
`SpringCoulomb03` from the `SlidingYieldingDomain*` fields. The C#
`ConstitutiveLawOperations` code instead creates a `ConstitutiveLawElastic`
when the applicable `scorr*` switch is false. Both material 146 (`Soil`) and
the final prepared wall require linear-elastic sliding links in this path.

Second, the accelerated interface runtime managed the transverse springs but
omitted ordinary linear-elastic in-plane and out-of-plane sliding forces on
the same interface. These forces were absent from the restored resisting-force
cache and subsequent domain updates.

Python now:

1. creates `SpringLinearElastic` or `SpringCoulomb03` according to the C#
   `scorr*` switch;
2. transfers the common committed spring state when a material stage changes
   a sliding link between the two spring families, as C# `SpringStateDBclass`
   does;
3. retains linear sliding contributions on otherwise batch-managed
   interfaces;
4. parses and restores the serialized C# `SpringLinearElastic` type;
5. constructs interface fibre geometry using the same single-precision
   `Vector3` boundary used by C#.

After the correction, all 216 foundation sliding entries (72 in-plane and
144 out-of-plane) have the same spring family as the C# prepared model.

## Numerical benchmark

### Authoritative same-state restart

The most discriminating solver comparison restores the final C# `scour_1`
committed state and runs `LiveLoad_1` in Python. This removes preprocessing
history from the comparison and tests the live solver from an identical
constitutive and displacement state.

Python committed all 224 C# steps. The maximum differences over the complete
run were as follows. The measured Python runtime for this 224-step restart
benchmark was 214.11 s with 14 Numba threads on the current machine.

| Quantity | Maximum absolute difference |
|---|---:|
| total reaction R1 | 7.45e-8 kN |
| total reaction R2 | 2.05e-8 kN |
| total reaction R3 | 3.82e-6 kN |
| model point 16 Ux | 2.51e-11 cm |
| model point 16 Uy | 1.19e-7 cm |
| model point 16 Uz | 5.96e-8 cm |

At live step 1, the entire 2352-DOF displacement vector had maximum absolute
error 4.9e-13 cm and norm-relative error 2.67e-11. This establishes that the
Python live solver follows the C# nonlinear path when it starts from the same
committed state.

Selected C#-matched live results are:

| Step | Load factor | Applied live load (kN) | R3 (kN) |
|---:|---:|---:|---:|
| 1 | 245.404999 | 107.978200 | -312.352361 |
| 2 | 283.059605 | 124.546226 | -337.779301 |
| 5 | 306.353168 | 134.795394 | -351.801118 |
| 20 | 323.842820 | 142.490841 | -363.309712 |
| 41 | 326.037509 | 143.456504 | -365.396764 |
| 45 | 325.572736 | 143.252004 | -366.326234 |
| 100 | about 323.725 | 142.439007 | -365.385030 |
| 224 | 312.889906 | 137.671559 | -362.208245 |

There are two line loads, each `22 cm * 0.01`, so the nominal reference load
is `0.44 kN` per unit load factor. The actual peak applied live load is
therefore **143.456504 kN at step 41**, not the increase in total support
reaction.

### From-raw workflow

Running the complete Python preparation and analysis chain gives:

| State | C# R3 (kN) | Python R3 (kN) | Difference (kN) |
|---|---:|---:|---:|
| `Vert`, step 5 | -110.798334837 | -110.798335254 | -4.17e-7 |
| `scour_1`, step 5 | -112.244969038 | -112.245212365 | -2.43e-4 |
| `LiveLoad_1`, step 1 | -312.352360964 | -312.352375984 | -1.50e-5 |

The first Python live load factor is 245.405019522, differing from C# by
2.06e-5. The remaining small from-raw drift originates in the zero-load scour
re-equilibration and accumulates on the path-sensitive arc-length branch. It
does not occur in the same-state solver benchmark above.

## Why the reported critical load is too high

### The contact really does become a pivot

The foundation is 288 cm wide. The six rows on the negative-Y side are
removed, leaving a supported width of 180 cm and a scour boundary at
`y = -36 cm`. During the live analysis the normal compression migrates to the
first supported row, whose centre is `y = -27 cm`; the other supported rows
lift off. By step 5 all meaningful compression is already confined to that
front row. The number of compressive fibres later reduces from 108 at step 45
to 54 at step 224.

This is the expected no-tension Soil contact mechanism. The wall is rocking
about the scour edge. The pivot observation is therefore correct, but it does
not validate the reported load magnitude.

### Static overturning check

The model's computed dead weight is:

`W = 110.798335 kN`

Its Y centroid is approximately zero. The live load is at `y = -144 cm`, so
the moment arms about the scour boundary are 36 cm for dead load and 108 cm
for live load. A rigid pivot equilibrium gives:

`Pcrit = W * 36 / 108 = 36.9328 kN`

This is consistent with the observed contact mechanism and far below both
143.46 kN and the reaction-derived value near 254 kN.

### The C# `Work` convergence test accepts a non-equilibrated state

`LiveLoad_1` uses the absolute Work criterion with tolerance 0.005. It tests

`0.5 * abs(delta_u dot residual) <= 0.005`

A small correction vector can satisfy this scalar work test even while the
force residual is large. At C# live step 1 the analysis commits after 22
iterations with:

- work error: 0.004716 (passes);
- generalized residual norm: 32.078 (not close to force equilibrium);
- applied live load: 107.978 kN;
- support R3: -312.352 kN.

The predecessor reaction magnitude is 112.245 kN. Dead plus applied live load
would therefore require about 220.223 kN of vertical support, not 312.352 kN.
The step contains roughly 92.13 kN of vertical imbalance.

At the nominal peak, step 41:

- applied live load: 143.4565 kN;
- expected support magnitude from predecessor plus live load: 255.7015 kN;
- reported support magnitude: 365.3968 kN;
- vertical imbalance: about 109.6953 kN.

The reaction increment reaches about 254.081 kN at step 45, but the actual
applied live load there is only 143.252 kN. Treating `abs(R3 - R3_baseline)` as
the live load converts the unbalanced residual into fictitious capacity.

### Force-equilibrated diagnostic

Keeping the model, springs, arc-length method and P-Delta settings unchanged,
but replacing only the convergence criterion with `ForceMoment` at tolerance
0.005 gives:

| Step | Applied live load (kN) |
|---:|---:|
| 1 | 29.5740 |
| 2 | 32.5177 |
| 3 | 33.6706 |
| 5 | 34.8738 |
| 8 | 35.6726 |
| 10 | 35.9353 |

The curve approaches the independent rigid-pivot estimate of 36.9328 kN.
P-Delta was retained in this diagnostic, so removing geometric nonlinearity is
not the explanation.

## Engineering conclusion

The support becoming a pivot is a real and appropriate result of the Soil
no-tension interface. The excessive critical load is caused by accepting an
unbalanced nonlinear solution with the absolute Work criterion, compounded
if support-reaction change is plotted as though it were the applied live load.

For engineering interpretation of this model:

1. compute applied live load as `load_factor * 0.44 kN`;
2. require a force/moment residual criterion (or, at minimum, independently
   verify force and moment equilibrium before accepting every committed step);
3. report the residual norm and vertical equilibrium error with the capacity
   curve;
4. retain the Soil no-tension contact unless a different physical support law
   is intentionally required.

## Implemented solver safeguard

The Python solver now audits global X/Y/Z force balance and the complete
active-DOF residual independently of the selected `.HRX` convergence
criterion, before every commit. Replaying the authoritative C# scour state
through real `LiveLoad_1` step 1 produced:

```text
Work error                  0.004716472593  (passes 0.005)
residual L2                32.078249043
expected R3             -220.223160651 kN
actual R3               -312.352360964 kN
R3 balance error          -92.129200313 kN
allowed force error         0.004123524 kN
equilibrium_ok              false
```

Warning mode retains this C#-matching state only for comparison and marks it
unsafe. Strict mode returns exit code `-12`, restores the complete pre-step
state, and does not commit it. See
[nonlinear convergence and equilibrium safety](nonlinear_convergence_safety.md).
