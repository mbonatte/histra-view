# Dhir horizontal out-of-plane comparison, 2026-10-15

Python now matches every available checked C# 2026.1.1 output through the last
committed step of the horizontal model. It reconstructs the computational model
from geometry and uses the default masonry materials throughout, as confirmed
by the user. No saved native interfaces, springs or histories enter the solve.

| Analysis | Committed steps compared | Result |
| --- | --- | --- |
| Vert | 1-20 | Available identities and numeric fields exact |
| Pushover_5Axle_P1 | 1-501 | Available identities and numeric fields exact |

The 521 commits contain **40,158,680 spring records**: all 77,080 spring identities
are checked at every commit. Across 523 states, including two initial states,
all 434,705,854 compared numeric values have zero absolute difference. Step zero
is initial and is not counted as a commit. Available spring U, F, Phase, Fy1/Fy2,
Up1/Up2, N and SpringType, interface forces/moments and local displacements,
Quad states, restraint/NodeC states, reactions, energies and model-point outputs
match exactly. Saved private spring fields and full global vectors are checked
where present; their absence elsewhere is recorded as unavailable.

Both solvers retain step 501 as their final commit and stop on attempt 502 at
the configured element-displacement limit (Python code -3). The native HRX
records LargeDisplacement and 18.69 cm at Quad 135; Python logs a maximum of
18.68671 against the same limit of 10. The native description reports six
iterations for that failed attempt. No horizontal native iteration trace was
available, so this comparison does not claim equality of all iteration counts
or identification of the failed Python element from the retained log.

## Original-source corrections exercised

The HRX's line-load item selects IdLoadDirection=2 (global +Y), while its stored
DirX/DirY/DirZ vector is still (0,0,-1). Original LoadTemplateItem.Dir(Element)
uses the direction selector first. Python now follows that selection and the
native Single normalization. The six loaded Quads are 1771, 1776, 1857, 1801,
1827 and 1832; +Y is normal to their spandrel surfaces. Direct fresh original
construction matches all 16,408 load-vector entries and all 425,560 stored
initial stiffness entries exactly.

Original StaticIntegrator.UpdateK retries a failed tangent factorization with
alfa=0. That value persists inside the current Newton call; the next call gets
the outer argument again. Python now preserves that by-value call boundary.
Native fixtures exercise regular, recoverable and unrecoverable systems, and a
two-step controller regression guards against retaining the local fallback
across steps. See the [masonry source audit](masonry-source-audit-2026-10-14.md).

A compiled exact-zero-column check avoids factorizing a guaranteed singular
matrix, invoking the same fallback without changing matrix entries or using a
rank tolerance. This full run exercises nine such shortcuts across 543 checks
and preserves exact committed output.

## Provenance and limits

[Compact evidence](../../release-evidence/dhir/2026-10-15-horizontal-full-chain.json)
records hashes, measured fields, coverage and terminal metadata. The mechanical
run qualifies the numerical source committed as c5ed111. The later UMFPACK
numeric-failure retry cleanup at 02f5f84 has native unit coverage and a separate
[fresh original-Dhir full-chain regression](dhir-full-chain-native-parity-progress.md).
Native controls are UMFPACK strategy 3, refinement 2 and AMD ordering.

The original horizontal.hrx and horizontal.Results hashes are unchanged.
Comparison reads a SQLite backup with added audit indexes; no data rows are
modified. Paired arrays and per-state summaries remain under the local audit
folder horizontal-native-exact-rank/static/every-step.

Native NULL spring energies are excluded. Complete private pushover histories
and full global vectors are not saved at every step. This horizontal Results
file contains no modal values. Python's separate equilibrium audit remains
active under the selected warn policy: 18 Vert commits and all 501 horizontal
commits fail that independent check despite matching C# Work acceptance and
saved outputs. This establishes available-output parity for this reference,
not independent equilibrium or equivalence for every masonry input.

## Snapshot performance regression

The complete chain was repeated at ed8a104 with reusable Newton snapshot
buffers. Every available checked output and identity remains exact across all
521 commits and 523 states. Both solvers retain step 501 and stop on attempt
502 at the displacement limit. Original reference hashes are unchanged.
[Evidence](../../release-evidence/dhir/2026-10-15-horizontal-snapshot-reuse-full-chain.json)
and the [performance report](newton-snapshot-reuse-performance.md) describe the
source boundary; faster library configurations are evaluated separately.

## Virgin tangent and precision audit regression, 2026-10-16

A fresh chain at 97a8cd5 preserves exact equality for every available checked
field and identity across Vert 20 and horizontal pushover 501. Step zero is
excluded from the 521 commits. Python retains committed step 501 and stops
at attempt 502 with code -3, reaching the same displacement limit as C#.
Original reference hashes are unchanged.

[Evidence](../../release-evidence/dhir/2026-10-16-horizontal-virgin-tangent-full-chain.json)
records the measured coverage and source boundary after the virgin tangent
and precision corrections. The subsequent 9c622b4 saved-force cache change
has separate native P-Delta chain tests; this reference has no P-Delta updates.
Unavailable private histories, the absent native iteration trace, and the
independent equilibrium limitations described above still apply.
