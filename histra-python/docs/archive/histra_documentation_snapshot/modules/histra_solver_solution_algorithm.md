# `histra.solver.solution_algorithm`

**Source:** `histra/solver/solution_algorithm.py`  
**Size:** 98 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Selects the equilibrium algorithm, static integrator, line search, and convergence test from analysis settings.

## Dependencies

**Internal:** `histra.solver.incremental_integrator`, `histra.types.convergence_test`, `histra.types.linear_system`  
**Python/third-party:** `numpy`, `typing`  

## API and implementation units

### `SolutionAlgorithm`

Port of SolutionAlgorithm base (empty).

### `EquiSolnAlgo`

Port of EquiSolnAlgo.

**Bases:** `SolutionAlgorithm`

**Methods**

| Method | Description |
|---|---|
| `def __init__()` | Initializes object state. |
| `def solve_current_step(p: Any, ls: LinearSystem, model: Any, an: Any, combination: int, step: int, alfa: float) -> int` | Virtual _ subclasses override. |
| `def new_equi_soln_algo(an: Any, combination: int) -> EquiSolnAlgo` | Factory _ port of NewEquiSolnAlgo. |

### Module functions

| Function | Description |
|---|---|
| `def _new_line_search(an: Any) -> Any` | Port of LineSearch.NewLineSearch factory. |

## Known issues affecting this module

- **ISSUE-10 — Configured maximum displacement is read but not passed to the convergence test** (High). See [ISSUES.md](../ISSUES.md#issue-10).
- **ISSUE-17 — Factory and linear-solver arguments silently select incorrect behavior** (High). See [ISSUES.md](../ISSUES.md#issue-17).
- **ISSUE-22 — Duplicate definitions and factories obscure the active implementation** (Low). See [ISSUES.md](../ISSUES.md#issue-22).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
