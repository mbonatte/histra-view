# `histra.types.convergence_test`

**Source:** `histra/types/convergence_test.py`  
**Size:** 112 lines  
**Layer:** Shared numerical containers, enums, geometry, and state records.

## Purpose

Evaluates residual convergence, iteration limits, and maximum-displacement limits.

## Dependencies

**Python/third-party:** `logging`, `typing`  

## API and implementation units

### `ConvergenceTest`

Port of SolverRuntime.ConvergenceTest.ConvergenceTest.

**Methods**

| Method | Description |
|---|---|
| `def __init__(tolerance: float = 1e-06, max_iter: int = 100, max_u: float = 1e+30, print_level: int = 0, norm_type: int = 2, absolute: bool = False)` | Initializes object state. |
| `def set_tolerance(tol: float) -> None` | Set tolerance. |
| `def set_max_num_iter(n: int) -> None` | Set max num iter. |
| `def set_print_level(n: int) -> None` | Set print level. |
| `def test(*args, **kwargs)` | Test. |
| `def start(ls: LinearSystem \| None = None, reference_norm: float = 0.0) -> int` | Start. |
| `def get_error() -> float` | Get error. |
| `def get_tol() -> float` | Get tol. |
| `def test(p: Program, model: Any, ls: LinearSystem) -> int` | Check convergence (high-level API used by NewtonRaphson). |

## Known issues affecting this module

- **ISSUE-07 — NewtonLineSearch initializes relative convergence with a zero reference norm** (Critical). See [ISSUES.md](../ISSUES.md#issue-07).
- **ISSUE-10 — Configured maximum displacement is read but not passed to the convergence test** (High). See [ISSUES.md](../ISSUES.md#issue-10).
- **ISSUE-22 — Duplicate definitions and factories obscure the active implementation** (Low). See [ISSUES.md](../ISSUES.md#issue-22).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
