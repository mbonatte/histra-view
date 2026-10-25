# Dhir Vert: native C# parity validation

Validated for v1.4.2, including the spring-history corrections following v1.4.1.

## 2026-10-14: Vert gate closed; constant-load transition open

The latest run supersedes the earlier reaction discrepancy below. Commit `1731e4d` matches the float32 result of C# `Operations.sqrt(float)` when computing out-of-plane spring distance factors. Six direct native distance cases agree exactly. Fresh geometry preparation with foundation material 146 now passes every available numeric state field at step zero and all ten committed Vert steps, with all reaction vectors exactly matching C#. Phase/history differences remain zero. Final maximum global displacement difference is 2.60903e-15, spring-force difference 6.82122e-13 kN, and spring displacement difference 1.02696e-15. NULL per-spring energy fields remain unavailable; the separate equilibrium diagnostic is not qualified by this parity result.

Evidence: `python-comparison-2026-10-13/dhir-vert-native-spring-distance/comparison-numeric-fields.json` under the local dnSpy HiStrA audit directory. Original input/result hashes are unchanged.

Commit `ddea51d` subsequently matches native line-load polygon bisection, source projection and float arithmetic against seventeen direct C# cases. The complete Python suite passes 725 tests, with 23 skips and 819 subtests. The gated second-load run agrees at its initial state but stops at the first TLM_Constant_UDL commit. Replaying C# local displacement endpoints in a fresh diagnostic Python model still reveals an interface spring-history offset, so correcting global load integration alone does not explain it.

The original source and native calls establish that spring rollback restores committed/trial hysteretic state but leaves base spring U unchanged. They do not establish that a failed attempt occurred in this saved run. Native database-reader checks also reproduce the saved spring U and interface U values exactly. The user has no solver log and recalls a large first-step jump followed by linear increments.

A separate application copy at `C:\Users\mbonatte\Documents\Histra\csharp-diagnostics-2026.1.1\app` instruments original solver IL with the C# helper in [the diagnostic tools](../../tools/csharp-diagnostics/README.md). The subsequent GUI run reproduced all original Vert/constant-load stored fields exactly and confirmed the stale-U rollback defect for the rejected first constant-load attempt. See [the dated constant-load investigation](dhir-constant-load-rollback.md). Python's earlier full-increment convergence remains a separate open difference; pushover remains gated behind resolving the second analysis.

## 2026-10-14: native transcendental arithmetic

Post-release validation at source commit `e651ddc`, following v1.4.2. The original release evidence below remains historical.

Direct calls to the installed C# `Quad.GetFiberProperties` and `Quad.GetFiberStiffness` isolated cancellation-sensitive stiffness differences despite exactly matching geometry coefficients and lengths. The .NET Framework power and arctangent functions round differently from Python/LLVM on those inputs. Compiled fibre integration now calls the corresponding Windows CRT functions through registered symbols, retaining source operation order. Production uses the same source-owning batch kernel as its native regression, avoiding a stale cached wrapper with an older imported implementation.

The native unittest covers 126 fibres in seven interfaces, both parent Quads, through scalar and actual production batch paths. The full suite passes: **723 tests, 23 skipped, 796 subtests**. Separate-process cached execution was also checked for the power correction.

Fresh Dhir preparation reapplies material 146 to all 148 foundation interfaces before Vert. Step 0 remains initial; both implementations have exactly 10 committed steps and 77,080 matching spring identities. All available numeric spring histories and responses pass unchanged thresholds. C# NULL per-spring energy values remain unavailable. Other available state tables pass except step 9 ReactionSumStates.R1.

Initial stiffness comparison against all saved C# definitions:

| Spring family | Maximum absolute difference | Maximum relative difference |
|---|---:|---:|
| Transverse | 5.45697e-12 | 4.99166e-15 |
| Shear | 5.23869e-10 | 4.35236e-15 |
| Out-of-plane | 5.09317e-11 | 4.90871e-15 |
| Diagonal | 9.31323e-10 | 5.84087e-15 |

The previous transverse relative difference was 2.06e-8. Its remaining difference is now consistent with the decimal precision of the saved definitions. This correction does **not** resolve the remaining reaction discrepancy or imply bit-identical output.

| Step | Maximum spring-force difference (kN) | Maximum spring-displacement difference | Phase differences |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1 | 2.6608449e-08 | 2.17043924e-11 | 0 |
| 2 | 5.16791099e-08 | 3.68610396e-11 | 0 |
| 3 | 7.88373753e-08 | 5.47109841e-11 | 0 |
| 4 | 1.21961737e-07 | 6.94304678e-11 | 0 |
| 5 | 2.05149917e-07 | 9.0306105e-11 | 0 |
| 6 | 3.07142253e-07 | 1.10553871e-10 | 0 |
| 7 | 3.7897129e-07 | 1.36807719e-10 | 0 |
| 8 | 4.56456139e-07 | 1.88121088e-10 | 0 |
| 9 | 5.17715215e-07 | 2.37214252e-10 | 0 |
| 10 | 6.09531721e-07 | 3.00569347e-10 | 0 |

Final saved global displacement maximum difference: 1.42254e-10. Step 9 R1 remains 7.152557373046875e-7 kN in Python versus 2.8014183044433594e-6 kN in C#, a 2.086162567138672e-6 kN difference above the unchanged 1e-6 absolute cutoff. Its remaining source must be investigated downstream of initial stiffness construction.

Exact runtime rounding is selected when the Windows .NET Framework CRT is available. Other platforms retain standard compiled arithmetic; this Windows precision qualification does not establish bitwise portability. These changes affect preprocessing, with no Python callback in the compiled integration. The full audit took 102.70 seconds while other validation processes were running; it is not a controlled performance comparison.

The independent equilibrium diagnostic remains in warning mode for C# acceptance parity; all 10 commits fail that additional residual check. Source HRX and Results hashes stayed unchanged. This audit does not qualify later stages or strict equilibrium.

Commits: `115affc` (power), `8f533a3` (production kernel), `e651ddc` (arctangent).

Raw paired data and unfiltered per-field diagnostics: `C:\Users\mbonatte\Downloads\_Organized_Downloads\Software\dnSpy-net-win64\histra\python-comparison-2026-10-13\dhir-vert-native-transcendental\static\every-step`. Numeric summary excluding explicitly unavailable SQL NULL fields: `C:\Users\mbonatte\Downloads\_Organized_Downloads\Software\dnSpy-net-win64\histra\python-comparison-2026-10-13\dhir-vert-native-transcendental\comparison-numeric-fields.json`.

## v1.4.2 release evidence (2026-10-13)

## Scope and construction

Reference: HiStrA Bridges 2026.1.1 Dhir HRX and Results. This audit covers Vert only. Python recreates geometry, all interfaces, springs and local-to-global mappings from the structural inputs. It applies material 146 (`Soil_Foundation_ONLY_V75_X024`) to all 148 foundation interfaces before Vert. C# computational objects remain comparison references only.

Step 0 is initial, never committed. Both implementations have 10 committed Vert steps. All 77,080 spring identities match: 56,052 transverse, 6,228 shear, 12,456 out-of-plane and 2,344 diagonal.

## Source corrections

- Native Quad face projection, contact containment, node/plane tolerances and Vector3 normalization.
- Native local spring cells and projected fibre stiffness.
- Native float32 ray–plane sliding distances and masonry modulus arithmetic.
- Compiled polygon-strip bisection for shear-DOF coordinates with the original 0.001 stopping tolerance.
- Hysteretic yield-coordinate initialization (`Fy/K`) for scalar and lazy proxy springs.
- Committed Coulomb unloading memory in compiled interface/Quad rows, including snapshot and object synchronization.
- Literal Interface.SetSpring post-ultimate curve reassignment: the selected ultimate displacement also selects its originating curve family, followed by reinitialization. Preserved the preceding E2n/E3n values when the source changes to Parabolic.

Native regression fixtures call original DLL methods. The interface construction oracle calls CombinationSpring, SetUltimateDisplacement and initialize using the literal Interface.SetSpring selection protocol. The final suite passes: **722 tests, 23 skipped, 670 subtests**.

## Every committed spring state

| Step | Maximum spring-force difference (kN) | Maximum spring-displacement difference | Phase differences |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1 | 2.66094526e-08 | 2.1704413e-11 | 0 |
| 2 | 5.1677576e-08 | 3.68619186e-11 | 0 |
| 3 | 7.88400625e-08 | 5.47125785e-11 | 0 |
| 4 | 1.21955108e-07 | 6.94328386e-11 | 0 |
| 5 | 2.05141998e-07 | 9.03080575e-11 | 0 |
| 6 | 3.07127452e-07 | 1.10558836e-10 | 0 |
| 7 | 3.78937415e-07 | 1.36807602e-10 | 0 |
| 8 | 4.5638183e-07 | 1.88115837e-10 | 0 |
| 9 | 5.17635456e-07 | 2.37187246e-10 | 0 |
| 10 | 6.09430238e-07 | 3.00451587e-10 | 0 |

**Every available numeric spring field passes the unchanged comparison thresholds**, including final SpringStates yield coordinates, extrema, unloading phases, contact history and tangent metadata. Interface displacements/forces/moments, Quad states, restraint/model-node displacements, global energy sums, and model-point displacements pass at each available step. One aggregate horizontal reaction field remains outside its unchanged cutoff at step 9. The final saved global displacement vector passes as well.

Final maximum global displacement difference: 1.43e-10. Final maximum reaction-component difference: 2.38e-7 kN. Spring response and all categorical phase/history fields agree; floating-point values are not bit-identical.

## Remaining aggregate reaction difference

Step 9 R1 is 7.152557373046875e-7 kN in Python versus 2.8014183044433594e-6 kN in C#, a 2.086162567138672e-6 kN difference near zero. This exceeds the current 1e-6 absolute cutoff; it is explicitly retained as an open numerical difference. Reconstructing the source formula from each implementation’s saved interface resultants reproduces its recorded reaction exactly. The summation path matches; the difference comes from the slightly different resultants entering float32 projection/cancellation. Native calls also verified all first-six rigid mapping coefficients in 330 cases exactly. The threshold is not relaxed.

## Evidence limits

- Detailed SpringStates and DynamicVectorsState are saved only at final Vert step 10; earlier steps have SpringStatesTmp and the other available state tables. The audit does not invent missing C# histories.
- C# E/Ed/Eel per-spring database columns are NULL for all 77,080 final rows (confirmed directly by SQL). These are unavailable measurements, not zero energies or passing numeric comparisons. Global energy sums are compared separately.
- This validates this Dhir Vert reference in explicit C# compatibility mode. It does not qualify other models, later load stages, modal analysis or independent strict equilibrium. Python retains the separate equilibrium diagnostic.
- Neither thresholds nor existing regression assertions were relaxed. A midpoint interpolation test now uses an exact original-C# oracle instead of an algebraic midpoint assumption.

Original HRX and Results hashes remained unchanged. Raw paired arrays and unfiltered diagnostics are preserved; the numeric summary explicitly separates SQL NULL fields:

`C:\Users\mbonatte\Downloads\_Organized_Downloads\Software\dnSpy-net-win64\histra\python-comparison-2026-10-13\dhir-vert-native-final-history\comparison-numeric-fields.json`

`C:\Users\mbonatte\Downloads\_Organized_Downloads\Software\dnSpy-net-win64\histra\python-comparison-2026-10-13\dhir-vert-native-final-history\static\every-step`
