# `histra.types.xml_utils`

**Source:** `histra/types/xml_utils.py`  
**Size:** 16 lines  
**Layer:** Shared numerical containers, enums, geometry, and state records.

## Purpose

Provides typed, default-aware XML attribute extraction.

## Dependencies

**Python/third-party:** `typing`  

## API and implementation units

### Module functions

| Function | Description |
|---|---|
| `def _attr(elem: Any, name: str, default: Any = '', type: Callable[[str], Any] = str) -> Any` | Safely extract an XML attribute with type conversion. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
