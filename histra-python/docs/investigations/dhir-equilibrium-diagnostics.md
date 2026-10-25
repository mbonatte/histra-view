# Dhir equilibrium diagnostics against original C# routines

The checked Dhir residual warnings do not originate from a Python residual
assembly discrepancy. Original C# force assembly reproduces every one of the
16,408 Python residual entries exactly in five selected committed states.
Original CTestEnergyIncr accepts each state's Work value; original
CTestNormUnbalance continues iterating when given the same numeric tolerance
of 0.002. These are different tests with different quantities and units.

## Native routine replay

The oracle freshly generates native geometry, interfaces and afference. For
the foundation-modified chain it reapplies material 146 to all 148 selected
foundations using original ReSetInterfaces. Controlled GetForce implementations
supply the saved native force for all 77,080 spring identities. Original
Interface/Quad resisting-force assembly and ModelManager.formUnbalance then
construct the residual using the exported Fext. Original convergence routines
receive the exported correction vector. All 82,040 compared residual entries
match Python exactly. This isolates routine behavior; it does not repeat the
independent native nonlinear solve or reconstruct private constitutive history.

| Model/state | Native Work (kN cm) | Native raw residual L2 | Max translation residual (kN) | Max rotation residual (kN cm) | Max internal shear-angle residual (kN cm) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Horizontal, Vert 20 | 0.00196529 | 1469.14 | 3.07704 | 83.0185 | 833.489 |
| Horizontal, pushover 1 | 0.00199267 | 4535.05 | 2.80939 | 75.0381 | 2206.82 |
| Foundation-modified, Vert 20 | 0.00199692 | 1505.14 | 3.94582 | 187.659 | 812.102 |
| Foundation-modified, constant load 10 | 0.00199917 | 1421.01 | 9.50347 | 452.291 | 612.497 |
| Foundation-modified, pushover 1 | 0.00195971 | 1334.13 | 11.6730 | 557.826 | 519.788 |

The native fresh afference export verifies seven independent DOFs per Quad for
this model: three translations, three rigid rotations and the internal shear
angle. The seventh DOF is dimensionless and its work-conjugate generalized
force has moment units: original Quad.SetResistingForce multiplies the diagonal
spring force by DAlfa2DDiag, which has length units. The largest raw component
in both Vert states is Quad 487's internal shear-angle DOF (global DOF 3409).

The raw L2 value combines forces and generalized moments. It is not a total
unbalanced force in kN, and it must not be compared directly with the total
support reaction. Local translational residuals also remain nonzero, as the
table shows. Global reaction balance alone does not establish local equilibrium.

## Meaning of the warning

Work evaluates half the absolute scalar product of correction and residual.
Small corrections and cancellation can make it pass while the residual norm
remains above a separately imposed threshold. The numerical value 0.002 in a
Work test is an energy threshold; using 0.002 for the independent raw residual
is a different requirement, not an equivalent interpretation of Work.

Python retains both independent checks, their explicit limits, and the
warn/error policies. No warning is hidden and no threshold is relaxed by this
investigation. The results establish native acceptance parity, rather than a
claim that the configured response satisfies every alternative equilibrium
criterion. An engineering choice of dimensional/normalized equilibrium limits
requires its own qualification; changing criteria or tolerance is a new analysis.

## Norm-selector correction

Inspection also found an independent Python defect: positive norm selectors
other than 2 previously returned the maximum absolute component. Original C#
uses the ordered p-norm for every positive selector and the maximum norm for
nonpositive selectors. Python now uses a compiled ordered reduction matching
all 48 checked native b/x norms exactly, including p=1, 2, 3 and 4. Actual Work
and force-test values at the five Dhir states also match bit-for-bit. Existing
fail-closed handling of NaN maximum norms remains in place.

The small previous NumPy/ordered L2 rounding difference was a few ULPs and
cannot explain residuals of this size. The selected Work path does not call
these norm helpers to decide convergence; its mechanical update is unchanged.
The completed exact snapshot regression uses source ed8a104, before the norm
correction. Faster-library global screens use the corrected norm helpers.

[Compact evidence](../../release-evidence/equilibrium/2026-10-15-native-residual-investigation.json)
records group values, source provenance and native routine decisions. The
portable native fixtures retain exact binary vectors and expected error bits.
The full suite passes 796 tests and 1,614 subtests, with 14 skips.
