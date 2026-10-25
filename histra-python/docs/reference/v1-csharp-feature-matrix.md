# C# to Python V1 feature matrix

Status is one of `verified`, `partial`, `missing`, `intentional C# defect`, or
`out of V1 scope`. “Verified” refers to the named tests; release acceptance also
requires the Article and platform gates.

| Feature | Status | C# authority | Python owner | Test/evidence |
|---|---|---|---|---|
| HRX masonry/Quad/Interface/load parsing | verified | `Objects.*`, serializer attributes | `histra/io/hr_loader.py` | `test_hr_loader.py`, `test_load_vector.py`, analysis-control metadata test |
| Unlocked preprocessing, six faces, afference | verified | `ModelManagement.ComputationalElementsOperations` | `histra/preprocessing` | `test_prepare_model.py`, contact/afference tests |
| Self-weight/load combinations | verified | `LoadOperations`, Quad gravity | `histra/solver/load_vector.py` | load-vector and self-weight tests; static `Force`/`LoadCombination` distributions accepted explicitly |
| Modal/Triangular/Adaptive/ShearFloor static distributions | out of V1 scope | `ModelLoadOperations.GenerateLoadsForPushOverMultiModalAnalysis` and desktop pushover generators | capability preflight | static preflight rejects them rather than assembling a different ordinary-load problem |
| Dependency/restart/state transfer | verified | `Analysis.InitialAnalysisKey`, domain commit/revert | `histra/solver/session.py` | session, chain, restart tests |
| Interface material changes/mixed sides | verified | Interface `SetSpring` and material operations | `interface_material.py`, preprocessing selection | interface-material tests |
| Elastic/hardening/softening/exponential/parabolic envelopes | verified | `ConstitutiveLawHysteretic`, `SpringHysteretic` | `constitutive_laws.py`, `springs/hysteretic.py`, `hysteretic_runtime.py` | scalar/compiled differential lifecycle and material-update tests; benchmark-scale all-Parabolic preflight has zero unmanaged objects (`test_hysteretic_batch_material_update.py`, `test_backend_coverage_enforcement.py`) |
| Linear/Coulomb/Cacovic domains | verified | `ConstitutiveLawOperations.SetShearConstitutiveLaw` | `constitutive_laws.py`, `coulomb03*` | constitutive and Coulomb tests |
| Fracture energy/ductility/contact area/orthotropy | verified | `ConstitutiveLawCoulomb`, `MasonryMaterial.GetShearUltimateStrain` | preprocessing and Coulomb runtime | constitutive, material-selection, Coulomb tests; compiled and scalar Quad paths both apply fixed and stress-interpolated shear energy |
| Initial/Takeda Coulomb reversal | verified | `SpringCoulomb03.setTrialStrain*` | `coulomb03_state.py`, batch kernels | scalar/batch hysteretic tests |
| `UnloadShear` Origin/Mixed selector | intentional C# defect | C# stores the material enum but Quad diagonal construction forces Takeda and combined Interface sliding forces Initial | `constitutive_laws.py`, `spring_assignment.py` | enum is validated; Python follows the same constructible Initial/Takeda paths instead of dispatching a different law |
| Static integrators and controllers | verified | `SolverRuntime.Integrator/StaticIntegrator.cs`, `ArcLength.cs`, `ArcLength1.cs`, `UtilityLibrary.Tipi/IntegratorEnum.cs`, `ArcLengthProcedureEnum.cs` | `incremental_integrator.py`, `arc_length.py` | integrator/controller, ArcLengthLinear linearized-corrector, and unknown-procedure preflight tests |
| Newton and line-search methods | verified | `EquiSolnAlgo` factory | `solution_algorithm.py` | solution-algorithm tests |
| Initial-Interpolated through base factory | intentional C# defect | C# hidden `new` method/base dispatch | explicit compatibility behavior | dispatch regression test |
| ForceMoment/DispRotation/Work | verified | C# convergence-test factory | `convergence_test.py` | convergence and equilibrium tests |
| RelativeWork | intentional C# defect | enum exists; C# factory branch absent | `capabilities.py` | preflight rejection test |
| P-Delta EachStep/EachIteration | verified | C# incremental-integrator geometric update | `incremental_integrator.py` | unit parity and compiled scatter verified (`test_pdelta.py`) |
| Modal mass/eigensolution/projection | partial for C# 2026.1.1 | `SolverRuntime/ModelManager.cs`, `Pseudovectors.cs`, `SubSpaceIteration2`; modal/mass enums in `UtilityLibrary.Tipi` | `mass_matrix.py`, `modal.py`, output projection | 2026.1.1 inverse-iteration numerical fixtures pass; full-model 2026.1.1 modal results and shared subspace ports remain pending; unsupported modal/mass enums fail before assembly |
| Dynamic nonlinear/response spectrum | out of V1 scope | dynamic analysis subsystem | capability preflight | precise rejection tests |
| Frame/Slab/Link/Joint/Solid/Truss/Vertex/InterfaceMF/NodeBC and concrete/steel/fiber | out of V1 scope | C# computational-element and material collections | capability/input boundary | every serialized non-V1 element tag is inventoried and rejected; no partial-result claim |

The authoritative release evidence is the versioned Article report, strategy
report, full test logs, and platform CI—not this inventory alone.
