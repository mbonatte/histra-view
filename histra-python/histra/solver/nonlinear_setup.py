"""C#-ordered setup phase for the static nonlinear analysis.

Runs once per analysis, before any Newton correction: equilibrium-policy
validation, readiness/preparation, virgin/restart/chained initial state
selection (C# ``ModelManager.SetStatus`` / ``SetFextEqualToFint`` order),
hysteretic runtime configuration, load assembly, the initial tangent with the
C# lability check, and the step-0 reference reaction/graph. The returned
:data:`_NonlinearSetup` is immutable input for the step executor.

The operation order in this module is behavior (C#
``StaticNonLinearAnalysis`` / ``ModelManager``); do not reorder independent
looking calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np

from histra.io.results_reader import ResultsStateError, find_results_path
from histra.model.model import Model
from histra.postprocessing import compute_total_reaction
from histra.preprocessing import inspect_solver_readiness, require_solver_ready
from histra.solver.cancellation import CancelCheck, raise_if_cancelled
from histra.solver.diagnostics import DiagnosticOptions, create_diagnostics
from histra.solver.equilibrium import (
    applied_force_resultant,
    normalize_equilibrium_policy,
)
from histra.solver.load_assembly import assemble_load_vector  # noqa: F401 (setup contract)
from histra.solver.model_manager import ModelManager, pdelta_enabled
from histra.solver.program import Program
from histra.solver.restart import restore_committed_analysis_state
from histra.solver.solution_algorithm import EquiSolnAlgo
from histra.types.linear_system import LinearSystem


@dataclass
class _NonlinearSetup:
    p: Program
    ls: LinearSystem
    n: int
    alfa: float
    dof: int
    integrator: Any
    algorithm: EquiSolnAlgo
    diagnostic_writer: Any
    initial_reaction: Any
    equilibrium_reference_load_factor: float
    equilibrium_target_force: Any
    reference: list
    reference_displacement: float
    equilibrium_policy: str
    equilibrium_force_absolute_tolerance: float
    equilibrium_force_relative_tolerance: float
    equilibrium_residual_tolerance: float


def _setup_nonlinear_analysis(
    model: Model,
    analysis: Any,
    combination: int = 1,
    *,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: CancelCheck | None = None,
    results_path: str | Path | None = None,
    initial_displacement: np.ndarray | None = None,
    restart_from_current_state: bool = False,
    auto_prepare: bool = True,
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
) -> _NonlinearSetup:
    """Validate policy, prepare the model and build the C#-ordered initial state."""
    if isinstance(analysis, (int, str)) and model.collections is not None:
        if analysis in model.collections.analyses:
            analysis = model.collections.analyses[analysis]
        elif isinstance(analysis, str) and analysis.isdigit() and int(analysis) in model.collections.analyses:
            analysis = model.collections.analyses[int(analysis)]
    equilibrium_policy = normalize_equilibrium_policy(equilibrium_policy)
    equilibrium_force_absolute_tolerance = float(
        equilibrium_force_absolute_tolerance
    )
    equilibrium_force_relative_tolerance = float(
        equilibrium_force_relative_tolerance
    )
    if equilibrium_force_absolute_tolerance < 0.0:
        raise ValueError("equilibrium_force_absolute_tolerance must be non-negative")
    if equilibrium_force_relative_tolerance < 0.0:
        raise ValueError("equilibrium_force_relative_tolerance must be non-negative")
    if equilibrium_residual_tolerance is None:
        equilibrium_residual_tolerance = float(
            getattr(analysis, "convergence_tolerance", 1.0e-6)
        )
    equilibrium_residual_tolerance = float(equilibrium_residual_tolerance)
    if equilibrium_residual_tolerance < 0.0:
        raise ValueError("equilibrium_residual_tolerance must be non-negative")
    readiness = inspect_solver_readiness(model)
    raise_if_cancelled(should_cancel)
    requires_python_preparation = bool(
        getattr(model, "requires_python_preparation", False)
    )
    if requires_python_preparation and results_path is None and not restart_from_current_state:
        if auto_prepare:
            if on_log is not None:
                on_log(
                    "Preparing brand-new Python computational model from HRX geometry/materials "
                    f"({readiness.quad_count} Quads)..."
                )
            prep_started = time.perf_counter()
            prep = ModelManager.prepare_model(model, force=True)
            prepare_model_seconds = time.perf_counter() - prep_started
            raise_if_cancelled(should_cancel)
            if on_log is not None:
                on_log(
                    "PrepareModel completed: "
                    f"GDL={prep.gdl}, interfaces={prep.interfaces}, "
                    f"springs={prep.quad_springs + prep.transverse_springs + prep.sliding_springs + prep.out_of_plane_springs}"
                )
        else:
            from histra.preprocessing.errors import ModelPreparationError

            raise ModelPreparationError(
                "Cannot solve model using serialized HRX mesh. Serialized HRX interfaces "
                "and springs are reference-only for testing/comparison; you must prepare "
                "a brand new Python computational model before solving (auto_prepare=True or ModelManager.prepare_model)."
            )
    elif not readiness.is_ready and auto_prepare:
        if on_log is not None:
            on_log(
                "Preparing Python computational model from HRX geometry/materials "
                f"({readiness.quad_count} Quads)..."
            )
        prep_started = time.perf_counter()
        prep = ModelManager.prepare_model(model, force=True)
        prepare_model_seconds = time.perf_counter() - prep_started
        raise_if_cancelled(should_cancel)
        if on_log is not None:
            on_log(
                "PrepareModel completed: "
                f"GDL={prep.gdl}, interfaces={prep.interfaces}, "
                f"springs={prep.quad_springs + prep.transverse_springs + prep.sliding_springs + prep.out_of_plane_springs}"
            )
    require_solver_ready(model)
    raise_if_cancelled(should_cancel)

    policy = str(performance_policy).strip().lower()
    if policy == "compiled":
        from histra.solver.backend_coverage import inspect_solver_backend

        backend = inspect_solver_backend(
            model, [analysis], linear_solver_backend=linear_solver_backend
        )
        backend.require_compiled()
    elif policy == "diagnostic-scalar" and on_log is not None:
        on_log(
            "PERFORMANCE POLICY NOTICE: Running in 'diagnostic-scalar' mode. "
            "This unmanaged/scalar execution is for diagnostics only and cannot support production release acceptance."
        )

    n = int(model.gdl)
    diagnostic_writer = create_diagnostics(diagnostics, model)
    p = Program(
        gdl=n, on_log=on_log, on_progress=on_progress, should_cancel=should_cancel,
        diagnostics=diagnostic_writer,
    )
    effective_precision = getattr(
        analysis, "linear_solver_precision", linear_solver_precision
    )
    effective_irstep = getattr(analysis, "umfpack_irstep", umfpack_irstep)
    effective_ordering = getattr(
        analysis, "linear_solver_ordering", linear_solver_ordering
    )
    ls = LinearSystem(
        n,
        backend=linear_solver_backend,
        precision=effective_precision,
        irstep=effective_irstep,
        ordering=effective_ordering,
    )
    if adaptive_tangent_refresh is not None and not hasattr(
        analysis, "adaptive_tangent_refresh"
    ):
        setattr(analysis, "adaptive_tangent_refresh", adaptive_tangent_refresh)
    if tangent_refresh_cadence is not None and not hasattr(
        analysis, "tangent_refresh_cadence"
    ):
        setattr(analysis, "tangent_refresh_cadence", tangent_refresh_cadence)
    p.ls = ls
    p.u = np.zeros(n)
    p.v = np.zeros(n)
    # C# ModelManager.SetStatus/CommonOperations.SetInitial initializes a
    # virgin analysis independently of any solved state serialized in the HRX.
    # Without this reset, the first Python increment is added to the saved local
    # element displacements, producing a completely different residual path.
    initial_analysis_key = int(getattr(analysis, "initial_analysis_key", -100))
    initial_external_load = np.zeros(n)
    if initial_analysis_key < 0:
        if restart_from_current_state or initial_displacement is not None:
            raise ValueError(
                "A virgin analysis cannot restart from an in-memory committed state."
            )
        ModelManager.clear_hysteretic_batch()
        _set_initial_state(model, p.u, p.v, ls)
        ModelManager.prepare_hysteretic_batch(model, rebuild=True)
    elif restart_from_current_state:
        if initial_displacement is None:
            raise ValueError(
                "restart_from_current_state=True requires initial_displacement."
            )
        restored_u = np.asarray(initial_displacement, dtype=float)
        if restored_u.shape != (n,):
            raise ValueError(
                f"Expected initial_displacement shape ({n},), got {restored_u.shape}."
            )
        if not np.all(np.isfinite(restored_u)):
            raise ValueError("initial_displacement contains NaN or infinite values.")
        p.u[:] = restored_u
        p.v.fill(0.0)
        ls.set_zero_displacement()
        p.log(
            f"Using in-memory committed state from analysis {initial_analysis_key}: "
            f"{n} DOFs"
        )
        # The model's Quad/Interface/spring objects are already at the prior
        # analysis' last committed state. Reuse (or build) the dense hysteretic
        # runtime from those committed objects before evaluating equilibrium.
        ModelManager.prepare_hysteretic_batch(model, rebuild=False)
        # Reproduce C# SetFextEqualToFint so the new analysis starts from exact
        # equilibrium without a .Results DB.
        ModelManager.get_resisting_force(model, ls)
        initial_external_load = -ls.b.copy()
        if pdelta_enabled(getattr(analysis, "pdelta_effect", None)) and ModelManager._pq is not None:
            initial_external_load -= ModelManager._pq
        p.log(
            "Restored chained baseline load from in-memory resisting forces: "
            f"norm={np.linalg.norm(initial_external_load):.6g}"
        )
    else:
        initial_combination = int(
            getattr(analysis, "initial_combination_analysis_key", combination)
        )
        resolved_results = Path(results_path) if results_path is not None else (
            find_results_path(model.source_path) if model.source_path else None
        )
        if resolved_results is None:
            raise ResultsStateError(
                "Chained analysis requires a C# .Results database. Pass results_path=... "
                "or place a sibling .Results file next to the HRX model."
            )
        ModelManager.clear_hysteretic_batch()
        restart = restore_committed_analysis_state(
            model, resolved_results, initial_analysis_key, initial_combination,
            p.u, p.v, ls,
        )
        ModelManager.prepare_hysteretic_batch(model, rebuild=True)
        p.log(
            f"Restored analysis {restart.analysis_key}, combination {restart.combination}, "
            f"step {restart.step}: {restart.dof_count} DOFs, "
            f"{restart.spring_count} complete spring states"
        )
        # C# does not reconstruct the predecessor load combination here.
        # After restoring the committed element state it calls
        # SetFextEqualToFint(), making the chained analysis start from an
        # exactly self-equilibrated baseline even when the predecessor was
        # committed by a work criterion with a non-zero residual.
        ModelManager.get_resisting_force(model, ls)
        initial_external_load = -ls.b.copy()
        if pdelta_enabled(getattr(analysis, "pdelta_effect", None)) and ModelManager._pq is not None:
            initial_external_load -= ModelManager._pq
        p.log(
            f"Restored chained baseline load from committed resisting forces: "
            f"norm={np.linalg.norm(initial_external_load):.6g}"
        )
    runtime = ModelManager.hysteretic_batch_for(model)
    if policy == "compiled":
        if runtime is None:
            from histra.solver.backend_coverage import CompiledBackendRequiredError

            err = ModelManager._hysteretic_batch_error or "runtime construction failed"
            raise CompiledBackendRequiredError(
                f"Compiled production execution is required for '{model.source_path or 'model'}', "
                f"but runtime construction failed at execution boundary: {err}"
            )
        from histra.solver.backend_coverage import inspect_solver_backend

        backend = inspect_solver_backend(
            model, [analysis], linear_solver_backend=linear_solver_backend
        )
        backend.require_compiled()
    if runtime is not None:
        selected_threads = runtime.configure_numba_threads()
        if selected_threads is not None:
            p.log(
                "Compiled nonlinear kernels: "
                f"{selected_threads} Numba worker(s) for "
                f"{len(runtime.records)} interfaces and {len(runtime.springs)} springs"
            )
    incoming_pq = ModelManager._pq.copy() if ModelManager._pq is not None else np.zeros(n)
    ModelManager._ptarget = np.zeros(n)
    ModelManager._fext = initial_external_load.copy()
    ModelManager._pq = np.zeros(n)
    ModelManager._pq_prev = incoming_pq
    ModelManager._u_total = p.u

    if getattr(analysis, "load_function_key", 0) in model.collections.load_functions:
        analysis.load_function = model.collections.load_functions[analysis.load_function_key]

    p.check_cancelled()
    load_started = time.perf_counter()
    ModelManager.assemble_load(model, ls, getattr(analysis, "key", None), combination)
    load_seconds = time.perf_counter() - load_started
    if diagnostic_writer is not None:
        diagnostic_writer.add_timing("load_vector_assembly", load_seconds)
        if "prepare_model_seconds" in locals():
            diagnostic_writer.add_timing("prepare_model", prepare_model_seconds)
    p.check_cancelled()
    algorithm = EquiSolnAlgo.new_equi_soln_algo(analysis, combination)
    integrator = algorithm.the_integrator
    assert integrator is not None
    integrator.u = p.u
    integrator.v = p.v
    integrator.u_committed = p.u.copy()
    alfa = 0.0 if "Modified" in str(getattr(analysis, "method", "")) else 1.0
    # C# PrepareModelForAnalysis calls PrepareK(..., alfa=0) for every static
    # non-modal analysis, regardless of whether the later Newton method is
    # labelled Standard or Modified.  Standard methods may replace this matrix
    # inside their iteration loop; StandardInitialInterpolatedLineSearch is
    # accidentally omitted from that loop and therefore relies on this exact
    # initial-stiffness matrix for the whole step.
    if diagnostic_writer is None:
        integrator.update_k(p, model, 0.0)
    else:
        with diagnostic_writer.timed("tangent_assembly"):
            integrator.update_k(p, model, 0.0)

    # C# ModelManager.PrepareK() does not stop after assembling and
    # factorizing the initial tangent.  It clears the load vector, sets
    # B[0] = 1, and calls Solve() once as a lability check before assembling
    # the physical analysis load.  Besides detecting a singular system at the
    # same point, this establishes the native UMFPACK numeric/solve state in
    # the same call order as the reference solver.
    stiffness_check_rhs = np.zeros(n, dtype=np.float64)
    if n:
        stiffness_check_rhs[0] = 1.0
        ls.solve(stiffness_check_rhs)
        ls.set_zero_displacement()
    integrator.domain_changed(p, model, n)
    p.current_load_factor = integrator.mult
    equilibrium_reference_load_factor = float(integrator.mult)
    equilibrium_target_force = applied_force_resultant(model)
    dof = ModelManager.get_dof_for_max_displacement(p, model, analysis)
    # C# StaticNonLinearAnalysis computes the step-0 ReactionSum before the
    # initial GetValueGraphAnalysis call, so the reference graph force is the
    # projected reaction of the initial (restored or zero) state.
    initial_reaction = compute_total_reaction(model)
    reference_displ: list[float] = []
    reference = p.get_value_graph_analysis(
        model.collections, analysis, dof, initial_reaction, reference_displ
    )
    reference_displacement = reference_displ[0] if reference_displ else 0.0

    if diagnostic_writer is not None:
        runtime = ModelManager.hysteretic_batch_for(model)
        diagnostic_writer.emit(
            "analysis_start",
            analysis_key=int(getattr(analysis, "key", -1)),
            analysis_name=str(getattr(analysis, "name", "")),
            combination=int(combination),
            initial_analysis_key=initial_analysis_key,
            integration_method=str(getattr(analysis, "integration_method", "")),
            nonlinear_method=str(getattr(analysis, "method", "")),
            linear_solver_backend=ls.backend,
            requested_linear_solver_backend=ls.requested_backend,
            dof_count=n,
            stiffness_nnz=int(ls.k.nnz),
            stiffness_frobenius_norm=float(np.linalg.norm(ls.k.data)),
            target_load_norm=float(np.linalg.norm(ModelManager._ptarget)),
            external_load_norm=float(np.linalg.norm(ModelManager._fext)),
            equilibrium_policy=equilibrium_policy,
            equilibrium_force_absolute_tolerance=equilibrium_force_absolute_tolerance,
            equilibrium_force_relative_tolerance=equilibrium_force_relative_tolerance,
            equilibrium_residual_tolerance=equilibrium_residual_tolerance,
            equilibrium_target_force=equilibrium_target_force.tolist(),
            managed_transverse_springs=0 if runtime is None else len(runtime.springs),
            managed_coulomb_springs=0 if runtime is None else len(runtime.coulomb_springs),
            managed_quad_records=0 if runtime is None else len(runtime.quad_records),
            **diagnostic_writer.integrator_metrics(integrator),
        )


    return _NonlinearSetup(
        p=p,
        ls=ls,
        n=n,
        alfa=alfa,
        dof=dof,
        integrator=integrator,
        algorithm=algorithm,
        diagnostic_writer=diagnostic_writer,
        initial_reaction=initial_reaction,
        equilibrium_reference_load_factor=equilibrium_reference_load_factor,
        equilibrium_target_force=equilibrium_target_force,
        reference=reference,
        reference_displacement=reference_displacement,
        equilibrium_policy=equilibrium_policy,
        equilibrium_force_absolute_tolerance=equilibrium_force_absolute_tolerance,
        equilibrium_force_relative_tolerance=equilibrium_force_relative_tolerance,
        equilibrium_residual_tolerance=equilibrium_residual_tolerance,
    )


def _set_initial_state(
    model: Model, u: np.ndarray, v: np.ndarray, ls: LinearSystem
) -> None:
    """Reset the supported model entities to the C# virgin state.
    This is the translated subset of ``CommonOperations.SetInitial`` for the
    element types implemented by this Python package.  Applied loads stored in
    ``Quad.status.p`` are deliberately preserved; they are regenerated later by
    ``ModelManager.assemble_load``.
    """
    ls.set_zero_displacement()
    u.fill(0.0)
    v.fill(0.0)
    for quad in model.collections.quads.values():
        quad.status.u[:] = [0.0] * len(quad.status.u)
        quad.status.f = 0.0
        if quad.spring is not None:
            quad.spring.k_tang = quad.spring.k
            quad.spring.revert_to_start()
            quad.spring.revert_to_last_commit()
    for intf in model.collections.interfaces.values():
        state = intf.status
        state.evd = 0.0
        state.u[:] = [0.0] * len(state.u)
        state.v[:] = [0.0] * len(state.v)
        state.fd[:] = [0.0] * len(state.fd)
        state.forces = (0.0, 0.0, 0.0)
        state.bending_moments = (0.0, 0.0, 0.0)
        state.normal_increment = 0.0
        state.committed_normal_force = 0.0
        state.max_spring_displacement = 0.0
        intf.f[:] = [0.0] * len(intf.f)
        for spring_group in (
            intf.trasv_1, intf.trasv_2, intf.slid, intf.slid_out_plan
        ):
            for spring in spring_group:
                if spring is None:
                    continue
                spring.revert_to_start()
                spring.revert_to_last_commit()
