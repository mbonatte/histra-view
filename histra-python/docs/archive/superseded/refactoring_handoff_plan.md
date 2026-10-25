# HiStrA Python refactoring and performance handoff plan

## 1. Purpose

This document is the implementation handoff for continuing the architecture-wide
refactor of HiStrA Python. It is intentionally detailed enough for another AI
agent to continue without reconstructing the decisions, numerical invariants,
benchmarks, or repository state from conversation history.

The objective is not cosmetic cleanup. The work must simultaneously:

1. preserve or improve numerical parity with `C#_Original`;
2. reduce runtime and memory cost on real bridge analyses;
3. split large mixed-responsibility modules into coherent owners;
4. retain compatibility facades while production code imports the owner;
5. make tests stricter, more complete, and no slower;
6. commit only isolated, fully verified slices.

Accuracy is the first priority. Velocity is the second priority. A fast result
that drifts from the C# execution path is not acceptable.

The architecture contract is [refactoring_architecture.md](refactoring_architecture.md).
Read that file and this handoff before editing production code.

## 2. Non-negotiable constraints

### 2.1 Numerical behavior

- Treat `C#_Original` as the behavioral authority unless an intentional C# bug
  fix is explicitly documented and isolated.
- Preserve C# operation order where floating-point branch selection depends on
  it. Do not replace a verbose expression with an algebraically equivalent one
  without bit-level evidence.
- Preserve C# `System.Single` and XNA `Vector3` behavior where material or
  geometry values originate as float32.
- Keep the warning audit strict. Do not increase warning tolerances for load,
  displacement/rotation, work, force balance, or active-DOF residuals.
- Do not suppress `UnsafeEquilibriumWarning`. The current expected default-suite
  count is part of the regression gate.
- Unknown enum, phase, direction, or constitutive values should fail explicitly
  instead of silently falling back.

### 2.2 Performance implementation

- Do not add Python scalar loops to a production hot path.
- Use NumPy for medium-grain vectorized work and Numba for repeated numerical
  kernels where Python dispatch would dominate.
- A small scalar function may remain as a strict oracle/fallback, but the real
  production batch path must remain NumPy/Numba-backed.
- Do not enable `fastmath` in parity-sensitive kernels.
- Numba kernels should normally use `cache=True`; use `nogil=True` where safe.
- Warm JIT separately when measuring steady-state performance.
- Do not assume `prange` is faster. Prior experiments showed thread scheduling
  overhead exceeded the gain for the current per-correction batch sizes.
- Independent models can run in parallel, but do not run more than four large
  Article models concurrently on the reference 31 GiB machine. Eight workers
  exhausted RAM and 8 GiB swap.

### 2.3 Repository discipline

- Use `rg`/`rg --files` for discovery.
- Use `apply_patch` for code edits.
- Preserve unrelated dirty files. Never stage them.
- Do not normalize a whole mixed-EOL file. Several test and solver files contain
  intentional/pre-existing mixed CRLF/LF chunks. Inspect `git diff --check` and
  the actual diff after every patch.
- Keep each commit focused and independently revertible.
- Run focused tests first, then the complete default suite before committing.

## 3. Verified repository state at handoff

The latest completed commit is:

```text
8616038 refactor(preprocessing): extract contact geometry
```

Immediately preceding verified commits are:

```text
efe7bb3 refactor(preprocessing): extract spring factory
1876cec refactor(preprocessing): extract constitutive law mapping
cfc9a4d refactor(solver): centralize interface stiffness ownership
8ddb868 feat(tools): add strict article C# benchmark
051bf6a refactor(solver): separate load assembly and tighten C# parity
```

### 3.1 Current default test gate

The exact last command was:

```bash
/usr/bin/time -f 'ELAPSED=%e MAXRSS_KB=%M' .venv/bin/pytest -q histra/tests
```

The result after `8616038` was:

```text
440 passed, 5 skipped, 12 warnings in 75.24s
ELAPSED=76.21
MAXRSS_KB=537196
```

The 12 warnings are expected strict safety-audit warnings. A refactor must not
make them disappear by weakening the audit.

The original measured baseline before this refactor sequence was:

```text
376 passed, 5 skipped, 16 warnings in 109.90s
```

The current suite is therefore approximately 31.5% faster despite 64 additional
passing tests.

### 3.2 Current preprocessing benchmark

Use:

```bash
.venv/bin/python -m histra.tools.benchmark_preprocessing \
  --reference histra/model-output/model.hrx \
  --output /tmp/histra-preprocessing.json
```

The last result after contact extraction was 0.5382 seconds for preparation of
the 126-DOF reference model. The immediately preceding measurements were 0.5331
and 0.5686 seconds. Treat these differences as run-to-run noise.

The important invariant is that all of the following were unchanged:

- exact interface topology;
- exact global-DOF afference sequence;
- afference coefficient error signature;
- transverse, in-plane, out-of-plane, and Quad spring error signatures;
- initial global stiffness error signature.

### 3.3 Current module sizes

```text
histra/preprocessing/prepare_model.py       2,012 lines
histra/preprocessing/contact_geometry.py     922 lines
histra/preprocessing/constitutive_laws.py    263 lines
histra/preprocessing/spring_factory.py       858 lines
histra/solver/hysteretic_batch.py          4,938 lines
histra/solver/solve.py                       949 lines
histra/elements/quad.py                    1,225 lines
histra/springs/coulomb03.py                1,118 lines
```

`prepare_model.py` began at 3,921 lines and is now 48.7% smaller.

### 3.4 Dirty files that are not part of this refactor

At handoff, the following pre-existing/user-owned changes remain unstaged. Do
not modify, discard, or stage them unless the user explicitly changes scope:

```text
 M histra/postprocessing.py
 M histra/solver/outcomes.py
 M histra/solver/session.py
 M histra/solver/state_snapshot.py
 M histra/types/linear_system.py
 M run_model.ipynb
 D run_overturning_wall.ipynb
?? analytical_sensitivity/
?? docs/PhD-Thesis/
?? run_overturning_wall_with_rotation_analysis.ipynb
```

Always run `git status --short` before staging. Stage exact paths only.

## 4. Work already completed

### 4.1 Load assembly

`histra/solver/load_assembly.py` now owns C# load-template coefficient
resolution and global load-vector assembly. Tests exhaustively cover the C#
`Gamma × Psi` and `GC` branches. `solver/assembler.py` no longer owns load
generation.

C# authority:

```text
C#_Original/CommonObjectManagement/LoadTemplateManager.cs
```

### 4.2 Interface stiffness ownership

`elements/interface.py` is the only owner of interface-local flexural, sliding,
and out-of-plane stiffness formulas. Duplicate implementations were removed
from `solver/assembler.py`.

Standalone assembly calls each element's `compute_k(alfa)` exactly once and
consumes the resulting status blocks. The nonlinear runtime continues to use
precomputed blocks and fixed sparse scatter topology.

C# authority:

```text
C#_Original/Objects/Interface.cs
```

### 4.3 Constitutive-law mapping

`preprocessing/constitutive_laws.py` owns immutable material-to-law mappings.
`prepare_model.py` retains private compatibility aliases.

The C# comparison fixed three real parity defects:

1. `MasonryMaterial.AlfaShear` clamps to `[1e-5f, 0.99999f]`;
2. C# inverts `IsDuctility` into `IsDuctilityFixed` in
   `ConstitutiveLawCoulomb`;
3. out-of-plane vertical sliding uses C# `CriterioSnervamento` and `Gs`, not
   the in-plane vertical domain and `GsVer`.

Strict tests cover every flexural/shear constructor field, all six sliding
slots, float32 reads, clamp boundaries, ductility modes, and the C# diagonal
elasto-plastic tensile-weight asymmetry.

C# authorities:

```text
C#_Original/ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs
C#_Original/Objects.Material/MasonryMaterial.cs
C#_Original/Objects.ConstitutiveLaw/ConstitutiveLawCoulomb.cs
```

### 4.4 Spring factory

`preprocessing/spring_factory.py` owns scalar and NumPy-batched spring
construction, copying, combination, and envelope initialization.

The existing bit-exact scalar-vs-batch tests now import the owner directly.
`prepare_model.py` keeps stable private aliases for compatibility.

### 4.5 Contact geometry

`preprocessing/contact_geometry.py` owns:

- six-face Quad geometry caching;
- broad-phase NumPy overlap filtering;
- exact clipping fallback;
- XNA-compatible float32 vector arithmetic;
- C# contact tolerances and interface subdivision;
- endpoint selection and geometric-node spatial indexing;
- Quad/Quad and restraint/Quad interface generation.

The conservative prefilter test checks 1,500 randomized contact pairs and
asserts that no scalar contact is rejected.

## 5. Immediate next task: extract afference and inverse bilinear mapping

This is the next recommended commit. Do not combine it with fibre-stiffness or
solver changes.

### 5.1 Target file

Create:

```text
histra/preprocessing/afference.py
```

The module should own generalized-DOF mappings and the C# float32 inverse
bilinear implementation used by warping interpolation.

### 5.2 Exact symbols to move

Move these definitions from `prepare_model.py`:

```text
_QuadAfferenceGeometry
_assign_quad_afference
_warping_nodal_vectors
_quad_afference_geometry
_warping_vector_from_geometry
_warping_vector_at_point
_point_afference
_rotation_afference
_assign_interface_afference
_bilinear
_bilinear_f32
_inverse_bilinear_f32_bisection_reference
_inverse_bilinear_f32_python
_bilinear_component_f32_nb
_inverse_bilinear_f32_nb
_inverse_bilinear_f32
_inverse_bilinear
```

In the current committed file, the main regions are approximately:

```text
_QuadAfferenceGeometry                       around line 125
_assign_quad_afference .. _assign_interface_afference
                                             around lines 290-518
_bilinear .. _inverse_bilinear               around lines 519-946
```

Resolve by symbol names rather than trusting line numbers after edits.

### 5.3 Important extraction pitfall

`PreparationReport` and `_QuadAfferenceGeometry` are adjacent dataclasses. Do
not mechanically extract from the first `@dataclass(frozen=True)` marker; that
would accidentally move `PreparationReport`. Extract only the
`_QuadAfferenceGeometry` decorator/class block.

No incomplete afference file is present at handoff. A draft was deliberately
removed before writing this plan.

### 5.4 Required imports in the new owner

Expected dependencies are:

```python
from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

try:
    from numba import njit
except Exception:
    njit = None

from histra.elements.interface_state import InterfaceState
from histra.elements.quad import Quad
from histra.model.model import Model
from histra.preprocessing.contact_geometry import (
    _cross3_f32,
    _dot3_f32,
    _f32,
    _unit_f32,
    _v,
)
from histra.preprocessing.errors import ModelPreparationError
from histra.types.afference_entry import AfferenceEntry
```

Verify imports with `ruff` if available and with focused tests. Do not introduce
a reverse import from `afference.py` to `prepare_model.py`.

### 5.5 Compatibility facade

`prepare_model.py` must import/re-export every moved private symbol so existing
callers remain valid. Production code inside `prepare_model.py` should consume
the imported owner symbols, not duplicate logic.

Add:

```text
histra/tests/test_afference_architecture.py
```

The test should import `histra.preprocessing.afference`, import
`histra.preprocessing.prepare_model` through `importlib`, and assert identity
for every moved symbol.

### 5.6 Tests that must be retargeted to the owner

Update owner-level numerical tests without deleting facade compatibility tests:

```text
histra/tests/test_prepare_model_inverse_bilinear_numba.py
histra/tests/test_prepare_model_performance.py
```

Specific changes:

- `test_prepare_model_inverse_bilinear_numba.py` should import the float32
  inverse functions from `preprocessing.afference`, not the facade.
- In `test_prepare_model_performance.py`, the test that monkeypatches
  `_warping_vector_from_geometry` must monkeypatch the owning `afference` module.
  Monkeypatching the facade will not affect globals resolved inside the moved
  function.
- Calls through the facade may remain where the purpose is explicitly testing
  compatibility.

### 5.7 Required focused gate

Run at minimum:

```bash
.venv/bin/pytest -q \
  histra/tests/test_afference_architecture.py \
  histra/tests/test_prepare_model_inverse_bilinear_numba.py \
  histra/tests/test_prepare_model_performance.py \
  histra/tests/test_prepare_model.py \
  histra/tests/test_prepare_model_numeric_hysteretic_batch.py
```

The inverse bilinear test must continue comparing returned float32 values by
their exact `uint32` bit patterns over all three dropped-coordinate
orientations.

### 5.8 Acceptance conditions for the afference commit

- No change to interface topology or afference DOF order.
- No change to benchmark coefficient/stiffness error signatures.
- Python reference and Numba inverse mappings remain bit-exact.
- Full suite passes with exactly the expected warning behavior.
- `git diff --check` is clean.
- Only the afference owner, facade, tests, and architecture document are staged.

Suggested commit:

```text
refactor(preprocessing): extract afference mapping
```

## 6. Next preprocessing task: extract fibre and cell geometry

After afference is committed, create:

```text
histra/preprocessing/fibre_geometry.py
```

### 6.1 Symbols to move

Move the interface-cell and fibre-stiffness block as one unit:

```text
_cell_vertices
_dot3_nb
_norm3_nb
_cross3_nb
_bilinear_nb
_interface_cells_nb
_polygon_areas_3d_nb
_inverse_bilinear_nb
_fiber_stiffness_batch_nb
_interface_cells
_polygon_areas_3d
_fiber_stiffness_batch
_fiber_stiffness
```

The block currently begins near `_cell_vertices` and ends before
`_distance_to_interface_plane`.

### 6.2 Ownership and dependencies

- Import `_bilinear`/`_inverse_bilinear` from `preprocessing.afference`.
- Import `_cross3`, `_norm3`, `_quad_vint`, `_unit`, and `_v` from
  `preprocessing.contact_geometry`.
- Keep scalar functions as exact test oracles/fallbacks.
- Keep the real multi-cell path in Numba/NumPy.
- Do not merge the scalar and compiled inverse-bilinear implementations if that
  changes operation order.

### 6.3 Required tests

Retarget or add owner tests for:

- batched cell vertices vs scalar `_cell_vertices`;
- batched polygon area vs scalar `_polygon_area_3d`;
- exact compiled bilinear operation order;
- all three inverse-bilinear coordinate orientations;
- fibre stiffness batch vs scalar reference, including error codes;
- fallback behavior when Numba is unavailable.

Add a compatibility identity test for every moved private symbol.

Suggested commit:

```text
refactor(preprocessing): extract fibre geometry kernels
```

## 7. Finish preprocessing decomposition

After afference and fibre geometry, `prepare_model.py` will still contain
material-law selection and model-dependent spring assignment. Split those
without changing the verified generic spring factory.

### 7.1 Material selection module

Recommended file:

```text
histra/preprocessing/material_selection.py
```

Move:

```text
_material
_cached_flex_law
_cached_diagonal_laws
_cached_sliding_law
_blend_coulomb_laws
_interface_sliding_law
```

This module may depend on model/interface geometry and
`constitutive_laws.py`, but not on spring construction.

Add exact tests for:

- cache keys and one-parse-per-material/orientation behavior;
- broad faces 4/5 selecting direction 3;
- horizontal/vertical orthotropic blending;
- restraint interfaces resolving the Quad side correctly;
- preserving the primary runtime law type during orthotropic blending.

### 7.2 Model-dependent spring assignment module

Recommended file:

```text
histra/preprocessing/spring_assignment.py
```

Move:

```text
_distance_to_interface_plane
_quad_spring
_side_transverse_spring
_interface_parent_material
_side_sliding_spring
_transverse_side_properties_batch
_create_interface_springs
rebuild_interface_springs
```

The generic arithmetic remains in `spring_factory.py`; this module only binds
geometry/material sides to concrete Quad and Interface objects.

Preserve these C# quirks with explicit tests:

- restraint/custom-material identity aliasing for out-of-plane springs;
- C# creates two out-of-plane entries from the same temporary in one custom
  restraint path, so both entries can be the same object;
- `SetUltimateDisplacement` runs after side combination;
- broad Quad faces use direction-3 sliding modulus;
- plane distance is calculated once per Quad side;
- non-restrained transverse cells use the NumPy batch factory;
- restraint paths preserve C# scalar validation/error order.

### 7.3 Final `prepare_model.py` responsibility

The final file should contain only:

- `PreparationReport`;
- public `prepare_model` orchestration;
- readiness/unsupported-topology validation specific to preparation order;
- stable compatibility imports/re-exports.

Target size: preferably below 500 lines. Do not force the line target by
creating artificial one-function modules.

Suggested final preprocessing commit:

```text
refactor(preprocessing): reduce prepare model to orchestration
```

## 8. Performance work after preprocessing architecture is stable

Refactoring by itself is not a sufficient performance result. Once the
preprocessing split is complete, take fresh profiles of the actual slow
Benchmark 3 and one representative Article model.

### 8.1 Measurement protocol

For every benchmark:

1. record model, analysis chain, commit, machine, Python/NumPy/Numba versions;
2. measure load, preparation, each analysis, and result projection separately;
3. record RSS before/after and peak RSS;
4. separate cold JIT and warm steady-state runs;
5. use `cProfile` only to locate Python overhead, not as wall-time truth;
6. retain C# step/reaction/displacement checkpoints in the same report;
7. make one optimization at a time and rerun strict parity tests.

Do not use the full pytest wall time as the application benchmark.

### 8.2 Known current performance evidence

- The supplied pair of Benchmark 3 runs previously took approximately 16
  minutes on the user's machine.
- Older profiling showed interface spring creation dominant during large-model
  preparation, which motivated `spring_factory.py`.
- Current small-model preparation is about 0.54 seconds.
- In the 560-DOF profile, nonlinear runtime was dominated by fused constitutive
  updates, not sparse scatter.
- Sparse factorization mattered, but replacing it alone could not dominate the
  complete LiveLoad runtime.
- Parallel Numba loops were previously slower at the measured batch size.

### 8.3 Highest-value runtime target

The next major runtime target is:

```text
histra/solver/hysteretic_batch.py (4,938 lines)
```

Do not begin optimization by rewriting scalar spring classes. First split
kernel ownership and runtime state so performance changes are measurable and
reviewable.

## 9. Split `solver/hysteretic_batch.py`

The current file mixes Numba kernels, parameter extraction, topology, mutable
runtime state, object synchronization, force scatter, snapshots, and public
construction.

### 9.1 Recommended target structure

```text
histra/solver/hysteretic_kernels/
    __init__.py
    transverse.py
    interface_coulomb.py
    quad_takeda.py
    kinematics.py
    scatter.py
histra/solver/hysteretic_topology.py
histra/solver/hysteretic_runtime.py
histra/solver/hysteretic_batch.py   # compatibility facade only
```

### 9.2 Kernel grouping

#### `transverse.py`

Move the linear/simple hysteretic stress, tangent, rotation-limit, advance,
finish, and commit kernels currently concentrated roughly before line 1,430.

Preserve complete state-array differentials, not only final forces.

#### `kinematics.py`

Move:

```text
_map_global_to_local
_prepare_interface_kinematics
_map_and_prepare_interface_kinematics
_prepare_quad_kinematics
```

#### `interface_coulomb.py`

Move initial Coulomb, elastic sliding, full interface-force assembly, and
interface commit kernels.

#### `quad_takeda.py`

Move Quad tau limit, energy interpolation, ultimate-strain calculation,
positive/negative increments, trial evaluation, and commit kernels.

#### `scatter.py`

Move fixed-topology local/global force scatter, force-by-DOF refresh, and max-u
cache kernels.

### 9.3 Topology module

`hysteretic_topology.py` should own immutable compact topology and extraction:

```text
_InterfaceSlice
_build_force_by_dof_topology
parameter/state/target extraction helpers
compact offset/GDL/coefficient arrays
```

Construction can use Python because it runs once, but do not add Python work to
each Newton correction.

### 9.4 Runtime module

`hysteretic_runtime.py` should own `HystereticBatchRuntime`, dense arrays,
material mutation, snapshots, object synchronization, and cached result APIs.

Key invariants:

- no extra Python call boundary inside the fused correction hot path;
- no forced object synchronization during normal Newton corrections;
- snapshots restore every dense state array exactly;
- interface material mutation refreshes only affected slices;
- force and max-u caches have explicit invalidation rules;
- unmanaged spring fallback remains correct and visible in performance counts.

### 9.5 Compatibility facade

`hysteretic_batch.py` should re-export the existing runtime, builder, thread
helpers, and any private symbols used by tests. Production imports should use
the owning modules after migration.

### 9.6 Required strict gates

- scalar spring vs Numba state differential for every phase branch;
- simple vs general transverse kernels where applicable;
- interface Coulomb state, force, tangent, phase, normal-stress mutation;
- Quad Takeda complete state arrays;
- global/local kinematics and scatter exactness;
- snapshot/restore and commit/revert exactness;
- object synchronization only when requested;
- fixed-topology reuse count;
- warm performance regression ceiling.

Split this file over multiple commits. Never move all 4,938 lines in one
unreviewable commit.

## 10. Split the nonlinear driver

After hysteretic runtime ownership is stable, decompose:

```text
histra/solver/solve.py (949 lines)
```

### 10.1 Recommended modules

```text
histra/solver/nonlinear_setup.py
histra/solver/nonlinear_step.py
histra/solver/continuation.py
histra/solver/equilibrium_audit.py
histra/solver/solve.py             # public facade
```

### 10.2 Execution-order invariant

The C# order is behavior. Tests must lock sequences such as:

```text
restore/restart state
build or reuse stiffness
integrator reference/correction update
domain update
residual and selected convergence test
independent safety audit
line search/cutback/ALS decision
commit integrator and element state
project/store result row
```

Do not reorder operations because two calls appear mathematically independent.
Path-dependent spring phases, cached stiffness, and arc-length state can make
the order observable.

C# authorities:

```text
C#_Original/SolverRuntime.AnalysisProcedure/StaticNonLinearAnalysis.cs
C#_Original/SolverRuntime.NumericalProcedure/*.cs
C#_Original/SolverRuntime.ConvergenceTest/*.cs
C#_Original/SolverRuntime.Integrator/*.cs
C#_Original/SolverRuntime/ModelManager.cs
```

### 10.3 Safety audit

Keep the audit separate from the selected C# convergence criterion. A selected
criterion may pass while force balance or active-DOF residual remains unsafe.
Never make the warning disappear by using the selected criterion as the audit.

## 11. Split large element and spring classes last

Do this only after batch-runtime differentials are complete.

### 11.1 `elements/quad.py`

Recommended boundaries:

- static/line/self-weight loads;
- geometry and stiffness;
- C# nonlinear yield search;
- resisting force/energy;
- state and XML adapter.

The public `Quad` object should remain compatible. Extract pure kernels and
helpers rather than replacing it with a new object model in one step.

C# authority:

```text
C#_Original/Objects/Quad.cs
```

### 11.2 `springs/coulomb03.py`

Recommended boundaries:

- envelope math;
- Takeda state transitions;
- Initial hysteretic state transitions;
- state commit/revert;
- XML adapter/public facade.

Before extraction, add complete phase-transition matrices covering positive
and negative increments, unloading/reloading, reversals, ultimate limits,
normal-force changes, and both hysteretic types.

C# authority:

```text
C#_Original/Objects.Spring/SpringCoulomb03.cs
```

Resolve the exact generated-source path with `rg` because C# folders may differ
between `Objects` and `ModelLibrary` copies.

## 12. Unit-test refactor plan

### 12.1 Keep the default suite fast

- Unit tests should use small synthetic models and exact arrays.
- Reuse authoritative C# checkpoints instead of rerunning a long chain when the
  same contract can be tested from a saved state.
- Keep long acceptance runs behind explicit environment flags.
- Do not duplicate a 16-minute analysis in multiple tests.
- Warm Numba once per relevant test module/fixture where safe.
- Avoid session-scoped mutable models unless each test gets an exact restored
  snapshot.

### 12.2 Make tests stricter

For moved logic, prefer:

- dataclass/field equality;
- `np.testing.assert_array_equal` for expected bit equality;
- explicit `rtol` and `atol` only where C#/Python precision differs by design;
- exact step keys and committed-step counts;
- complete phase/state arrays;
- exact call order and call counts;
- explicit failure tests for unknown values;
- compatibility identity assertions.

Avoid vague assertions such as “not zero”, “roughly similar”, or “values
differ”.

### 12.3 Performance tests

Every optimized kernel should have:

1. a scalar or previous implementation oracle;
2. exact numerical differential coverage;
3. a warmed performance test with a conservative regression ceiling;
4. enough work to exceed timer noise;
5. no brittle claim that depends on one unusually fast run.

## 13. Deferred benchmark investigations

These are known issues but were explicitly deprioritized while refactoring.
Return to them after architecture and runtime profiling are stable.

### 13.1 Benchmark 3 offsets

Observed behavior:

- No-P-Delta: C# is slightly higher at every compared step.
- P-Delta: C# is higher near step 3 but lower near step 55, indicating a
  trajectory/cumulative-state difference rather than one constant scale.
- Running linear and P-Delta chains together took about 16 minutes.

Investigation sequence:

1. compare exact load vectors at each committed step;
2. compare restart state immediately after Vert and scour;
3. compare displacement-control/arc-length integrator state;
4. compare geometric stiffness/P-Delta contribution separately;
5. compare complete spring phase distributions at steps 3 and 55;
6. identify the first divergent Newton correction, not only the final reaction;
7. profile the same run after correctness is established.

### 13.2 Article models

The strict harness is:

```text
histra/tools/article_models_benchmark.py
```

The user explicitly said not to spend time finishing the remaining Article
models right now. Existing authored checkpoints showed many unsafe warnings and
large C# reaction differences. Do not erase those warnings or loosen tolerance.

Checkpoint output is under the ignored path:

```text
my_model/Article_Models_Benchmark/benchmark_outputs/strict_verification/checkpoints/
```

If this work resumes, use at most four parallel workers and distinguish authored
settings from strict reruns.

## 14. Recommended commit sequence from handoff

Use this order unless new evidence changes priority:

1. `refactor(preprocessing): extract afference mapping`
2. `refactor(preprocessing): extract fibre geometry kernels`
3. `refactor(preprocessing): extract material selection`
4. `refactor(preprocessing): extract spring assignment`
5. `refactor(preprocessing): reduce prepare model to orchestration`
6. `refactor(solver): split transverse hysteretic kernels`
7. `refactor(solver): split interface and quad kernels`
8. `refactor(solver): extract hysteretic topology`
9. `refactor(solver): extract hysteretic runtime ownership`
10. `refactor(solver): split nonlinear setup and step execution`
11. `refactor(solver): isolate continuation and equilibrium audit`
12. profile and optimize Benchmark 3 with strict C# checkpoints
13. split `Quad` and `SpringCoulomb03` only after complete differentials
14. run long acceptance benchmarks and public-API/dependency-cycle audit

Each numbered item may require more than one commit. Never combine unrelated
correctness and performance changes merely to reduce commit count.

## 15. Verification checklist for every slice

Before editing:

- [ ] Read the relevant C# authority.
- [ ] Record current `git status --short`.
- [ ] Identify pre-existing dirty files.
- [ ] Identify direct imports and monkeypatches of symbols being moved.
- [ ] Establish focused numerical and performance baselines.

After editing:

- [ ] Owner module has no reverse dependency on the facade.
- [ ] Compatibility facade re-exports moved APIs by identity.
- [ ] Production imports use the owner.
- [ ] Scalar/NumPy/Numba differentials pass.
- [ ] Unknown-value/error branches are tested.
- [ ] C# benchmark signature is unchanged or an intentional correction is
      documented with stronger evidence.
- [ ] Focused tests pass.
- [ ] Full `histra/tests` suite passes.
- [ ] Warning behavior is unchanged unless a real equilibrium defect was fixed.
- [ ] Performance is flat or better within measurement noise.
- [ ] `git diff --check` is clean.
- [ ] Staged paths contain no unrelated user changes.
- [ ] Architecture document is updated with exact measured evidence.

## 16. Standard commands

Discovery:

```bash
git status --short
rg -n '^class |^def |^    def ' path/to/module.py
rg -n 'symbol_name' histra C#_Original --glob '*.py' --glob '*.cs'
```

Focused preprocessing gate:

```bash
.venv/bin/pytest -q \
  histra/tests/test_prepare_model.py \
  histra/tests/test_prepare_model_performance.py \
  histra/tests/test_prepare_model_numeric_hysteretic_batch.py \
  histra/tests/test_prepare_model_contact_prefilter.py
```

Full gate:

```bash
/usr/bin/time -f 'ELAPSED=%e MAXRSS_KB=%M' \
  .venv/bin/pytest -q histra/tests
```

Preprocessing benchmark:

```bash
.venv/bin/python -m histra.tools.benchmark_preprocessing \
  --reference histra/model-output/model.hrx \
  --output /tmp/histra-preprocessing.json
```

Diff/staging audit:

```bash
git diff --check
git diff --stat
git status --short
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

## 17. Definition of completion

The architecture refactor is complete only when all of the following are true:

1. `prepare_model.py`, `hysteretic_batch.py`, and `solve.py` are facades or
   focused orchestrators rather than mixed-responsibility monoliths.
2. Every hot numerical family has an owning NumPy/Numba module and complete
   scalar/compiled differential coverage.
3. C# execution order and material/geometry float precision are explicit.
4. The complete default suite is stricter and no slower than the current gate.
5. Benchmark 3 performance has been re-profiled and materially improved without
   weakening parity or warnings.
6. Long acceptance benchmarks pass under their explicit environment flags.
7. Public compatibility, private compatibility facades used by existing tests,
   and dependency direction have been audited.
8. All refactor commits are isolated, documented, and free of unrelated user
   changes.

Until those conditions hold, do not mark the broader refactoring goal complete.
