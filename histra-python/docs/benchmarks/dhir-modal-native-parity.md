# Dhir modal comparison against C# 2026.1.1

Python regenerates the Dhir geometry with the default masonry materials, before
changing the 148 foundation interfaces to material 146 for the static chain.
The existing installed-run reference supplies all 20 modes and 328,160 shape
components. No saved computational interfaces or spring histories are reused.

The fresh v1.5.0 wheel initially differed by up to 1.735e-8 relative in frequency.
The source audit traced the main difference to input precision in mass assembly:
`Operations.g` and `MasonryMaterial.w` are C# `System.Single` values promoted to
double. Python now preserves those conversions. The native fixture calls the
original `Quad.ComputeLocalMassfromSelfWeight` routine and checks the gravity,
weight and translational mass block.

| Quantity | Maximum absolute difference after correction |
| --- | --- |
| Frequency | 3.36e-13 |
| Total mass, each direction | 7.11e-15 |
| Mode-shape component | 5.99e-12 |
| Participation coefficient | 5.93e-12 |
| Effective modal mass | 2.63e-12 |
| Modal mass percentage | 7.48e-12 |

Maximum relative frequency difference is 2.60e-14. Minimum MAC is
0.9999999999999997. These are numerical agreement measurements, not bit-exact
parity. Relative differences for almost-zero participation coefficients remain
larger; the [compact evidence](../../release-evidence/dhir/2026-10-15-modal-single-inputs.json)
records both absolute and relative differences for every compared field.

The run uses native UMFPACK, strategy 3, refinement 2 and AMD ordering.
The original inverse-iteration convergence gates and discovered signs/order are
preserved. This qualifies the recorded virgin Dhir modal configuration only.
Exact rotational mass-integration operation order, other masonry branches and
modal analyses following nonlinear predecessors remain separate validation work.
The tiny native rotational coupling in the isolated symmetric Quad fixture is
retained as evidence, rather than claimed as an exact match.
