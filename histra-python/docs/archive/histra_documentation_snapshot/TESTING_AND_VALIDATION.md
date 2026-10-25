# Testing and Validation

## Final default suite

The final command output is included as a deliverable. The default suite contains focused tests for both benchmarks and skips two opt-in long acceptance runs.

Coverage added for Live Load includes:

- HRX model-point/load-template/line-load parsing.
- Exact generalized line-load vector.
- C# Coulomb03 negative-envelope slope selection.
- Hidden InitialInterpolated base dispatch and combined Work vector.
- Sparse factorization reuse/invalidation.
- Solver-scoped cyclic-GC restoration.
- First Live Load C# step.
- Optional complete 87-step ArcLength reference path.


## Preprocessing validation

Focused tests force-regenerate the locked C# benchmark from geometry and
materials, then verify exact interface topology, exact global DOF ordering,
exact afference row structure, close afference coefficients, and initial global
stiffness. Additional tests cover idempotence and automatic preparation before
a nonlinear solve.

Run the measured preprocessing benchmark with:

```bash
python -m histra.tools.benchmark_preprocessing \
  --reference histra/model-output/model.hrx \
  --raw /path/to/unlocked/model.HRX \
  --run-vert \
  --output preprocessing_metrics.json
```

## Commands

From the directory containing `histra/`:

```bash
python -m compileall -q histra
python -c "import histra; print('import ok')"
python -m pytest -q histra/tests
```

Run the long Live Load acceptance test:

```bash
HISTRA_RUN_LIVE_BENCHMARK=1 \
python -m pytest -q histra/tests/test_live_load_arc_length.py \
  -k complete_live_load_reference_path
```

Run the benchmark metrics tool:

```bash
python -m histra.tools.benchmark_csharp_sqlite \
  --hrx histra/model-live/model.hrx \
  --results histra/model-live/model.Results \
  --analysis 22 --combination 1 --selected-dofs 58 \
  --output live_load_benchmark_metrics.json
```
