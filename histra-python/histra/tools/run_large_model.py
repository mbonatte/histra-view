"""Run one model using separately budgeted compiled kernels and native BLAS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from histra import PythonAnalysisRequest, PythonSolverJob, SolverResources, run_large_solver_job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--analysis", default="Vert")
    parser.add_argument("--kernel-threads", type=int, default=8)
    parser.add_argument("--blas-threads", type=int, default=4)
    parser.add_argument("--blas-directory", type=Path)
    parser.add_argument("--backend", choices=("auto", "umfpack", "superlu", "cholmod", "cudss"), default="auto")
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--output", type=Path, default=Path("large_model_results"))
    args = parser.parse_args(argv)
    settings = SolverResources(args.kernel_threads, args.blas_threads, args.blas_directory, args.backend)
    request = PythonAnalysisRequest(args.analysis, None, args.timeout)
    job = PythonSolverJob(args.model.resolve(), (request,), args.timeout, output_directory=args.output.resolve())
    started = time.time()
    try:
        environment = settings.environment()
        print(f"Running {args.model}: kernels={environment['HISTRA_NUMBA_THREADS']}, "
              f"BLAS={environment['OPENBLAS_NUM_THREADS']}, backend={args.backend}", flush=True)
        print(f"Native library search: {environment.get('LD_LIBRARY_PATH', 'system default')}", flush=True)
        outcome = run_large_solver_job(job, resources=settings, stream_output=True)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    report = {"completed": outcome.completed, "wall_seconds": outcome.runtime_seconds, "error": outcome.error}
    if outcome.result is not None:
        report["resources"] = outcome.result.metadata.get("resources")
        report["exported_results"] = outcome.result.metadata.get("exported_results")
        report["analyses"] = [{"name": item.analysis_name, "outcome": item.outcome.value,
                               "committed_steps": len(item.committed_steps)}
                              for item in outcome.result.executions]
    if not outcome.completed and args.output.exists():
        report["partial_results"] = [str(path) for path in args.output.glob("*.histra")
                                     if path.stat().st_mtime >= started]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "run_summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))
    return 0 if outcome.completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
