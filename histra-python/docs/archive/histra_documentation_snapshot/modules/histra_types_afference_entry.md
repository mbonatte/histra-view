# `histra.types.afference_entry`

**Source:** `histra/types/afference_entry.py`  
**Size:** 14 lines  
**Layer:** Shared numerical containers, enums, geometry, and state records.

## Purpose

Defines a local-to-global DOF mapping coefficient.

## Dependencies

**Python/third-party:** `dataclasses`  

## API and implementation units

### `AfferenceEntry`

Afference coefficient linking a local DOF to a global DOF.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `gdl` | `int` | `required/implicit` |
| `alfa` | `float` | `required/implicit` |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
