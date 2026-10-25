"""Independent safety audit for committed static nonlinear states.

The legacy HiStrA convergence criteria answer whether one scalar Newton
measure is small enough.  They do not all guarantee equilibrium.  In
particular, ``Work`` can be small because the latest displacement correction
is small even when the residual force vector is not.

This module deliberately does not participate in the Newton iteration.  It
checks the candidate state after the selected C#-compatible test has accepted
it and before it is committed, allowing callers either to warn (the default)
or reject the unsafe state without changing the numerical path of accepted
solutions.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from histra.postprocessing import ReactionResult


UNSAFE_EQUILIBRIUM_EXIT_CODE = -12


class UnsafeEquilibriumWarning(RuntimeWarning):
    """A nonlinear step passed its selected test but failed the safety audit."""


def normalize_equilibrium_policy(value: str) -> str:
    """Return one of ``warn``, ``error``, or ``off``."""

    policy = str(value).strip().lower()
    aliases = {"raise": "error", "strict": "error", "none": "off"}
    policy = aliases.get(policy, policy)
    if policy not in {"warn", "error", "off"}:
        raise ValueError(
            "equilibrium_policy must be one of: warn, error, off; "
            f"received {value!r}"
        )
    return policy


def applied_force_resultant(model: Any) -> np.ndarray:
    """Return the unit-load global force resultant in kN.

    ``Quad.status.p[0:3]`` are the three rigid-translation generalized loads.
    Their sum is therefore the physical resultant of the analysis load pattern
    before multiplication by the integrator load factor.  Internal diagonal
    and rotational generalized loads are intentionally excluded.
    """

    resultant = np.zeros(3, dtype=np.float64)
    for quad in model.collections.quads.values():
        values = getattr(getattr(quad, "status", None), "p", ())
        for axis in range(min(3, len(values))):
            resultant[axis] += float(values[axis])
    return resultant


@dataclass(frozen=True)
class EquilibriumAudit:
    """Force-balance and active-DOF residual checks for one candidate step."""

    expected_reaction: tuple[float, float, float]
    actual_reaction: tuple[float, float, float]
    force_error: tuple[float, float, float]
    force_error_norm: float
    force_error_max: float
    force_limit: float
    force_relative_error: float
    force_ok: bool
    residual_norm: float
    residual_max: float
    residual_limit: float
    residual_ok: bool

    @property
    def safe(self) -> bool:
        return self.force_ok and self.residual_ok

    def step_fields(self) -> dict[str, float | bool]:
        return {
            "equilibrium_ok": self.safe,
            "equilibrium_force_ok": self.force_ok,
            "equilibrium_residual_ok": self.residual_ok,
            "equilibrium_expected_reaction_x": self.expected_reaction[0],
            "equilibrium_expected_reaction_y": self.expected_reaction[1],
            "equilibrium_expected_reaction_z": self.expected_reaction[2],
            "equilibrium_force_error_x": self.force_error[0],
            "equilibrium_force_error_y": self.force_error[1],
            "equilibrium_force_error_z": self.force_error[2],
            "equilibrium_force_error_norm": self.force_error_norm,
            "equilibrium_force_error_max": self.force_error_max,
            "equilibrium_force_limit": self.force_limit,
            "equilibrium_force_relative_error": self.force_relative_error,
            "equilibrium_residual_norm": self.residual_norm,
            "equilibrium_residual_max": self.residual_max,
            "equilibrium_residual_limit": self.residual_limit,
        }

    def warning_message(
        self, *, analysis_name: str, step: int, criterion: str, criterion_error: float
    ) -> str:
        ex, ey, ez = self.force_error
        return (
            "UNSAFE NONLINEAR EQUILIBRIUM: "
            f"analysis={analysis_name!r}, step={step}, selected criterion={criterion}, "
            f"selected error={criterion_error:.6g}; the selected criterion passed, "
            f"but the independent safety audit failed. Global force-balance error "
            f"[Fx,Fy,Fz]=[{ex:.6g}, {ey:.6g}, {ez:.6g}] kN, "
            f"max={self.force_error_max:.6g} kN, allowed={self.force_limit:.6g} kN; "
            f"active-DOF residual L2={self.residual_norm:.6g}, "
            f"allowed={self.residual_limit:.6g} in HiStrA native generalized "
            "force/moment units. Do not use this step for engineering capacity."
        )


def audit_static_equilibrium(
    *,
    reaction: ReactionResult,
    reference_reaction: ReactionResult,
    target_force: np.ndarray,
    load_factor_increment: float,
    residual: np.ndarray,
    force_absolute_tolerance: float,
    force_relative_tolerance: float,
    residual_tolerance: float,
) -> EquilibriumAudit:
    """Audit a candidate state without changing any solver or element state.

    Reactions use HiStrA's ``ReactionSum`` sign convention, in which an applied
    downward load and the corresponding restrained-interface resultant are
    both negative.  The expected current reaction is consequently the baseline
    reaction plus the physical applied-load increment.
    """

    target = np.asarray(target_force, dtype=np.float64)
    residual_values = np.asarray(residual, dtype=np.float64)
    if target.shape != (3,):
        raise ValueError(f"target_force must have shape (3,), received {target.shape}")
    if residual_values.ndim != 1:
        raise ValueError("residual must be a one-dimensional vector")
    if force_absolute_tolerance < 0.0 or force_relative_tolerance < 0.0:
        raise ValueError("equilibrium force tolerances must be non-negative")
    if residual_tolerance < 0.0:
        raise ValueError("equilibrium residual tolerance must be non-negative")

    baseline = np.asarray(
        (reference_reaction.x, reference_reaction.y, reference_reaction.z),
        dtype=np.float64,
    )
    actual = np.asarray((reaction.x, reaction.y, reaction.z), dtype=np.float64)
    expected = baseline + float(load_factor_increment) * target
    error = actual - expected
    error_norm = float(np.linalg.norm(error))
    error_max = float(np.max(np.abs(error)))
    scale = max(float(np.linalg.norm(actual)), float(np.linalg.norm(expected)), 1.0)
    force_limit = float(force_absolute_tolerance) + float(force_relative_tolerance) * scale
    relative_error = error_norm / scale

    residual_norm = float(np.linalg.norm(residual_values))
    residual_max = (
        float(np.max(np.abs(residual_values))) if residual_values.size else 0.0
    )
    finite = all(
        math.isfinite(value)
        for value in (error_norm, error_max, force_limit, residual_norm, residual_max)
    )
    return EquilibriumAudit(
        expected_reaction=tuple(float(value) for value in expected),
        actual_reaction=tuple(float(value) for value in actual),
        force_error=tuple(float(value) for value in error),
        force_error_norm=error_norm,
        force_error_max=error_max,
        force_limit=force_limit,
        force_relative_error=relative_error,
        force_ok=finite and error_max <= force_limit,
        residual_norm=residual_norm,
        residual_max=residual_max,
        residual_limit=float(residual_tolerance),
        residual_ok=finite and residual_norm <= float(residual_tolerance),
    )
