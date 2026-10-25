# `histra.springs.base`

**Source:** `histra/springs/base.py`  
**Size:** 145 lines  
**Layer:** Constitutive spring laws and XML type dispatch.

## Purpose

Defines the base spring state contract, stiffness/force accessors, commit/revert lifecycle, diagonal-spring setup, and XML dispatch.

## Dependencies

**Internal:** `histra.types.afference_entry`, `histra.types.point`, `histra.types.xml_utils`  
**Python/third-party:** `dataclasses`, `math`, `typing`, `xml`  

## API and implementation units

### `Spring`

Base spring — used as fallback when *TypeOf* is unknown.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `type_of` | `str` | `''` |
| `extra` | `Dict[str, str]` | `field(default_factory=dict)` |
| `key` | `int` | `0` |
| `parent_key` | `int` | `0` |
| `parent_type` | `str` | `''` |
| `spring_purpose` | `str` | `''` |
| `type_name` | `str` | `''` |
| `area` | `float` | `0.0` |
| `length` | `float` | `0.0` |
| `k` | `float` | `0.0` |
| `k_tang` | `float` | `0.0` |
| `f` | `float` | `0.0` |
| `u` | `float` | `0.0` |
| `is_on` | `bool` | `True` |
| `phase` | `int` | `0` |
| `t_phase` | `int` | `0` |

**Methods**

| Method | Description |
|---|---|
| `def get_k(alfa: float = 0.0) -> float` | Returns the current/selected spring stiffness. |
| `def get_force() -> float` | Current spring force (C# ``Spring.GetForce()``). |
| `def get_incr_force() -> float` | Force increment since last commit (C# ``Spring.GetIncrForce()``). |
| `def get_displacement() -> float` | Current spring displacement (C# ``Spring.GetDisplacement()``). |
| `def set_trial_strain(strain: float) -> None` | Set the current trial strain ``u`` and update state. |
| `def revert_to_start() -> None` | Reset to initial (virgin) state (C# ``Spring.revertToStart()``). |
| `def revert_to_last_commit() -> None` | Revert trial state to last committed state (C# ``RevertToLastCommit()``). |
| `def commit() -> None` | Commit trial → committed (C# ``Spring.Commit()``). |
| `def set_quad_diagonal(k: float, fy: Tuple[float, float] \| None = None, mu: float = 0.0, eps_u: Tuple[float, float] \| None = None, plastic_stiffness_ratio: float = 0.0, reload_stiffness_ratio: float = 1.0, max_tensile_ratio: float = 0.0, plastic_stiffness_ratio2: float = 1.0, plastic_strain_ratio: float = 1.0, sub_law: str = 'Linear', is_ductility_fixed: bool = False, bcacovic: float = 0.0) -> None` | Set diagonal spring properties (C# ``Spring.SetQuadDiagonal``). |
| `def from_xml(elem: ET.Element) -> Spring` | Dispatch to the correct subclass based on *TypeOf*. |
| `def _from_xml(elem: ET.Element, type_of: str = '') -> Spring` | Construct instance (default implementation for base spring). |

## Runtime behavior

- Defines the constitutive lifecycle expected by elements: set trial strain, read force/tangent, commit, and revert.
- Unknown spring types fall back to the base spring, allowing parsing to continue but potentially reducing physical fidelity.

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
