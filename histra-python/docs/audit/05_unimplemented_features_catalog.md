# Chapter 05: Exhaustive Catalog of Unimplemented C# HiStrA Features, Algorithms, and Models

## High-Fidelity Comparative Parity Audit, Boundary Preflight Enforcement, and Strategic Porting Pathways

---

## 1. Executive Overview & Scope Definition

### 1.1 Background, Context, and Architectural Focus
The original C# HiStrA software suite (developed by SirioSoft and the University of Catania) is a comprehensive, multi-purpose structural engineering analysis platform built upon the .NET Framework 4.8. Over two decades of development, C# HiStrA accumulated a vast inventory of structural modeling capabilities spanning discrete macro-elements, 3D continuum finite elements, Timoshenko frame beam-columns, DKT shell slabs, parametric CAD meshing wizards, dynamic time-history solvers, and national regulatory code assessment procedures.

The `histra-python` project is an in-process, headless Python implementation of the **Discrete Macro-Element Method (DMEM)** specifically optimized for the static nonlinear and modal assessment of historical masonry structures (buildings and arch bridges). The core development philosophy of `histra-python` is governed by strict non-negotiable invariants:
1. **Numerical Accuracy & C# Parity Over Raw Velocity**: Numerical parity against C# `.Results` SQLite benchmarks is paramount ($< 10^{-10}\\text{ mm}$ displacement parity). No optimization or simplification that alters numerical results, alters contact branch selection, or weakens equilibrium checks is accepted.
2. **Compiled Numba Backend Coverage**: In production numerical steps, 100% of element and spring evaluations are executed via compiled Numba vectorized kernels (`hysteretic_kernels/`) operating on flat, contiguous NumPy arrays, completely eliminating object-oriented traversal overhead.
3. **Fresh Model Preparation Boundary**: Serialized interfaces in legacy `.hrx` files are treated as historical snapshots. Python always regenerates interface contact geometry, fiber discretization, and spring parameters freshly from raw polygon geometry (`ModelManager.prepare_model(model, force=True)`).

Because `histra-python` V1 deliberately focuses on the masonry Quad and Interface substructure, approximately 58% of the source files in the C# numerical core remain **unimplemented**. These omitted capabilities do not represent missing bugs or incomplete ports; rather, they represent intentional architectural boundaries separating the stable V1 discrete macro-element masonry engine from non-masonry, continuum, transient dynamic, and desktop CAD features.

This document provides the exhaustive, authoritative catalog of every unported feature, algorithm, element type, material model, load distribution generator, and analysis option present in C# HiStrA.

---

### 1.2 Core Inventory Statistics & Classification Breakdown

An exhaustive file-by-file audit of the **426 unique source files** constituting the C# numerical and modeling core (`SolverRuntime`, `MatrixManager`, `SectionBuilderCore`, `AdapticIO`, `ModelLibrary`, `ModelManagement`, and `Objects`) reveals the following distribution:

| Classification | Unique C# Files | Percentage | Subsystem Distribution & Description |
|---|---|---|---|
| **Ported** | 131 | 30.8% | DMEM Quad, Interface, Spring models (Coulomb03, Hysteretic, Elastic, MultiLinear), Newton-Raphson, Arc-Length, Line Searches, Subspace Modal, Linear System / UMFPACK bindings, HRX loader, SQLite reader. |
| **Partial** | 15 | 3.5% | Partial implementations where data models or serialization formats are parsed (e.g., Pushover analysis metadata, database table schemas, model properties), while unneeded methods or desktop GUI hooks are omitted. |
| **Intentional Deviation** | 4 | 0.9% | Architectural redesigns to fix documented C# bugs or enhance performance (e.g., in-memory state snapshots replacing deep XML cloning, independent equilibrium safety audit to detect deceptive `Work` convergence, vectorization of spring evaluation). |
| **Unimplemented** | 248 | 58.2% | Features outside the V1 DMEM masonry boundary: 12 Element types, 7 Material classes, 10 specialized spring models, transient dynamic solvers, code-based response spectra, adaptive pushover generators, and CAD meshing wizards. |
| **Out-of-Scope** | 28 | 6.6% | .NET project metadata (`AssemblyInfo.cs`), desktop WPF/WinForms controls, CAD renderers, and Excel COM automation located inside core folders. |
| **Total C# Core Files** | **426** | **100.0%** | **Exhaustive core inventory audited** |

```
                               C# CORE FILE DISTRIBUTION (426 Unique Files)
   ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
   │ [Ported: 131 files (30.8%)]  │ [Partial: 15] │ [Dev: 4] │ [Unimplemented: 248 (58.2%)] │ [Out-of-Scope: 28] │
   └─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
   ▲                              ▲               ▲           ▲                              ▲
   DMEM Masonry Core              HRX Subsets     Safety/Perf Unported Capabilities          Desktop / .NET Meta
```

---

### 1.3 The Python Fail-Closed Preflight Architecture

A critical architectural achievement of `histra-python` is its **fail-closed preflight validation boundary**. Rather than failing silently, producing corrupted results, or falling back to unmanaged scalar Python loops when encountering unsupported features, `histra-python` intercepts and rejects unsupported models before any numerical computation begins.

This boundary is enforced by a three-tiered defense:

```
                                PYTHON PREFLIGHT DEFENSE LAYERS
 
    1. HRX Ingestion (histra.io.hr_loader)
       │ • Scans XML tags against _UNSUPPORTED_V1_ELEMENT_TAGS
       │ • Records unsupported elements in model.unsupported_v1_features["element:<Tag>"]
       │ • Inspects material templates and captures non-masonry materials in model.unsupported_material_templates
       ▼
    2. Capability Preflight (histra.solver.capabilities)
       │ • inspect_solver_capabilities() audits model geometry, materials, analyses, and output requests
       │ • Verifies element scope (V1_ELEMENT_DOMAIN_UNSUPPORTED)
       │ • Verifies material assignments (V1_MATERIAL_DOMAIN_UNSUPPORTED)
       │ • Verifies analysis types (DYNAMIC_ANALYSIS_UNSUPPORTED)
       │ • Verifies static load distributions (STATIC_LOAD_DISTRIBUTION_UNSUPPORTED)
       │ • Verifies static integrators (STATIC_INTEGRATOR_UNSUPPORTED)
       │ • Verifies nonlinear equilibrium methods (NONLINEAR_METHOD_UNSUPPORTED)
       │ • Halts execution via require_supported() raising UnsupportedSolverCapability
       ▼
    3. Production Backend Coverage Guard (histra.solver.backend_coverage)
       │ • inspect_solver_backend_coverage() validates runtime domain arrays
       │ • Requires 100% of Quads and Interfaces to be managed by compiled Numba kernels
       │ • Fails closed with RuntimeError if any unmanaged Python object loop is detected
```

#### Layer 1: Ingestion Tag Interception (`histra/io/hr_loader.py`)
During HRX deserialization, the XML parser maintains explicit sets of unsupported computational elements and material definitions:
```python
_UNSUPPORTED_V1_ELEMENT_TAGS = frozenset({
    "Frame", "Slab", "Link", "Joint", "Solid", "Fiber", "Truss", "Vertex", "InterfaceMF", "NodeBC"
})
```
When encountering these tags, `_record_unsupported(model, "element", tag)` records the occurrence in `model.unsupported_v1_features`. Similarly, material templates whose `PurposeType` is not `MasonryMaterial` (such as `ConcreteMaterial`, `SteelMaterial`, `FiberMaterial`, `GeotecnicalMaterial`) are registered in `model.unsupported_material_templates`.

#### Layer 2: Capability Preflight Audit (`histra/solver/capabilities.py`)
Before `ModelManager.prepare_model` or solver execution, `inspect_solver_capabilities(model, analysis_names, output_requests)` performs an exhaustive inspection:
- **Element Domain**: If `unsupported_v1_features` contains any non-quad/interface elements, it emits issue code `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Material Domain**: If any Quad or Interface references a material in `unsupported_material_templates`, it emits issue code `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Analysis Types**: If `analysis_type` is 3 or 4 (Dynamic linear/nonlinear), it emits `DYNAMIC_ANALYSIS_UNSUPPORTED`. If not 2 (Static nonlinear) or 5 (Modal), it emits `ANALYSIS_TYPE_UNSUPPORTED`.
- **Pushover Load Distributions**: If `type_load_distribution` is `Modal`, `Triangular`, `Adaptive`, or `ShearFloor`, it emits `STATIC_LOAD_DISTRIBUTION_UNSUPPORTED`.
- **Static Integrators**: If `integration_method` is not in `{"LoadControl", "ArcLength", "ArcLengthLinear"}`, it emits `STATIC_INTEGRATOR_UNSUPPORTED`.
- **Solution Methods**: If `method` is not one of the 10 supported Newton / Line Search combinations, it emits `NONLINEAR_METHOD_UNSUPPORTED`.
- **Modal Requests**: If response-spectrum modal contribution projection is requested, it emits `MODAL_CONTRIBUTION_OUTPUT_UNSUPPORTED`.

Calling `report.require_supported()` aggregates all detected violations into a clean, semicolon-delimited error message and raises `UnsupportedSolverCapability`.

#### Layer 3: Compiled Backend Enforcement (`histra/solver/backend_coverage.py`)
Even if a model passes capability preflight, `require_compiled_backend(model)` ensures that 100% of Quads and Interfaces are executed via compiled Numba batch kernels. If any element lacks vector indices or relies on legacy scalar Python loops, the solver immediately aborts.

---

### 1.4 Master Taxonomy of Unimplemented Capabilities

The table below summarizes all unported capabilities across the five functional domains, indicating the number of affected C# source files, the Python preflight error code, and the strategic porting complexity:

| Functional Domain | Key Capabilities & Formulations | C# Core Files | Python Preflight Guard Code | Porting Complexity |
|---|---|---|---|---|
| **Domain 1: Computational Elements** | Frame (Timoshenko 3D beam), Slab (DKT shell/plate), Solid (8-node hexahedron), Truss (axial tie), Vertex (3D corner macro-node), InterfaceMF (macro-frame line contact), InterfacePoligonal (3D polygonal contact), NodeBC (generalized boundary node), Link & Joint (kinematic/rotational connections), InternalConstraint (rigid diaphragm MPC), Curved Vault meshers. | 54 files | `V1_ELEMENT_DOMAIN_UNSUPPORTED` | **High to Very High** |
| **Domain 2: Materials & Springs** | ConcreteMaterial (Kent-Park, Mander), SteelMaterial (Menegotto-Pinto), FiberMaterial (FRP/TRM delamination), ConcreteMultiLinearPlasticMaterial, ElasticIsotropicMaterial (3D continuum), GeotechnicalMaterial (soil reaction $p-y$), MomentCurvature ($M-\\chi$ hinges), 10 specialized cyclic spring models (SpringConcrete01/02/04/07, SpringSteel01/02, SpringEndochronic, SpringStok, SpringArmFried, SpringElastoPlastic). | 35 files | `V1_MATERIAL_DOMAIN_UNSUPPORTED` | **Medium to High** |
| **Domain 3: Load Generators & BCs** | Pushover lateral load distributions (Modal multi-mode projection, Inverted Triangular acceleration, Adaptive tangent-mode updating, ShearFloor mass distribution), Non-rigid restraint impedance refresh ($K_x, K_y, K_z$), Moving vehicle train load patterns (`VehicleLoadElement`, `Corsia`), 3D vault filling pressure distributions. | 22 files | `STATIC_LOAD_DISTRIBUTION_UNSUPPORTED` | **Low to Medium** |
| **Domain 4: Analysis Procedures & Solvers** | Dynamic nonlinear time-history integration (`DynamicNonLinearAnalysis`, `TransientIntegrator`), Implicit dynamic integrators (Newmark-$\\beta$, Hilber-Hughes-Taylor HHT-$\\alpha$, Wilson-$\\theta$), Ground motion accelerograms, Rayleigh/Caughey damping, Eurocode 8 / NTC2008/NTC2018 Method A/B response spectra, Complex eigenvalue solvers, Alternative Quasi-Newton solvers (Krylov, Broyden, BFGS). | 28 files | `DYNAMIC_ANALYSIS_UNSUPPORTED`, `STATIC_INTEGRATOR_UNSUPPORTED`, `NONLINEAR_METHOD_UNSUPPORTED` | **High** |
| **Domain 5: Post-Processing & Special Tools** | Adaptic solver IO translator (`InputManager`, `OutputManager`), SectionBuilder 2D cross-section fiber mesher (Triangle.NET Delaunay meshing, geometric inertia moments, fiber coordinate mapping), Seismic vulnerability assessment indices (Method A / Method B risk index $\\zeta_E$, N2 method, capacity spectrum evaluation), Enterprise SQL Server DB, AutoCAD DXF / Abaqus INP converters. | 109 files | Preflight exclusion & external boundaries | **Medium to High** |

---

## 2. Domain 1: Computational Elements & Structural Connectors

### 2.1 Overview of Unimplemented Elements
In C# HiStrA, discrete macro-element Quads and Interfaces operate alongside a rich ecosystem of structural finite elements, connection links, and 3D continuum bodies. In `histra-python` V1, the element domain is strictly confined to 2D quadrilateral masonry panels (`Quad`) and 12-DOF distributed contact joints (`Interface`).

The table below catalogs the 12 unported element classes, their file locations, degrees of freedom, and primary physical roles:

| Element Type | Primary C# Source Files | Key Classes & DOFs | Physical Role & Structural Mechanics |
|---|---|---|---|
| **Frame** | `Objects/Frame.cs`<br>`ModelLibrary.ComputationalElements/FrameDB.cs`<br>`FramesSDB.cs`<br>`FrameInteract.cs`<br>`ModelManagement/FrameOperations.cs` | `Frame`, `GeometryFrame`, `FrameState`, `FrameSegment`<br>**12 DOFs** (2 nodes $\\times$ 6 DOFs) | 3D Timoshenko / Euler-Bernoulli beam-column element with distributed fiber sections. Models RC beams/columns, steel frames, timber rafters, and masonry ring beams. |
| **Slab** | `Objects.ComputationalElements/Slab.cs`<br>`Objects.ComputationalElements/SlabEdge.cs`<br>`Objects/GeometrySlab.cs`<br>`ModelManagement/SlabOperations.cs` | `Slab`, `SlabEdge`, `SlabState`, `GeometrySlab`<br>**24 DOFs** (4 nodes $\\times$ 6 DOFs) | 4-node 3D flat shell element combining in-plane membrane action with Discrete Kirchhoff Theory (DKT) plate bending. Models floor diaphragms and composite decks. |
| **Solid** | `Objects/Solid.cs`<br>`Objects.ElementStates/SolidState.cs`<br>`Objects/SolidNodeKeysInfDBclass.cs`<br>`ModelManagement/SolidOperations.cs` | `Solid`, `SolidState`<br>**24 DOFs** (8 nodes $\\times$ 3 DOFs) | 8-node 3D continuum hexahedral (brick) macro-element with $2 \\times 2 \\times 2$ Gauss quadrature and 3D Mohr-Coulomb/Drucker-Prager plasticity. Models bridge piers, abutments, and soil blocks. |
| **Truss** | `Objects/Truss.cs`<br>`Objects.ElementStates/TrussState.cs`<br>`ModelManagement/TrussOperations.cs` | `Truss`, `TrussState`<br>**6 DOFs** (2 nodes $\\times$ 3 DOFs) | 2-node 3D uniaxial tension/compression member. Models iron tie-rods (*catene*), cables, post-tensioned tendons, and diagonal bracing struts. |
| **Vertex** | `Objects/Vertex.cs`<br>`Objects.ElementStates/VertexState.cs`<br>`ModelManagement/VertexOperations.cs` | `Vertex`, `VertexState`<br>**6 DOFs** (Centroidal) | 3D macro-element node representing 3D wall intersections, corners, vertical piers, and multi-wall junctions, generating 3D kinematic afference mapping. |
| **InterfaceMF** | `Objects/InterfaceMF.cs`<br>`Objects/InterfaceStateMF.cs`<br>`ModelManagement/InterfaceMFOperations.cs` | `InterfaceMF`, `InterfaceStateMF`<br>Multi-spring line contact | Specialized Macro-Frame Interface connecting 2D masonry Quad panel edges to 1D Frame beam-column elements for infilled frames and perimeter ties. |
| **InterfacePoligonal** | `Objects/InterfacePoligonal.cs`<br>`ModelManagement/InterfacePoligonalOperations.cs` | `InterfacePoligonal`<br>3D surface contact | 3D general polygonal contact interface between 3D Solid elements or non-rectangular surfaces with Delaunay surface triangulation. |
| **NodeBC** | `Objects/NodeBC.cs`<br>`Objects.ElementStates/NodeBCState.cs`<br>`ModelManagement/NodeCOperations.cs` | `NodeBC`, `NodeBCState`<br>**6 DOFs** | Generalized Boundary Condition node supporting translational/rotational elastic foundation impedance springs, multipoint master-slave links, and enforced displacements. |
| **Link** | `Objects.ComputationalElements/Link.cs`<br>`ModelManagement/LinkOperations.cs` | `Link`<br>**12 DOFs** (2 nodes $\\times$ 6 DOFs) | Kinematic connection element imposing rigid or flexible relative displacement constraints between two arbitrary structural nodes (rigid links, gap/expansion joints). |
| **Joint** | `Objects.ComputationalElements/Joint.cs`<br>`ModelManagement/JointOperations.cs` | `Joint`<br>**6 DOFs** relative | Discrete nonlinear rotational/shear connection joint positioned at frame intersections or frame-to-wall interfaces for semi-rigid connections and moment releases. |
| **InternalConstraint** | `Objects.ComputationalElements/InternalConstraint.cs`<br>`PConstraint.cs`<br>`ModelManagement/PConstraintOperations.cs` | `InternalConstraint`, `PConstraint`<br>Multipoint MPC | Multipoint kinematic constraints (MPC) enforcing rigid diaphragm planar constraints and tied degrees of freedom across arbitrary node groups. |
| **Curved Vault Elements** | `Objects/Arch.cs`, `BarrelVault.cs`, `CloisterVault.cs`, `CrossVault.cs`, `Dome.cs`, `DomicalVault.cs`, `Drum.cs`, `Pendentive.cs`, `SpecchioVault.cs`, `Abside.cs` | Parametric geometry generators & meshers | Differential geometry generators and CAD meshers discretizing 3D historical curved vaults, arches, and domes into discrete macro-element Quads and Interfaces. |

---

### 2.2 Granular Element Formulations & Audit Details

#### 2.2.1 Frame Element
- **C# Source Location**: `C#_Original/Objects/Frame.cs` (90,359 bytes, 4,044 lines), `ModelLibrary.ComputationalElements/FrameDB.cs`, `FrameInteract.cs`, `FrameSegment.cs`, `ModelManagement.ComputationalElementsOperations/FrameOperations.cs`.
- **C# Classes & Interfaces**: `class Frame : ComputationalElement`, `class GeometryFrame`, `class FrameState : BaseObjectStateDBclass`, `class FrameSegment`, `enum FrameTypeEnum { Beam, Column, Tie, RingBeam }`, `enum TypeBeamEnum { Elastic, SDB, SDBH }`.
- **Physical Formulation & Mechanics**:
  - The `Frame` element is a 3D, two-node beam-column member formulated under both Euler-Bernoulli (slender members) and Timoshenko beam theory (shear deformable beams, `TypeBeamEnum.SDB`).
  - Each node possesses 6 degrees of freedom, producing a 12-element element displacement vector:
    $$\\mathbf{u}_e = [u_{x1}, u_{y1}, u_{z1}, \\theta_{x1}, \\theta_{y1}, \\theta_{z1}, u_{x2}, u_{y2}, u_{z2}, \\theta_{x2}, \\theta_{y2}, \\theta_{z2}]^T$$
  - Kinematic transformation from local to global coordinates uses a $12 \\times 12$ block-diagonal rotation matrix $\\mathbf{T}_{12 \\times 12}$ determined by the longitudinal centroidal axis and the local cross-section orientation angle `_localAxesAngle`:
    $$\\mathbf{K}_{e,\\text{global}} = \\mathbf{T}^T \\mathbf{K}_{e,\\text{local}} \\mathbf{T}$$
  - Cross-section distributed plasticity is captured by dividing the element into $N$ longitudinal control segments (`_nSections`, typically 5 to 9 Gauss-Lobatto integration stations), each referenced to a fiber cross-section (`_SectionKeys`).
  - Axial force and biaxial bending coupling ($P-M_y-M_z$) are evaluated through cross-section fiber strain integration:
    $$\\varepsilon(y, z) = \\varepsilon_0 + \\kappa_y z - \\kappa_z y$$
    $$\\sigma(y, z) = f(\\varepsilon(y, z)), \\quad N = \\int_A \\sigma \\, dA, \\quad M_y = \\int_A \\sigma z \\, dA, \\quad M_z = -\\int_A \\sigma y \\, dA$$
  - Geometric nonlinearities (P-$\\Delta$ effects) are incorporated via the geometric stiffness matrix $\\mathbf{K}_G(N)$ updated at each Newton iteration when `PdeltaEffect` is active.
- **Role in C# Solver**:
  - Models mixed historical and modern structural systems: reinforced concrete frames, masonry buildings with RC tie beams / ring beams (*cordoli*), wooden roof trusses, timber floor joists, and iron tie-rods.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:54` intercepts the `<Frame>` XML tag and calls `_record_unsupported(model, "element", "Frame")`.
  - `histra/solver/capabilities.py:179-185` inspects `model.unsupported_v1_features` during preflight and halts execution:
    ```python
    SolverCapabilityIssue("V1_ELEMENT_DOMAIN_UNSUPPORTED", 
        f"HRX contains {count} Frame object(s); Frame is outside the V1 Quad/Interface masonry domain.")
    ```
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: 3D frame kinematics, 6-DOF nodal transformations, fiber cross-section integration engine (SectionBuilder), and geometric stiffness $\\mathbf{K}_G$.
  - **Porting Pathway**: Phase 2 implementation introducing `histra/elements/frame.py`, fiber state arrays, and coupled frame-to-quad stiffness assembly.

---

#### 2.2.2 Slab Element
- **C# Source Location**: `C#_Original/Objects.ComputationalElements/Slab.cs` (92,878 bytes, 3,472 lines), `Objects.ComputationalElements/SlabEdge.cs`, `Objects.ElementStates/SlabState.cs`, `Objects/GeometrySlab.cs`, `ModelManagement.ComputationalElementsOperations/SlabOperations.cs`.
- **C# Classes & Interfaces**: `class Slab : ComputationalElement`, `class SlabEdge`, `class SlabState : BaseObjectStateDBclass`, `class GeometrySlab`.
- **Physical Formulation & Mechanics**:
  - The `Slab` element is a 4-node 3D flat shell element with 24 global degrees of freedom (6 DOFs per corner node: 3 translations and 3 rotations).
  - The element formulation superimposes:
    1. **In-Plane Membrane Action**: 4-node bilinear isoparametric plane stress formulation capturing in-plane extensional stiffness ($E_x, E_y$) and shear stiffness ($G_{xy}$). Supports orthotropic material properties representing one-way timber floors or hollow-core concrete slabs (*laterocemento*).
    2. **Out-of-Plane Plate Bending**: Discrete Kirchhoff Theory (DKT) quadrilateral bending element, derived from four sub-triangles (DKQ), enforcing zero transverse shear strain at discrete boundary collocation points:
       $$\\gamma_{xz} = \\frac{\\partial w}{\\partial x} + \\beta_x = 0, \\quad \\gamma_{yz} = \\frac{\\partial w}{\\partial y} + \\beta_y = 0$$
  - Slab edges (`SlabEdge`) formulate kinematic edge-coupling constraints linking slab perimeter displacements directly to underlying masonry wall quads or supporting frame beams.
  - Floor vertical gravity loads (self-weight, permanent dead loads, live loads) are automatically integrated over the slab polygon and apportioned to supporting boundary edges according to tributary areas or yield-line fracture patterns.
- **Role in C# Solver**:
  - Models floor diaphragms (rigid, semi-rigid, or flexible timber floors), vaults approximated as faceted plates, and reinforced concrete floor decks. Enforces horizontal diaphragm action distributing seismic inertia forces across lateral-resisting masonry walls.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:55` records `element:Slab`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED` and rejects the model.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: DKQ/DKT plate bending stiffness integration, membrane-bending transformation into 3D space, and edge-to-quad kinematic tying.
  - **Porting Pathway**: Phase 4 implementation for comprehensive 3D building floor diaphragm modeling.

---

#### 2.2.3 Solid Continuum Element
- **C# Source Location**: `C#_Original/Objects/Solid.cs` (30,648 bytes, 1,291 lines), `Objects.ElementStates/SolidState.cs`, `Objects/SolidNodeKeysInfDBclass.cs`, `Objects/SolidNodeKeysSupDBclass.cs`, `ModelManagement.ComputationalElementsOperations/SolidOperations.cs`.
- **C# Classes & Interfaces**: `class Solid : ComputationalElement`, `class SolidState : BaseObjectStateDBclass`, `class SolidNodeKeysInfDBclass`.
- **Physical Formulation & Mechanics**:
  - The `Solid` element is an 8-node 3D continuum hexahedral (brick) macro-element possessing 24 translational degrees of freedom (8 nodes $\\times$ 3 translations: $u_x, u_y, u_z$).
  - Kinematics are governed by standard 3D trilinear isoparametric shape functions in intrinsic coordinates $(\\xi, \\eta, \\zeta) \\in [-1, 1]^3$:
    $$N_i(\\xi, \\eta, \\zeta) = \\frac{1}{8} (1 + \\xi_i \\xi)(1 + \\eta_i \\eta)(1 + \\zeta_i \\zeta)$$
  - Strain-displacement matrix $\\mathbf{B}_{6 \\times 24}(\\xi, \\eta, \\zeta)$ evaluates the 6-component 3D strain tensor $\\boldsymbol{\\varepsilon} = [\\varepsilon_{xx}, \\varepsilon_{yy}, \\varepsilon_{zz}, \\gamma_{xy}, \\gamma_{yz}, \\gamma_{zx}]^T$.
  - Stiffness integration uses $2 \\times 2 \\times 2$ (8-point) Gauss-Legendre quadrature:
    $$\\mathbf{K}_e = \\int_{-1}^1 \\int_{-1}^1 \\int_{-1}^1 \\mathbf{B}^T \\mathbf{D} \\mathbf{B} \\det(\\mathbf{J}) \\, d\\xi \\, d\\eta \\, d\\zeta$$
  - Constitutive modeling encompasses 3D isotropic elasticity (`ElasticIsotropicMaterial`), 3D Drucker-Prager plasticity, and 3D Mohr-Coulomb yield criteria with a non-associated plastic potential function to control volumetric dilatancy.
- **Role in C# Solver**:
  - Models massive masonry structures: thick bridge piers, massive abutments, arch bridge spandrel fill, large foundation blocks, and 3D soil-structure interaction domains.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:58` records `element:Solid`.
  - `capabilities.py:179-185` triggers `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Very High.
  - **Prerequisites**: 3D continuum kinematics, 3D constitutive stress update algorithms, 8-node hexahedron Gauss integration kernels, and 3D sparse linear solver ordering.
  - **Porting Pathway**: Phase 4 implementation targeting massive arch bridge abutment and pier modeling.

---

#### 2.2.4 Truss Element
- **C# Source Location**: `C#_Original/Objects/Truss.cs` (14,084 bytes, 582 lines), `Objects.ElementStates/TrussState.cs`, `ModelManagement.ComputationalElementsOperations/TrussOperations.cs`.
- **C# Classes & Interfaces**: `class Truss : ComputationalElement`, `class TrussState : BaseObjectStateDBclass`.
- **Physical Formulation & Mechanics**:
  - The `Truss` element is a 2-node 3D uniaxial bar element carrying 6 translational degrees of freedom (2 nodes $\\times$ 3 translations: $u_{x1}, u_{y1}, u_{z1}, u_{x2}, u_{y2}, u_{z2}$).
  - Axial strain is evaluated along the chord connecting node 1 ($\mathbf{x}_1$) to node 2 ($\mathbf{x}_2$):
    $$L = \\|\\mathbf{x}_2 - \\mathbf{x}_1\\|, \\quad \\mathbf{n} = \\frac{\\mathbf{x}_2 - \\mathbf{x}_1}{L}, \\quad \\Delta L = \\mathbf{n} \\cdot (\\mathbf{u}_2 - \\mathbf{u}_1), \\quad \\varepsilon = \\frac{\\Delta L}{L}$$
  - Element tangent stiffness matrix is purely axial:
    $$\\mathbf{K}_{e} = \\frac{E_t A}{L} \\begin{bmatrix} \\mathbf{n} \\mathbf{n}^T & -\\mathbf{n} \\mathbf{n}^T \\\\ -\\mathbf{n} \\mathbf{n}^T & \\mathbf{n} \\mathbf{n}^T \\end{bmatrix}$$
  - Constitutive laws include linear elasticity, bilinear elastoplasticity with kinematic hardening (`ConstitutiveLawSteel`), and tension-only behavior with zero compressive resistance (slack cable / loose tie-rod modeling).
- **Role in C# Solver**:
  - Models historical wrought-iron and steel tie-rods (*catene*), post-tensioned anchor ties, diagonal bracing members, and cables.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:60` records `element:Truss`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low-to-Medium.
  - **Prerequisites**: 3D coordinate projection vector $\\mathbf{n}$, uniaxial spring integration, and global stiffness assembly.
  - **Porting Pathway**: Phase 2 implementation. Highly valuable for historical buildings where iron ties prevent outward vault and wall thrusts.

---

#### 2.2.5 Vertex Element
- **C# Source Location**: `C#_Original/Objects/Vertex.cs` (154,422 bytes, 6,102 lines), `Objects.ElementStates/VertexState.cs`, `ModelManagement.ComputationalElementsOperations/VertexOperations.cs`.
- **C# Classes & Interfaces**: `class Vertex : ComputationalElement`, `class VertexState : BaseObjectStateDBclass`.
- **Physical Formulation & Mechanics**:
  - The `Vertex` element is a specialized 3D macro-element block formulated to represent wall corners, T-junctions, cross-intersections, and vertical boundary piers.
  - It maintains 6 centroidal degrees of freedom ($u_x, u_y, u_z, \\theta_x, \\theta_y, \\theta_z$) and formulates complex 3D kinematic afference matrices linking multiple intersecting interface planes in arbitrary spatial orientations.
  - Evaluates out-of-plane kinematic rocking and twisting across corner joints, capturing torsional restraint and diagonal spalling at wall connections.
  - Integrates lumped and consistent mass matrices for dynamic and modal eigenvalue calculations.
- **Role in C# Solver**:
  - Solves the geometric ambiguity at 3D wall corners where multiple planar Quad panels meet at $90^\\circ$ or oblique angles, eliminating artificial stress concentrations.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:61` records `element:Vertex`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium-High.
  - **Prerequisites**: Multi-plane 3D afference geometry transformations, corner contact topology generation.
  - **Porting Pathway**: Phase 3 full 3D building assembly expansion.

---

#### 2.2.6 InterfaceMF (Macro-Frame Interface)
- **C# Source Location**: `C#_Original/Objects/InterfaceMF.cs` (34,265 bytes, 1,418 lines), `Objects/InterfaceStateMF.cs`, `Objects/InterfacesCollectionMF.cs`, `ModelManagement.ComputationalElementsOperations/InterfaceMFOperations.cs`.
- **C# Classes & Interfaces**: `class InterfaceMF : Interface`, `class InterfaceStateMF : InterfaceState`, `class InterfacesCollectionMF`.
- **Physical Formulation & Mechanics**:
  - The `InterfaceMF` is a hybrid contact interface connecting the 1D continuous displacement field of a `Frame` element (cubic Hermite bending shape functions $w(x)$ and linear axial displacement $u(x)$) to the 2D edge displacement field of an adjacent `Quad` masonry panel.
  - Discretizes the common boundary into distributed normal springs (capturing detachment and crushing) and tangential shear springs (capturing friction sliding, dowel action, and bond slip).
  - Normal stress coupling updates friction shear capacity based on contact compression between the frame beam/column and the masonry panel infill.
- **Role in C# Solver**:
  - Crucial for modeling reinforced concrete or steel frames infilled with unreinforced masonry panels, evaluating out-of-plane frame-panel detachment, diagonal strut formation, and corner crushing.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:62` records `element:InterfaceMF`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: `Frame` element implementation, mixed 1D-2D displacement kinematics, and contact spring factory integration.
  - **Porting Pathway**: Phase 2 infilled-frame structural assessment extension.

---

#### 2.2.7 InterfacePoligonal (3D Polygonal Interface)
- **C# Source Location**: `C#_Original/Objects/InterfacePoligonal.cs` (22,607 bytes, 982 lines), `ModelManagement.ComputationalElementsOperations/InterfacePoligonalOperations.cs`.
- **C# Classes & Interfaces**: `class InterfacePoligonal : Interface`.
- **Physical Formulation & Mechanics**:
  - Formulates contact between general 3D non-rectangular polygons (e.g. pentagonal or triangular surfaces produced by geometric clipping of 3D Solid elements or irregular Quad panels).
  - Uses Triangle.NET / Sutherland-Hodgman polygon clipping to decompose the arbitrary contact polygon into Delaunay triangles, establishing Gauss integration points and fiber spring cells over irregular footprints.
- **Role in C# Solver**:
  - Connects 3D solid continuum elements and non-standard geometric macro-blocks in bridge piers, voussoir arch contacts, and complex vault spandrel walls.
- **Python Boundary Guard**:
  - Preflight inspection rejects non-quad/interface models.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: 3D Solid elements and robust 3D polygon triangulation library.
  - **Porting Pathway**: Phase 4 3D bridge engineering expansion.

---

#### 2.2.8 NodeBC (Generalized Boundary Condition Node)
- **C# Source Location**: `C#_Original/Objects/NodeBC.cs` (54,693 bytes, 2,342 lines), `Objects.ElementStates/NodeBCState.cs`, `ModelManagement.ComputationalElementsOperations/NodeCOperations.cs`.
- **C# Classes & Interfaces**: `class NodeBC : NodeC`, `class NodeBCState`.
- **Physical Formulation & Mechanics**:
  - `NodeBC` is an advanced boundary entity carrying 6 degrees of freedom. It extends standard fixed/free nodal restraints by supporting:
    1. Uncoupled or coupled 6-DOF elastic foundation impedance matrices ($K_{xx}, K_{yy}, K_{zz}, K_{\\theta x}, K_{\\theta y}, K_{\\theta z}$).
    2. Nonlinear elastoplastic subgrade springs with hysteretic degradation.
    3. Multi-point master-slave kinematic constraints linking arbitrary degrees of freedom.
    4. Time-dependent enforced displacement history vectors for support settlement or multi-support seismic excitation.
- **Role in C# Solver**:
  - Flexible foundation boundary condition modeling, soil impedance modeling, and multi-point constraint assignment.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:63` records `element:NodeBC`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: 6-DOF boundary spring matrix assembly and linear solver RHS modification.
  - **Porting Pathway**: Phase 1 flexible foundation impedance extension.

---

#### 2.2.9 Link Element
- **C# Source Location**: `C#_Original/Objects.ComputationalElements/Link.cs` (12,062 bytes, 508 lines), `ModelManagement.ComputationalElementsOperations/LinkOperations.cs`.
- **C# Classes & Interfaces**: `class Link : ComputationalElement`.
- **Physical Formulation & Mechanics**:
  - The `Link` element connects two arbitrary structural nodes (Node $I$ and Node $J$) in 3D space, enforcing kinematic or elastic relations across selected degrees of freedom.
  - Can be configured as:
    1. **Rigid Link**: Enforces $\\mathbf{u}_J = \\mathbf{u}_I + \\boldsymbol{\\theta}_I \\times (\\mathbf{x}_J - \\mathbf{x}_I)$ via penalty formulation or static condensation.
    2. **Flexible Link**: Assigns discrete linear or nonlinear spring stiffnesses ($k_x, k_y, k_z, k_{\\theta x}, k_{\\theta y}, k_{\\theta z}$).
    3. **Gap / Hook Element**: Unilateral contact element active only in compression (gap closure) or tension (hook).
- **Role in C# Solver**:
  - Models rigid diaphragm links, floor-to-wall ties, seismic separation joints, and structural expansion gaps.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:56` records `element:Link`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low-to-Medium.
  - **Prerequisites**: Master-slave kinematic reduction or penalty row insertion in `linear_system.py`.
  - **Porting Pathway**: Phase 1 diaphragm linkage extension.

---

#### 2.2.10 Joint Element
- **C# Source Location**: `C#_Original/Objects.ComputationalElements/Joint.cs` (4,954 bytes, 218 lines), `ModelManagement.ComputationalElementsOperations/JointOperations.cs`.
- **C# Classes & Interfaces**: `class Joint : ComputationalElement`.
- **Physical Formulation & Mechanics**:
  - Formulates discrete nonlinear connection joints between frame elements or between frame beams and masonry wall quads.
  - Models rotational beam-column hinges, semi-rigid connections with moment-rotation degradation curves ($M - \\theta_r$), shear keys, and pin releases.
- **Role in C# Solver**:
  - Frame joint flexibility and moment releases in timber roofs and steel connections.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:57` records `element:Joint`.
  - `capabilities.py:179-185` flags `V1_ELEMENT_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Frame elements and rotational hysteretic springs.
  - **Porting Pathway**: Phase 2 frame connection modeling.

---

#### 2.2.11 InternalConstraint & PConstraint
- **C# Source Location**: `C#_Original/Objects.ComputationalElements/InternalConstraint.cs` (2,043 bytes), `Objects.ComputationalElements/PConstraint.cs`, `PConstraintDBclass.cs`, `ModelManagement.ComputationalElementsOperations/PConstraintOperations.cs`.
- **C# Classes & Interfaces**: `class InternalConstraint`, `class PConstraint : ComputationalElement`.
- **Physical Formulation & Mechanics**:
  - Multipoint constraint (MPC) equations imposing linear kinematic dependencies across collections of degrees of freedom:
    $$\\sum_{j} A_{ij} u_j = C_i$$
  - Primary application is the **Rigid Diaphragm Plane Constraint**, enforcing all nodes at a given floor elevation $Z = Z_{\\text{floor}}$ to move as a rigid body in the $XY$ plane:
    $$u_{xi} = u_{\\text{master}} - (y_i - y_{\\text{master}}) \\theta_{zi}$$
    $$u_{yi} = u_{\\text{master}} + (x_i - x_{\\text{master}}) \\theta_{zi}$$
- **Role in C# Solver**:
  - Enforces rigid floor diaphragm behavior, drastically reducing the effective degrees of freedom and preventing in-plane floor distortion.
- **Python Boundary Guard**:
  - Preflight capability check rejects models containing active MPC constraints.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Transformation matrix condensation $\\mathbf{K}^* = \\mathbf{T}^T \\mathbf{K} \\mathbf{T}$ or Lagrange multiplier rows in `histra/solver/assembler.py`.
  - **Porting Pathway**: Phase 1 rigid floor diaphragm extension.

---

#### 2.2.12 Curved Vault Elements & Parametric Meshing Wizards
- **C# Source Location**:
  - `C#_Original/Objects/Arch.cs` (25,139 bytes), `BarrelVault.cs` (23,028 bytes), `CloisterVault.cs`, `CrossVault.cs`, `Dome.cs` (14,069 bytes), `DomicalVault.cs`, `Drum.cs`, `Pendentive.cs`, `SpecchioVault.cs`, `Abside.cs`, `VaultProperties.cs`, `FiberVault.cs`.
  - `C#_Original/ModelManagement.GeometryElementsOperations/` (`ArchOperations.cs`, `BarrelVaultOperations.cs`, `CloisterVaultOperations.cs`, `CrossVaultOperations.cs`, `DomeOperations.cs`, `DomicalVaultOperations.cs`, `DrumOperations.cs`, `FiberVaultOperations.cs`, `SpecchioVaultOperations.cs`).
  - `C#_Original/ModelManagement.Mesher/` (`VaultMesher.cs`, `ArcoMesher.cs`, `DomeMesher.cs`, `DrumMesher.cs`).
  - `C#_Original/ModelLibrary.Wizard/` (`WizardArch.cs`, `WizardDome.cs`, `WizardBridge.cs`).
- **C# Classes & Interfaces**:
  - `class Arch`, `class BarrelVault`, `class CloisterVault`, `class CrossVault`, `class Dome`, `class DomicalVault`, `class Drum`, `class Pendentive`, `class SpecchioVault`, `class Abside`.
- **Physical Formulation & Mechanics**:
  - Implements analytical differential geometry formulations for 3D curved surfaces:
    - **Barrel Vaults**: Cylindrical surface defined by radius $R$, arc angle $2\\alpha$, span $L$, and thickness $t$.
    - **Cross (Groin) Vaults**: Geometric Boolean intersection of two orthogonal cylindrical barrel vaults.
    - **Cloister Vaults**: Intersection of cylindrical surfaces meeting at inward groins.
    - **Domes & Drums**: Spherical and toroidal surfaces with meridional and circumferential parametric subdivisions.
    - **Pendentives & Squinches**: Spherical triangle transitions converting a square floor plan into a circular dome base.
  - The parametric mesher evaluates differential surface normals, maps curved surfaces into discretized planar Quad elements, and calculates skewed interface planes connecting adjacent curved blocks.
- **Role in C# Solver**:
  - Parametric CAD modeling and automated geometric mesh generation for historical monumental churches, cathedrals, and masonry arch bridges.
- **Python Boundary Guard**:
  - When an HRX model contains pre-discretized Quads and Interfaces produced by these wizards, `histra-python` solves it natively. The upstream interactive CAD wizards and geometric surface meshers are excluded from the headless numerical core.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High (CAD geometry domain).
  - **Prerequisites**: 3D geometric surface representation and polygon clipping algorithms.
  - **Porting Pathway**: Standalone preprocessing utility or integration with external CAD/BIM tools (e.g. FreeCAD, Gmsh, Rhino/Grasshopper).

---

## 3. Domain 2: Materials & Constitutive Laws

### 3.1 Overview of Unimplemented Materials & Springs
In `histra-python` V1, material constitutive laws are strictly focused on masonry mechanical behavior (`MasonryMaterial`). This encompasses orthotropic Young's moduli ($E_1, E_2$), shear modulus ($G$), specific weight ($\\gamma$), Mohr-Coulomb friction angle ($\\varphi$), cohesion ($c$), tensile fracture energy ($G_{ft}$), compressive crushing strength ($f_m$), and multi-envelope hysteretic fiber backbones (Exponential tension, Parabolic compression).

All non-masonry material classes, continuum constitutive models, and 10 specialized cyclic spring formulations remain outside the V1 boundary.

The table below catalogs all unported material models and spring classes:

| Material / Spring Name | Primary C# Source Files | Key Classes & Methods | Mathematical Formulation & Role |
|---|---|---|---|
| **ConcreteMaterial** | `Objects.Material/ConcreteMaterial.cs`<br>`ModelManagement/ConcreteMaterialOperations.cs` | `ConcreteMaterial`<br>`GetE()`, `GetFc()`, `GetStrainAtPeak()` | Confined and unconfined concrete (Kent-Park, Mander, EC2 parabolic-rectangular). Used in RC frames and slabs. |
| **SteelMaterial** | `Objects.Material/SteelMaterial.cs`<br>`Objects.ConstitutiveLaw/ConstitutiveLawSteel.cs` | `SteelMaterial`<br>`ConstitutiveLawSteel` | Reinforcing rebar and structural steel (bilinear with hardening, Menegotto-Pinto cyclic model). |
| **FiberMaterial** | `Objects.Material/FiberMaterial.cs`<br>`Objects/Fiber.cs`<br>`ConstitutiveLawDebonding.cs` | `FiberMaterial`<br>`ConstitutiveLawDebonding` | FRP/TRM composites; linear elasticity to brittle rupture and shear debonding / delamination slip laws. |
| **ConcreteMultiLinearPlasticMaterial** | `Objects.Material/ConcreteMultiLinearPlasticMaterial.cs` | `ConcreteMultiLinearPlasticMaterial` | Piecewise multi-linear degrading backbone curve for reinforced concrete members with cyclic degradation. |
| **ElasticIsotropicMaterial** | `Objects.Material/ElasticIsotropicMaterial.cs` | `ElasticIsotropicMaterial`<br>`GetE()`, `GetG()`, `GetNu()` | 3D continuum linear isotropic elasticity ($E, \\nu, G, K$) for 3D Solid elements and elastic frames. |
| **GeotechnicalMaterial** | `Objects.Material/GeotecnicalMaterial.cs`<br>`ConstitutiveLawGeo.cs` | `GeotecnicalMaterial`<br>`ConstitutiveLawGeo` | Soil-structure interaction models: subgrade modulus $k_s(z)$, nonlinear lateral $p-y$ curves, bearing capacity. |
| **MomentCurvature** | `Objects.Material/MomentCurvature.cs`<br>`MomentCurvatureValue.cs` | `MomentCurvature`<br>`MomentCurvatureValue` | Fiber-integrated moment-curvature ($M-\\chi$) and axial-moment interaction ($P-M_y-M_z$) for plastic hinges. |
| **SpringConcrete01** | `Objects.GeneratedObjects.Springs/SpringConcrete01.cs` | `SpringConcrete01` | Kent-Park cyclic concrete compression spring with parabolic ascending curve and linear softening. |
| **SpringConcrete02** | `Objects.GeneratedObjects.Springs/SpringConcrete02.cs` | `SpringConcrete02` | Scott-Park-Priestley cyclic concrete model with linear tensile tension stiffening and crack closure. |
| **SpringConcrete04** | `Objects.GeneratedObjects.Springs/SpringConcrete04.cs` | `SpringConcrete04` | Popovics-Mander cyclic concrete model with fractional exponent curve and degraded unloading stiffness. |
| **SpringConcrete07** | `Objects/SpringConcrete07.cs` | `SpringConcrete07` | Advanced Mander cyclic concrete spring with dynamic crack opening/closing and plastic offset strains. |
| **SpringSteel01** | `Objects.GeneratedObjects.Springs/SpringSteel01.cs` | `SpringSteel01` | Menegotto-Pinto cyclic steel spring with curved transition branches and Bauschinger effect evolution. |
| **SpringSteel02** | `Objects/SpringSteel02.cs` | `SpringSteel02` | Bilinear kinematic hardening steel spring with explicit yield plateau and ultimate strain limit. |
| **SpringEndochronic** | `Objects/SpringEndochronic.cs` | `SpringEndochronic` | Valanis endochronic plasticity modeling inelastic hereditary deformation without an explicit yield surface. |
| **SpringStok** | `Objects/SpringStok.cs` | `SpringStok` | Stock cyclic shear-slip spring for rock joints and soil-structure interfaces with normal stress coupling. |
| **SpringArmFried** | `Objects/SpringArmFried.cs` | `SpringArmFried` | Armstrong-Frederick nonlinear kinematic hardening spring with back-stress differential evolution. |
| **SpringElastoPlastic & Takeda** | `Objects/SpringElastoPlastic.cs`<br>`SpringElastoPlasticTakeda.cs` | `SpringElastoPlastic`<br>`SpringElastoPlasticTakeda` | Standalone 1D elastoplastic spring with kinematic hardening and standalone Takeda trilinear spring. |

---

### 3.2 Detailed Material Formulations

#### 3.2.1 ConcreteMaterial
- **C# Source Location**: `C#_Original/Objects.Material/ConcreteMaterial.cs` (17,558 bytes, 694 lines), `ModelManagement.Material/ConcreteMaterialOperations.cs`.
- **C# Classes & Methods**: `class ConcreteMaterial : MaterialBase`, `GetFc()`, `GetStrainAtPeak()`, `GetStrainUltimate()`, `GetTensileStrength()`.
- **Physical Formulation & Mechanics**:
  - Implements classical concrete constitutive relationships for unconfined and confined concrete in compression and tension:
    1. **Unconfined Concrete (Kent-Park)**:
       - Ascending Branch ($0 \\le \\varepsilon \\le \\varepsilon_0$):
         $$\\sigma_c = f_c' \\left[ \\frac{2\\varepsilon}{\\varepsilon_0} - \\left(\\frac{\\varepsilon}{\\varepsilon_0}\\right)^2 \\right]$$
       - Softening Branch ($\\varepsilon_0 < \\varepsilon \\le \\varepsilon_{20}$):
         $$\\sigma_c = f_c' [1 - Z(\\varepsilon - \\varepsilon_0)] \\ge 0.2 f_c'$$
         where $Z = \\frac{0.5}{\\varepsilon_{50u} - \\varepsilon_0}$ is the strain softening slope.
    2. **Confined Concrete (Mander et al., 1988)**:
       - Incorporates lateral confinement provided by rectangular or circular transverse ties/spirals:
         $$f_{cc}' = f_{c0}' \\left( -1.254 + 2.254 \\sqrt{1 + \\frac{7.94 \\sigma_l'}{f_{c0}'}} - 2 \\frac{\\sigma_l'}{f_{c0}'} \\right)$$
         where $\\sigma_l' = K_e \\rho_s f_{yh}$ is the effective lateral confining stress and $K_e$ is the confinement effectiveness coefficient.
       - Compressive stress follows the Popovics equation:
         $$\\sigma_c = \\frac{f_{cc}' x r}{r - 1 + x^r}, \\quad x = \\frac{\\varepsilon}{\\varepsilon_{cc}}, \\quad r = \\frac{E_c}{E_c - E_{\\text{sec}}}$$
    3. **Tensile Behavior**:
       - Linear elastic up to tensile strength $f_{ct} = 0.3 (f_c')^{2/3}$.
       - Post-cracking exponential tension stiffening or linear softening based on concrete fracture energy $G_F$:
         $$\\sigma_t = f_{ct} \\exp\\left( -\\frac{\\varepsilon - \\varepsilon_{cr}}{\\varepsilon_{tu}} \\right)$$
- **Role in C# Solver**:
  - Assigns nonlinear constitutive properties to fibers in `Frame` cross-sections, beam-column plastic hinges, and composite floor `Slab` elements.
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:322` records `ConcreteMaterial` in `model.unsupported_material_templates`.
  - `histra/solver/capabilities.py:202-206` halts execution with `V1_MATERIAL_DOMAIN_UNSUPPORTED` if referenced by any active element.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Fiber section integration engine and Frame element state tracking.
  - **Porting Pathway**: Phase 2 reinforced concrete frame modeling extension.

---

#### 3.2.2 SteelMaterial
- **C# Source Location**: `C#_Original/Objects.Material/SteelMaterial.cs` (10,685 bytes, 412 lines), `Objects.ConstitutiveLaw/ConstitutiveLawSteel.cs`, `ModelManagement.Material/SteelMaterialOperations.cs`.
- **C# Classes & Methods**: `class SteelMaterial : MaterialBase`, `class ConstitutiveLawSteel : ConstitutiveLawBase`, `GetFy()`, `GetEs()`, `GetHardeningRatio()`.
- **Physical Formulation & Mechanics**:
  - Models reinforcing rebar, prestressing tendons, and structural steel profiles:
    1. **Bilinear Elastoplastic Model**:
       - Elastic branch: $\\sigma = E_s \\varepsilon$ for $|\\varepsilon| \\le \\varepsilon_y = f_y / E_s$.
       - Hardening branch: $\\sigma = f_y + b E_s (\\varepsilon - \\varepsilon_y)$ where $b = E_h / E_s \\in [0.005, 0.03]$ is the strain hardening ratio.
       - Ultimate limit: brittle rupture at ultimate tensile strain $\\varepsilon_u$ (typically $0.05$ to $0.10$).
    2. **Menegotto-Pinto Cyclic Model (1973)**:
       - Evaluates curved transition branches between asymptotic lines upon load reversal:
         $$\\sigma^* = b \\varepsilon^* + \\frac{(1 - b) \\varepsilon^*}{(1 + (\\varepsilon^*)^R)^{1/R}}$$
         where $\\sigma^* = \\frac{\\sigma - \\sigma_r}{\\sigma_0 - \\sigma_r}$, $\\varepsilon^* = \\frac{\\varepsilon - \\varepsilon_r}{\\varepsilon_0 - \\varepsilon_r}$, and $R$ is the Bauschinger curvature parameter:
         $$R(\\xi) = R_0 - \\frac{a_1 \\xi}{a_2 + \\xi}$$
         which degrades with accumulated plastic strain $\\xi = |\\varepsilon_{\\max} - \\varepsilon_0| / \\varepsilon_y$.
- **Role in C# Solver**:
  - Rebar layers in `Frame` fiber sections, structural steel framing members, and tension tie-rods (`Truss`).
- **Python Boundary Guard**:
  - `histra/io/hr_loader.py:322` records `SteelMaterial` in `unsupported_material_templates`.
  - `capabilities.py:202-206` raises `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium-Low.
  - **Prerequisites**: Truss elements or Frame fiber sections.
  - **Porting Pathway**: Phase 2 tie-rod and frame support.

---

#### 3.2.3 FiberMaterial & Composite Debonding
- **C# Source Location**: `C#_Original/Objects.Material/FiberMaterial.cs` (16,694 bytes, 680 lines), `Objects/Fiber.cs`, `Objects.ConstitutiveLaw/ConstitutiveLawDebonding.cs`, `ModelManagement.Material/FiberMaterialOperations.cs`.
- **C# Classes & Methods**: `class FiberMaterial : MaterialBase`, `class ConstitutiveLawDebonding : ConstitutiveLawBase`, `GetFRPProperties()`, `EvaluateSlip()`.
- **Physical Formulation & Mechanics**:
  - Represents composite strengthening materials: Carbon Fiber-Reinforced Polymer (CFRP), Glass Fiber (GFRP), and Textile-Reinforced Mortar (TRM/FRCM).
  - Unidirectional tensile behavior is purely linear elastic up to brittle tensile rupture:
    $$\\sigma_f = E_f \\varepsilon_f \\quad (\\varepsilon_f \\le \\varepsilon_{fu})$$
  - The critical structural failure mode in composite-retrofitted masonry is **intermediate crack debonding / delamination** from the substrate. This is modeled via a cohesive shear stress-slip law (CNR-DT 200 R1/2013):
    - Bilinear bond-slip formulation:
      $$\\tau(s) = \\tau_{\\max} \\frac{s}{s_0} \\quad (s \\le s_0)$$
      $$\\tau(s) = \\tau_{\\max} \\frac{s_u - s}{s_u - s_0} \\quad (s_0 < s \\le s_u)$$
    - Cohesive fracture energy:
      $$G_f = \\int_0^{s_u} \\tau(s) \\, ds = \\frac{1}{2} \\tau_{\\max} s_u$$
      Max transferable anchor force: $F_{fd} = b_f \\sqrt{2 E_f t_f G_f}$.
- **Role in C# Solver**:
  - Models retrofitted masonry walls, arches, and vaults strengthened with FRP strips, composite ties, or fabric meshes.
- **Python Boundary Guard**:
  - Intercepted by `hr_loader.py` and rejected by `capabilities.py` with `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Surface interface elements or reinforced quad skin layers.
  - **Porting Pathway**: Phase 3 historical masonry retrofit analysis.

---

#### 3.2.4 ConcreteMultiLinearPlasticMaterial
- **C# Source Location**: `C#_Original/Objects.Material/ConcreteMultiLinearPlasticMaterial.cs` (5,289 bytes, 214 lines).
- **C# Classes & Methods**: `class ConcreteMultiLinearPlasticMaterial : MaterialBase`.
- **Physical Formulation & Mechanics**:
  - General piecewise multi-linear backbone material defined by $N$ strain-stress coordinate points in compression and tension:
    $$\\{(\\varepsilon_{c,i}, \\sigma_{c,i})\\}_{i=1}^{N_c}, \\quad \\{(\\varepsilon_{t,j}, \\sigma_{t,j})\\}_{j=1}^{N_t}$$
  - Unloading paths can be configured with stiffness degradation factors $(\\beta_c, \\beta_t)$ to simulate progressive crushing and cracking without requiring analytical stress-strain functions.
- **Role in C# Solver**:
  - Experimental or custom concrete materials with user-defined test curves.
- **Python Boundary Guard**:
  - Intercepted by `hr_loader.py` and rejected by `capabilities.py` with `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low-to-Medium.
  - **Prerequisites**: Multi-linear spring integration in batch runtime.
  - **Porting Pathway**: Phase 2 generalized material extension.

---

#### 3.2.5 ElasticIsotropicMaterial
- **C# Source Location**: `C#_Original/Objects.Material/ElasticIsotropicMaterial.cs` (2,279 bytes, 98 lines).
- **C# Classes & Methods**: `class ElasticIsotropicMaterial : MaterialBase`, `GetE()`, `GetNu()`, `GetG()`.
- **Physical Formulation & Mechanics**:
  - Classical 3D continuum isotropic linear elasticity defined by:
    - Young's modulus $E$
    - Poisson's ratio $\nu$
    - Shear modulus $G = \\frac{E}{2(1+\\nu)}$
    - Bulk modulus $K = \\frac{E}{3(1-2\\nu)}$
    - Mass density $\\rho$
  - Constitutive elasticity matrix $\\mathbf{D}_{6 \\times 6}$ for 3D continuum elements:
    $$\\mathbf{D} = \\frac{E}{(1+\\nu)(1-2\\nu)} \\begin{bmatrix} 1-\\nu & \\nu & \\nu & 0 & 0 & 0 \\\\ \\nu & 1-\\nu & \\nu & 0 & 0 & 0 \\\\ \\nu & \\nu & 1-\\nu & 0 & 0 & 0 \\\\ 0 & 0 & 0 & \\frac{1-2\\nu}{2} & 0 & 0 \\\\ 0 & 0 & 0 & 0 & \\frac{1-2\\nu}{2} & 0 \\\\ 0 & 0 & 0 & 0 & 0 & \\frac{1-2\\nu}{2} \\end{bmatrix}$$
- **Role in C# Solver**:
  - Required for 3D `Solid` continuum macro-elements, elastic `Frame` members, and elastic foundation blocks.
- **Python Boundary Guard**:
  - Intercepted by `hr_loader.py` and rejected by `capabilities.py` with `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low.
  - **Prerequisites**: 3D Solid or Frame elements.
  - **Porting Pathway**: Phase 4 continuum solid mechanics extension.

---

#### 3.2.6 GeotechnicalMaterial
- **C# Source Location**: `C#_Original/Objects.Material/GeotecnicalMaterial.cs` (2,623 bytes, 114 lines), `Objects.ConstitutiveLaw/ConstitutiveLawGeo.cs`.
- **C# Classes & Methods**: `class GeotecnicalMaterial : MaterialBase`, `class ConstitutiveLawGeo : ConstitutiveLawBase`.
- **Physical Formulation & Mechanics**:
  - Formulates soil mechanics parameters for soil-structure interaction:
    - Depth-dependent subgrade reaction modulus: $k_s(z) = k_{s0} + m \\cdot z$.
    - Non-linear lateral subgrade reaction curves ($p-y$ curves) for piles and piers.
    - Soil shear strength via classical Mohr-Coulomb parameters: cohesion $c$, internal friction angle $\\phi$, and dilatancy $\\psi$.
    - Foundation soil ultimate bearing capacity ($q_{\\text{ult}} = c N_c + q N_q + 0.5 \\gamma B N_\\gamma$).
- **Role in C# Solver**:
  - Assigns material properties to foundation soil interface layers, soil springs at `NodeBC`, and 3D foundation soil solid blocks.
- **Python Boundary Guard**:
  - Intercepted by `hr_loader.py` and rejected by `capabilities.py` with `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Non-rigid foundation boundary springs or 3D soil continuum elements.
  - **Porting Pathway**: Phase 1 foundation impedance extension.

---

#### 3.2.7 MomentCurvature & Concentrated Plastic Hinges
- **C# Source Location**: `C#_Original/Objects.Material/MomentCurvature.cs` (4,651 bytes, 196 lines), `Objects.Material/MomentCurvatureValue.cs`.
- **C# Classes & Methods**: `class MomentCurvature : MaterialBase`, `class MomentCurvatureValue`.
- **Physical Formulation & Mechanics**:
  - Pre-computed or fiber-integrated moment-curvature ($M-\\chi$) and axial force-moment interaction ($P-M_y-M_z$) curves.
  - Formulates lumped plastic hinges located at beam-column ends (e.g. FEMA 356 / ASCE 41 generalized force-deformation backbones with elastic, yield, ultimate, and residual branches).
  - Rotational tangent stiffness $K_\\theta = \\frac{dM}{d\\theta_p}$ degrades as curvature exceeds yield curvature $\\chi_y$.
- **Role in C# Solver**:
  - Concentrated plastic hinge modeling for RC and steel frame members, avoiding full distributed fiber section integration.
- **Python Boundary Guard**:
  - Intercepted by `hr_loader.py` and rejected by `capabilities.py` with `V1_MATERIAL_DOMAIN_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Frame elements and rotational spring state machines.
  - **Porting Pathway**: Phase 2 lumped-plasticity frame analysis.

---

### 3.3 The 10 Specialized Unimplemented Spring Models

In addition to the ported spring formulations (`SpringLinearElastic`, `SpringCoulomb03`, `SpringHysteretic`, `SpringMultiLinearPlastic`), C# HiStrA contains 10 specialized 1D mechanical spring models developed for specific material combinations:

#### 3.3.1 SpringConcrete01 (Kent-Park Cyclic Concrete)
- **C# Source**: `C#_Original/Objects.GeneratedObjects.Springs/SpringConcrete01.cs` (6,510 bytes).
- **Class**: `class SpringConcrete01 : Spring`.
- **Mechanics**: Implements the Kent-Park cyclic compression model. Parabolic compressive loading up to $f_c'$, linear post-peak softening to residual stress $0.2 f_c'$, zero tensile resistance, and linear unloading directed toward the plastic offset strain $\\varepsilon_p = \\varepsilon_0 [(\\varepsilon_{\\max}/\\varepsilon_0) - \\ln(1 + \\varepsilon_{\\max}/\\varepsilon_0)]$.

#### 3.3.2 SpringConcrete02 (Scott-Park-Priestley Cyclic Concrete)
- **C# Source**: `C#_Original/Objects.GeneratedObjects.Springs/SpringConcrete02.cs` (7,680 bytes).
- **Class**: `class SpringConcrete02 : Spring`.
- **Mechanics**: Extends Kent-Park by incorporating linear tensile tension stiffening ($f_t, E_t$). Unloading paths feature hysteresis loops with energy dissipation and explicit crack opening and closure rules upon strain reversal.

#### 3.3.3 SpringConcrete04 (Popovics-Mander Cyclic Concrete)
- **C# Source**: `C#_Original/Objects.GeneratedObjects.Springs/SpringConcrete04.cs` (9,307 bytes).
- **Class**: `class SpringConcrete04 : Spring`.
- **Mechanics**: Popovics-Mander model with fractional exponent compressive curve $\\sigma = f_c' \\frac{x r}{r - 1 + x^r}$. Unloading stiffness degrades with maximum compressive strain: $E_u = E_c (\\varepsilon_0 / \\varepsilon_{\\max})^{0.5}$. Cyclic loops exhibit degradation of reloading strength.

#### 3.3.4 SpringConcrete07 (Advanced Mander Cyclic Concrete)
- **C# Source**: `C#_Original/Objects/SpringConcrete07.cs` (24,031 bytes, 1,028 lines).
- **Class**: `class SpringConcrete07 : Spring`.
- **Mechanics**: Highly detailed cyclic concrete spring accounting for dynamic crack opening and closure, plastic offset strain accumulation under severe seismic reversals, and energy-based stiffness degradation.

#### 3.3.5 SpringSteel01 (Menegotto-Pinto Cyclic Steel)
- **C# Source**: `C#_Original/Objects.GeneratedObjects.Springs/SpringSteel01.cs` (5,926 bytes).
- **Class**: `class SpringSteel01 : Spring`.
- **Mechanics**: Direct 1D spring realization of the Menegotto-Pinto model. Maintains smooth curved transition branches between elastic and plastic asymptotes, capturing the Bauschinger effect with dynamic parameter evolution $R(\\xi)$.

#### 3.3.6 SpringSteel02 (Bilinear Kinematic Hardening Steel)
- **C# Source**: `C#_Original/Objects/SpringSteel02.cs` (7,898 bytes, 342 lines).
- **Class**: `class SpringSteel02 : Spring`.
- **Mechanics**: Bilinear steel spring with kinematic hardening. Features explicit yield plateau, secondary strain hardening modulus $E_{sh}$, and ultimate strain cut-off $\\varepsilon_u$ triggering brittle bar rupture.

#### 3.3.7 SpringEndochronic (Valanis Endochronic Plasticity)
- **C# Source**: `C#_Original/Objects/SpringEndochronic.cs` (2,116 bytes, 98 lines).
- **Class**: `class SpringEndochronic : Spring`.
- **Mechanics**: Implements Valanis endochronic theory of plasticity. Models inelastic deformation as a continuous hereditary process governed by intrinsic pseudo-time $dz = \\frac{d\\zeta}{f(\\zeta)}$, eliminating the requirement for an explicit yield surface or discontinuous loading/unloading criteria.

#### 3.3.8 SpringStok (Stock Cyclic Shear-Slip Interface)
- **C# Source**: `C#_Original/Objects/SpringStok.cs` (10,808 bytes, 462 lines).
- **Class**: `class SpringStok : Spring`.
- **Mechanics**: Cyclic shear-slip model designed for rock joints and soil-structure interfaces. Formulates displacement-dependent friction mobilization, normal stress coupling, and hysteretic shear degradation under cyclic reversals.

#### 3.3.9 SpringArmFried (Armstrong-Frederick Kinematic Hardening)
- **C# Source**: `C#_Original/Objects/SpringArmFried.cs` (6,892 bytes, 298 lines).
- **Class**: `class SpringArmFried : Spring`.
- **Mechanics**: 1D nonlinear kinematic hardening model with fading memory back-stress evolution:
  $$d\\alpha = C \\, d\\varepsilon_p - \\gamma \\alpha |d\\varepsilon_p|$$
  Accurately predicts cyclic ratcheting and mean stress relaxation under unsymmetric cycling.

#### 3.3.10 SpringElastoPlastic & SpringElastoPlasticTakeda
- **C# Source**: `C#_Original/Objects/SpringElastoPlastic.cs` (11,430 bytes), `Objects/SpringElastoPlasticTakeda.cs` (17,941 bytes).
- **Classes**: `class SpringElastoPlastic : Spring`, `class SpringElastoPlasticTakeda : Spring`.
- **Mechanics**: Standalone 1D elastoplastic spring with kinematic hardening and standalone Takeda trilinear degrading spring (operating independently of normal stress coupling).

#### Python Boundary Guard for Specialized Springs
- In `histra-python`, `histra/springs/registry.py` enforces an explicit whitelist of constructible spring types:
  ```python
  _SPRING_TYPES = {
      "SpringLinearElastic": SpringElastic,
      "SpringCoulomb02": SpringCoulomb,
      "SpringCoulomb03": SpringCoulomb03,
      "SpringHysteretic": SpringHysteretic,
      "SpringMultiLinearPlastic": SpringMultiLinear,
  }
  ```
  Any attempt to deserialize an HRX containing `SpringConcrete01..07`, `SpringSteel01..02`, `SpringEndochronic`, or `SpringStok` fails closed during model ingestion or spring factory assignment.
- **Porting Complexity**: Low-to-Medium per spring model.
- **Prerequisites**: Numba compiled batch kernel vectorization (`hysteretic_kernels/`).

---

## 4. Domain 3: Load Generators & Boundary Conditions

### 4.1 Overview of Unimplemented Load Generators & Boundary Conditions
In `histra-python` V1, load application is strictly limited to static nodal point loads (`PointLoadElement`), static edge line loads (`LineLoadElement`), uniform quadrilateral surface loads (`AreaLoadElement`), self-weight gravity body forces, and proportional load combinations (`LoadCombination` / `StaticLoad`).

In C# HiStrA, pushover analysis supports advanced lateral load distribution generators (Modal, Triangular, Adaptive, ShearFloor) conforming to Eurocode 8 and Italian Building Code (NTC2008/NTC2018). Furthermore, C# supports non-rigid foundation boundary condition refresh, moving vehicle traffic train loads, and parametric vault hydrostatic/earth pressure loads.

The table below catalogs these unported load generators and boundary condition capabilities:

| Capability | Primary C# Source Files | Key Classes & Methods | Mathematical Formulation & Role |
|---|---|---|---|
| **Modal Pushover Distribution** | `ModelManagement.Load/ModelLoadOperations.cs`<br>`Objects.Analyses/PushModalSet.cs`<br>`PushOverData.cs` | `GenerateLoadsForPushOverMultiModalAnalysis()`<br>`PushModalSet` | Evaluates lateral loads proportional to structural vibration mode shapes $\\boldsymbol{\\phi}_i$ and modal participation factors $\\Gamma_i$. |
| **Triangular Pushover Distribution** | `ModelManagement.Load/ModelLoadOperations.cs`<br>`Objects.ElementStates/InverseTriangularValues.cs`<br>`SolverRuntime/Pseudovectors.cs` | `ComputePhiTriangolareInversa()`<br>`InverseTriangularValues` | Inverted triangular lateral acceleration profile along building height: $a(z) \\propto (z - z_{\\min})$. |
| **Adaptive Pushover Distribution** | `ModelManagement.Load/ModelLoadOperations.cs`<br>`ModelManagement.Analyses/PushoverOperations.cs` | `GenerateLoadsForPushOverAnalysis()`<br>Adaptive mode updating | Dynamically updates lateral load pattern at each step based on instantaneous tangent mode shapes or story drifts. |
| **ShearFloor Pushover Distribution** | `ModelManagement.Load/ModelLoadOperations.cs`<br>`ModelManagement.Mesher/SlabMesher.cs` | `GenerateLoadsForPushOverAnalysis()` | Distributes total lateral base shear across floor diaphragms in proportion to floor masses and elevations ($F_j \\propto m_j h_j$). |
| **Non-Rigid Restraint Refresh** | `Objects/Restraint.cs`<br>`ModelManagement.GeometryElementsOperations/`<br>`GeometryPointRestraintOperations.cs` | `CountMaterialKeyPositive()`<br>`UpdateRestraints()` | Foundation boundary restraints carrying soil impedance springs ($K_x, K_y, K_z$) refreshed across multi-stage analyses. |
| **Moving Vehicle Traffic Loads** | `Objects.Loads/VehicleLoadElement.cs`<br>`WheelLoadElement.cs`<br>`ModelLibrary.Wizard.Bridge/Corsia.cs`<br>`VehiclePath.cs` | `VehicleLoadElement`<br>`WheelLoadElement`<br>`Corsia`, `VehiclePath` | Moving axle vehicle trains traveling along discrete traffic lanes across bridge decks at sequential spatial positions. |
| **Vault Earth/Hydrostatic Loads** | `Objects.Loads/VaultLoadElement.cs`<br>`ModelManagement.Load/VaultLoadOperations.cs` | `VaultLoadElement`<br>`VaultLoadOperations` | Hydrostatic earth pressure and spandrel fill loads acting normally and tangentially on curved vault surfaces. |

---

### 4.2 Detailed Formulations & Mechanics

#### 4.2.1 Modal Pushover Load Distribution
- **C# Source Location**: `C#_Original/ModelManagement.Load/ModelLoadOperations.cs` (lines 400–650), `Objects.Analyses/PushModalSet.cs`, `Objects.Analyses/PushOverData.cs`.
- **C# Classes & Methods**: `ModelLoadOperations.GenerateLoadsForPushOverMultiModalAnalysis(Collections, Analysis an, int Combination, SparseMatrix Mass, bool[] Ex, bool[] Ey, bool[] Ez, out Vector f, out string errorLog)`.
- **Physical Formulation & Mathematical Derivation**:
  - In code-based seismic assessment (Eurocode 8 §4.3.3.4.2, NTC2018 §7.3.4.1), pushover analysis requires lateral force patterns proportional to elastic vibration mode shapes.
  - The method requires a completed predecessor modal eigenvalue analysis (`PushModal_ModalAnalysisKey`) from which mode shapes $\\boldsymbol{\\phi}_i$ and natural frequencies $\\omega_i$ are extracted.
  - Modal participation factor for mode $i$ in direction $\\mathbf{d} = [d_x, d_y, d_z]^T$:
    $$\\Gamma_i = \\frac{\\boldsymbol{\\phi}_i^T \\mathbf{M} \\boldsymbol{\\iota}_d}{\\boldsymbol{\\phi}_i^T \\mathbf{M} \\boldsymbol{\\phi}_i}, \\quad \\boldsymbol{\\iota}_d = [d_x, d_y, d_z, 0, 0, 0, \\dots]^T$$
  - The modal lateral load pattern is formulated as:
    $$\\mathbf{P}_{\\text{ref}} = \\sum_{i=1}^{M} \\alpha_i \\Gamma_i \\mathbf{M} \\boldsymbol{\\phi}_i$$
    where $\\alpha_i$ represents the modal contribution weight (e.g., SRSS or CQC modal combination).
  - In C# (`PushModalTypeEnum.Single`), the user selects a single dominant mode shape (e.g. Mode 1 in $X$ or Mode 2 in $Y$). The force applied to node $k$ is:
    $$\\mathbf{F}_k = \\lambda \\cdot m_k \\cdot \\boldsymbol{\\phi}_{i,k}$$
- **Role in C# Solver**:
  - Automatically generates lateral seismic pushover forces reflecting fundamental structural vibration modes for regulatory seismic vulnerability certification.
- **Python Boundary Guard**:
  - `histra/solver/capabilities.py:290-300` inspects `analysis.type_load_distribution`. If set to `"Modal"`, it halts execution:
    ```python
    SolverCapabilityIssue("STATIC_LOAD_DISTRIBUTION_UNSUPPORTED", 
        f"TypeLoadDistribution='Modal' requires a pushover load generator not implemented "
        "in the V1 Quad/Interface core; use Force or LoadCombination.")
    ```
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: In-memory mode shape transfer from `solve_modal_analysis` to `AnalysisSession` without intermediate disk persistence.
  - **Porting Pathway**: Phase 1 implementation. High practical value for standard seismic pushover assessments.

---

#### 4.2.2 Triangular / Inverted Triangular Pushover Distribution
- **C# Source Location**: `C#_Original/ModelManagement.Load/ModelLoadOperations.cs`, `Objects.ElementStates/InverseTriangularValues.cs`, `C#_Original/SolverRuntime/Pseudovectors.cs` (`ComputePhiTriangolareInversa`).
- **C# Classes & Methods**: `Pseudovectors.ComputePhiTriangolareInversa(Analysis an, SparseMatrix M, out Vector phi)`, `InverseTriangularValues`.
- **Physical Formulation & Mechanics**:
  - Represents the standard inverted triangular acceleration distribution, simulating a linear first-mode drift profile where acceleration increases linearly with height above foundation level:
    $$a(z) = \\frac{z - z_{\\min}}{z_{\\max} - z_{\\min}}$$
    where $z_{\\min}$ is the lowest ground restraint elevation and $z_{\\max}$ is the roof elevation.
  - In `Pseudovectors.cs`, C# constructs the shape vector $\\boldsymbol{\\phi}_{\\text{triang}}$ by iterating over all Quads, Vertices, and Solids, evaluating centroid height $z_G$, and projecting the directional unit vector through element afference matrices:
    $$\\phi_i = \\sum_e A_{ie} \\cdot a(z_G) \\cdot \\mathbf{d}$$
  - The static lateral reference load vector is:
    $$\\mathbf{P}_{\\text{triang}} = \\mathbf{M} \\boldsymbol{\\phi}_{\\text{triang}}$$
    The modal mass and participation factor are recorded in `InverseTriangularValues` and persisted to SQLite for downstream N2 capacity spectrum conversion.
- **Role in C# Solver**:
  - Provides the mandatory "Group 1" (linear/triangular) lateral load pattern required by Eurocode 8 and Italian NTC regulations alongside the uniform/modal distribution.
- **Python Boundary Guard**:
  - Rejected by `capabilities.py:290-300` with `STATIC_LOAD_DISTRIBUTION_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low.
  - **Prerequisites**: Node elevation bounds inspection and global mass matrix multiplication $\\mathbf{P} = \\mathbf{M} \\boldsymbol{\\phi}$.
  - **Porting Pathway**: Phase 1 implementation. Very low implementation effort with high engineering utility.

---

#### 4.2.3 Adaptive Pushover Distribution
- **C# Source Location**: `C#_Original/ModelManagement.Load/ModelLoadOperations.cs`, `ModelManagement.Analyses/PushoverOperations.cs`.
- **C# Classes & Methods**: `ModelLoadOperations.GenerateLoadsForPushOverAnalysis()`, adaptive tangent updating loop.
- **Physical Formulation & Mechanics**:
  - Conventional invariant pushover load patterns (Modal, Triangular) assume that the relative distribution of lateral forces remains constant throughout the analysis. However, as masonry walls crack, yield, and lose stiffness, higher modes contribute significantly and the instantaneous vibration mode shape shifts dramatically.
  - The **Adaptive Pushover** procedure executes a generalized eigenvalue analysis on the current tangent stiffness matrix $\\mathbf{K}_T(\\mathbf{u}^k)$ at intermediate load levels or limit states:
    $$\\mathbf{K}_T(\\mathbf{u}^k) \\boldsymbol{\\phi}_i^k = (\\omega_i^k)^2 \\mathbf{M} \\boldsymbol{\\phi}_i^k$$
  - The lateral load increment $\\Delta \\mathbf{P}^k$ is recomputed using updated instantaneous mode shapes $\\boldsymbol{\\phi}_i^k$ and spectral amplifications, adapting the load pattern to progressive structural degradation.
- **Role in C# Solver**:
  - Advanced seismic assessment of highly irregular masonry buildings and asymmetric structures prone to torsional twists and soft-story mechanisms.
- **Python Boundary Guard**:
  - Rejected by `capabilities.py:290-300` with `STATIC_LOAD_DISTRIBUTION_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: Intermediate tangent eigensolver invocations within the static continuation loop, non-proportional load incrementation handlers.
  - **Porting Pathway**: Phase 3 advanced research extension.

---

#### 4.2.4 ShearFloor Distribution
- **C# Source Location**: `C#_Original/ModelManagement.Load/ModelLoadOperations.cs`, `ModelManagement.Mesher/SlabMesher.cs`.
- **C# Classes & Methods**: `ModelLoadOperations.GenerateLoadsForPushOverAnalysis()`.
- **Physical Formulation & Mechanics**:
  - Distributes total base shear across discrete building floor levels in accordance with classical code-equivalent lateral force procedures:
    $$F_j = V_{\\text{base}} \\frac{m_j h_j}{\\sum_{k=1}^N m_k h_k}$$
    where $m_j$ is the total tributary mass of floor $j$ and $h_j$ is the floor height above ground.
  - The floor lateral force $F_j$ is applied as a concentrated force at the floor center of mass or distributed across all floor slab perimeter nodes.
- **Role in C# Solver**:
  - Standard pushover analysis for multi-story masonry buildings with well-defined rigid floor diaphragms.
- **Python Boundary Guard**:
  - Rejected by `capabilities.py:290-300` with `STATIC_LOAD_DISTRIBUTION_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low.
  - **Prerequisites**: Floor diaphragm detection and mass aggregation.
  - **Porting Pathway**: Phase 1 building pushover extension.

---

#### 4.2.5 Non-Rigid Restraint Refresh & Foundation Impedance
- **C# Source Location**: `C#_Original/Objects/Restraint.cs` (`CountMaterialKeyPositive`), `ModelManagement.GeometryElementsOperations/GeometryPointRestraintOperations.cs`, `SurfaceRestraintOperations.cs`, `RestraintMesher.cs`.
- **C# Classes & Methods**: `Restraint.CountMaterialKeyPositive()`, `UpdateRestraints()`.
- **Physical Formulation & Mechanics**:
  - In C# HiStrA, nodal restraints can be designated as either rigid (kinematic zero-displacement constraints) or flexible (elastic/plastic foundation impedance springs).
  - When a restraint has `MaterialKey > 0`, C# instantiates translational and rotational subgrade springs ($K_x, K_y, K_z, K_{\\theta x}, K_{\\theta y}, K_{\\theta z}$).
  - In multi-stage analysis chains (e.g. soil scour, excavation, foundation differential settlement), C# triggers `UpdateRestraints()` at stage boundaries to recompute foundation stiffness matrices based on evolving geotechnical parameters.
- **Role in C# Solver**:
  - Dynamic foundation impedance updates, soil-structure interaction modeling, and multi-stage scour simulations.
- **Python Treatment & Parity Status**:
  - `histra-python` currently supports rigid fixed/free boundary restraints and freshly generated foundation interface springs (`interfaccia_vincolata == True`).
  - While Python supports sequential interface material mutations (`AnalysisSession.change_interface_materials`), general multi-stage non-rigid point/surface restraint impedance refresh routines from C# CAD mesher are not ported.
- **Python Boundary Guard**:
  - Rigid restraints solve natively; non-rigid restraint material reassignment outside interface springs is unported.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: General boundary spring assembly into global stiffness matrix $\\mathbf{K}$.
  - **Porting Pathway**: Phase 1 flexible foundation extension.

---

#### 4.2.6 Other Load Generators: Moving Vehicles & Vault Loads
- **C# Source Location**: `C#_Original/Objects.Loads/VehicleLoadElement.cs` (8,412 bytes), `WheelLoadElement.cs`, `ModelLibrary.Wizard.Bridge/Corsia.cs`, `VehiclePath.cs`, `Objects.Loads/VaultLoadElement.cs`, `ModelManagement.Load/VaultLoadOperations.cs`.
- **C# Classes & Methods**: `class VehicleLoadElement : LoadElement`, `class WheelLoadElement`, `class Corsia`, `class VehiclePath`, `class VaultLoadElement`.
- **Physical Formulation & Mechanics**:
  - **Moving Vehicle Train Generator**:
    - Defines traffic lanes (`Corsia`) along bridge decks parameterized by centerline spline $\\mathbf{r}(s)$ and lane width $W$.
    - Standard vehicle load models (Eurocode 1 Load Model 1, Italian NTC Load Model 1 with tandem axles and distributed load $q_{ik}$) place pairs of concentrated wheel loads at discrete longitudinal positions $s_k$.
    - Automatically projects wheel footprints onto underlying bridge deck Quads and Interfaces, generating sequential load cases for influence line and live load capacity envelopes.
  - **Vault Earth / Hydrostatic Pressure Generator**:
    - Evaluates normal and tangential surface pressures produced by backfill soil acting on curved vault extrados surfaces:
      $$p_n(z) = \\gamma_{\\text{fill}} (z_{\\text{road}} - z) K_0 \\cos^2(\\theta) + \\gamma_{\\text{fill}} (z_{\\text{road}} - z) \\sin^2(\\theta)$$
      where $\\theta$ is the local vault slope angle and $K_0$ is the at-rest lateral earth pressure coefficient.
- **Role in C# Solver**:
  - Automated traffic loading for masonry arch bridges and spandrel backfill pressure integration.
- **Python Boundary Guard**:
  - In `histra-python`, vehicle loads must be pre-converted into static nodal or area loads in the HRX file; the automated parametric moving lane generator is unported.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Lane centerline projection algorithms and wheel-to-quad tributary area calculation.
  - **Porting Pathway**: Phase 3 bridge live-load assessment extension.

---

## 5. Domain 4: Analysis Procedures & Solvers

### 5.1 Overview of Unimplemented Analysis Types & Numerical Solvers
In `histra-python` V1, numerical solving is strictly centered around static nonlinear continuation and real undamped modal eigenvalue extraction:
- **Static Nonlinear Solver**: Standard Newton-Raphson, Modified Newton-Raphson, and Newton accelerated by 4 line-search algorithms (Secant, Bisection, Regula-Falsi, Initial-Interpolated), driven by 3 static path integrators (Load Control, Crisfield Arc-Length, and Linearized Arc-Length).
- **Modal Solver**: Undamped real generalized eigenvalue analysis ($\mathbf{K} \boldsymbol{\phi}_i = \omega_i^2 \mathbf{M} \boldsymbol{\phi}_i$) using Subspace Iteration and sequential Inverse Iteration with bit-exact .NET PRNG replication.

All transient nonlinear dynamic time-history solvers, implicit dynamic integrators (Newmark, HHT, Wilson), earthquake accelerograms, viscous damping models, regulatory seismic response spectra, complex eigenvalue routines, and alternative Quasi-Newton algorithms remain **unimplemented** in Python.

The table below catalogs these unported solver capabilities:

| Solver Capability | Primary C# Source Files | Key Classes & Methods | Mathematical Formulation & Role |
|---|---|---|---|
| **Dynamic Nonlinear Analysis** | `SolverRuntime.AnalysisProcedure/`<br>`DynamicNonLinearAnalysis.cs` | `class DynamicNonLinearAnalysis`<br>`Execute()` | Solves second-order equations of motion in time domain: $\mathbf{M} \ddot{\mathbf{u}} + \mathbf{C} \dot{\mathbf{u}} + \mathbf{F}_{\text{int}}(\mathbf{u}) = \mathbf{F}_{\text{ext}}(t)$. Full time-stepping with ALS. |
| **Transient Integrator Base** | `SolverRuntime.Integrator/`<br>`TransientIntegrator.cs` | `class TransientIntegrator`<br>`NewStep()`, `Update()` | Abstract base tracking velocity ($\mathbf{V}$), acceleration ($\mathbf{A}$), dynamic damping dissipation, and energy balance. |
| **Newmark-$\beta$ Integrator** | `SolverRuntime.Integrator/Newmark.cs` | `class Newmark : TransientIntegrator` | Classical implicit Newmark-$\beta$ time integration ($\gamma = 0.5, \beta = 0.25$) with effective dynamic stiffness $\mathbf{K}_{\text{eff}}$. |
| **HHT-$\alpha$ Integrator** | `SolverRuntime.Integrator/HHT.cs`<br>`HHT2.cs` | `class HHT : TransientIntegrator`<br>`class HHT2` | Hilber-Hughes-Taylor $\alpha$-method introducing numerical dissipation for high-frequency spurious modes while maintaining second-order accuracy. |
| **Wilson-$\theta$ Integrator** | `SolverRuntime.Integrator/Wilson.cs` | `class Wilson : TransientIntegrator` | Wilson-$\theta$ extended step integrator ($\theta = 1.4$) ensuring unconditional stability for multi-DOF structural systems. |
| **Dynamic Loads & Accelerograms** | `Objects.Analyses/Accelerogram.cs`<br>`DynamicLoad.cs`<br>`Objects.Loads/LoadDynamicFunction.cs` | `class Accelerogram`<br>`class DynamicLoad`<br>`class LoadDynamicFunction` | Earthquake ground acceleration records $\ddot{u}_g(t)$, baseline corrections, and dynamic time-dependent force functions. |
| **Viscous Damping Formulations** | `UtilityLibrary.Tipi/DampingCriterionEnum.cs`<br>`TransientIntegrator.cs` | `DetermineDampingCoefficient()`<br>`enum DampingCriterionEnum` | Rayleigh damping ($\mathbf{C} = \alpha_M \mathbf{M} + \beta_K \mathbf{K}$), Caughey damping series, and stiffness-proportional damping. |
| **Seismic Response Spectra** | `Objects.Spettri/AccSpectrum.cs`<br>`PointSpectrum.cs`<br>`SpectralResponseITA2018.cs` | `class AccSpectrum`<br>`class PointSpectrum`<br>`class SpectralResponseITA2018` | Elastic and design acceleration spectra conforming to Eurocode 8 and Italian NTC2008/2018 regulations. |
| **Complex Eigenvalue Solvers** | `MatrixManager/`<br>`SolverRuntime/SubSpaceIteration2.cs` | Complex eigensolver interfaces | Complex eigenvalue extraction for non-classically damped systems ($[\mathbf{K} - \omega^2 \mathbf{M} + i \omega \mathbf{C}] \boldsymbol{\phi} = \mathbf{0}$) and transfer functions. |
| **Quasi-Newton Algorithms** | `UtilityLibrary.Tipi/AnalysisMethodEnum.cs`<br>`SolverRuntime.Integrator/RiksWempner.cs` | `KrylovNewton`, `Broyden`, `BFGS`<br>`class RiksWempner` | Low-rank secant matrix updates (Broyden, BFGS), Krylov subspace acceleration, and Riks-Wempner arc-length solver. |

---

### 5.2 Detailed Mathematical Formulations & Solver Flow

#### 5.2.1 Dynamic Nonlinear Time-History Analysis
- **C# Source Location**: `C#_Original/SolverRuntime/SolverRuntime.AnalysisProcedure/DynamicNonLinearAnalysis.cs` (274 lines), `SolverRuntime.Integrator/TransientIntegrator.cs` (630 lines).
- **C# Classes & Methods**: `DynamicNonLinearAnalysis.Execute(Program p, LinearSystem LS, ref Collections _collections, Analysis an, int Combination)`.
- **Physical Formulation & Governing Equations**:
  - Direct integration of the nonlinear equations of motion in the time domain under base acceleration or time-varying external loads:
    $$\mathbf{M} \ddot{\mathbf{u}}(t) + \mathbf{C} \dot{\mathbf{u}}(t) + \mathbf{F}_{\text{int}}(\mathbf{u}(t), \dot{\mathbf{u}}(t)) = \mathbf{F}_{\text{ext}}(t) - \mathbf{M} \boldsymbol{\iota} \ddot{u}_g(t)$$
  - Solves for state vectors at step $n+1$ ($t_{n+1} = t_n + \Delta t$): displacement $\mathbf{u}_{n+1}$, velocity $\dot{\mathbf{u}}_{n+1}$, and acceleration $\ddot{\mathbf{u}}_{n+1}$.
  - Adaptive Load Stepping (ALS) for dynamic analysis: when Newton iterations fail to converge within `MaxNumIter`, the time step is automatically bisected:
    $$\Delta t_{\text{sub}} = \frac{\Delta t}{N_{\text{sub}}}$$
    and state vectors are rolled back to the last committed checkpoint (`revertToLastCommit`).
  - Total dynamic energy balance is audited at each committed step:
    $$E_{\text{kinetic}}(t) + E_{\text{damping}}(t) + E_{\text{strain}}(t) + E_{\text{plastic}}(t) = E_{\text{input}}(t)$$
    where $E_{\text{input}} = -\int_0^t \dot{\mathbf{u}}^T \mathbf{M} \boldsymbol{\iota} \ddot{u}_g \\, dt$ and $E_{\text{damping}} = \int_0^t \dot{\mathbf{u}}^T \mathbf{C} \dot{\mathbf{u}} \\, dt$.
- **Role in C# Solver**:
  - Simulates nonlinear earthquake response, structural collapse, wall rocking, and post-earthquake residual deformations under recorded strong-motion accelerograms.
- **Python Boundary Guard**:
  - `histra/solver/capabilities.py:258-267` inspects `analysis.analysis_type`. If in `{3, 4}` (Dynamic Linear or Dynamic Nonlinear), preflight immediately halts execution:
    ```python
    SolverCapabilityIssue("DYNAMIC_ANALYSIS_UNSUPPORTED",
        "Dynamic linear and nonlinear analyses are outside the V1 masonry core.", name)
    ```
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: Dynamic state vectors ($\mathbf{u}, \dot{\mathbf{u}}, \ddot{\mathbf{u}}$) in memory session, global damping matrix assembly, transient integrator implementations, and accelerogram parser.
  - **Porting Pathway**: Phase 3 transient dynamic engine expansion.

---

#### 5.2.2 Transient Integrators: Newmark, HHT, Wilson
C# HiStrA implements three implicit second-order time integrators inheriting from `TransientIntegrator`:

##### 1. Newmark-$\beta$ Integrator (`SolverRuntime.Integrator/Newmark.cs`)
- Approximates displacement and velocity using Newmark's difference formulas:
  $$\mathbf{u}_{n+1} = \mathbf{u}_n + \Delta t \dot{\mathbf{u}}_n + \Delta t^2 \left[ \left(\frac{1}{2} - \beta\right) \ddot{\mathbf{u}}_n + \beta \ddot{\mathbf{u}}_{n+1} \right]$$
  $$\dot{\mathbf{u}}_{n+1} = \dot{\mathbf{u}}_n + \Delta t \left[ (1 - \gamma) \ddot{\mathbf{u}}_n + \gamma \ddot{\mathbf{u}}_{n+1} \right]$$
- Standard parameters: $\gamma = 0.5$, $\beta = 0.25$ (Average Acceleration Method, unconditionally stable, zero numerical damping).
- Effective dynamic tangent stiffness matrix:
  $$\mathbf{K}_{\text{eff}} = \mathbf{K}_T + \frac{\gamma}{\beta \Delta t} \mathbf{C} + \frac{1}{\beta \Delta t^2} \mathbf{M}$$
- Effective dynamic unbalance residual:
  $$\mathbf{R}_{n+1} = \mathbf{F}_{\text{ext}, n+1} - \mathbf{F}_{\text{int}, n+1} - \mathbf{M} \ddot{\mathbf{u}}_{n+1} - \mathbf{C} \dot{\mathbf{u}}_{n+1}$$

##### 2. Hilber-Hughes-Taylor (HHT-$\alpha$) Integrator (`SolverRuntime.Integrator/HHT.cs`, `HHT2.cs`)
- Introduces controllable numerical dissipation to damp out spurious high-frequency modes in finite element / macro-element meshes without sacrificing second-order accuracy.
- Modifies the discrete equation of motion with parameter $\alpha \in [-1/3, 0]$:
  $$\mathbf{M} \ddot{\mathbf{u}}_{n+1} + (1 + \alpha) \mathbf{C} \dot{\mathbf{u}}_{n+1} - \alpha \mathbf{C} \dot{\mathbf{u}}_n + (1 + \alpha) \mathbf{F}_{\text{int}}(\mathbf{u}_{n+1}) - \alpha \mathbf{F}_{\text{int}}(\mathbf{u}_n) = \mathbf{F}_{\text{ext}}(t_{n + 1 + \alpha})$$
  Integration constants:
  $$\gamma = \frac{1 - 2\alpha}{2}, \quad \beta = \frac{(1 - \alpha)^2}{4}$$
  When $\alpha = 0$, HHT collapses to the classical Newmark average acceleration method. When $\alpha = -0.1$, high-frequency noise is attenuated.

##### 3. Wilson-$\theta$ Integrator (`SolverRuntime.Integrator/Wilson.cs`)
- Assumes linear variation of acceleration over an extended time interval $\theta \Delta t$ where $\theta \ge 1.37$ (standard $\theta = 1.4$).
- Unconditionally stable for linear and nonlinear systems; damping increases with $\theta$.

##### Python Boundary Guard for Integrators
- `histra/solver/capabilities.py:352-360` enforces an explicit whitelist:
  ```python
  _STATIC_INTEGRATORS = {"LoadControl", "ArcLength", "ArcLengthLinear"}
  ```
  Specifying `Newmark`, `HHT`, `Wilson`, or any other transient integrator emits `STATIC_INTEGRATOR_UNSUPPORTED`.
- **Porting Complexity**: High.
- **Prerequisites**: `TransientIntegrator` base class, effective dynamic matrix assembly, time-stepping loop.
- **Porting Pathway**: Phase 3 transient dynamic engine.

---

#### 5.2.3 Dynamic Seismic Excitation & Viscous Damping Models
- **C# Source Location**: `C#_Original/Objects.Analyses/Accelerogram.cs`, `DynamicLoad.cs`, `Objects.Loads/LoadDynamicFunction.cs`, `UtilityLibrary.Tipi/DampingCriterionEnum.cs`.
- **C# Classes & Methods**: `class Accelerogram`, `class DynamicLoad`, `class LoadDynamicFunction`, `TransientIntegrator.DetermineDampingCoefficient()`.
- **Physical Formulation & Mechanics**:
  - **Accelerogram Processing**:
    - Imports natural or spectrum-compatible earthquake ground acceleration time records $\ddot{u}_g(t)$.
    - Performs linear baseline correction and unit scaling (g to $\text{cm/s}^2$ or $\text{mm/s}^2$).
  - **Viscous Damping Formulations**:
    1. **Rayleigh Damping** (`DampingCriterionEnum.Rayleigh`):
       $$\mathbf{C} = \alpha_M \mathbf{M} + \beta_K \mathbf{K}_T$$
       where coefficients $\alpha_M, \beta_K$ are calibrated from two target damping ratios $\xi_1, \xi_2$ at frequencies $\omega_1, \omega_2$:
       $$\begin{bmatrix} \alpha_M \\ \beta_K \end{bmatrix} = \frac{2}{\omega_2^2 - \omega_1^2} \begin{bmatrix} \omega_1 \omega_2 & 0 \\ 0 & 1 \end{bmatrix} \begin{bmatrix} \omega_2 & -\omega_1 \\ -\frac{1}{\omega_2} & \frac{1}{\omega_1} \end{bmatrix} \begin{bmatrix} \xi_1 \\ \xi_2 \end{bmatrix}$$
    2. **Stiffness-Proportional Damping**: $\mathbf{C} = \beta_K \mathbf{K}_T$ ($\beta_K = 2\xi / \omega_1$).
    3. **Caughey Damping Series**: Generalized orthogonal damping matrix covering $N$ modes without spurious damping at intermediate frequencies.
- **Role in C# Solver**:
  - Energy dissipation and realistic dynamic damping in time-history earthquake simulations.
- **Python Boundary Guard**:
  - Dynamic loads and damping criteria are rejected by `capabilities.py`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Modal frequency extraction to calibrate Rayleigh coefficients $\alpha_M, \beta_K$.
  - **Porting Pathway**: Phase 3 dynamic damping integration.

---

#### 5.2.4 Seismic Response Spectra & Italian Code Spectra (NTC2008 / NTC2018)
- **C# Source Location**: `C#_Original/Objects.Spettri/AccSpectrum.cs` (14,212 bytes), `PointSpectrum.cs`, `Objects.ModelProperty/SpectralResponseITA2018.cs`, `SpectralResponseCustom.cs`, `SeismicCriteria.cs`, `RegulationDefaultValues.cs`, `VitaUtile.cs`.
- **C# Classes & Methods**: `class AccSpectrum`, `class PointSpectrum`, `class SpectralResponseITA2018 : SpectralResponse`, `GetSpectrum()`.
- **Physical Formulation & Regulatory Standards**:
  - Implements elastic and design acceleration response spectra $S_e(T)$ and $S_d(T)$ according to Eurocode 8 and Italian Building Code (NTC2008 / NTC2018 §3.2.3):
    - **Branch 1** ($0 \le T < T_B$):
      $$S_e(T) = a_g \cdot S \cdot \eta \cdot F_0 \left[ \frac{T}{T_B} + \frac{1}{\eta \cdot F_0} \left(1 - \frac{T}{T_B}\right) \right]$$
    - **Branch 2** ($T_B \le T < T_C$):
      $$S_e(T) = a_g \cdot S \cdot \eta \cdot F_0$$
    - **Branch 3** ($T_C \le T < T_D$):
      $$S_e(T) = a_g \cdot S \cdot \eta \cdot F_0 \left( \frac{T_C}{T} \right)$$
    - **Branch 4** ($T \ge T_D$):
      $$S_e(T) = a_g \cdot S \cdot \eta \cdot F_0 \left( \frac{T_C T_D}{T^2} \right)$$
    where $a_g$ is peak ground acceleration, $F_0$ is dynamic amplification factor, $T_C^*$ is corner period, $S = S_S \cdot S_T$ combines stratigraphic and topographic amplification, and $\eta = \sqrt{10 / (5 + \xi)}$ is damping correction.
  - Includes geographic hazard grid lookup across 10,751 Italian seismic zones for 4 Limit States:
    - SLO (Operability Limit State)
    - SLD (Damage Limitation Limit State)
    - SLV (Life Safety Limit State)
    - SLC (Collapse Prevention Limit State)
- **Role in C# Solver**:
  - Generation of seismic demand spectra for the N2 / capacity spectrum method in pushover vulnerability evaluations.
- **Python Boundary Guard**:
  - `histra/solver/capabilities.py:133-143` rejects modal contribution output requests with `MODAL_CONTRIBUTION_OUTPUT_UNSUPPORTED`.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Italian geographic hazard grid coordinates and spectrum generator library.
  - **Porting Pathway**: Phase 5 code-compliant seismic vulnerability module.

---

#### 5.2.5 Complex Eigenvalue Solvers & Frequency-Domain Analysis
- **C# Source Location**: Stubs in `MatrixManager` and `SolverRuntime`.
- **Formulations**:
  - Complex eigenvalue analysis of non-classically damped structural systems:
    $$\left[ \lambda^2 \mathbf{M} + \lambda \mathbf{C} + \mathbf{K} \right] \boldsymbol{\phi} = \mathbf{0}$$
    Linearized into state-space generalized eigenproblem:
    $$\begin{bmatrix} -\mathbf{K} & \mathbf{0} \\ \mathbf{0} & \mathbf{M} \end{bmatrix} \begin{bmatrix} \boldsymbol{\phi} \\ \lambda \boldsymbol{\phi} \end{bmatrix} = \lambda \begin{bmatrix} \mathbf{C} & \mathbf{M} \\ \mathbf{M} & \mathbf{0} \end{bmatrix} \begin{bmatrix} \boldsymbol{\phi} \\ \lambda \boldsymbol{\phi} \end{bmatrix}$$
    yielding complex eigenvalues $\lambda_j = -\xi_j \omega_j \pm i \omega_j \sqrt{1 - \xi_j^2}$.
  - Harmonic steady-state frequency response function (FRF) analysis:
    $$\mathbf{H}(\omega) = \left[ -\omega^2 \mathbf{M} + i \omega \mathbf{C} + \mathbf{K} \right]^{-1}$$
- **Python Boundary Guard**:
  - `histra/solver/modal.py` only implements real undamped generalized eigenvalue analysis (`SubspaceIterations`, `InverseIterations`). Complex eigensolving is unported.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: Complex sparse direct solver (SuiteSparse UMFPACK complex interface or SciPy `splu` with complex dtype).
  - **Porting Pathway**: Phase 3 frequency-domain vibration analysis.

---

#### 5.2.6 Unimplemented Quasi-Newton & Alternative Nonlinear Solvers
- **C# Source Location**: `C#_Original/UtilityLibrary/UtilityLibrary.Tipi/AnalysisMethodEnum.cs` (`KrylovNewton`, `Broyden`, `BFGS`, `AcceleratedNewton`, `PeriodicNewton`), `SolverRuntime.Integrator/RiksWempner.cs`.
- **C# Enums & Classes**: `class RiksWempner : IncrementalIntegrator`.
- **Mechanics**:
  1. **Quasi-Newton Methods (Broyden, BFGS)**: Updates the inverse tangent stiffness matrix $\mathbf{H}_{k+1} \approx \mathbf{K}_{k+1}^{-1}$ using low-rank outer-product corrections ($\mathbf{s}_k = \Delta \mathbf{u}_k, \mathbf{y}_k = \Delta \mathbf{R}_k$), avoiding sparse matrix refactorizations. In C# HiStrA, these are mostly stubs in `EquiSolnAlgoFactory`.
  2. **Krylov-Newton Acceleration**: Accelerates modified Newton iterations using a small Krylov subspace of recent residual vectors.
  3. **Riks-Wempner Arc-Length**: Path-following continuation algorithm with a linear orthogonal constraint. Unlike Crisfield arc-length, Riks-Wempner in C# aborts with error code `-11` ("imaginary roots due to multiple instability directions") rather than falling back to linearized updates.
- **Python Boundary Guard**:
  - `capabilities.py:374-382` enforces that `method` must be one of the 10 supported Newton / Line Search combinations, emitting `NONLINEAR_METHOD_UNSUPPORTED` for any Quasi-Newton method.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Low-to-Medium.
  - **Prerequisites**: Low-rank matrix update handler in `linear_system.py`.
  - **Porting Pathway**: Phase 3 alternative solver acceleration.

---

## 6. Domain 5: Post-Processing & Special Capabilities

### 6.1 Overview of Unimplemented Post-Processing & Special Tools
In `histra-python` V1, post-processing is focused on high-precision data extraction:
- Capacity curves ($F - d$ curves) relating total base reaction in the pushover direction to control node displacement.
- Global reaction force and moment sums ($\sum F_x, \sum F_y, \sum F_z, \sum M_x, \sum M_y, \sum M_z$).
- Local point displacements via model point projection (`histra.solver.output_projection`).
- Natural frequencies, cyclic periods, and Modal Assurance Criterion (MAC) matrices (`histra.validation.modal_results`).

In C# HiStrA, several specialized subsystems provide external solver interoperability, cross-section finite element meshing, regulatory seismic vulnerability indices, and proprietary database persistence.

The table below catalogs these unported special capabilities:

| Subsystem | Primary C# Source Files | Key Classes & Methods | Purpose & Role in C# Suite |
|---|---|---|---|
| **Adaptic IO Translator** | `AdapticIO/AdapticIO/`<br>`InputManager.cs`<br>`InputManager2.cs`<br>`OutputManager.cs`<br>`GroupFrameItem.cs` | `class InputManager`<br>`class OutputManager`<br>`enum FileDatEnum` | Full bidirectional translation of HiStrA models to Adaptic FE `.dat` format, executing external `adaptic.exe`, and parsing binary results back into SQLite. |
| **SectionBuilder Core** | `SectionBuilderCore/`<br>`MeshMaker.cs`<br>`Polygon.cs`<br>`PolygonOperations.cs`<br>`Objects.Section/*` | `class MeshMaker`<br>`class Polygon`<br>`calculateInerziaMatrix()` | 2D cross-section geometry editor, Triangle.NET Delaunay mesher, geometric inertia calculations, and fiber discretization for 3D Frame elements. |
| **Seismic Vulnerability Checker** | `SeismicVulnerabiltyLibrary/`<br>`SeismicVulnerabilityChecker.cs`<br>`Objects.SeismicVulnerabilityAssessment/*` | `RunMetodoA_NTC18()`<br>`RunMetodoB_NTC18()`<br>`class SeismicVulnerability` | Automated seismic vulnerability evaluation conforming to Italian NTC2008/2018: N2 capacity spectrum method, SDOF bilinear curve, and risk index $\zeta_E$. |
| **Enterprise SQL Server DB** | `DBManagement/`<br>`dbSQLserverManager.cs`<br>`dbSQLServerModelManager.cs` | `class dbSQLserverManager`<br>`class dbSQLServerModelManager` | Multi-user enterprise Microsoft SQL Server database synchronization and model versioning. |
| **CAD & File Interoperability** | `ModelManagement/DxfIO.cs`<br>`ModelManagement/InpIO.cs`<br>`ExcelLibrary.Excel/ExcelManager.cs` | `class DxfIO`<br>`class InpIO`<br>`class ExcelManager` | AutoCAD DXF geometry import/export, Abaqus `.inp` finite element input deck translation, and Microsoft Excel COM automation for reporting. |

---

### 6.2 Detailed Technical Formulations & Mechanics

#### 6.2.1 Adaptic Solver IO Translator
- **C# Source Location**: `C#_Original/AdapticIO/AdapticIO/InputManager.cs` (2,323 lines), `InputManager2.cs` (650 lines), `InputManager3.cs` (480 lines), `OutputManager.cs` (1,210 lines), `GroupFrameItem.cs`, `FileDatEnum.cs`, `Helper.cs`.
- **C# Classes & Methods**: `InputManager.SaveFileDat()`, `OutputManager.ReadBinaryOutput()`, `InputManager.RunAdapticProcess()`.
- **Technical Formulation & Architecture**:
  - Adaptic is a high-performance nonlinear structural finite element solver developed by Prof. Bassam Izzuddin at Imperial College London.
  - In legacy HiStrA workflows, Adaptic served as the primary numerical engine for 1D beam-column frame structures and nonlinear dynamic time-history analysis before HiStrA's internal solver was fully mature.
  - `AdapticIO` translates HiStrA domain objects into the Adaptic ASCII `.dat` deck format:
    - Nodal coordinates and boundary restraints.
    - 3D beam-column elements (`cb3`, `cbf3` with distributed plasticity).
    - Material definitions (bilinear steel, Kent-Park concrete, elastic materials).
    - Sequential analysis stages: gravity load control followed by displacement-controlled pushover or dynamic ground acceleration time-histories.
  - Launches external `adaptic.exe` as a child operating system process, monitors execution via stdout pipes, and parses proprietary Adaptic binary output files into HiStrA's `.Results` SQLite database schema.
- **Role in C# Solver**:
  - Alternative external FE solver runner and validation benchmark engine.
- **Python Boundary Guard & Treatment**:
  - `histra-python` is intentionally designed as an **in-process, headless, native Python solver**. All numerical solving (Newton-Raphson, Arc-Length, Line Search, Subspace Modal) is performed directly in Python with Numba-compiled execution, eliminating external executable dependencies.
  - Adaptic IO is omitted as out-of-scope for the native Python engine.
- **Porting Complexity & Recommendation**:
  - **Complexity**: High.
  - **Recommendation**: Do not port. Native Python solver provides complete control, memory safety, and cross-platform independence without requiring legacy Windows-only binaries.

---

#### 6.2.2 SectionBuilder Core (Cross-Section Mesher & Fiber Integrator)
- **C# Source Location**: `C#_Original/SectionBuilderCore/SectionBuilderCore/MeshMaker.cs` (43 lines), `SectionBuilderCore.Objects/Polygon.cs`, `PolygonOperations.cs` (350 lines), `Objects.Section/FrameSectionTemplateBase.cs`, `BeamColumnTemplate.cs`, `DoubleTSectionTemplate.cs`, `RectangularSectionTemplate.cs`, `SlabSectionTemplate.cs`.
- **C# Classes & Methods**: `MeshMaker.Triangulate()`, `PolygonOperations.calculateCenterOfMass()`, `calculateTotalMass()`, `calculateInerziaMatrix()`.
- **Technical Formulation & Mechanics**:
  - SectionBuilder is an automated 2D finite element cross-section mesher and mechanical property evaluator for structural beam-columns:
    1. **Arbitrary 2D Polygon Boundary Input**: Ingestion of arbitrary polygonal section contours (including exterior perimeters, interior voids/hollows, rebar coordinate locations, and composite steel-concrete interfaces).
    2. **Delaunay Triangulation (Triangle.NET)**:
       - Uses Shewchuk's Delaunay triangulation algorithm (`MeshMaker.Triangulate`) with user-specified quality constraints (minimum angle `MinAngle` $\ge 20^\circ$, maximum triangle area `MaxArea`).
       - Discretizes complex cross-sections into hundreds of triangular sub-elements (fibers).
    3. **Geometric Cross-Section Properties**:
       - Evaluates cross-sectional area $A = \int_A dA$, centroid coordinates:
         $$y_G = \frac{1}{A} \int_A y \\, dA, \quad z_G = \frac{1}{A} \int_A z \\, dA$$
       - Moments of inertia and product of inertia:
         $$I_{yy} = \int_A z^2 \\, dA, \quad I_{zz} = \int_A y^2 \\, dA, \quad I_{yz} = \int_A y z \\, dA$$
       - Principal inertia axes rotation angle:
         $$\theta_p = \frac{1}{2} \arctan\left( \frac{2 I_{yz}}{I_{zz} - I_{yy}} \right)$$
       - Saint-Venant torsional constant $J$ via Prandtl stress function or 2D Poisson finite element solve ($\nabla^2 \psi = -2$).
    4. **Fiber Discretization for Distributed Plasticity**:
       - Assigns material pointers (`ConcreteMaterial`, `SteelMaterial`) and tributary areas $A_i$ to each fiber centroid $(y_i, z_i)$, enabling 3D biaxial bending and axial force integration ($P-M_y-M_z$) in `Frame` elements.
- **Role in C# Solver**:
  - Generates cross-section fiber layouts for RC beams, columns, bridge piers, steel wide-flange girders, and composite floor sections.
- **Python Boundary Guard & Treatment**:
  - Python V1 models 2D masonry panels without 1D fiber beam elements; SectionBuilder is omitted from V1.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: High.
  - **Prerequisites**: 2D polygon Boolean clipping library, Delaunay triangulation (e.g. Python bindings to `triangle` or `scipy.spatial.Delaunay`), and fiber section state integration.
  - **Porting Pathway**: Phase 2 cross-section meshing module supporting future `Frame` elements.

---

#### 6.2.3 Seismic Vulnerability Assessment Indices (Method A & Method B)
- **C# Source Location**: `C#_Original/SeismicVulnerabiltyLibrary/SeismicVulnerabiltyLibrary/SeismicVulnerabilityChecker.cs` (462 lines), `Objects.SeismicVulnerabilityAssessment/SeismicVulnerability.cs`, `SeismicVulnerabilityItem.cs`, `ModelLibrary/SeismicVulnerabilityData.cs`.
- **C# Classes & Methods**: `SeismicVulnerabilityChecker.RunMetodoA_NTC18(Model model, SeismicVulnerability SV = null)`, `RunMetodoB_NTC18()`.
- **Regulatory Framework & Mathematical Derivation**:
  - Formulates automated seismic safety verification according to the Italian Building Code (NTC2008 / NTC2018 §7.3.4.1 and Circular No. 7/2019):
    1. **Multi-Degree-of-Freedom to Equivalent Single-Degree-of-Freedom (SDOF) Transformation**:
       - Extracts the multi-degree-of-freedom (MDOF) pushover capacity curve ($V_b - d_c$, base shear vs control node displacement).
       - Evaluates the modal transformation factor:
         $$\Gamma = \frac{\boldsymbol{\phi}^T \mathbf{M} \boldsymbol{\iota}}{\boldsymbol{\phi}^T \mathbf{M} \boldsymbol{\phi}} = \frac{m^*}{\sum m_k \phi_k^2}$$
       - Converts to equivalent SDOF system coordinates ($F^* - d^*$):
         $$F^* = \frac{V_b}{\Gamma}, \quad d^* = \frac{d_c}{\Gamma}, \quad m^* = \boldsymbol{\phi}^T \mathbf{M} \boldsymbol{\iota}$$
    2. **Bilinear Idealization of the Capacity Curve**:
       - Fits an equivalent elastoplastic bilinear curve enforcing equal energy dissipation up to ultimate displacement capacity $d_u^*$:
         $$E_{\text{diss}} = \int_0^{d_u^*} F^*(d^*) \\, dd^* = F_y^* \left( d_u^* - \frac{d_y^*}{2} \right)$$
       - Yield force $F_y^*$ and elastic stiffness $k^* = F_y^* / d_y^*$ calibrated from the secant stiffness at $0.6 V_{\max}^*$.
       - Equivalent SDOF natural period:
         $$T^* = 2\pi \sqrt{\frac{m^*}{k^*}}$$
    3. **Seismic Demand Evaluation (N2 Method / Capacity Spectrum)**:
       - Compares displacement capacity $d_u^*$ against inelastic displacement demand $d_{\max}^*$ determined from the elastic response spectrum $S_e(T^*)$:
         - If $T^* \ge T_C$ (medium-to-long period, equal displacement rule):
           $$d_{\max}^* = S_{de}(T^*) = S_e(T^*) \left( \frac{T^*}{2\pi} \right)^2$$
         - If $T^* < T_C$ (short period):
           $$d_{\max}^* = \frac{S_{de}(T^*)}{q^*} \left[ 1 + (q^* - 1) \frac{T_C}{T^*} \right] \ge S_{de}(T^*)$$
           where $q^* = \frac{m^* S_e(T^*)}{F_y^*}$ is the ductility demand ratio.
    4. **Method A vs Method B Evaluation**:
       - **Method A**: Evaluates the seismic risk index at fixed code-prescribed spectral demand:
         $$\zeta_E = \frac{d_u^*}{d_{\max}^*}$$
         Risk index $\zeta_E \ge 1.0$ indicates compliance; $\zeta_E < 1.0$ indicates seismic vulnerability.
       - **Method B (Iterative Capacity Acceleration Search)**:
         - Iteratively scales the seismic demand spectrum until displacement demand equals displacement capacity ($d_{\max}^* = d_u^*$), determining the maximum peak ground acceleration the structure can sustain: $PGA_C$ (Capacity PGA).
         - Evaluates the acceleration-based seismic safety index:
           $$\alpha_S = \frac{PGA_C}{PGA_D}$$
- **Role in C# Solver**:
  - Produces official regulatory seismic safety certification certificates, risk indices, and safety factor tables across the 4 Limit States (SLO, SLD, SLV, SLC).
- **Python Boundary Guard & Treatment**:
  - `histra-python` focuses on providing mathematically verified raw numerical outputs: exact capacity curves, reaction vectors, and nodal displacements (`histra.postprocessing`). Regulatory SDOF curve idealization and code assessment are omitted from V1.
- **Porting Complexity & Prerequisites**:
  - **Complexity**: Medium.
  - **Prerequisites**: NTC response spectra generator, bilinear curve fitting algorithms, and N2 capacity spectrum solver.
  - **Porting Pathway**: Phase 5 code-compliant vulnerability assessment module.

---

#### 6.2.4 Enterprise Database & CAD Interoperability
- **C# Source Location**: `C#_Original/DBManagement/dbSQLserverManager.cs`, `dbSQLServerModelManager.cs`, `ModelManagement/DxfIO.cs`, `ModelManagement/InpIO.cs`, `ExcelLibrary.Excel/ExcelManager.cs`.
- **C# Classes & Methods**: `dbSQLserverManager.Connect()`, `DxfIO.Import()`, `InpIO.Export()`, `ExcelManager.OpenConnection()`.
- **Technical Formulation & Role**:
  1. **Microsoft SQL Server Management**:
     - Provides multi-user enterprise database synchronization, network project collaboration, and centralized model storage.
     - Unused in standard desktop workflows; HiStrA overwhelmingly uses local SQLite `.Results` databases.
  2. **AutoCAD DXF Geometry Import/Export**:
     - Parses 2D/3D AutoCAD DXF files (polylines, 3DFACE, lines) into structural geometry panels, openings, and beam axes.
  3. **Abaqus `.inp` Input Deck Translation**:
     - Translates HiStrA meshes into Abaqus finite element input decks for independent verification in commercial FE software.
  4. **Excel COM Automation**:
     - Automates Microsoft Excel via Windows OLE/COM interop to generate formatted engineering calculation workbooks.
- **Python Boundary Guard & Treatment**:
  - `histra-python` utilizes lightweight SQLite databases (`histra/io/results_reader.py`) and standard JSON/CSV output formats. Proprietary Windows COM automation, enterprise SQL Server, and legacy CAD translators are omitted as platform-specific desktop tooling.
- **Porting Complexity & Recommendation**:
  - DXF import: Low complexity, candidate for Phase 5 geometry import utility.
  - SQL Server / Excel COM: Out-of-scope, replaced by open-source SQLite, pandas, and openpyxl libraries if needed.

---

## 7. Comparative Porting Feasibility & Strategic Roadmap

### 7.1 Comprehensive Feasibility & Priority Matrix

To guide future architectural expansion beyond the V1 Discrete Macro-Element Method masonry core, every unported capability has been systematically evaluated across four engineering metrics:
1. **Porting Complexity**: Estimated implementation effort and mathematical complexity (Low, Medium, High, Very High).
2. **Architectural Prerequisites**: Core subsystem foundations that must be in place before implementation can begin.
3. **Engineering Impact & Practical ROI**: Practical value to practicing structural engineers, researchers, and masonry assessment workflows (High, Medium, Low).
4. **Target Strategic Phase**: Recommended chronological sequencing across 5 expansion phases.

| Functional Domain | Capability / Feature | C# Files | Porting Complexity | Architectural Prerequisites | Engineering ROI | Target Phase |
|---|---|---|---|---|---|---|
| **Domain 3: Loads & BCs** | **Triangular Pushover Pattern** | 3 files | **Low** | Global mass matrix multiplication | **High** | **Phase 1** |
| **Domain 3: Loads & BCs** | **Modal Pushover Pattern** | 4 files | **Medium** | In-memory modal eigenvector transfer | **High** | **Phase 1** |
| **Domain 3: Loads & BCs** | **ShearFloor Pushover Pattern** | 2 files | **Low** | Floor elevation and mass grouping | **Medium** | **Phase 1** |
| **Domain 3: Loads & BCs** | **Non-Rigid Restraint Refresh** | 4 files | **Medium** | Boundary spring stiffness assembly | **High** | **Phase 1** |
| **Domain 1: Elements** | **Link & Diaphragm Constraints** | 3 files | **Low-Med** | Master-slave / penalty linear solver | **High** | **Phase 1** |
| **Domain 1: Elements** | **Truss Tie-Rod Elements** | 3 files | **Low-Med** | 3D bar kinematics, tension-only law | **High** | **Phase 2** |
| **Domain 1: Elements** | **3D Frame Elements (Beams/Cols)** | 8 files | **High** | 6-DOF transformations, fiber integration | **High** | **Phase 2** |
| **Domain 1: Elements** | **InterfaceMF (Infilled Frames)** | 4 files | **High** | Frame elements, mixed kinematics | **High** | **Phase 2** |
| **Domain 1: Elements** | **Joint Elements (Frame Hinges)** | 2 files | **Medium** | Rotational hysteretic spring laws | **Medium** | **Phase 2** |
| **Domain 2: Materials** | **ConcreteMaterial (Kent-Park/Mander)**| 4 files | **Medium** | Fiber section integration | **High** | **Phase 2** |
| **Domain 2: Materials** | **SteelMaterial (Menegotto-Pinto)** | 3 files | **Low-Med** | Uniaxial hysteretic cyclic laws | **High** | **Phase 2** |
| **Domain 2: Materials** | **MomentCurvature Hinges** | 2 files | **Medium** | Concentrated plastic hinge state | **Medium** | **Phase 2** |
| **Domain 5: Special** | **SectionBuilder 2D Fiber Mesher** | 6 files | **High** | 2D Delaunay meshing (Triangle) | **High** | **Phase 2** |
| **Domain 4: Solvers** | **Dynamic Time-History Solver** | 3 files | **High** | Dynamic state vectors, transient loop | **Med-High** | **Phase 3** |
| **Domain 4: Solvers** | **Transient Integrators (Newmark/HHT)**| 6 files | **High** | Effective dynamic stiffness $\mathbf{K}_{\text{eff}}$ | **Med-High** | **Phase 3** |
| **Domain 4: Solvers** | **Viscous Damping (Rayleigh)** | 3 files | **Medium** | Modal frequencies calibration | **Medium** | **Phase 3** |
| **Domain 4: Solvers** | **Accelerogram Input Handling** | 3 files | **Low-Med** | Ground acceleration time stepping | **Medium** | **Phase 3** |
| **Domain 2: Materials** | **FiberMaterial (FRP/TRM Debonding)** | 4 files | **Medium** | Cohesive shear-slip interface laws | **Medium** | **Phase 3** |
| **Domain 3: Loads & BCs** | **Moving Vehicle Train Generator** | 5 files | **Medium** | Lane spline projection algorithms | **Medium** | **Phase 3** |
| **Domain 1: Elements** | **Vertex (3D Corner Macro-Block)** | 3 files | **Med-High** | 3D multi-plane afference mapping | **Medium** | **Phase 3** |
| **Domain 1: Elements** | **Slab Elements (DKT Shell/Plate)** | 5 files | **High** | Plate bending stiffness integration | **Med-High** | **Phase 4** |
| **Domain 1: Elements** | **Solid Continuum (8-node Brick)** | 5 files | **Very High** | 3D continuum B-matrix, 3D plasticity | **Medium** | **Phase 4** |
| **Domain 1: Elements** | **InterfacePoligonal (3D Contact)** | 2 files | **High** | 3D Solid elements, 3D polygon mesh | **Medium** | **Phase 4** |
| **Domain 2: Materials** | **ElasticIsotropicMaterial (3D)** | 1 file | **Low** | 3D Solid continuum elements | **Medium** | **Phase 4** |
| **Domain 4: Solvers** | **Seismic Response Spectra (NTC18)** | 7 files | **Medium** | Italian geographic hazard database | **High** | **Phase 5** |
| **Domain 5: Special** | **Vulnerability Assessment (N2/$\zeta_E$)** | 4 files | **Medium** | Bilinear idealization, spectra | **High** | **Phase 5** |
| **Domain 5: Special** | **AutoCAD DXF Geometry Importer** | 2 files | **Low-Med** | DXF polyline/face parsing | **Medium** | **Phase 5** |
| **Domain 5: Special** | **Adaptic IO Converter** | 9 files | **High** | External Adaptic executable | **Low** | *Do Not Port* |
| **Domain 5: Special** | **Enterprise SQL Server DB** | 2 files | **High** | Microsoft SQL Server client | **Low** | *Do Not Port* |

---

### 7.2 Phased Strategic Porting Roadmap

Based on engineering utility and prerequisite dependencies, a structured 5-phase expansion roadmap is established:

```
                           RECOMMENDED 5-PHASE EXPANSION ROADMAP
 
  PHASE 1: Code Pushover & Foundations (Months 1–3)
  ├── Inverted Triangular Pushover Distribution
  ├── Single-Mode and Multi-Mode Modal Pushover Distribution
  ├── Floor-Shear Load Pattern (ShearFloor)
  └── Foundation Restraint Impedance Refresh & Multi-Point Constraints (Link)
       ▼
  PHASE 2: Frames & Mixed Structural Systems (Months 4–7)
  ├── 3D Timoshenko Beam-Column Element (Frame)
  ├── Uniaxial Tie-Rods and Cables (Truss)
  ├── Macro-Frame Infill Boundary Interface (InterfaceMF)
  ├── SectionBuilder 2D Cross-Section Fiber Mesher
  └── ConcreteMaterial (Kent-Park/Mander) & SteelMaterial (Menegotto-Pinto)
       ▼
  PHASE 3: Transient Dynamics & Advanced Retrofit (Months 8–11)
  ├── Nonlinear Dynamic Time-History Solver (DynamicNonLinearAnalysis)
  ├── Implicit Transient Integrators (Newmark-β, Hilber-Hughes-Taylor HHT-α)
  ├── Viscous Rayleigh Damping Matrix Assembly
  ├── Accelerogram Ground Motion Loading
  └── FRP / TRM Composite Overlay & Debonding Laws (FiberMaterial)
       ▼
  PHASE 4: Slabs & 3D Continuum Solid Mechanics (Months 12–16)
  ├── 4-Node DKT Shell / Plate Bending Element (Slab)
  ├── Orthotropic Flexible Diaphragms & Horizontal Load Distribution
  ├── 8-Node Hexahedral Continuum Macro-Element (Solid)
  └── 3D Polygonal Contact Interfaces (InterfacePoligonal)
       ▼
  PHASE 5: Regulatory Compliance & CAD Interoperability (Months 17–19)
  ├── Italian NTC2008 / NTC2018 Code Response Spectra Generator
  ├── Automated N2 Capacity Spectrum Method & Bilinear Curve Idealization
  ├── Seismic Risk Index Evaluation (Method A & Method B: ζ_E, α_S)
  └── AutoCAD DXF Geometry Model Importer
```

#### Phase 1: Advanced Pushover Distributions & Foundation Impedance (P1, Low-Medium Complexity)
- **Objective**: Complete the standard seismic pushover suite required by Eurocode 8 and Italian Building Code (NTC2018) for existing masonry buildings.
- **Key Deliverables**:
  1. `histra.solver.pushover_patterns`: Implements `Triangular` and `Modal` lateral load distribution generators. Enables automatic modal force vector derivation from completed modal analyses without leaving Python process memory.
  2. `histra.solver.floor_shear`: Implements `ShearFloor` proportional load application.
  3. `histra.elements.link`: Implements rigid and elastic multi-point constraints (MPC) for rigid floor diaphragm enforcement.
  4. Non-rigid boundary restraint refresh supporting foundation impedance updates in multi-stage analysis chains.

#### Phase 2: Frames, Ties & Mixed Macro-Frame Systems (P2, Medium-High Complexity)
- **Objective**: Enable assessment of mixed masonry-frame structures, reinforced concrete buildings with masonry infills, and historical masonry buildings with iron tie-rods.
- **Key Deliverables**:
  1. `histra.elements.truss`: 2-node 3D tension/compression tie-rod element modeling iron ties (*catene*) with slack-in-compression capability.
  2. `histra.elements.frame`: 2-node 3D Timoshenko beam-column element with distributed fiber cross-sections.
  3. `histra.elements.interface_mf`: Macro-Frame contact interface coupling beam deflection to masonry panel boundary edges.
  4. `histra.materials.concrete` & `histra.materials.steel`: Kent-Park, Mander, and Menegotto-Pinto constitutive laws.
  5. `histra.preprocessing.section_builder`: 2D polygonal cross-section fiber mesher with Triangle.NET-equivalent Delaunay triangulation.

#### Phase 3: Transient Nonlinear Dynamics & Damping (P3, High Complexity)
- **Objective**: Deliver full time-history earthquake simulation capability.
- **Key Deliverables**:
  1. `histra.solver.transient_integrator`: Base class managing dynamic velocity, acceleration, and energy balance.
  2. `histra.solver.newmark` & `histra.solver.hht`: Implicit Newmark-$\beta$ and HHT-$\alpha$ dynamic integrators.
  3. `histra.solver.damping`: Rayleigh damping matrix assembly ($\mathbf{C} = \alpha_M \mathbf{M} + \beta_K \mathbf{K}_T$) with automatic calibration from modal analysis frequencies.
  4. `histra.io.accelerogram`: Earthquake ground acceleration record reader and baseline correction.
  5. `histra.materials.fiber_composite`: FRP/TRM debonding and delamination models for structural retrofitting.

#### Phase 4: Slab Elements & 3D Continuum Mechanics (P4, Very High Complexity)
- **Objective**: 3D continuum modeling for massive bridge piers, thick abutments, and flexible floor diaphragms.
- **Key Deliverables**:
  1. `histra.elements.slab`: 4-node flat shell combining membrane action and DKT plate bending.
  2. `histra.elements.solid`: 8-node hexahedral continuum macro-element with 3D Mohr-Coulomb / Drucker-Prager plasticity.
  3. `histra.elements.interface_poligonal`: 3D arbitrary polygonal contact interface.

#### Phase 5: Regulatory Compliance & CAD Interoperability (P5, Medium Complexity)
- **Objective**: Automate engineering compliance certification and CAD workflow integration.
- **Key Deliverables**:
  1. `histra.standards.ntc2018`: Italian NTC2008/NTC2018 and Eurocode 8 elastic and design response spectrum generator with Italian geographic hazard lookup.
  2. `histra.postprocessing.vulnerability`: Automated N2 capacity spectrum solver, equivalent SDOF bilinear curve fitting, and seismic risk index calculation ($\zeta_E = d_u^* / d_{\max}^*$ and $\alpha_S = PGA_C / PGA_D$).
  3. `histra.io.dxf`: AutoCAD DXF polyline/face importer generating native HiStrA model geometry.

---

### 7.3 Conclusion & Audit Certification

1. **Definitive Scope Demarcation**:
   This catalog definitively proves that `histra-python`'s omissions are not arbitrary or unintentional gaps; they represent a principled, disciplined boundary confining the V1 engine to the Discrete Macro-Element Method for masonry structures.
2. **Robust Preflight Enforcement**:
   Every unported element, material, load generator, and solver option is rigorously intercepted by fail-closed preflight checks in `histra/io/hr_loader.py` and `histra/solver/capabilities.py`. In production, 100% of executed elements are verified to be compiled Numba backends.
3. **Actionable Future Roadmap**:
   The 5-phase expansion roadmap establishes a clear, dependency-ordered engineering blueprint for future development teams seeking to expand `histra-python` into mixed frame-masonry structures, dynamic earthquake time-histories, 3D continuums, and automated regulatory seismic risk certification.

---
