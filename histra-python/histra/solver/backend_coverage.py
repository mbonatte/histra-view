"""Coverage and preflight inspection for compiled solver execution."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Iterable

from histra.model.model import Model


class CompiledBackendError(RuntimeError):
    """Base exception for compiled production solver backend failures."""


class CompiledBackendRequiredError(CompiledBackendError):
    """Raised when production policy requires compiled execution but it is unavailable."""


class UnmanagedSolverObjectError(CompiledBackendRequiredError):
    """Raised when production policy requires 100% kernel coverage but unmanaged objects exist."""


@dataclass(frozen=True)
class SolverBackendCoverageReport:
    """Detailed audit of compiled NumPy/Numba and SciPy solver coverage."""

    model_name: str
    numba_available: bool
    numba_threads: int | None
    linear_solver_backend: str
    total_interfaces: int
    managed_interfaces: int
    unmanaged_interfaces: int
    total_quads: int
    managed_quads: int
    unmanaged_quads: int
    managed_transverse_springs: int
    managed_interface_coulomb_springs: int
    managed_quad_coulomb_springs: int
    managed_quad_cacovic_springs: int
    managed_quad_elastic_springs: int
    managed_quad_hysteretic_springs: int = 0
    interface_rejection_reasons: dict[str, int] = field(default_factory=dict)
    interface_coulomb_rejection_reasons: dict[str, int] = field(default_factory=dict)
    quad_rejection_reasons: dict[str, int] = field(default_factory=dict)
    requested_linear_solver_backend: str = "auto"
    linear_solver_available: bool = True
    linear_solver_error: str | None = None
    analysis_names: tuple[str, ...] = ()
    analysis_resolution_errors: tuple[str, ...] = ()

    @property
    def is_compiled_ready(self) -> bool:
        """True only if Numba is active, sparse solver is compiled, and 0 objects are unmanaged."""
        return (
            self.numba_available
            and self.linear_solver_available
            and not self.analysis_resolution_errors
            and self.unmanaged_interfaces == 0
            and self.unmanaged_quads == 0
            and not self.interface_rejection_reasons
            and not self.interface_coulomb_rejection_reasons
            and not self.quad_rejection_reasons
        )

    def require_compiled(self) -> None:
        """Enforce production compiled-only contract, raising if incomplete."""
        if not self.numba_available:
            raise CompiledBackendRequiredError(
                f"Compiled production execution is required for {self.model_name!r}, "
                "but Numba is unavailable or disabled via environment variable."
            )
        if not self.linear_solver_available:
            raise CompiledBackendRequiredError(
                f"Compiled production execution requested sparse backend "
                f"{self.requested_linear_solver_backend!r} for {self.model_name!r}, "
                f"but it is unavailable: {self.linear_solver_error or 'unknown error'}."
            )
        if self.analysis_resolution_errors:
            raise CompiledBackendRequiredError(
                f"Compiled production execution cannot preflight requested analysis "
                f"selection for {self.model_name!r}: "
                f"{'; '.join(self.analysis_resolution_errors)}"
            )
        if self.unmanaged_interfaces > 0 or self.unmanaged_quads > 0:
            reasons: list[str] = []
            if self.unmanaged_interfaces > 0:
                reasons.append(
                    f"{self.unmanaged_interfaces} unmanaged interface(s) "
                    f"(reasons: {self.interface_rejection_reasons or 'unclassified'})"
                )
            if self.unmanaged_quads > 0:
                reasons.append(
                    f"{self.unmanaged_quads} unmanaged quad(s) "
                    f"(reasons: {self.quad_rejection_reasons or 'unclassified'})"
                )
            raise UnmanagedSolverObjectError(
                f"Compiled production execution requires 100% kernel coverage for {self.model_name!r}, "
                f"but found unmanaged objects: {'; '.join(reasons)}. "
                "Diagnostic scalar execution must be requested explicitly via performance_policy='diagnostic-scalar'."
            )
        if self.interface_coulomb_rejection_reasons:
            raise UnmanagedSolverObjectError(
                f"Compiled production execution requires 100% kernel coverage for {self.model_name!r}, "
                f"but found unmanaged interface Coulomb springs: {self.interface_coulomb_rejection_reasons}. "
                "Diagnostic scalar execution must be requested explicitly via performance_policy='diagnostic-scalar'."
            )


def inspect_solver_backend(
    model: Model,
    analysis_names: Iterable[int | str | Any] | None = None,
    *,
    linear_solver_backend: str | None = None,
) -> SolverBackendCoverageReport:
    """Audit the actual compiled domain and sparse backend for requested analyses."""
    from histra.preprocessing import inspect_solver_readiness
    from histra.solver.hysteretic_runtime import (
        _evaluate_linear_batch,
        current_numba_threads,
    )
    from histra.solver.model_manager import ModelManager

    model_name = Path(model.source_path).name if getattr(model, "source_path", None) else "in-memory"
    env_disabled = os.environ.get("HISTRA_DISABLE_COMPILED_SPRINGS", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    numba_available = (_evaluate_linear_batch is not None) and not env_disabled

    collections = getattr(model, "collections", None)
    interfaces_dict = getattr(collections, "interfaces", {}) if collections is not None else {}
    quads_dict = getattr(collections, "quads", {}) if collections is not None else {}
    total_interfaces = len(interfaces_dict) if interfaces_dict else 0
    total_quads = len(quads_dict) if quads_dict else 0

    requested_backend, sparse_backend, sparse_available, sparse_error = (
        _resolve_linear_solver_backend(linear_solver_backend)
    )
    selected_analyses, analysis_errors = _resolve_requested_analyses(
        model, analysis_names
    )

    if not numba_available:
        return SolverBackendCoverageReport(
            model_name=model_name,
            numba_available=False,
            numba_threads=None,
            linear_solver_backend=sparse_backend,
            total_interfaces=total_interfaces,
            managed_interfaces=0,
            unmanaged_interfaces=total_interfaces,
            total_quads=total_quads,
            managed_quads=0,
            unmanaged_quads=total_quads,
            managed_transverse_springs=0,
            managed_interface_coulomb_springs=0,
            managed_quad_coulomb_springs=0,
            managed_quad_cacovic_springs=0,
            managed_quad_elastic_springs=0,
            interface_rejection_reasons={"numba_unavailable_or_disabled": total_interfaces} if total_interfaces else {},
            interface_coulomb_rejection_reasons={},
            quad_rejection_reasons={"numba_unavailable_or_disabled": total_quads} if total_quads else {},
            requested_linear_solver_backend=requested_backend,
            linear_solver_available=sparse_available,
            linear_solver_error=sparse_error,
            analysis_names=selected_analyses,
            analysis_resolution_errors=analysis_errors,
        )

    if total_interfaces == 0 and total_quads == 0:
        return SolverBackendCoverageReport(
            model_name=model_name,
            numba_available=True,
            numba_threads=current_numba_threads(),
            linear_solver_backend=sparse_backend,
            total_interfaces=0,
            managed_interfaces=0,
            unmanaged_interfaces=0,
            total_quads=0,
            managed_quads=0,
            unmanaged_quads=0,
            managed_transverse_springs=0,
            managed_interface_coulomb_springs=0,
            managed_quad_coulomb_springs=0,
            managed_quad_cacovic_springs=0,
            managed_quad_elastic_springs=0,
            requested_linear_solver_backend=requested_backend,
            linear_solver_available=sparse_available,
            linear_solver_error=sparse_error,
            analysis_names=selected_analyses,
            analysis_resolution_errors=analysis_errors,
        )

    readiness = inspect_solver_readiness(model)
    if not readiness.is_ready:
        ModelManager.prepare_model(model)

    runtime = ModelManager.prepare_hysteretic_batch(model, rebuild=False)
    if runtime is None:
        err = ModelManager._hysteretic_batch_error or "unknown construction failure"
        return SolverBackendCoverageReport(
            model_name=model_name,
            numba_available=True,
            numba_threads=current_numba_threads(),
            linear_solver_backend=sparse_backend,
            total_interfaces=total_interfaces,
            managed_interfaces=0,
            unmanaged_interfaces=total_interfaces,
            total_quads=total_quads,
            managed_quads=0,
            unmanaged_quads=total_quads,
            managed_transverse_springs=0,
            managed_interface_coulomb_springs=0,
            managed_quad_coulomb_springs=0,
            managed_quad_cacovic_springs=0,
            managed_quad_elastic_springs=0,
            interface_rejection_reasons={"runtime_construction_failed": total_interfaces},
            interface_coulomb_rejection_reasons={},
            quad_rejection_reasons={"runtime_construction_failed": total_quads},
            requested_linear_solver_backend=requested_backend,
            linear_solver_available=sparse_available,
            linear_solver_error=sparse_error,
            analysis_names=selected_analyses,
            analysis_resolution_errors=analysis_errors,
        )

    counts = runtime.performance_counts()
    return SolverBackendCoverageReport(
        model_name=model_name,
        numba_available=True,
        numba_threads=current_numba_threads(),
        linear_solver_backend=sparse_backend,
        total_interfaces=len(model.collections.interfaces),
        managed_interfaces=len(runtime.records),
        unmanaged_interfaces=counts["unmanaged_interfaces"],
        total_quads=len(model.collections.quads),
        managed_quads=len(runtime.quad_records),
        unmanaged_quads=counts["unmanaged_quads"],
        managed_transverse_springs=counts["managed_transverse_springs"],
        managed_interface_coulomb_springs=counts["managed_interface_coulomb_springs"],
        managed_quad_coulomb_springs=counts["managed_quad_coulomb_springs"],
        managed_quad_cacovic_springs=counts["managed_quad_cacovic_springs"],
        managed_quad_elastic_springs=counts["managed_quad_elastic_springs"],
        managed_quad_hysteretic_springs=counts["managed_quad_hysteretic_springs"],
        interface_rejection_reasons=dict(counts["interface_rejection_reasons"]),
        interface_coulomb_rejection_reasons=dict(counts["interface_coulomb_rejection_reasons"]),
        quad_rejection_reasons=dict(counts["quad_rejection_reasons"]),
        requested_linear_solver_backend=requested_backend,
        linear_solver_available=sparse_available,
        linear_solver_error=sparse_error,
        analysis_names=selected_analyses,
        analysis_resolution_errors=analysis_errors,
    )


def _resolve_linear_solver_backend(
    requested: str | None,
) -> tuple[str, str, bool, str | None]:
    """Resolve the same sparse backend the forthcoming ``LinearSystem`` uses."""
    from histra.types.cholmod import find_cholmod_library
    from histra.types.linear_system import LinearSystem
    from histra.types.umfpack import find_umfpack_library

    try:
        system = LinearSystem(0, backend=requested)
    except (TypeError, ValueError) as exc:
        label = "auto" if requested is None else str(requested)
        return label, "unavailable", False, str(exc)

    if system.backend == "umfpack" and find_umfpack_library() is None:
        return (
            system.requested_backend,
            system.backend,
            False,
            "UMFPACK was requested but no native library was found; set "
            "HISTRA_UMFPACK_LIBRARY or select SuperLU.",
        )
    if system.backend == "cholmod" and find_cholmod_library() is None:
        return (
            system.requested_backend,
            system.backend,
            False,
            "CHOLMOD was requested but no native library was found; set "
            "HISTRA_CHOLMOD_LIBRARY or select another backend.",
        )
    return system.requested_backend, system.backend, True, None


def _resolve_requested_analyses(
    model: Model,
    requested: Iterable[int | str | Any] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve public analysis selectors without silently ignoring a typo."""
    if requested is None:
        return (), ()
    analyses = getattr(getattr(model, "collections", None), "analyses", {}) or {}
    by_name = {
        str(getattr(value, "name", "")).casefold(): value
        for value in analyses.values()
    }
    labels: list[str] = []
    errors: list[str] = []
    for selector in requested:
        candidate = None
        if hasattr(selector, "key"):
            candidate = analyses.get(int(selector.key))
        elif isinstance(selector, int):
            candidate = analyses.get(selector)
        else:
            text = str(selector)
            try:
                candidate = analyses.get(int(text))
            except ValueError:
                candidate = by_name.get(text.casefold())
        if candidate is None:
            errors.append(f"unknown analysis selector {selector!r}")
            continue
        label = f"{int(candidate.key)}:{candidate.name}"
        if label not in labels:
            labels.append(label)
    return tuple(labels), tuple(errors)
