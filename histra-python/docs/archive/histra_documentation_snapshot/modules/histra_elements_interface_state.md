# `histra.elements.interface_state`

**Source:** `histra/elements/interface_state.py`  
**Size:** 60 lines  
**Layer:** Runtime finite/discrete element implementations and their mutable state.

## Purpose

Stores the mutable local displacement, velocity, force, moment, and stiffness state of an interface element.

## Dependencies

**Python/third-party:** `dataclasses`, `numpy`, `typing`  

## API and implementation units

### `InterfaceState`

Port of Objects.InterfaceState (.NET).

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `u` | `List[float]` | `field(default_factory=lambda: [0.0] * 12)` |
| `v` | `List[float]` | `field(default_factory=lambda: [0.0] * 12)` |
| `fd` | `List[float]` | `field(default_factory=lambda: [0.0] * 12)` |
| `evd` | `float` | `0.0` |
| `forces` | `Tuple[float, float, float]` | `(0.0, 0.0, 0.0)` |
| `bending_moments` | `Tuple[float, float, float]` | `(0.0, 0.0, 0.0)` |
| `k` | `List[List[float]]` | `field(default_factory=lambda: _list2d(6, 6))` |
| `kslid` | `List[List[float]]` | `field(default_factory=lambda: _list2d(2, 2))` |
| `kslid_out_plan` | `List[List[float]]` | `field(default_factory=lambda: _list2d(4, 4))` |

**Methods**

| Method | Description |
|---|---|
| `def init_from_interface(intf: Interface) -> None` | Create/reshape the stiffness matrices to match *intf.dim_aff*. |
| `def compute_du(intf: Interface, x: np.ndarray, i: int) -> float` | Return Σ x[gdl-1] · alfa over the afference entries of DOF *i*. |

### Module functions

| Function | Description |
|---|---|
| `def _list2d(rows: int, cols: int) -> List[List[float]]` | Create a rows×cols zero-initialised 2-D list. |

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
