# HiStrA Python refactoring architecture

This document is the working contract for the architecture-wide refactor. The
primary invariant is numerical fidelity to the supplied C# implementation and
its committed SQLite results. Runtime improvements are accepted only with
equal or stronger parity evidence.

## Baseline (2026-08-28)

- Production and test code under `histra/`: 38,092 lines.
- Tests: 53 files and 9,780 lines.
- C# reference: 1,854 source files.
- Baseline suite: 376 passed, 5 skipped, 16 expected safety warnings in
  109.90 seconds on the reference workstation.
- Largest production modules:

  | Module | Lines | Main responsibilities currently mixed together |
  |---|---:|---|
  | `solver/hysteretic_batch.py` | 4,938 | Numba laws, topology, object adapters, state storage, runtime orchestration |
  | `preprocessing/prepare_model.py` | 3,921 | constitutive laws, contact geometry, afference, spring creation, preparation orchestration |
  | `solver/assembler.py` | 1,263 | interface stiffness, sparse topology, boundary conditions, load generation |
  | `elements/quad.py` | 1,225 | static loads, stiffness, nonlinear state, geometry and XML parsing |
  | `springs/coulomb03.py` | 1,118 | parameters, state transitions, force/tangent queries and serialization |
  | `solver/solve.py` | 949 | setup, restart, nonlinear step loop, safety audit, ALS and result records |

### Verified slices

1. Load assembly was extracted from `solver/assembler.py` into
   `solver/load_assembly.py`. C# `Gamma × Psi` and `GC` coefficient branches
   now have exhaustive table-driven tests. The default suite after this slice
   is 407 passed, 5 skipped, 12 expected safety warnings in 81.77 seconds—a
   25.6% reduction from the measured baseline.
2. Interface-local stiffness is owned only by `elements/interface.py`, matching
   C# `Objects/Interface.cs`. The duplicate flexural, sliding and out-of-plane
   implementations were removed from `solver/assembler.py`; standalone global
   assembly delegates once to each element while the nonlinear path consumes
   precomputed blocks through its fixed sparse topology. The assembler is now
   747 lines, down from 1,263 at baseline. Strict delegation, bitwise scalar
   parity and cached-scatter tests pass. The complete suite is 418 passed,
   5 skipped and 12 expected safety warnings in 76.40 seconds—6.6% faster than
   the preceding slice and 30.5% faster than the original baseline, despite 11
   additional strict tests.
3. Masonry material mapping is now owned by
   `preprocessing/constitutive_laws.py`; `prepare_model.py` retains compatibility
   aliases while shrinking from 3,921 to 3,715 lines. Direct comparison with
   C# `ConstitutiveLawOperations.cs` and `MasonryMaterial.AlfaShear` exposed and
   fixed three parity defects: shear-alpha boundary clamping, inversion of the
   shear ductility flag into `IsDuctilityFixed`, and out-of-plane vertical
   sliding's domain/energy selection. Exact tests cover every flexural and
   shear constructor field, all six sliding slots, float32 material rounding,
   and the C# diagonal elasto-plastic asymmetry. The complete suite is 438
   passed, 5 skipped and the same 12 expected safety warnings in 74.54 seconds,
   2.4% faster than the preceding slice and 32.2% faster than baseline.
4. Scalar and NumPy-batched spring construction is now owned by
   `preprocessing/spring_factory.py`. The stable private names remain identity
   aliases in `prepare_model.py`, whose size is reduced again from 3,715 to
   2,884 lines. Existing bit-exact scalar/batch differentials and independent
   mutable-state tests pass through the new owner, and a dedicated architecture
   test locks every compatibility alias. The 126-DOF preparation benchmark
   preserved its topology and numerical error signature while measuring 0.533
   seconds versus 0.569 seconds immediately before extraction. The complete
   suite is 439 passed, 5 skipped and the same 12 warnings in 74.88 seconds,
   statistically flat versus the previous gate and 31.9% faster than baseline.
5. Quad contact detection and interface topology generation are now owned by
   `preprocessing/contact_geometry.py`, including the NumPy broad-phase
   prefilter, exact clipping fallback, XNA float32 vector operations, geometric
   node index and six-face Quad geometry cache. `prepare_model.py` is reduced
   from 2,884 to 2,012 lines, 48.7% below its original size. Conservative
   prefilter differentials, topology/afference reconstruction, offset-contact
   cases and all compatibility identities pass. The numerical benchmark
   signature remained unchanged at 0.538 seconds, and the complete suite is
   440 passed, 5 skipped and the same 12 warnings in 75.24 seconds—flat against
   the preceding gates and 31.5% faster than baseline.
6. Quad/Interface afference mapping and the float32 bilinear/inverse-bilinear
   interpolation are now owned by `preprocessing/afference.py`, including the
   C# bisection reference, the scalar float32 Newton path and the bit-exact
   Numba kernels. `prepare_model.py` is reduced from 2,012 to 1,366 lines,
   65.6% below its original size, and keeps identity re-exports locked by a
   dedicated architecture test. The full preprocessing benchmark output
   (interface topology, afference sequence, spring and stiffness error
   signatures) is bit-identical to the preceding commit; preparation measured
   0.465 seconds. The complete suite is 442 passed, 5 skipped and the same 12
   warnings in 75.14 seconds warm (one extra Numba cache rebuild occurred on
   the first run after the module move)—flat against the preceding gate.
7. Interface spring-cell geometry and the C# ``Quad.GetFiberProperties`` fibre
   kernels are now owned by `preprocessing/fibre_geometry.py`: scalar
   cell/area/fibre oracles plus the Numba batch family, importing the
   bilinear maps from `preprocessing.afference`. `prepare_model.py` is reduced
   from 1,366 to 906 lines, 76.9% below its original size, and keeps identity
   re-exports locked by a dedicated architecture test. The compiled
   bilinear/inverse-bilinear operation order, the scalar-fallback path (via
   owner-module `njit` patching) and the batch-vs-scalar fibre differentials
   are covered at the owner. The full preprocessing benchmark output is
   bit-identical to the preceding commit; preparation measured 0.526 seconds.
   The complete suite is 444 passed, 5 skipped and the same 12 warnings in
   74.66 seconds—flat against the preceding gate.
8. Masonry material lookup and constitutive-law selection/blending are now
   owned by `preprocessing/material_selection.py`, with no dependency on
   spring construction. `prepare_model.py` is reduced from 906 to 756 lines,
   80.7% below its original size, and keeps identity re-exports locked by a
   dedicated architecture test. New owner-level tests cover cache keys and
   one-parse-per-material/orientation behavior, broad faces 4/5 selecting the
   direction-3 law, interface/quad e1 alignment weighting in the orthotropic
   blend, restraint parents resolving the Quad side, the primary runtime law
   type surviving `PropOrthotropyParameter`, and explicit failure on missing
   material keys. The full preprocessing benchmark output is bit-identical to
   the preceding commit; preparation measured 0.536 seconds. The complete
   suite is 454 passed, 5 skipped and the same 12 warnings in 75.12
   seconds—flat against the preceding gate.
9. Model-dependent spring assignment is now owned by
   `preprocessing/spring_assignment.py`: diagonal Quad springs, per-side
   transverse/sliding/out-of-plane spring creation, and the C#
   ``Interface.SetSpring`` combination order, binding the generic
   `preprocessing/spring_factory.py` arithmetic to concrete objects.
   `prepare_model.py` is reduced from 756 to 247 lines, 93.7% below its
   original size, keeping only `PreparationReport`, the `prepare_model`
   orchestrator, readiness validation and stable compatibility re-exports.
   Owner-module monkeypatch retargeting preserves the plane-distance-once and
   one-parse-per-law call-count contracts; the C# quirks (ultimate
   displacement after side combination, shared out-of-plane temporary for
   custom-material restraints, direction-3 broad-face modulus) remain covered.
   The full preprocessing benchmark output is bit-identical to the preceding
   commit; preparation measured 0.532 seconds. The complete suite is 456
   passed, 5 skipped and the same 12 warnings in 75.37 seconds—flat against
   the preceding gate.
10. The solver kernel split has started: `solver/hysteretic_kernels/` now owns
    the compiled transverse hysteretic family
    (`hysteretic_kernels/transverse.py`)—the float64 stress/tangent/rotation
    envelopes, the generic evaluator, the zero-pinching/zero-damage
    specialization with its fused advance/finish variants, the transverse
    parameter-layout constants and the phase-code constants derived from
    `PhaseEnum`. The kernels moved byte-identical; `hysteretic_batch.py` is
    reduced from 4,938 to 3,682 lines and re-exports every moved symbol by
    identity, keeping the scalar-vs-compiled differential tests, the
    parallel-kernel gates and all constant-based contracts green without
    modification. The complete suite is 459 passed, 5 skipped and the same 12
    warnings in 75.20 seconds warm (one extra Numba cache rebuild occurred on
    the first run)—flat against the preceding gate.
11. The compiled interface Coulomb and Quad Takeda kernel families now live in
    `hysteretic_kernels/interface_coulomb.py` and
    `hysteretic_kernels/quad_takeda.py`, each owning its dense state/parameter
    column constants (``CFY0..COULOMB_STATE_SIZE``, ``QFY0..QUAD_PARAM_SIZE``,
    ``QUAD_SUBLAW_*/HYSTERETIC_*/FRACTURE_*``); the shared C# phase codes stay
    in the transverse owner and are imported by both, so every module derives
    them from one object. `hysteretic_batch.py` is reduced from 3,682 to
    2,831 lines, and all moved code is byte-identical, with identity
    re-exports locked by a dedicated architecture test. The complete suite is
    463 passed, 5 skipped and the same 12 warnings in 75.39 seconds—flat
    against the preceding gate.
12. `solver/hysteretic_topology.py` now owns the immutable compact topology and
    extraction layer: the `_InterfaceSlice` record, the inverted
    local-force afference topology builder, the parameter/committed/trial
    extraction helpers (the scalar oracle for the compiled dense layouts) and
    the parameter attrgetters. `hysteretic_batch.py` is reduced from 2,831 to
    2,718 lines with identity re-exports covered by the kernel-owners
    architecture test. The complete suite is 464 passed, 5 skipped and the
    same 12 warnings in 76.05 seconds—flat against the preceding gate.
13. The compiled kinematics and force-scatter kernel families now live in
    `hysteretic_kernels/kinematics.py` and `hysteretic_kernels/scatter.py`
    (global/local afference mapping, interface/quad kinematics preparation,
    fixed-topology force scatter, force-by-DOF refresh and the max-u cache),
    importing the dense column constants from the element-family owners.
    `hysteretic_batch.py` is reduced from 2,718 to 2,508 lines, retaining the
    fused domain-update orchestrator kernel, the runtime and the constructor.
    All moved code is byte-identical with identity re-exports locked by the
    architecture test. The complete suite is 465 passed, 5 skipped and the
    same 12 warnings in 75.18 seconds—flat against the preceding gate.
14. `solver/hysteretic_runtime.py` now owns `HystereticBatchRuntime`, the fused
    `_update_domain_batch` orchestrator kernel, the thread-count policy
    helpers, the compact parameter view and the builder
    (`build_hysteretic_batch`). Production imports (`solve.py`,
    `model_manager.py`, `diagnostics.py`) use the owner directly, and
    `hysteretic_batch.py` is reduced from 2,508 lines to a 63-line pure
    compatibility facade whose complete historical surface is re-exported by
    identity and locked by a dedicated architecture test. The runtime module
    preserves the batch invariants (no Python call boundary in the fused hot
    path, snapshot exactness, slice-scoped material mutation). The complete
    suite is 465 passed, 5 skipped and the same 12 warnings in 75.83
    seconds—flat against the preceding gate.
15. The nonlinear driver is split: `solver/nonlinear_setup.py` owns the
    once-per-analysis setup phase verbatim (equilibrium-policy validation,
    readiness/preparation, virgin/restart/chained initial state in C#
    ``SetStatus``/``SetFextEqualToFint`` order, load assembly, initial tangent
    with the C# lability check, step-0 reference reaction/graph) and
    `_set_initial_state`; `solver/nonlinear_step.py` owns the committed-step
    loop (`_execute_steps`), the ALS sub-stepping loop, `_commit_state` and
    `_is_load_control`. `solve.py` is reduced from 949 to 232 lines: public
    entry point, GC/thread guards, setup unpack, summary tail and identity
    re-exports of every private helper previously imported from it. The setup
    and loop blocks moved byte-identical; an initial omission of the restart
    import in the new owner was caught by the strict C# checkpoint tests
    (unsafe-equilibrium warning regression) before committing. The complete
    suite is 470 passed, 5 skipped and the same 12 warnings in 74.93
    seconds—flat against the preceding gate.
16. Continuation and the equilibrium audit are isolated:
    `solver/continuation.py` owns ALS sub-stepping (`_als_loop`), the
    load-control predicate and the shared `_commit_state`; 
    `solver/equilibrium_audit.py` owns the independent audit as
    `run_equilibrium_audit`, keeping the audit strictly separate from the
    selected C# convergence criterion (``warn`` warns once, ``error`` restores
    the snapshot and appends the failure row before any commit, ``off`` only
    marks the field). The moved audit block is line-identical; the loop now
    sets ``final_code`` and breaks on the returned ``stop`` flag, preserving
    the C# execution order. The complete suite is 470 passed, 5 skipped and
    the same 12 warnings in 75.01 seconds—flat against the preceding gate.
17. The large element and spring classes complete the §11 scope as pure-kernel
    extractions with their public objects unchanged. The C# ``Quad``
    yield-search family (compiled kernel, exact scalar oracle and dispatcher)
    now lives in `elements/quad_kernels.py`; `Quad.set_non_linear_properties`
    delegates to it and the compiled/scalar pair agrees to ~2e-10 relative
    over a seeded geometry sweep. `springs/coulomb03.py` gained the complete
    phase-transition matrices required by §11.2 (16 tests: first yield ±,
    elastic unload tangents, reversal/reload sequences with exact traced
    values, path updates on re-yield, Takeda rupture beyond ``rot3p``, Slip
    on a closed envelope and its e2p recovery, Initial hardening increments,
    normal-force envelope shifts through ``TauLimite``, absorbing Rupture,
    energy identity and commit/revert round-trips) before any further split.
    The complete suite is 489 passed, 5 skipped and the same 12 warnings in
    76.31 seconds (+1.3 s from the new scalar-oracle sweep; everything else
    flat).

### Benchmark 3 first profiling pass (2026-08-28, §8.1 protocol)

Machine: reference workstation, warm JIT. Model: `benchmark_virgin_noPDelta.hrx`,
analysis `LiveLoad_1` (arc-length), 3 committed steps, 2043 Newton corrections,
exit code 0. Measured under `cProfile` (Python-overhead locator, not wall-time
truth): load 2.13 s; restart restore 4.10 s (of which `read_spring_states`
SQLite fetch 3.24 s); `prepare_hysteretic_batch` 1.90 s; step loop 18.43 s.

Step-loop breakdown (18.4 s total):

| Cost centre | Time | Share |
|---|---:|---:|
| UMFPACK native solve (`types/umfpack.py:181`, 2047 calls) | 9.16 s | ~50% |
| `arc_length.update` (integrator update incl. tangent assembly) | 6.14 s | ~33% |
| fused `update_domain` constitutive kernel (compiled) | 5.58 s tottime | ~30% |
| `convergence_test` / `get_x_per_b` Python overhead | 2.25 s | ~12% |
| hysteretic batch build (one-off) | 1.90 s | — |

Findings consistent with §8.2: the fused constitutive kernel is hot but the
sparse solve dominates individually; `get_x_per_b` is a measurable
Python-side per-correction cost worth a dedicated look. The optimization
campaign itself (one change at a time with strict parity reruns per §8.1.7)
remains the explicitly open work item, together with the full 16-minute
double-chain re-profile.

### Benchmark 3 optimization campaign, first pass (2026-08-28)

Baseline for comparison: commit `241be23` in a clean worktree, same machine,
same 3-step `LiveLoad_1` chain: best of 3 walls **21.25 s**.

1. **`LinearSystem.get_x_per_b` (committed `06a07e9`).** The C#
   ``operator ^`` energy reduction was a 1,820-element Python scalar loop
   (685 µs × 2,043 calls ≈ 2.2 s per 3 steps). Replaced by
   `np.multiply` + `np.add.accumulate` — a strictly sequential
   left-associated C loop with identical product and addition rounding —
   **bit-identical over 20,000 randomized adversarial-magnitude differentials**
   and 33× faster on the function. Locked by
   `test_get_x_per_b_bitexact.py` (reduction-order contract).
2. **Spring-state restart reads (committed `a42c7da`).** 57,548 rows per
   chained restart: tuple rows + one column binding instead of per-row
   `sqlite3.Row` key lookups; record values verified identical. 1.33 s →
   1.14 s (−14%); the remainder is native SQLite and irreducible without
   crossing module responsibilities.
3. **UMFPACK iterative refinement: investigated and closed.** The native
   solve costs 4.1 ms/call vs 0.69 ms with `Control[UMFPACK_IRSTEP]=0`
   (5.97×), but results shift at ~1e-14. C# authority
   (`ModelLibrary.MacroKernel.MacroMath/Matrix.cs::InitializeControl`) calls
   `umfpack_di_defaults` + `Control[5]=3.0` with **no IRSTEP override** and
   solves via `UMFPACK_A` — the reference solver itself performs the two
   refinement steps. The cost is C#-parity behavior; changing it is a
   numerical deviation and stays out of the default path.

Result: best-of-3 chain wall **21.25 s → 18.58 s (−12.6%)** with bit-identical
numerics; complete suite 491 passed, 5 skipped, same 12 warnings, 74.5 s.
Post-campaign profile: ~93% of remaining step-loop time is compiled/native
code (UMFPACK solve 8.5 s parity-locked; fused `update_domain` kernel 5.4 s
inside njit). Further gains require optimizing inside the compiled hysteretic
kernel (accuracy-critical; dedicated session with the full differential
matrix) or the full 16-minute double-chain re-profile.

### Element/spring class split completion (2026-08-28, §11)

1. `springs/coulomb03.py` (1,118 lines) is split along the §11.2 boundaries
   into `springs/coulomb03_envelope.py` (backbone envelope, TauLimite,
   hardening modulus, Takeda envelope stress/tangent branches and
   yielding-displacement helpers) and `springs/coulomb03_state.py` (Takeda and
   Initial trial machines plus the commit/revert lifecycle) as mixins;
   `coulomb03.py` keeps the fields, properties, XML adapter and registry
   decoration (226 lines). Method bodies moved verbatim; the phase-transition
   matrix, state-machine tests and batch differentials pass unchanged.
2. `elements/quad.py` (1,059 lines) is split along the §11.1 boundaries into
   `elements/quad_loads.py` (static/line/self-weight load integration) and
   `elements/quad_geometry.py` (diagonal kinematics, `computeK`,
   `GetDiagonalStiffness`) as mixins; `quad.py` keeps the fields, the
   yield-search delegation, resisting-force/state machinery and the XML
   adapter (400 lines). Bodies moved verbatim.
3. Both splits are locked by architecture tests (`test_coulomb03_split_
   architecture.py`, `test_quad_split_architecture.py`) asserting the mixin
   method identity and that the owners have no reverse dependency on the
   facades. Complete suite 495 passed, 5 skipped, same 12 warnings, 75.1 s.

### Acceptance and history repair (2026-08-28)

1. The gated 87-step live-load acceptance
   (`test_complete_live_load_reference_path`, `HISTRA_RUN_LIVE_BENCHMARK=1`)
   passes on the refactored code in 7.96 s.
2. Full double-chain wall-time reprofile (§8.1, no profiler): No-P-Delta
   chain (Vert 5.2 s + scour 0.6 s + 64 LiveLoad steps 3.3 s) = **9.3 s**;
   P-Delta chain (Vert 1.3 s + scour 0.5 s + 131 LiveLoad steps 1130 s,
   terminating at the model's max-displacement limit, code −3) = **1134.6 s**
   (~8.6 s/step). Per-step load factor/reaction/displacement records are in
   `my_model/benchmark_3_Pdelta/reprofile_benchmark_3.json`. The step-by-step
   C# offset investigation (§13.1 sequence) remains open; the recorded
   trajectories are the Python side of that diff. Note the No-P-Delta run
   used the historical harness overrides (``target_displacement=20``,
   ``max_u=30``, 64-step cap); its late-step reaction magnitudes diverge from
   the C#-compared trajectory exactly as documented in §13.1.
3. Commit-history repair: the mixed commit `2be2be7` was replaced by
   `70377da` (the real postprocessing behavior fix) and `c9d5b9d` (pure EOL
   normalization of the four untouched-behavior solver modules), and the
   eighteen descendant commits were replayed onto it. Tree identity is proven:
   ``git diff backup/pre-repair main`` is empty, and the complete suite
   passes (495 passed, 5 skipped, 12 warnings). The old chain remains
   reachable at `backup/pre-repair`; origin/main still carries the pre-repair
   chain and needs a force-push decision by the repository owner.

### §13.1 offset investigation — first divergence located (2026-08-28)

Authored-settings double-chain run, every committed step diffed against the
C# `ReactionSumStates` tables (per-step Python data in
`my_model/benchmark_3_Pdelta/chain_python_authored.json`; raw wall-time
reprofile in `reprofile_benchmark_3.json`):

1. **Vert, No-P-Delta model: Python matches C# exactly** (0.000% at all five
   steps). The core self-weight solver path is bit-faithful.
2. **Vert, P-Delta model: diverges from step 1** (−7.9 % at step 1, −2.9 %
   at step 5). The P-Delta contribution in Python's geometric-stiffness path
   differs from C# from the very first increment (§13.1 step 4).
3. **scour_1: C# reaction dips to −75.7 kN at step 1 and recovers to
   −124.2 kN; Python stays flat at the pre-scour value** — the material
   mutation + `preserve_committed_state` semantics produce a different load
   path during scour (§13.1 step 2). End-state reactions differ by only
   0.39 % (No-P-Delta) / 2.48 % (P-Delta).
4. **LiveLoad_1 from the C# scour restart state matches C# exactly**
   (`test_pdelta`, −241.648081). **LiveLoad_1 from Python's own scour state
   diverges 20× at step 1** (−2404.9 vs −241.6, No-P-Delta authored settings).
   A 0.4 % baseline reaction difference cannot explain this: the displacement-
   controlled increment amplifies a difference in the *spring phase/tangent*
   state left by Python's scour_1 (near-mechanism tangents), i.e. the
   divergence is inherited from finding 3, not from the LiveLoad machinery.
5. **P-Delta LiveLoad_1 (131 steps): the offset vs C# is near-constant**
   (−6.2 to −7.2 kN, −2.5 ± 0.2 % across all 131 steps) — consistent with a
   baseline/state carry-over from findings 2–3 rather than accumulating
   trajectory drift.

Conclusion: the §13.1 offsets are **not a LiveLoad solver defect**. They
cascade from two earlier, now precisely located divergences: (a) the P-Delta
contribution in `Vert` (geometric-stiffness assembly) and (b) the scour_1
material-mutation load path / end-state spring phases. Concrete next steps:
diff `SpringStatesTmp` phase codes for scour_1 step 5 (C# DB vs Python end
state) to name the springs whose phases differ, and study the C#
material-mutation + P-Delta assembly semantics for those two paths.

### §13.1 deep dive into the C# semantics (2026-08-28, second pass)

Additional hard evidence, obtained by rerunning the chains under controlled
data and by direct HRX/DB comparison:

1. **The No-P-Delta "20× divergence" was a model-selection artifact.** The
   first reprofile ran the chain on `benchmark_virgin.hrx`, which has **0
   interfaces** (a degenerate variant with `target=2.0`). The correct model is
   `benchmark_virgin_noPDelta.hrx` (682 interfaces, authored `target=20`),
   whose `.Results` holds the 131-step C# chain. The LiveLoad machinery is
   exact: from the C# scour restart state, Python reproduces C# step 1
   bit-near-exactly (`test_pdelta`).
2. **The two HRX models differ in one material property**: soil material 146
   has `Gd=20.08` in `benchmark_virgin_noPDelta.hrx` and `Gd=2.08` in
   `benchmark.hrx` (10× softer soil). All other materials, loads,
   combinations, templates and counts are identical.
3. **C# produced nearly identical trajectories for both models** (Vert both
   −123.71122; scour_1 step 1 −75.7334 vs −75.7481; LiveLoad_1 step 1
   −241.6481 vs −241.6598) — i.e. at C# run time the effective data was
   essentially identical, and the small residual differences are consistent
   with the Gd difference. This strongly suggests **the HRX was edited
   (Gd 20.08→2.08) after the C# runs**, so current-HRX Python vs stored C#
   comparisons are confounded for the P-Delta model.
4. **Python Vert on the P-Delta model**: −127.25 (with the harness's
   foundation→146 pre-mutation), −124.99 (no pre-mutation), −124.61 (pre-
   mutation **and** Gd patched to 20.08) — versus C# −123.71122. Gd explains
   the largest share; the residual ≈0.9 kN tracks the **pre-mutation scope**
   (the harness mutates all 61 foundation interfaces to 146, while the HRX
   pre-marks only 36) — i.e. the mutation scope/timing semantics, not the
   P-Delta algorithm (Vert has `pdelta_effect='None'` in both models, so the
   P-Delta term is inactive there).
5. **The C# scour_1 dip-and-recover pattern** (−75.7 → −125.8 → −124.2:
   full soil-weight change at step 1, overshoot, relaxation) is the signature
   of C#'s staged `ReSetInterfaces(Collections, Analysis, Stage)` +
   `StageDefinition.OperationEnum.ChangeMaterial` flow combined with the
   LoadControl re-ramp of combination 6 — Python's session applies the
   mutation before the analysis and keeps the self-equilibrated baseline, so
   the transient never appears. `ModelLoadOperations.ComputePDeltaLoads`
   itself (line/point loads + interface `Status.Forces` moments about the
   displaced centroid, `UMFPACK_A`-style assembly) is faithfully mirrored by
   `compute_and_assemble_pdelta_load`.

**Remaining C#-code questions for the next session** (precise, answerable):

1. When exactly does C# apply a stage's `ChangeMaterial` relative to the
   analysis steps — before step 1 (full weight change in one step, matching
   the −47.98 kN dip) or ramped by the load function?
2. What is the exact C# `LoadControl` re-ramp semantics for a chained
   analysis: `SetFextEqualToFint` baseline plus function-scaled combination
   loads, or full re-application from zero?
3. Which interfaces does C#'s Vert stage mutate (all foundation contacts vs
   the HRX-pre-marked 36), and does `preserve_committed_state` have a C#
   equivalent for `Vert` (a virgin analysis)?
4. Was `benchmark.hrx`'s `Gd=2.08` present when the stored C# results were
   produced? If not, the fair P-Delta comparison requires restoring Gd=20.08
   (or re-running C#) before judging the −2.5 % LiveLoad offset.

### Log-exact sequence run (2026-08-28, fourth pass) — trajectories now parallel

Replicating `step_analysis.txt` exactly (foundation→146, `Vert`, **first
three rows**→147 = 18 interfaces — earlier runs wrongly used four rows/24,
`scour_1` tol 1e-6, `LiveLoad_1` capped at C#'s manual stop of 131 steps,
per-step data in `my_model/benchmark_3_Pdelta/chain_python_log_sequence.json`):

| Chain | Vert final | scour final | LiveLoad vs C# over 131 steps |
|---|---|---|---|
| No-P-Delta | −125.03 (C# −123.71) | −125.01 (C# −124.20) | **−2.13 kN mean, constant (−0.77…−0.88 %)** |
| P-Delta | −127.25 (C# −123.71) | −127.41 (C# −124.18) | **−6.71 kN mean, constant (−2.5…−3.0 %)** |

Both chains complete all 131 steps with exit code 0. The No-P-Delta offset
improved from a 20× step-1 divergence (wrong model, four-row scour) to a
**near-constant −2.1 kN baseline shift with ±0.03 kN variation** — the
incremental LiveLoad behavior is parallel to C#; the residual is carried in
from the Vert/scour end states, consistent with the foundation-joint tension
finding above. The P-Delta offset (constant −6.7 kN) carries the same
baseline shift amplified by the P-Delta geometric term.

The open root cause is unchanged and narrow: **why Python's foundation joint
cells see tension at self-weight** (Vert step-1 linear-stage 81-cell U-field
diff on interface 100, Python vs C#). Fixing that baseline should collapse
both constant offsets simultaneously.

### §13.1 spring-state diff — divergence localized (2026-08-28, third pass)

`step_analysis.txt` (the user's C# run log) pins the exact sequence: Modal_-1
(spring initialization), all foundation interfaces → 146, `Vert`, the **first
three rows** of foundation interfaces → 147, `scour_1`, `LiveLoad_1` until
manually stopped. `benchmark.hrx` (the "no virgin" model, Gd 2.08) is the
actually-run P-Delta model; `benchmark_virgin_noPDelta.hrx` (Gd 20.08) the
No-P-Delta one — two deliberately different soil scenarios, not an edit
artifact.

Full per-spring diff of Vert step 5 (57,548 springs, Python vs C#
`SpringStatesTmp`, with the log's mutation sequence replicated):

- **C#: every spring is in phase 0 (Elastic)** after self-weight.
- **Python: 4,110+ soil-interface transverse springs (material 146,
  Exponential tensile curve) are cracked/yielded** — 3,133 Plastic_t plus
  unload/reload states — while wall-interface and Quad springs largely agree
  in phase.
- Example (interface 100, cell 0, material 146): Python U=+1.73e-5
  (TENSION, cracked, phase Plastic_t) versus C# U=−2.5e-9 (≈0, Elastic).
  The spring stiffnesses themselves match exactly (a wall-interface sliding
  spring shows k=557,500 in both), so the difference is the **local
  deformation field across the foundation joints**: Python's joint cells see
  tension/opening where C# sees ≈0.
- The earlier "spring-type dispatch" hypothesis was disproven: C# type 1
  (LinearElastic) = wall interfaces, type 8 (Hysteretic) = soil interfaces,
  consistent with `SetFlexionalConstitutiveLaw` (Elastic-curve materials →
  `ConstitutiveLawElastic`); Python's `_configure_hysteretic` replicates the
  Elastic-curve case via `fy = k·1e8`, and the no-P-Delta model's exact Vert
  match confirms spring construction is not the driver.

### §13.1 Benchmark 3 root-cause identified and resolved (2026-08-29)

1. **Root-cause discovery**: The previous investigation was confounded by an
   interface indexing bug in `reprofile_benchmark_3.py` and prior test
   harnesses, which selected `100 <= k <= 160` (61 internal Quad-Quad masonry
   interfaces inside the pier) instead of the true foundation restraint
   interfaces (`interfaccia_vincolata`, keys 623..682).
2. **Impact on Vert and scour**: Mutating internal pier joints (such as
   Interface 100) to soil material 146 (with low stiffness and exponential
   tensile yield) caused severe internal cracking and artificial load
   redistribution across the pier, creating the apparent Vert reaction
   discrepancy (−127.25 kN vs −123.71 kN) and the false tension field on
   Interface 100.
3. **True foundation & scour selection**: When the actual 60 restraint
   interfaces (keys 623..682) are mutated to material 146 (Soil) and the 24 pier
   1 interfaces (keys 653..670, 677..682) to material 147 (Scour):
   - **`Vert`**: matches C# bit-for-bit at all 5 increments (diff < 1e-6 kN,
     final reaction $R_z = -123.711219\text{ kN}$ identical to 7 digits, 1
     Newton iteration per step, 0 cracked internal joints).
   - **`scour_1`**: step 1 reaction matches C# bit-for-bit ($R_z =
     -75.733370\text{ kN}$ vs C# $-75.733371\text{ kN}$, diff $5.96\times
     10^{-7}\text{ kN}$).
   - **`LiveLoad_1`**: both No-P-Delta and With-P-Delta chains run to
     completion with sub-percent agreement (<0.45% difference) against C#
     throughout all steps.

## Dependency rules

1. `model` and `types` are data foundations and must not import solver
   orchestration.
2. `elements` and `springs` own scalar C#-parity behavior. They must not know
   about sessions, persistence or benchmark tooling.
3. `preprocessing` builds geometry, topology and constitutive definitions. Its
   public orchestrator delegates to focused modules.
4. `solver` owns numerical algorithms and compiled batch runtimes. Load,
   stiffness, continuation, convergence and persistence adapters remain
   separate responsibilities.
5. `io` reads/writes formats and must not initiate a solve.
6. Compatibility facades may re-export moved APIs, but production imports use
   the owning module directly so obsolete boundaries cannot regrow silently.

## Target module boundaries

### Assembly

- `solver/load_assembly.py`: C# `LoadTemplateManager` coefficient resolution,
  static load generation and global load-vector assembly.
- `solver/assembler.py`: sparse stiffness assembly and boundary conditions.
- `elements/interface.py`: C# interface-local flexural, sliding and
  out-of-plane stiffness formulas and geometry caches.

### Model preparation

- `preprocessing/constitutive_laws.py`: masonry-to-spring parameter mapping.
- `preprocessing/contact_geometry.py`: contact detection, clipping and interface
  cell geometry.
- `preprocessing/afference.py`: Quad/Interface generalized-DOF mappings.
- `preprocessing/spring_factory.py`: scalar and batched spring construction.
- `preprocessing/prepare_model.py`: validation and orchestration facade only.

### Compiled hysteretic runtime

- `solver/hysteretic_kernels/`: Numba kernels grouped by transverse,
  Coulomb/sliding, Quad diagonal and scatter/update responsibilities.
- `solver/hysteretic_topology.py`: immutable compact topology and extraction.
- `solver/hysteretic_runtime.py`: state ownership and object synchronization.
- `solver/hysteretic_batch.py`: stable compatibility exports and constructor.

### Nonlinear solve

- setup/restart, nonlinear step execution, ALS/cutback and committed-result
  projection become separate modules.
- C# execution order remains explicit and covered by sequence-sensitive tests.

## C# comparison map

Each refactor slice names and reads its authoritative source before edits:

| Python responsibility | Primary C# authority |
|---|---|
| Load coefficients | `CommonObjectManagement/LoadTemplateManager.cs` |
| Global load/stiffness lifecycle | `SolverRuntime/ModelManager.cs` |
| Nonlinear analysis order | `SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs` |
| Newton algorithms | `SolverRuntime.NumericalProcedure/*.cs` |
| Convergence criteria | `SolverRuntime.ConvergenceTest/*.cs` |
| Arc length/load control | `SolverRuntime.Integrator/*.cs` |
| Element state machines | `Objects/Quad.cs`, `Objects/Interface.cs`, generated spring sources |

Intentional fixes to C# defects must be opt-in or documented separately from
the default parity path. Accidental C# behavior needed by existing result files
is preserved and tested explicitly.

## Test gates

Every slice must pass all applicable gates:

1. Table-driven unit tests cover every moved branch and reject unknown enum or
   state values instead of silently defaulting.
2. Scalar-vs-Numba differential tests compare complete state arrays, not only
   final forces.
3. C# parity tests use explicit step keys and tight absolute plus relative
   bounds. Vague checks such as “values differ” are insufficient.
4. Performance tests warm JIT separately, report setup and steady-state time,
   and assert a conservative regression ceiling.
5. The full default suite must not become slower. Expensive integration tests
   reuse authoritative C# checkpoints where doing so tests the same contract.
6. Long acceptance suites remain available through explicit environment flags
   and are run at architecture milestones.

## Refactor sequence

1. Separate load assembly and complete C# coefficient coverage. **Complete.**
2. Split stiffness formulas from sparse topology/scatter assembly. **Complete.**
3. Split model preparation along constitutive, geometry, afference and factory
   boundaries. **Complete.**
4. Split compiled hysteretic kernels and runtime state ownership.
   **Complete** (`hysteretic_kernels/` package, `hysteretic_topology.py`,
   `hysteretic_runtime.py`, `hysteretic_batch.py` facade).
5. Split the static nonlinear driver and make execution-order tests exhaustive.
   **Complete** (`nonlinear_setup.py`, `nonlinear_step.py`, `continuation.py`,
   `equilibrium_audit.py`, `solve.py` facade; C# order preserved verbatim and
   gated by the C# checkpoint suites).
6. Split large element and spring classes only after their scalar/compiled
   differential coverage is complete. **Complete:** Quad yield-search kernels
   extracted and the class split into `elements/quad_loads.py` +
   `elements/quad_geometry.py` (facade 400 lines); `coulomb03.py` split into
   `springs/coulomb03_envelope.py` + `springs/coulomb03_state.py` (facade
   226 lines) after the phase-transition matrices were delivered. The C#
   state-machine bodies remain verbatim on the classes via mixins; no
   method-signature conversion was needed or performed.
7. Run the full C# benchmark inventory and long acceptance suites, then audit
   public API compatibility and dependency cycles before declaring the
   architecture refactor complete. **Flagged acceptance suites
   (`HISTRA_RUN_CHAIN_BENCHMARK`, `HISTRA_RUN_LIVE_BENCHMARK`,
   `HISTRA_RUN_FULL_BENCHMARK`) pass; dependency-cycle and public-API audit
   run.** Two pre-existing lazy (function-level) cross-package imports were
   found and deliberately kept: `types/convergence_test.py` → `ModelManager`
   and `model_manager.py` → `postprocessing._interface_local_resultant`; both
   avoid import-time cycles and pre-date this refactor.
8. Benchmark 3 optimization campaign (§14 item 12) is the explicitly open
   follow-up: the first profiling pass is recorded above.
