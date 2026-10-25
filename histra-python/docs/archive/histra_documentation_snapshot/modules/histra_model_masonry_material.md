# `histra.model.masonry_material`

**Source:** `histra/model/masonry_material.py`  
**Size:** 21 lines  
**Layer:** Schema-oriented dataclasses and compatibility re-exports.

## Purpose

Defines masonry material properties used by element load and stiffness calculations.

## Dependencies

**Python/third-party:** `dataclasses`  

## API and implementation units

### `MasonryMaterial`

Class defined by `histra.model.masonry_material`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `key` | `int` | `0` |
| `name` | `str` | `''` |
| `w` | `float` | `0.0` |
| `E_min` | `float` | `0.0` |
| `E_med` | `float` | `0.0` |
| `E_max` | `float` | `0.0` |
| `G_min` | `float` | `0.0` |
| `G_med` | `float` | `0.0` |
| `G_max` | `float` | `0.0` |
| `fm_min` | `float` | `0.0` |
| `fm_med` | `float` | `0.0` |
| `fm_max` | `float` | `0.0` |
| `fvk0_min` | `float` | `0.0` |
| `fvk0_med` | `float` | `0.0` |
| `fvk0_max` | `float` | `0.0` |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
