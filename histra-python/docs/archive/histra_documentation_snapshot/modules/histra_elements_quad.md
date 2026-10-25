# `histra.elements.quad`

**Source:** `histra/elements/quad.py`  
**Size:** 719 lines  
**Layer:** Runtime finite/discrete element implementations and their mutable state.

## Purpose

Implements the quadrilateral masonry macro-element, including load distribution, diagonal spring behavior, stiffness, resisting forces, state updates, energy, and XML construction.

## Dependencies

**Internal:** `histra.elements.quad_state`, `histra.springs.base`, `histra.types.afference_entry`, `histra.types.point`  
**Python/third-party:** `dataclasses`, `math`, `typing`  

## API and implementation units

### `Quad`

Class defined by `histra.elements.quad`.

**Declared state fields**

| Field | Type | Default |
|---|---|---|
| `key` | `int` | `0` |
| `node_keys` | `List[int]` | `field(default_factory=lambda: [0, 0, 0, 0])` |
| `length` | `List[float]` | `field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])` |
| `sin` | `List[float]` | `field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])` |
| `cos` | `List[float]` | `field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])` |
| `diago` | `List[float]` | `field(default_factory=lambda: [0.0, 0.0])` |
| `thickness` | `List[float]` | `field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])` |
| `normal` | `List[Point]` | `field(default_factory=lambda: [Point(), Point(), Point(), Point()])` |
| `g` | `Point` | `field(default_factory=Point)` |
| `material_key` | `int` | `0` |
| `aff` | `List[List[AfferenceEntry]]` | `field(default_factory=lambda: [[] for _ in range(7)])` |
| `interface_keys` | `List[List[int]]` | `field(default_factory=lambda: [[] for _ in range(6)])` |
| `reference_e1` | `Tuple[float, float, float]` | `(1.0, 0.0, 0.0)` |
| `reference_e2` | `Tuple[float, float, float]` | `(0.0, 1.0, 0.0)` |
| `reference_e3` | `Tuple[float, float, float]` | `(0.0, 0.0, 1.0)` |
| `reference_origin` | `Point` | `field(default_factory=Point)` |
| `status` | `QuadState` | `field(default_factory=QuadState)` |
| `name` | `str` | `''` |
| `extra` | `Dict[str, str]` | `field(default_factory=dict)` |
| `parent_key` | `int` | `0` |
| `parent_type` | `str` | `''` |
| `material_key` | `int` | `0` |
| `layer_key` | `int` | `0` |
| `master_element_key` | `int` | `0` |
| `master_element_type` | `str` | `''` |

**Methods**

| Method | Description |
|---|---|
| `def springs() -> List[Spring]` | Springs. |
| `def springs(val: List[Spring]) -> None` | Springs. |
| `def compute_static_load_internal(node_coords: List[Point], nodal_forces: List[Tuple[float, float, float]]) -> List[float]` | 2×2 Gauss integration of load distribution → P[0..6]. |
| `def compute_self_weight_load(dir_x: float, dir_y: float, dir_z: float, w: float) -> List[Tuple[float, float, float]]` | Compute nodal forces for self-weight: F[i] = thickness[i] * w * dir |
| `def d_alfa_2d_diag() -> float` | Kinematic factor from 7th DOF (warping amplitude) to diagonal spring strain. |
| `def d_diag_2d_alfa() -> float` | Inverse of :meth:`d_alfa_2d_diag`. |
| `def compute_k(alfa: float = 0.0) -> float` | Diagonal (7th DOF) stiffness. |
| `def get_diagonal_stiffness(E: float, G: float) -> float` | Full in-plane stiffness projected onto the diagonal (7th) DOF. |
| `def set_non_linear_properties(k: float, E: float, G: float, Fyt: float, Fyc: float) -> Tuple[float, float]` | Compute nonlinear yield forces in tension and compression. |
| `def set_resisting_force() -> None` | Compute internal force F[0] from the diagonal spring. |
| `def get_resisting_force(gdl_map: List[int], alfa_map: List[float], b: List[float]) -> None` | Distribute the diagonal spring resisting force into global vector b. |
| `def update_domain(x, state) -> None` | Port of ``Quad.UpdateDomain``. |
| `def commit(_ls = None) -> None` | Port of ``Quad.Commit``. |
| `def revert_to_last_commit(ls) -> None` | Port of ``Quad.revertToLastCommit``. |
| `def max_u() -> float` | Port of ``Quad.MaxU``. |
| `def _warping_coeffs(quad: Quad) -> List[float]` | Compute the warping displacement vector a[0..3] (C# array2). |
| `def compute_energy() -> Tuple[float, float, float]` | Port of Quad.ComputeEnergy — delegates to the spring. |
| `def from_xml(elem) -> Quad` | Constructs the object from an XML element. |

## Runtime behavior

- Afference lists map each local element coordinate to one or more global DOFs with scaling coefficients.
- The diagonal nonlinear spring supplies the principal nonlinear resisting force and tangent behavior.
- The element maintains trial state during Newton iterations and commits or reverts it at step boundaries.

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
