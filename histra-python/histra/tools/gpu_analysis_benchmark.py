"""Compare fresh CPU/GPU static chains, including every committed runtime state."""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import time

import numpy as np

from histra import AnalysisSession, load_model
from histra.solver import ModelManager
from histra.solver.backend_coverage import _resolve_linear_solver_backend
from histra.tools.gpu_solver_benchmark import error_metrics, provenance


_RESPONSE_FIELDS = (
    "u", "load_factor", "reaction_x", "reaction_y", "reaction_z",
    "elastic_energy", "dissipated_energy", "residual_norm", "convergence_error",
    "equilibrium_force_error_norm", "equilibrium_residual_norm",
)
_BEHAVIOR_FIELDS = ("step", "status", "exit_code", "iterations", "equilibrium_ok")


def _capture_state(model):
    from histra.solver.hysteretic_kernels.interface_coulomb import CCPHASE
    from histra.solver.hysteretic_kernels.quad_takeda import QPHASE, QHCOMMITTED

    runtime = ModelManager.hysteretic_batch_for(model)
    if runtime is None or not runtime.active:
        raise RuntimeError("Compiled runtime unavailable during precision capture")
    state = {f"runtime/{index}": array for index, array in enumerate(runtime.snapshot())}
    state["phase/transverse"] = runtime.committed[:, 8].copy()
    state["phase/coulomb"] = runtime.coulomb_state[:, CCPHASE].copy()
    state["phase/quad"] = runtime.quad_state[:, [QPHASE, QHCOMMITTED + 8]].copy()
    return state


def _run_chain(path, target, backend, max_steps):
    started = time.perf_counter()
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    preparation = time.perf_counter() - started
    session = AnalysisSession(model, linear_solver_backend=backend,
                              linear_solver_precision="accurate", strategy_policy="off")
    chain = session.dependency_chain(target)
    if any(int(a.analysis_type) == 5 for a in chain):
        raise ValueError("GPU comparison currently supports static chains only; modal uses CPU")
    # Explicit controls override any private backend attributes carried by a model.
    for analysis in chain:
        analysis.linear_solver_backend = backend
    executions, frames = [], []
    capture_seconds = 0.0

    def capture(step, analysis_definition):
        nonlocal capture_seconds
        tick = time.perf_counter()
        state = _capture_state(model)
        frames.append(state)
        capture_seconds += time.perf_counter() - tick

    tick = time.perf_counter()
    for analysis in chain:
        result = session.run(analysis, max_committed_steps=max_steps, on_step_committed=capture)
        executions.append(result)
        if not result.completed:
            break
    wall = time.perf_counter() - tick
    summary = {
        "backend": backend, "prepare_seconds": preparation,
        "observed_solve_seconds": wall, "capture_seconds": capture_seconds,
        "solve_excluding_capture_seconds": wall - capture_seconds,
        "analyses": [{"key": e.analysis_key, "name": e.analysis_name, "code": e.code,
                      "outcome": str(e.outcome), "committed_steps": len(e.committed_steps)}
                     for e in executions],
    }
    return summary, executions, frames


def _compare_mapping(reference, candidate, fields, atol, rtol):
    results = {}
    for name in fields:
        left, right = reference.get(name), candidate.get(name)
        if left is None and right is None:
            continue
        results[name] = error_metrics(left, right, atol=atol, rtol=rtol) if (
            left is not None and right is not None) else {"within_tolerance": False}
    return results


def compare_histories(reference, candidate, *, atol=1e-9, rtol=1e-9):
    left_summary, left_executions, left_frames = reference
    right_summary, right_executions, right_frames = candidate
    behavior = left_summary["analyses"] == right_summary["analyses"]
    steps = []
    for left, right in zip(left_executions, right_executions):
        behavior &= len(left.steps) == len(right.steps)
        for a, b in zip(left.steps, right.steps):
            same = all(a.get(key) == b.get(key) for key in _BEHAVIOR_FIELDS)
            behavior &= same
            steps.append({"analysis_key": left.analysis_key, "step": a.step,
                          "same_behavior": same,
                          "fields": _compare_mapping(a, b, _RESPONSE_FIELDS, atol, rtol)})
    runtime = []
    phase_mismatches = 0
    behavior &= len(left_frames) == len(right_frames)
    for a, b in zip(left_frames, right_frames):
        behavior &= set(a) == set(b)
        runtime.append(_compare_mapping(a, b, sorted(set(a) | set(b)), atol, rtol))
        for name in a.keys() & b.keys():
            if name.startswith("phase/"):
                phase_mismatches += (int(np.count_nonzero(a[name] != b[name]))
                                     if a[name].shape == b[name].shape else 1)
    precision = all(value["within_tolerance"] for step in steps for value in step["fields"].values())
    precision &= all(value["within_tolerance"] for frame in runtime for value in frame.values())
    equilibrium_ok = all(step.get("equilibrium_ok") is not False
                         for execution in (*left_executions, *right_executions)
                         for step in execution.committed_steps)
    return {"same_behavior": bool(behavior), "phase_mismatches": phase_mismatches,
            "within_tolerance": bool(precision), "equilibrium_ok": equilibrium_ok,
            "steps": steps, "runtime_states": runtime,
            "passed": bool(left_frames and right_frames and behavior and precision
                           and phase_mismatches == 0 and equilibrium_ok)}


def _attempt_chain(path, target, backend, max_steps, report):
    try:
        # ModelManager owns process-wide arrays. A new worker for every chain
        # prevents allocator/cache history from contaminating repeated comparisons.
        with multiprocessing.get_context("spawn").Pool(processes=1) as worker:
            return worker.apply(_isolated_chain, (path, target, backend, max_steps))
    except Exception as exc:
        # Preserve the baseline and provenance if a candidate fails mid-analysis.
        report.update({"passed": False, "failed_backend": backend,
                       "error": f"{type(exc).__name__}: {exc}"})
        return None


def _isolated_chain(path, target, backend, max_steps):
    from histra.solver.warmup import warmup_compiled_backends

    warmup_compiled_backends()
    _, _, available, error = _resolve_linear_solver_backend(backend)
    if not available:
        raise RuntimeError(error)
    return _run_chain(path, target, backend, max_steps)


def compare_analyses(path, target, *, cpu_backend="superlu", repeats=1,
                     max_steps=None, atol=1e-9, rtol=1e-9, candidate_backend="cudss"):
    if repeats < 1 or (max_steps is not None and max_steps < 1):
        raise ValueError("repeats and max_steps must be positive")
    if min(atol, rtol) < 0 or not np.isfinite(atol + rtol):
        raise ValueError("Tolerances must be finite and nonnegative")
    path = Path(path).resolve()
    report = provenance("cpu-gpu-static-chain")
    report.update({"generator": "histra.tools.gpu_analysis_benchmark", "model": str(path),
                   "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "target": str(target), "atol": atol, "rtol": rtol,
                   "max_steps_per_analysis": max_steps, "scope": "static_chain",
                   "partial": max_steps is not None, "runs": {}, "comparisons": [],
                   "cudss_mode": os.environ.get("HISTRA_CUDSS_MODE", "deterministic"),
                   "repeatability": {}})
    for backend in (cpu_backend, candidate_backend):
        _, _, available, error = _resolve_linear_solver_backend(backend)
        if not available:
            report.update({"passed": False, "error": error, "unavailable_backend": backend})
            return report
    # Discard fresh-chain warmups to populate disk caches before measured workers.
    for backend in dict.fromkeys((cpu_backend, candidate_backend)):
        warmup = _attempt_chain(path, target, backend, max_steps, report)
        if warmup is None:
            return report
        report["runs"][backend] = {"warmup": warmup[0], "samples": []}
    previous = {}
    for repeat in range(repeats):
        # Alternate execution order to reduce systematic thermal/cache bias.
        order = (cpu_backend, candidate_backend) if repeat % 2 == 0 else (candidate_backend, cpu_backend)
        results = {}
        for backend in dict.fromkeys(order):
            results[backend] = _attempt_chain(path, target, backend, max_steps, report)
            if results[backend] is None:
                return report
            report["runs"][backend]["samples"].append(results[backend][0])
            if backend in previous:
                # Zero tolerance here distinguishes backend repeatability from
                # the separate CPU/GPU precision envelope and equilibrium audit.
                stable = compare_histories(previous[backend], results[backend], atol=0, rtol=0)
                report["repeatability"].setdefault(backend, []).append({
                    key: stable[key] for key in ("same_behavior", "phase_mismatches", "within_tolerance")
                })
            previous[backend] = results[backend]
        report["comparisons"].append(compare_histories(results[cpu_backend], results[candidate_backend], atol=atol, rtol=rtol))
    report["passed"] = all(value["passed"] for value in report["comparisons"])
    report["median_solve_seconds"] = {
        name: float(np.median([s["solve_excluding_capture_seconds"] for s in run["samples"]]))
        for name, run in report["runs"].items()}
    report["speedup"] = report["median_solve_seconds"][cpu_backend] / report["median_solve_seconds"][candidate_backend]
    report["median_total_seconds"] = {
        name: float(np.median([s["prepare_seconds"] + s["solve_excluding_capture_seconds"]
                              for s in run["samples"]]))
        for name, run in report["runs"].items()}
    report["total_speedup"] = report["median_total_seconds"][cpu_backend] / report["median_total_seconds"][candidate_backend]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--analysis", default="Vert", help="Target analysis name, including its HRX predecessors")
    parser.add_argument("--cpu-backend", choices=("superlu", "umfpack"), default="superlu")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-steps", type=int, help="Partial smoke test; does not qualify a complete history")
    parser.add_argument("--atol", type=float, default=1e-9)
    parser.add_argument("--rtol", type=float, default=1e-9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = compare_analyses(args.model, args.analysis, cpu_backend=args.cpu_backend,
                              repeats=args.repeats, max_steps=args.max_steps,
                              atol=args.atol, rtol=args.rtol)
    output = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
    print(output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
