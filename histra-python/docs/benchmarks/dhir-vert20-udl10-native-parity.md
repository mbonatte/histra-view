# Dhir C# parity: 20-step Vert followed by 10-step constant load

## Qualification, 2026-10-14

Both stages pass the unchanged numeric/history parity gate against C# 2026.1.1. Python independently reconstructs the computational model from geometry, reapplies material 146 to all 148 foundation interfaces, and solves Vert followed by TLM_Constant_UDL using compiled element kernels and the shared native UMFPACK backend. Saved C# computational interfaces are not used for the Python solve.

All 77,080 spring identities match. Every available numeric state field passes at initial state and every committed step, including transverse, shear, out-of-plane and diagonal spring responses; complete final spring history; local element displacements/resultants; restraints; model nodes/points; global energy sums; and final global displacement vectors. Phase/history categories agree. C# NULL per-spring E/Ed/Eel measurements remain unavailable, rather than zero or passing numeric comparisons.

| Quantity | Vert | TLM_Constant_UDL |
|---|---:|---:|
| Committed steps | 20 | 10 |
| Maximum spring-force difference (kN) | 1.81842e-11 | 3.41061e-12 |
| Maximum spring-displacement difference | 1.84575e-15 | 1.19349e-15 |
| Final global-displacement maximum difference | 2.33147e-15 | 2.94210e-15 |
| Reaction-vector difference at every saved step | 0, exactly equal | 0, exactly equal |
| Phase differences | 0 | 0 |
| Native rollback calls | 0 | 0 |

Step zero is initial state, not a commit: Vert saves states 0 through 20, and constant load saves states 0 through 10. Native and Python iteration counts match at every step. Vert: 1, 1, 1, 2, 3, 13, 28, 44, 57, 65, 95, 75, 88, 92, 98, 104, 139, 109, 131, 176. Constant load: 1, 3, 5, 6, 10, 14, 18, 21, 26, 31.

The user triggered the Vert rerun by changing its load discretization from ten to twenty steps, then ran constant load in the same application session. The trace's final two analysis blocks identify that order; earlier repeated constant-load attempts in the same trace are not substituted for this final run. The previously missing 418 diagonal CmomMax values now match, confirming that recomputing Vert in memory avoids the native reopening/restoration omission for this reference. Smaller constant-load increments also avoid the earlier failed-step rollback defect. Neither C# defect has been copied into Python or repaired in the original application.

## Evidence and limits

[Committed numeric evidence](../../release-evidence/dhir/2026-10-14-vert20-udl10.json) records input/result hashes, source revision, per-step differences, native iteration counts and the gate outcome. Detailed paired arrays and unchanged input/result/trace copies are retained in the local dnSpy HiStrA audit directory under `python-comparison-2026-10-13/dhir-native-vert20-udl10-reference` and `dhir-vert20-udl10-fresh-python/static/every-step`. The Python run took about 101 seconds, including fresh preparation and every-state comparisons; this is not a solver-only performance measurement. All reference-copy hashes remain unchanged.

This is output parity under the source Work criterion for these two stages. Python's separate equilibrium diagnostic fails 19 of 20 Vert steps and all ten constant-load steps under the recorded warn policy, so the result does not qualify strict equilibrium acceptance. It also does not qualify a failed native rollback branch, a reopened-history branch, other models or modal analysis. Solver implementation and tolerances were unchanged for this validation; the existing suite remains at 727 passed, 23 skipped and 857 subtests from the preceding native-history regression run.

## Subsequent full-chain reference

The user subsequently supplied the full same-session chain. It contains 58 pushover commits and a failed attempt 59. See [the full-chain comparison](dhir-full-chain-native-parity-progress.md) for the construction fixes, remaining strict phase mismatch and targeted native diagnostics. The older pushover reference is not substituted for this new chain.
