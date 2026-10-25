# `histra.solver.arc_length`

**Source:** `histra/solver/arc_length.py`  
**Size:** 376 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Implements a Crisfield-style arc-length integrator with predictor/corrector load-factor updates.

## Dependencies

**Internal:** `.assembler`, `histra.model.model`, `histra.solver.incremental_integrator`, `histra.solver.model_manager`, `histra.solver.program`, `histra.types.linear_system`  
**Python/third-party:** `logging`, `math`, `numpy`, `scipy`, `typing`  

## API and implementation units

### `ArcLength`

Spherical arc-length integrator (Crisfield 1981).

**Bases:** `StaticIntegrator`

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `PSI` | `float` | `0.0` |

**Methods**

| Method | Description |
|---|---|
| `def __init__()` | Initializes object state. |
| `def new_step(p: Program, model: Model, ls: LinearSystem, an: Any, combination: int, step: int, dof: int) -> None` | Start a new arc-length step — applies the predictor load increment. |
| `def form_unbalance(p: Program, model: Model, an: Any) -> None` | Compute residual R = lambda*P_ref _ F_int. |
| `def compute_increment(p: Program, ls: LinearSystem, model: Model, an: Any, fixed_dofs: Set[int] \| None = None) -> np.ndarray` | Compute search direction Du = du* + dlambda*duP using the arc-length |
| `def update(model: Model, p: Program, an: Any) -> int` | Update element state from ls.x, accumulate u, and advance lambda. |
| `def commit(model: Model, an: Any, disp: float, dof_max: int, has_domain_changed: list[bool]) -> bool` | Finalise the step _ advance pseudo-time and check termination. |
| `def get_time() -> float` | Returns the current pseudo-time. |

### `ArcLengthLinear`

Linear arc-length stub.

**Bases:** `ArcLength`

## Runtime behavior

- Computes a reference displacement direction `duP = K⁻¹P` and uses an arc-length constraint to solve for load-factor corrections.
- Tracks cumulative displacement within the current step and the global load factor `lambda`.

## Known issues affecting this module

- **ISSUE-08 — Standard ArcLength predictor can solve against an unassembled zero matrix** (Critical). See [ISSUES.md](../ISSUES.md#issue-08).
- **ISSUE-18 — Sparse solve warnings and nonfinite results are not promoted to solver failures** (High). See [ISSUES.md](../ISSUES.md#issue-18).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
