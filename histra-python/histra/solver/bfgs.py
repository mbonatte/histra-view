from __future__ import annotations

import math
import os
from typing import Any

import numpy as np

from histra.model.model import Model
from histra.solver.line_search import (
    LineSearch,
    _csharp_dot,
)
from histra.solver.program import Program
from histra.solver.solution_algorithm import EquiSolnAlgo, _new_line_search
from histra.types.linear_system import LinearSolveError, LinearSystem


class BFGSSolnAlgo(EquiSolnAlgo):
    """Quasi-Newton (BFGS) solution algorithm for Discrete Macro-Element systems.

    Implements the Matthies & Strang (1979) product form / two-loop recursion
    for large-scale nonlinear finite/discrete element equilibrium equations.
    The tangent stiffness matrix is factorized once at the start of a step
    (or upon curvature/stall detection). Subsequent iterations compute search
    directions via low-rank vector updates in O(m*N) time, eliminating repeated
    sparse matrix factorizations.
    """

    def __init__(self, max_history: int = 15) -> None:
        super().__init__()
        self.max_history = max(1, int(max_history))
        self._history: list[tuple[np.ndarray, np.ndarray, float]] = []
        self._scratch_residual0: np.ndarray | None = None
        self._scratch_dx0: np.ndarray | None = None
        self._scratch_direction: np.ndarray | None = None
        self._scratch_q: np.ndarray | None = None

    def clear_history(self) -> None:
        self._history.clear()

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
        error = 1.0
        previous_error = 1.0
        stalls = 0
        csharp_line_search_compatibility = bool(
            getattr(an, "csharp_line_search_compatibility", True)
        )
        dot_fn = _csharp_dot if csharp_line_search_compatibility else np.dot

        # Allocate reusable scratch vectors matching the active DOF count
        if (
            self._scratch_residual0 is None
            or self._scratch_residual0.shape != (ls.n,)
        ):
            self._scratch_residual0 = np.empty(ls.n, dtype=np.float64)
            self._scratch_dx0 = np.empty(ls.n, dtype=np.float64)
            self._scratch_direction = np.empty(ls.n, dtype=np.float64)
            self._scratch_q = np.empty(ls.n, dtype=np.float64)

        residual0 = self._scratch_residual0
        dx0 = self._scratch_dx0
        line_search_direction = self._scratch_direction
        q_vec = self._scratch_q

        # Initial tangent update for the current step (factorizes K_0 once)
        self.clear_history()
        refresh_alfa = alfa if alfa != 0.0 else 1.0
        if diagnostics is None:
            self.the_integrator.update_k(p, model, refresh_alfa)
        else:
            with diagnostics.timed("tangent_assembly"):
                self.the_integrator.update_k(p, model, refresh_alfa)

        while result == -1:
            p.check_cancelled()
            current_it = self.the_test.current_iter
            np.copyto(residual0, ls.b)

            # Compute search direction using BFGS two-loop recursion
            if len(self._history) == 0:
                # Base solve: K_0 * dx0 = residual0
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
            else:
                # Matthies-Strang two-loop recursion
                np.copyto(q_vec, residual0)
                alphas: list[float] = []
                for s_j, y_j, rho_j in reversed(self._history):
                    alpha_j = rho_j * float(dot_fn(s_j, q_vec))
                    q_vec -= alpha_j * y_j
                    alphas.append(alpha_j)

                # Direct solve with base factorized K_0 (fast, ~26 ms)
                try:
                    if diagnostics is None:
                        ls.solve(q_vec)
                    else:
                        with diagnostics.timed("linear_solver"):
                            ls.solve(q_vec)
                except LinearSolveError as exc:
                    p.log(f"Linear solve failed during BFGS iteration at step {step}: {exc}")
                    return -3

                r_vec = np.copy(ls.x)
                for (s_j, y_j, rho_j), alpha_j in zip(self._history, reversed(alphas)):
                    beta = rho_j * float(dot_fn(y_j, r_vec))
                    r_vec += s_j * (alpha_j - beta)

                np.copyto(dx0, r_vec)
                ls.set_x_vector(dx0)

            self.the_line_search.new_step(p, ls)
            s0 = -float(dot_fn(dx0, residual0))

            # Safeguard: if BFGS search direction is not a descent direction,
            # refresh the base tangent K_0 and clear history
            if s0 > 0.0 and len(self._history) > 0:
                self.clear_history()
                if diagnostics is None:
                    self.the_integrator.update_k(p, model, refresh_alfa)
                    self.the_integrator.compute_increment(p, ls, model, an)
                else:
                    with diagnostics.timed("tangent_assembly"):
                        self.the_integrator.update_k(p, model, refresh_alfa)
                    with diagnostics.timed("linear_solver"):
                        self.the_integrator.compute_increment(p, ls, model, an)
                np.copyto(dx0, ls.x)
                s0 = -float(dot_fn(dx0, residual0))

            if diagnostics is None:
                update_code = self.the_integrator.update(model, p, an)
            else:
                with diagnostics.timed("update_domain"):
                    update_code = self.the_integrator.update(model, p, an)
            if update_code < 0:
                return update_code

            np.copyto(line_search_direction, ls.x)
            if not csharp_line_search_compatibility:
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

            result = self.the_test.test(p, model, ls)
            error = self.the_test.get_error()

            if diagnostics is not None:
                tested_iteration = max(
                    1,
                    int(self.the_test.current_iter)
                    - (1 if result in {-1, -2} else 0),
                )
                captured = diagnostics.capture_state(
                    label="bfgs",
                    step=step,
                    iteration=tested_iteration,
                    program=p,
                    model=model,
                )
                diagnostics.emit(
                    "iteration",
                    step=step,
                    iteration=tested_iteration,
                    solver="BFGS",
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

            if result != -1:
                break

            # Update BFGS history with displacement increment s and residual difference y
            # s = step displacement change applied to the domain (ls.x)
            # y = - (new_residual - old_residual) = old_residual - new_residual
            s_vec = np.copy(ls.x)
            y_vec = residual0 - ls.b

            curv = float(dot_fn(s_vec, y_vec))
            norm_s = float(np.linalg.norm(s_vec))
            norm_y = float(np.linalg.norm(y_vec))

            # Curvature safeguard (Powell condition: s^T y > 1e-8 * ||s|| * ||y||)
            if norm_s > 1e-15 and norm_y > 1e-15 and curv > 1e-8 * norm_s * norm_y:
                rho = 1.0 / curv
                self._history.append((s_vec, y_vec, rho))
                if len(self._history) > self.max_history:
                    self._history.pop(0)
            else:
                # Curvature condition failed (local softening or non-positive curvature)
                stalls += 1

            # Check if contraction is genuinely stalling (error not decreasing)
            if error >= 0.98 * previous_error:
                stalls += 1
            else:
                stalls = max(0, stalls - 1)

            # If convergence stalls for multiple iterations, refresh base tangent K_0
            if stalls >= 6:
                p.log(f"BFGS: convergence stall detected at iteration {current_it}; refreshing tangent.")
                if diagnostics is None:
                    self.the_integrator.update_k(p, model, refresh_alfa)
                else:
                    with diagnostics.timed("tangent_assembly"):
                        self.the_integrator.update_k(p, model, refresh_alfa)
                self.clear_history()
                stalls = 0

            previous_error = error
            if p.to_stop:
                return -4

        if result == -2:
            p.log(
                f"BFGS convergence failed at step={step}: "
                f"error={self.the_test.get_error():.6e}"
            )
        elif result == -3:
            p.log(
                f"BFGS maximum displacement exceeded at step={step}: "
                f"error={self.the_test.get_error():.6e}"
            )
        return result
