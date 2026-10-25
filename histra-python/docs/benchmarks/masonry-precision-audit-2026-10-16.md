# Masonry precision-boundary audit, C# 2026.1.1

This pass follows types and expression order through the supported masonry
pipeline, including inputs that did not yet fail a global benchmark. It extends
the [construction and update audit](masonry-source-audit-2026-10-14.md).
It is ongoing; an inventory match or a passing isolated routine does not prove
every independently converged structural history matches.

## Rules and evidence

Preserve C# `Single` storage, arithmetic rounding after each Single operation,
and promotion to `Double` at the actual consumer. Do not convert complete
constitutive routines to Single: their state and calculations are Double.
Maintain scalar and compiled implementations together. Native routine tests
retain their exact comparisons; global numerical-library tolerances require
separate complete-history and stopping validation.

The original Framework assemblies are called using Windows PowerShell 5.1.
The oracle scripts record assembly hashes. Python solves start from geometry;
native saved interfaces and histories are comparison data only. Step zero is
excluded from committed counts.

| Boundary / original source | Python consumer and tests | Finding / status |
| --- | --- | --- |
| `AdvancedOptionsDefault`: `ToleranceNode`, `TolerancePlane` Single; `InterfaceImax` Double | `hr_loader`, `prepare_model`; `test_csharp_geometry_setting_precision` | Preserve storage for HRX and programmatic inputs. Original property values captured in a native fixture. Fractional-tolerance topology needs broader structural coverage. |
| `Operations`, XNA `Vector3`, `Quad.SetGeometry`, contact/fibre construction | `quad_geometry`, `quad_faces`, `intrinsic_coordinates`, `csharp_fibre_geometry`; existing native geometry/contact/intrinsic tests | Single vectors and ordered reductions retained. Native contact admission is distinct from a generic polygon clipper. Linux-only Sin tolerance remains limited to the specified geometry test. |
| `SpringOperations.SetInterfaceTrasvSpring`, `Operations.Area` | scalar/batched `spring_assignment`; `test_csharp_polygon_area` | Corrected restraint cell area to native Single projection/shoelace. 93 original polygons. |
| `MasonryMaterial`, `ConstitutiveLawOperations`, orthotropic interface selection | `material_selection`, spring construction; native moduli/default/blend/restraint tests | Existing native-backed checks cover property conversion, Single axis alignment, ordered blending and elastic/nonlinear law dispatch. This is not coverage of every possible material curve. |
| `LoadTemplateManager.GetCoefficient` | `load_assembly`; `test_csharp_load_coefficients` | Corrected intermediate Single products including secondary coefficients. 540 original cases across all 26 supported primary coefficient types. |
| `GenerateLoadsForceAnalysis`, `Quad.ComputeNodalForce` | `load_assembly`, `quad_loads`; native direction/line-load tests and `test_masonry_reference_models` | Self-weight direction multiplication rounds before promotion. 448 fresh original load-vector entries cover fractional coefficients, oblique directions, static and modal loads. |
| Modal load direction and directional mass inputs | `load_assembly`; wall modal and fresh-load fixtures | Native modal direction is (1,1,1); line loads carry all specified directional mass factors. Corrected prior missing horizontal mass. |
| `Quad.ComputeLocalMassfromSelfWeight`, `ComputeLocalMass` | `mass_matrix`; `test_modal_analysis` | Node coordinates, normals, thickness, centre and axes stored Single then promoted. Length/cos/sin and integration remain Double. Mass integration tests retain documented floating-point tolerances. |
| `SpringHysteretic`, `SpringCoulomb03`, elastic spring updates | scalar springs and `hysteretic_batch`; native cyclic/update/commit/energy fixtures | Core state is Double. Display-only Single getters do not justify rounding history. Correcting batch import of virgin E1p resolves all four walls' checked phase/history differences. |
| Interface local stiffness, forces, normal-force cache and global assembly | scalar elements and compiled assembly; native interface-stiffness/normal-force/local-displacement fixtures | Preserve ordered reductions, projection increments and force-minus-increment cancellation. Initial wall K and first native linear solve matched exactly in the preceding wall audit. |
| `LineSearch.NewLineSearch`: tolerance / min/max eta Single | `_new_line_search`; native analysis-setting fixture and existing search traces | Corrected factory promotion; direct search defaults retain their native Double values. |
| `Analysis.MaxArcLengthRay` Single; `ArcLength.Commit` | `arc_length`; native analysis-setting fixture | Default C# mode caps squared state by the native field directly. Explicit stable mode retains its alternative squared-radius cap. |
| `LoadReductionRatioToStopValue` Single | `nonlinear_step`; native setting and adjacent-double boundary tests | Strict comparison uses promoted Single threshold. |
| `ComputePDeltaLoads`, `Quad.DisplacementsCurrent`, `MatrixPerVector3` | scalar `model_manager`, compiled runtime/scatter kernels; `test_csharp_pdelta` | Original routines supply 24 cases covering seismic/nonseismic direction, zero/ordinary/large translation, interface force inputs and oblique force frames. Corrected template direction, translation-add/subtract rounding and Single force-frame multiplication. All 28 global entries match exactly in scalar and compiled paths. |
| `StaticNonLinearAnalysis.Execute`: `CheckSecantStiffness` / Single `SecantStiffnessRatio` | `secant_stiffness`, called before integrator commit | Two independent native chains match every available checked output, actual alpha choices and iteration counts. Ratios 0.4 and 1.1 exercise current and initial stiffness. Negative/recovery branches retain source-derived boundary tests. |
| `CommonOperations.AddStateElements`, `ComputePDeltaLoads`: saved force cache | `nonlinear_step`, `model_manager`, dense runtime; `test_pdelta_native_execution` | Native P-Delta reads Interface.Status.Forces saved at output boundaries. Four complete chains cover EachStep/EachIteration and StepSave 1/2; all checked available fields match exactly. Saved-force state participates in snapshot/revert/reset. |
| `ModalValues.Set`, `Pseudovectors.ComputeUmax` | `modal`; four native wall modal fixtures | Modal UMax is stored Single, eigenvectors remain Double. Corrected native `UMaxX/Y/Z` column spelling and require every available native field to be present. |

## Inventory and remaining work

`tools/csharp-diagnostics/inventory_precision_boundaries.py` inventories numeric
declarations/casts with line numbers and source hashes across SolverRuntime,
MatrixManager, model objects, relevant model-management helpers and utility
mathematics. Run it with `--source-root` pointing at the decompilation and
`--output` in the ignored diagnostic directory. Its candidates include
unsupported and display paths; the tool deliberately produces no pass verdict.
Implicit promotions and overloaded operators still require source review.

The inventory, including model-load regeneration, contains 317 files and 14,690 candidate lines. Those
numbers describe the search surface, not completed manual review.

The remaining audit includes less-used supported input branches, general
shared-DOF P-Delta reduction order and fractional-tolerance contact outcomes.
P-Delta now has both imposed-input routine fixtures and four independently
converged small structural chains. These do not cover arbitrary contact-centre
geometry. A direct native material-mutation metadata differential check was
pending at this report's original source boundary.
The 2026-10-17 correction now calls original `SpringStateDBclass.SetSpring`
and fixes numeric-group tangent/yield/F0 restoration for its recorded cases.
Python deliberately retains predecessor energy, which native DB restoration
omits. Complete staged structural validation of this correction remains open;
see the [current validation register](../audit/csharp_python_function_mapping_matrix.md).
Dynamic/Adaptic and
non-masonry properties stay outside this task. Fields such as
`ReduceRayArcLength` must not be implemented solely because they exist in the
model: a numerical consumer must first be established in the original code.

All four wall references now match every checked available internal history;
see the dated resolution in the [wall comparison report](masonry-wall-native-parity-2026-10-15.md).
The Article model gate remains unavailable on this computer. Current package
artifacts predate these fixes and need rebuilding before release qualification.

## Regression after merging the GitHub refactor

The incoming commits `92bb7c4` and `e5ef0f6` were merged with the pending
analysis-control precision changes. Eight fresh wall chains were then rerun
with native UMFPACK, AMD ordering and two refinement steps: Vert has 10 commits
and Reversal has 32 in each chain. Excluding the repeated Vert chains and step
zero gives 296 unique commits and 100,640 spring records. Every available
table/field comparison report is identical to the preceding wall audit,
including raw differences, branch mismatches and unavailable fields. Native
Results hashes remain unchanged. This verifies no regression on those inputs;
it does not waive the previously reported internal-history differences.

Local diagnostic evidence is stored in
`four-wall-precision-merged-static-comparison/comparison.json` under the
comparison directory, separate from the original saved results.

## Subsequent full-execution resolution

The E1p import correction supersedes the remaining differences in the preceding
merge-only regression. Current exact evidence is in
`four-wall-virgin-tangent-static-comparison/comparison.json`; original native
Newton captures and the complete saved-state fingerprints are protected by
committed fixtures. All 296 unique wall states have zero measured differences
in every available checked table/field.

The native secant chains each have 10 Vert and 7 ArcLength commits. Four native
P-Delta chains have the same actual committed counts. With StepSave=2, C# reports
AnalysisState.Step=6 but stores the final private spring state at step 7:
`StaticNonLinearAnalysis.Execute` truncates that metadata to the regular save
boundary. Tests count the actual terminal state and exclude step zero.

P-Delta force-cache timing follows the authoritative implementation, including
its dependence on StepSave. It is not interchangeable with recomputing current
trial resultants. Independent equilibrium diagnostics remain active: matching
the original Work convergence decision does not establish a separate
force-equilibrium pass.

## Verification of the current changes

At 9c622b4, the complete Windows suite passes with 826 tests and 1,662 subtests
(14 skips); Linux passes with 789 tests and 1,461 subtests (51 skips). Native
Windows-library integration cases are explicitly skipped where that library
is unavailable. The two Windows warnings are expected independent-equilibrium
diagnostics in the native P-Delta cases. Ruff and the configured mypy checks
also pass.

The large fresh Dhir chain independently retains exact available-field and
committed-iteration parity through all 88 commits after the virgin tangent
correction; see its [dated regression](dhir-full-chain-native-parity-progress.md).
The [horizontal chain](dhir-horizontal-native-parity.md) also retains exact
available-field parity through all 521 commits and the attempt-502 stop.
The numerical source boundary of that longer run is 97a8cd5. The subsequent
saved-force cache bookkeeping has separate complete native P-Delta chain
tests. These are explicit qualification boundaries, rather than a claim that
all supported inputs have now been exhaustively validated.
