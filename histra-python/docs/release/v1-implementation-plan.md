# HiStrA Python V1.0.0 implementation and validation plan

Status: **active and blocked for release**  
Last consolidated: 2026-09-06  
Working branch: `codex/v1-release`  
Latest focused fix: `064f7b1` (`Fix ArcLength segment tangent parity`)

This is the authoritative plan for completing, validating, packaging, and
releasing HiStrA Python V1.0.0. It consolidates the original release scope,
the Article-model requirements, the C# audit, solver-strategy qualification,
performance work, and the findings from the supplied source data and C#
results. A completed run is not automatically a passed gate: every claim below
must be supported by the stated acceptance evidence.

Checkboxes mean acceptance has been demonstrated, not merely that code exists.
The [independent review](v1-independent-review.md) is still in progress and
records contradictions in current completion claims. Its open findings are
mandatory remediation work; this consolidation does not approve a release.

## 1. V1 product boundary

V1 is a private, production-ready masonry Quad/Interface solver supporting:

- locked HRX loading and unlocked masonry preprocessing;
- six-face Quad contacts and afference;
- self-weight, direct loads, load combinations, and analysis dependencies;
- committed-state restart and transfer between analyses;
- interface material changes between committed analyses;
- force- and displacement-controlled static nonlinear analysis;
- LoadControl, ArcLength, and ArcLengthLinear;
- standard and modified Newton with the supported line searches;
- ForceMoment, DispRotation, and Work compatibility criteria;
- P-Delta `EachStep` and `EachIteration`;
- modal mass, eigensolution, participation, effective mass, and projected mode
  shapes;
- the masonry constitutive and shear families declared supported in the V1
  feature matrix.

Dynamic nonlinear analysis, response-spectrum contributions, Frame, Slab,
Link, Joint, Vertex, InterfaceMF, NodeBC, concrete, steel, and fiber systems
are outside V1. Their presence must produce a precise capability error before
solving, never a partial result or a substituted law.

## 2. Non-negotiable execution contracts

### 2.1 Accuracy and safety

- C# is the compatibility authority unless a C# defect is explicitly isolated
  and documented.
- Production capacity results require ForceMoment convergence and an
  independent active-DOF equilibrium audit.
- No unsafe state may be committed in production-safe mode.
- Unknown enum values and unsupported constitutive paths fail before solving.
- Tolerances must not be relaxed to explain backend or branch differences.
- Floating-point operation order and float32 conversions are preserved where
  they affect constitutive branch selection.

### 2.2 Compatibility mode versus production-safe mode

`authored` mode reproduces the HRX/C# numerical strategy. It may use Work or
DispRotation and may therefore reproduce a C# row that fails the independent
residual audit. Such rows are compatibility evidence only.

`strict` mode uses ForceMoment plus the independent equilibrium audit. An
unsafe candidate is rejected without commit. Only strict results can support
engineering capacity or the production release gate.

### 2.3 Compiled-only production rule

Production nonlinear execution must use NumPy/Numba kernels for repeated
element and spring work and SciPy's compiled sparse solver. Python may
orchestrate analyses, but no per-interface, per-Quad, per-spring, per-DOF, or
reduction loop may remain on the production hot path.

The scalar implementations remain only as:

- exact C# parity oracles in differential tests;
- explicitly requested diagnostic execution outside the production contract.

The current optional-acceleration behavior is not release-ready. V1 must:

1. make compiled execution the default and mandatory public policy;
2. fail preflight if Numba is unavailable or kernel construction fails;
3. fail preflight if any supported V1 Interface, Quad, transverse spring,
   sliding spring, or out-of-plane spring is unmanaged;
4. prevent environment variables from silently selecting scalar execution for
   a production session;
5. revalidate compiled coverage after initialization, restart, every runtime
   rebuild, and every interface-material mutation, at the execution boundary;
6. record kernel/backend identity, Numba thread count, managed counts, rejection
   reasons, warm/cold state, and sparse-solver backend in benchmark evidence.

Required public design (implementation exists; lifecycle enforcement remains
under review):

- add a structured `SolverBackendCoverageReport`;
- add `inspect_solver_backend(model, analysis_names)`;
- add `performance_policy="compiled" | "diagnostic-scalar"`, defaulting to
  `"compiled"`, on `AnalysisSession` and `run_python_solver_job`;
- keep `diagnostic-scalar` conspicuous and exclude it from production release
  evidence;
- raise a dedicated preflight exception for missing kernels or unmanaged V1
  objects rather than falling back.

## 3. Current evidence snapshot

### 3.1 Test and package status

- Original release baseline: `496 passed, 5 skipped, 12 warnings`.
- Latest verified Linux Python 3.12 suite:
  `614 passed, 6 skipped, 0 warnings in 52.60s`. Legacy authored-compatibility tests explicitly disable the audit
  they intentionally do not test; warning-specific tests capture and assert
  the advisory/audit warning instead of leaking it into suite output.
- Warning-count changes are reconciled through the policy requested by each
  test; zero suite warnings are not permission to publish unsafe results.
- Wheel and sdist build, `twine check`, isolated wheel installation, public API,
  version `1.0.0`, and SHA-256 generation have passed previously.
- Linux Python 3.13/3.14 remain unexecuted release gates. Windows validation
  is explicitly deferred until after V1 and is not a V1 supported-platform
  claim.

### 3.2 Article source evidence

The supplied `Original_article_data.csv` and `Graphs_HISTRA.ipynb` are
integrated under `release-evidence/article-source-data/`. Harness revision 4
validates the original series used by Figures 9, 12, 13, 15, 17, 20, 22, 24,
and 25 and anchors Table 1 capacities to the supplied paper. Input hashes and
the exact notebook-cell/series mapping are preserved in compact evidence.

### 3.3 Article model status

The current [RC aggregate](../../release-evidence/article-models-v1-rc/article_models_csharp_verification.md)
contains 14 authored entries and only three strict entries. Earlier attempts
are not a substitute for complete, current evidence.

- Authored coverage is 7,090/7,277 rows: Bridge_1 stops at 112/297 and
  Bridge_5.1_coarse at 1,583/1,585. All 14 entries are NOT RELEASE-READY.
- No Article model currently has a complete strict release pass.
- Current strict entries are 3.1 coarse 1,065/1,065, 3.1 multiring 13/91,
  and 3.2 49/338. All report zero unsafe commits, but all fail acceptance:
  coarse has 180.628 kN reaction error and 33.0172 mm point error, and the
  other two lack full range coverage.
- No raw Article assets may be deleted while this gate is open.

### 3.4 Bridge 3.1 Coarse resolved compatibility defect

Python previously rebuilt the tangent unconditionally when ArcLength advanced
between load-function segments. C# performs that rebuild only for Modified
methods. The model uses `StandardInitialInterpolatedLineSearch`, so Python
selected the wrong branch at step 42.

After matching the C# condition, the authored run completes 1,065/1,065 rows.
Peak-load error is 0.0213%, normalized curve RMSE 0.0708%, area error 0.0295%,
initial-stiffness error 0.00221%, and peak-displacement error 0.02795 mm. All
191 rupture identities agree. Reversible unload/reload labels drift on the
unsafe Work path. All authored commits fail the independent residual audit, so
the strict gate remains open. The complete diagnosis is in
`release-evidence/article-models/BRIDGE_3.1_COARSE_DIFFERENCE_ROOT_CAUSE.md`.

### 3.5 Bridge 3.2 and interface-material changes

`Bridge_3.2.hrx` contains 1,002 interfaces: 976 use the default material key
and 26 use material 142. Its `StageDefinitions` and `StageItems` are empty.
It therefore validates a mixed-material/ring-separation model, not a material
mutation between analyses.

The existing authored Bridge 3.2 result covers 338/338 C# rows. Peak-load error
is 0.0241%, normalized curve RMSE 0.0531%, maximum reaction error 0.893 kN, and
maximum model-point error 0.0131 mm. All 338 authored steps fail the independent
residual audit, and its terminal spring-phase distribution is not exact. The
current strict diagnostic covers only 49/338 rows.
Bridge 3.2 is checked but not closed.

The actual interface-change benchmark is the separate chain:

```text
Vert -> change four interfaces -> scour_1 -> LiveLoad_1
```

Its opt-in full C# comparison passes the expected 5 + 5 + 38 committed-step
path and displacement tolerances. The change rebuilds 48 springs on four
interfaces while preserving committed history. The dense runtime remains
active through the mutation and scour analysis with zero unmanaged Interfaces
and zero unmanaged Quads. This authored chain still produces unsafe Work
commits; it also requires a full strict and performance qualification.

The newer `interface-chain-v1-rc` runner reports PASS for a strict 5/1/0-step
chain with nonconverged live loading. That is a false gate pass, not release
evidence (review R1). Correct its acceptance logic and rerun the complete chain;
missing reference data, failed terminal conditions, and excessive response
errors must fail qualification.

### 3.6 Current compiled coverage on the two supplied Article models

The present Numba runtime can manage the complete nonlinear domain of both
models when explicitly constructed:

| Model | Managed transverse | Managed interface sliding | Managed Quads | Unmanaged Interfaces/Quads |
|---|---:|---:|---:|---:|
| Bridge 3.1 Coarse | 5,720 | 705 | 126 | 0 / 0 |
| Bridge 3.2 | 24,128 | 3,006 | 518 | 0 / 0 |

This demonstrates kernel coverage for these inputs. It does not satisfy the
compiled-only release rule because the public solver still catches acceleration
errors and permits a scalar fallback, and other registered models have not yet
received a zero-unmanaged release report.

### 3.7 Current solver-strategy evidence

Only three initial matrices exist; the coarse matrices predate the required
external-reference schema and are diagnostic only:

| Scenario | Candidates | Qualifiers | Limitation |
|---|---:|---:|---|
| Coarse gravity | 7 | 0 | One model, one repetition, no accepted reference |
| Coarse live load | 6 | 0 | First five live-load increments; no accepted reference |
| P-Delta gravity | 7 | 0 | Three repeats; safe force path but 3.10 relative master-point displacement error vs C# |

The public advisor currently emits three rule families:

- `HISTRA-STRATEGY-001`: Work/DispRotation may pass with an unsafe residual;
- `HISTRA-STRATEGY-002`: Modified ArcLength requires model-specific checking;
- `HISTRA-STRATEGY-003`: a non-Bisection strict ArcLength strategy is not the
  currently measured coarse-model starting point.

These warnings are useful but not comprehensive. They do not prove that every
supported numerical strategy has been measured or that the recommendation is
valid for Bridge 3.2, a fine mesh, a material-change chain, P-Delta live load,
or a complete near-collapse branch. The P-Delta gravity physical-response
comparison now also isolates a master-point displacement parity defect that
must be resolved before any P-Delta strategy is recommended.

## 4. Mandatory implementation gates

### Gate A — enforce the compiled production backend

- [x] Add the public backend coverage report and compiled-only policy.
- [x] Make missing Numba or failed kernel compilation an execution-boundary
      error, including rebuilds after successful preflight (review R2).
- [ ] Make any unmanaged supported V1 object an execution-boundary error.
- [ ] Remove silent full-runtime and scalar hot-path fallbacks from production
      mode; retain them only behind explicit diagnostic policy.
- [ ] Convert remaining repeated Python loops in tangent construction,
      stiffness scatter fallback, reactions, energy, maximum-displacement,
      line-search reductions, output projection, and material-change refresh to
      NumPy/Numba or prove they are outside the per-step hot path.
- [x] Precompute analysis/combination-specific Quad line-load vectors and
      evaluate/scatter their P-Delta moments in a Numba kernel. The compiled
      path preserves scalar load/item/scatter order and is covered by the
      P-Delta compiled/scalar differential tests.
- [ ] Verify every compiled kernel against its scalar C# oracle across complete
      phase transitions, commit, revert, restart, and cyclic reversal.
- [ ] Require zero unmanaged Interfaces and Quads before the first step and
      after every material change.
- [ ] Add CI tests proving public APIs fail closed when compiled execution is
      unavailable or incomplete.

Acceptance: every V1 benchmark records an active compiled runtime, zero
unmanaged V1 objects, no scalar hot-path calls, and unchanged accepted response.

### Gate B — close the Article suite

- [ ] Consolidate duplicate scripts into one tracked canonical harness and an
      authoritative registry for all 14 models/variants, specimens and figures.
- [ ] Distinguish sparse stored C# rows from missing solver steps; compare the
      correct master point/direction and subtract predecessor reactions and
      displacements for live-load curves.
- [ ] Verify dependencies, stored analysis states and terminal conditions.
- [x] Require every requested model/mode pair in aggregation; fail on missing,
      stale or duplicate evidence, including `--aggregate-only` (review R4).
- [ ] Record input and source-code hashes (including dirty changes), harness
      revision, configuration, package/platform/backend versions, runtime,
      peak metrics and checkpoint provenance. Invalidate incompatible resumes.
- [ ] Run a complete clean authored and strict aggregate after all relevant fixes.
- [ ] Execute every documented dependency chain to its terminal condition.
- [ ] Cover every stored C# reaction, model-point, and spring checkpoint row.
- [ ] Investigate from the earliest divergent stage: load vector, committed
      global state, stable spring identity/phase, then Newton iteration.
- [ ] Close Bridge 3.2 strict gravity and its subsequent live-load range.
- [ ] Compare rupture and critical damage identities, not only phase totals.
- [ ] Validate failure localization for all models.
- [x] Keep at most four Article workers on the reference machine.

Near-exact target:

- reaction error at most 0.1 kN;
- model-point error at most 0.05 mm.

When an equivalent native-solver branch is proven but pointwise matching is
not achievable, all of the following are required:

- peak-load error at most 1%;
- normalized curve RMSE at most 1%;
- curve-area and initial-stiffness errors at most 2%;
- peak-displacement error at most `max(0.1 mm, 2%)`;
- identical critical rupture/failure localization;
- zero unsafe strict commits and full reference peak/displacement coverage;
- deterministic C# trace evidence for any claimed backend waiver.

### Gate C — close material-change validation

- [x] Correct the false-pass acceptance logic identified in review R1.
- [ ] Promote the opt-in Vert/change/scour/live benchmark into signed release
      evidence rather than leaving it as an environment-gated test only.
- [ ] Run authored and strict variants through the complete chain.
- [ ] Record pre-change and post-change material keys, spring identities,
      committed-history transfer, dense-array identity/reuse, and backend
      coverage.
- [ ] Test linear and exponential transverse laws plus Linear, Coulomb, and
      Cacovic shear where constructible.
- [ ] Test topology-compatible in-place updates and topology-changing compiled
      rebuilds; both must end with zero unmanaged V1 objects.
- [ ] Add cyclic reversal after mutation and compare C# spring checkpoints.

Acceptance: state transfer, response, failure localization, and strict
equilibrium pass with compiled-only execution throughout.

### Gate D — complete the C# core audit

Maintain a traceable C# -> Python matrix with `verified`, `partial`, `missing`,
`intentional C# defect`, or `out of V1 scope`. Every row must identify its C#
authority, Python owner, focused tests, Article evidence, and compiled backend
owner.

Audit and close:

- HRX loading, unlocked preprocessing, six-face contacts, afference,
  self-weight, combinations, dependencies, restart, mutation, and projection;
- elastic, linear-hardening, linear-softening, exponential-tension, and
  parabolic-compression masonry curves;
- constructible unloading/hysteretic behavior, fracture energy, ductility,
  contact area, mixed material, and cyclic reversal;
- Linear, Coulomb, and Cacovic shear domains;
- LoadControl, ArcLength, ArcLengthLinear, force/displacement control;
- standard/modified Newton, Regula-Falsi, Secant, Bisection, and
  Initial-Interpolated behavior;
- ForceMoment, DispRotation, and Work semantics;
- P-Delta EachStep/EachIteration;
- modal mass, eigensolution, participation, effective mass, and shapes.

The existing P-Delta capability inconsistency must remain resolved as validated
support, not merely the presence of dormant implementation code.

Review R5 requires direct C# differential verification of concrete ArcLength
line-search trial equations. Route authored compatibility and production-safe
behavior explicitly; improving strict convergence does not justify changing
the authored numerical path silently.

### Gate E — qualify every solver recommendation

Build scenario matrices for:

- coarse and fine gravity/seating;
- force-controlled pushover;
- displacement-controlled pushover;
- full live-load ArcLength through peak and descending branch;
- Bridge 3.2 mixed-material/ring-separation behavior;
- the complete interface-material-change chain;
- P-Delta EachStep and EachIteration for gravity and live load;
- near-collapse and cyclic reversal;
- modal analyses where eigensolver choices are exposed.

Enumerate every constructible supported combination of integrator, standard or
modified method, line search, and convergence criterion. A candidate qualifies
only if it reaches safe equilibrium, covers the required range, and preserves
the accepted response. Compare speed only among qualifiers.

For every candidate record cold and warm runtime, nonlinear iterations, linear
solves, factorizations, peak memory, kernel/backend coverage, terminal outcome,
equilibrium audit, and response metrics. Use at least five measured repetitions
after one explicit warm-up for performance rankings; report median and spread.

Replace hard-coded or generic advisor claims with evidence-qualified rules.
Retain and test the public `SolverStrategyAdvisory`, `SolverStrategyReport`,
`SuboptimalSolverStrategyWarning`, and
`inspect_solver_strategy(model, analysis_names)` interfaces, plus
`strategy_policy="warn" | "off"` on `AnalysisSession` and
`run_python_solver_job`, defaulting to `"warn"`.
Each warning must include a stable code, scenario, selected configuration,
reason, measured recommendation, evidence version, and documentation link. It
must be emitted once through Python warnings and `on_log`, and must never mutate
the HRX automatically.

Deduplicate per analysis/configuration, test both warning and log delivery,
and test `off`. An unmeasured combination must be identified as unqualified,
not declared optimal or suboptimal without evidence. Remove unsupported
"always", "guarantees", and fixed `100×` claims from existing documentation.

### Gate F — performance qualification

- [ ] Establish cold-JIT and warm-cache baselines on representative coarse and
      fine models.
- [ ] Profile preparation, runtime construction, load assembly, tangent
      assembly, residual/domain update, sparse factorization/solve, line search,
      snapshot/rollback, mutation, and output projection separately.
- [ ] Demonstrate that every repeated numerical family uses NumPy/Numba/SciPy.
- [ ] Compare before/after response and backend coverage for every optimization.
- [ ] Measure Linux on Python 3.12, 3.13, and 3.14. Defer Windows measurement
      until after V1.
- [ ] Record CPU, RAM, OS, package versions, thread count, cache state, hashes,
      repetitions, median, dispersion, and peak RSS.
- [ ] Reject an optimization if it changes an accepted response or introduces
      an unmanaged/scalar production path.

No universal speedup claim may be made from one machine, one model, or one
repetition.

### Gate G — documentation and packaging

- [ ] Update the scenario strategy table only from qualified matrices.
- [ ] Document convergence criteria, units, equilibrium audit, cutbacks,
      terminal outcomes, compatibility mode, and strict mode.
- [ ] Document the compiled-only backend contract and diagnostic-scalar oracle.
- [ ] Publish supported-law and unsupported-feature matrices.
- [ ] Keep `pyproject.toml` as version authority and expose it through
      `importlib.metadata`.
- [ ] Set `1.0.0`, classifiers and tested dependency compatibility bounds;
      document private installation, changelog and known limitations.
- [ ] Run Linux Python 3.12-3.14 CI, package build, wheel install, API
      smoke test, deterministic compact benchmarks, and documentation review.
- [x] Build wheel and sdist from the current worktree, run `twine check`,
      regenerate `SHA256SUMS`, verify all packaged non-test Python modules
      byte-for-byte, and import the dependency-resolved installed wheel.
- [ ] Repeat that package gate from the final approved, committed release
      candidate after the remaining validation gates close.

### Gate H — release and raw-data retirement

Tag `v1.0.0` only after Gates A-G pass. Preserve together:

- wheel, sdist, and SHA-256 manifest;
- changelog, feature matrix, limitations, and private-install instructions;
- Article source validation, authored/strict report, data, plots, hashes, and
  compact C# golden rows;
- critical spring checkpoints and failure-localization evidence;
- strategy and performance reports;
- Linux CI evidence. Windows evidence is a post-V1 follow-up.

Only after the tag may ignored raw HRX/Results assets, transient plots,
checkpoints, and calibration outputs under `my_model/Article_Models_Benchmark`
be removed. Record every removed absolute path, byte size, total reclaimed
space, and whether recovery is possible.

## 5. Required execution order

Preserve all current uncommitted work. Implement on `codex/v1-release` using
focused, independently verified commits; never discard unrelated changes.
This document update itself does not authorize a tag or raw-data deletion
before the release gates pass.

1. Enforce compiled-only public execution and zero-unmanaged reporting.
2. Re-run focused compiled differential and interface-mutation tests.
3. Close Bridge 3.2 strict gravity, then its mixed-material live-load path.
4. Re-run all 14 Article models authored and strict with the compiled gate.
5. Build and execute the complete solver-strategy/performance matrices.
6. Update advisor rules from qualified evidence.
7. Finish the C# feature matrix and user documentation.
8. Run the OS/Python CI matrix and clean-wheel verification.
9. Review evidence, tag, preserve artifacts, then retire raw assets.

CI must cover 64-bit Linux on each of Python 3.12, 3.13 and 3.14, with clean
dependency installation, the full unit/integration suite, build, clean-wheel
numerical/API/version smoke tests and deterministic compact benchmarks. Windows
validation is deferred until after V1. Keep the approximately 36 GB raw Article
suite outside CI and run it as a signed-off release-candidate gate with no more
than four workers.

## 6. Reproducible commands

Full tests:

```console
.venv/bin/python -m pytest -q
```

Actual interface-change C# comparison:

```console
HISTRA_RUN_CHAIN_BENCHMARK=1 .venv/bin/python -m pytest \
  histra/tests/test_interface_material_chain.py::test_complete_vert_scour_live_chain_matches_csharp_results -q
```

Article release candidate, maximum four workers:

```console
.venv/bin/python -m histra.tools.article_models_benchmark \
  --models-dir my_model/Article_Models_Benchmark \
  --model all --run-mode both --max-workers 4 \
  --output-dir release-evidence/article-models-v1-rc
```

Strategy matrix:

```console
.venv/bin/python -m histra.tools.strategy_benchmark <matrix.json> \
  --output <versioned-result.json>
```

Package verification:

```console
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*.whl dist/*.tar.gz
.venv/bin/python -m histra.tools.release_manifest dist --output dist/SHA256SUMS
```

## 7. External evidence and current user dependency

No additional user data is required for the next implementation work. The
supplied Article CSV/notebook and Bridge 3.1 Coarse HRX/Results are integrated.
The immediate trace target is the interface-change chain with the original HRX:
run `Vert`, change interfaces 359–362 to material 147, then record `scour_1`
step 2 with ForceMoment tolerance `1e-4` and the selected modified line-search
configuration. Capture each Newton and line-search trial deterministically:
sparse K, B, X, residual, load factor, line-search eta/bracket values, control
displacement, and the relevant Quad/interface spring strain, stress and phase.
A `.Results` file alone cannot reconstruct those iteration-level quantities or
justify a tolerance waiver. The trace will distinguish an assembly/constitutive
state difference from a strict solution branch that C# also cannot equilibrate.

## 8. Definition of done

V1 is done only when every checkbox in Gates A-H is closed with versioned
evidence, every public production analysis is compiled-only and fail-closed,
all Article strict runs are safe and cover their required range, every advisor
recommendation is measured for its stated scenario, supported C# core behavior
is traceable to tests, Linux passes on its supported Python versions, the clean
wheel passes, and the documentation review approves the exact release candidate.
