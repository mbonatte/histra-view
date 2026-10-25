# `histra.types.linear_system`

**Source:** `histra/types/linear_system.py`  
**Size:** 79 lines  
**Layer:** Shared numerical containers, enums, geometry, and state records.

## Purpose

Owns sparse matrices and the global right-hand-side/solution vectors for the current equilibrium iteration.

## Dependencies

**Python/third-party:** `numpy`, `scipy`, `typing`  

## API and implementation units

### `LinearSystem`

Port of C# ``LinearSystem`` — holds K, M, C, b, x.

**Methods**

| Method | Description |
|---|---|
| `def __init__(n: int)` | Initializes object state. |
| `def sumb(i: int, v: float) -> None` | Add *v* to ``b[i]`` (port of ``A.sumb(i, v)`` in C#). |
| `def get_b_norm(norm_type: int = 2) -> float` | Get b norm. |
| `def set_x(i: int, v: float) -> None` | Set ``x[i] = v``. |
| `def get_x(i: int) -> float` | Return ``x[i]``. |
| `def set_b(i: int, v: float) -> None` | Set ``b[i] = v``. |
| `def get_b(i: int) -> float` | Return ``b[i]``. |
| `def set_k(i: int, j: int, v: float) -> None` | Set entry K[i,j] = v (only if K is in LIL format). |
| `def get_k(i: int, j: int) -> float` | Return K[i, j]. |
| `def zero_b() -> None` | Zero b. |
| `def zero_x() -> None` | Zero x. |
| `def copy_b_to_b0() -> None` | Copy b to b0. |
| `def set_zero_load() -> None` | Zero the load vector b (port of A.setZeroLoad). |
| `def set_zero() -> None` | Zero the entire system (port of K.SetZero). |
| `def solve() -> None` | Solve K*x = b (in-place, stores result in x). |

## Runtime behavior

- Stores `K`, `M`, and `C` as CSC sparse matrices and `x`, `b`, and `b0` as dense NumPy vectors.
- The current `solve()` method invokes SciPy `spsolve` on the complete system.

## Known issues affecting this module

- **ISSUE-05 — Load-controlled Newton solves ignore restrained DOFs** (Critical). See [ISSUES.md](../ISSUES.md#issue-05).
- **ISSUE-06 — Rollback calls `LinearSystem.set_x` with the wrong signature** (Critical). See [ISSUES.md](../ISSUES.md#issue-06).
- **ISSUE-18 — Sparse solve warnings and nonfinite results are not promoted to solver failures** (High). See [ISSUES.md](../ISSUES.md#issue-18).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
