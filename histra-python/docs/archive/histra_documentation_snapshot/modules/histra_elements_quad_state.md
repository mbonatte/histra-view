# `histra.elements.quad_state`

**Source:** `histra/elements/quad_state.py`  
**Size:** 11 lines  
**Layer:** Runtime finite/discrete element implementations and their mutable state.

## Purpose

Defines the small mutable state record held by each quadrilateral element.

## Dependencies

**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `QuadState`

Class defined by `histra.elements.quad_state`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `u` | `List[float]` | `field(default_factory=lambda: [0.0] * 7)` |
| `k` | `float` | `0.0` |
| `p` | `List[float]` | `field(default_factory=lambda: [0.0] * 7)` |
| `f` | `float` | `0.0` |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
