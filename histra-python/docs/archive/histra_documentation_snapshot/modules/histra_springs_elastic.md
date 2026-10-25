# `histra.springs.elastic`

**Source:** `histra/springs/elastic.py`  
**Size:** 14 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Implements a linear elastic spring parser using base-class force and stiffness behavior.

## Dependencies

**Internal:** `histra.springs.base`, `histra.springs.registry`  
**Python/third-party:** `dataclasses`, `xml`  

## API and implementation units

### `SpringElastic`

Linear elastic spring.

**Bases:** `Spring`

**Methods**

| Method | Description |
|---|---|
| `def _from_xml(elem: ET.Element, type_of: str = '') -> SpringElastic` | Subclass-specific XML constructor used by the registry/base factory. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
