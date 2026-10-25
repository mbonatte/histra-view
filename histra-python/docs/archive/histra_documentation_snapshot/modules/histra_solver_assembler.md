# `histra.solver.assembler`

**Source:** `histra/solver/assembler.py`  
**Size:** 598 lines  
**Layer:** Assembly, integration, equilibrium algorithms, convergence, and analysis orchestration.

## Purpose

Builds global sparse stiffness and load vectors, maps local DOFs through afference coefficients, applies boundary-condition reduction, and extracts displacements.

### Source docstring

Global stiffness matrix and load vector assembly.

Maps .NET HiStrA element assembly into COO / CSC format for scipy.

## Dependencies

**Internal:** `histra.model._types`, `histra.model.interface`, `histra.model.model`, `histra.model.quad`  
**Python/third-party:** `numpy`, `scipy`, `typing`  

## API and implementation units

### Module functions

| Function | Description |
|---|---|
| `def _intf_get_di(intf: Interface, row: int, index: int) -> float` | Port of Interface.Getdi(row, index): bilinear interpolation of vInt2D.X. |
| `def _intf_get_dj(intf: Interface, row: int, index: int) -> float` | Port of Interface.Getdj(row, index) = Length - Getdi(row, index). |
| `def _intf_get_dm(intf: Interface, row: int, index: int) -> float` | Port of Interface.Getdm(row, index) = 0.5*Length - Getdi(row, index). |
| `def _intf_ecc_spring(intf: Interface, row: int, index: int) -> float` | Port of Interface.EccSpring(row, index): bilinear interpolation of vInt2D.Y. |
| `def _compute_interface_kfless(intf: Interface, alfa: float = 0.0) -> List[List[float]]` | Build the 6×6 flexural stiffness matrix (port of ComputeKflessNoInteract). |
| `def _compute_interface_kslid(intf: Interface, alfa: float = 0.0) -> List[List[float]]` | 2×2 sliding stiffness (port of ComputeKslid). |
| `def _compute_interface_kslid_op(intf: Interface, alfa: float = 0.0) -> List[List[float]]` | 4×4 out-of-plane stiffness (port of ComputeKslidOutPlanRotationalSpring). |
| `def _assemble_afference(rows: list, cols: list, vals: list, n: int, aff_i: List[AfferenceEntry], aff_j: List[AfferenceEntry], k_ij: float)` | Scatter local stiffness k_ij through afference matrices into global COO. |
| `def assemble_global_k(model: Model, alfa: float = 0.0) -> sp.csc_matrix` | Assemble the global stiffness matrix K (CSC format). |
| `def get_restrained_dofs(model: Model, K: Optional[sp.csc_matrix] = None) -> Set[int]` | Identify DOF indices (0-based) that are fixed. |
| `def apply_boundary_conditions(K: sp.csc_matrix, b: np.ndarray, fixed_dofs: Set[int]) -> Tuple[sp.csc_matrix, np.ndarray]` | Eliminate fixed DOFs from the system (row/col deletion). |
| `def _get_comb_coeff_gravity(model: Model, analysis_key: int, combination: int) -> float` | Port of GetCombCoeffGravity: read gravity coefficient from load combination. |
| `def _resolve_coefficient(item: 'LoadCombinationItem', lc: 'LoadCondition') -> float` | Port of LoadTemplateManager.GetCoefficient for a single item + condition. |
| `def generate_self_weight_loads(model: Model, analysis_key: int, combination: int = 1)` | Port of GenerateLoadsForceAnalysis for self-weight only. |
| `def assemble_load_vector(model: Model, analysis_key: int \| None = None, combination: int = 1) -> np.ndarray` | Assemble the global load vector b. |
| `def extract_displacements(model: Model, results_path: 'str \| None' = None, analysis_key: int = 1, combination: int = 1, step: 'int \| None' = None) -> np.ndarray` | Extract the full displacement vector u from the model state. |

## Runtime behavior

- Collects element contributions into COO triplets and converts the result to CSC for sparse solves.
- Treats HRX `gdl` values as one-based and converts them to zero-based NumPy indices.
- Currently generates self-weight loads before scattering each quadrilateral local load vector.

## Known issues affecting this module

- **ISSUE-13 — Zero-diagonal DOFs are silently converted into restraints** (High). See [ISSUES.md](../ISSUES.md#issue-13).
- **ISSUE-14 — Psi load-combination coefficients are hard-coded to zero** (High). See [ISSUES.md](../ISSUES.md#issue-14).
- **ISSUE-24 — Load support is limited to self-weight while parsing suggests broader load-condition support** (High). See [ISSUES.md](../ISSUES.md#issue-24).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
