# `histra.springs.registry`

**Source:** `histra/springs/registry.py`  
**Size:** 22 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Maps HRX `TypeOf` identifiers to spring subclasses and delegates XML construction.

## Dependencies

**Internal:** `histra.springs.base`  
**Python/third-party:** `typing`, `xml`  

## API and implementation units

### Module functions

| Function | Description |
|---|---|
| `def _register_spring(type_of: str)` | Decorator that registers a Spring subclass for a given *TypeOf* value. |
| `def spring_from_xml(elem: ET.Element) -> Spring` | Convenience wrapper — calls ``Spring.from_xml``. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
