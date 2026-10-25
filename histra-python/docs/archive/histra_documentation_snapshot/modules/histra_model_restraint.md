# `histra.model.restraint`

**Source:** `histra/model/restraint.py`  
**Size:** 25 lines  
**Layer:** Schema-oriented dataclasses and compatibility re-exports.

## Purpose

Defines support/restraint records and parses their constrained-node references and stiffness flags.

## Dependencies

**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `Restraint`

Class defined by `histra.model.restraint`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `key` | `int` | `0` |
| `name` | `str` | `''` |
| `node_c_keys` | `List[int]` | `field(default_factory=lambda: [0, 0])` |
| `k` | `List[float]` | `field(default_factory=lambda: [-1.0, -1.0, -1.0, -1.0, -1.0, -1.0])` |

**Methods**

| Method | Description |
|---|---|
| `def from_xml(elem) -> Restraint` | Constructs the object from an XML element. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
