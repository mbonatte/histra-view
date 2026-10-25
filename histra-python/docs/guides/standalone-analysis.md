# Standalone Vert → Live Load analysis

Run an HRX model without using a C# `.Results` database as the analysis-state
transport.

```bash
python -m histra.tools.run_vert_live path/to/model.hrx \
  --output-dir python-results
```

Optional selectors:

```bash
python -m histra.tools.run_vert_live path/to/model.hrx \
  --vert-analysis Vert \
  --live-analysis LiveLoad_1 \
  --combination 1 \
  --output-dir python-results
```

The command:

1. loads the HRX;
2. preprocesses it when the validated computational objects are absent;
3. runs the selected gravity/Vert analysis;
4. retains committed global and constitutive state in memory;
5. initializes the chained Live Load analysis;
6. exports step summaries, node displacements, reactions, a solver log, and
   `run_summary.json`.

The Live Load terminal state may be a configured displacement-limit condition
rather than an ordinary converged continuation state. Read the output status
instead of assuming a zero process exit means every requested continuation is
available.

## Recommended Solver Method

- Use **`ForceMoment`** when strict force-equilibrium acceptance is required.
  `StandardRegulaFalsiLineSearch` is the first strategy to benchmark for
  nonlinear pushovers, but it is a recommendation rather than a universal
  optimum: qualify it against the accepted response and equilibrium audit for
  the model being released.
- **`Work`** and **`DispRotation`** can reproduce an authored C# path, but they
  do not independently establish force equilibrium. Keep the default strategy
  advisor enabled and use strict equilibrium auditing for production runs.
- See [Nonlinear convergence safety](../nonlinear_convergence_safety.md) and the
  [strategy benchmark methodology](../benchmarks/solver-strategy-methodology.md)
  for the qualification criteria and reproducible commands.
