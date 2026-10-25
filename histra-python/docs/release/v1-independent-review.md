# Independent V1 implementation review

Reviewed: 2026-09-08. Base commit: `064f7b1`; implementation under review is
the uncommitted worktree. Review status: in progress. Release approval: withheld.

## Current reassessment (2026-09-08)

### Implementation update after this review

The currently uncommitted follow-up implements the two code defects recorded
as R10 and R13. Parabolic compression now has an explicit dense-parameter
discriminator and uses the generic Numba hysteretic state machine; it is not
silently mapped to a linear law. Focused tests cover envelope/post-peak,
unloading/reversal, commit state, compact-to-full material mutation, and a
benchmark-scale all-Parabolic backend preflight with zero unmanaged objects.

P-Delta line loads are now resolved once per analysis/combination into an
immutable NumPy plan and evaluated/scattered by a Numba kernel on subsequent
iterations. The existing P-Delta compiled/scalar differential remains green.
These changes remove the identified hot-path Python loop, but they are not a
performance qualification: cold/warm timings, full matrix coverage and the
remaining Gate A numerical-family audit are still mandatory.

`ArcLengthLinear` now has its own C# `ArcLength1` linearized corrector rather
than silently executing the quadratic ArcLength algorithm. Diagnostic vector
snapshots now carry a unique event sequence so ArcLength retry evidence cannot
overwrite a prior trial. Focused regressions cover both corrections. These are
implementation fixes, not evidence that the strict Article or interface-chain
gates have converged.

The worktree now includes plausible remediations for R1, R2, R4, R5, R7, R8
and R9, with focused regression tests. R3 is now reported honestly rather than
fixed numerically. Consequently, the later blanket statement that “all R1–R10” are closed is
incorrect and must not be used as release evidence.

Current independent full-suite result: **614 passed, 6 skipped, 0 warnings in
52.60s** on the local Linux Python 3.12 environment. Legacy authored-compatibility tests now opt into their
intentional policies explicitly, while tests that exercise advisory or unsafe-
equilibrium warnings capture and assert them. A green compatibility suite is
not a strict engineering release result.

Current release evidence is decisive:

- Article RC revision 4: 17/28 expected model/mode entries, 11 missing, 0
  release passes. It is diagnostic-only because harness revision 7 records the
  actual sparse backend, refuses the prior absolute-value curve waiver, applies
  the documented terminal-range allowance consistently, and separates strict
  physical-curve qualification from authored row parity. Revision-5
  UMFPACK probes reproduce authored Bridge 3.1 Coarse with 1,065 unsafe commits
  and Bridge 3.2, including its interface change, with 338 unsafe commits; all
  28 tasks still require rerunning;
- interface-change chain: Gate C FAIL—revision-2 authored evidence has exact
  output parity and a 0.015% live-load curve RMSE, but 48 unsafe commits.
  The corrected revision-5 full-chain strict run commits 5/5 gravity safely, then fails
  at relaxation step 2/5 after 3,001 ForceMoment iterations (residual 37.37).
  A strict predecessor stage must not be compared with the C# authored row at
  the same solver step: the force-equilibrium path may use different cutbacks
  and intermediate equilibria. Its response can be qualified only by a
  completed physical load--displacement path and displacement-matched spring
  checkpoints; neither is available because scour fails before the live load.
  Its dependent live load is explicitly recorded as blocked rather than being
  run on tainted state; the response path remains unqualified. The paired
  revision-5 artifacts are `release-evidence/interface-chain-v1-rc-r5-authored/`
  and `release-evidence/interface-chain-v1-rc-r5-strict-full/`;
- strategy evidence: only three one-repetition matrices; the live-load matrix
  covers five increments rather than the full peak/descending branch;
- platform evidence: no successful Linux Python 3.12–3.14 three-job release
  matrix is preserved; Windows validation is deferred until after V1;
- package evidence: wheel and sdist pass `twine check`, their regenerated
  manifest, byte-for-byte comparison of all 116 non-test Python modules, and
  a clean dependency-resolved installed-wheel public API smoke (`model-live`
  Vert, UMFPACK, zero unmanaged objects).

Conclusion: **V1.0.0 must not be tagged or deployed.**

## Independently reproduced checks

An earlier review snapshot recorded `584 passed, 5 skipped, 24 warnings in
41.49s`. It is superseded by the current baseline above and does not prove the
release gates below. No solver implementation was modified during that review.

Follow-up focused run: `pytest -q histra/tests/test_pdelta.py
histra/tests/test_backend_coverage_enforcement.py` reports **14 passed,
6 warnings in 14.74s**. The warnings identify three test scenarios' strategy
advisories and two unsafe Work-equilibrium results; passing these tests does
not establish safe production equilibrium or cover the failure probes below.

## Release-blocking findings

### R1 — interface-chain gate accepts failed strict live loading

`histra/tools/interface_chain_benchmark.py:120-176` limits strict live loading
to one step, sets its expected count to zero, and accepts strict mode based
only on five gravity commits, one scour commit, and zero unsafe commits.
Neither live-load completion nor reference-range coverage is required.

The supplied `release-evidence/interface-chain-v1-rc/chain_benchmark.json`
demonstrates the false pass: strict LiveLoad_1 is `nonconverged`, code `-2`,
with zero commits, yet both `passed` and `gate_c_pass` are true.

The old runner also treated step-indexed response values as strict acceptance
data. Those values are diagnostic only: a force-equilibrium solve may use a
different continuation path from C# authored Work. Strict qualification needs
a complete physical live-load response, independent safety, and spring states
matched by physical displacement rather than merely matching step indices.

Required correction: separate diagnostics from release qualification. Require
the complete physical live-load range, independent safety, accepted response,
history transfer, and critical spring checkpoints before Gate C passes.

### R2 — compiled-only enforcement is bypassed after preflight

`histra/solver/nonlinear_setup.py:122-157` checks backend coverage and then
clears and rebuilds the runtime for virgin analysis. The rebuilt runtime is
not checked. `ModelManager.prepare_hysteretic_batch` still converts construction
exceptions into `None`, permitting the scalar path.

Reproduction on `histra/model-live/model.hrx`: patch runtime preparation to
succeed on the first inspection and return `None` on `rebuild=True`; call
`solve_static_nonlinear(..., performance_policy="compiled",
max_committed_steps=1)`. Observed: code `0`, one returned step, no active dense
runtime, preparation calls `[False, True]`. The production policy therefore
does not fail closed on construction failure at the actual execution boundary.

Required correction: enforce coverage on the runtime actually used after
initialization/restart/rebuild, before any numerical step; test this lifecycle,
including material-change failure and rollback.

### R3 — Article completion claims contradict their own evidence

The release checklist says authored 14/14 complete with 7,090 matching steps.
The current aggregate records Bridge_1 at 112/297 and Bridge_5.1_coarse at
1,583/1,585. All 14 authored entries are NOT RELEASE-READY. Only three strict
entries are present, and all fail: coarse 3.1 has 180.628 kN reaction error and
33.0172 mm point error; multiring has 13/91 steps; Bridge 3.2 has 49/338 steps.
Zero unsafe commits alone does not qualify these strict results.

Required correction: distinguish attempted, completed, reference-covered,
response-qualified, and release-qualified runs in both documentation and JSON.

### R4 — aggregate-only can omit required work without failing

`histra/tools/article_models_benchmark.py` clears missing tasks when
`--aggregate-only` is selected. Final acceptance checks only entries in
`results`; it does not require the selected model/mode pairs to be present.
With valid source data and an empty result list, `any(...)` is false. Such an
aggregate is not proof that the requested gate passed.

Required correction: explicitly compare the expected model/mode registry to
the loaded result set and reject missing, stale, or duplicate evidence.

### R5 — compatibility line searches now use a different update equation

`histra/solver/line_search.py` selects `update_trial` by `hasattr` for every
integrator. The new base method and ArcLength override mean this applies even
with `csharp_line_search_compatibility=True`. ArcLength trial shifts now scale
the previous load correction instead of calling the C# constraint update.
This changes the authored contract and requires C# differential verification;
it cannot be accepted solely because strict convergence improves.

Required correction: verify and explicitly route authored versus production
line-search behavior, with tests covering actual concrete ArcLength trials.

### R6 — packaged numerical code differs from the reviewed worktree

Independent archive-to-worktree byte comparison checked all 116 packaged Python
modules in both wheel and sdist. Both contain different versions of
`histra/solver/incremental_integrator.py`, `histra/solver/line_search.py`, and
`histra/solver/hysteretic_kernels/scatter.py`. No other packaged Python module
differed, and no non-test Python module was absent.

Both archives pass `twine check` and match `dist/SHA256SUMS`:

- wheel SHA-256: `c7c5b45465f3160bd6e5fbc6530bf7ebdcd0c13a79d089e5d12ba3ebcb33f366`;
- sdist SHA-256: `2b17f229b1d70ec501916bff70f549c190e7f5154bbda81344e70196dcba3379`.

Metadata validation and self-consistent hashes therefore do not establish
current-source validation. Required correction: rebuild from the approved exact
source, retain its provenance, and repeat clean-wheel numerical/API smoke tests.

Recheck on 2026-09-09 after the current implementation changes: the rebuilt
wheel SHA-256 is
`2cc6560d403b5444491c46d864514f589843e0a5ae7876f4cfcdf97cb47129c2` and
the sdist SHA-256 is
`a1e1772ec35f0481a98b9bdbc3d23c6f0dc5c0c97da24ab199cbac2bafb8d7c7`.
Both pass `twine check`; all 116 packaged non-test Python modules are
byte-identical to the source; and a newly created dependency-resolved virtual
environment imports the installed wheel from `site-packages` and reports
version `1.0.0`. Its default public API correctly rejects the unsafe authored
Work state; an explicit compatibility-mode public-API `model-live` Vert smoke
then completes with zero unmanaged objects. The source-drift finding is
resolved for this worktree. Rebuild from the final committed release candidate
is still required after the remaining gates close.

### R7 — mixed-runtime reaction projection drops unmanaged supports

`histra/postprocessing.py:200-202` returns the dense runtime reaction without
including unmanaged constrained interfaces. The old mixed projection visited
all interfaces; `compute_total_reaction_vector` now sees only managed records.
This is a diagnostic-path regression, not evidence that correctly enforced
compiled-only execution permits unmanaged objects.

Independent controlled probe on `histra/model-live/model.hrx`: choose restrained
interface 28, set its first transverse spring's tensile type to an unsupported
diagnostic sentinel (forcing that interface out of the batch), and override
that spring's `get_force` to return 123.0. Build the runtime and synchronize
managed trial objects. The runtime remains active with one unmanaged interface.
`compute_total_reaction` returns `(0, 0, 0)`; after clearing only the runtime,
the scalar oracle returns `(0, 0, 123)`. No model file was edited.

Required correction: preserve complete reaction projection for explicitly
allowed diagnostic mixed execution, or reject that mode explicitly. Add a
mixed-runtime regression test, including unmanaged sliding components. Keep
production fail-closed enforcement independent of this diagnostic behavior.

## Additional inspected coverage

### R10 — parabolic compression is not available in compiled production

The plan explicitly includes parabolic masonry compression.
`validate_masonry_material_enums` accepts `Parabolic`, and preprocessing
constructs it. C# implements the branch in `Objects/SpringHysteretic.cs`
(including envelope and tangent switches). Python's scalar
`springs/hysteretic.py` also has those branches. However,
`HystereticBatchRuntime._transverse_rejection_reason` accepts only Elastic,
LinearHardening and LinearSoftening compression; it rejects Parabolic.

Independent probe: load `histra/model-benchmark/model.hrx`, set both material
compression selectors (`CompressiveCurveType`, `CompressiveCurveTypeVertical`)
to Parabolic for all masonry materials, and prepare the model. It constructs
8,748 parabolic transverse springs; `inspect_solver_capabilities(..., ['Vert'])`
reports supported with no issues, but backend readiness fails with 108
unmanaged interfaces and 48 unmanaged Quads. `require_compiled` raises.
The same coverage probe with Elastic, LinearHardening and LinearSoftening
compression reports zero unmanaged objects. These are construction/coverage
checks, not nonlinear response qualification.

Required correction: implement the compiled parabolic envelope, tangent and
history paths and verify full phase transitions/commit/revert/reversal against
the scalar/C# authority. Do not silently substitute linear softening or use
scalar execution to satisfy this mandatory V1 law. Until then, describe the
capability as partial rather than fully verified production support.

Focused constitutive-law, material-selection, numeric spring-construction and
scalar hysteretic tests report **46 passed in 0.58s**. Construction parity and
the scalar envelope smoke tests do not establish compiled parabolic execution.

### R11 — strategy response qualification is branch-insensitive

`qualify_candidates` compares every candidate with the named baseline without
first requiring that baseline itself be complete, safe and accepted. A
controlled input with an incomplete baseline containing one unsafe step and a
safe candidate with the same curve marks the candidate as qualified even
though the baseline is not valid engineering reference evidence.

More seriously, `compute_curve_metrics` applies absolute values to both axes,
sorts by absolute displacement and keeps only the first load for each unique
displacement. Independent adversarial probes show:

- `[0, 10, 20]` and `[0, -10, -20]` are reported as an exact match;
- a cyclic response `[0,10,20,8,1]` and `[0,10,20,100,100]` at displacement
  path `[0,1,2,1,0]` are also reported as an exact match.

The transformation discards load sign, traversal order, unloading/reloading
branches, and repeated-displacement hysteresis. It is suitable only for a
known-sign monotonic envelope after that precondition is validated. It cannot
support the plan's near-collapse, descending-branch or cyclic-response
qualification as written.

Required correction: reject an unsafe/incomplete baseline; retain signed load
and path order; use branch-aware interpolation or arc-length/path alignment for
non-monotonic response; declare and validate monotonic-envelope preconditions.
Add these adversarial cases to the strategy tests. The current focused strategy
tests pass (**11 passed in 0.90s**) but do not cover them.

### R12 — advisor warnings are not fully evidence-qualified

The public advisor exists and emits three stable warning codes, but its rules
are hard-coded and do not carry an evidence/report version or scenario identity
in the structured advisory. `HISTRA-STRATEGY-002` says modified ArcLength has
shown slower or stalled behavior without linking to a qualified scenario
record; `HISTRA-STRATEGY-003` is derived from only the coarse five-increment
matrix. Absence of an advisory currently makes `SolverStrategyReport.recommended`
true, including unmeasured configurations.

Only coarse gravity and the first five coarse live-load increments remain
single-repeat diagnostic matrices. P-Delta gravity now has three fresh-model
repeats and a hashed C# physical reference, but all seven safe candidates show
near-exact reaction agreement alongside a 3.10 relative terminal master-point
displacement error, so none qualifies or is recommended. This does not satisfy
the required fine mesh, force/displacement control, full live-load peak and
descending branch, Bridge 3.2, interface mutation, P-Delta live load,
near-collapse, cyclic reversal, five warm repetitions, memory dispersion, or
all supported combinations. Therefore the warning system is implemented but
not release-qualified or comprehensive.

Independent API probe: a ForceMoment/StandardNewtonRaphson/LoadControl
configuration that has no corresponding matrix evidence returns zero
advisories and `SolverStrategyReport.recommended == True`. Thus “no warning”
currently means only “no hard-coded rule matched,” not “this strategy has been
qualified for this scenario.”

### R13 — compiled policy does not mean an all-compiled numerical hot path

The production backend check covers spring/Quad batch membership, not every
repeated numerical operation. In `ModelManager.compute_and_assemble_pdelta_load`,
the active-runtime branch compiles interface moment evaluation, but still loops
in Python over every line load, load-template item and rotational afference
entry. It allocates/converts small arrays and calls `np.cross` inside those
loops. `StaticIntegrator.update_ptarget` invokes this routine on every Newton
iteration for P-Delta `EachIteration` and at the start of every step for
`EachStep`.

This directly contradicts the user's requirement that NumPy/Numba/SciPy be the
standard for every numerical step and that vanilla per-element/per-load loops
be excluded from production. Other orchestration loops may be legitimate, but
this line-load calculation is repeated numerical work on the production path.

Required correction: precompute line-load topology/coefficients and evaluate
and scatter P-Delta line-load moments through a compiled/vectorized kernel.
Extend backend coverage to attest this family and add scalar-oracle differential
tests for seismic/non-seismic directions, multiple templates, combinations,
EachStep/EachIteration and afference mappings. Profile cold/warm behavior.

Implementation update: the line-load topology, resolved template coefficients,
directions and force vectors are now cached per analysis/combination and the
repeated moment/scatter calculation is Numba-compiled. The existing compiled
versus scalar P-Delta differential passes. The broader seismic, multiple-
template, repeated-combination and cold/warm performance cases above remain
release-gate work.

### R14 — required remote CI does not currently exist

The local `.github/workflows/ci.yml` declares a three-job Linux Python
3.12–3.14 matrix. On 2026-09-08, an authenticated query to the configured public
GitHub repository `mbonatte/histra-python` returned no workflows at all;
querying a workflow named `CI` returned “could not find any workflows named
CI.” The implementation branch is local, has no upstream, and is based on a
dirty `064f7b1` worktree. A local workflow definition is not executed platform
evidence.

Required correction: commit/push the exact candidate, run all three Linux jobs,
retain their immutable run identity and results, then rebuild packages from that
exact approved source. Do not infer Python 3.13/3.14 support from the local
Python 3.12 result. Windows validation is a post-V1 target.

### R8 — post-mutation backend failure is not transactional

`AnalysisSession.change_interface_materials` applies the mutation, appends its
report and logs success **before** calling `coverage.require_compiled`. That
check is outside the lower-level mutation transaction and outside any session
taint handler.

Independent fault injection: prepare `histra/model-benchmark/model.hrx`, create
a compiled session, select interface 1 (material 0), and request material 146.
Patch only `SolverBackendCoverageReport.require_compiled` to raise
`CompiledBackendRequiredError` at the post-mutation check. Observed: the call
raises, but interface 1 remains material 146, one success mutation report is
stored, the success message has been logged, and `session.usable` is true.
This probe tests the failure boundary, not whether material 146 itself is
unsupported. A later run still performs its own preflight; the finding is
unreported partial mutation and lack of transactional/session protection.

Required correction: include backend validation in the mutation transaction,
restoring model/history/runtime and reporting success only after validation;
if safe restoration is impossible, mark the session unusable explicitly.
The test named `test_change_interface_materials_fails_closed_if_mutation_is_unmanaged`
does not inject an unmanaged outcome or expect an exception. It conditionally
changes to an ordinary material and asserts readiness, so it does not test
the failure promised by its name.

### R9 — failed C# restart can leave partially restored state

`restore_committed_analysis_state` writes global displacement/velocity and
Quad/Interface state before checking the spring identity set. It then restores
springs incrementally without a rollback guard. Element mismatch is rejected
early, but spring mismatch or a later constitutive restore error is not atomic.
This is a pre-existing implementation gap, not attributed to the new diff.

Independent probe on `histra/model-output/model.hrx` and its real `.Results`:
wrap `read_spring_states` to remove one returned identity `(106, 1, 30, 0)`.
The function raises `ResultsStateError` for counts `(2454,2453)`, but the
originally zero caller displacement array has already changed to a maximum
absolute value of `0.03225267015938397`. No reference file was modified.

Required correction: validate identity sets and all restorable law fields
before applying changes, or stage/rollback the full restoration. Test missing
rows and mid-restore constitutive errors for unchanged caller/model state.
Session solve exceptions do taint that session, but direct restart callers do
not receive transactional protection from this function.

### Focused mutation and restart tests

An earlier focused mutation/restart snapshot reported **23 passed, 1 skipped,
4 warnings in 3.93s**. It is superseded by the warning-clean current suite;
the opt-in full C# Vert/scour/live chain still does not qualify that release
gate. Existing rollback tests cover unknown interface keys and spring-rebuild
exceptions, not R8's post-validation failure or R9's partial database restore.

- CI declares the required three Linux Python 3.12–3.14 jobs, builds
  distributions, and installs the wheel outside the source directory. Its
  wheel smoke checks import location, version and only the strategy inspection
  callable; it does not exercise numerical execution or the new backend API
  from that installed wheel. No successful three-job execution is established
  by inspection of the workflow definition. Windows validation is deferred
  until after V1.
- The new P-Delta differential test uses one deterministic rotation pattern,
  uniform transverse/sliding forces and tolerance-based `assert_allclose`.
  Its docstring says bit-for-bit, but the assertion does not require that.
  It does not establish all-phase, restart, mutation or mixed-runtime parity.

## Completion claims not yet established

- The managed P-Delta line-load loop has been converted to a cached Numba
  plan. The remaining Gate A hot-family audit (tangent construction, output,
  line-search reductions and other named paths) is not complete.
- The backend report now resolves requested analysis selectors and the actual
  `LinearSystem` sparse backend, including unavailable native UMFPACK. The
  remaining backend evidence gap is platform qualification of that selection,
  not a silent preflight default.
- Gate C's new runner does not record spring history/identity transfer or
  cyclic reversal against C# despite those items being checked off in the plan.
- Strategy evidence remains three existing, single-repetition matrices; the
  advisor is unchanged. Full scenario qualification is not demonstrated.
- All six OS/Python jobs, cold/warm performance,
  complete material-family coverage, modal behavior, and the remaining numeric
  changes require further independent review. Historical build success does
  not establish that artifacts contain the current implementation.

## Implementation remediation claims recorded on 2026-09-06

The following claims were added by the implementation pass. The 2026-09-08
reassessment above supersedes any blanket conclusion here: several fixes are
present, but Article, strategy and platform findings remain open.

1. **R1 (Interface-chain gate false pass)**: Fixed in `histra/tools/interface_chain_benchmark.py`. Stage acceptance requires the documented full stage count, zero unsafe commits, and physical reaction/master-point response tolerances; it never compares an arbitrary global displacement vector. Strict mode no longer limits scour/live stages to a diagnostic one-step probe. If a predecessor fails, the dependent stage is recorded as blocked rather than attempted on tainted state. Current full-chain evidence remains `FAIL (NOT RELEASE-READY)` because strict scour fails at step 2/5.
2. **R2 (Compiled enforcement at execution boundary)**: Fixed in `histra/solver/nonlinear_setup.py`. After virgin/restart/rebuild preparation and prior to any load or tangent assembly, `ModelManager.hysteretic_batch_for(model)` is checked; if `None`, `CompiledBackendRequiredError` is raised, and `inspect_solver_backend(model, [analysis]).require_compiled()` is called. Verified by unit test `test_nonlinear_setup_fails_closed_if_runtime_fails_at_execution_boundary`.
3. **R3 (Article completion claims honesty)**: Clarified in `docs/release/v1-release-checklist.md`, `docs/release/v1-implementation-plan.md`, and `release-evidence/article-models-v1-rc/`. The aggregate explicitly records 14 authored models (7,090/7,277 steps, all with unsafe Work commits, marked `NOT RELEASE-READY`) and incomplete strict probes (coarse 3.1 reaches 1,065/1,065 safe commits, multiring reaches 13/91, and Bridge 3.2 is incomplete). Strict probes are not compared row-by-row with authored C# output; they remain `NOT RELEASE-READY` because no complete, physical curve-qualified path and displacement-matched phase evidence exists.
4. **R4 (Aggregate-only task verification)**: Fixed in `histra/tools/article_models_benchmark.py`. The runner now compares the expected `(run_mode, model_id)` task registry against loaded results in `main()` and `_markdown_report()`. Missing tasks are recorded in the JSON payload, surfaced in the markdown summary, and cause non-zero exit unless `--allow-incomplete`.
5. **R5 (Line search trial update routing)**: Fixed in `histra/solver/line_search.py`. In `_trial` and `RegulaFalsiLineSearch.search`, when `an.csharp_line_search_compatibility` is `True` (authored compatibility mode), C#'s authored `ls.set_x_vector` + `integrator.update` is used. When `False` (production-safe mode), `integrator.update_trial` is used. Verified by unit test `test_line_search_routing_respects_csharp_line_search_compatibility`.
6. **R6 (Packaged wheel/sdist byte parity)**: Rebuilt `dist/histra_python-1.0.0-py3-none-any.whl` and `dist/histra_python-1.0.0.tar.gz` from the current worktree. An automated byte-by-byte check verified all 116 packaged non-test `.py` modules match source exactly. `dist/SHA256SUMS` was regenerated, and a dependency-resolved isolated virtualenv imports the installed wheel, reports `1.0.0`, and completes the compiled public `model-live` Vert smoke with zero unmanaged objects.
7. **R7 (Mixed-runtime reaction projection)**: Fixed in `histra/postprocessing.py` and `histra/solver/hysteretic_runtime.py`. `compute_total_reaction` projects forces from all restrained interfaces, including any unmanaged interfaces in diagnostic mixed mode. Verified by unit test `test_mixed_runtime_reaction_projection_includes_unmanaged_restraints` which confirms non-zero reaction and exact match against the scalar oracle.
8. **R8 (Transactional mutation rollback)**: Fixed in `histra/solver/session.py`. `AnalysisSession.change_interface_materials` creates interface backups before mutating, executes `coverage.require_compiled()`, rolls back interface definitions and clears hysteretic batch if validation fails, and only appends to `self.mutations` and logs upon success. Verified by unit test `test_change_interface_materials_fails_closed_and_rolls_back_if_post_mutation_coverage_fails`.
9. **R9 (Atomic C# restart state restoration)**: Fixed in `histra/solver/restart.py`. All quad, interface, and spring identities, types, and Coulomb $U_{p1}/U_{p2}$ values are validated before writing to `u`, `v`, `ls`, quads, interfaces, or springs. Caller displacement arrays and element states are backed up and rolled back on unexpected errors. Verified by unit test `test_restore_committed_analysis_state_is_atomic`.
10. **R10 (Parabolic compression)**: Fixed in the current worktree. The full
    dense parameter layout has a compression-law discriminator, and the
    generic compiled state machine implements the scalar parabolic stress,
    tangent and rotation-limit branches. The focused regression suite verifies
    history and material-update behavior plus benchmark-scale compiled
    coverage. This is still subject to the Article and platform release gates.
