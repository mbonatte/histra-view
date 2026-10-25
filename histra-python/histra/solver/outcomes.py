"""Stable result records and outcome classification for solver integrations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any, Mapping

import numpy as np

from histra.solver.cancellation import CANCELLED_EXIT_CODE
from histra.solver.equilibrium import UNSAFE_EQUILIBRIUM_EXIT_CODE


class AnalysisOutcome(StrEnum):
    COMPLETED = "completed"
    COMPLETED_AT_DISPLACEMENT_LIMIT = "completed_at_configured_displacement_limit"
    CANCELLED = "cancelled"
    NONCONVERGED = "nonconverged"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class AnalysisStep(dict[str, Any]):
    """Typed solver step that remains a real dict for legacy compatibility."""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AnalysisStep":
        result = cls(value)
        result["step"] = int(result.get("step", 0))
        result["status"] = str(result.get("status", "UNKNOWN"))
        result["exit_code"] = int(result.get("exit_code", 0))
        result["u"] = np.asarray(result.get("u", np.zeros(0)), dtype=float).copy()
        for key in (
            "load_factor", "displacement", "convergence_error",
            "convergence_tolerance", "residual_norm",
            "increment_norm", "max_element_displacement", "elastic_energy",
            "dissipated_energy", "reaction_x", "reaction_y", "reaction_z",
            "balancing_reaction_x", "balancing_reaction_y", "balancing_reaction_z",
            "equilibrium_expected_reaction_x", "equilibrium_expected_reaction_y",
            "equilibrium_expected_reaction_z", "equilibrium_force_error_x",
            "equilibrium_force_error_y", "equilibrium_force_error_z",
            "equilibrium_force_error_norm", "equilibrium_force_error_max",
            "equilibrium_force_limit", "equilibrium_force_relative_error",
            "equilibrium_residual_norm", "equilibrium_residual_max",
            "equilibrium_residual_limit",
        ):
            if key in result and result[key] is not None:
                result[key] = float(result[key])
        for key in (
            "iterations", "max_element_key", "linear_solve_count",
            "factorization_count",
        ):
            if key in result and result[key] is not None:
                result[key] = int(result[key])
        if "max_element_type" in result:
            result["max_element_type"] = str(result["max_element_type"])
        if "convergence_criterion" in result:
            result["convergence_criterion"] = str(result["convergence_criterion"])
        for key in (
            "equilibrium_checked", "equilibrium_ok", "equilibrium_force_ok",
            "equilibrium_residual_ok",
        ):
            if key in result:
                result[key] = bool(result[key])
        return result

    @classmethod
    def initial(
        cls,
        displacement: np.ndarray,
        *,
        reaction_x: float = 0.0,
        reaction_y: float = 0.0,
        reaction_z: float = 0.0,
    ) -> "AnalysisStep":
        return cls.from_mapping(
            {
                "step": 0,
                "status": "INITIAL",
                "exit_code": 0,
                "u": np.asarray(displacement, dtype=float),
                "load_factor": 0.0,
                "displacement": 0.0,
                "iterations": 0,
                "reaction_x": float(reaction_x),
                "reaction_y": float(reaction_y),
                "reaction_z": float(reaction_z),
            }
        )

    @property
    def step(self) -> int:
        return int(self["step"])

    @property
    def status(self) -> str:
        return str(self["status"])

    @property
    def exit_code(self) -> int:
        return int(self["exit_code"])

    @property
    def u(self) -> np.ndarray:
        return np.asarray(self["u"], dtype=float)

    @property
    def committed(self) -> bool:
        return self.status == "OK"

    @property
    def cancelled(self) -> bool:
        return self.status == "CANCELLED"

    @property
    def max_element_displacement(self) -> float:
        return float(self.get("max_element_displacement", 0.0))

    @property
    def reaction_x(self) -> float | None:
        return _optional_float(self.get("reaction_x"))

    @property
    def reaction_y(self) -> float | None:
        return _optional_float(self.get("reaction_y"))

    @property
    def reaction_z(self) -> float | None:
        return _optional_float(self.get("reaction_z"))

    @property
    def equilibrium_ok(self) -> bool | None:
        value = self.get("equilibrium_ok")
        return None if value is None else bool(value)

    def to_dict(self) -> dict[str, Any]:
        return dict(self)


@dataclass(frozen=True)
class AnalysisExecution:
    analysis_key: int
    analysis_name: str
    code: int
    steps: tuple[AnalysisStep, ...]
    runtime_seconds: float
    outcome: AnalysisOutcome | None = None
    message: str | None = None
    initial_step: AnalysisStep | None = None
    modal_result: Any | None = None

    @property
    def committed_steps(self) -> tuple[AnalysisStep, ...]:
        return tuple(step for step in self.steps if step.committed)

    @property
    def completed(self) -> bool:
        if self.outcome is None:
            return self.code == 0
        return self.outcome in {
            AnalysisOutcome.COMPLETED,
            AnalysisOutcome.COMPLETED_AT_DISPLACEMENT_LIMIT,
        }

    @property
    def output_steps(self) -> tuple[AnalysisStep, ...]:
        prefix = (self.initial_step,) if self.initial_step is not None else ()
        return prefix + self.committed_steps


def classify_analysis_outcome(
    code: int,
    steps: tuple[AnalysisStep, ...],
    analysis: Any,
) -> AnalysisOutcome:
    if int(code) == 0:
        return AnalysisOutcome.COMPLETED
    if int(code) == CANCELLED_EXIT_CODE or any(step.cancelled for step in steps):
        return AnalysisOutcome.CANCELLED
    if int(code) == -3:
        terminal = next((step for step in reversed(steps) if step.status == "FAILED"), None)
        configured_limit = abs(float(getattr(analysis, "max_u", 0.0)))
        measured = abs(terminal.max_element_displacement) if terminal is not None else 0.0
        if configured_limit > 0.0 and math.isfinite(configured_limit) and measured >= configured_limit:
            return AnalysisOutcome.COMPLETED_AT_DISPLACEMENT_LIMIT
        return AnalysisOutcome.NONCONVERGED
    if int(code) in {-2, UNSAFE_EQUILIBRIUM_EXIT_CODE}:
        return AnalysisOutcome.NONCONVERGED
    return AnalysisOutcome.FAILED


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
