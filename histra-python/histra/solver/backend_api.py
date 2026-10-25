"""High-level in-process API intended for orchestration backends."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping

from histra.io.hr_loader import load_model
from histra.solver.cancellation import CancelCheck, SolverCancelled
from histra.solver.capabilities import inspect_solver_capabilities
from histra.solver.interface_material import InterfaceMaterialMutationReport
from histra.solver.outcomes import AnalysisExecution, AnalysisOutcome
from histra.solver.output_projection import project_analysis_outputs
from histra.solver.session import AnalysisSession


@dataclass(frozen=True)
class ConcreteInterfaceMutation:
    """Backend-ready interface mutation using resolved HRX keys."""

    interface_keys: tuple[int, ...]
    material_key: int
    preserve_committed_state: bool = True
    spring_type_change: str = "reject"


@dataclass(frozen=True)
class PythonAnalysisRequest:
    name: str
    output_request: Any
    timeout_seconds: float


@dataclass(frozen=True)
class PythonAnalysisResult:
    execution: AnalysisExecution
    outputs: Mapping[str, Any]
    mutations: tuple[InterfaceMaterialMutationReport, ...] = ()

    @property
    def mutation(self) -> InterfaceMaterialMutationReport | None:
        """Backward-compatible access for callers that supplied one mutation."""
        return self.mutations[-1] if self.mutations else None


@dataclass(frozen=True)
class PythonSolverJobResult:
    analyses: Mapping[str, PythonAnalysisResult]
    executions: tuple[AnalysisExecution, ...]
    logs: tuple[str, ...]
    model_path: Path
    metadata: Mapping[str, Any] = field(default_factory=dict)


class PythonSolverJobError(RuntimeError):
    """Raised when an analysis cannot produce a completed backend result."""

    def __init__(self, execution: AnalysisExecution):
        super().__init__(
            f"Analysis {execution.analysis_name!r} ended as "
            f"{(execution.outcome or AnalysisOutcome.FAILED).value}: "
            f"{execution.message or 'no diagnostic message'}"
        )
        self.execution = execution


class PythonSolverTimeout(TimeoutError):
    """Raised when a job-wide or per-analysis deadline expires."""


def run_python_solver_job(
    model_path: str | Path,
    analyses: Iterable[PythonAnalysisRequest],
    *,
    timeout_seconds: float,
    interface_mutations: Mapping[
        str, ConcreteInterfaceMutation | Iterable[ConcreteInterfaceMutation]
    ] | None = None,
    combination_row: int = 1,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: CancelCheck | None = None,
    equilibrium_policy: str = "error",
    strategy_policy: str = "warn",
    performance_policy: str = "compiled",
) -> PythonSolverJobResult:
    """Run an HRX analysis plan entirely in process with deadline enforcement.

    Loads the HRX once, resolves predecessor dependency chains, executes analyses
    in memory, enforces cooperative timeouts, and projects C#-compatible output rows.
    Supports intermediate interface material mutations (e.g. Scour stages) across
    analysis boundaries.

    Parameters
    ----------
    model_path : str or Path
        Path to the target ``.hrx`` model file.
    analyses : Iterable[PythonAnalysisRequest]
        Sequence of analysis requests specifying analysis names and required output rows.
    timeout_seconds : float
        Overall job deadline in seconds.
    interface_mutations : Mapping[str, ConcreteInterfaceMutation | Iterable[...]], optional
        Optional material mutations keyed by analysis name, applied before that analysis starts.
    combination_row : int, default=1
        1-based load combination row to evaluate.
    on_log : Callable[[str], None], optional
        Logger callback for progress and diagnostic output.
    on_progress : Callable[[float], None], optional
        Progress callback reporting completion percentage.
    should_cancel : CancelCheck, optional
        Cooperative cancellation callback invoked at step and iteration checkpoints.
    equilibrium_policy : {"error", "warn", "strict", "off"}, default="error"
        Independent static equilibrium audit policy.
    strategy_policy : {"warn", "error", "off"}, default="warn"
        Solver strategy advisor warning/enforcement policy.
    performance_policy : {"compiled", "warn", "off"}, default="compiled"
        Compiled backend coverage enforcement policy.

    Returns
    -------
    PythonSolverJobResult
        Contains results keyed by analysis name, overall execution outcomes, and captured logs.

    Examples
    --------
    >>> from histra import PythonAnalysisRequest, run_python_solver_job
    >>> req = PythonAnalysisRequest(name="Vert", timeout_seconds=300)
    >>> job = run_python_solver_job("path/to/model.hrx", [req], timeout_seconds=600)
    >>> "vert" in job.results
    True
    """
    job_timeout = float(timeout_seconds)
    if job_timeout <= 0.0:
        raise ValueError("timeout_seconds must be positive.")

    requested = tuple(analyses)
    if not requested:
        raise ValueError("At least one analysis request is required.")
    for request in requested:
        if float(request.timeout_seconds) <= 0.0:
            raise ValueError(
                f"Analysis {request.name!r} timeout_seconds must be positive."
            )

    path = Path(model_path)
    model = load_model(path)
    output_requests = {request.name: request.output_request for request in requested}
    capability_report = inspect_solver_capabilities(
        model,
        [request.name for request in requested],
        output_requests=output_requests,
    )
    capability_report.require_supported()

    from histra.solver.backend_coverage import inspect_solver_backend

    backend_report = inspect_solver_backend(
        model, [request.name for request in requested]
    )
    if performance_policy == "compiled":
        backend_report.require_compiled()

    captured_logs: list[str] = []

    def log(message: str) -> None:
        captured_logs.append(str(message))
        if on_log is not None:
            on_log(str(message))

    session = AnalysisSession(
        model,
        combination_row=combination_row,
        on_log=log,
        on_progress=on_progress,
        equilibrium_policy=equilibrium_policy,
        strategy_policy=strategy_policy,
        performance_policy=performance_policy,
    )
    request_by_name = {request.name.casefold(): request for request in requested}
    run_order = _dependency_order(session, requested)
    implicit_timeout = max(float(request.timeout_seconds) for request in requested)
    mutations = interface_mutations or {}
    mutation_by_name = {
        name.casefold(): _normalize_mutations(value) for name, value in mutations.items()
    }
    job_deadline = time.monotonic() + job_timeout
    results: dict[str, PythonAnalysisResult] = {}

    for definition in run_order:
        name = str(definition.name)
        request = request_by_name.get(name.casefold())
        analysis_timeout = (
            float(request.timeout_seconds) if request is not None else implicit_timeout
        )
        analysis_deadline = min(job_deadline, time.monotonic() + analysis_timeout)
        if analysis_deadline <= time.monotonic():
            raise PythonSolverTimeout(
                f"Deadline expired before analysis {name!r} could start."
            )

        mutation_reports: list[InterfaceMaterialMutationReport] = []
        for mutation in mutation_by_name.get(name.casefold(), ()):
            mutation_reports.append(
                session.change_interface_materials(
                    mutation.interface_keys,
                    mutation.material_key,
                    preserve_committed_state=mutation.preserve_committed_state,
                    spring_type_change=mutation.spring_type_change,
                )
            )

        def analysis_cancelled() -> bool:
            return (
                time.monotonic() >= analysis_deadline
                or (should_cancel is not None and bool(should_cancel()))
            )

        execution = session.run(definition, should_cancel=analysis_cancelled)
        if not execution.completed:
            if time.monotonic() >= analysis_deadline:
                raise PythonSolverTimeout(
                    f"Analysis {name!r} exceeded its effective timeout."
                )
            if execution.outcome is AnalysisOutcome.CANCELLED:
                raise SolverCancelled(
                    f"Analysis {name!r} was cancelled by the caller."
                )
            raise PythonSolverJobError(execution)

        if request is not None:
            results[request.name] = PythonAnalysisResult(
                execution=execution,
                outputs=project_analysis_outputs(
                    model,
                    execution,
                    request.output_request,
                ),
                mutations=tuple(mutation_reports),
            )

    return PythonSolverJobResult(
        analyses=results,
        executions=tuple(session.executions),
        logs=tuple(captured_logs),
        model_path=path,
        metadata={
            "combination_row": int(combination_row),
            "serialized_in_process": True,
            "equilibrium_policy": str(equilibrium_policy),
            "strategy_policy": str(strategy_policy),
            "performance_policy": str(performance_policy),
            "backend_coverage": backend_report,
        },
    )


def _dependency_order(
    session: AnalysisSession,
    requested: Iterable[PythonAnalysisRequest],
) -> tuple[Any, ...]:
    ordered: list[Any] = []
    seen: set[int] = set()
    for request in requested:
        for definition in session.dependency_chain(request.name):
            key = int(definition.key)
            if key not in seen:
                seen.add(key)
                ordered.append(definition)
    return tuple(ordered)


def _normalize_mutations(
    value: ConcreteInterfaceMutation | Iterable[ConcreteInterfaceMutation],
) -> tuple[ConcreteInterfaceMutation, ...]:
    if isinstance(value, ConcreteInterfaceMutation):
        return (value,)
    result = tuple(value)
    if not all(isinstance(item, ConcreteInterfaceMutation) for item in result):
        raise TypeError("interface_mutations values must contain ConcreteInterfaceMutation objects.")
    return result
