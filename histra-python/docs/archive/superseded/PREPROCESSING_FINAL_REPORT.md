# Update: exact nonlinear preprocessing alignment

The later 560-DOF C# benchmark exposed additional compatibility-sensitive rules.
They are now corrected. See `PREPROCESSING_EXACTNESS_REPORT.md` for the complete
source trace and measured 38-step Live Load comparison. The earlier statement
that preprocessing was merely topology/stiffness complete is superseded by that
report.

# HiStrA `ModelManager.PrepareModel` Python port — final report

## Result

The C# preprocessing path required by the supplied masonry Quad/Restraint
models has been ported to Python. The uploaded `new_model.hrx`, which contains
geometry and materials but no computational objects, is now converted in memory
into a solver-ready nonlinear model and completes its full five-step `Vert`
analysis.

## Baseline failure

Before this work, the unlocked HRX failed first with:

```text
AttributeError: 'Quad' object has no attribute 'spring'
```

That exception hid the complete missing state: `GDL=0`, no diagonal springs, no
interfaces, no interface springs, and no afference matrices.

## Implemented C# behavior

The new preprocessing module implements the selected path through C#
`ModelManager.PrepareModel` and its required dependencies:

- material-to-constitutive-law extraction;
- Quad geometry/local-axis preparation;
- Quad global DOF assignment;
- Quad diagonal Coulomb spring generation;
- exact shared-edge Quad–Quad interface generation;
- fixed Quad–Restraint interface generation;
- transverse-fiber discretization and hysteretic spring construction;
- in-plane and two out-of-plane Coulomb spring families;
- interface status initialization;
- Quad and Interface afference generation;
- C# `1e-4` afference-coefficient cutoff;
- solver-readiness validation and automatic invocation before analysis.

## C# compatibility details corrected during porting

Several non-obvious source behaviors were verified rather than inferred:

- C# rocking `IsDuct*` flags select the effectively unlimited branch when
  `true`, contrary to the intuitive reading of the names.
- `BetaUnload*` values populate hysteretic `Alfau`; C# hard-codes `Alfar=1` in
  this constructor path.
- Coulomb `Set`/`Set2` use constitutive ratios to create the virgin envelope but
  do not persist all ratios into the serialized spring properties.
- Quad compression capacity uses the C# shear/cohesion cap.
- Afference assembly discards coefficients below `1e-4`.
- Restraint material selection must use parent element type, not only a numeric
  key that may collide with a Quad key.

## Regeneration benchmark

Python force-regenerated the existing locked 18-Quad C# benchmark from its raw
geometry and material data.

| Metric | Result |
|---|---:|
| Global DOFs | 126, exact |
| Interfaces | 29, exact topology and order |
| Interface afference entries | 880, exact |
| Afference DOF sequence | exact |
| Afference coefficient relative L2 error | `4.112e-8` |
| Afference maximum absolute difference | `1.257e-5` |
| Initial global stiffness relative L2 error | `1.974e-7` |

Spring-property relative L2 errors are generally between `1e-8` and `3e-6` for
the compared virgin fields. Post-analysis Quad friction/cohesion fields were
excluded because the locked HRX stores a normal-force-mutated envelope rather
than the virgin preprocessing state.

## Uploaded raw model result

| Generated item | Count |
|---|---:|
| Global DOFs | 560 |
| Quad diagonal springs | 80 |
| Quad–Quad interfaces | 129 |
| Quad–Restraint interfaces | 6 |
| Transverse springs | 10,935 |
| In-plane sliding springs | 135 |
| Out-of-plane sliding springs | 270 |

The complete `Vert` run committed five steps:

| Step | Load factor | Iterations | HiStrA `ReactionSum Z` |
|---:|---:|---:|---:|
| 1 | 0.2 | 5 | `-183.5790405` |
| 2 | 0.4 | 10 | `-367.1580238` |
| 3 | 0.6 | 7 | `-550.7369919` |
| 4 | 0.8 | 23 | `-734.3160553` |
| 5 | 1.0 | 2 | `-917.8950195` |

Measured audit runtime:

- preprocessing: approximately 20.0 seconds;
- five-step Vert solve: approximately 2.0 seconds;
- combined benchmark command, including C#-reference regeneration: 27.6
  seconds.

## Live Load status

Preprocessing is no longer the blocker. The uploaded HRX defines the line load
under condition 11 but its custom load combination 15 has no condition-11
coefficient. Python stops explicitly rather than applying zero load. The known
working model uses row-1 coefficient `1.0` for condition 11.

## Test status

Final verification:

```text
compileall: PASS
import: PASS
140 passed, 2 skipped, 0 failed
```

The new focused tests cover C# topology regeneration, afference identity,
initial stiffness, idempotence, the `ModelManager.prepare_model` public entry
point, and automatic preprocessing before a nonlinear solve.

## Remaining preprocessing limitations

The implementation is intentionally scoped to the supplied masonry
Quad/fixed-Restraint topology. Partial polygon contacts, slave/partition
models, other computational element families, non-fixed restraint behavior,
and dynamic preprocessing remain explicit unsupported cases. Python also does
not yet serialize the generated computational model back into an HRX file.
