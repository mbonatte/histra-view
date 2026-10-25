# Dhir native construction and update audit, 2026-10-14

The original C# 2026.1.1 assemblies remain the reference. The latest strict run matches every available committed state through Vert 20, constant load 10 and pushover 58. The output replay also matches reported displacements and energies exactly. See the [full-chain report](dhir-full-chain-native-parity-progress.md) for scope and missing native measurements.

Python regenerates its model from geometry and reapplies material 146 to 148 foundation interfaces. The native construction oracle also regenerates geometry/interfaces and calls the original `ReSetInterfaces` for those material assignments. It does not transplant C# computational objects or histories into Python.

## Corrections and native tests

- `61fec0d`: use the current Framework private UCRT (`ucrtbase_clr0400.dll`) before the older VC120 runtime. Calls to original `System.Math` verify 36 power and six arctangent cases, including cancellation near one.
- `fcc9dac`: preserve the original `Quad.SetGeometry` nested power calls for corner sines. Twelve native geometry cases compare lengths, diagonals, cosines and sines exactly.
- `5b7c11d`: preserve `Quad.SetNonLinearProperties` principal-stress powers and `k * (diagonal factor * strain scale)` association. Twelve native capacity cases compare scalar and compiled Python exactly. The shared arithmetic helper lives outside preprocessing to avoid circular model imports; the earlier import path remains available.
- `fa5250b`, `ec071b8`: use the original quadratic arc-length correction and exact zero comparisons by default. Eight fixtures call the installed `ArcLength.Update` itself with a native identity system, including the negative-discriminant fallback, a very small nonzero reference and both zero-denominator failure branches. The simplified one-dimensional correction remains available through `ArcLength(constraint_mode="stable")` and can change last bits and branch decisions.
- `9db0dc6`: close the final load-control interval with the original target-minus-accumulated-multiplier calculation. Four fixtures invoke original `GetDt`/`GetIncrMult`, including accumulated rounding, a shorter interval and a scaled target.
- `533f374`: preserve Double shear intermediates until the completed displacement correction is converted to Single; accumulate node contributions with the original Single sum and reciprocal multiplication. Eight original quad displacement cases and two original node averaging cases match binary outputs.
- `139af0d`: add each element's energy directly into running totals, preserving original `ModelManager.ComputeEnergy` operation order. Four native seeded-total cases exercise the original manager, quad and spring routines.

The complete suite with the installed UMFPACK library passes **757 tests and 1,418 subtests**, with 14 skips. The exact Framework fixtures require that arithmetic backend; portable numeric checks remain separate.

## Whole-model checks

| Check | Scope | Result |
| --- | --- | --- |
| Spring construction after foundation material change | All 77,080 identities; K, area, Fy, Ur and available E3p | Exact values |
| Local-to-global mapping | 91,144 local rows, 217,166 coefficients; 16,408 DOFs | Exact |
| Initial global stiffness | 425,560 stored entries, alpha 0 | Exact |
| Vert gravity target vector | All 16,408 DOFs | Exact |
| Recorded global displacement components after endpoint correction | Original trace's first 16 components at 30 load-controlled commits | All 480 components exact |
| Imposed-input mechanics replay | 20 input increments, every spring U/F/tangent/phase and global resisting-force vector | Exact |
| Tangent assembly after each imposed input | 425,560 entries at each of 20 frames, alpha 1 | Exact |

The last row is a mechanics diagnostic, not a converged-analysis comparison. Both implementations receive the same increments derived from Python Vert endpoints, call their update routines and commit after each input. This omits the actual Newton correction trajectory. It tests 1,541,600 spring records per field while avoiding differences introduced by independent solves.

## Diagnostic precision and solver controls

Framework JSON uses a legacy round-trip formatter/parser combination that can yield a different last bit when Python parses the displayed decimal. The construction oracle therefore exports the original binary representation as integer strings. Several apparent tiny construction discrepancies disappeared when those original bits were compared.

Original `SparseMatrix.InitializeControl` gives UMFPACK strategy 3, refinement 2 and ordering 1 (AMD). Python's explicit native comparison uses `linear_solver_precision="accurate"`, `umfpack_irstep=2` and AMD ordering. The existing fast setting disables refinement. Full-chain qualification uses the native controls; the default fast configuration is not certified for exact branch parity.

The installed reference HRX/Results remain unchanged. Missing native measurements stay unavailable. Current paired data and scripts are retained under the local `python-comparison-2026-10-13` audit folder. `Invoke-FreshConstructionOracle.ps1` reproduces construction, mapping, initial assembly/load and imposed-input update checks by calling original routines; `Invoke-LinearControlOracle.ps1` captures the original control settings.

The original quadratic correction alone still failed one phase at pushover commit 23. Adding the final-load-interval correction removed that divergence and produced exact saved spring fields at all 88 commits. All committed iteration counts and failed attempt 59/code -2 match. Subsequent output corrections reproduce 91 model-point snapshots and 88 energy totals from saved Python states. Native private histories remain unavailable for the complete pushover chain; neither this replay nor the earlier scalar/compiled shadow comparison establishes equality of unavailable measurements.
