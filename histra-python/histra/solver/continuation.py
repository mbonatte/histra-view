"""Continuation controls for the static nonlinear analysis.

Automatic load-step reduction (ALS) following the original C# sequence, the
load-control predicate and the shared element/state commit helper used by the
step executor and the ALS sub-stepping path.

ALS always restarts from an exact pre-step snapshot: this restores external
loads, pseudo-time, all local element values and every trial/committed spring
field before any reduced increment is applied.
"""
from __future__ import annotations

import time
from typing import Any

from histra.model.model import Model
from histra.solver.load_control import LoadControl
from histra.solver.incremental_integrator import StaticIntegrator
from histra.solver.model_manager import ModelManager
from histra.solver.program import Program
from histra.solver.solution_algorithm import EquiSolnAlgo
from histra.solver.state_snapshot import SolverStateSnapshot
from histra.types.linear_system import LinearSystem


def _is_load_control(an: Any) -> bool:
    return "ArcLength" not in str(getattr(an, "integration_method", "LoadControl"))


def _domain_change_requires_tangent_refresh(an: Any) -> bool:
    """Match the C# domain-change stiffness refresh policy.

    ``StaticNonLinearAnalysis`` only calls ``UpdateK`` at a load-function
    segment boundary for Modified methods.  Standard methods retain the
    matrix/factorization produced by their solution algorithm.  Reassembling
    the tangent unconditionally changes the next arc-length predictor and can
    select a different equilibrium branch.
    """

    return "modified" in str(getattr(an, "method", "")).casefold()



def _commit_state(model: Model, ls: LinearSystem) -> None:
    runtime = ModelManager.hysteretic_batch_for(model)
    if runtime is not None:
        runtime.commit()
    for collection_name in ("quads", "interfaces"):
        for element in getattr(model.collections, collection_name).values():
            element.commit(ls)


def _als_loop(
    p: Program,
    ls: LinearSystem,
    model: Model,
    an: Any,
    combination: int,
    step: int,
    alfa: float,
    integrator: StaticIntegrator,
    algorithm: EquiSolnAlgo,
    step_snapshot: SolverStateSnapshot,
) -> int:
    """Automatic load-step reduction following the original C# sequence."""
    if not isinstance(integrator, LoadControl):
        return -2
    original_increment = integrator.incr_mult
    original_step_dt = integrator._step_dt
    factor = max(2, int(getattr(an, "load_factor_als", 2)))
    max_reductions = max(1, int(getattr(an, "max_number_als", 5)))

    # Start ALS from an exact pre-step snapshot.  This restores external loads,
    # pseudo-time, all local element values, and every trial/committed spring field.
    restore_started = time.perf_counter()
    step_snapshot.restore()
    if p.diagnostics is not None:
        p.diagnostics.add_timing("restore", time.perf_counter() - restore_started)
        p.diagnostics.emit("restore", step=step, reason="als_start")

    completed = 0.0
    sub_increment = original_increment / factor
    reduction = 0
    while abs(original_increment - completed) > 1e-12 and reduction <= max_reductions:
        p.check_cancelled()
        remaining = original_increment - completed
        direction = 1.0 if remaining >= 0.0 else -1.0
        trial_increment = direction * min(abs(sub_increment), abs(remaining))
        p.log(
            f">>> Automatic step reduction ({reduction + 1}): "
            f"LoadIncrement={trial_increment:.6g}"
        )
        snapshot_started = time.perf_counter()
        substep_snapshot = SolverStateSnapshot.capture(
            model, p, ls, integrator, algorithm.the_test, algorithm.the_line_search
        )
        if p.diagnostics is not None:
            p.diagnostics.add_timing("snapshot", time.perf_counter() - snapshot_started)
            p.diagnostics.emit(
                "als_substep_start",
                step=step,
                reduction=reduction + 1,
                trial_increment=float(trial_increment),
                completed_increment=float(completed),
            )
        integrator.new_step_with_incr(
            p, model, ls, an, combination, step, trial_increment
        )
        p.check_cancelled()
        result = algorithm.solve_current_step(
            p, ls, model, an, combination, step, alfa
        )
        p.check_cancelled()
        if result >= 0:
            commit_started = time.perf_counter()
            _commit_state(model, ls)
            if p.diagnostics is not None:
                p.diagnostics.add_timing("commit", time.perf_counter() - commit_started)
                p.diagnostics.emit(
                    "als_substep_commit",
                    step=step,
                    reduction=reduction + 1,
                    trial_increment=float(trial_increment),
                )
            if integrator.u_committed is not None and integrator.u is not None:
                integrator.u_committed[:] = integrator.u
            completed += trial_increment
            continue
        # Restore the exact last-successful substep checkpoint.
        restore_started = time.perf_counter()
        substep_snapshot.restore()
        if p.diagnostics is not None:
            p.diagnostics.add_timing("restore", time.perf_counter() - restore_started)
            p.diagnostics.emit(
                "restore",
                step=step,
                reason="als_substep_failure",
                reduction=reduction + 1,
            )
        reduction += 1
        if reduction > max_reductions:
            restore_started = time.perf_counter()
            step_snapshot.restore()
            if p.diagnostics is not None:
                p.diagnostics.add_timing("restore", time.perf_counter() - restore_started)
                p.diagnostics.emit("restore", step=step, reason="als_exhausted")
            return -2
        sub_increment /= factor

    # The pre-step snapshot contains the previous step's dt. ALS restores it
    # while retrying loads, but a successful full increment must advance time
    # by the interval selected for this step, exactly once at outer commit.
    integrator._step_dt = original_step_dt
    integrator.incr_mult = original_increment
    return 0
