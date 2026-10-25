# `histra.solver.newton_raphson`

**Source:** `histra/solver/newton_raphson.py`  
**Size:** 184 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Runs standard or modified Newton-Raphson equilibrium iterations and convergence checks.

### Source docstring

Newton-Raphson iteration loop _ port of HiStrA's NewmarkNewtonRaphson.

## Dependencies

**Internal:** `histra.model.model`, `histra.solver.assembler`, `histra.solver.model_manager`, `histra.solver.program`, `histra.solver.solution_algorithm`, `histra.types.linear_system`  
**Python/third-party:** `logging`, `numpy`, `scipy`, `typing`  

## API and implementation units

### `NewtonRaphson`

Port of NewtonRaphson (SolverRuntime.NumericalProcedure.NewtonRaphson).

**Bases:** `EquiSolnAlgo`

**Methods**

| Method | Description |
|---|---|
| `def solve_current_step(p: Program, ls: LinearSystem, model: Model, an: Any, combination: int, step: int, alfa: float) -> int` | Runs equilibrium iterations for one analysis step. |

## Runtime behavior

- Forms the residual, optionally rebuilds stiffness, computes a displacement correction, updates every element, and tests convergence.
- The `alfa` argument distinguishes the intended standard/full tangent path from modified Newton behavior.

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
