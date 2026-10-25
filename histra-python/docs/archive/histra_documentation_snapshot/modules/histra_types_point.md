# `histra.types.point`

**Source:** `histra/types/point.py`  
**Size:** 25 lines  
**Layer:** Shared numerical containers, enums, geometry, and state records.

## Purpose

Defines a lightweight three-dimensional point/vector and string parser.

## Dependencies

**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `Point`

Represents a 3D point / vector (port of C# ``Point``).

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `x` | `float` | `0.0` |
| `y` | `float` | `0.0` |
| `z` | `float` | `0.0` |

**Methods**

| Method | Description |
|---|---|
| `def from_str(s: str) -> Point` | From str. |
| `def __iter__() -> Tuple[float, float, float]` | Iter. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
