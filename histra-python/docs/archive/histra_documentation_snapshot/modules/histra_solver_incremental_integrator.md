# `histra.solver.incremental_integrator`

**Source:** `histra/solver/incremental_integrator.py`  
**Size:** 292 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Defines the common incremental/static integrator protocol, state vectors, load application, load-function increments, and integrator factory.

## Dependencies

**Internal:** `histra.solver.assembler`, `histra.solver.model_manager`, `histra.types.integrator_state`, `histra.types.linear_system`  
**Python/third-party:** `numpy`, `scipy`, `typing`  

## API and implementation units

### `IncrementalIntegrator`

Port of SolverRuntime.Integrator.IncrementalIntegrator.

**Methods**

| Method | Description |
|---|---|
| `def __init__()` | Initializes object state. |
| `def step() -> int` | Step. |
| `def step(val: int) -> None` | Step. |
| `def iteration() -> int` | Iteration. |
| `def iteration(val: int) -> None` | Iteration. |
| `def incr_mult() -> float` | Incr mult. |
| `def incr_mult(val: float) -> None` | Incr mult. |
| `def mult() -> float` | Mult. |
| `def mult(val: float) -> None` | Mult. |
| `def update(model: Any, p: Any, an: Any) -> int` | Port of Update _ update element state, accumulate u += Du. |
| `def form_unbalance(p: Any, model: Any, an: Any) -> None` | Port of formUnbalance virtual _ delegates to ModelManager. |
| `def update_k(p: Any, model: Any, alfa: float, compute_c: bool = False) -> None` | Port of UpdateK virtual _ assemble tangent stiffness. |
| `def new_step(p: Any, model: Any, ls: LinearSystem, an: Any, combination: int, step: int, dof: int) -> None` | Port of NewStep _ start a new load step. |
| `def commit(model: Any, an: Any, disp: float, dof_max: int, has_domain_changed: list[bool]) -> bool` | Port of Commit _ finalise the step. |
| `def domain_changed(p: Any, model: Any, size: int) -> None` | Port of domainChanged _ called when the domain topology changes. |
| `def revert_to_last_commit(model: Any, ls: LinearSystem) -> None` | Port of revertToLastCommit _ undo to last committed state. |
| `def get_time() -> float` | Returns the current pseudo-time. |
| `def _get_initial_time_and_force(an: Any) -> None` | Read the load function definition (port of GetInitialTimeAndForce). |
| `def domain_changed(p: Any, model: Any, size: int) -> None` | Port of domainChanged _ init load function on first call. |
| `def _get_increment() -> tuple[float, float]` | Port of GetIncrement. |
| `def compute_increment(p: Any, ls: LinearSystem, model: Any, an: Any, fixed_dofs: Set[int] \| None = None) -> np.ndarray` | Compute the search direction Du for the current iteration. |
| `def update_ptarget(p: Any, model: Any, an: Any, combination: int, iteration: int) -> None` | Port of UpdatePtarget _ reassemble loads if P-D or frames present. |

### `StaticIntegrator`

Port of SolverRuntime.Integrator.StaticIntegrator.

**Bases:** `IncrementalIntegrator`

**Methods**

| Method | Description |
|---|---|
| `def apply_load_domain(model: Any, incr_mult: float) -> None` | Port of ApplyLoadDomain: Fext += IncrMult * Ptarget. |
| `def new_step(p: Any, model: Any, ls: LinearSystem, an: Any, combination: int, step: int, dof: int) -> None` | Default new step _ apply load increment. |
| `def commit(model: Any, an: Any, disp: float, dof_max: int, has_domain_changed: list[bool]) -> bool` | Default commit _ stop after one step. |
| `def new_static_integrator(an: Any, combination: int) -> StaticIntegrator` | Factory _ port of NewStaticIntegrator. |

## Known issues affecting this module

- **ISSUE-05 — Load-controlled Newton solves ignore restrained DOFs** (Critical). See [ISSUES.md](../ISSUES.md#issue-05).
- **ISSUE-06 — Rollback calls `LinearSystem.set_x` with the wrong signature** (Critical). See [ISSUES.md](../ISSUES.md#issue-06).
- **ISSUE-09 — Load-function points are not represented or parsed** (High). See [ISSUES.md](../ISSUES.md#issue-09).
- **ISSUE-11 — P-Delta configuration uses incompatible string and integer representations and has no computed load vector** (High). See [ISSUES.md](../ISSUES.md#issue-11).
- **ISSUE-19 — Multiplier-based discretization mishandles unloading ranges** (Medium). See [ISSUES.md](../ISSUES.md#issue-19).
- **ISSUE-22 — Duplicate definitions and factories obscure the active implementation** (Low). See [ISSUES.md](../ISSUES.md#issue-22).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
