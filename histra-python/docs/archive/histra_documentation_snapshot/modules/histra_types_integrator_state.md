# `histra.types.integrator_state`

**Source:** `histra/types/integrator_state.py`  
**Size:** 21 lines  
**Layer:** Shared numerical containers, enums, geometry, and state records.

## Purpose

Carries step/iteration analysis context into element update routines.

## Dependencies

**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `IntegratorState`

State data carried through a step integration (port of ``IntegratorState``).

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `step` | `int` | `0` |
| `lambda_` | `float` | `0.0` |
| `dlambda` | `float` | `0.0` |
| `u` | `Any` | `None` |
| `delta_lambda` | `float` | `0.0` |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
