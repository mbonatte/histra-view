from __future__ import annotations

import math
import os
from typing import Any

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - optional acceleration
    njit = None

from histra.model.model import Model
from histra.solver.program import Program
from histra.solver.incremental_integrator import effective_tangent_alpha
from histra.solver.solution_algorithm import EquiSolnAlgo, _new_line_search
from histra.types.linear_system import LinearSolveError, LinearSystem


def _csharp_dot_python(left: np.ndarray, right: np.ndarray) -> float:
    """Scalar C# reduction used as the authoritative fallback/reference."""
    value = 0.0
    for index in range(left.size):
        value += float(left[index]) * float(right[index])
    return value


if njit is not None:
    _csharp_dot_impl = njit(cache=True, nogil=True)(_csharp_dot_python)
else:  # pragma: no cover
    _csharp_dot_impl = _csharp_dot_python


def _csharp_dot(left: np.ndarray, right: np.ndarray) -> float:
    """C# MatrixManager.Vector ``^`` reduction order, compiled when possible.

    Fast-math is deliberately disabled.  The loop remains scalar and
    left-associated, so this changes execution location only, not the
    floating-point reduction order used for C# parity.
    """
    if left.shape != right.shape:
        raise ValueError(f"dot shape mismatch: {left.shape} vs {right.shape}")
    return float(_csharp_dot_impl(left, right))


def _updates_tangent_each_iteration(an: Any) -> bool:
    """Match the exact C# NewtonLineSearch dispatch condition.

    The original condition accidentally omits StandardInitialInterpolatedLineSearch
    (and repeats StandardBisectionLineSearch), so that nominally standard method
    keeps the initial stiffness throughout the step.  Existing C# result databases
    therefore depend on this compatibility behavior.
    """
    return str(getattr(an, "method", "")) in {
        "StandardNewtonRaphson",
        "StandardBisectionLineSearch",
        "StandardRegulaFalsiLineSearch",
        "StandardSecantLineSearch",
    }


class NewtonLineSearch(EquiSolnAlgo):
    """Newton-Raphson with the C# line-search call sequence."""

    def __init__(self) -> None:
        super().__init__()
        self._scratch_residual0: np.ndarray | None = None
        self._scratch_dx0: np.ndarray | None = None
        self._scratch_direction: np.ndarray | None = None

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
        if self.the_line_search is None:
            self.the_line_search = _new_line_search(an)
        diagnostics = p.diagnostics

        self.the_test.start()
        if diagnostics is None:
            self.the_integrator.form_unbalance(p, model, an)
        else:
            with diagnostics.timed("residual_assembly"):
                self.the_integrator.form_unbalance(p, model, an)
        result = -1
        previous_error = 1.0
        error = 1.0
        last_error: float | None = None
        last_contraction: float = 1.0
        updates_tangent = _updates_tangent_each_iteration(an)
        csharp_line_search_compatibility = bool(
            getattr(an, "csharp_line_search_compatibility", True)
        )
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

        if (
            self._scratch_residual0 is None
            or self._scratch_residual0.shape != (ls.n,)
        ):
            self._scratch_residual0 = np.empty(ls.n, dtype=np.float64)
            self._scratch_dx0 = np.empty(ls.n, dtype=np.float64)
            self._scratch_direction = np.empty(ls.n, dtype=np.float64)

        residual0 = self._scratch_residual0
        dx0 = self._scratch_dx0
        line_search_direction = self._scratch_direction
        dot_fn = _csharp_dot if csharp_line_search_compatibility else np.dot

        while result == -1:
            alfa = effective_tangent_alpha(p, alfa)
            p.check_cancelled()
            # Match the C# NewtonLineSearch sequence: line-search points are
            # reached incrementally from the current trial point and no full
            # constitutive snapshot is taken for each Newton correction.
            # solve.py owns the complete pre-step checkpoint and restores it
            # after any failed/cancelled step (including ALS and ArcLength
            # retries), so an additional per-iteration copy is redundant.
            np.copyto(residual0, ls.b)
            current_it = self.the_test.current_iter

            refresh_tangent = False
            if updates_tangent and alfa != 0.0:
                if adaptive_tangent_refresh in {True, "adaptive"} or str(adaptive_tangent_refresh).lower() == "true":
                    cadence = tangent_refresh_cadence if (tangent_refresh_cadence is not None and tangent_refresh_cadence > 0) else 4
                    if current_it == 1 or (current_it % cadence == 0):
                        refresh_tangent = True
                    elif current_it >= 2 and last_contraction > 0.7:
                        refresh_tangent = True
                elif tangent_refresh_cadence is not None and tangent_refresh_cadence > 0:
                    if current_it == 1 or (current_it % tangent_refresh_cadence == 0):
                        refresh_tangent = True
                else:
                    refresh_tangent = True
            elif adaptive_tangent_refresh and not updates_tangent:
                if tangent_refresh_cadence is not None and tangent_refresh_cadence > 0:
                    if current_it == 1 or (current_it % tangent_refresh_cadence == 0):
                        refresh_tangent = True
                elif isinstance(adaptive_tangent_refresh, int) and adaptive_tangent_refresh > 0:
                    if current_it == 1 or (current_it % adaptive_tangent_refresh == 0):
                        refresh_tangent = True
                elif adaptive_tangent_refresh is True or str(adaptive_tangent_refresh).lower() in {"true", "adaptive"}:
                    if current_it == 1 and step > 1:
                        refresh_tangent = True
                    elif current_it >= 4 and (error > 0.7 * previous_error or current_it % 5 == 0):
                        refresh_tangent = True

            if refresh_tangent:
                refresh_alfa = alfa if (updates_tangent and alfa != 0.0) else 1.0
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
                p.log(f"Stiffness matrix is singular at step {step}: {exc}")
                return -3

            np.copyto(dx0, ls.x)
            self.the_line_search.new_step(p, ls)
            s0 = -float(dot_fn(dx0, residual0))

            if diagnostics is None:
                update_code = self.the_integrator.update(model, p, an)
            else:
                with diagnostics.timed("update_domain"):
                    update_code = self.the_integrator.update(model, p, an)
            if update_code < 0:
                return update_code

            # C# computes s0/s1 with the raw residual solve ``dx0``, but each
            # concrete LineSearch reads LS.X only *after* Integrator.Update.
            # LoadControl leaves the two vectors equal; ArcLength replaces
            # LS.X with delta_u_bar + delta_lambda * delta_u_hat.  Passing the
            # pre-update vector here made ArcLength line searches move along a
            # different direction from C# and could produce runaway load
            # factors after an otherwise safe predecessor stage.
            np.copyto(line_search_direction, ls.x)
            if not csharp_line_search_compatibility:
                # Production-safe ArcLength mode uses one physical search
                # direction for both endpoint projections and every trial.
                # The C# path projects s0/s1 with delta_u_bar while searching
                # along the combined constrained correction; retain that only
                # when compatibility was explicitly selected/defaulted.
                s0 = -float(dot_fn(line_search_direction, residual0))

            if diagnostics is None:
                self.the_integrator.form_unbalance(p, model, an)
            else:
                with diagnostics.timed("residual_assembly"):
                    self.the_integrator.form_unbalance(p, model, an)
            projection_direction = (
                dx0
                if csharp_line_search_compatibility
                else line_search_direction
            )
            s1 = -float(dot_fn(projection_direction, ls.b))
            if diagnostics is None:
                eta = self.the_line_search.search(
                    model, p, ls, self.the_integrator, an,
                    line_search_direction, s0, s1
                )
            else:
                with diagnostics.timed("line_search"):
                    eta = self.the_line_search.search(
                        model, p, ls, self.the_integrator, an,
                        line_search_direction, s0, s1
                    )
            if eta < 0.0:
                return -10

            # Search evaluates the residual at its final trial point and stores
            # eta*dx0 in LS.x for displacement/work convergence tests.
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
                    solver="NewtonLineSearch",
                    line_search=type(self.the_line_search).__name__,
                    eta=float(eta),
                    s0=float(s0),
                    s1=float(s1),
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
                return -4

            iteration = max(1, self.the_test.current_iter)
            estimate = max(iteration + 1.0, float(self.the_test.max_iter))
            if last_error is not None and error < last_error:
                estimate = max(iteration + 1.0, iteration / max(1e-6, 1.0 - error / max(last_error, 1e-30)))
            if last_error is not None and last_error > 0.0:
                last_contraction = error / last_error
            last_error = error
            previous_error = error

            if p.to_stop:
                return -4

        if result == -2:
            p.log(
                f"Line-search convergence failed at step={step}: "
                f"error={self.the_test.get_error():.6e}"
            )
        elif result == -3:
            p.log(
                f"Maximum displacement reached at step={step}: "
                f"max_u={p.max_u:.6e}"
            )
        return result
