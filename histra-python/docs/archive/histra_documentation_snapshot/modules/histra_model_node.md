# `histra.model.node`

**Source:** `histra/model/node.py`  
**Size:** 74 lines  
**Layer:** Schema-oriented dataclasses and compatibility re-exports.

## Purpose

Defines geometric nodes, constrained nodes (`NodeC`), and master/slave relationships.

## Dependencies

**Internal:** `._types`  
**Python/third-party:** `dataclasses`, `typing`  

## API and implementation units

### `Node`

Class defined by `histra.model.node`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `key` | `int` | `0` |
| `point` | `Point` | `field(default_factory=Point)` |
| `name` | `str` | `''` |

**Methods**

| Method | Description |
|---|---|
| `def from_xml(elem) -> Node` | Constructs the object from an XML element. |

### `SlaveElement`

Class defined by `histra.model.node`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `slave_key` | `int` | `0` |
| `slave_type` | `str` | `''` |

### `NodeC`

Class defined by `histra.model.node`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `key` | `int` | `0` |
| `node_key` | `int` | `0` |
| `name` | `str` | `''` |
| `master_element_key` | `int` | `0` |
| `master_element_type` | `str` | `''` |
| `slave_elements` | `List[SlaveElement]` | `field(default_factory=list)` |
| `u` | `List[float]` | `field(default_factory=lambda: [0.0] * 6)` |
| `p` | `List[float]` | `field(default_factory=lambda: [0.0] * 6)` |

**Methods**

| Method | Description |
|---|---|
| `def master_elements() -> List[SlaveElement]` | Master elements. |
| `def master_elements(val: List[SlaveElement]) -> None` | Master elements. |
| `def from_xml(elem) -> NodeC` | Constructs the object from an XML element. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
