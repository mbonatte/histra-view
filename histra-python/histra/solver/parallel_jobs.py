"""Bounded CPU jobs in isolated interpreters; solver globals never cross jobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
import pickle
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Iterable, Mapping

from histra.solver.resources import SolverResources

from histra.solver.backend_api import (
    ConcreteInterfaceMutation,
    PythonAnalysisRequest,
    PythonSolverJobResult,
    run_python_solver_job,
)


@dataclass(frozen=True)
class PythonSolverJob:
    """One independent model/analysis chain with a wall-clock deadline."""

    model_path: str | Path
    analyses: tuple[PythonAnalysisRequest, ...]
    timeout_seconds: float
    interface_mutations: Mapping[
        str, ConcreteInterfaceMutation | tuple[ConcreteInterfaceMutation, ...]
    ] | None = None
    combination_row: int = 1
    equilibrium_policy: str = "error"
    strategy_policy: str = "warn"
    output_directory: str | Path | None = None


@dataclass(frozen=True)
class PythonSolverJobOutcome:
    """Ordered batch entry; a failed job does not discard successful neighbours."""

    result: PythonSolverJobResult | None
    error: str | None
    runtime_seconds: float
    process_id: int | None = None

    @property
    def completed(self) -> bool:
        return self.result is not None and self.error is None


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _worker_limit(max_workers: int | None, threads: int, memory_budget_mb: int | None,
                  estimated_job_memory_mb: int | None) -> int:
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    limit = max(1, cores // threads)
    workers = min(limit, 2 if max_workers is None else _positive_integer(max_workers, "max_workers"))
    if (memory_budget_mb is None) != (estimated_job_memory_mb is None):
        raise ValueError("Supply both memory_budget_mb and estimated_job_memory_mb")
    if memory_budget_mb is not None:
        budget = _positive_integer(memory_budget_mb, "memory_budget_mb")
        estimate = _positive_integer(estimated_job_memory_mb, "estimated_job_memory_mb")
        if estimate > budget:
            raise ValueError("The memory budget must accommodate at least one job")
        workers = min(workers, budget // estimate)
    return workers


def run_parallel_solver_jobs(
    jobs: Iterable[PythonSolverJob], *, max_workers: int | None = None,
    threads_per_worker: int = 1, memory_budget_mb: int | None = None,
    estimated_job_memory_mb: int | None = None,
) -> tuple[PythonSolverJobOutcome, ...]:
    """Run independent CPU analyses, returning outcomes in input order.

    Each job gets a fresh interpreter with Numba and BLAS thread limits set
    before import. Analysis dependencies stay sequential inside that process.
    Optional memory estimates cap concurrency; they are not OS memory limits.
    Timeouts include interpreter startup, loading, preparation and solving.
    """
    threads = _positive_integer(threads_per_worker, "threads_per_worker")
    workers = _worker_limit(max_workers, threads, memory_budget_mb, estimated_job_memory_mb)
    pending = tuple(jobs)
    for job in pending:
        if not math.isfinite(job.timeout_seconds) or job.timeout_seconds <= 0:
            raise ValueError("Each job timeout_seconds must be finite and positive")
        # Catch nonportable callback/local-class requests before starting workers.
        pickle.dumps(job)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return tuple(executor.map(lambda job: _launch_job(job, threads), pending))


def _launch_job(
    job: PythonSolverJob, threads: int, *, environment: dict[str, str] | None = None,
    stream_output: bool = False,
) -> PythonSolverJobOutcome:
    started = time.perf_counter()
    if environment is None:
        environment = SolverResources(threads, threads, blas_directory=None).environment()
        # Ordinary batch jobs retain their previous native-library selection.
        if "LD_LIBRARY_PATH" not in os.environ:
            environment.pop("LD_LIBRARY_PATH", None)
        else:
            environment["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    with TemporaryDirectory(prefix="histra-job-") as directory:
        request, response = Path(directory) / "request.pkl", Path(directory) / "response.pkl"
        request.write_bytes(pickle.dumps(job))
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "histra.solver._job_worker", str(request), str(response)],
                env=environment, capture_output=not stream_output, text=True, timeout=job.timeout_seconds,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Worker exited {completed.returncode}: {(completed.stderr or "See worker output")[-4000:]}")
            outcome = pickle.loads(response.read_bytes())
            return replace(outcome, runtime_seconds=time.perf_counter() - started)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            return PythonSolverJobOutcome(None, f"{type(exc).__name__}: {exc}", time.perf_counter() - started)


def _execute_job(job: PythonSolverJob) -> PythonSolverJobOutcome:
    started = time.perf_counter()
    try:
        from histra.solver.resources import validate_native_blas

        validate_native_blas()
        stream = os.environ.get("HISTRA_WORKER_STREAM_OUTPUT") == "1"
        # Leave a small part of the hard deadline for exporting committed work
        # after cooperative timeout. The launcher still enforces the full limit.
        export_reserve = min(30.0, job.timeout_seconds * 0.05) if job.output_directory is not None else 0.0
        result = run_python_solver_job(
            job.model_path, job.analyses, timeout_seconds=job.timeout_seconds - export_reserve,
            interface_mutations=job.interface_mutations, combination_row=job.combination_row,
            equilibrium_policy=job.equilibrium_policy, strategy_policy=job.strategy_policy,
            output_directory=job.output_directory,
            on_log=(lambda message: print(message, flush=True)) if stream else None,
        )
        from histra.solver.resources import inspect_process_resources

        metadata = dict(result.metadata, resources=inspect_process_resources())
        result = replace(result, metadata=metadata)
        return PythonSolverJobOutcome(result, None, time.perf_counter() - started, os.getpid())
    except Exception as exc:
        return PythonSolverJobOutcome(None, f"{type(exc).__name__}: {exc}",
                                      time.perf_counter() - started, os.getpid())


def run_large_solver_job(
    job: PythonSolverJob, *, resources: SolverResources | None = None, stream_output: bool = False,
) -> PythonSolverJobOutcome:
    """Give one model separate kernel/BLAS teams and optional native OpenBLAS.

    The subprocess retains compiled-only enforcement, authored analysis settings
    and equilibrium checks. A backend change still needs full-history validation.
    """
    if not math.isfinite(job.timeout_seconds) or job.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    pickle.dumps(job)
    selected = resources if resources is not None else SolverResources()
    environment = selected.environment()
    environment["HISTRA_WORKER_STREAM_OUTPUT"] = "1" if stream_output else "0"
    return _launch_job(job, int(environment["HISTRA_NUMBA_THREADS"]),
                       environment=environment, stream_output=stream_output)
