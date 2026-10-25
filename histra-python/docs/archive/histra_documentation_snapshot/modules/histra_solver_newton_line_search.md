# `histra.solver.newton_line_search`

**Source:** `histra/solver/newton_line_search.py`  
**Size:** 206 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Runs Newton equilibrium iterations with an additional line-search scaling phase.

### Source docstring

Newton-Raphson with line search _ port of HiStrA's NewtonLineSearch.

## Dependencies

**Internal:** `histra.model.model`, `histra.solver.arc_length`, `histra.solver.assembler`, `histra.solver.line_search`, `histra.solver.model_manager`, `histra.solver.program`, `histra.solver.solution_algorithm`, `histra.types.linear_system`  
**Python/third-party:** `logging`, `numpy`, `scipy`, `typing`  

## API and implementation units

### `NewtonLineSearch`

Port of NewtonLineSearch (C# SolverRuntime.NumericalProcedure.NewtonLineSearch).

**Bases:** `EquiSolnAlgo`

**Methods**

| Method | Description |
|---|---|
| `def solve_current_step(p: Program, ls: LinearSystem, model: Model, an: Any, combination: int, step: int, alfa: float) -> int` | Runs equilibrium iterations for one analysis step. |

### Module functions

| Function | Description |
|---|---|
| `def _new_line_search(an: Any) -> LineSearch` | Port of LineSearch.NewLineSearch factory. |

## Runtime behavior

- Applies a full Newton update first, evaluates the new residual, then asks the line-search object for a scale factor.
- The line search may perform additional trial updates before the convergence test is evaluated.

## Known issues affecting this module

- **ISSUE-01 — Regula Falsi line search starts with a degenerate bracket and corrupts trial-state accounting** (Critical). See [ISSUES.md](../ISSUES.md#issue-01).
- **ISSUE-07 — NewtonLineSearch initializes relative convergence with a zero reference norm** (Critical). See [ISSUES.md](../ISSUES.md#issue-07).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
