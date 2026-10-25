# Benchmark Methodology

## Reference selection

The benchmark is the only analysis represented in `model.Results`:

- analysis key 1 (`Vert`),
- database combination 1,
- steps 0–5,
- HRX load-combination key 6, row 1.

## SQLite reading

The comparison script reads all reference displacement vectors before solving. Final step 5 is read directly from `DynamicVectorsState`. Intermediate global vectors are reconstructed from `QuadStates` and `InterfaceStates` through the model's afference mappings, with consistency checks where multiple elements contribute to the same DOF.

Spring history is not reconstructed from `SpringStatesTmp`: those rows omit fields required for lossless constitutive restart. `SpringStates` contains complete final-step history and is used for restart validation.

## Metrics

For each committed Python step:

- load-factor absolute error,
- global displacement relative L2 error,
- maximum absolute DOF error,
- iteration count,
- convergence Work error,
- residual norm,
- increment norm,
- selected DOFs,
- finite-value status.

Acceptance is initially displacement relative error <= 1e-4 and load-factor error <= 1e-6, with exact step number/order and no NaN/Inf.

## Reproduction command

From the directory containing the `histra` folder:

```bash
python -m histra.tools.benchmark_csharp_sqlite \
  --hrx histra/model-output/model.hrx \
  --results histra/model-output/model.Results \
  --analysis 1 --combination 1 \
  --output histra_benchmark_metrics.json
```
