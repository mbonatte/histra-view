# `histra.springs.multilinear`

**Source:** `histra/springs/multilinear.py`  
**Size:** 26 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Parses a piecewise force-deformation spring definition.

## Dependencies

**Internal:** `histra.springs.base`, `histra.springs.registry`  
**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `SpringMultiLinear`

Multi-linear spring.

**Bases:** `Spring`

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `deformations` | `str` | `''` |
| `forces` | `str` | `''` |

**Methods**

| Method | Description |
|---|---|
| `def _from_xml(elem: ET.Element, type_of: str = '') -> SpringMultiLinear` | Subclass-specific XML constructor used by the registry/base factory. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
