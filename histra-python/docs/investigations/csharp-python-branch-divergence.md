# C# / Python nonlinear branch-divergence investigation

## Scope

The supplied bridge model contains a vertical predecessor analysis followed by
an arc-length live-load analysis. The C# `.Results` database is authoritative.
The investigation compared committed states from the first vertical step
onward rather than beginning at the later live-load termination.

## Reconstructed workflow

Both implementations assemble the target load, build an initial tangent, form
a predictor, iterate Newton/line-search corrections, update trial element
states, evaluate energy convergence, and commit only after convergence. A
failed trial restores a pre-step snapshot before retry or termination.

Two implementation differences were confirmed:

1. C# solves sparse systems with SuiteSparse UMFPACK, while the Python snapshot
   used SciPy SuperLU.
2. C# subtracts the predecessor graph displacement before passing the control
   displacement to the integrator commit decision. Python previously passed
   the absolute displacement.

The second discrepancy is corrected in `solve.py`. It affects chained-analysis
arc-length decisions, but it is not the origin of the vertical branch split.

## Earliest detected divergence

Vertical committed steps 1 through 9 have identical spring phases. At step 9,
the maximum local spring-displacement difference remains approximately
`3.27e-11`. At vertical step 10 the solutions select different equilibrium
branches:

- 724 spring phases differ;
- maximum spring displacement difference is approximately `5.776e-3`;
- maximum spring stress difference is approximately `8.767`;
- the governing change is a Quad diagonal Coulomb spring entering `Slip` in C#
  while remaining `Elastic` in Python.

A representative governing spring is identified by the stable tuple
`(ParentType=106, ParentKey=100, SpringPurpose=30, IdLocal=0)`. In C#, its
step-10 local displacement is about `-7.00055e-3` and its force is zero in the
Slip phase. Python remains near `-1.22459e-3`, force `-8.76669`, Elastic.

This is a discontinuous branch-selection event, not gradual constitutive drift.
The model is effectively coincident through step 9 and then amplifies a very
small numerical perturbation when a diagonal friction limit is reached.

## Root-cause status

The divergence has been isolated to the sparse linear-solver/evaluation path at
a branch-sensitive step. Regula-Falsi shortcut removal, SuperLU iterative
refinement, alternate SuperLU ordering and disabling the compiled Quad path did
not reproduce the C# branch. Exact proof requires rerunning Python against the
same native UMFPACK library used by C#; that library was not available in the
analysis environment.

The repository therefore provides a direct `umfpack_di_*` backend rather than
introducing convergence workarounds or changing tolerances. An explicit
`linear_solver_backend="umfpack"` parity run is required before claiming exact
C# branch parity.

## Chained live-load behavior

Restoring the authoritative C# vertical step-15 state lets the current Python
implementation commit live-load steps 1 through 31 and stop on the same maximum
model-displacement criterion on the attempted next step. Starting from
Python's own vertical state follows a different internal path, confirming that
the late live-load discrepancy is inherited from the predecessor state.

The supplied Python snapshot did not reproduce a literal termination at
committed step 27 in this environment; it passed that step but diverged in its
step and iteration history. This result should not be hidden by changing
iteration limits, arc-length radii, tolerances or failure criteria.

## Validation boundary

- Python test suite: all normal tests pass.
- C# executable regression: not run because no .NET/Mono toolchain was
  available.
- Native UMFPACK parity run: not run because no loadable UMFPACK library was
  available.
- C# per-Newton-iteration comparison: impossible from the supplied `.Results`
  database, which stores committed states but not Newton trial states.
