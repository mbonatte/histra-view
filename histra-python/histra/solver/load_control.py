from __future__ import annotations

from typing import Any

import numpy as np

from histra.model.model import Model
from histra.solver.incremental_integrator import StaticIntegrator
from histra.solver.model_manager import ModelManager
from histra.solver.program import Program
from histra.types.linear_system import LinearSystem


class LoadControl(StaticIntegrator):
    """Load-controlled nonlinear integrator aligned with C# ``LoadControl``."""

    def __init__(self) -> None:
        super().__init__()
        self._t = 0.0
        self._last_pseudo_time = 0.0
        self._lf_items: list[tuple[float, float]] = []
        self._step_dt = 0.0

    def _get_initial_time_and_force(self, an: Any) -> None:
        items = list(getattr(getattr(an, "load_function", None), "items", []) or [])
        self._lf_items = sorted(
            [(float(it.pseudo_time), float(it.multiplier)) for it in items],
            key=lambda item: item[0],
        )
        if not self._lf_items:
            self._lf_items = [(0.0, 0.0), (1.0, 1.0)]
        self._t = self._lf_items[0][0]
        self._last_pseudo_time = self._lf_items[-1][0]
        self.mult = self._lf_items[0][1]

    def domain_changed(self, p: Program, model: Model, size: int) -> None:
        del p, model, size
        if not self._lf_items:
            self._get_initial_time_and_force(self.state.analysis)

    def _segment(self) -> tuple[tuple[float, float], tuple[float, float]]:
        if len(self._lf_items) == 1:
            return self._lf_items[0], self._lf_items[0]
        previous = self._lf_items[0]
        for following in self._lf_items[1:]:
            if self._t < following[0] - 1e-12:
                return previous, following
            previous = following
        return self._lf_items[-2], self._lf_items[-1]

    def _get_increment(self) -> tuple[float, float]:
        if not self._lf_items:
            self._get_initial_time_and_force(self.state.analysis)

        last_time, last_multiplier = self._lf_items[-1]
        analysis_multiplier = float(getattr(self.state.analysis, "mult", 1.0))
        lf = getattr(self.state.analysis, "load_function", None)
        discretization = abs(float(getattr(lf, "discr_val", 0.1)))
        if discretization < 1e-15:
            raise ValueError("Load-function discretization must be positive")
        if self._t >= last_time - 1e-12:
            return 0.0, last_multiplier * analysis_multiplier - self.mult
        # Original GetIncrement closes the final interval against the accumulated
        # multiplier. Reusing the nominal increment changes its last bits.
        if last_time - 1e-5 < self._t + discretization:
            return last_time - self._t, last_multiplier * analysis_multiplier - self.mult

        (t0, f0), (t1, f1) = self._segment()
        dt_range = t1 - t0
        df_range = f1 - f0
        force_based = bool(getattr(lf, "type_discr", False))
        span = abs(df_range) if force_based else abs(dt_range)
        n_steps = max(1, int(np.ceil(span / discretization)))

        dt = dt_range / n_steps
        df = df_range / n_steps * analysis_multiplier
        # Do not step beyond the segment endpoint because floating point and
        # a non-divisible discretization can leave a shorter final interval.
        dt = min(dt, t1 - self._t) if dt >= 0 else max(dt, t1 - self._t)
        if abs(dt_range) > 1e-30:
            df = df_range * (dt / dt_range) * analysis_multiplier
        return dt, df

    def new_step(
        self,
        p: Program,
        model: Model,
        ls: LinearSystem,
        an: Any,
        combination: int,
        step: int,
        dof: int,
    ) -> None:
        del ls, dof
        self.step = step
        self.iteration = 0
        self._step_dt, self.incr_mult = self._get_increment()
        p.log(
            f"Step {step} solving: Mult={self.mult + self.incr_mult:.6f}, "
            f"IncrMult={self.incr_mult:.6f}"
        )
        p.progress(min(1.0, self._t / self._last_pseudo_time) if self._last_pseudo_time else 0.0)
        self.update_ptarget(p, model, an, combination, self.iteration)
        self.apply_load_domain(model, self.incr_mult)

    def new_step_with_incr(
        self,
        p: Program,
        model: Model,
        ls: LinearSystem,
        an: Any,
        combination: int,
        step: int,
        incr_mult: float,
    ) -> None:
        del ls
        self.step = step
        self.iteration = 0
        self.incr_mult = float(incr_mult)
        p.log(
            f"Step {step}, Mult={self.mult + self.incr_mult:.6f}, "
            f"IncrMult={self.incr_mult:.6f}"
        )
        self.update_ptarget(p, model, an, combination, self.iteration)
        self.apply_load_domain(model, self.incr_mult)

    def undo_current_load_increment(self, model: Model) -> None:
        """Undo the external-load part of a failed step before rollback/ALS."""
        self.apply_load_domain(model, -self.incr_mult)
        self.incr_mult = 0.0

    def update(self, model: Model, p: Program, an: Any) -> int:
        del an
        self.iteration += 1
        ModelManager.update_domain(model, p.ls, self.state)
        if self.u is not None:
            self.u += p.ls.x
        return 0

    def commit(
        self,
        model: Model,
        an: Any,
        disp: float,
        dof_max: int,
        has_domain_changed: list[bool],
    ) -> bool:
        del model, an, disp, dof_max, has_domain_changed
        if self.u_committed is not None and self.u is not None:
            self.u_committed[:] = self.u
        self._t += self._step_dt
        return self._t >= self._last_pseudo_time - 1e-12

    def get_time(self) -> float:
        return self._t
