"""Run independent HRX models on bounded CPU workers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from histra import PythonAnalysisRequest, PythonSolverJob, run_parallel_solver_jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--analysis", default="Vert")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    request = PythonAnalysisRequest(args.analysis, None, args.timeout)
    jobs = [PythonSolverJob(path, (request,), args.timeout) for path in args.models]
    started = time.perf_counter()
    try:
        outcomes = run_parallel_solver_jobs(jobs, max_workers=args.workers,
                                           threads_per_worker=args.threads)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    report = {"wall_seconds": time.perf_counter() - started, "jobs": []}
    for path, outcome in zip(args.models, outcomes):
        entry = {"model": str(path), "completed": outcome.completed,
                 "wall_seconds": outcome.runtime_seconds, "error": outcome.error}
        if outcome.result is not None:
            entry["analyses"] = [
                {"name": execution.analysis_name, "outcome": execution.outcome.value,
                 "committed_steps": len(execution.committed_steps)}
                for execution in outcome.result.executions
            ]
        report["jobs"].append(entry)
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if all(outcome.completed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
