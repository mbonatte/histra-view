# Dhir full-chain comparison, 2026-10-14

The installed C# 2026.1.1 Dhir reference now matches through its last committed pushover step. Python freshly regenerates geometry and reapplies material 146 to all 148 foundation interfaces, using the accepted C# interface-registration strategy. Native computational objects and histories are not reused.

| Analysis | Committed steps compared | Result |
| --- | --- | --- |
| Vert | 1–20 | Every available spring value and phase exact |
| TLM_Constant_UDL | 1–10 | Every available spring value and phase exact |
| Pushover_5Axle_P1 | 1–58 | Every available spring value and phase exact |

All 77,080 spring identities are checked at each of the 88 commits: **6,783,040 spring records**, with exact U, F, Phase, Fy1/Fy2, Up1/Up2, N and SpringType. Available private spring fields at the final Vert and constant-load states also match, excluding native NULL energies. Local element states, reactions and available full global displacement vectors match exactly. Every committed-step iteration count matches the original trace.

Both solvers fail to converge at pushover attempt 59 with code -2. Step zero remains an initial state, not a committed step. The reference contains no rollback in this chain. The input HRX and Results hashes are unchanged.

The mechanical chain was solved at `9db0dc6`, using native UMFPACK controls: strategy 3, refinement 2, AMD ordering. Two subsequent output corrections at `533f374` and `139af0d` were checked by replaying saved Python states: all 91 model-point snapshots, including initial states, and energy totals at all 88 commits match exactly. This replay does not repeat the mechanical solve or inject reference values. The energy replay calls the production compiled accumulator.

The decisive controller corrections preserve the original quadratic arc-length calculation and close the final load-controlled interval using target multiplier minus accumulated multiplier. Before the latter correction, the final constant-load displacement had a last-bit difference that propagated into a pushover phase mismatch. Direct fixtures invoke original C# routines for the controller, displacement projection, node averaging and energy accumulation. See the [native construction and update audit](dhir-native-construction-and-update-audit.md) for the earlier arithmetic corrections and whole-model checks.

The full suite passes **757 tests and 1,418 subtests**, with 14 skips. [Compact evidence](../../release-evidence/dhir/2026-10-14-full-chain-progress.json) records provenance, hashes, scope and validation. Paired arrays remain in `dhir-installed-chain-native-load-endpoint/static/every-step` under the local audit directory.

This establishes available-output parity for this model and configuration. Complete native pushover private histories and global displacement vectors are unavailable; native NULL per-spring energy fields are excluded. C# Work-criterion acceptance still fails Python's separate equilibrium audit, retained under the selected warn policy. Matching C# outputs does not qualify independent equilibrium. Remaining masonry branches are listed in the [source audit](masonry-source-audit-2026-10-14.md); modal reference validation is recorded in the update below.


## Fresh released-package confirmation, 2026-10-15

The published v1.5.0 wheel at `7fa31ab` has now repeated the full mechanical solve
and corrected output projection together. All available measured fields have
zero absolute difference across all 91 states, including the three initial
states. The 88 commits contain 6,783,040 spring records. All committed iteration
counts match, and attempt 59 stops with code -2 in both solvers. Reference files
are unchanged. This supersedes the output-replay-only limitation for the
released package. Native UMFPACK controls remain strategy 3, refinement 2, AMD.

[Released-package evidence](../../release-evidence/dhir/2026-10-15-v1.5.0-fresh-full-chain.json)
records the full field list and provenance. Modal validation is now recorded
separately in [the modal benchmark](dhir-modal-native-parity.md). Post-release
elastic branch and modal precision changes pass the 2026-10-15 full suite:
764 tests, 1,429 subtests and 14 skips. The static full-chain run qualifies the
released wheel; the new elastic branch has native routine and compiled lifecycle
tests, rather than a new structural benchmark. The independent equilibrium
qualification and unavailable native measurements remain unchanged.

## Post-release branch rerun, 2026-10-15

A fresh full-chain solve at `8138ddd` repeats the native comparison after the
elastic/zero-friction/restraint-axis changes and the NR=False/contact audit.
Vert 1-20, constant load 1-10 and pushover 1-58 match every available checked
field exactly. All 6,783,040 committed spring records and all 91 states including
initial states have zero numeric differences and matching available identities.
All 88 committed iteration counts match the original trace. Both solvers stop
at pushover attempt 59 with code -2; reference files are unchanged. The original
UMFPACK strategy 3, refinement 2 and AMD ordering are applied explicitly.

[Post-branch evidence](../../release-evidence/dhir/2026-10-15-post-branch-full-chain.json)
records the field maxima, provenance and terminal outcomes. This run qualifies
8138ddd. The later omitted-material defaults, shear alias, singular-tangent
fallback and horizontal direction-selector changes have separate native tests;
this run is not a full-chain qualification of those later commits. Missing native
measurements and independent equilibrium limitations remain unchanged.

## Current-source regression, 2026-10-15

A fresh complete run at 02f5f84 now includes the omitted-material defaults,
shear-strain alias/Single promotion, load-direction selection, Newton-call
fallback scope, exact-zero-column shortcut and numeric-failure retry cleanup.
The material-146 assignment is reapplied to all 148 foundation interfaces after
fresh geometry generation, preserving the accepted native registration strategy.

All 88 committed states and all 91 states including initial states match every
available checked field and identity exactly: 6,783,040 committed spring records
and 80,059,459 compared numeric values. All 88 iteration counts match the original
native trace; both solvers stop at pushover attempt 59 with code -2. Original
reference hashes are unchanged. The read-only audit uses an indexed SQLite
backup; only indexes are added and no data rows are changed.

[Current-source evidence](../../release-evidence/dhir/2026-10-15-current-full-chain.json)
records measured field maxima, trace hash and source provenance. This supersedes
the source-boundary limitation of the earlier 8138ddd regression for these
changes. The separate [horizontal reference](dhir-horizontal-native-parity.md)
now matches all 521 commits through its final pushover step 501. Missing native
measurements and independent equilibrium limitations remain as described above.

## Snapshot performance regression

A fresh run at ed8a104 after Newton snapshot buffer reuse retains exact checked
output at all 88 commits and all 91 states. Every native committed iteration
count matches, and both solvers stop at attempt 59 with code -2. Reference
hashes are unchanged. [Evidence](../../release-evidence/dhir/2026-10-15-snapshot-reuse-full-chain.json)
and the [performance report](newton-snapshot-reuse-performance.md) record source
boundaries and timing scope. Later norm-helper corrections have original-routine
bit-exact tests and do not alter this model's Work convergence decision.

## Virgin tangent and precision audit regression, 2026-10-16

A fresh full-chain run at 97a8cd5 retains exact equality for every available
checked output through Vert 20, TLM_Constant_UDL 10 and pushover 58. All 88
committed iteration counts match the original trace, and both solvers stop at
attempt 59 with code -2. The audit covers 6,783,040 committed spring records;
step zero remains an initial snapshot. The original HRX and Results hashes
are unchanged. Foundation material 146 is applied to all 148 selected fresh
interfaces before Vert.

[Evidence](../../release-evidence/dhir/2026-10-16-virgin-tangent-full-chain.json)
records field maxima, coverage and source provenance. This run includes the
virgin E1p tangent correction and prior precision fixes. The later 9c622b4
saved-force cache change has separate native P-Delta chain coverage; this Dhir
reference has no P-Delta updates. Independent equilibrium warnings and missing
native measurements remain outside the available-output parity conclusion.
