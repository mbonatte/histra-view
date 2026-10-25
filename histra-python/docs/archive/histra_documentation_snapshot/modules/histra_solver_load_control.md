# `histra.solver.load_control`

**Source:** `histra/solver/load_control.py`  
**Size:** 199 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Implements pseudo-time/load-factor stepping and domain updates for load-controlled nonlinear analysis.

## Dependencies

**Internal:** `histra.model.model`, `histra.solver.incremental_integrator`, `histra.solver.model_manager`, `histra.solver.program`, `histra.types.linear_system`  
**Python/third-party:** `logging`, `numpy`, `scipy`, `typing`  

## API and implementation units

### `LoadControl`

Port of SolverRuntime.Integrator.LoadControl.

**Bases:** `StaticIntegrator`

**Methods**

| Method | Description |
|---|---|
| `def __init__()` | Initializes object state. |
| `def _get_initial_time_and_force(an: Any) -> None` | Read the load function definition (port of GetInitialTimeAndForce). |
| `def domain_changed(p: Program, model: Model, size: int) -> None` | Port of domainChanged _ init load function on first call. |
| `def _get_increment() -> tuple[float, float]` | Port of GetIncrement. |
| `def new_step(p: Program, model: Model, ls: LinearSystem, an: Any, combination: int, step: int, dof: int) -> None` | Port of the 6-arg NewStep. |
| `def new_step_with_incr(p: Program, model: Model, ls: LinearSystem, an: Any, combination: int, step: int, incr_mult: float) -> None` | Port of the 7-arg NewStep (used by ALS). |
| `def update(model: Model, p: Program, an: Any) -> int` | Port of LoadControl.Update _ increment iteration, update domain, accumulate u. |
| `def commit(model: Model, an: Any, disp: float, dof_max: int, has_domain_changed: list[bool]) -> bool` | Port of LoadControl.Commit. Returns True when all load steps done. |
| `def get_time() -> float` | Returns the current pseudo-time. |

## Runtime behavior

- Interpolates pseudo-time and multiplier increments from the active load function.
- Adds `increment × reference load` to the accumulated external load vector at each step.

## Known issues affecting this module

- **ISSUE-03 — LoadControl clears the vector documented and used as total displacement at every step** (Critical). See [ISSUES.md](../ISSUES.md#issue-03).
- **ISSUE-19 — Multiplier-based discretization mishandles unloading ranges** (Medium). See [ISSUES.md](../ISSUES.md#issue-19).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
