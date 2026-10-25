# `histra.springs.coulomb`

**Source:** `histra/springs/coulomb.py`  
**Size:** 21 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Parses the original Coulomb friction spring parameters.

## Dependencies

**Internal:** `histra.springs.base`, `histra.springs.registry`  
**Python/third-party:** `dataclasses`  

## API and implementation units

### `SpringCoulomb`

Coulomb friction spring (original type).

**Bases:** `Spring`

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `mu` | `float` | `0.0` |
| `kt` | `float` | `0.0` |
| `kn` | `float` | `0.0` |

**Methods**

| Method | Description |
|---|---|
| `def _from_xml(elem: ET.Element, type_of: str = '') -> SpringCoulomb` | Subclass-specific XML constructor used by the registry/base factory. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
