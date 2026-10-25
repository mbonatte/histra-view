# Faster linear-library screens, 2026-10-15

The user permits small global-analysis rounding differences from faster
libraries while retaining original C# logic and exact routine tests. Complete
response histories and terminal behavior therefore determine qualification;
an accurate individual matrix solution is insufficient.

## Configurations and measured scope

The exact reference uses the installed native UMFPACK library, strategy 3,
AMD ordering and two iterative-refinement steps. Candidates use either SciPy
SuperLU or the existing fast UMFPACK profile (METIS, no refinement). Model
construction, constitutive laws, load definitions, convergence criterion and
analysis limits are identical. Python regenerates geometry; the separate Dhir
chain reapplies material 146 to its 148 foundation interfaces.

Global screens capture every available reaction, energy and model-point
displacement state, plus global DOF vectors where the reference supplies them.
They exclude private/local spring histories. A separate complete SuperLU Dhir
audit measures all available saved local fields. Initial step zero is excluded
from committed-step counts. Original HRX/Results files remain untouched.

The initial displacement component envelope is atol=1e-8 in native units,
rtol=1e-6; energies use atol=1e-6, rtol=1e-6. The later reaction-vector screen
uses L2(error) <= 1e-5 kN + 1e-8 * max(L2(reference), 1 kN), retaining the earlier
near-zero component failures. After numeric cutoffs were exceeded, fresh
observational runs recorded exceedances and continued to the natural stop.
Continuing an experiment does not convert an exceeded limit into a pass.

## Foundation-modified Dhir chain

Both candidates reproduce all 20 Vert / 10 constant-load / 58 pushover commits
and stop at pushover attempt 59 with code -2. Available reaction and model-point
displacement histories are exact. Maximum available global-vector differences
are 2.89e-15 (SuperLU) and 2.72e-15 (fast UMFPACK); measured energy differences
are below 7.24e-10 in native units.

The complete SuperLU local audit finds 14 phase-label differences among
6,783,040 committed spring records, all in unloading/reloading labels 3–6.
There are no measured rupture/slip phase differences in that run. Maximum
measured spring force/displacement differences are 4.50e-10 kN / 9.44e-13 in
native units. These are not bit-exact local histories and do not qualify
unmeasured private state. The lighter fast-UMFPACK screen excludes local fields.

## Horizontal terminal sensitivity

Fast UMFPACK reaches the displacement limit at attempt 495 after 494 pushover
commits, whereas the exact reference commits 501 and stops at attempt 502.
Its governing failed-trial element is Quad 494 (23.42085 cm, nine iterations),
versus native Quad 135 (18.68671 cm, six iterations). The last committed load
factor is 56.97843 versus 57.54830, a difference of about 0.99%. This candidate
is **not qualified for the complete horizontal analysis**.

Common-step load-factor differences remain around 1e-12 through step 300,
then grow near the end. Small initial rounding errors do not establish
preservation of the final nonlinear response. The experiment alone does not
identify the first diverging local constitutive branch.

SuperLU commits step 502, while C# stops before committing that step. The
comparison callback then interrupts because the native state is missing; this
is a harness limitation, not a measured natural solver stop. Its available
common-step model-point displacement difference reaches 1.35e-4 cm, with a
maximum structure-scaled difference of 3.89e-4. Fast UMFPACK reaches 3.22e-5 cm
and 9.90e-5 over its common states. Both exceed the initial numeric envelopes.
Neither candidate is qualified across both complete references.

[Compact experiment evidence](../../release-evidence/performance/2026-10-15-fast-library-global-response.json)
records all field maxima, missing terminal information, raw report hashes and
source-provenance limits. The older Dhir candidate harnesses did not embed a
launch commit; these measurements are not final-release artifact certification.

## Original source check and recommendation

Original `SparseMatrix.InitializeControl` calls native defaults and sets slot
5 to strategy 3. Original `NewtonRaphson.solveCurrentStep` solves, updates,
assembles residual and calls the convergence test in that order.
`CTestEnergyIncr.test` computes FindMaxU and Work, accepts passing Work first,
then checks iteration and element-displacement limits. Python retains that
ordering. No convergence or displacement limit is changed to obtain a pass.

Use the explicit native reference controls for reproducing these complete
histories. The separately qualified [snapshot optimization](newton-snapshot-reuse-performance.md)
improves performance without changing their measured results. Candidate
backends remain model-dependent experiments. Diagnostic elapsed times include
different export volumes and concurrent workers; they are not fair backend
speed comparisons.
