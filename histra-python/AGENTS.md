# HiStrA-Python Agent Operating Manual

Operating manual and rules for AI agents working in `histra-python`. For in-depth derivations, benchmark logs, and release evidence, consult the linked documents under [`docs/`](docs/README.md).

---

## 1. Project Overview & Entry Points

`histra-python` is an in-process Python implementation of the Discrete Macro-Element Method (DMEM) for static nonlinear and modal analysis of masonry structures, porting the numerical core of the authoritative C# HiStrA solver.

### Key Packages
- `histra.model`: Domain data models and entities (`Model`, `Quad`, `Interface`, `Spring`, `Node`, `MasonryMaterial`, `Restraint`, loads).
- `histra.preprocessing`: Mesh preparation, topology regeneration, and foundation restraint assignment (`prepare_model`, `create_brand_new_model`, `rebuild_interface_springs`).
- `histra.elements`: Quad, interface, and spring mechanical models (Coulomb friction, hysteretic fibers, multi-linear).
- `histra.solver`: Static solvers (Newton-Raphson, Arc-Length, Line Search), runtime state & assembly facade (`ModelManager`), modal solver (`solve_modal_analysis`), session execution (`AnalysisSession`), and linear system interfaces.
- `histra.io`: HRX model parser, C# `.Results` SQLite reader, and projection utilities.
- `histra.tools`: Command-line entry points, benchmark runners, and diagnostics.

### Primary Public API
Exported from `histra`:
- `load_model(path)`: Parse an HRX model file.
- `AnalysisSession(model)`: Stateful multi-analysis execution manager with in-memory state preservation.
- `run_python_solver_job(model_path, requests)`: High-level job runner with dependency resolution and deadline enforcement.
- `solve_modal_analysis(model, analysis_key)`: C#-compatible modal eigenvalue analysis.
- `inspect_solver_strategy(analysis)`: Independent solver strategy advisor.

For structural definitions and full feature scope, see [Supported Features](docs/reference/v1-supported-features.md), [Data Model](docs/reference/data-model.md), and [Current Status](docs/STATUS.md).

---

## 2. Core Development Rules & Non-Negotiable Invariants

### 1. Accuracy & C# Parity Over Raw Velocity
- Numerical accuracy and C# parity are the highest priority; execution velocity is secondary (`_rules/accuracy-first-performance.md`).
- Preserve original numerical logic and bit-exact routine tests. Faster numerical libraries may introduce small global-analysis rounding differences when complete response histories and stopping behavior are validated. Keep those performance experiments separate from exact native regression; document local phase differences and numerical limits.
- Hot numerical paths must use vectorized NumPy or compiled Numba routines protected by differential regression tests against C# `.Results` databases.

### 2. Compiled Backend Coverage is Mandatory
- Production numerical execution must run entirely through compiled Numba backends (`_rules/require-compiled-execution-in-production-numerical-steps.md`).
- Silent fallback to unmanaged Python loops during numerical steps is strictly forbidden.
- Enforcement must be rechecked across lifecycle boundaries (initialization, restart, rebuild, and material mutations). Backend coverage tests require zero unmanaged Quads or Interfaces.

### 3. Fresh Model Preparation Boundary
- Serialized interfaces and springs in `.hrx` files are reference-only snapshots from past C# runs (`decisions/fresh-python-preprocessing.md`).
- Before numerical or modal solving, the model must be freshly prepared using `ModelManager.prepare_model(model, force=True)` (or `auto_prepare=True`) from `histra.solver` (or `prepare_model` from `histra.preprocessing`).
- `ModelManager.create_brand_new_model` strips serialized computational objects and reconstructs topology from geometry while preserving the source HRX for differential auditing. Solvers fail closed if solving unprepared serialized models.
- See [Preprocessing Guide](docs/guides/preprocessing.md).

### 4. Single-Solve Process Concurrency
- The solver uses shared class-level runtime arrays internally. Only one solve can execute concurrently per Python process.
- A process-wide lock guards against concurrent invocation.
- Cooperative cancellation checkpoints occur at load-step, Newton iteration, line-search, and Arc-Length retry boundaries.

### 5. Documentation Policy
- Follow [Documentation Policy](docs/DOCUMENTATION_POLICY.md): delegate deep architectural explanations and evidence to canonical guides under `docs/`.
- Never cite or link files in `docs/archive/` as current guidance; archived files exist solely for historical record.
- Maintain accurate module invocation commands (`python -m histra.tools.<module>`).

## 3. Code Structure & Agent Readability Guidelines

To ensure code remains navigable, robust, and maintainable by both human engineers and AI coding agents:

### 1. Small, Single-Responsibility Functions
- Target 4–20 lines for helper and operational logic; avoid mega-functions that sprawl across multiple screens.
- Extract self-contained logic steps (e.g., configuration resolution, convergence checks, clipping routines, boundary condition filtering) into focused private helpers.

### 2. Guard Clauses & Flat Nesting
- Prefer early returns, guard clauses, and dispatch helpers over deeply nested `if/elif/else` ladders.
- Keep control-flow nesting to a maximum of 2–3 indentation levels.

### 3. Modular File Decomposition & Facade Parity
- Decompose multi-concern modules into focused single-responsibility files (e.g., separating geometric routines into `polygon_clipping.py` or system setup into `boundary_conditions.py`).
- Re-export extracted functions from original facade modules (`__all__` / module imports) to preserve backwards compatibility for existing callers and tests.

### 4. Greppable, Descriptive Naming
- Use unambiguous, domain-accurate names for functions, types, and variables.
- Avoid vague abbreviations; choose searchable names reflecting structural mechanics or solver semantics.

### 5. "Why", Not "What" Documentation
- Write docstrings and comments explaining *why* an algorithm choice, numerical tolerance, or branch exists (citing C# HiStrA parity, physical assumptions, or matrix properties).
- Do not restate syntax. Preserve domain invariants and gotcha warnings near the code.

### 6. Strict Numerical & Parity Invariance
- Refactoring must strictly preserve numerical and behavioral parity. Never modify constitutive formulas, solver thresholds, or data models without differential regression validation.

---

## 4. Known Gotchas & Common Traps

### 1. Benchmark 3 Serialized HRX State Trap
- **Gotcha**: A historical diagnostic reported a false 100,000× stiffness discrepancy on pier foundation interface 682.
- **Cause**: The diagnostic inspected saved HRX files with `force=False`. The HRX files had been exported from C# *after* the scour stage, where interface 682 was mutated to `Soil_removed` (`E1n = 0.003183 kN/mm²`). In C# `Vert` (pre-scour), interface 682 used `Soil` (`318.3059 kN/mm²`).
- **Rule**: Always prepare models freshly (`force=True`) and apply pre-scour material assignments. Python achieves `< 7 × 10⁻¹¹ mm` displacement parity across all 1,820 DOFs.
- **Foundation Interface Identification Trap**: In `benchmark_virgin.hrx`, foundation restraint interfaces generated by `ModelManager.prepare_model` have `intf.interfaccia_vincolata == True` (keys 623..682). Do not hardcode arbitrary interface ranges such as 100..160; keys 100..160 are internal Quad-Quad masonry joints inside the pier walls. Mutating them to soil cracks the masonry, causing artificial gravity discrepancies and divergence in live loading.
- **Reference**: [Benchmark 3 Resolution Investigation](docs/investigations/benchmark-3-base-spring-reference-consistency.md) and memory page `decisions/benchmark_3_resolution.md`.

### 2. Linear-System Reset Semantics
- **Gotcha**: Resetting the linear system during Newton iterations can inadvertently discard assembled residuals.
- **Semantics**:
  - Stiffness matrix reset clears `K` only.
  - Load-vector reset clears `b` only.
  - Displacement reset clears `x` only.
- **Rule**: Matrix rebuild must never clear `b`. A Newton iteration may assemble the residual into `b` before rebuilding `K`. Clearing `b` causes catastrophic divergence from the C# solution path.
- **Reference**: ai-memory page `gotchas/linear-system-reset-semantics.md`.

### 3. Deceptive Convergence under Work / DispRotation
- **Gotcha**: `Work` convergence evaluates `0.5 * abs(du · residual) <= tol`. If `du` is tiny or near-orthogonal to the residual, `Work` can report convergence while the active-DOF force residual remains huge.
- **Rule**: Never rely solely on `Work` or `DispRotation` as proof of physical equilibrium. Use `ForceMoment` or Python's independent equilibrium audit for safety-critical evaluations.
- **Reference**: [Nonlinear Convergence Safety](docs/nonlinear_convergence_safety.md).

### 4. Interface Material Mutation Timing
- **Gotcha**: Mutating interface materials inside an active step is invalid.
- **Rule**: Interface material changes are supported strictly at committed analysis boundaries via `AnalysisSession.change_interface_materials(...)`.
- **State Preservation**: When mutating interface materials, only affected interface spring definitions are rebuilt. The predecessor deformation and committed constitutive history on unaffected interfaces must be preserved across the boundary (`concepts/interface-material-mutation-state-preservation.md`).
- **Reference**: [Analysis Chains Guide](docs/guides/analysis-chains.md).

### 5. Linear Solver Parity & Branch Divergence
- **Gotcha**: Python defaults to SciPy `SuperLU`, whereas C# uses SuiteSparse `UMFPACK`. Slight floating-point differences can trigger divergent contact branch outcomes in highly nonlinear models.
- **Rule**: For strict branch-parity debugging, set `HISTRA_LINEAR_SOLVER=umfpack` with `HISTRA_UMFPACK_LIBRARY` pointing to the shared library.
- **Reference**: [C# Parity Diagnostics](docs/guides/csharp-parity-diagnostics.md) and [Branch Divergence Investigation](docs/investigations/csharp-python-branch-divergence.md).

---

## 5. ai-memory Tooling Protocol

The project maintains persistent knowledge across agent sessions using the `ai-memory` MCP server. Future agents must consult memory before making architectural decisions or modifying numerical routines.

### When to Consult Memory
- Before modifying preprocessing, solver loops, or material constitutive models.
- Before investigating benchmark discrepancies (check existing gotchas and resolved investigations).
- When validating release readiness or reviewing performance requirements.

### Core Memory Tools
- `memory_status`: Quick health check of memory repository (page counts, sessions, observation statistics).
- `memory_explore` / `memory_recent`: Scan recent changes, pending handoffs, and active briefing notes.
- `memory_query(query=...)`: Natural language and keyword search across stored rules, decisions, concepts, and gotchas.
  - *Example*: `memory_query(query="compiled execution numba rules")`
  - *Example*: `memory_query(query="benchmark 3 parity gotchas")`
- `memory_read_page(path=...)`: Retrieve the full content of a known rule, decision, or gotcha page.
  - Essential pages to read:
    - `_rules/accuracy-first-performance.md`
    - `_rules/require-compiled-execution-in-production-numerical-steps.md`
    - `decisions/fresh-python-preprocessing.md`
    - `decisions/benchmark_3_resolution.md`
    - `concepts/interface-material-mutation-state-preservation.md`
    - `gotchas/benchmark-3-force-flag-diagnostic.md`
    - `gotchas/linear-system-reset-semantics.md`
    - `concepts/v1-release-qualification.md`

---

## 6. Document Map & Reference Links

| Category | Document | Description |
|---|---|---|
| **Architecture** | [Architecture Refactoring](docs/refactoring_architecture.md) | High-level subsystem architecture and design patterns |
| **Status & Releases** | [Current Status](docs/STATUS.md) | Supported boundary, release state, and open limitations |
| | [V1 Release Checklist](docs/release/v1-release-checklist.md) | Formal pre-release verification checklist |
| | [V1 Implementation Plan](docs/release/v1-implementation-plan.md) | Milestone scope and validation criteria |
| | [V1 Independent Review](docs/release/v1-independent-review.md) | External audit findings and tracking |
| **Guides** | [Standalone Analysis](docs/guides/standalone-analysis.md) | Running standalone Vert → Live Load analyses |
| | [Analysis Chains](docs/guides/analysis-chains.md) | Dependency execution and interface mutation |
| | [Preprocessing](docs/guides/preprocessing.md) | Mesh preparation, Quad contacts, and limitations |
| | [Modal Analysis](docs/guides/modal-analysis.md) | Modal solver execution, MAC checks, and parity |
| | [C# Parity Diagnostics](docs/guides/csharp-parity-diagnostics.md) | Diagnostic traces and UMFPACK backend configuration |
| **Benchmarks** | [Article Models Gate](docs/benchmarks/article-models-release-gate.md) | 14 canonical bridge benchmark models |
| | [Solver Strategy Methodology](docs/benchmarks/solver-strategy-methodology.md) | Strategy qualification protocol and evidence |
| | [Wall Overturning Benchmark](docs/benchmarks/wall_6_rows_benchmark.md) | Overturning wall benchmark and failure modes |
| | [Scour Optimization Profile](docs/benchmarks/scour-workflow-optimization-2026-08-20.md) | Multi-stage scour workflow profiling |
| **Theory & Safety** | [Nonlinear Convergence Safety](docs/nonlinear_convergence_safety.md) | Equilibrium auditing, convergence criteria, and work gotchas |
| **Reference** | [Documentation Policy](docs/DOCUMENTATION_POLICY.md) | Rules for authoring and maintaining documentation |
| | [C# Feature Matrix](docs/reference/v1-csharp-feature-matrix.md) | Granular C# vs Python parity mapping |
| | [Supported Features](docs/reference/v1-supported-features.md) | Granular scope of supported geometry, materials, and solver features |
| | [Data Model](docs/reference/data-model.md) | Stable entity definitions and schema fields |
| | [Glossary](docs/reference/glossary.md) | Domain terminology and symbol definitions |
| | [Porting Notes](docs/reference/porting-notes.md) | Technical implementation nuances from C# to Python |
