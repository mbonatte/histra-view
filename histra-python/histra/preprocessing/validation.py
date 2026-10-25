"""Detect geometry-only HRX files before they enter the nonlinear solver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from histra.model.model import Model


@dataclass(frozen=True)
class ModelReadinessReport:
    """Summary of solver-generated data present in an HRX model."""

    is_ready: bool
    is_locked: bool
    gdl: int
    quad_count: int
    quad_spring_count: int
    quad_afference_count: int
    interface_count: int
    interface_spring_count: int
    interface_afference_count: int
    missing: tuple[str, ...]

    def format(self, source: str | None = None) -> str:
        label = source or "HRX model"
        lines = [
            f"{label} is not solver-ready and requires HiStrA preprocessing (computational model generation).",
            "",
            "Detected computational data:",
            f"  IsLocked: {self.is_locked}",
            f"  GDL: {self.gdl}",
            f"  Quads: {self.quad_count}",
            f"  Quads with diagonal springs: {self.quad_spring_count}",
            f"  Quads with complete afference: {self.quad_afference_count}",
            f"  Interfaces: {self.interface_count}",
            f"  Interfaces with springs: {self.interface_spring_count}",
            f"  Interfaces with complete afference: {self.interface_afference_count}",
        ]
        if self.missing:
            lines.extend(("", "Missing preprocessing outputs:"))
            lines.extend(f"  - {item}" for item in self.missing)
        lines.extend(
            (
                "",
                "The Python solver can automatically run PrepareModel for supported "
                "unlocked Quad/Restraint HRX models. Unsupported element types or "
                "partial-contact topologies fail explicitly with a preparation error.",
            )
        )
        return "\n".join(lines)


class ModelPreprocessingRequiredError(RuntimeError):
    """Raised when a geometry-only HRX is passed to the nonlinear solver."""

    def __init__(self, report: ModelReadinessReport, source: str | None = None):
        self.report = report
        self.source = source
        super().__init__(report.format(source))


def _complete_afference(aff: Iterable[object], expected: int) -> bool:
    matrices = list(aff)
    if len(matrices) < expected:
        return False
    return all(bool(matrix) for matrix in matrices[:expected])


def inspect_solver_readiness(model: Model) -> ModelReadinessReport:
    """Inspect whether the computational data required by the solver exists."""

    collections = model.collections
    if collections is None:
        return ModelReadinessReport(
            is_ready=False,
            is_locked=bool(model.is_locked),
            gdl=int(model.gdl),
            quad_count=0,
            quad_spring_count=0,
            quad_afference_count=0,
            interface_count=0,
            interface_spring_count=0,
            interface_afference_count=0,
            missing=("Model.collections is not initialized",),
        )

    quads = tuple(collections.quads.values())
    interfaces = tuple(collections.interfaces.values())
    quad_spring_count = sum(getattr(q, "spring", None) is not None for q in quads)
    quad_afference_count = sum(
        _complete_afference(getattr(q, "aff", ()), 7) for q in quads
    )
    interface_spring_count = sum(
        bool(getattr(i, "trasv_1", ()))
        and bool(getattr(i, "slid", ()))
        and bool(getattr(i, "slid_out_plan", ()))
        for i in interfaces
    )
    interface_afference_count = sum(
        len(list(getattr(i, "aff", ())))
        >= int(getattr(i, "dim_aff_tot", 0) or 0)
        and any(bool(matrix) for matrix in getattr(i, "aff", ()))
        for i in interfaces
    )

    missing: list[str] = []
    if not model.is_locked:
        missing.append("model lock/preprocessing flag (IsLocked=false)")
    if int(model.gdl) <= 0:
        missing.append("global degree-of-freedom numbering (GDL=0)")
    if quads and quad_spring_count != len(quads):
        missing.append(
            f"Quad diagonal springs ({len(quads) - quad_spring_count} missing)"
        )
    if quads and quad_afference_count != len(quads):
        missing.append(
            f"Quad afference matrices ({len(quads) - quad_afference_count} incomplete)"
        )
    if len(quads) > 1 and not interfaces:
        missing.append("generated Quad-Quad/Quad-Restraint interfaces (none present)")
    if interfaces and interface_spring_count != len(interfaces):
        missing.append(
            f"interface spring groups ({len(interfaces) - interface_spring_count} incomplete)"
        )
    if interfaces and interface_afference_count != len(interfaces):
        missing.append(
            "interface afference matrices "
            f"({len(interfaces) - interface_afference_count} incomplete)"
        )

    return ModelReadinessReport(
        is_ready=not missing,
        is_locked=bool(model.is_locked),
        gdl=int(model.gdl),
        quad_count=len(quads),
        quad_spring_count=quad_spring_count,
        quad_afference_count=quad_afference_count,
        interface_count=len(interfaces),
        interface_spring_count=interface_spring_count,
        interface_afference_count=interface_afference_count,
        missing=tuple(missing),
    )


def require_solver_ready(model: Model) -> ModelReadinessReport:
    """Raise a precise error when the HRX lacks preprocessor-generated data."""

    report = inspect_solver_readiness(model)
    if not report.is_ready:
        raise ModelPreprocessingRequiredError(report, model.source_path)
    return report
