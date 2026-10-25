# `histra.elements.interface`

**Source:** `histra/elements/interface.py`  
**Size:** 772 lines  
**Layer:** Runtime finite/discrete element implementations and their mutable state.

## Purpose

Implements the interface element: spring-grid geometry, local stiffness matrices, domain updates, resisting-force assembly, commit/revert, energy, and XML construction.

## Dependencies

**Internal:** `histra.elements.interface_state`, `histra.types.afference_entry`, `histra.types.point`  
**Python/third-party:** `dataclasses`, `math`, `numpy`, `typing`  

## API and implementation units

### `Interface`

Class defined by `histra.elements.interface`.

**Declared state fields (grouped)**

- Configuration/public: `key`, `node_keys`, `parent_element_key1`, `parent_element_key2`, `parent_type_element1`, `parent_type_element2`, `face1`, `face2`, `length`, `thickness`, `nrow`, `ncol`, `nspring`, `dim_aff`, `dim_aff_tot`, `trasv_1`, `trasv_2`, `slid`, `slid_out_plan`, `aff`, `reference_e1`, `reference_e2`, `reference_e3`, `reference_origin`, `status`, `name`, `material_key`, `layer_key`, `interfaccia_vincolata`, `frot`, `imax`, `csi`, `vint2d`, `vint3d`, `f`
- Committed/history: `csi`
- Trial/current: `thickness`, `trasv_1`, `trasv_2`

**Methods**

| Method | Description |
|---|---|
| `def interfaccia_vincolata_computed() -> bool` | Port of .NET InterfacciaVincolata(): True if either parent is a Restraint. |
| `def idx(row: int, col: int) -> int` | Port of Interface.idx(riga, colonna) = riga * Ncol + colonna. |
| `def get_di(row: int, index: int) -> float` | Port of Interface.Getdi(row, index). |
| `def get_dj(row: int, index: int) -> float` | Port of Interface.Getdj(row, index) = Length - Getdi(row, index). |
| `def get_dm(row: int, index: int) -> float` | Port of Interface.Getdm(row, index) = 0.5*Length - Getdi(row, index). |
| `def geometry_spring(row: int, index: int) -> Tuple[float, float, float]` | Port of Interface.GeometrySpring(row, index, di, dj, dm). |
| `def ecc_spring(row: int, index: int) -> float` | Port of Interface.EccSpring(row, index). |
| `def compute_dist_spring() -> Tuple[float, float]` | Compute distance distribution factors *di*, *dj*. |
| `def compute_dist_spring_for(intf: Interface) -> Tuple[float, float]` | Port of ``ComputeDistSpring(Interface I, ref double di, ref double dj)``. |
| `def _compute_di_from_geometry(intf: Interface) -> float` | Helper: compute *di* from plate theory (port of the else-branch). |
| `def compute_k(alfa: float = 0.0) -> None` | Port of Interface.ComputeK(double alfa). |
| `def _compute_kfless(alfa: float) -> None` | Port of ComputeKflessNoInteract (ComputeKfless for Ngroup == 1). |
| `def _compute_kslid(alfa: float) -> None` | Port of ComputeKslid — 2×2 in-plane sliding stiffness. |
| `def _compute_kslid_out_plan(alfa: float) -> None` | Port of ComputeKslidOutPlan → RotationalSpring branch (default). |
| `def update_domain(x: np.ndarray, state: Any) -> None` | Port of Interface.UpdateDomain(LinearSystem LS, IntegratorState state). |
| `def set_resisting_force() -> None` | Port of Interface.SetResistingForce(). |
| `def get_resisting_force(ls: Any) -> None` | Port of Interface.GetResistingForce(LinearSystem A). |
| `def commit(ls: Any = None) -> None` | Port of Interface.Commit(). |
| `def revert_to_last_commit(ls: Any) -> None` | Port of Interface.revertToLastCommit(LinearSystem LS). |
| `def max_u() -> float` | Maximum absolute spring displacement (port of a common pattern). |
| `def compute_energy() -> Tuple[float, float, float]` | Port of Interface.ComputeEnergy. |
| `def from_xml(elem) -> Interface` | Constructs the object from an XML element. |

## Runtime behavior

- Uses spring arrays for transverse, sliding, and out-of-plane behavior.
- Computes local stiffness blocks and scatters them through afference mappings during global assembly.
- Maintains separate trial/committed spring state and local force/energy quantities.

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
