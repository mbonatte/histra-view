# `histra.solver.solver`

**Source:** `histra/solver/solver.py`  
**Size:** 73 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Provides the simpler linear static solve, reference-solution verification, and residual calculation helpers.

### Source docstring

Linear system solver — wraps scipy.sparse.linalg.spsolve.

## Dependencies

**Internal:** `.assembler`, `histra.model.model`  
**Python/third-party:** `numpy`, `scipy`  

## API and implementation units

### Module functions

| Function | Description |
|---|---|
| `def solve_linear(model: Model, alfa: float = 0.0) -> np.ndarray` | Solve the linear static system K·u = b. |
| `def verify_solution(model: Model, alfa: float = 0.0) -> dict` | Verification: assemble K, extract reference u, compute f = K·u. |
| `def compute_residual(K: sp.csc_matrix, u: np.ndarray, b: np.ndarray) -> float` | Compute \|\|K·u - b\|\| / \|\|b\|\|. |

## Known issues affecting this module

- **ISSUE-17 — Factory and linear-solver arguments silently select incorrect behavior** (High). See [ISSUES.md](../ISSUES.md#issue-17).
- **ISSUE-18 — Sparse solve warnings and nonfinite results are not promoted to solver failures** (High). See [ISSUES.md](../ISSUES.md#issue-18).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
