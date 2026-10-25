"""Committed graph-slope policy from C# StaticNonLinearAnalysis.Execute."""
from __future__ import annotations

from typing import Any

import numpy as np

from histra.solver.incremental_integrator import effective_tangent_alpha


class SecantStiffnessPolicy:
    """Select initial/current stiffness using the first graph displacement.

    C# uses graph column 1, which may differ from the master displacement
    supplied to Integrator.Commit. Only the exact ArcLength integrator enables
    this policy; ArcLengthLinear and Modified methods do not enter this branch.
    """

    def __init__(self, analysis: Any, reference: list[float]) -> None:
        self.enabled = (
            bool(getattr(analysis, "check_secant_stiffness", False))
            and str(getattr(analysis, "integration_method", "")) == "ArcLength"
            and "Modified" not in str(getattr(analysis, "method", ""))
        )
        self.ratio = float(np.float32(getattr(analysis, "secant_stiffness_ratio", 0.0)))
        self.reference = reference[:2]
        self.previous = reference[:2]
        self.initial_stiffness = 0.0

    @staticmethod
    def _slope(values: list[float], previous: list[float]) -> float:
        # .NET division retains infinities and NaN at zero graph increments.
        with np.errstate(divide="ignore", invalid="ignore"):
            return float(np.divide(values[0] - previous[0], values[1] - previous[1]))

    def update(self, step: int, values: list[float], alpha: float,
               program: Any, model: Any, integrator: Any) -> float:
        if not self.enabled:
            return alpha
        if step == 1:
            self.initial_stiffness = abs(self._slope(values, self.reference))
        else:
            slope = self._slope(values, self.previous)
            use_initial = slope < 0.0 or abs(slope) < self.ratio * self.initial_stiffness
            selected = 0.0 if use_initial else 1.0
            program.log("Secant stiffness policy: using " + ("initial" if use_initial else "current") + " stiffness")
            if selected != alpha:
                integrator.update_k(program, model, selected)
                alpha = effective_tangent_alpha(program, selected)
        self.previous = values[:2]
        return alpha
