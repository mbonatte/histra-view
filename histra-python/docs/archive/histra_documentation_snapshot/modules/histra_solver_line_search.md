# `histra.solver.line_search`

**Source:** `histra/solver/line_search.py`  
**Size:** 144 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Defines the line-search interface and a Regula Falsi implementation for scaling Newton increments.

## Dependencies

**Python/third-party:** `numpy`, `typing`  

## API and implementation units

### `LineSearch`

Port of C# LineSearch base class.

**Methods**

| Method | Description |
|---|---|
| `def __init__()` | Initializes object state. |
| `def new_step(p: Any, ls: Any) -> None` | Port of newStep _ save initial dx for the search direction. |
| `def search(model: Any, p: Any, ls: Any, integrator: Any, an: Any, dx0: np.ndarray, s0: float, s1: float) -> float` | Port of search _ find optimal step scaling eta. |

### `RegulaFalsiLineSearch`

Port of C# RegulaFalsiLineSearch.

**Bases:** `LineSearch`

**Methods**

| Method | Description |
|---|---|
| `def __init__()` | Initializes object state. |
| `def new_step(p: Any, ls: Any) -> None` | Initializes and applies the predictor/load increment for a new step. |
| `def search(model: Any, p: Any, ls: Any, integrator: Any, an: Any, dx0: np.ndarray, s0: float, s1: float) -> float` | Search. |

## Known issues affecting this module

- **ISSUE-01 — Regula Falsi line search starts with a degenerate bracket and corrupts trial-state accounting** (Critical). See [ISSUES.md](../ISSUES.md#issue-01).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
