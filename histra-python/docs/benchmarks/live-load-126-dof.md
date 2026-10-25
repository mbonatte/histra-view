# Vert → Live Load ArcLength Integration

## Selected reference analysis

The added benchmark is the C# SQLite analysis identified by:

- analysis key: `22`
- name: `LiveLoad_1`
- combination: `1`
- integration: `ArcLength`
- nonlinear method: `StandardInitialInterpolatedLineSearch`
- predecessor: analysis `1` (`Vert`), combination `1`, final committed step `5`
- arc-length procedure: `OnlyModelPointsSelected`
- active point: model point `2`, Quad `9`, Z direction, global zero-based DOF `58`
- reference load: one line load on Quad `4`; length `288`, intensity `0.01`, total vertical resultant `2.88`
- C# committed public steps: `1..87`
- C# terminal event: attempted step `88` reaches the configured maximum displacement and is not committed

The `.Results` database is authoritative for committed displacements and compact constitutive states. It does not store an independent ArcLength multiplier per public step, so displacement/state comparisons are the numerical acceptance basis; Python multipliers are still recorded diagnostically.

## Final measured result

Python commits exactly steps `1..87`, in order, then reaches the same maximum-displacement terminal event at attempted step `88` with exit code `-3`. All global vectors are finite.

- maximum relative global-displacement error: `9.142238482844599e-05` (step 3)
- maximum absolute DOF difference: `1.9055000020862245e-05` (step 76)
- steps above the `1e-4` relative tolerance: none
- attempted-step-88 maximum displacement: `1.000006`

Selected rows:

| Step | Python multiplier | Iterations | Relative U error | Max absolute DOF error |
|---:|---:|---:|---:|---:|
| 1 | 11.388762 | 54 | 7.139e-05 | 3.016e-06 |
| 2 | 12.752696 | 87 | 8.802e-05 | 4.085e-06 |
| 3 | 13.980280 | 89 | 9.142e-05 | 4.975e-06 |
| 4 | 15.202878 | 90 | 8.852e-05 | 5.624e-06 |
| 10 | 20.284298 | 94 | 7.339e-05 | 7.863e-06 |
| 40 | 28.959881 | 98 | 3.063e-05 | 1.386e-05 |
| 76 | 30.567582 | 104 | 1.870e-05 | 1.906e-05 |
| 87 | 30.793530 | 105 | 1.634e-05 | 1.848e-05 |

The validation wall time recorded in the supplied metrics includes sandbox CPU throttling and validation-only process checkpoints; it should not be treated as a production performance measurement.

## Required compatibility behavior

The result depends on several non-obvious C# behaviors:

1. Chained initialization restores the complete final `Vert` state and then sets the new analysis baseline external vector equal to the negative committed resisting-force vector (`SetFextEqualToFint`). It does not regenerate the predecessor load combination.
2. Static preparation assembles initial stiffness with `alfa = 0` for this analysis.
3. The C# Newton tangent-update condition accidentally omits `StandardInitialInterpolatedLineSearch`, so the initial matrix is retained throughout each step.
4. `InitialInterpolatedSearch` hides rather than overrides the base methods. Through the base `LineSearch` reference, the search is a no-op.
5. Because the search is a no-op, the Work convergence test must retain the ArcLength combined correction already stored in `LS.X`; replacing it with the raw Newton direction changes commit iterations and the nonlinear path.
6. `SpringCoulomb03.setEnvelope` uses the maximum of the three negative-envelope slopes for `Eun`.
7. Sparse factorization is reused while the initial stiffness remains unchanged.

## Constitutive evidence

Starting from the complete C# `Vert` committed state and applying exact C# Live Load displacements through step 4 reproduces all 2,454 compact spring states:

- 2,349 transverse hysteretic springs: matching force and phase
- 105 Coulomb03 springs: matching force, phase, normal force, friction limits, and plastic/slip state
- maximum observed force difference in this exact-input diagnostic: approximately `2.55e-10`
- no phase mismatches

This establishes that the remaining small global displacement differences are numerical path differences within tolerance, not constitutive-state divergence.

## Line-load source/database note

A literal port of the supplied C# intrinsic-coordinate helper (`AlignNodes`/`FindU`/`FindV`) worsened agreement with the database by roughly two orders of magnitude. The retained float32 Newton inverse reproduces the committed database path. This indicates source/binary skew or a corrected line-load implementation in the binary that generated the database. Python prioritizes the measured SQLite reference and documents the deviation rather than claiming literal source identity.

## Commands

From the directory containing `histra/`:

```bash
python -m compileall -q histra
python -c "import histra; print(histra.__file__)"
python -m pytest -q histra/tests
```

Focused first-step test:

```bash
python -m pytest -q histra/tests/test_live_load_arc_length.py \
  -k first_live_load_step
```

Complete 87-step acceptance test:

```bash
HISTRA_RUN_LIVE_BENCHMARK=1 \
python -m pytest -q histra/tests/test_live_load_arc_length.py \
  -k complete_live_load_reference_path
```

Machine-readable benchmark:

```bash
python -m histra.tools.benchmark_csharp_sqlite \
  --hrx histra/model-live/model.hrx \
  --results histra/model-live/model.Results \
  --analysis 22 --combination 1 \
  --selected-dofs 58 \
  --output live_load_benchmark_metrics.json
```

For this ArcLength benchmark, reproducing the reference terminal condition (`-3` at attempted step 88 after exact committed steps `1..87`) is reported as a successful reference completion.
