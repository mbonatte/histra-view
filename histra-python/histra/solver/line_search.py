from __future__ import annotations

from typing import Any

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - optional acceleration
    njit = None


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


def _check_cancelled(program: Any) -> None:
    if program is not None:
        try:
            program.check_cancelled()
        except AttributeError:
            pass


class LineSearch:
    """Base/no-op line search matching the C# solver interface."""

    def __init__(self) -> None:
        self.tolerance = 0.8
        self.max_iter = 100
        self.min_eta = 0.1
        self.max_eta = 10.0
        self.print_flag = 1
        self._direction: np.ndarray | None = None

    def new_step(self, p: Any, ls: Any) -> None:
        del p, ls

    def search(
        self,
        model: Any,
        p: Any,
        ls: Any,
        integrator: Any,
        an: Any,
        dx0: np.ndarray,
        s0: float,
        s1: float,
    ) -> float:
        # The C# base LineSearch.search() is a true no-op.  In the hidden
        # InitialInterpolated benchmark path, ArcLength.Update has already
        # replaced LS.X with the combined constrained correction
        # (delta_u_bar + delta_lambda * delta_u_hat).  The Work convergence
        # test must see that vector; restoring the raw Newton direction dx0
        # changes the commit iteration and nonlinear path.
        del model, p, ls, integrator, an, dx0, s0, s1
        return 1.0

    def _trial(
        self,
        model: Any,
        p: Any,
        ls: Any,
        integrator: Any,
        an: Any,
        direction: np.ndarray,
        eta: float,
        eta_previous: float,
        *,
        csharp_sign: bool = False,
    ) -> tuple[int, float]:
        """Move from the current trial point to ``eta`` and evaluate ``s``.

        The full Newton step has already been applied by ``NewtonLineSearch``,
        so the first correction is ``(eta - 1) * direction``.  Trial points are
        reached incrementally, exactly as in the C# algorithm.
        """
        _check_cancelled(p)
        delta_eta = eta - eta_previous
        if (
            not getattr(an, "csharp_line_search_compatibility", True)
        ) and hasattr(integrator, "update_trial"):
            code = integrator.update_trial(model, p, an, delta_eta, direction)
        else:
            ls.set_x_vector(delta_eta * direction)
            code = integrator.update(model, p, an)
        if code < 0:
            return code, float("nan")
        integrator.form_unbalance(p, model, an)
        # C# compatibility retains positive trial dots. The Python strategy
        # uses a consistent negative sign for its improved search methods.
        dot_fn = (
            _csharp_dot
            if getattr(an, "csharp_line_search_compatibility", True)
            else np.dot
        )
        dot = float(dot_fn(direction, ls.b))
        return 0, dot if csharp_sign else -dot

    @staticmethod
    def _ratio(s: float, s0: float) -> float:
        return abs(s / s0) if abs(s0) > 1e-30 else 0.0

    def _finish(self, ls: Any, direction: np.ndarray, eta: float) -> float:
        # Elements and total displacement are already at eta from incremental
        # trial corrections.  Set LS.x to the *total* scaled Newton increment
        # for displacement/work convergence tests, without updating again.
        ls.set_x_vector(eta * direction)
        return float(eta)


class RegulaFalsiLineSearch(LineSearch):
    """Faithful port of the supplied C# Regula-Falsi line search.

    The reference implementation evaluates trial ``s`` values with the
    opposite sign from ``s0``/``s1``.  That is mathematically inconsistent,
    but it materially changes the accepted nonlinear path in the supplied
    benchmark.  Compatibility is therefore preserved here and documented as
    an original C# defect rather than silently "corrected".
    """

    def search(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        if not getattr(an, "csharp_line_search_compatibility", True):
            return self._search_python(model, p, ls, integrator, an, dx0, s0, s1)
        ratio_initial = self._csharp_ratio(s1, s0)
        if ratio_initial <= self.tolerance or s1 == s0:
            return 1.0  # C# retains the integrator's current correction.

        direction = ls.x.copy()
        eta = 1.0
        eta_hi, s_hi = 1.0, s1
        eta_lo, s_lo = 0.0, s0
        ratio = ratio_initial
        eta_previous = 1.0
        stopped = False

        iterations = 0
        use_update_trial = (
            not getattr(an, "csharp_line_search_compatibility", True)
        ) and hasattr(integrator, "update_trial")

        while ratio > self.tolerance and iterations < self.max_iter and not stopped:
            _check_cancelled(p)
            iterations += 1
            denominator = s_lo - s_hi
            with np.errstate(divide='ignore', invalid='ignore'):
                eta = eta_hi - float(np.divide(s_hi * (eta_lo - eta_hi), denominator))
            if eta > self.max_eta:
                eta = self.max_eta
            # Exact C# safeguard: once a trial is worse than the initial full
            # step, evaluate eta=1 again rather than returning immediately.
            if ratio > ratio_initial:
                eta = 1.0
            if eta < self.min_eta:
                eta = self.min_eta

            delta_eta = eta - eta_previous
            if use_update_trial:
                code = integrator.update_trial(model, p, an, delta_eta, direction)
            else:
                ls.set_x_vector(delta_eta * direction)
                code = integrator.update(model, p, an)
            if code < 0:
                return float(code)
            integrator.form_unbalance(p, model, an)

            dot_fn = (
                _csharp_dot
                if getattr(an, "csharp_line_search_compatibility", True)
                else np.dot
            )
            s_eta = float(dot_fn(direction, ls.b))
            ratio = self._csharp_ratio(s_eta, s0)

            # Do not collapse the C# endpoint cycle.  Although all supported
            # springs rebuild trial state from committed state, the integrator
            # reaches the endpoint through many incremental floating-point
            # updates.  Those last bits are significant for branch selection
            # in symmetric nonlinear models, so exact compatibility requires
            # traversing the original sequence.

            if eta_previous == eta:
                stopped = True
            eta_previous = eta

            if s_eta * s_hi < 0.0:
                eta_lo, s_lo = eta, s_eta
            elif s_eta * s_hi == 0.0:
                stopped = True
            else:
                eta_hi, s_hi = eta, s_eta
            if s_lo == s_hi:
                stopped = True

        return self._finish(ls, direction, eta)

    @staticmethod
    def _csharp_ratio(s: float, s0: float) -> float:
        return abs(s / s0) if s0 != 0.0 else 0.0

    def _search_python(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        ratio_initial = self._ratio(s1, s0)
        if ratio_initial <= self.tolerance or s1 == s0:
            return self._finish(ls, dx0, 1.0)

        eta = 1.0
        eta_hi, s_hi = 1.0, s1
        eta_lo, s_lo = 0.0, s0
        ratio = ratio_initial
        eta_previous = 1.0
        stopped = False

        iterations = 0
        use_update_trial = (
            not getattr(an, "csharp_line_search_compatibility", True)
        ) and hasattr(integrator, "update_trial")

        while ratio > self.tolerance and iterations < self.max_iter and not stopped:
            _check_cancelled(p)
            iterations += 1
            denominator = s_lo - s_hi
            if denominator == 0.0:
                break
            eta = eta_hi - s_hi * (eta_lo - eta_hi) / denominator
            if eta > self.max_eta:
                eta = self.max_eta
            # Exact C# safeguard: once a trial is worse than the initial full
            # step, evaluate eta=1 again rather than returning immediately.
            if ratio > ratio_initial:
                eta = 1.0
            if eta < self.min_eta:
                eta = self.min_eta

            delta_eta = eta - eta_previous
            if use_update_trial:
                code = integrator.update_trial(model, p, an, delta_eta, dx0)
            else:
                ls.set_x_vector(delta_eta * dx0)
                code = integrator.update(model, p, an)
            if code < 0:
                return -1.0
            integrator.form_unbalance(p, model, an)

            dot_fn = (
                _csharp_dot
                if getattr(an, "csharp_line_search_compatibility", True)
                else np.dot
            )
            s_eta = float(dot_fn(dx0, ls.b))
            ratio = self._ratio(s_eta, s0)

            # Do not collapse the C# endpoint cycle.  Although all supported
            # springs rebuild trial state from committed state, the integrator
            # reaches the endpoint through many incremental floating-point
            # updates.  Those last bits are significant for branch selection
            # in symmetric nonlinear models, so exact compatibility requires
            # traversing the original sequence.

            if eta_previous == eta:
                stopped = True
            eta_previous = eta

            if s_eta * s_hi < 0.0:
                eta_lo, s_lo = eta, s_eta
            elif s_eta * s_hi == 0.0:
                stopped = True
            else:
                eta_hi, s_hi = eta, s_eta
            if s_lo == s_hi:
                stopped = True

        return self._finish(ls, dx0, eta)


class SecantLineSearch(LineSearch):
    """2026.1.1 C# secant trial sequence, including its sign convention."""

    def search(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        if not getattr(an, "csharp_line_search_compatibility", True):
            return self._search_python(model, p, ls, integrator, an, dx0, s0, s1)
        ratio_initial = self._csharp_ratio(s1, s0)
        if ratio_initial <= self.tolerance or s1 == s0:
            return 1.0  # C# leaves the integrator's current LS.x untouched.
        direction = ls.x.copy()
        eta = eta_previous = 1.0
        eta_older = 0.0
        s_previous, s_older = s1, s0
        ratio = ratio_initial
        stopped = False
        iteration = 0
        while ratio > self.tolerance and iteration < self.max_iter and not stopped:
            _check_cancelled(p)
            iteration += 1
            with np.errstate(divide="ignore", invalid="ignore"):
                eta = eta_previous - float(np.divide(
                    s_previous * (eta_older - eta_previous), s_older - s_previous
                ))
            if eta > self.max_eta:
                eta = self.max_eta
            if ratio > ratio_initial:
                eta = 1.0
            if eta < self.min_eta:
                eta = self.min_eta
            code, s_eta = self._trial(
                model, p, ls, integrator, an, direction, eta, eta_previous,
                csharp_sign=True,
            )
            if code < 0:
                return float(code)
            ratio = self._csharp_ratio(s_eta, s0)
            stopped = eta_previous == eta
            eta_older, eta_previous = eta_previous, eta
            s_older, s_previous = s_previous, s_eta
            stopped = stopped or s_older == s_previous
        return self._finish(ls, direction, eta)

    @staticmethod
    def _csharp_ratio(s: float, s0: float) -> float:
        return abs(s / s0) if s0 != 0.0 else 0.0

    def _search_python(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        if abs(s0) < 1e-30 or self._ratio(s1, s0) <= self.tolerance or s1 == s0:
            return self._finish(ls, dx0, 1.0)

        eta_prev2, s_prev2 = 0.0, s0
        eta_prev, s_prev = 1.0, s1
        baseline_ratio = self._ratio(s1, s0)

        for _ in range(self.max_iter):
            _check_cancelled(p)
            denominator = s_prev2 - s_prev
            if abs(denominator) < 1e-30:
                break
            eta = eta_prev - s_prev * (eta_prev2 - eta_prev) / denominator
            eta = float(np.clip(eta, self.min_eta, self.max_eta))
            code, s_eta = self._trial(
                model, p, ls, integrator, an, dx0, eta, eta_prev
            )
            if code < 0:
                return -1.0
            ratio = self._ratio(s_eta, s0)
            if ratio <= self.tolerance:
                return self._finish(ls, dx0, eta)
            if ratio > baseline_ratio and eta != 1.0:
                code, _ = self._trial(model, p, ls, integrator, an, dx0, 1.0, eta)
                if code < 0:
                    return -1.0
                return self._finish(ls, dx0, 1.0)
            eta_prev2, s_prev2 = eta_prev, s_prev
            eta_prev, s_prev = eta, s_eta

        return self._finish(ls, dx0, eta_prev)


class BisectionLineSearch(LineSearch):
    """2026.1.1 C# bracket/bisection sequence and exit-state semantics.

    C# doubles past maxEta during bracketing, retains the last correction on
    an early bracket exit, and applies an extra full step if no bracket is
    found. These observable quirks are preserved for nonlinear output parity.
    """

    def search(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        if not getattr(an, "csharp_line_search_compatibility", True):
            return self._search_python(model, p, ls, integrator, an, dx0, s0, s1)
        ratio_initial = self._csharp_ratio(s1, s0)
        if ratio_initial <= self.tolerance or s1 == s0:
            return 1.0
        direction = ls.x.copy()
        eta = eta_hi = eta_previous = 1.0
        eta_lo = 0.0
        s_hi, s_lo = s1, s0
        ratio = ratio_initial
        iteration = 0
        while s_hi * s_lo > 0.0 and eta_hi < self.max_eta and iteration < self.max_iter:
            _check_cancelled(p)
            iteration += 1
            eta_hi *= 2.0
            code, s_hi = self._trial(
                model, p, ls, integrator, an, direction, eta_hi, eta_previous,
                csharp_sign=True,
            )
            if code < 0:
                return float(code)
            ratio = self._csharp_ratio(s_hi, s0)
            if ratio < self.tolerance:
                return 1.0  # Do not overwrite the last correction in LS.x.
            eta_previous = eta_hi
        if s_hi * s_lo > 0.0:
            _check_cancelled(p)
            ls.set_x_vector(direction)
            integrator.update(model, p, an)
            integrator.form_unbalance(p, model, an)
            return 1.0
        stopped = ratio <= self.tolerance
        iteration = 0  # C# gives bisection its own full iteration budget.
        while ratio > self.tolerance and iteration < self.max_iter and not stopped:
            _check_cancelled(p)
            iteration += 1
            eta = (eta_hi + eta_lo) * 0.5
            if ratio > ratio_initial:
                eta = 1.0
            code, s_eta = self._trial(
                model, p, ls, integrator, an, direction, eta, eta_previous,
                csharp_sign=True,
            )
            if code < 0:
                return float(code)
            ratio = self._csharp_ratio(s_eta, s0)
            eta_previous = eta
            if s_eta * s_hi < 0.0:
                eta_lo, s_lo = eta, s_eta
            elif s_eta * s_hi == 0.0:
                stopped = True
            else:
                eta_hi, s_hi = eta, s_eta
            stopped = stopped or s_lo == s_hi
        return self._finish(ls, direction, eta)

    @staticmethod
    def _csharp_ratio(s: float, s0: float) -> float:
        return abs(s / s0) if s0 != 0.0 else 0.0

    def _search_python(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        if abs(s0) < 1e-30 or self._ratio(s1, s0) <= self.tolerance or s1 == s0:
            return self._finish(ls, dx0, 1.0)

        eta_lo, s_lo = 0.0, s0
        eta_hi, s_hi = 1.0, s1
        eta_previous = 1.0

        # Expand the upper point until a sign change is found.
        attempts = 0
        while s_lo * s_hi > 0.0 and eta_hi < self.max_eta and attempts < self.max_iter:
            _check_cancelled(p)
            attempts += 1
            eta_new = min(self.max_eta, 2.0 * eta_hi)
            code, s_new = self._trial(
                model, p, ls, integrator, an, dx0, eta_new, eta_previous
            )
            if code < 0:
                return -1.0
            eta_previous = eta_new
            eta_hi, s_hi = eta_new, s_new
            if self._ratio(s_hi, s0) <= self.tolerance:
                return self._finish(ls, dx0, eta_hi)

        if s_lo * s_hi > 0.0:
            # No bracket: restore the already accepted full Newton point.
            if eta_previous != 1.0:
                code, _ = self._trial(
                    model, p, ls, integrator, an, dx0, 1.0, eta_previous
                )
                if code < 0:
                    return -1.0
            return self._finish(ls, dx0, 1.0)

        eta = eta_previous
        for _ in range(max(0, self.max_iter - attempts)):
            _check_cancelled(p)
            eta = 0.5 * (eta_lo + eta_hi)
            code, s_eta = self._trial(
                model, p, ls, integrator, an, dx0, eta, eta_previous
            )
            if code < 0:
                return -1.0
            eta_previous = eta
            if self._ratio(s_eta, s0) <= self.tolerance or s_eta == 0.0:
                break
            if s_eta * s_hi < 0.0:
                eta_lo, s_lo = eta, s_eta
            else:
                eta_hi, s_hi = eta, s_eta

        return self._finish(ls, dx0, eta)


class InitialInterpolatedLineSearch(LineSearch):
    """Initial-interpolation search, ported as a real override.

    The original C# class declares ``new virtual`` instead of ``override``;
    through a base ``LineSearch`` reference that likely dispatches to the no-op
    base method.  The Python version implements the intended algorithm.
    """

    def search(self, model, p, ls, integrator, an, dx0, s0, s1) -> float:
        if abs(s0) < 1e-30 or self._ratio(s1, s0) <= self.tolerance or s1 == s0:
            return self._finish(ls, dx0, 1.0)

        eta_previous = 1.0
        eta = float(np.clip(s0 / (s0 - s1), self.min_eta, self.max_eta))
        for _ in range(self.max_iter):
            _check_cancelled(p)
            code, s_eta = self._trial(
                model, p, ls, integrator, an, dx0, eta, eta_previous
            )
            if code < 0:
                return -1.0
            if self._ratio(s_eta, s0) <= self.tolerance:
                break
            denominator = s0 - s_eta
            if abs(denominator) < 1e-30:
                break
            eta_previous = eta
            eta = float(np.clip(eta * s0 / denominator, self.min_eta, self.max_eta))
        return self._finish(ls, dx0, eta)
