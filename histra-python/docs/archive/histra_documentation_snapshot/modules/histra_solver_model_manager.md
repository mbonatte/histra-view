# `histra.solver.model_manager`

**Source:** `histra/solver/model_manager.py`  
**Size:** 199 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Coordinates element assembly, global reference/external load vectors, residual formation, domain updates, energy, and displacement monitoring.

## Dependencies

**Internal:** `histra.model.model`, `histra.solver.assembler`, `histra.types.integrator_state`, `histra.types.linear_system`  
**Python/third-party:** `logging`, `numpy`, `typing`  

## API and implementation units

### `ModelManager`

Port of SolverRuntime.ModelManager (static methods).

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `_ptarget` | `np.ndarray | None` | `None` |
| `_fext` | `np.ndarray | None` | `None` |
| `_pq` | `np.ndarray | None` | `None` |
| `_pq_prev` | `np.ndarray | None` | `None` |
| `_u_total` | `np.ndarray | None` | `None` |
| `on_log` | `Callable[[str], None] | None` | `None` |
| `on_progress` | `Callable[[float], None] | None` | `None` |

**Methods**

| Method | Description |
|---|---|
| `def assemble_k(model: Model, ls: LinearSystem, set_zero: bool = True) -> None` | Port of AssembleK. |
| `def assemble_load(model: Model, ls: LinearSystem, analysis_key: int \| None = None, combination: int = 1) -> None` | Port of AssembleLoad. |
| `def compute_ktang(model: Model, ls: LinearSystem, alfa: float) -> int` | Port of AssembleKtang. |
| `def compute_k(model: Model, alfa: float = 1.0) -> None` | Port of ComputeK _ calls each element's ComputeK(alfa). |
| `def form_unbalance(model: Model, ls: LinearSystem, an: Any) -> None` | Port of formUnbalance. |
| `def get_resisting_force(model: Model, ls: LinearSystem) -> None` | Port of GetResistingForce. |
| `def update_domain(model: Model, ls: LinearSystem, state: IntegratorState) -> None` | Port of updateDomain. |
| `def compute_energy(model: Model, eel: float, ed: float) -> None` | Port of ComputeEnergy _ sums elastic and dissipated energy. |
| `def find_max_u(model: Model, p: Program) -> None` | Port of FindMaxU. |
| `def get_dof_for_max_displacement(p: Program, model: Model, an: Any) -> int` | Port of GetDofForMaxDisplacement. |

## Known issues affecting this module

- **ISSUE-04 — Standard Newton tangent assembly is overwritten by initial-stiffness assembly** (Critical). See [ISSUES.md](../ISSUES.md#issue-04).
- **ISSUE-11 — P-Delta configuration uses incompatible string and integer representations and has no computed load vector** (High). See [ISSUES.md](../ISSUES.md#issue-11).
- **ISSUE-16 — Energy accumulation modifies local float copies and returns nothing** (Medium). See [ISSUES.md](../ISSUES.md#issue-16).
- **ISSUE-21 — ModelManager stores analysis vectors as class-global mutable state** (Medium). See [ISSUES.md](../ISSUES.md#issue-21).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
