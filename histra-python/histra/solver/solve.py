from __future__ import annotations

from pathlib import Path
import gc
import time
import warnings
from typing import Any, Callable

import numpy as np
from histra.model.model import Model
from histra.io.results_reader import ResultsStateError, find_results_path
from histra.solver.arc_length import ArcLength
from histra.solver.load_assembly import assemble_load_vector
from histra.solver.incremental_integrator import StaticIntegrator
from histra.solver.load_control import LoadControl
from histra.solver.model_manager import ModelManager, pdelta_enabled
from histra.solver.program import Program
from histra.solver.solution_algorithm import EquiSolnAlgo
from histra.solver.state_snapshot import SolverStateSnapshot
from histra.solver.restart import restore_committed_analysis_state
from histra.postprocessing import compute_total_reaction
from histra.preprocessing import inspect_solver_readiness, require_solver_ready
from histra.types.linear_system import LinearSolveError, LinearSystem
from histra.solver.diagnostics import DiagnosticOptions, create_diagnostics
from histra.solver.equilibrium import (
    UNSAFE_EQUILIBRIUM_EXIT_CODE,
    UnsafeEquilibriumWarning,
    applied_force_resultant,
    audit_static_equilibrium,
    normalize_equilibrium_policy,
)
from histra.solver.cancellation import (
    CANCELLED_EXIT_CODE,
    CancelCheck,
    SolverCancelled,
    exclusive_solver_access,
    raise_if_cancelled,
)

def solve_static_nonlinear(
    model: Model,
    analysis: Any,
    combination: int = 1,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
    results_path: str | Path | None = None,
    initial_displacement: np.ndarray | None = None,
    restart_from_current_state: bool = False,
    auto_prepare: bool = True,
    max_committed_steps: int | None = None,
    should_stop_after_commit: Callable[[dict[str, Any]], bool] | None = None,
    on_step_committed: Callable[[dict[str, Any], Any], None] | None = None,
    should_cancel: CancelCheck | None = None,
    diagnostics: DiagnosticOptions | str | Path | None = None,
    linear_solver_backend: str | None = None,
    linear_solver_precision: str = "fast",
    linear_solver_ordering: str | None = None,
    umfpack_irstep: int | None = None,
    adaptive_tangent_refresh: bool | int | None = None,
    tangent_refresh_cadence: int | None = None,
    equilibrium_policy: str = "warn",
    equilibrium_force_absolute_tolerance: float = 1.0e-3,
    equilibrium_force_relative_tolerance: float = 1.0e-5,
    equilibrium_residual_tolerance: float | None = None,
    performance_policy: str = "compiled",
) -> tuple[int, list[dict[str, Any]]]:
    """Execute a static nonlinear analysis with bounded snapshot GC overhead.

    ``should_stop_after_commit`` is an optional clean termination predicate. It
    receives each fully committed step dictionary and, when it returns true,
    stops the analysis with exit code zero while retaining that committed state.
    It is intended for path-dependent terminal conditions such as a descending
    ArcLength branch returning to zero load; it is never evaluated on trial or
    failed states.

    ``on_step_committed`` receives the same committed row plus the private
    analysis definition used by the solve. It may adjust continuation controls
    such as ``dr2`` for the next step without modifying an accepted state.

    Reversible Newton trials create thousands of short-lived state containers.
    CPython's cyclic collector can pause for minutes while scanning these fully
    reachable constitutive graphs even though reference counting already frees
    each prior snapshot.  Suspend cyclic collection only for the synchronous
    solve and restore the caller's GC setting on every exit.
    """
    numba_threads_before: int | None = None
    try:
        from histra.solver.hysteretic_runtime import current_numba_threads

        numba_threads_before = current_numba_threads()
        with exclusive_solver_access(should_cancel):
            gc_was_enabled = gc.isenabled()
            if gc_was_enabled:
                gc.disable()
            try:
                return _solve_static_nonlinear_impl(
                    model, analysis, combination, on_log=on_log,
                    on_progress=on_progress, results_path=results_path,
                    initial_displacement=initial_displacement,
                    restart_from_current_state=restart_from_current_state,
                    auto_prepare=auto_prepare,
                    max_committed_steps=max_committed_steps,
                    should_stop_after_commit=should_stop_after_commit,
                    on_step_committed=on_step_committed,
                    should_cancel=should_cancel,
                    diagnostics=diagnostics,
                    linear_solver_backend=linear_solver_backend,
                    linear_solver_precision=linear_solver_precision,
                    linear_solver_ordering=linear_solver_ordering,
                    umfpack_irstep=umfpack_irstep,
                    adaptive_tangent_refresh=adaptive_tangent_refresh,
                    tangent_refresh_cadence=tangent_refresh_cadence,
                    equilibrium_policy=equilibrium_policy,
                    equilibrium_force_absolute_tolerance=equilibrium_force_absolute_tolerance,
                    equilibrium_force_relative_tolerance=equilibrium_force_relative_tolerance,
                    equilibrium_residual_tolerance=equilibrium_residual_tolerance,
                    performance_policy=performance_policy,
                )
            finally:
                try:
                    runtime = ModelManager.hysteretic_batch_for(model)
                    if runtime is not None:
                        # Dense Numba state is authoritative during the solve. Publish it
                        # once for callers, chained analyses, and post-processing instead
                        # of rewriting >10k Python spring objects at every committed step.
                        runtime.sync_all_to_objects()
                finally:
                    from histra.solver.hysteretic_runtime import restore_numba_threads

                    restore_numba_threads(numba_threads_before)
                    if gc_was_enabled:
                        gc.enable()
    except SolverCancelled:
        if on_log is not None:
            on_log("Analysis cancelled before a load-step checkpoint was available.")
        return CANCELLED_EXIT_CODE, []

def _solve_static_nonlinear_impl(
    model: Model,
    analysis: Any,
    combination: int = 1,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
    results_path: str | Path | None = None,
    initial_displacement: np.ndarray | None = None,
    restart_from_current_state: bool = False,
    auto_prepare: bool = True,
    max_committed_steps: int | None = None,
    should_stop_after_commit: Callable[[dict[str, Any]], bool] | None = None,
    on_step_committed: Callable[[dict[str, Any], Any], None] | None = None,
    should_cancel: CancelCheck | None = None,
    diagnostics: DiagnosticOptions | str | Path | None = None,
    linear_solver_backend: str | None = None,
    linear_solver_precision: str = "fast",
    linear_solver_ordering: str | None = None,
    umfpack_irstep: int | None = None,
    adaptive_tangent_refresh: bool | int | None = None,
    tangent_refresh_cadence: int | None = None,
    equilibrium_policy: str = "warn",
    equilibrium_force_absolute_tolerance: float = 1.0e-3,
    equilibrium_force_relative_tolerance: float = 1.0e-5,
    equilibrium_residual_tolerance: float | None = None,
    performance_policy: str = "compiled",
) -> tuple[int, list[dict[str, Any]]]:
    """C#-ordered static nonlinear solver implementation."""
    raise_if_cancelled(should_cancel)
    if model.collections is None:
        raise ValueError("Model.collections is not initialized")

    if isinstance(analysis, (int, str)):
        if analysis in model.collections.analyses:
            analysis = model.collections.analyses[analysis]
        elif isinstance(analysis, str) and analysis.isdigit() and int(analysis) in model.collections.analyses:
            analysis = model.collections.analyses[int(analysis)]

    policy = str(performance_policy).strip().lower()
    if policy not in {"compiled", "diagnostic-scalar"}:
        raise ValueError(
            f"Unknown performance_policy {performance_policy!r}; "
            "expected 'compiled' or 'diagnostic-scalar'."
        )

    setup = _setup_nonlinear_analysis(
        model, analysis, combination,
        on_log=on_log, on_progress=on_progress, should_cancel=should_cancel,
        results_path=results_path, initial_displacement=initial_displacement,
        restart_from_current_state=restart_from_current_state,
        auto_prepare=auto_prepare, diagnostics=diagnostics,
        linear_solver_backend=linear_solver_backend,
        linear_solver_precision=linear_solver_precision,
        linear_solver_ordering=linear_solver_ordering,
        umfpack_irstep=umfpack_irstep,
        adaptive_tangent_refresh=adaptive_tangent_refresh,
        tangent_refresh_cadence=tangent_refresh_cadence,
        equilibrium_policy=equilibrium_policy,
        equilibrium_force_absolute_tolerance=equilibrium_force_absolute_tolerance,
        equilibrium_force_relative_tolerance=equilibrium_force_relative_tolerance,
        equilibrium_residual_tolerance=equilibrium_residual_tolerance,
        performance_policy=policy,
    )
    p = setup.p
    ls = setup.ls
    n = setup.n
    alfa = setup.alfa
    dof = setup.dof
    integrator = setup.integrator
    algorithm = setup.algorithm
    diagnostic_writer = setup.diagnostic_writer
    initial_reaction = setup.initial_reaction
    equilibrium_reference_load_factor = setup.equilibrium_reference_load_factor
    equilibrium_target_force = setup.equilibrium_target_force
    reference = setup.reference
    reference_displacement = setup.reference_displacement
    equilibrium_policy = setup.equilibrium_policy
    equilibrium_force_absolute_tolerance = setup.equilibrium_force_absolute_tolerance
    equilibrium_force_relative_tolerance = setup.equilibrium_force_relative_tolerance
    equilibrium_residual_tolerance = setup.equilibrium_residual_tolerance

    final_code, step_data, unsafe_equilibrium_steps, step = _execute_steps(
        model, analysis, combination,
        p=p, ls=ls, n=n, integrator=integrator, algorithm=algorithm,
        alfa=alfa, dof=dof, diagnostic_writer=diagnostic_writer,
        initial_reaction=initial_reaction,
        equilibrium_reference_load_factor=equilibrium_reference_load_factor,
        equilibrium_target_force=equilibrium_target_force,
        reference=reference,
        reference_displacement=reference_displacement,
        equilibrium_policy=equilibrium_policy,
        equilibrium_force_absolute_tolerance=equilibrium_force_absolute_tolerance,
        equilibrium_force_relative_tolerance=equilibrium_force_relative_tolerance,
        equilibrium_residual_tolerance=equilibrium_residual_tolerance,
        on_step_committed=on_step_committed,
        should_stop_after_commit=should_stop_after_commit,
        max_committed_steps=max_committed_steps,
    )
    if final_code == 0:
        p.log("Analysis executed and completed" if step else "Analysis not executed")
    else:
        p.log("Analysis executed but not completed")
    if unsafe_equilibrium_steps:
        p.log(
            f"EQUILIBRIUM SAFETY SUMMARY: {unsafe_equilibrium_steps} candidate "
            f"step(s) failed the independent audit (policy={equilibrium_policy})."
        )
    if diagnostic_writer is not None:
        diagnostic_writer.emit(
            "analysis_end",
            exit_code=final_code,
            committed_steps=sum(1 for row in step_data if row.get("status") == "OK"),
            attempted_steps=len(step_data),
            unsafe_equilibrium_steps=unsafe_equilibrium_steps,
            equilibrium_policy=equilibrium_policy,
        )
        diagnostic_writer.close()
    return final_code, step_data


# Compatibility re-exports: histra.solver.__init__ and tests import these
# private helpers from this facade by identity.
from histra.solver.nonlinear_setup import (  # noqa: E402
    _NonlinearSetup,
    _set_initial_state,
    _setup_nonlinear_analysis,
)
from histra.solver.nonlinear_step import (  # noqa: E402
    _als_loop,
    _commit_state,
    _execute_steps,
    _is_load_control,
)
