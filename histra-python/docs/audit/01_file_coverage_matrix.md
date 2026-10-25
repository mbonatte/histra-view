# Chapter 1: Master Numerical Core File-by-File Coverage Matrix
## HiStrA C# Original (`C#_Original/`) vs. HiStrA Python (`histra/`)

**Author**: Forensic Audit Team (`worker_m1_gen2`)  
**Status**: Authoritative Release Gate Audit Deliverable  
**Scope**: Complete, exhaustive line-by-line and file-by-file mapping of the numerical modeling and solver core between the original C# HiStrA engine and the modern headless Python implementation.

---

## 1. Executive Summary & Codebase Architecture

### 1.1 Purpose and Background
The `histra-python` codebase is an in-process, headless Python implementation of the Discrete Macro-Element Method (DMEM) for nonlinear static pushover and modal eigenvalue analysis of masonry and historical structures. It ports the authoritative numerical modeling core of the C# HiStrA structural engineering suite (originally developed by SirioSoft / University of Catania).

This survey establishes the complete, authoritative file-by-file correspondence between the original C# codebase (`C#_Original/`) and the modern Python implementation (`histra/`). It provides the foundational ground truth for Chapter 1 (`01_file_coverage_matrix.md`) of the master audit suite.

### 1.2 Structure of `C#_Original/`
The original C# codebase is an enterprise .NET Framework 4.8 desktop application composed of multiple Visual Studio projects, WPF/WinForms user interfaces, DirectX/MonoGame rendering viewports, and SQLite database storage.

A critical structural finding revealed by this survey is the directory organization of `C#_Original/`:
1. **Root Projects and Namespaces**:
   - `ModelLibrary.csproj`: The domain data model, geometry generators, meshers, constitutive laws, and computational elements.
   - `SolverRuntime.csproj`: The numerical solver runtime, integrators, line searches, equilibrium solvers, and modal analysis.
   - `MatrixManager.csproj`: Sparse matrix representations, linear system assembly, and SuiteSparse UMFPACK P/Invoke bindings.
   - `SectionBuilderCore.csproj`: Cross-section geometry and fiber integration for beam/column elements.
   - `AdapticIO.csproj`: File export/import converter for the Adaptic finite element solver.
   - `UtilityLibrary.csproj`: Mathematical tools, combinatorics, units, and domain enumerations (`UtilityLibrary.Tipi`).
   - `SirioCommon.csproj`: Corporate application framework (licensing, PDF generation, general utilities).
   - `WindowsHistra.csproj`, `WindowsRuntime.csproj`, `IDEcontrols.csproj`: Desktop graphical user interfaces, ribbons, OpenGL/DirectX viewports, and CAD dialogs.
2. **Physical Duplication in Repository Export**:
   - In `C#_Original/`, the projects `ModelLibrary` and `SolverRuntime` exist both as top-level directories containing nested namespace directories and as flat peer directories at the repository root.
   - For example, `C#_Original/Objects/Quad.cs` is identical (byte-for-byte SHA256 match) to `C#_Original/ModelLibrary/Objects/Quad.cs`.
   - Across the entire `C#_Original/` directory tree, there are **1,854** `.cs` file paths on disk, representing **1,419** unique file contents. Exactly **428** duplicate paths represent redundant mirror copies inside `ModelLibrary/` and `SolverRuntime/`.
   - For the purposes of this audit, all analyses are performed against the canonical unique file definitions.

### 1.3 Core vs Secondary vs Out-of-Scope Classification
The C# codebase is divided into three major architectural tiers:
- **Core Numerical and Modeling Engine (426 unique files)**: Files directly governing structural definitions, discrete macro-element formulations, material constitutive models, load applications, matrix assembly, solver integrators, line searches, and eigenvalue solvers across `SolverRuntime`, `MatrixManager`, `SectionBuilderCore`, `AdapticIO`, `ModelLibrary`, `ModelManagement`, and `Objects`.
- **Secondary and Utility Infrastructure (576 unique files)**: Auxiliary tools including `UtilityLibrary` / `UtilityLibrary.Tipi` (250 files), `SirioCommon` (304 files), `CommonObject*` (10 files), and `DBManagement*` (12 files).
- **Out-of-Scope Desktop GUI & Platform (420 unique files)**: Interactive graphical editors, WPF controls, ribbons, DirectX/MonoGame rendering viewports, and Excel COM automation (`IDEcontrols`, `WindowsHistra`, `WindowsRuntime`, `ExcelLibrary.Excel`, `HiStrA.Plugins`, `SeismicVulnerabiltyLibrary`, `UnityServiceClasses`).

### 1.4 Global Classification Summary of C# Core Files
Every one of the 426 C# core files has been audited and classified into one of four standard categories:
1. **Ported (131 files, 30.8%)**: Fully implemented in Python with verified numerical and behavioral parity against C# benchmarks and SQLite reference databases.
2. **Partial (15 files, 3.5%)**: Partially implemented; relevant data structures or subsets required for DMEM masonry V1 are ported, while non-V1 features or unneeded methods are omitted.
3. **Intentional Deviation (4 files, 0.9%)**: Refactored or adapted to resolve documented C# defects, enforce memory safety, or replace slow object graphs with high-performance vectorized Numba kernels.
4. **Unimplemented (248 files, 58.2%)**: Capabilities outside the V1 Discrete Macro-Element Method masonry boundary (e.g., Frame elements, Slab elements, Solid elements, Truss elements, transient nonlinear dynamics, CAD meshing wizards).
5. **Out-of-Scope (28 files, 6.6%)**: Project metadata (`AssemblyInfo.cs`), desktop GUI dialogs, and presentation helpers located within core folders.

| Classification | File Count | Percentage | Description |
|---|---|---|---|
| **Ported** | 131 | 30.8% | Fully ported to Python with verified parity |
| **Partial** | 15 | 3.5% | Relevant V1 subset implemented |
| **Intentional Deviation** | 4 | 0.9% | Redesigned for Numba vectorization, safety, or C# defect fix |
| **Unimplemented** | 248 | 58.2% | Outside V1 DMEM masonry scope (Frames, Slabs, Dynamics, CAD) |
| **Out-of-Scope** | 28 | 6.6% | .NET metadata, GUI dialogs, CAD display helpers |
| **Total C# Core Files** | **426** | **100.0%** | **Exhaustive core inventory** |

### 1.5 Python Codebase Summary (`histra/`)
The `histra-python` production codebase consists of **117 Python files** totaling **35,680 lines of code** (excluding tests, benchmarks, and caches):
- `histra/model` (11 files, 729 LOC): Core structural domain entities (Model, Node, Quad, Interface, Restraint, MasonryMaterial, Loads).
- `histra/elements` (9 files, 2,590 LOC): Discrete macro-element formulations (Quad panel, Interface joint, kinematics, loads).
- `histra/springs` (10 files, 2,288 LOC): 1D mechanical spring models (Hysteretic, Coulomb03, Elastic, MultiLinear).
- `histra/preprocessing` (11 files, 4,676 LOC): Fresh mesh preparation, 6-face contact geometry, fibre discretization, and spring assignment.
- `histra/solver` (38 files, 14,373 LOC): Solver facade, integrators (LoadControl, ArcLength), Newton algorithms, line search, session state machine, and matrix assembly.
- `histra/solver/hysteretic_kernels` (6 files, 3,068 LOC): Numba-compiled vector kernels executing the numerical hot paths.
- `histra/types` (10 files, 733 LOC): Domain data structures, enums, linear system wrappers, and UMFPACK bindings.
- `histra/io` (3 files, 1,119 LOC): HRX XML model loader and C# SQLite results reader.
- `histra/validation` (2 files, 370 LOC): Modal analysis and numerical validation helpers.
- `histra/tools` (14 files, 5,300 LOC): Release gate benchmarks, CLI runners, and differential SQLite comparison tools.
- `histra` root (3 files, 434 LOC): Public API facade, CLI entry point, and postprocessing utilities.

---

## 2. Comprehensive Python-to-C# Master Correspondence Matrix

This matrix maps **every production Python file** (117 files) to its C# source file(s), class(es), method(s), and architectural role.


### 2.1 Top-Level Package Root

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/__init__.py` | 125 | `Public API facade (aggregates SolverRuntime, ModelLibrary, ModelManagement)` | Model, AnalysisSession, solve_modal_analysis, run_python_solver_job / Package root exports | High-level package entry point exposing core modeling, solving, session, and diagnostic APIs. |
| `histra/__main__.py` | 78 | `SolverRuntime/Program.cs` | Program / Main | CLI dispatcher routing commands to histra.tools modules. |
| `histra/postprocessing.py` | 231 | `ModelManagement/ResponseOperations.cs, Objects.Analyses/Response.cs` | ResponseOperations, Response / GetCurveValues, ExtractDisplacements, ExtractReactions | Postprocessing utility extracting capacity curves, reactions, and model point displacements from results. |

### 2.2 histra/model (Structural Domain Model)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/model/__init__.py` | 34 | `ModelLibrary/Model.cs, Objects/` | Model, Node, Quad, Interface, Restraint, MasonryMaterial / Domain model re-exports | Public re-exports for structural domain entities. |
| `histra/model/_types.py` | 6 | `UtilityLibrary.Vector3F/Vector3F.cs, Objects/AfferenceMatrixItem.cs` | Vector3F, AfferenceMatrixItem / Data structures | Internal re-exports for geometric Point, AfferenceEntry, and XML attribute utilities. |
| `histra/model/interface.py` | 5 | `Objects/Interface.cs, Objects/InterfaceState.cs` | Interface, InterfaceState / Class aliases | Domain facade re-exporting Interface and InterfaceState from histra.elements. |
| `histra/model/load.py` | 214 | `Objects.Loads/LoadCombination.cs, LoadCondition.cs, StaticLoad.cs, PointLoadElement.cs, AreaLoadElement.cs` | LoadCombination, LoadCombinationItem, LoadCondition, StaticLoad, Force / GetCoefficient, IsGravity, Load XML deserialization | Load cases, combinations, gravity multipliers, and nodal force representations. |
| `histra/model/masonry_material.py` | 112 | `Objects.Material/MasonryMaterial.cs, MaterialBase.cs` | MasonryMaterial, MaterialBase / GetE, GetG, GetWeight, Value dictionary access | Masonry material definition containing elastic moduli, specific weight, friction, cohesion, and cracking parameters. |
| `histra/model/model.py` | 57 | `ModelLibrary/Model.cs, Objects/BaseObject.cs` | Model / Collections initialization, entity lookup dictionaries | Central model entity aggregating nodes, quads, interfaces, restraints, materials, and load combinations. |
| `histra/model/node.py` | 77 | `Objects/Node.cs, Objects.ComputationalElements/NodeC.cs` | Node, NodeC, SlaveElement / Node constructor, dof mapping, XML deserialization | Structural node entity holding Cartesian coordinates, degrees of freedom, and slave-node relationships. |
| `histra/model/quad.py` | 5 | `Objects/Quad.cs, Objects.ElementStates/QuadState.cs` | Quad, QuadState / Class aliases | Domain facade re-exporting Quad and QuadState from histra.elements. |
| `histra/model/restraint.py` | 56 | `Objects/Restraint.cs, Objects/LineReference.cs` | Restraint, LineReference / Restraint constructor, boundary condition flags, XML deserialization | Nodal boundary restraint defining fixed, free, and spring-supported degrees of freedom. |
| `histra/model/shear_law.py` | 135 | `Objects.ConstitutiveLaw/ConstitutiveLawCoulomb.cs, ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs` | ConstitutiveLawCoulomb, ConstitutiveLawOperations / ConstitutiveLawShearType enum, SetShearConstitutiveLaw | Shear constitutive law definitions (Linear, Mohr-Coulomb, Cacovic, Non-linear Turnsek-Cacovic). |
| `histra/model/spring.py` | 28 | `Objects/Spring.cs, SpringLinearElastic.cs, SpringCoulomb03.cs, SpringHysteretic.cs, SpringMultiLinearPlastic.cs` | Spring, SpringElastic, SpringCoulomb03, SpringHysteretic, SpringMultiLinear / Re-exports | Domain facade re-exporting spring classes from histra.springs. |

### 2.3 histra/elements (Discrete Macro-Elements)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/elements/__init__.py` | 11 | `Objects/Quad.cs, Objects/Interface.cs` | Quad, Interface / Element re-exports | Package initialization for DMEM macro-elements. |
| `histra/elements/interface.py` | 979 | `Objects/Interface.cs` | Interface / ComputeDn, ComputeAreaCorr, InterfacciaVincolataComputed, GetDI, SetSpring, Commit, Revert | Discrete Macro-Element Interface joint connecting Quads or boundary restraints via distributed nonlinear springs. |
| `histra/elements/interface_state.py` | 66 | `Objects/InterfaceState.cs` | InterfaceState / InitFromInterface, ComputeDU, Commit, RevertToLastCommit, RevertToStart | Runtime displacement and internal force state tracking for Interface contact joints. |
| `histra/elements/quad.py` | 400 | `Objects/Quad.cs` | Quad / SetNonLinearProperties, SetResistingForce, GetResistingForce, ComputeVolume, GetTangentStiffnessMatrix | Discrete Macro-Element Quad representing masonry panels with internal diagonal shear and bending springs. |
| `histra/elements/quad_geometry.py` | 287 | `Objects/Quad.cs` | Quad (QuadGeometryMixin) / D_Alfa_2D_Diag, D_Diag_2D_Alfa, cosAlfa, Compute_K, GetDiagonalStiffness, Array2, Array3, Array4 | Kinematics and geometric transformations for Quad elements: diagonal angles, orientation cosines, and stiffness. |
| `histra/elements/quad_kernels.py` | 222 | `Objects/Quad.cs` | Quad / SetNonLinearProperties (yield search iteration) | Numba-accelerated and scalar yield-point search algorithms for Quad diagonal springs. |
| `histra/elements/quad_loads.py` | 419 | `Objects/Quad.cs, ModelManagement.ComputationalElementsOperations/IntrinsicOperations.cs` | Quad (QuadLoadsMixin) / ComputeStaticLoadInternal, ComputeLineLoadInternal, ComputeSelfWeightLoad, Intrinsic | Static load integration over Quad elements: self-weight gravity forces, uniform area loads, and edge line loads. |
| `histra/elements/quad_state.py` | 11 | `Objects.ElementStates/QuadState.cs` | QuadState / Commit, RevertToLastCommit, RevertToStart | Runtime deformation and force state tracking for Quad elements across Newton iterations. |
| `histra/elements/quad_static_load.py` | 195 | `Objects/Quad.cs` | Quad / ComputeStaticLoadInternal (numerical integration) | High-performance vectorized Quad area load numerical integration matching C# 32-bit floating point precision. |

### 2.4 histra/springs (1D Mechanical Springs)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/springs/__init__.py` | 19 | `Objects/Spring.cs` | Spring / Re-exports | Package initialization for 1D nonlinear springs. |
| `histra/springs/base.py` | 159 | `Objects/Spring.cs` | Spring / GetK, GetForce, GetIncrForce, GetDisplacement, SetTrialStrain, Commit, RevertToStart, RevertToLastCommit | Abstract base class for all DMEM 1D mechanical spring models. |
| `histra/springs/coulomb.py` | 21 | `Objects/SpringCoulomb02.cs` | SpringCoulomb02 (SpringCoulomb) / GetK, GetForce, SetTrialStrain | Legacy Mohr-Coulomb friction spring model. |
| `histra/springs/coulomb03.py` | 226 | `Objects/SpringCoulomb03.cs` | SpringCoulomb03 / SetEnvelope, TauLimite, SetTrialStrainTakeda, SetTrialStrainInitial | Advanced Mohr-Coulomb friction spring with normal-stress-dependent shear strength and degrading cohesion. |
| `histra/springs/coulomb03_envelope.py` | 263 | `Objects/SpringCoulomb03.cs` | SpringCoulomb03 (Coulomb03EnvelopeMixin) / SetEnvelope, TauLimite, PosEnvlpStressTakeda, NegEnvlpStressTakeda, PosEnvlpTangentTakeda | Shear stress envelope calculation, friction angle decay, and tangential stiffness for Coulomb03. |
| `histra/springs/coulomb03_state.py` | 678 | `Objects/SpringCoulomb03.cs` | SpringCoulomb03 (Coulomb03StateMixin) / SetTrialStrainTakeda, SetTrialStrainInitial, PositiveIncrementTakeda, NegativeIncrementTakeda | State machine and reversal logic for Coulomb03 springs (Takeda Quad diagonals and Initial Interface sliding). |
| `histra/springs/elastic.py` | 66 | `Objects/SpringLinearElastic.cs` | SpringLinearElastic (SpringElastic) / GetK, GetForce, SetTrialStrain, Commit, Revert | Linear elastic spring model with constant stiffness in tension and compression. |
| `histra/springs/hysteretic.py` | 808 | `Objects/SpringHysteretic.cs` | SpringHysteretic / SetTrialStrain, GetForce, GetTangent, Commit, RevertToLastCommit, RevertToStart | Multi-envelope axial hysteretic fiber spring supporting elastic, hardening, softening, exponential, and parabolic laws. |
| `histra/springs/multilinear.py` | 26 | `Objects/SpringMultiLinearPlastic.cs` | SpringMultiLinearPlastic (SpringMultiLinear) / GetForce, GetK, SetTrialStrain | Piecewise multi-linear plastic spring with user-defined backbone curve. |
| `histra/springs/registry.py` | 22 | `Objects/Spring.cs` | Spring (Factory) / SpringFromXml, RegisterSpring | Deserialization registry mapping HRX XML spring types to Python spring classes. |

### 2.5 histra/preprocessing (Mesh Preparation & Topology)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/preprocessing/__init__.py` | 27 | `ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs` | ComputationalElementsOperations / Re-exports | Preprocessing package initialization. |
| `histra/preprocessing/afference.py` | 711 | `ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs, Objects/Quad.cs` | ComputationalElementsOperations, Quad / SetAfferenceMatrixQuad, SetAfferenceMatrixInterface, ComputeAfference, WarpingVector | Nodal afference matrix assembly and out-of-plane warping vector calculations mapping element DOFs to global nodes. |
| `histra/preprocessing/constitutive_laws.py` | 372 | `Objects.ConstitutiveLaw/ConstitutiveLawHysteretic.cs, ConstitutiveLawCoulomb.cs, ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs` | ConstitutiveLawHysteretic, ConstitutiveLawCoulomb, ConstitutiveLawOperations / FlexLaw, CoulombLaw, ValidateMasonryMaterialEnums | Constitutive law configurations: hysteretic tension/compression envelopes and Mohr-Coulomb shear parameters. |
| `histra/preprocessing/contact_geometry.py` | 922 | `ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs, InterfaceOperations.cs` | ComputationalElementsOperations, InterfaceOperations / ComputeAfferenceInterface, ComputeInterfaceGeometry, ComputeFaceFaceIntersection | Geometric contact detection across 6 Quad faces: 3D bounding boxes, polygon clipping, and interface area calculation. |
| `histra/preprocessing/errors.py` | 5 | `ModelManagement/ModelOperations.cs` | ModelOperations / Exceptions | Custom exceptions for model preparation and mesh validation failures. |
| `histra/preprocessing/fibre_geometry.py` | 524 | `ModelManagement.ComputationalElementsOperations/InterfaceOperations.cs` | InterfaceOperations / ComputeFibers, ComputeFiberAreas, BilinearMapping, InverseBilinear | Interface discretization into transverse fiber cells: bilinear mapping, cell area computation, and Gauss integration points. |
| `histra/preprocessing/material_selection.py` | 194 | `ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs, ModelManagement.Material/MasonryMaterialOperations.cs` | ConstitutiveLawOperations, MasonryMaterialOperations / SetShearConstitutiveLaw, BlendCoulombLaws, InterfaceSlidingLaw | Material parameter resolution and blending across interface sides (harmonic/series stiffness, minimum friction/cohesion). |
| `histra/preprocessing/prepare_model.py` | 321 | `ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs` | ComputationalElementsOperations / PrepareBuildInterface, PreBuildInterface, ResetComputationalElements, PrepareModel | Master orchestrator for model preprocessing: strips serialized objects, regenerates contact topology and springs. |
| `histra/preprocessing/spring_assignment.py` | 589 | `ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs, Objects/Interface.cs` | ComputationalElementsOperations, Interface / SetSpring, CreateInterfaceSprings, RebuildInterfaceSprings | Assigning transverse and sliding springs to interfaces, combining spring properties in series, and foundation restraint assignment. |
| `histra/preprocessing/spring_factory.py` | 858 | `ModelManagement.ComputationalElementsOperations/SpringOperations.cs` | SpringOperations / CreateSpring, ConfigureSpring, ConfigureHysteretic, ConfigureCoulomb | Mechanical spring instantiation and parameter calibration from geometric afference and constitutive laws. |
| `histra/preprocessing/validation.py` | 153 | `SolverRuntime/ModelManager.cs` | ModelManager / Pre-solve validation checks | Solver readiness inspections verifying afference completeness, spring existence, and preprocessed topology validity. |

### 2.6 histra/solver (Numerical Solver Core & Orchestration)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/solver/__init__.py` | 161 | `SolverRuntime/` | ModelManager, Program / Re-exports | Solver package initialization. |
| `histra/solver/arc_length.py` | 784 | `SolverRuntime.Integrator/ArcLength.cs, ArcLength1.cs` | ArcLength, ArcLength1 / NewStep, Update, GetInitialTimeAndForce, ComputeDeltaLambda | Arc-Length continuation integrator supporting cylindrical/spherical constraint equations and adaptive step size adjustments. |
| `histra/solver/assembler.py` | 747 | `SolverRuntime/ModelManager.cs` | ModelManager / BuildStiffnessMatrix, AssembleGlobalMatrix, AssembleAfference | Global stiffness matrix assembler projecting Quad and Interface tangent matrices into sparse CSC linear systems. |
| `histra/solver/backend_api.py` | 240 | `SolverRuntime/Program.cs` | Program / RunPythonSolverJob, PythonAnalysisRequest, PythonAnalysisResult | High-level job execution API supporting chained requests, mutation specs, and deadline enforcement. |
| `histra/solver/backend_coverage.py` | 311 | `Architectural requirement (Zero unmanaged objects)` | Coverage validator / InspectSolverBackendCoverage, RequireCompiledBackend | Production runtime guard verifying 100% compiled Numba coverage (fails closed on unmanaged objects). |
| `histra/solver/cancellation.py` | 46 | `SolverRuntime/Program.cs` | Program / CancellationCheck, ProcessLock | Process-wide execution lock and cooperative cancellation checkpoints across solver steps and iterations. |
| `histra/solver/capabilities.py` | 426 | `SolverRuntime.NumericalProcedure/EquiSolnAlgoFactory.cs, IntegratorFactory.cs` | EquiSolnAlgoFactory, IntegratorFactory / InspectSolverCapabilities, RequireSupported | Preflight capability validator rejecting unsupported elements, enums, or algorithms before solving. |
| `histra/solver/continuation.py` | 588 | `SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs` | StaticNonLinearAnalysis / AlsLoop, CommitState, DomainChangeRequiresTangentRefresh | Continuation loop orchestrating Newton-Raphson equilibrium iterations and Arc-Length continuation checks. |
| `histra/solver/diagnostics.py` | 402 | `SolverRuntime/Program.cs, EventLoggerAndDebug` | Program, EventLogger / TraceResiduals, DumpParityTraces | Detailed numerical execution tracer capturing step residuals, displacement deltas, and UMFPACK parity logs. |
| `histra/solver/equilibrium.py` | 185 | `SolverRuntime.ConvergenceTest/CTestNormUnbalance.cs` | CTestNormUnbalance / AppliedForceResultant, EquilibriumAudit | Independent physical force equilibrium auditor verifying applied vs resisting forces and reacting base reactions. |
| `histra/solver/equilibrium_audit.py` | 147 | `SolverRuntime.ConvergenceTest/CTestNormUnbalance.cs` | CTestNormUnbalance / RunEquilibriumAudit | Equilibrium audit runner executing post-step equilibrium safety validations. |
| `histra/solver/hysteretic_batch.py` | 67 | `SolverRuntime/ModelManager.cs` | ModelManager / Vectorized domain update | Batch evaluation data buffers and memory layouts for high-throughput compiled spring kernel evaluation. |
| `histra/solver/hysteretic_runtime.py` | 2819 | `SolverRuntime/ModelManager.cs` | ModelManager / UpdateDomain, ComputeInternalForces | Numba-compiled vectorized runtime manager replacing C# element-by-element loops with contiguous array evaluations. |
| `histra/solver/hysteretic_topology.py` | 160 | `SolverRuntime/ModelManager.cs` | ModelManager / Spring-to-DOF mapping | Precomputed flat indexing structures mapping local element springs to global degrees of freedom for batch execution. |
| `histra/solver/incremental_integrator.py` | 223 | `SolverRuntime.Integrator/IncrementalIntegrator.cs, StaticIntegrator.cs` | IncrementalIntegrator, StaticIntegrator / Step, Iteration, UpdateGeometricStiffness, NewStep | Abstract base classes for incremental nonlinear integrators managing step counters, geometric P-Delta updates, and load factors. |
| `histra/solver/interface_material.py` | 196 | `Objects/Interface.cs, ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs` | Interface, ComputationalElementsOperations / SetSpring, ChangeInterfaceMaterials | Interface material mutation at committed analysis boundaries (e.g. pier scour modeling) with state preservation. |
| `histra/solver/line_search.py` | 323 | `SolverRuntime.LineSearch/LineSearch.cs, BisectionLineSearch.cs, RegulaFalsiLineSearch.cs, SecantLineSearch.cs, InitialInterpolatedSearch.cs` | LineSearch, BisectionLineSearch, RegulaFalsiLineSearch, SecantLineSearch, InitialInterpolatedSearch / Search, FindRoot, CSharpDot | Line search root-finding algorithms minimizing residual energy along the Newton search direction. |
| `histra/solver/load_assembly.py` | 388 | `SolverRuntime/ModelManager.cs, ModelManagement.Load/ModelLoadOperations.cs` | ModelManager, ModelLoadOperations / AssembleLoadsVector, GenerateLineLoads, GetCombCoeffGravity | Load vector assembler combining self-weight, nodal point loads, edge line loads, and combination multipliers. |
| `histra/solver/load_control.py` | 152 | `SolverRuntime.Integrator/LoadControl.cs` | LoadControl / NewStep, Update, DomainChanged, GetInitialTimeAndForce | Static load-control integrator incrementing proportional load factors monotonically. |
| `histra/solver/mass_matrix.py` | 321 | `SolverRuntime/MassesMatrixOperation.cs, Pseudovectors.cs` | MassesMatrixOperation, Pseudovectors / AssembleMassMatrix, ComputeQuadMass, HexahedronInversion | Mass matrix assembly integrating Quad element masses into global translational degrees of freedom. |
| `histra/solver/modal.py` | 805 | `SolverRuntime.AnalysisProcedure/ModalAnalysis.cs, SolverRuntime/SubSpaceIteration2.cs` | ModalAnalysis, SubSpaceIteration2 / SolveModalAnalysis, SubSpaceIteration, FrequencyCalculation, ModeNormalization | Modal eigenvalue solver performing subspace iteration, mode shape extraction, and MAC parity validation. |
| `histra/solver/model_manager.py` | 516 | `SolverRuntime/ModelManager.cs` | ModelManager / PrepareModel, CreateBrandNewModel, BuildStiffnessMatrix, UpdateDomain, CommitDomain, RevertDomain | Core solver facade managing runtime linear systems, element state transitions, and step coordination. |
| `histra/solver/newton_line_search.py` | 235 | `SolverRuntime.NumericalProcedure/NewtonLineSearch.cs` | NewtonLineSearch / SolveCurrentStep, Line search acceleration | Newton-Raphson solver accelerated by line search step-length scaling. |
| `histra/solver/newton_raphson.py` | 149 | `SolverRuntime.NumericalProcedure/NewtonRaphson.cs` | NewtonRaphson / SolveCurrentStep, Standard/Modified Newton iteration | Newton-Raphson nonlinear equilibrium solver with standard and modified tangent stiffness policies. |
| `histra/solver/nonlinear_setup.py` | 433 | `SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs, SolverParametersOperations.cs` | StaticNonLinearAnalysis, SolverParametersOperations / SetupNonlinearAnalysis, SetInitialState | Initialization routine configuring integrator parameters, convergence tolerances, and initial state vectors. |
| `histra/solver/nonlinear_solver.py` | 11 | `SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs` | StaticNonLinearAnalysis / RunAnalysis, ExecuteStepLoop | Static nonlinear analysis execution pipeline coordinating load incrementation and equilibrium iterations. |
| `histra/solver/nonlinear_step.py` | 433 | `SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs` | StaticNonLinearAnalysis / ExecuteSteps, CutbackTangentAlfa, StepRetry | Adaptive step controller handling convergence cutbacks, step retry strategies, and tangent stiffness updates. |
| `histra/solver/outcomes.py` | 196 | `UtilityLibrary.Tipi/AnalysisStateEnum.cs` | AnalysisStateEnum / AnalysisOutcome, AnalysisStep | Step and analysis outcome enumerations (SUCCESS, DIVERGED, CUTBACK_LIMIT, CANCELLED). |
| `histra/solver/output_projection.py` | 253 | `ModelManagement/ResponseOperations.cs, ModelManagement.ComputationalElementsOperations/ModelPointOperations.cs` | ResponseOperations, ModelPointOperations / ProjectReactions, ProjectDisplacements, ModelPointDisplacement | Projecting global nodal displacements and base reactions into model points and output response curves. |
| `histra/solver/program.py` | 121 | `SolverRuntime/Program.cs` | Program / Log, Progress, CheckCancelled, GetValueGraphAnalysis | Execution coordinator handling logging, progress updates, cancellation signals, and step results recording. |
| `histra/solver/restart.py` | 381 | `SolverRuntime/ModelManager.cs, DBModelManager/dbOutputManager.cs` | ModelManager, dbOutputManager / RestoreState, RestoreSpringTargets | State restoration module restoring element deformations, stresses, and spring history from saved states. |
| `histra/solver/session.py` | 390 | `Objects.Analyses/Analysis.cs (InitialAnalysisKey), DBModelManager/dbModelManager.cs` | Analysis, dbModelManager / Multi-stage dependency execution, state restoration | In-memory stateful multi-analysis execution manager preserving committed constitutive state across chained analyses. |
| `histra/solver/solution_algorithm.py` | 101 | `SolverRuntime.NumericalProcedure/SolutionAlgorithm.cs, EquiSolnAlgo.cs` | SolutionAlgorithm, EquiSolnAlgo / SolveCurrentStep, GetLinearSystem, DomainChanged | Base classes for nonlinear equilibrium solution algorithms. |
| `histra/solver/solve.py` | 246 | `SolverRuntime/Program.cs` | Program / RunAnalysis, SolveStaticNonlinear | High-level entry point function for static nonlinear analysis execution. |
| `histra/solver/solver.py` | 51 | `MatrixManager/MatrixManager/LinearSystem.cs` | LinearSystem / SolveLinear, ComputeResidual, VerifySolution | Sparse linear solver dispatching equation solving to SciPy SuperLU or SuiteSparse UMFPACK. |
| `histra/solver/state_snapshot.py` | 475 | `ModelLibrary/Clone.cs` | Clone / DeepClone | High-speed in-memory state snapshotting copying element and spring committed arrays without deep object graphs. |
| `histra/solver/strategy.py` | 288 | `Independent solver advisor (Domain heuristics)` | SolverStrategyAdvisory / InspectSolverStrategy | Intelligent solver strategy advisor recommending optimal integrator, step size, and line search for a model. |
| `histra/solver/strategy_evidence.py` | 603 | `Independent strategy certification` | ModelStrategyEvidence, CertifiedCandidateEvidence / MatchesAnalysis, ValidateEvidence | Strategy qualification evidence tracking benchmarked convergence and performance. |

### 2.7 histra/solver/hysteretic_kernels (Numba Compiled Numerical Kernels)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/solver/hysteretic_kernels/__init__.py` | 69 | `SolverRuntime/ModelManager.cs` | ModelManager / Kernel re-exports | Compiled hysteretic numerical kernels package initialization. |
| `histra/solver/hysteretic_kernels/interface_coulomb.py` | 321 | `Objects/SpringCoulomb03.cs` | SpringCoulomb03 / EvaluateInitialCoulombBatch, EvaluateElasticSlidingBatch, CommitInitialCoulombBatch | Numba-compiled Mohr-Coulomb sliding contact evaluation for interface distributed shear springs. |
| `histra/solver/hysteretic_kernels/kinematics.py` | 160 | `Objects/Quad.cs, Objects/Interface.cs` | Quad, Interface / MapGlobalToLocal, PrepareQuadKinematics, PrepareInterfaceKinematics | Numba-compiled global-to-local nodal displacement transformation and spring trial strain evaluation. |
| `histra/solver/hysteretic_kernels/quad_takeda.py` | 764 | `Objects/SpringCoulomb03.cs` | SpringCoulomb03 / QuadTauLimit, QuadInterpolatedShearEnergy, QuadTangentReloadT | Numba-compiled Takeda hysteretic shear model for Quad diagonal springs. |
| `histra/solver/hysteretic_kernels/scatter.py` | 359 | `Objects/Quad.cs, Objects/Interface.cs, SolverRuntime/ModelManager.cs` | Quad, Interface, ModelManager / ScatterLocalForces, RefreshGlobalResistingForce | Numba-compiled local-to-global resisting force scattering assembling element forces into global residual vectors. |
| `histra/solver/hysteretic_kernels/transverse.py` | 1395 | `Objects/SpringHysteretic.cs` | SpringHysteretic / PosStress, NegStress, PosTangent, NegTangent | Numba-compiled constitutive stress-strain updates and tangent evaluation for hysteretic transverse fibers. |

### 2.8 histra/types (Types, Linear Systems & Enums)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/types/__init__.py` | 22 | `UtilityLibrary.Tipi/` | Enums and types / Re-exports | Types package initialization. |
| `histra/types/afference_entry.py` | 14 | `Objects/AfferenceMatrixItem.cs` | AfferenceMatrixItem / AfferenceEntry dataclass | Afference entry mapping element local degrees of freedom to global nodal degrees of freedom with geometric weights. |
| `histra/types/convergence_test.py` | 140 | `SolverRuntime.ConvergenceTest/ConvergenceTest.cs, CTestNormUnbalance.cs, CTestNormDispIncr.cs, CTestEnergyIncr.cs` | ConvergenceTest, CTestNormUnbalance, CTestNormDispIncr, CTestEnergyIncr / SetTolerance, SetMaxNumIter, Test | Convergence test specifications (ForceMoment, DispRotation, Work). |
| `histra/types/hysteretic_curve_types.py` | 16 | `UtilityLibrary.Tipi/HystereticTensileCurveTypeEnum.cs, HystereticCompressiveCurveTypeEnum.cs` | HystereticTensileCurveTypeEnum, HystereticCompressiveCurveTypeEnum / Enum definitions | Tensile and compressive backbone curve type enumerations (Elastic, Hardening, Softening, Exponential, Parabolic). |
| `histra/types/integrator_state.py` | 21 | `Objects.Analyses/IntegratorState.cs` | IntegratorState / IntegratorState dataclass | State container storing current load factor lambda, step number, iteration count, and Arc-Length radius. |
| `histra/types/linear_system.py` | 241 | `MatrixManager/MatrixManager/LinearSystem.cs` | LinearSystem / Sumb, GetBNorm, ResetLoadVector, ResetStiffnessMatrix, ResetDisplacementVector | Linear system abstraction managing the global stiffness matrix K, load vector b, and displacement vector x. |
| `histra/types/phase_enum.py` | 17 | `UtilityLibrary.Tipi/PhaseEnum.cs` | PhaseEnum / Enum definition (Elastic, Plastic, Softening, Residual, Crushed) | Constitutive phase enumeration for hysteretic fibers and Mohr-Coulomb contact. |
| `histra/types/point.py` | 25 | `UtilityLibrary.Vector3F/Vector3F.cs, Objects/Node.cs` | Vector3F / Point constructor, FromStr, arithmetic operations | Immutable 3D geometric point class representing coordinates in space. |
| `histra/types/umfpack.py` | 221 | `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/` | NativeMethods, UmfpackControl, UmfpackInfo / FindUmfpackLibrary, UmfpackFactorization, UmfpackNumeric, UmfpackSolve | Ctypes dynamic library bindings to SuiteSparse UMFPACK direct sparse LU solver. |
| `histra/types/xml_utils.py` | 16 | `UtilityLibrary.IO/IO.cs` | XML helpers / _attr, _child_text | XML attribute extraction helpers with default fallbacks and type conversion. |

### 2.9 histra/io (Model Loading & SQLite IO)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/io/__init__.py` | 2 | `ModelLibrary/Model.cs` | Model / Re-exports | IO package initialization. |
| `histra/io/hr_loader.py` | 566 | `ModelLibrary/Model.cs (XML Serialization attributes), Objects/*` | Model, Quad, Interface, Node, MasonryMaterial, LoadCombination / LoadModel, ParseHRX, ParseNodes, ParseQuads, ParseMaterials, ParseLoads | HRX XML parser deserializing HiStrA model geometry, materials, boundary conditions, and analysis definitions. |
| `histra/io/results_reader.py` | 551 | `DBManagement.SQLiteDb/Database.cs, DBModelManager/dbOutputManager.cs` | Database, dbOutputManager / ReadResultsDatabase, GetModelPointDisplacements, GetReactionSums | C# .Results SQLite reader extracting reference displacement and reaction outputs for parity verification. |

### 2.10 histra/validation (Validation Utilities)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/validation/__init__.py` | 13 | `Validation utilities` | Validation / Re-exports | Validation package initialization. |
| `histra/validation/modal_results.py` | 357 | `SolverRuntime.AnalysisProcedure/ModalAnalysis.cs, DBModelManager/dbOutputManager.cs` | ModalAnalysis, dbOutputManager / ValidateModalResults, ComputeMAC, CompareFrequencies | Modal analysis validation utilities comparing Python frequencies and MAC eigenvectors against C# SQLite results. |

### 2.11 histra/tools (CLI Tools & Benchmark Runners)

| Python File | LOC | Primary C# Source(s) | C# Class(es) & Method(s) | Architectural Role & Parity Notes |
|---|---|---|---|---|
| `histra/tools/__init__.py` | 1 | `CLI tools` | Tools / Re-exports | Tools package initialization. |
| `histra/tools/article_models_benchmark.py` | 1612 | `Verification suite` | Release gate runner / RunBenchmark, EvaluateParity | Authoritative release gate runner evaluating numerical parity across the 14 canonical Article Bridge models. |
| `histra/tools/benchmark_csharp_sqlite.py` | 240 | `DBModelManager/dbOutputManager.cs` | dbOutputManager / CompareSQLite | Differential comparison tool auditing Python memory/output against C# .Results databases. |
| `histra/tools/benchmark_preprocessing.py` | 234 | `ModelManagement.ComputationalElementsOperations/ComputationalElementsOperations.cs` | ComputationalElementsOperations / BenchmarkPreparation | Preprocessing performance benchmark measuring fresh mesh preparation and contact generation speed. |
| `histra/tools/compare_csharp_results.py` | 151 | `DBModelManager/dbOutputManager.cs` | dbOutputManager / CompareCurves | Automated curve comparison comparing Python and C# capacity curves (F-d curves) and error metrics. |
| `histra/tools/interface_chain_benchmark.py` | 575 | `Verification suite` | Analysis session benchmark / RunInterfaceChain | Multi-stage benchmark runner evaluating interface material mutation under sequential loading. |
| `histra/tools/release_manifest.py` | 43 | `Verification suite` | Manifest checker / VerifyManifest | Release readiness checker auditing artifact files, parity reports, and package metadata. |
| `histra/tools/run_benchmark_full_comparison.py` | 265 | `Verification suite` | Benchmark comparator / RunFullComparison | Comprehensive regression comparator evaluating displacement and reaction parity on benchmark models. |
| `histra/tools/run_five_scour_comparison.py` | 210 | `Verification suite` | Scour benchmark / RunFiveScour | Five-stage pier scour sequence parity runner. |
| `histra/tools/run_modal.py` | 577 | `SolverRuntime.AnalysisProcedure/ModalAnalysis.cs` | ModalAnalysis / Batch modal solver | CLI runner for batch modal analysis comparing Python and C# eigenvalues across model collections. |
| `histra/tools/run_six_soil_vert_comparison.py` | 146 | `Verification suite` | Soil benchmark / RunSixSoil | Six-soil foundation stiffness variation benchmark runner. |
| `histra/tools/run_vert_live.py` | 596 | `SolverRuntime/Program.cs` | Program / Main execution workflow | Standalone CLI tool running sequential Gravity (Vert) followed by Lateral/Live load analysis on an HRX model. |
| `histra/tools/strategy_benchmark.py` | 588 | `Verification suite` | Strategy benchmark / BenchmarkStrategies | Benchmark runner qualifying solver strategies across model categories. |
| `histra/tools/validate_modal_results.py` | 62 | `SolverRuntime.AnalysisProcedure/ModalAnalysis.cs` | ModalAnalysis / ValidateModal | CLI tool validating modal results against analytical or C# reference standards. |

---

## 3. Exhaustive C# Core Source File Classification

This chapter provides an exhaustive, file-by-file audit of all **426 core C# source files** across `SolverRuntime`, `MatrixManager`, `SectionBuilderCore`, `AdapticIO`, `ModelLibrary`, `ModelManagement`, and `Objects`.


### 3.1 Solver Runtime & Numerical Procedures (33 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `SolverRuntime/CommonOperations.cs` | **Ported** | `histra/solver/model_manager.py`, `histra/solver/program.py` | Shared runtime utility methods for numerical operations, array transformations, and error handling. |
| `SolverRuntime/MassesMatrixOperation.cs` | **Ported** | `histra/solver/mass_matrix.py` | Global translational and rotational mass matrix assembly from Quad density and geometry for modal analysis. |
| `SolverRuntime/ModelManager.cs` | **Ported** | `histra/preprocessing/validation.py`, `histra/solver/__init__.py`, `histra/solver/model_manager.py` | Core solver runtime facade managing linear systems, element states, and step coordination; spring loops vectorized into compiled Numba batches. |
| `SolverRuntime/Program.cs` | **Ported** | `histra/__main__.py`, `histra/solver/__init__.py`, `histra/solver/program.py` | Static solver orchestration, progress reporting, event logging, and cooperative cancellation checks. |
| `SolverRuntime/Properties/AssemblyInfo.cs` | **Out-of-Scope** | N/A (Project Metadata) | .NET assembly metadata and compilation flags; replaced by pyproject.toml. |
| `SolverRuntime/Pseudovectors.cs` | **Ported** | `histra/solver/mass_matrix.py` | Pseudovector calculations and spatial transformation vectors for coordinate transformations and mass formulation. |
| `SolverRuntime/SolverRuntime.AnalysisProcedure/DynamicNonLinearAnalysis.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic nonlinear time-history integration; outside V1 scope |
| `SolverRuntime/SolverRuntime.AnalysisProcedure/ModalAnalysis.cs` | **Ported** | `histra/solver/modal.py`, `histra/validation/modal_results.py`, `histra/tools/run_modal.py` | Subspace iteration eigenvalue algorithm extracting structural natural frequencies, periods, mode shapes, and modal participation factors. |
| `SolverRuntime/SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs` | **Ported** | `histra/solver/nonlinear_solver.py`, `histra/solver/nonlinear_step.py`, `histra/solver/nonlinear_setup.py` | Master incremental nonlinear static analysis procedure driving the load-stepping loop, cutback retries, and equilibrium convergence. |
| `SolverRuntime/SolverRuntime.ConvergenceTest/CTestEnergyIncr.cs` | **Intentional Deviation** | `histra/types/convergence_test.py`, `histra/solver/equilibrium.py` | Work convergence ported with independent physical force residual audit to prevent false convergence under orthogonal/tiny displacements. |
| `SolverRuntime/SolverRuntime.ConvergenceTest/CTestNormDispIncr.cs` | **Ported** | `histra/types/convergence_test.py` | Relative and absolute displacement increment convergence test checking ||du|| / ||u|| against user-specified tolerances. |
| `SolverRuntime/SolverRuntime.ConvergenceTest/CTestNormUnbalance.cs` | **Ported** | `histra/solver/equilibrium.py`, `histra/solver/equilibrium_audit.py`, `histra/types/convergence_test.py` | Unbalanced residual force and moment norm convergence test checking ||R|| / ||R0||. |
| `SolverRuntime/SolverRuntime.ConvergenceTest/ConvergenceTest.cs` | **Ported** | `histra/solver/equilibrium.py`, `histra/solver/equilibrium_audit.py`, `histra/types/convergence_test.py` | Abstract base class and interface defining convergence evaluation contracts and iteration limits. |
| `SolverRuntime/SolverRuntime.Integrator/ArcLength.cs` | **Ported** | `histra/solver/arc_length.py` | Cylindrical arc-length continuation integrator maintaining a constant multidimensional displacement-load constraint radius. |
| `SolverRuntime/SolverRuntime.Integrator/ArcLength1.cs` | **Ported** | `histra/solver/arc_length.py` | Spherical/modified arc-length continuation integrator adjusting load increment lambda adaptively upon path changes. |
| `SolverRuntime/SolverRuntime.Integrator/HHT.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic nonlinear time-history integration; outside V1 scope |
| `SolverRuntime/SolverRuntime.Integrator/HHT2.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic nonlinear time-history integration; outside V1 scope |
| `SolverRuntime/SolverRuntime.Integrator/IncrementalIntegrator.cs` | **Ported** | `histra/solver/incremental_integrator.py` | Abstract base class for incremental step integrators governing step advancing, lambda scaling, and geometric P-Delta updates. |
| `SolverRuntime/SolverRuntime.Integrator/LoadControl.cs` | **Ported** | `histra/solver/load_control.py` | Monotonic proportional static load incrementation integrator advancing load factor lambda per step. |
| `SolverRuntime/SolverRuntime.Integrator/Newmark.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic nonlinear time-history integration; outside V1 scope |
| `SolverRuntime/SolverRuntime.Integrator/RiksWempner.cs` | **Ported** | `histra/solver/arc_length.py` | Classic Riks-Wempner normal plane arc-length constraint formulation. |
| `SolverRuntime/SolverRuntime.Integrator/StaticIntegrator.cs` | **Ported** | `histra/solver/incremental_integrator.py` | Base class for static incremental integrators defining tangent matrix and residual update interfaces. |
| `SolverRuntime/SolverRuntime.Integrator/TransientIntegrator.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic nonlinear time-history integration; outside V1 scope |
| `SolverRuntime/SolverRuntime.Integrator/Wilson.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic nonlinear time-history integration; outside V1 scope |
| `SolverRuntime/SolverRuntime.LineSearch/BisectionLineSearch.cs` | **Ported** | `histra/solver/line_search.py` | Bisection root-finding line search evaluating residual energy across bisected search intervals. |
| `SolverRuntime/SolverRuntime.LineSearch/InitialInterpolatedSearch.cs` | **Intentional Deviation** | `histra/solver/line_search.py` | Line search ported with explicit compatibility handling C# runtime dispatch defect where default algorithm was invoked instead of interpolated variant. |
| `SolverRuntime/SolverRuntime.LineSearch/LineSearch.cs` | **Ported** | `histra/solver/newton_line_search.py`, `histra/solver/line_search.py` | Abstract base class for energy-minimizing line search root-finders scaling Newton displacement vectors. |
| `SolverRuntime/SolverRuntime.LineSearch/RegulaFalsiLineSearch.cs` | **Ported** | `histra/solver/line_search.py` | False-position (Regula Falsi) root-finding line search accelerating Newton step convergence. |
| `SolverRuntime/SolverRuntime.LineSearch/SecantLineSearch.cs` | **Ported** | `histra/solver/line_search.py` | Secant method line search iteratively projecting residual slope along the search vector. |
| `SolverRuntime/SolverRuntime.NumericalProcedure/EquiSolnAlgo.cs` | **Ported** | `histra/solver/solution_algorithm.py`, `histra/solver/capabilities.py` | Base equilibrium solution algorithm encapsulating Newton-Raphson iteration loop and convergence evaluation. |
| `SolverRuntime/SolverRuntime.NumericalProcedure/NewtonLineSearch.cs` | **Ported** | `histra/solver/newton_line_search.py` | Newton-Raphson equilibrium solver incorporating energy line search damping and acceleration. |
| `SolverRuntime/SolverRuntime.NumericalProcedure/NewtonRaphson.cs` | **Ported** | `histra/solver/newton_raphson.py` | Standard and modified Newton-Raphson nonlinear equilibrium solver updating tangent stiffness matrices. |
| `SolverRuntime/SolverRuntime.NumericalProcedure/SolutionAlgorithm.cs` | **Ported** | `histra/solver/solution_algorithm.py` | Abstract base class for numerical solution algorithms coordinating linear system solves and domain updates. |

### 3.2 Matrix Manager & Sparse Linear Solvers (20 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/Constants.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/NativeMethods.cs` | **Ported** | `histra/types/umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackControl.cs` | **Ported** | `histra/types/umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackException.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackInfo.cs` | **Ported** | `histra/types/umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackOrdering.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackScale.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackSolve.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/CSparse.Interop.SuiteSparse.Umfpack/UmfpackStrategy.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | SuiteSparse UMFPACK Ctypes interop in histra/types/umfpack.py |
| `MatrixManager/MatrixManager/AfferenceMatrix.cs` | **Ported** | `histra/model/_types.py`, `histra/types/afference_entry.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/DenseMatrix.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/LinearSystem.cs` | **Ported** | `histra/solver/solver.py`, `histra/types/linear_system.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/MaskMatrix.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/MatrixBase.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/SPGraph.cs` | **Unimplemented** | N/A (Outside V1 scope) | Graph bandwidth reduction; handled natively by SuiteSparse/SuperLU AMD/COLAMD |
| `MatrixManager/MatrixManager/SparseMatrix.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/SparseVector.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/Vector.cs` | **Ported** | `histra/model/_types.py`, `histra/types/point.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/MatrixManager/VectorList.cs` | **Ported** | `histra/types/linear_system.py`, `umfpack.py` | Sparse matrix, vector, and linear system abstractions in histra/types/linear_system.py |
| `MatrixManager/Properties/AssemblyInfo.cs` | **Out-of-Scope** | N/A (Project Metadata) | .NET assembly metadata and compilation flags; replaced by pyproject.toml. |

### 3.3 Section Builder Core (Beam/Frame Sections) (4 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `SectionBuilderCore/Properties/AssemblyInfo.cs` | **Out-of-Scope** | N/A (Project Metadata) | .NET assembly metadata and compilation flags; replaced by pyproject.toml. |
| `SectionBuilderCore/SectionBuilderCore.Objects/Polygon.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame cross-section fiber discretization; outside DMEM masonry V1 |
| `SectionBuilderCore/SectionBuilderCore.Objects/PolygonOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame cross-section fiber discretization; outside DMEM masonry V1 |
| `SectionBuilderCore/SectionBuilderCore/MeshMaker.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame cross-section fiber discretization; outside DMEM masonry V1 |

### 3.4 Adaptic Solver IO Translator (9 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `AdapticIO/AdapticIO/FileDatEnum.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/GroupFrameItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/Helper.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/InputManager.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/InputManager2.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/InputManager3.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/OutputManager.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/AdapticIO/OutputManager_old.cs` | **Unimplemented** | N/A (Outside V1 scope) | Adaptic solver format exporter/runner; outside DMEM Python core |
| `AdapticIO/Properties/AssemblyInfo.cs` | **Out-of-Scope** | N/A (Project Metadata) | .NET assembly metadata and compilation flags; replaced by pyproject.toml. |

### 3.5 ModelLibrary Root, Computational Elements, Math & Wizards (49 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `ModelLibrary.ComputationalElements/ChildPartition.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.ComputationalElements/FrameDB.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.ComputationalElements/FrameInteract.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.ComputationalElements/FramesSDB.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.ComputationalElements/MainPartition.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.ComputationalElements/Partition.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.ComputationalElements/SpringReference.cs` | **Ported** | `histra/springs/base.py`, `histra/elements/interface.py` | Reference handle linking interface contact cells to 1D spring instances. |
| `ModelLibrary.ComputationalElements/SteelBarMeshLine.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame/Slab/Steel bar meshing; outside V1 scope |
| `ModelLibrary.MacroKernel.MacroMath/EigenvalueDecomposition.cs` | **Ported** | `histra/solver/modal.py` | Symmetric generalized eigenvalue problem solving implemented via scipy.linalg.eigh in modal solver. |
| `ModelLibrary.MacroKernel.MacroMath/LUDecomposition.cs` | **Ported** | `histra/solver/solver.py`, `histra/types/umfpack.py` | Direct LU factorization and linear solves implemented via scipy.sparse.linalg.splu and SuiteSparse UMFPACK. |
| `ModelLibrary.MacroKernel.MacroMath/Matrix.cs` | **Ported** | `histra/model/_types.py`, `histra/solver/mass_matrix.py`, `histra/solver/solver.py` | Dense and sparse matrix data structures and algebraic operations mapped directly to NumPy and SciPy arrays. |
| `ModelLibrary.MacroKernel.MacroMath/Vector.cs` | **Ported** | `histra/model/_types.py`, `histra/types/point.py` | 1D spatial vectors and numerical operations mapped to NumPy 1D ndarrays and Point dataclasses. |
| `ModelLibrary.MacroKernel.MacroNumTools/Coords.cs` | **Ported** | `histra/types/point.py`, `histra/elements/quad_geometry.py` | Cartesian coordinate transformation vectors and local element coordinate systems. |
| `ModelLibrary.MacroKernel.MacroNumTools/FForma.cs` | **Ported** | `histra/elements/quad.py`, `histra/preprocessing/fibre_geometry.py` | Bilinear shape functions and shape derivatives for 4-node quadrilaterals. |
| `ModelLibrary.MacroKernel.MacroNumTools/Position.cs` | **Ported** | `histra/elements/quad_geometry.py` | Spatial point location testing, quadrant identification, and orientation checks. |
| `ModelLibrary.MacroKernel.MacroNumTools/QuadraturaGaussiana.cs` | **Ported** | `histra/elements/quad.py` | Numerical quadrature and linear algebra mapped to NumPy/SciPy |
| `ModelLibrary.Wizard.Bridge.Graphic2DObjects/Polygons.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Abutment.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/BackFill.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Binary.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/BridgeDefinition.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/BridgeElement.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/BridgeGeoData.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/BridgeTrunk.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/BridgeZlevel.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Corsia.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Elevation.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Elevations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/MasonryBridgeWall.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Pier.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Schema.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/SchemaCombinationDefinitionData.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/Span.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/VehiclePath.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Bridge/VehiclePosition.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Frame/Floor.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Frame/SpanX.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard.Frame/SpanY.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard/WizardArch.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard/WizardBase.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard/WizardBridge.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard/WizardDome.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary.Wizard/WizardFrame.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric geometry wizard; models loaded from HRX |
| `ModelLibrary/Clone.cs` | **Intentional Deviation** | `histra/solver/state_snapshot.py` | Replaced by high-speed NumPy array state snapshotting (StateSnapshot) instead of slow .NET ICloneable / BinaryFormatter object serialization. |
| `ModelLibrary/Collections.cs` | **Ported** | `histra/model/model.py` | Core model collections container and object indexing dictionaries. |
| `ModelLibrary/ControlPointData.cs` | **Ported** | `histra/model/model.py`, `histra/solver/nonlinear_setup.py` | Control point monitoring data structure tracking pushover capacity curve displacements. |
| `ModelLibrary/ExternalParameters.cs` | **Ported** | `histra/model/model.py`, `histra/io/hr_loader.py` | Model parameter dictionary and global units/scaling factors parsed from HRX. |
| `ModelLibrary/Model.cs` | **Ported** | `histra/__init__.py`, `histra/postprocessing.py`, `histra/model/__init__.py` | Core model and container classes in histra/model/ |
| `ModelLibrary/SeismicVulnerabilityData.cs` | **Unimplemented** | N/A (Outside V1 scope) | Regulatory seismic vulnerability indices |

### 3.6 ModelManagement Operations, Meshers & Loads (91 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `ModelManagement.Analyses/AnalysesDefinitionOperations.cs` | **Ported** | `histra/solver/session.py`, `histra/solver/nonlinear_setup.py` | Analysis definition builder and stage execution sequence generator. |
| `ModelManagement.Analyses/ModalAnalysisOperations.cs` | **Ported** | `histra/solver/modal.py` | Modal analysis parameter setup, subspace dimensioning, and mass matrix scaling. |
| `ModelManagement.Analyses/PushoverOperations.cs` | **Partial** | `histra/solver/nonlinear_setup.py`, `histra/solver/load_control.py` | Static pushover load distribution parameters ported; multi-modal adaptive pushover omitted. |
| `ModelManagement.Analyses/SolverParametersOperations.cs` | **Ported** | `histra/solver/nonlinear_setup.py` | Analysis definition and modal operations |
| `ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs` | **Ported** | `histra/model/shear_law.py`, `histra/preprocessing/material_selection.py`, `histra/preprocessing/constitutive_laws.py` | Core preprocessing, contact, afference, and spring factory operations |
| `ModelManagement.ComputationalElementsOperations/ElementOperation.cs` | **Partial** | `histra/model/model.py`, `histra/preprocessing/prepare_model.py` | General element collection management and key indexing ported; CAD manipulation methods omitted. |
| `ModelManagement.ComputationalElementsOperations/FrameOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/FrameSDBHOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/FrameSDBOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/FrameSectionOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/GroupObjectOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/InterfaceMFOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/InterfaceOperations.cs` | **Ported** | `histra/preprocessing/contact_geometry.py`, `histra/preprocessing/fibre_geometry.py` | Core preprocessing, contact, afference, and spring factory operations |
| `ModelManagement.ComputationalElementsOperations/InterfacePoligonalOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/IntrinsicOperations.cs` | **Ported** | `histra/elements/quad_loads.py` | Core preprocessing, contact, afference, and spring factory operations |
| `ModelManagement.ComputationalElementsOperations/JointOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/LinkOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/LogEventHandler.cs` | **Ported** | `histra/solver/program.py` | Solver event logging delegator mapped to standard Python logging. |
| `ModelManagement.ComputationalElementsOperations/ModelPointOperations.cs` | **Ported** | `histra/solver/output_projection.py` | Core preprocessing, contact, afference, and spring factory operations |
| `ModelManagement.ComputationalElementsOperations/NodeCOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/PConstraintOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/ProgressEventHandler.cs` | **Ported** | `histra/solver/program.py` | Solver iteration and step progress notification callbacks. |
| `ModelManagement.ComputationalElementsOperations/SlabOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/SolidOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/SpringOperations.cs` | **Ported** | `histra/preprocessing/spring_factory.py` | Core preprocessing, contact, afference, and spring factory operations |
| `ModelManagement.ComputationalElementsOperations/SteelBarMeshLineOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/TrussOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.ComputationalElementsOperations/VertexOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, Slab, Solid, Joint, Link, Truss, Vertex operations outside V1 |
| `ModelManagement.GeometryElementsOperations/ArchOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/BarrelVaultOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/BridgeOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/CloisterVaultOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/CrossVaultOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/DomeOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/DomicalVaultOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/DrumOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/FiberVaultOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/GeometryFiberOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/GeometryFrameOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/GeometryLineRestraintOperations.cs` | **Ported** | `histra/preprocessing/prepare_model.py` | Edge line boundary restraint generation and node fixed-DOF assignment. |
| `ModelManagement.GeometryElementsOperations/GeometryPanelOperations.cs` | **Ported** | `histra/elements/quad_geometry.py` | Quad panel geometry validation, vertex ordering, and normal vector computation. |
| `ModelManagement.GeometryElementsOperations/GeometryPointRestraintOperations.cs` | **Ported** | `histra/preprocessing/prepare_model.py` | Point restraint expansion and node fixed-DOF assignment. |
| `ModelManagement.GeometryElementsOperations/GeometrySlabOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/MyExtensions.cs` | **Ported** | `histra/types/point.py`, `histra/preprocessing/contact_geometry.py` | Geometric vector math extension methods (cross products, dot products, bounding box tests). |
| `ModelManagement.GeometryElementsOperations/NodeOperations.cs` | **Ported** | `histra/model/node.py`, `histra/preprocessing/prepare_model.py` | Nodal coordinate manipulation, bounding box computation, and distance checks. |
| `ModelManagement.GeometryElementsOperations/OpeningOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/PointAndCurvatureRay.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/SpecchioVaultOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD/vault/arch/bridge geometry modeling operations |
| `ModelManagement.GeometryElementsOperations/SurfaceRestraintOperations.cs` | **Ported** | `histra/preprocessing/prepare_model.py`, `histra/preprocessing/spring_assignment.py` | Surface restraint projection and foundation interface spring generation. |
| `ModelManagement.Load/AreaLoadOperations.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/LineLoadOperations.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/LoadCombinationOperations.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/LoadConditionOperations.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/LoadElementOperations.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/ModelLoadOperations.cs` | **Ported** | `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/PointLoadOperations.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Self-weight, line load, point load, and combination assembly |
| `ModelManagement.Load/VaultLoadOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Vault-specific load distribution |
| `ModelManagement.Material/ConcreteMaterialOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber material operations |
| `ModelManagement.Material/FiberMaterialOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber material operations |
| `ModelManagement.Material/MasonryMaterialOperations.cs` | **Ported** | `histra/preprocessing/material_selection.py` | Masonry material property derivation and blending |
| `ModelManagement.Material/SteelMaterialOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber material operations |
| `ModelManagement.Mesher/AreaMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/BridgeMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/DomeMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/DrumMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/InfoOpening.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/RestraintMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/SlabMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/VaultMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.Mesher/WallMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement.MessageBoxCustom/MessageBoxCustom.cs` | **Out-of-Scope** | N/A (Desktop GUI Dialog) | WinForms/WPF interactive modal dialog box; irrelevant to headless Python execution. |
| `ModelManagement/ArcoMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement/CursorPointer.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/DxfIO.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/InpIO.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelCopying.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelDesigner.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelDrawer.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelGridOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelMesher.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD polygon mesher; models loaded from HRX |
| `ModelManagement/ModelMoving.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelOperations.cs` | **Partial** | `histra/preprocessing/errors.py`, `histra/preprocessing/prepare_model.py` | Core model validation checks ported; interactive CAD topology mutation omitted. |
| `ModelManagement/ModelPropertiesCopying.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelSelector.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelSnapOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ModelStretching.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/ObjectCopier.cs` | **Intentional Deviation** | `histra/solver/state_snapshot.py`, `histra/solver/session.py` | In-memory structural state snapshotting and restoration replacing recursive deep object serialization for multi-stage analysis transitions. |
| `ModelManagement/ResponseOperations.cs` | **Ported** | `histra/postprocessing.py`, `histra/solver/output_projection.py` | Model point and reaction response extraction |
| `ModelManagement/UndoRedoOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/VehicleOperations.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |
| `ModelManagement/tratto.cs` | **Unimplemented** | N/A (Outside V1 scope) | Interactive CAD editor operations, snapping, DXF/INP import |

### 3.7 Objects Elements, Springs, Loads, Materials & Sections (220 files)

| C# Source File | Status | Python Target / Subsystem | Technical Rationale & Capability Boundary |
|---|---|---|---|
| `Objects.Analyses/Accelerogram.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/AdapticPhaseItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/Analysis.cs` | **Ported** | `histra/__init__.py`, `histra/solver/modal.py`, `histra/solver/nonlinear_solver.py` | Analysis configuration, state tracking, and output points |
| `Objects.Analyses/AnalysisOptions.cs` | **Ported** | `histra/solver/nonlinear_setup.py` | Solver convergence tolerances, maximum iterations, and step size options. |
| `Objects.Analyses/AnalysisState.cs` | **Ported** | `histra/solver/outcomes.py` | Analysis configuration, state tracking, and output points |
| `Objects.Analyses/CoefficientCustomTableDBClass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/DynamicLoad.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/IntegratorState.cs` | **Ported** | `histra/types/integrator_state.py` | Analysis configuration, state tracking, and output points |
| `Objects.Analyses/LoadFunction.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/LoadFunctionItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/ModelPoint.cs` | **Ported** | `histra/solver/output_projection.py` | Analysis configuration, state tracking, and output points |
| `Objects.Analyses/PushModalSet.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic excitation, accelerograms, or multi-modal pushover sets |
| `Objects.Analyses/PushOverData.cs` | **Partial** | `histra/model/load.py`, `histra/solver/nonlinear_setup.py` | Pushover analysis parameters (target displacement, monitored DOF) parsed from HRX; spectrum generation omitted. |
| `Objects.Analyses/ReactionSum.cs` | **Ported** | `histra/solver/output_projection.py`, `histra/solver/equilibrium.py` | Global reaction resultant sum container for monitoring equilibrium. |
| `Objects.Analyses/Response.cs` | **Ported** | `histra/postprocessing.py`, `histra/solver/output_projection.py` | Analysis configuration, state tracking, and output points |
| `Objects.Analyses/StageDefinition.cs` | **Ported** | `histra/model/load.py`, `histra/solver/session.py` | Analysis stage load configuration and predecessor key specification. |
| `Objects.ComputationalElements/FrameSectionKeyDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/FrameSectionProperties.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/FrameSectionTemplateKeyDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/Interaction.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/InternalConstraint.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/Joint.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/Link.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/NodeC.cs` | **Ported** | `histra/model/node.py` | Slave/contact node entity parsed in histra/model/node.py |
| `Objects.ComputationalElements/PConstraint.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/PConstraintDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/Slab.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ComputationalElements/SlabEdge.cs` | **Unimplemented** | N/A (Outside V1 scope) | Frame, slab, link, joint computational elements |
| `Objects.ConstitutiveLaw/ConstitutiveLawBase.cs` | **Ported** | `histra/preprocessing/constitutive_laws.py` | Constitutive laws for shear and hysteretic flexural springs |
| `Objects.ConstitutiveLaw/ConstitutiveLawCoulomb.cs` | **Ported** | `histra/model/shear_law.py`, `histra/preprocessing/constitutive_laws.py` | Constitutive laws for shear and hysteretic flexural springs |
| `Objects.ConstitutiveLaw/ConstitutiveLawElastic.cs` | **Ported** | `histra/preprocessing/constitutive_laws.py` | Constitutive laws for shear and hysteretic flexural springs |
| `Objects.ConstitutiveLaw/ConstitutiveLawElastoPlastic.cs` | **Unimplemented** | N/A (Outside V1 scope) | Geotechnical, steel, and general elastoplastic laws |
| `Objects.ConstitutiveLaw/ConstitutiveLawElastoPlasticTakeda.cs` | **Unimplemented** | N/A (Outside V1 scope) | Geotechnical, steel, and general elastoplastic laws |
| `Objects.ConstitutiveLaw/ConstitutiveLawGeo.cs` | **Unimplemented** | N/A (Outside V1 scope) | Geotechnical, steel, and general elastoplastic laws |
| `Objects.ConstitutiveLaw/ConstitutiveLawHysteretic.cs` | **Ported** | `histra/preprocessing/constitutive_laws.py` | Constitutive laws for shear and hysteretic flexural springs |
| `Objects.ConstitutiveLaw/ConstitutiveLawSteel.cs` | **Unimplemented** | N/A (Outside V1 scope) | Geotechnical, steel, and general elastoplastic laws |
| `Objects.Defaults/AdvancedOptionsDefault.cs` | **Ported** | `histra/solver/nonlinear_setup.py` | Default numerical parameters for Newton-Raphson iterations, line search, and convergence tolerances. |
| `Objects.ElementStates/AddressReference.cs` | **Partial** | `histra/io/results_reader.py` | SQLite results database memory address reference mapping parsed for parity auditing. |
| `Objects.ElementStates/AnalysisReference.cs` | **Partial** | `histra/io/results_reader.py` | SQLite results database analysis table key foreign reference parsed for parity auditing. |
| `Objects.ElementStates/BaseObjectStateDBclass.cs` | **Partial** | `histra/io/results_reader.py` | SQLite results base entity state schema read for displacement/force comparison. |
| `Objects.ElementStates/DynamicVectorsState.cs` | **Unimplemented** | N/A (Outside V1 scope) | States for dynamic vectors, fibers, slabs, vertices |
| `Objects.ElementStates/FiberState.cs` | **Unimplemented** | N/A (Outside V1 scope) | States for dynamic vectors, fibers, slabs, vertices |
| `Objects.ElementStates/InverseTriangularValues.cs` | **Unimplemented** | N/A (Outside V1 scope) | States for dynamic vectors, fibers, slabs, vertices |
| `Objects.ElementStates/ModalShapeValues.cs` | **Ported** | `histra/solver/modal.py`, `histra/validation/modal_results.py` | Mode shape displacement eigenvector storage structure mapped to NumPy arrays. |
| `Objects.ElementStates/ModalValues.cs` | **Ported** | `histra/solver/modal.py` | Modal natural frequencies, circular frequencies, and modal participation factors. |
| `Objects.ElementStates/NodeBCState.cs` | **Unimplemented** | N/A (Outside V1 scope) | States for dynamic vectors, fibers, slabs, vertices |
| `Objects.ElementStates/QuadState.cs` | **Ported** | `histra/model/quad.py`, `histra/elements/quad_state.py` | Runtime state and modal shapes |
| `Objects.ElementStates/SlabState.cs` | **Unimplemented** | N/A (Outside V1 scope) | States for dynamic vectors, fibers, slabs, vertices |
| `Objects.ElementStates/SpringStateDBclass.cs` | **Partial** | `histra/io/results_reader.py` | SQLite results spring state table schema read for internal spring force auditing. |
| `Objects.ElementStates/VertexState.cs` | **Unimplemented** | N/A (Outside V1 scope) | States for dynamic vectors, fibers, slabs, vertices |
| `Objects.GeneratedObjects.Springs/SpringConcrete01.cs` | **Unimplemented** | N/A (Outside V1 scope) | Generated NLink, concrete, and steel springs |
| `Objects.GeneratedObjects.Springs/SpringConcrete02.cs` | **Unimplemented** | N/A (Outside V1 scope) | Generated NLink, concrete, and steel springs |
| `Objects.GeneratedObjects.Springs/SpringConcrete04.cs` | **Unimplemented** | N/A (Outside V1 scope) | Generated NLink, concrete, and steel springs |
| `Objects.GeneratedObjects.Springs/SpringDBclass.cs` | **Partial** | `histra/io/results_reader.py`, `histra/springs/registry.py` | Serialized spring database schema read from HRX and SQLite results. |
| `Objects.GeneratedObjects.Springs/SpringSteel01.cs` | **Unimplemented** | N/A (Outside V1 scope) | Generated NLink, concrete, and steel springs |
| `Objects.GeneratedObjects/NLink.cs` | **Unimplemented** | N/A (Outside V1 scope) | Generated NLink, concrete, and steel springs |
| `Objects.GeometryElements/DomeAnglesDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.GeometryElements/DrumAnglesDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Loads/ActionTable.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/AreaLoadElement.cs` | **Ported** | `histra/model/load.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/CombinationCoefficient.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/CombinationCoefficientData.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/GeometryLoadLine.cs` | **Partial** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Geometric line load definitions mapped to Quad edge line loads; polygon clipping for non-quad boundaries omitted. |
| `Objects.Loads/LineLoadElement.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/LoadCombination.cs` | **Ported** | `histra/model/load.py`, `histra/io/hr_loader.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/LoadCombinationItem.cs` | **Ported** | `histra/model/load.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/LoadCondition.cs` | **Ported** | `histra/model/load.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/LoadDynamicFunction.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/LoadDynamicFunctionItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/LoadElement.cs` | **Ported** | `histra/model/load.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/LoadTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/LoadTemplateItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/PointLoadElement.cs` | **Ported** | `histra/model/load.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/StageItem.cs` | **Ported** | `histra/model/load.py`, `histra/solver/load_assembly.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/StaticLoad.cs` | **Ported** | `histra/model/load.py` | Static load cases, combinations, and distributions |
| `Objects.Loads/TypeLoadDBClass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/VaultLoadElement.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/VehicleLoadElement.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Loads/WheelLoadElement.cs` | **Unimplemented** | N/A (Outside V1 scope) | Dynamic load functions, vehicle train loads, vault loads |
| `Objects.Material/ConcreteMaterial.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.Material/ConcreteMultiLinearPlasticMaterial.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.Material/ElasticIsotropicMaterial.cs` | **Partial** | `histra/model/masonry_material.py` | Elastic isotropic material constants (E, G, Poisson ratio, weight) mapped to MasonryMaterial elastic properties. |
| `Objects.Material/FiberMaterial.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.Material/GeotecnicalMaterial.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.Material/MasonryMaterial.cs` | **Ported** | `histra/model/__init__.py`, `histra/model/masonry_material.py`, `histra/preprocessing/material_selection.py` | Masonry material formulation and base properties |
| `Objects.Material/MaterialBase.cs` | **Ported** | `histra/model/masonry_material.py` | Masonry material formulation and base properties |
| `Objects.Material/MomentCurvature.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.Material/MomentCurvatureValue.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.Material/SteelMaterial.cs` | **Unimplemented** | N/A (Outside V1 scope) | Concrete, steel, fiber, geotechnical, moment-curvature materials |
| `Objects.ModelProperty/BuildingInfo.cs` | **Partial** | `histra/model/model.py`, `histra/io/hr_loader.py` | General building metadata (description, author, unit system) parsed from HRX header. |
| `Objects.ModelProperty/GeneralInfo.cs` | **Partial** | `histra/model/model.py`, `histra/io/hr_loader.py` | Project general info and timestamp metadata parsed from HRX. |
| `Objects.ModelProperty/ModelPropertyClass.cs` | **Partial** | `histra/model/model.py`, `histra/io/hr_loader.py` | Model property container parsed from HRX; seismic classification options omitted. |
| `Objects.ModelProperty/RegulationDefaultValues.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/SeismicCriteria.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/Soil.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/SpectralResponse.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/SpectralResponseCustom.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/SpectralResponseCustomA.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/SpectralResponseCustomT.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/SpectralResponseITA2018.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.ModelProperty/VitaUtile.cs` | **Unimplemented** | N/A (Outside V1 scope) | Seismic design code criteria (NTC2018 spectra, soil categories) |
| `Objects.Object/GridCoordinate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Object/GroupObjects.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Object/Layer.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Object/ModelInfo.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Object/UndoElement.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Others/CopyItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Others/ImageInfo.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Others/SnapPoint.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Others/TableItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/BeamColumnTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/BeamColumnTemplateItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/DoubleTSectionTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/ElasticFrameSection.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/FiberDoubleTFrameSection.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/FiberFrameSection.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/FiberRectangularFrameSection.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/FrameSection.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/FrameSectionState.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/FrameSectionTemplateBase.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/PlasticFrameSection.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/RectangularSectionTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/SlabCompositeSectionTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/SlabLatCaSectionTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/SlabSectionTemplate.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Section/SlabSectionTemplateBase.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.SeismicVulnerabilityAssessment/SeismicVulnerability.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.SeismicVulnerabilityAssessment/SeismicVulnerabilityItem.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Spettri/AccSpectrum.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Spettri/PointSpectrum.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Template/TemplateBase.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects.Template/TemplateBaseHelper.cs` | **Unimplemented** | N/A (Outside V1 scope) | CAD, section templates, seismic code assessments, or spectra |
| `Objects/Abside.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/AfferenceMatrixItem.cs` | **Ported** | `histra/model/_types.py`, `histra/types/afference_entry.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/Arch.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/BarrelVault.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/BaseObject.cs` | **Ported** | `histra/model/model.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/BaseObjectCollection.cs` | **Ported** | `histra/model/model.py` | Strongly-typed collection container with key-based lookup ported to dictionary collections. |
| `Objects/BaseObjectEventArgs.cs` | **Out-of-Scope** | N/A (Desktop GUI Event) | .NET event argument class for WPF desktop event dispatching and UI binding. |
| `Objects/Bridge.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/BridgeBaseElement.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/CloisterVault.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/ComputationalElement.cs` | **Out-of-Scope** | N/A (Desktop CAD Helper) | Base class for graphical display representations of elements in the desktop CAD viewport. |
| `Objects/ConstitutiveLawCollection.cs` | **Out-of-Scope** | N/A (Desktop UI Collection) | UI collection container for desktop property grid dropdowns and editors. |
| `Objects/CrossVault.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/CustomPropertyDescriptor.cs` | **Out-of-Scope** | N/A (Desktop Property Grid) | .NET System.ComponentModel descriptor for Visual Studio / WPF property grids. |
| `Objects/DbTable.cs` | **Partial** | `histra/io/results_reader.py` | Generic database table schema representation used in reading C# .Results SQLite files. |
| `Objects/Dome.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/DomicalVault.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Drum.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Element.cs` | **Ported** | `histra/model/node.py`, `histra/model/quad.py`, `histra/model/shear_law.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/ElementCollection.cs` | **Ported** | `histra/model/model.py` | Computational element container supporting iteration and type filtering. |
| `Objects/ElementCollectionBase.cs` | **Ported** | `histra/model/model.py` | Abstract base collection for structural elements. |
| `Objects/Event.cs` | **Out-of-Scope** | N/A (Desktop UI Event) | Desktop user interaction event tracking and GUI action logging. |
| `Objects/EventList.cs` | **Out-of-Scope** | N/A (Desktop UI Event) | Desktop UI event list container for undo/redo and visual history. |
| `Objects/Fiber.cs` | **Ported** | `histra/preprocessing/fibre_geometry.py`, `histra/solver/hysteretic_kernels/transverse.py` | Transverse contact fiber segment model ported to fiber cell arrays. |
| `Objects/FiberVault.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Frame.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/FrameInteractionState.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/FrameSegment.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/FrameSegmentCollection.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/FrameState.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/GeometryFiber.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | DirectX 3D viewport rendering geometry representation of transverse contact fibers. |
| `Objects/GeometryFrame.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/GeometryLineRestraint.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | CAD viewport glyph drawing support line restraints in 3D scene. |
| `Objects/GeometryLoad.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | CAD viewport glyph drawing load arrows and vectors in 3D scene. |
| `Objects/GeometryPanel.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | CAD viewport shaded masonry rendering entity for Quad panels. |
| `Objects/GeometryPointRestraint.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | CAD viewport glyph drawing support pins/triangles in 3D scene. |
| `Objects/GeometryRestraint.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | CAD viewport boundary restraint presentation entity. |
| `Objects/GeometrySlab.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/GeometrySlabAlfa.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/GeometrySlabNodeKeys.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/Interface.cs` | **Ported** | `histra/model/__init__.py`, `histra/model/interface.py`, `histra/elements/__init__.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/InterfaceMF.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/InterfacePoligonal.cs` | **Out-of-Scope** | N/A (Desktop CAD Tool) | Interactive CAD drawing tool for manual polygonal interface boundary creation. |
| `Objects/InterfaceState.cs` | **Out-of-Scope** | N/A (Desktop Visualization) | Obsolete WPF visualization state container for interface deformation rendering. |
| `Objects/InterfaceStateMF.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | 3D rendering state container for multi-fiber interfaces in DirectX viewport. |
| `Objects/InterfacesCollection.cs` | **Ported** | `histra/elements/interface.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/InterfacesCollectionMF.cs` | **Out-of-Scope** | N/A (Desktop UI Collection) | UI collection container for multi-fiber interface viewport rendering. |
| `Objects/IsModelModifiedEventArgs.cs` | **Out-of-Scope** | N/A (Desktop GUI Event) | Dirty-flag event triggering desktop Save Changes confirmation prompts. |
| `Objects/LineReference.cs` | **Ported** | `histra/model/restraint.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/LoadElementCollection.cs` | **Out-of-Scope** | N/A (Desktop UI Collection) | UI collection container for desktop load treeview display. |
| `Objects/MaterialCollection.cs` | **Out-of-Scope** | N/A (Desktop UI Collection) | UI collection container for desktop material palette editor. |
| `Objects/Node.cs` | **Ported** | `histra/model/__init__.py`, `histra/model/node.py`, `histra/types/point.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/NodeBC.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/NodeCState.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/NodeCollection.cs` | **Ported** | `histra/model/model.py` | Global node dictionary indexed by integer key. |
| `Objects/Opening.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Pendentive.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Quad.cs` | **Ported** | `histra/model/__init__.py`, `histra/model/quad.py`, `histra/elements/__init__.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/ReferenceSystem.cs` | **Ported** | `histra/elements/quad_geometry.py`, `histra/elements/interface.py` | Local Cartesian reference frame orientation and rotation matrices. |
| `Objects/Restraint.cs` | **Ported** | `histra/model/__init__.py`, `histra/model/restraint.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/RestraintState.cs` | **Out-of-Scope** | N/A (Desktop Visualization) | Graphical rendering state for boundary restraint icons in viewport. |
| `Objects/SlabNodeCKeys.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SlabNodeKeys.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/Solid.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SolidNodeKeysInfDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SolidNodeKeysSupDBclass.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SolidState.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpecchioVault.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Spring.cs` | **Ported** | `histra/model/spring.py`, `histra/springs/__init__.py`, `histra/springs/base.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/SpringArmFried.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpringConcrete07.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpringCoulomb02.cs` | **Ported** | `histra/springs/coulomb.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/SpringCoulomb03.cs` | **Ported** | `histra/model/spring.py`, `histra/springs/coulomb03.py`, `histra/springs/coulomb03_state.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/SpringElastoPlastic.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpringElastoPlasticTakeda.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpringEndochronic.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpringHysteretic.cs` | **Ported** | `histra/model/spring.py`, `histra/springs/hysteretic.py`, `histra/solver/hysteretic_kernels/transverse.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/SpringLinearElastic.cs` | **Ported** | `histra/model/spring.py`, `histra/springs/elastic.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/SpringMultiLinearPlastic.cs` | **Ported** | `histra/model/spring.py`, `histra/springs/multilinear.py` | DMEM Quad, Interface, Spring, Node, Restraint core entity |
| `Objects/SpringSteel02.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SpringStok.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/SurfaceRestraint.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | CAD surface restraint visualization entity for 3D rendering. |
| `Objects/TextureF.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | Bitmap masonry texture mapping parameters for realistic 3D wall rendering. |
| `Objects/TexturesCollection.cs` | **Out-of-Scope** | N/A (Desktop 3D Graphics) | Texture dictionary managing bitmap texture files for desktop renderer. |
| `Objects/Truss.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/TrussState.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |
| `Objects/VaultProperties.cs` | **Unimplemented** | N/A (Outside V1 scope) | Parametric vault/bridge CAD geometry entity |
| `Objects/Vertex.cs` | **Unimplemented** | N/A (Outside V1 scope) | Non-DMEM element or specialized spring formulation |

---

## 4. Secondary and Utility Libraries Survey

Beyond the numerical core, the C# HiStrA codebase includes four secondary and utility directories containing **576 files**. These libraries provide general utility services, data persistence, mathematics, domain types, and framework foundations.

### 4.1 `CommonObject`, `CommonObjectCollection`, and `CommonObjectManagement` (10 files)
- **C# Contents**:
  - `CommonObject/`: `DatiGrid.cs`, `GeometryVaultLoadTemplate.cs`, `InfoIntersection.cs`, `OsnapPoint.cs`, `filling.cs` (5 files).
  - `CommonObjectCollection/`: `GridCoordinateCollection.cs`, `LayerCollection.cs`, `LineReferenceCollection.cs` (3 files).
  - `CommonObjectManagement/`: `LineReferenceOperations.cs`, `LoadTemplateManager.cs` (2 files).
- **Role in C#**: Supporting geometry data structures for CAD snapping, coordinate grids, layer management, and load templates.
- **Python Mapping Status**:
  - `LineReferenceOperations.cs` and `LineReferenceCollection.cs` are ported to boundary restraint identification in `histra/model/restraint.py` and `histra/preprocessing/prepare_model.py`.
  - The remaining snapping (`OsnapPoint`), CAD grid (`DatiGrid`, `GridCoordinateCollection`), and layer visibility objects are **Out-of-Scope** for the Python headless solver.

### 4.2 `DBManagement`, `DBManagement.SQLiteDb`, and `DBModelManager` (12 files)
- **C# Contents**:
  - `DBManagement/`: `DatabaseBase.cs`, `DatabaseManager.cs`, `DatabaseType.cs`, `DataColumnInfo.cs`, `DataSetData.cs`, `DataTableInfo.cs`, `UtilityCommonMethods.cs`, `dbSQLserverManager.cs`, `dbSQLServerModelManager.cs` (9 files).
  - `DBManagement.SQLiteDb/`: `Database.cs` (1 file).
  - `DBModelManager/`: `dbModelManager.cs`, `dbOutputManager.cs` (2 files).
- **Role in C#**: SQLite database schema management, table creation, and result serialization (`.Results` files) for analysis runs.
- **Python Mapping Status**:
  - `DBManagement.SQLiteDb/Database.cs` and `dbOutputManager.cs` are ported to `histra/io/results_reader.py` to allow Python to read and audit reference `.Results` databases produced by C#.
  - The SQL Server management classes (`dbSQLserverManager.cs`, `dbSQLServerModelManager.cs`) are unused in standard HiStrA workflows and are **Unimplemented**.
  - In Python, runtime analysis states are preserved in-memory via `AnalysisSession` rather than writing intermediate SQLite state files, drastically improving multi-analysis execution velocity.

### 4.3 `UtilityLibrary` and `UtilityLibrary.Tipi` (250 files)
- **C# Contents**:
  - `UtilityLibrary.Tipi/` (**212 files**): Complete enumeration and data type definitions for the entire HiStrA suite (e.g., `PhaseEnum.cs`, `ArcLengthProcedureEnum.cs`, `ConvergenceTestEnum.cs`, `IntegratorEnum.cs`, `SolutionAlgorithmEnum.cs`, `HystereticTensileCurveTypeEnum.cs`, `HystereticCompressiveCurveTypeEnum.cs`, `UnloadType.cs`, `TypeRestraintEnum.cs`).
  - `UtilityLibrary/`: General mathematical, linear algebra, vector, combinatorics, and file IO utilities (38 files across `CSML`, `Matematics`, `Combinatorics`, `Units`, `Vector3F`, `IO`).
- **Role in C#**: Type authority and foundational mathematical functions.
- **Python Mapping Status**:
  - All critical domain enums governing V1 execution have been cleanly ported to `histra/types/` (`phase_enum.py`, `hysteretic_curve_types.py`, `convergence_test.py`, `integrator_state.py`).
  - 3D Cartesian vectors (`UtilityLibrary.Vector3F/Vector3F.cs`) are ported to `histra/types/point.py` (`Point`).
  - Dense linear algebra and matrix decomposition classes (`CSML`, `Matematics`) are mapped directly to standard, optimized `numpy` and `scipy.linalg` routines.
  - The remaining enums (relating to regulatory seismic codes, CAD display styles, and unported element types) are cataloged as inactive for V1.

### 4.4 `SirioCommon` (304 files)
- **C# Contents**: Enterprise shared library for SirioSoft desktop products (licensing verification, PDF generation, UI custom controls, error handling, string manipulation).
- **Role in C#**: Proprietary corporate framework providing software licensing dongle checks and reporting.
- **Python Mapping Status**: **Out-of-Scope**. Completely irrelevant to the open scientific Python numerical solver core.

---

## 5. Out-of-Scope Desktop GUI and Tooling Catalog

The C# HiStrA suite contains **420 files** dedicated entirely to interactive Windows desktop applications, CAD viewports, and Office interoperability. These are explicitly cataloged below as **Out-of-Scope** for the `histra-python` numerical core.

| Directory | File Count | Technologies Used | Primary Functions & UI Responsibilities | Out-of-Scope Rationale |
|---|---|---|---|---|
| `IDEcontrols/` | 200 | WPF, XAML, WinForms | Custom property grids, tree views, toolbars, color palettes, coordinate pickers, dialog boxes for load templates, and response chart plotting. | Interactive desktop GUI controls have no role in headless batch/command-line Python execution. |
| `WindowsHistra/` | 115 | WPF, MVVM, XAML | Main application window, ribbon toolbar, document view controllers, menu event routing, analysis launch wizards, and project save/load dialogs. | Desktop application shell and workflow coordination replaced by Python API and CLI entry points (`histra.tools`). |
| `WindowsRuntime/` | 88 | DirectX, SharpDX, MonoGame | Real-time 3D GPU graphics viewport rendering nodes, quads, interfaces, deformed meshes, contour stress maps, and animated mode shapes. | 3D rendering engine; Python exports raw displacement/reaction data or postprocesses results headlessly. |
| `ExcelLibrary.Excel/` | 1 | COM Interop, OpenXML | Automated export of analysis tables, load combinations, and modal participation factors into Microsoft Excel spreadsheets. | Office automation; Python utilizes native CSV, JSON, or DataFrame outputs when needed. |
| `HiStrA.Plugins/` | 5 | .NET Extensibility | Desktop plugin architecture allowing third-party UI extensions and custom menu buttons inside the HiStrA IDE ribbon. | IDE extension mechanism not required for headless library usage. |
| `SeismicVulnerabiltyLibrary/` | 7 | WinForms, Reports | Italian seismic vulnerability assessment dialogs and automated reporting forms. | Regulatory reporting UI; engineering core calculations reside in the solver. |
| `UnityServiceClasses/` | 4 | Unity Container (IoC) | Dependency injection container bootstrapping desktop services (model opening, saving, and logging). | Replaced by direct Python module imports and explicit dependency passing. |
| **Total Out-of-Scope** | **420** | | | |

---

## 6. Architectural Transformations & Intentional Deviations Deep-Dive

In porting the C# numerical engine to Python, several structural and algorithmic redesigns were implemented to ensure numerical parity, resolve C# design flaws, and achieve high performance.

### 6.1 Compiled Numba Batch Runtime vs C# Object Graph Traversal
- **C# Implementation**:
  - C# evaluates nonlinear constitutive laws by traversing deeply nested object references: `Model.ComputationalElements -> Quad -> Spring -> ConstitutiveLaw`.
  - In each Newton iteration, virtual method dispatch is invoked millions of times across individual Quad diagonal springs and Interface contact fibers.
- **Python Transformation (`histra/solver/hysteretic_runtime.py`, `histra/solver/hysteretic_kernels/`)**:
  - Python replaces object-oriented iteration with contiguous NumPy memory buffers and JIT-compiled Numba kernels.
  - The runtime pre-extracts element topology into flat integer arrays (`kinematics.py`, `scatter.py`).
  - Spring evaluations are vectorized into batch operations (`transverse.py`, `interface_coulomb.py`, `quad_takeda.py`), achieving compiled C-speed numerical execution.
  - Runtime coverage enforcement (`backend_coverage.py`) strictly verifies that zero unmanaged Python objects execute during solver iterations.

### 6.2 Fresh Model Preprocessing Boundary vs Serialized HRX State
- **C# Implementation**:
  - C# models saved as `.hrx` files frequently contain serialized snapshots of computational interfaces and springs created by previous analysis stages (e.g. post-scour states or modified soil assignments).
  - Inspecting or solving a model using serialized objects without resetting leads to corrupted baseline stiffnesses (as discovered in the historic Benchmark 3 pier interface 682 investigation).
- **Python Transformation (`histra/preprocessing/prepare_model.py`)**:
  - Python enforces the **Fresh Model Preparation Boundary**: serialized interfaces and springs in HRX files are treated strictly as reference metadata.
  - Before solving, `ModelManager.prepare_model(force=True)` completely regenerates the contact geometry, 6-face clipping, fibre discretization, and spring assignments from the pristine Quad geometry and material tables.
  - This guarantees 100% bit-exact parity (< 7 × 10⁻¹¹ mm displacement deviation across 1,820 DOFs) without carrying stale artifacts from past runs.

### 6.3 Multi-Stage Analysis Session vs Disk-Based SQLite DB Swapping
- **C# Implementation**:
  - In C#, sequential staged analyses (e.g., Gravity Vert -> Scour Stage 1 -> Live Load) communicate by writing element deformation states to SQLite `.Results` files on disk and rereading them via `Analysis.InitialAnalysisKey`.
  - Material mutations at stage boundaries (e.g. excavating pier soil) involve destructive in-place modification of database records.
- **Python Transformation (`histra/solver/session.py`, `histra/solver/interface_material.py`)**:
  - Python introduces `AnalysisSession`: a stateful, in-memory execution manager that preserves committed displacement states and internal spring histories across analysis boundaries without disk IO.
  - Interface material mutations (`AnalysisSession.change_interface_materials`) surgically rebuild only the affected interface springs while immutably preserving the predecessor history on unaffected masonry joints.

### 6.4 Nonlinear Convergence Safety vs Deceptive Work Convergence
- **C# Implementation**:
  - C# allows convergence testing using the `Work` criterion: $0.5 \cdot | \Delta u \cdot R | \le 	ext{tol}$.
  - When incremental displacements $\Delta u$ are tiny or near-orthogonal to the residual vector $R$, the work product converges to near-zero even while the physical out-of-balance force residual remains massive.
- **Python Transformation (`histra/solver/equilibrium.py`, `histra/solver/equilibrium_audit.py`)**:
  - Python maintains mathematical compatibility with C# convergence tests (`types/convergence_test.py`) but supplements them with an independent **Physical Equilibrium Audit**.
  - Python explicitly calculates applied force resultants vs reacting base shears, detecting false convergence and alerting engineers to non-physical equilibrium states.

### 6.5 Sparse Linear Solvers: SuiteSparse UMFPACK vs SciPy SuperLU
- **C# Implementation**:
  - C# delegates sparse linear system solving to SuiteSparse UMFPACK via unmanaged P/Invoke wrappers in `MatrixManager`.
- **Python Transformation (`histra/solver/solver.py`, `histra/types/umfpack.py`)**:
  - Python provides dual backends: a direct Ctypes binding to SuiteSparse UMFPACK (`histra/types/umfpack.py`) for exact floating-point branch parity, and a native fallback to SciPy `SuperLU` (`scipy.sparse.linalg.splu`).
  - Linear system reset semantics are strictly guarded: matrix rebuilds clear stiffness matrix $K$ while strictly preserving accumulated residual vector $b$ (`gotchas/linear-system-reset-semantics.md`).

---

## 7. Independent Verification Commands & Audit Protocol

An independent forensic auditor can verify every claim, classification count, and line of code mapping documented in this chapter using the automated verification commands detailed below.

### 7.1 Automated File Count and Parity Verification Script

Run the following standalone command from the root of `/home/mauricio/coding/histra-python` to verify the exact counts across both codebases:

```bash
python3 -c "
import os, re

# 1. Verify Production Python File Count (117 files)
py_files = []
for root, dirs, files in os.walk('histra'):
    dirs[:] = [d for d in dirs if d != '__pycache__' and d != 'tests' and not d.startswith('model-')]
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))
assert len(py_files) == 117, f'Expected 117 Python files, got {len(py_files)}'
print('✓ Python Production Files: Exactly 117 files verified.')

# 2. Verify C# Core Classification from Master Matrix
with open('docs/audit/01_file_coverage_matrix.md') as f:
    text = f.read()

csharp_rows = re.findall(r'\| \`([^\`]+\.cs)\` \| \*\*([^*]+)\*\* \| ([^|]+) \| ([^|]+) \|', text)
assert len(csharp_rows) == 426, f'Expected 426 core C# files, got {len(csharp_rows)}'

counts = {}
for path, status, target, rationale in csharp_rows:
    counts[status] = counts.get(status, 0) + 1
    assert os.path.exists(os.path.join('C#_Original', path)), f'Missing C# file: {path}'

assert counts['Ported'] == 131, f'Expected 131 Ported, got {counts.get(\"Ported\")}'
assert counts['Partial'] == 15, f'Expected 15 Partial, got {counts.get(\"Partial\")}'
assert counts['Unimplemented'] == 248, f'Expected 248 Unimplemented, got {counts.get(\"Unimplemented\")}'
assert counts['Intentional Deviation'] == 4, f'Expected 4 Intentional Deviation, got {counts.get(\"Intentional Deviation\")}'
assert counts['Out-of-Scope'] == 28, f'Expected 28 Out-of-Scope, got {counts.get(\"Out-of-Scope\")}'
print(f'✓ C# Core Classifications: Exactly 426 unique files verified (131 Ported, 15 Partial, 248 Unimplemented, 4 Deviation, 28 Out-of-Scope).')

# 3. Verify Desktop GUI Out-of-Scope Files (420 files)
gui_dirs = ['IDEcontrols', 'WindowsHistra', 'WindowsRuntime', 'ExcelLibrary.Excel', 'HiStrA.Plugins', 'SeismicVulnerabiltyLibrary', 'UnityServiceClasses']
gui_count = sum(len([f for f in files if f.endswith('.cs')]) for d in gui_dirs for _, _, files in os.walk(os.path.join('C#_Original', d)))
assert gui_count == 420, f'Expected 420 GUI files, got {gui_count}'
print('✓ Desktop GUI Directory Count: Exactly 420 files verified as Out-of-Scope.')

# 4. Verify Python Correspondence Rows (117 files)
py_rows = re.findall(r'\| \`(histra/[^\`]+)\` \| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|', text)
assert len(py_rows) == 117, f'Expected 117 Python rows, got {len(py_rows)}'
print('✓ Python Correspondence Rows: Exactly 117 rows verified in Section 2.')

print('\nALL MATRIX VERIFICATION AUDITS PASSED SUCCESSFULLY.')
"
```

### 7.2 Release-Critical Verification Commands

To confirm that all ported numerical modules compile and pass their strict regression suites:

```bash
# Activate virtual environment
source .venv/bin/activate

# 1. Full Fast Release-Critical Regression Suite
python -m pytest -q histra/tests/test_backend_coverage_enforcement.py histra/tests/test_article_models_benchmark.py histra/tests/test_package_metadata.py histra/tests/test_backend_api.py

# 2. Verify Compiled Numba Hot-Path Execution (Zero Unmanaged Quads/Interfaces)
python -m pytest -q histra/tests/test_backend_coverage_enforcement.py

# 3. Verify 14 Canonical Article Bridge Models Parity Gate
python -m histra.tools.article_models_benchmark --models-dir my_model/Article_Models_Benchmark --model all --run-mode authored --max-workers 4 --output-dir release-evidence/article-models
```

---
