from __future__ import annotations

import math
import os
from typing import Any

from histra.model.model import Model
from histra.solver.program import Program
from histra.solver.incremental_integrator import effective_tangent_alpha
from histra.solver.solution_algorithm import EquiSolnAlgo
from histra.solver.state_snapshot import SolverStateSnapshot
from histra.types.linear_system import LinearSolveError, LinearSystem


# Small snapshots copy faster than validating reusable buffers. Keep validation
# intact for large snapshots; this threshold only selects the storage strategy.
_BATCH_SNAPSHOT_REUSE_MIN_BYTES = 1 << 20


def _is_standard_method(an: Any) -> bool:
    return str(getattr(an, "method", "")).startswith("Standard")


def _resolve_tangent_refresh_config(
    an: Any,
) -> tuple[bool | int, int | None]:
    """Resolve adaptive tangent refresh and cadence settings from analysis or env."""
    adaptive_tangent_refresh = getattr(an, "adaptive_tangent_refresh", None)
    if adaptive_tangent_refresh is None:
        env_val = os.environ.get("HISTRA_ADAPTIVE_TANGENT_REFRESH", "").strip().lower()
        if env_val in {"1", "true", "yes", "on", "adaptive"}:
            adaptive_tangent_refresh = True
        elif env_val in {"0", "false", "no", "off"}:
            adaptive_tangent_refresh = False
        elif env_val.isdigit():
            adaptive_tangent_refresh = int(env_val)
        else:
            adaptive_tangent_refresh = False

    tangent_refresh_cadence = getattr(an, "tangent_refresh_cadence", None)
    if tangent_refresh_cadence is None:
        env_cadence = os.environ.get("HISTRA_TANGENT_REFRESH_CADENCE")
        if env_cadence is not None and env_cadence.isdigit():
            tangent_refresh_cadence = int(env_cadence)
    return adaptive_tangent_refresh, tangent_refresh_cadence


def _should_refresh_tangent(
    *,
    is_standard: bool,
    alfa: float,
    adaptive_refresh: Any,
    cadence: int | None,
    current_it: int,
    step: int,
    error: float,
    previous_error: float,
) -> bool:
    """Evaluate whether the tangent stiffness matrix should be refreshed."""
    if is_standard and alfa != 0.0:
        return True
    if not adaptive_refresh or is_standard:
        return False
    if cadence is not None and cadence > 0:
        return current_it == 1 or (current_it % cadence == 0)
    if isinstance(adaptive_refresh, int) and adaptive_refresh > 0:
        return current_it == 1 or (current_it % adaptive_refresh == 0)
    if adaptive_refresh is True or str(adaptive_refresh).lower() in {"true", "adaptive"}:
        if current_it == 1 and step > 1:
            return True
        if current_it >= 4 and (error > 0.7 * previous_error or current_it % 5 == 0):
            return True
    return False


def _estimate_newton_progress(
    the_test: Any,
    iteration: int,
    error: float,
    previous_error: float,
) -> float:
    """Estimate remaining iterations and return normalized percentage progress."""
    if error < previous_error and previous_error > 0.0:
        reduction = max(error / previous_error, 1e-12)
        if reduction < 1.0 and error > 0.0:
            target_ratio = max(the_test.tolerance / error, 1e-300)
            remaining = max(1.0, abs(math.log(target_ratio) / math.log(reduction)))
        else:
            remaining = 1.0
        estimate = iteration + remaining
    else:
        estimate = max(iteration + 1.0, float(the_test.max_iter))
    return min(90.0, iteration / estimate * 100.0)


class NewtonRaphson(EquiSolnAlgo):
    """C#-aligned Newton-Raphson iteration loop."""

    def solve_current_step(
        self,
        p: Program,
        ls: LinearSystem,
        model: Model,
        an: Any,
        combination: int,
        step: int,
        alfa: float,
    ) -> int:
        del combination
        # solveCurrentStep receives alfa by value; UpdateK changes only this
        # call's local reference parameter, not the next step's argument.
        p.static_tangent_alpha = float(alfa)
        assert self.the_integrator is not None
        assert self.the_test is not None
        diagnostics = p.diagnostics

        if diagnostics is None:
            self.the_integrator.form_unbalance(p, model, an)
        else:
            with diagnostics.timed("residual_assembly"):
                self.the_integrator.form_unbalance(p, model, an)
        self.the_test.start()
        result = -1
        previous_error = 1.0
        error = 1.0
        is_standard = _is_standard_method(an)
        adaptive_tangent_refresh, tangent_refresh_cadence = (
            _resolve_tangent_refresh_config(an)
        )

        iteration_batch_state = None
        reuse_iteration_batch_buffers = None
        while result == -1:
            alfa = effective_tangent_alpha(p, alfa)
            p.check_cancelled()
            iteration_snapshot = SolverStateSnapshot.capture(
                model, p, ls, self.the_integrator, self.the_test, self.the_line_search,
                reuse_batch_state=iteration_batch_state,
            )
            if reuse_iteration_batch_buffers is None:
                buffers = iteration_snapshot.batch_state
                reuse_iteration_batch_buffers = (
                    buffers is not None
                    and sum(value.nbytes for value in buffers) >= _BATCH_SNAPSHOT_REUSE_MIN_BYTES
                )
            iteration_batch_state = (
                iteration_snapshot.batch_state if reuse_iteration_batch_buffers else None
            )
            current_it = self.the_test.current_iter

            refresh_tangent = _should_refresh_tangent(
                is_standard=is_standard,
                alfa=alfa,
                adaptive_refresh=adaptive_tangent_refresh,
                cadence=tangent_refresh_cadence,
                current_it=current_it,
                step=step,
                error=error,
                previous_error=previous_error,
            )

            if refresh_tangent:
                refresh_alfa = alfa if (is_standard and alfa != 0.0) else 1.0
                if diagnostics is None:
                    self.the_integrator.update_k(p, model, refresh_alfa)
                else:
                    with diagnostics.timed("tangent_assembly"):
                        self.the_integrator.update_k(p, model, refresh_alfa)

            try:
                if diagnostics is None:
                    self.the_integrator.compute_increment(p, ls, model, an)
                else:
                    with diagnostics.timed("linear_solver"):
                        self.the_integrator.compute_increment(p, ls, model, an)
            except LinearSolveError as exc:
                iteration_snapshot.restore()
                p.log(f"Stiffness matrix is singular at step {step}: {exc}")
                return -3

            if diagnostics is None:
                update_code = self.the_integrator.update(model, p, an)
            else:
                with diagnostics.timed("update_domain"):
                    update_code = self.the_integrator.update(model, p, an)
            if update_code < 0:
                iteration_snapshot.restore()
                return update_code

            if diagnostics is None:
                self.the_integrator.form_unbalance(p, model, an)
            else:
                with diagnostics.timed("residual_assembly"):
                    self.the_integrator.form_unbalance(p, model, an)
            result = self.the_test.test(p, model, ls)
            error = self.the_test.get_error()
            if diagnostics is not None:
                tested_iteration = max(
                    1,
                    int(self.the_test.current_iter)
                    - (1 if result in {-1, -2} else 0),
                )
                captured = diagnostics.capture_state(
                    label="newton",
                    step=step,
                    iteration=tested_iteration,
                    program=p,
                    model=model,
                )
                diagnostics.emit(
                    "iteration",
                    step=step,
                    iteration=tested_iteration,
                    solver="NewtonRaphson",
                    convergence_error=float(error),
                    convergence_tolerance=float(self.the_test.tolerance),
                    convergence_criterion=str(self.the_test.criterion),
                    convergence_result=int(result),
                    convergence_reason=diagnostics.result_reason(result, self.the_test, p),
                    vector_snapshot=captured,
                    **diagnostics.integrator_metrics(self.the_integrator),
                    **diagnostics.vector_metrics(ls),
                    **diagnostics.spring_metrics(model),
                )
            if not math.isfinite(error):
                p.log(
                    f"Non-finite convergence error at step={step}, "
                    f"iteration={self.the_test.current_iter}"
                )
                iteration_snapshot.restore()
                return -4

            iteration = max(1, self.the_test.current_iter)
            p.progress(
                _estimate_newton_progress(
                    self.the_test, iteration, error, previous_error
                )
            )
            previous_error = error

            if p.to_stop:
                iteration_snapshot.restore()
                return -4

        if result == -2:
            p.log(
                f"Convergence failed at step={step}: max iterations "
                f"({self.the_test.max_iter}), error={self.the_test.get_error():.6e}"
            )
        elif result == -3:
            p.log(
                f"Maximum displacement reached at step={step}: "
                f"max_u={p.max_u:.6e}, limit={self.the_test.max_u:.6e}"
            )
        return result
