# `histra.solver.program`

**Source:** `histra/solver/program.py`  
**Size:** 68 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Holds analysis-wide vectors, status, callbacks, and graph/reporting hooks used by the solver loop.

## Dependencies

**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `Program`

Port of SolverRuntime.Program.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `gdl` | `int` | `0` |
| `ls` | `Any | None` | `None` |
| `u` | `Any | None` | `None` |
| `v` | `Any | None` | `None` |
| `max_u` | `float` | `0.0` |
| `elem_max_u_key` | `int` | `0` |
| `elem_max_u_type` | `str` | `''` |
| `to_stop` | `bool` | `False` |
| `index_fact_k` | `int` | `0` |
| `on_log` | `Any | None` | `None` |
| `on_progress` | `Any | None` | `None` |

**Methods**

| Method | Description |
|---|---|
| `def log(msg: str) -> None` | Log. |
| `def progress(val: float) -> None` | Progress. |
| `def get_value_graph_analysis(collections: Any, an: Any, dof: int, reaction_sum: Any, out_displ: list) -> list` | Port of GetValueGraphAnalysis _ [load_factor, displacement, ...]. |
| `def add_value_graph_static_analysis(collections: Any, an: Any, values: list, ref_values: list, dof: int, step: int, time: float) -> None` | Add value graph static analysis. |

## Known issues affecting this module

- **ISSUE-15 — Reported load factor and displacement-based stopping metric use placeholder/wrong values** (High). See [ISSUES.md](../ISSUES.md#issue-15).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
