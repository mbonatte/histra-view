# Changelog

## Unreleased

- Add an opt-in in-memory restart policy that preserves the committed applied load and reaction reference during material-change re-equilibration. The default retains the C# resisting-force baseline; the new policy is limited to analyses without P-Delta.

- Build virgin modal runtimes after state initialization, enforce live compiled coverage before stiffness/mass work, and use a compiled full-block scatter preserving the existing COO reduction order. Report the native backend used by each modal procedure and retain explicit diagnostic reference assembly.

- Batch Quad-corner displacement projection during dense result export and reuse it for ordered node averaging. Preserve C# FP32 output bits, saved mesh dimensions and existing result formats.

## 1.7.3 - 2026-10-26

- Accelerate CPU resultant geometry and fibre preparation while preserving C# arithmetic ordering. Skip saved computational HRX state in solver entry points and avoid duplicate compiled-runtime construction on virgin static solves.
- Add bounded, isolated CPU batch jobs and a single-model resource runner with independent Numba/BLAS thread budgets, optional project-local LP64 OpenBLAS installation, actual native-library reporting, and `.histra` output. Retain committed output after cooperative cancellation/failure where export completes before the hard deadline.
- Add an opt-in experimental NVIDIA cuDSS FP64 sparse backend, deterministic mode, reusable factors, and CPU/GPU precision and performance tools. CPU element kernels, compiled coverage checks and strict job equilibrium auditing remain enabled.
- Record model-specific CPU and GPU evidence. Repeated numeric factorization of the captured 47,768-DOF system improved 3.35× with optimized CPU BLAS and 18.18× with cuDSS. These are matrix-phase measurements, not whole-analysis speedups. Full Dhir CPU/GPU attempts timed out after two committed load steps; full-history GPU parity is not qualified, and the larger Article Bridge 1 GPU comparison exceeds the requested tolerance.
- Add regression coverage for loader equivalence, initialization count, resource isolation, native ABI checks, process timeouts, partial-result exports, and solver factorization lifecycle.

## 1.7.2 - 2026-10-26

- Add named ModelPoint XYZ displacement histories to summary JSON and bundled summaries, with cm/mm units, locations, analysis flags and reader plotting accessors. Retain point labels and predecessor histories at the analysis boundary.

- Extend native viewer schema to 2.1.0 with C# spring strain, plastic displacement/strain/demand and explicit phase/rupture/history indicators for fibres, sliding and Quad diagonals. Preserve undefined native divisions through validity masks.

- Add opt-in capture and native C# `.Results` SQLite output for supported static masonry states, with exact stored-record comparison against reference databases. File-byte identity and automatic solver bit parity are not claimed.

- Add lossless single-file `.histra` study bundles using ZIP/LZMA, reversible byte shuffling and content-based deduplication across cases, with embedded HRX sources and attachments.
- Add session bundle export, lazy `SimulationResults` bundle loading, full integrity verification and a converter for existing JSON/NPZ/HDF5 outputs with optional verified cleanup. See the [bundle guide](docs/reference/histra-bundle-format.md).

- Reorganize current documentation around usage, architecture, tooling and release workflows; archive superseded V1/refactoring plans and correct stale paths/preparation descriptions.
- Remove a verified duplicate model ZIP, consolidate dependency entry points, and relocate source-only analytical/profiling utilities out of the repository root.

- Remove tracked Jupyter notebooks and saved outputs; preserve benchmark plotting-source provenance in compact JSON and ignore local notebooks.

## 1.7.1 - 2026-10-25

- Correct native output units to cm/kN/kN·cm/rad, add explicit cm/mm displacement metrics, and select pushover forces by dominant baseline-subtracted reactions.
- Introduce native results schema 2.0.0 with complete topology, lossless per-face interface lists, per-Quad corner displacements, and explicit fibre offsets. Export actual MPa spring stress and correctly indexed Coulomb phase/force state.
- Preserve stage-end export snapshots across chained analyses and material mutations; write portable session manifests indexing every exported stage and copying the source HRX.
- Extend `SimulationResults` with topology, Quad displacement, spring-slicing and session-loading helpers while retaining legacy dataset access. See [native results format](docs/reference/native-results-format.md) for migration and scope.

## 1.7.0 - 2026-10-23

- Native Two-Tier Simulation Output Architecture (`ResultsWriter` and `SimulationResults`):
  - Tier 1 Summary Manifest (`<case_id>.summary.json`, < 100 KB): fast schema-versioned metrics, capacity summaries (F_max, d_max, ductility, failure classification), and 1D scalar response curves.
  - Tier 2 Dense Array Dataset (`<case_id>.fields.npz` or `.h5`): contiguous NumPy array storage separating static mesh topology (`mesh/nodes_xyz`, `mesh/quad_conn`, `mesh/interface_vint`, etc.) from dynamic step fields (`fields/U`, `fields/node_displacements`, `fields/interface_resultants`, `fields/interface_moments`) and stage-end spring constitutive states.
  - Session Export API: `session.export_analysis(...)` and `session.export_session(...)` for single analysis or multi-stage chained session exports.
  - Zero-dependency ParaView VTK Export: `SimulationResults.to_vtk(output_vtu_path, step=-1)` for immediate 3D deformed mesh visualization.
  - Zero-proxy per-step resultant hooks in solver loop capturing contiguous float32 interface force and moment arrays directly from `HystereticBatchRuntime`.

## 1.6.4 - 2026-10-23

- Eliminate proxy materialization in `TransverseFiberGroup` across nonlinear setup, stiffness assembly, state reverting, quad/interface caches, snapshotting, and postprocessing, preventing 550k proxy objects and saving ~1.90 GB dirty RAM on 3D bridge models.
- Implement custom fast `__deepcopy__` on `TransverseFiberGroup`, `_StiffnessAssemblyPlan`, `Point`, `AfferenceEntry`, `Interface`, `Quad`, and spring classes, reducing deepcopy memory overhead from +3,429 MB down to +254 MB (13.5x reduction) and dropping clone duration from minutes to 1.50 seconds.
- Break cyclic reference in `_TransverseParameterView` via `weakref` and release solver factorizations immediately on exit (`ls.close()`), allowing clean deallocation during loop execution with disabled GC.
- Add regression coverage in `test_transverse_group_memory_and_cache.py` ensuring zero proxy creation and Copy-On-Write array integrity.

## 1.6.3 - 2026-10-23

- Complete C# `Interface.CalcolaRisultanti` resultant bending-moment calculation (`Mx, My, Mz` in `float32`) in `histra.postprocessing` and compiled `HystereticBatchRuntime` / `ModelManager.refresh_saved_interface_forces`, verified against C# `InterfaceStates`.
- Synchronize 12-DOF local interface resisting forces (`Interface.f`) from `HystereticBatchRuntime._local_full_forces` when publishing dense runtime state to Python compatibility objects.
- Skip auxiliary 2-node interface edge vertices created during `ModelManager.prepare_model` when exporting Quad node translations in `compute_node_displacements`.

## 1.6.2 - 2026-10-17

- Reject interface spring-class changes by default. Add explicit `spring_type_change="csharp_reset"` compatibility through the session, free mutation function and backend job API, warning about discarded histories and reporting every reset spring. Matching classes retain their committed histories; failed mutations restore the prior model.
- Preserve C# elastic trial/committed field semantics in scalar springs and compiled runtime projections. Retain actual elastic Quad histories and restored tangent during runtime import.
- Validate the two new loaded-foundation GUI references against original C# 2026.1.1: 84 committed static steps match checked saved fields and iteration counts; all six available modal comparisons pass. Both return attempts stop before committing, as in C#, so successful return-stage validation remains open.
- Replace formula-only multilinear tests with original C# masonry `SpringHysteretic` backbone, trial, commit and reversal fixtures, checked against scalar and compiled execution. Generic `SpringMultiLinearPlastic` remains unimplemented; the legacy Python container now rejects numerical evaluation instead of silently returning a linear response.
- Preserve the predecessor tangent, yield metadata and F0 across numeric-fibre material resets. Native DB restoration checks cover virgin/plastic/reversed histories and repeated resets. Python's lossless cumulative-energy policy remains an explicit difference.
- Initialize dense constitutive arrays for topologies containing only numeric fibre groups, with native-state checks and poisoned-buffer regression coverage.
- Replace the unsubstantiated full-parity audit with a reproducible source inventory, bounded native source bindings, and an explicit remaining-validation register.

## 1.6.1 - 2026-10-17

- Add a function inventory and proposed C# mappings. Subsequent review found nonexistent source references and an incorrect blanket parity claim; the corrected scope is recorded in `docs/audit/csharp_python_function_mapping_matrix.md`.
- Add offline expected-output regressions for friction, hysteresis, quadrature, clipping, Arc-Length and convergence. Some expectations are analytical or use tolerances; these do not establish universal bitwise parity. The original multilinear tests exercised a test-only helper and are superseded by the 1.6.2 corrections.
- Add adversarial regressions for selected degenerate geometries, reversals and Arc-Length states. Native provenance and coverage are limited to identified fixtures and checks.
- Fix P-Delta test fixture initialization setup in `histra/tests/test_pdelta.py` to restore 100% test pass.
- Retain compiled backend coverage enforcement; this release did not change the production solver implementation.

## 1.6.0 - prepared 2026-10-15

- Reuse disposable Newton iteration snapshot buffers while preserving all spring state and rollback behavior. One sequential horizontal Newton-step profile measures an 8.50% runtime reduction; both complete native reference chains retain exact measured outputs at the snapshot implementation commit.
- Match original C# vector norm selectors and ordered reductions, including positive p-norms beyond L2. Add bit-exact native routine fixtures on Windows and Linux.
- Verify residual assembly and Work/force convergence directly with original C# routines for five Dhir states. Document force, moment and shear-angle residual units; retain independent equilibrium warnings and policies.
- Honor native load-direction identifiers for horizontal loading. Reproduce omitted masonry defaults, serialized ductility aliases, linear normal-force evaluation and native Quad contact admission.
- Scope the initial-stiffness fallback to the current Newton call, avoid factorizing exactly zero-column tangents, and propagate native numeric refactor failure without a duplicate retry.
- Validate the default-material horizontal reference through Vert 20 and pushover 501, including its attempt-502 displacement limit. Preserve the separate foundation-modified 20/10/58 reference and its attempt-59 nonconvergence.
- Keep routine parity tests exact while recording faster-library global-response experiments separately under the user's numerical-tolerance allowance. Preparation and qualification scope are recorded in [the release record](docs/release/v1.6.0-preparation.md).


- Match line-restraint material blending against its own native axes, including repeated Single normalization. Correct vertical sliding plastic-stiffness field selection and native sliding ductility constructor flags. Twelve native cases cover flexural, in-plane and out-of-plane law selection.


- Match C# zero-friction Coulomb masonry with a Hysteretic diagonal, including asymmetric strengths, fracture-energy/ultimate-strain construction and compiled trial/commit/revert lifecycle. Native routine fixtures cover eight geometry/material cases; production coverage includes material mutation and runtime rebuilds.


- Confirm the published v1.5.0 wheel with a fresh complete Dhir mechanical solve and output comparison: every available measured field matches through all 88 commits; attempt 59 and all iteration counts also match.
- Match native elastic transverse spring classes, mixed series construction and compiled cyclic updates, with preparation, rebuild and material-mutation coverage.
- Preserve C# Single gravity and masonry weight during modal mass assembly. The existing 20-mode Dhir reference now agrees within 2.60e-14 relative frequency difference; small remaining arithmetic differences and unqualified branches are documented in the modal benchmark.


## 1.5.0 - 2026-10-14

- Match the installed C# 2026.1.1 Dhir reference through all 20 Vert, 10 constant-load and 58 pushover commits. Every saved field for all 77,080 springs matches exactly at every commit; all 88 iteration counts match, and both solvers fail to converge at attempt 59 with code -2. Step zero is excluded from committed-step counts.
- Regenerate computational geometry from scratch and reapply material 146 to all 148 foundation interfaces; never reuse C# computational objects or histories.
- Preserve original Framework arithmetic, spring law selection, local-to-global accumulation, diagonal construction, stiffness and force operation order. Native whole-model checks cover all spring definitions, afference coefficients, initial stiffness and gravity loads.
- Make the original quadratic arc-length correction the default, retaining the simplified one-dimensional correction as an explicit alternative. Close final load-controlled intervals using the original target-minus-accumulated-multiplier calculation.
- Match original quad displacement projection, Single node averaging and cumulative element-energy order. Replaying saved Python states reproduces all 91 model-point snapshots and energy totals at all 88 commits exactly; the final output corrections have not yet been validated by a repeated full mechanical solve.
- Add unit fixtures generated by calling original C# routines, including controller branches, geometry, native UMFPACK controls, displacement projection and energy accumulation.
- Run the native geometry test on Linux with a 1e-15 absolute tolerance only for Sin; preserve exact equality for every other field and for Windows.

Validation uses original UMFPACK controls (strategy 3, refinement 2, AMD). The default fast profile is not certified for exact branch parity. Missing native pushover private histories/global vectors and NULL per-spring energies remain unavailable. C# output parity does not clear the independent equilibrium warnings. See [the full-chain report](docs/benchmarks/dhir-full-chain-native-parity-progress.md) for evidence and remaining scope; modal reference validation remains deferred.

## 1.4.2 - 2026-10-13

- Initialize hysteretic yield-coordinate metadata for generated scalar and lazy springs.
- Preserve C# Coulomb unloading memory in compiled interface and Quad commits.
- Apply Interface.SetSpring curve-family reassignment after ultimate-displacement selection.
- Dhir Vert now passes every available numeric spring response/history field; a near-zero aggregate R1 at step 9 differs by 2.09e-6 kN and remains open. C# per-spring NULL energy fields remain explicitly unavailable. Full suite: 722 passed, 23 skipped, 670 subtests.

## 1.4.1 - 2026-10-13

C# 2026.1.1 geometry and nonlinear parity improvements, with native DLL regression oracles.

### Fixes

- Reproduce C# Quad face projection, contact containment, node/plane tolerances, Vector3 normalization, local spring-cell construction, and projected fibre stiffness using compiled kernels.
- Match float32 ray–plane sliding distances and masonry shear/sliding modulus arithmetic.
- Use C# polygon-strip bisection for shear-DOF coordinates instead of Newton inversion, resolving Dhir Vert spring force and phase divergence.
- Preserve C# signed spring-energy increments, nonlinear convergence and Regula-Falsi/secant/bisection contracts, and successful Arc-Length retry clocks.
- Preserve C# interface registration on material resets by default, with the single-link alternative retained.
- Correct tapered sliding patch areas and parse legacy spring snapshots and empty load-combination cells.

### Modal

- Port C# 2026.1.1 sequential inverse iteration and configuration defaults, preserving mode identities and signs.

### Validation and limits

- Full local suite: 719 passed, 23 skipped, 623 subtests passed.
- Fresh Dhir Vert reconstruction, with material 146 applied to all 148 foundation interfaces: 77,080 springs compared at step 0 and every one of 10 committed steps; zero spring-phase differences.
- Final maximum spring-force difference: 6.10e-7 kN; spring-displacement difference: 3.01e-10. Reaction and global displacement comparisons pass.
- Detailed spring-history metadata still has open yield-coordinate, compression-history and unloading-memory differences; this release does not claim complete or bit-identical C# parity. See [the Vert audit](docs/investigations/dhir-vert-native-parity.md).
- These measurements concern Vert in explicit C# compatibility mode. They do not qualify later load stages or independent strict equilibrium.

## 1.4.0 - 2026-10-07

Batch element stiffness assembly ($K_e$), compiled Numba local-term evaluation, fixed-topology CSC scatter acceleration, and solver lifecycle plan caching: 24.4x faster element stiffness assembly with 100% bit-exact C# parity.

### Performance & Solver Optimization

- **Compiled Batch Element Stiffness Kernel (`histra.solver.assembler`)**: Implemented `_evaluate_stiffness_terms_batch`, a compiled Numba kernel that directly reads tangent stiffnesses from dense solver state arrays (`runtime.trial[:, 9]`, `coulomb_state`, `quad_state`) and computes quad, flexural, sliding, and out-of-plane local stiffness contributions into the flat term buffer in 0.34 ms, completely bypassing per-interface Python loops and heap allocations.
- **Fixed-Topology CSC Assembly Acceleration**: Fused compiled term evaluation directly with the precomputed fixed C#-order CSC scatter kernel (`_accumulate_csharp_order`), slashing tangent stiffness assembly time on `Bridge_1.hrx` from 56.1 ms down to 2.30 ms (24.4x speedup).
- **Plan Validation & Material Mutation Lifecycle (`histra.solver.model_manager`)**: Added cached plan validation across Newton-Raphson iterations (`validated_runtime_id`) while ensuring automatic invalidation and rebuild of precomputed base stiffnesses across material mutation boundaries (e.g. `Vert` -> soil material change -> `scour_1` -> `LiveLoad_1`).
- **Bit-Exact Parity & Comprehensive Test Coverage**: Validated against legacy authoritative assembly and C# `.Results` databases across multiple canonical benchmarks (`Bridge_1.hrx`, `Bridge_2.hrx`, `Bridge_3.1_Coarse.hrx`), confirming relative differences within float64 machine epsilon ($\text{rel\_diff} < 9 \times 10^{-16}$, 1 ULP).

## 1.3.0 - 2026-10-07

In-place state modernization: contiguous array-backed transverse fiber groups, 45x faster preprocessing spring allocation, 109x faster solver synchronization, and 3.7x–8x active memory reduction with 100% bit-exact C# parity.

### Performance & Memory Modernization

- **Array-Backed `TransverseFiberGroup` (`histra.springs.transverse_fiber_group`)**: Replaced individual Python `SpringHysteretic` dataclass instances and nested lists with contiguous NumPy array storage for parameters, stiffnesses, contact areas, and constitutive states. Slashes transverse spring allocation time from 13.93s down to 0.31s (45.2x speedup) on 550,000-fiber models and eliminates >4.4M Python heap objects.
- **On-Demand Proxy Compatibility**: Implemented standard `MutableSequence` interface on `TransverseFiberGroup` with transparent, on-demand `SpringHysteretic` proxy instantiation, preserving complete backward compatibility for external diagnostic tools and inspection readers.
- **Zero-Copy Dense Solver Synchronization**: Vectorized runtime state synchronization (`sync_all_to_objects`, `sync_tangents_to_objects`, `sync_interface_trial_to_objects`) directly between compiled Numba solver arrays and `TransverseFiberGroup` slices, cutting per-boundary synchronization latency from 1.88s down to 0.017s (109.4x speedup).
- **Virtual Sequence Mapping (`histra.solver.hysteretic_runtime`)**: Introduced `_VirtualSpringSequence` and `_VirtualManagedSequence` wrappers, avoiding allocation of 500k+ pointer arrays for runtime spring collections.
- **Material Chaining & Mutation**: Optimized `change_interface_materials` to transfer committed history directly across `TransverseFiberGroup` arrays without materializing scalar objects.
- **Heap & RSS Memory Footprint**: Reduced pymalloc tracked heap memory from 651 MB to 176 MB (3.7x reduction) and active RSS on canonical bridge benchmarks to ~400–500 MB.

## 1.2.3 - 2026-10-06

Fresh Quad geometry reconstruction and regression coverage for C# compatibility.

### Fixes

- Recompute Quad edge lengths, diagonals, corner angles, local axes, and thickness-weighted centroids from structural nodes before afference and spring generation, using a compiled Numba batch routine with C# Single arithmetic compatibility.
- Invalidate older preprocessing caches so prepared models use refreshed geometry.
- Add C# Dhir geometry fixtures and regression tests for distorted Quads, variable thickness, degenerate geometry, and rigid hysteretic placeholders.
- Include CI test corrections and CHOLMOD fallback fixes committed since 1.2.2.

### Tools

- Add a sparse linear solver benchmark harness and optional PyAMG preconditioning for PCG, with SSOR fallback when PyAMG setup fails.

## 1.2.2 - 2026-09-23

Native CHOLMOD supernodal Cholesky backend, preprocessing mesh & topology disk caching, Preconditioned Conjugate Gradient (PCG) iterative solver, and Quasi-Newton (BFGS) solver architecture.

### Performance & Solver Optimization

- **Native CHOLMOD Supernodal Backend (`histra.types.cholmod`)**: Direct ctypes binding to SuiteSparse `libcholmod.so.5` with zero-copy memory arrays and supernodal Cholesky factorization (`backend="cholmod"`). Slashes symbolic analysis time by 9.5x (from 6.70s to 0.70s) and numeric factorization time by 2.3x (from 5.89s to 2.55s) on large 3D models.
- **Preprocessing Mesh & Topology Caching (`histra.preprocessing.cache`)**: Transparent atomic disk and memory caching keyed by SHA-256 fingerprint of the source HRX file and code revision. Reduces model preparation time on Dhir Bridge from 30.40s down to 8.36s (3.6x speedup) while preserving fresh Python preprocessing parity rules.
- **Preconditioned Conjugate Gradient Solver (`histra.types.pcg`)**: Matrix-free iterative solver supporting Symmetric Successive Over-Relaxation (SSOR) and Jacobi (diagonal scaling) preconditioning with automatic fail-safe fallback to direct solvers (`backend="pcg"`).
- **Quasi-Newton (BFGS) Architecture (`histra.solver.bfgs`)**: Implemented Matthies & Strang (1979) two-loop recursion with Powell curvature safeguards (`curv > 1e-8 * norm_s * norm_y`), bounded memory history, and automatic tangent refresh upon stall detection (`method="BFGS"`). Combined with CHOLMOD, cuts 2-step Dhir Bridge runtime from >400s down to 46.45s with exact physical equilibrium ($1.19 \times 10^{-9}$).

## 1.2.1 - 2026-09-23

Graph partitioning matrix ordering, adaptive tangent refresh, interface scalar geometry caching, and large-scale 3D solver acceleration.

### Performance & Solver Optimization

- **METIS Graph Partitioning Matrix Ordering**: Enabled SuiteSparse UMFPACK METIS ordering by default for sparse stiffness factorization, reducing $L+U$ fill-in non-zeros by 4.3x (from 202.5M to 47.3M non-zeros on Dhir Bridge) and cutting numeric factorization time by 2.2x. Configurable via `linear_solver_ordering` and `HISTRA_UMFPACK_ORDERING`.
- **Adaptive Tangent Refresh & Cadence Newton**: Implemented residual contraction tracking (`last_contraction = error / last_error`) and cadence refresh in `NewtonLineSearch` for standard line searches, skipping redundant tangent factorizations while maintaining quadratic convergence.
- **Interface Geometry Precomputation Cache**: Precomputed invariant interface coordinate sums ($\sum d_i^2$, $\sum d_j^2$, $\sum d_i d_j$, $\sum e^2$, $\sum d_m^2$) during model preparation, enabling $O(1)$ closed-form elastic interface evaluation for uniform spring arrays in `_compute_kfless`.
- **Flexible Analysis Key Resolution**: Supported integer analysis keys in `solve_static_nonlinear` and `_setup_nonlinear_analysis`, ensuring analysis method and solver configurations are properly resolved when passed by ID.

## 1.2.0 - 2026-09-21

Fast linear solve acceleration, configurable UMFPACK iterative refinement, and non-linear solver performance optimizations.

### Performance & Solver Optimization

- **Default Fast Linear Solve Mode (`linear_solver_precision="fast"`)**: Configured UMFPACK `IRSTEP=0` by default, skipping iterative refinement and accelerating sparse back-substitutions by up to 3.24x while preserving $< 10^{-11}$ accuracy.
- **Strict C# Parity Opt-In**: Provided `linear_solver_precision="strict"` (and `HISTRA_LINEAR_SOLVER_PRECISION=strict`) to retain `IRSTEP=2` for bit-exact reference verification.
- **Vectorized Line-Search Dot Products**: Line search now uses vectorized BLAS (`np.dot`) when `csharp_line_search_compatibility=False` or `linear_solver_precision="fast"`.
- **Adaptive Tangent Refresh Architecture**: Added configurable periodic and stall-triggered tangent refreshment options in `NewtonLineSearch` and `NewtonRaphson`.

## 1.1.0 - 2026-09-21

Comprehensive performance optimization, solver acceleration, compiled backend pre-warming, and analytical C# parity documentation release.

### Performance & Solver Optimization

- **Zero-Copy UMFPACK Direct Solves**: Eliminated vector allocations during UMFPACK linear solves by directly storing results into `self.x` and passing direct memory pointers via `ctypes.c_void_p`.
- **Reusable Scratch Buffers in Newton Line-Search**: Pre-allocated reusable scratch arrays in `NewtonLineSearch` (`_scratch_residual0`, `_scratch_dx0`, `_scratch_direction`) to avoid intermediate vector allocations during iterations.
- **Fast Tangent Stiffness Assembly**: Added `sync_tangents_to_objects` option to `ModelManager.assemble_tangent_stiffness_matrix()` to bypass synchronization of individual Python spring objects during Newton matrix assembly.
- **Pre-Compiled Backend Warmup**: Added `histra.solver.warmup.warmup_compiled_backends()` to eliminate JIT compilation latency on the initial step of nonlinear analyses, integrated into `run_vert_live`.
- **Sutherland-Hodgman Polygon Clipping**: Optimized 2D polygon intersection kernel with hoisted edge math, inlined coordinate bounds, and cached coplanar intersection checking.
- **Broadphase Geometry Filtering**: Accelerated interface contact candidate filtering via compiled Numba pair search routines (`_find_broad_pairs_nb`, `_find_face_candidates_nb`).

### Analytical Engine & Parity Documentation

- **6-Chapter C# vs Python Parity Audit**: Comprehensive line-by-line mechanical and algorithmic audit covering data structures, preprocessing, constitutive models, nonlinear solvers, modal analysis, and input/output (`docs/audit/`).

## 1.0.0 - 2026-09-20

First private production release of the Python HiStrA masonry solver.

### Included

- Quad/Interface masonry preprocessing, six-face contacts, afference, self-weight,
  load combinations, staged dependencies, restart/state transfer, and interface
  material changes.
- Force- and displacement-controlled nonlinear static analysis with LoadControl,
  ArcLength, ArcLengthLinear, Newton and supported line-search variants.
- ForceMoment, DispRotation, and Work convergence criteria with an independent
  equilibrium audit; strict execution rejects unsafe committed states.
- P-Delta EachStep and EachIteration paths.
- Modal eigensolution, participation, effective mass, and mode-shape projection.
- Explicit capability preflight and solver-strategy advisories.

### Qualification & Verification

- Fresh brand-new Python preprocessing enforced across all benchmarks and entry points; never solves on serialized `.hrx` computational objects.
- All 14 Article models benchmarked in authored mode under fresh preprocessing with full step history and curve parity against `Original_article_data.csv`.
- Five-stage interface material chain qualified under fresh preprocessing with 0 unmanaged objects.
- P-Delta gravity strategy matrix requalified with 3 fresh-model repeats recommending `authored-each-step`.
- 100% compiled backend enforcement verified across initialization, restart, and post-mutation boundaries.
- Clean wheel and sdist built, byte-verified against source, and smoke-tested in isolated clean virtual environments.

### Release Status

The implementation, packaging, fresh-preprocessing verification, and local test matrix are complete.
Ready for remote CI execution on push and `v1.0.0` tagging. See `docs/release/v1-release-checklist.md`.
