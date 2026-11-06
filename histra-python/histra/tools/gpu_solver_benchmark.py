"""Compare CPU/cuDSS precision and blocking wall time on identical sparse systems."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import scipy.sparse as sp

from histra.types.linear_system import LinearSystem


def error_metrics(reference, candidate, *, atol=1e-9, rtol=1e-9):
    """Relative Linf uses the reference's largest magnitude, including near zero."""
    reference, candidate = np.asarray(reference, dtype=np.float64), np.asarray(candidate, dtype=np.float64)
    valid = (reference.shape == candidate.shape
             and np.all(np.isfinite(reference)) and np.all(np.isfinite(candidate)))
    if not valid:
        return {"max_absolute": None, "relative_linf": None, "within_tolerance": False}
    with np.errstate(over="ignore", invalid="ignore"):
        error = float(np.max(np.abs(candidate - reference), initial=0.0))
    scale = float(np.max(np.abs(reference), initial=0.0))
    relative = error / scale if scale else (0.0 if error == 0.0 else None)
    return {
        "max_absolute": error if np.isfinite(error) else None,
        "relative_linf": relative if relative is not None and np.isfinite(relative) else None,
        "within_tolerance": bool(np.isfinite(error) and np.allclose(candidate, reference, atol=atol, rtol=rtol)),
    }


def provenance(benchmark_id):
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        gpu_inventory = gpu.stdout.strip() if gpu.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        gpu_inventory = None
    packages = {}
    for name in ("histra-python", "numpy", "scipy", "numba", "nvmath-python", "nvidia-cudss-cu12"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit, "working_tree_dirty": dirty,
        "generator": "histra.tools.gpu_solver_benchmark", "benchmark_id": benchmark_id,
        "platform": platform.platform(), "processor": platform.processor(),
        "gpu_inventory": gpu_inventory, "python": platform.python_version(), "packages": packages,
        "cudss_mode": os.environ.get("HISTRA_CUDSS_MODE", "deterministic"),
    }


def _measure(matrix, rhs, backend):
    with LinearSystem(matrix.shape[0], backend=backend) as system:
        # UMFPACK retains a writable view of its first numeric values and updates
        # that buffer during refactorization. Each sample must own its matrix so
        # scaling one trial cannot change the next trial or the residual reference.
        system.k = matrix.copy()
        started = time.perf_counter()
        system.solve(rhs=rhs)
        first = time.perf_counter() - started
        solutions = {"first": system.x.copy()}
        started = time.perf_counter()
        system.solve(rhs=rhs)
        reused = time.perf_counter() - started
        solutions["reused"] = system.x.copy()
        started = time.perf_counter()
        system.k = matrix.copy()
        system.k.data *= 1.01
        system.solve(rhs=rhs)
        refactor = time.perf_counter() - started
        solutions["refactored"] = system.x.copy()
        return {
            "backend": system._factor_backend,
            "first_solve_seconds": first, "reused_rhs_seconds": reused,
            "numeric_refactor_solve_seconds": refactor,
        }, solutions


def _sample_precision(matrix, rhs, reference, samples, atol, rtol):
    results = []
    for _, solutions in samples:
        phases = {}
        for phase, solution in solutions.items():
            scale = 1.01 if phase == "refactored" else 1.0
            phases[phase] = {
                "solution": error_metrics(reference / scale, solution, atol=atol, rtol=rtol),
                "residual": error_metrics(rhs, scale * (matrix @ solution), atol=atol, rtol=rtol),
            }
        results.append(phases)
    return results


def compare_linear_systems(matrix, rhs, *, cpu_backend="superlu", candidate_backend="cudss",
                           repeats=3, atol=1e-9, rtol=1e-9):
    if repeats < 1 or atol < 0 or rtol < 0 or not np.isfinite(atol + rtol):
        raise ValueError("repeats must be positive and tolerances finite and nonnegative")
    matrix = sp.csc_matrix(matrix, dtype=np.float64, copy=True)
    rhs = np.asarray(rhs, dtype=np.float64)
    if matrix.shape[0] == 0 or matrix.shape[0] != matrix.shape[1] or rhs.shape != (matrix.shape[0],):
        raise ValueError("Expected a nonempty square matrix and matching RHS vector")
    report = provenance("cpu-gpu-sparse-system")
    report.update({"scope": "identical_sparse_matrix", "dofs": matrix.shape[0],
                   "nnz": matrix.nnz, "atol": atol, "rtol": rtol, "runs": {}})
    samples_by_backend = {}
    for backend in dict.fromkeys((cpu_backend, candidate_backend)):
        try:
            # Separate startup/context creation from the warmed repeated samples.
            cold_sample = _measure(matrix, rhs, backend)
            cold = cold_sample[0]
            samples = [_measure(matrix, rhs, backend) for _ in range(repeats)]
            samples_by_backend[backend] = [cold_sample, *samples]
            report["runs"][backend] = {
                "status": "ok", "cold": cold,
                "samples": [sample for sample, _ in samples],
                "median_seconds": {key: float(np.median([s[key] for s, _ in samples]))
                                   for key in cold if key.endswith("seconds")},
            }
        except Exception as exc:
            report["runs"][backend] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    if len(samples_by_backend) == len(set((cpu_backend, candidate_backend))):
        reference = samples_by_backend[cpu_backend][0][1]["first"]
        report["precision"] = {
            name: _sample_precision(matrix, rhs, reference, samples, atol, rtol)
            for name, samples in samples_by_backend.items()}
        report["passed"] = all(
            metric["within_tolerance"] for samples in report["precision"].values()
            for sample in samples for phase in sample.values() for metric in phase.values())
        report["speedup_first_solve"] = (
            report["runs"][cpu_backend]["median_seconds"]["first_solve_seconds"]
            / report["runs"][candidate_backend]["median_seconds"]["first_solve_seconds"])
    else:
        report["passed"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, help="SciPy sparse .npz matrix; default: synthetic tridiagonal")
    parser.add_argument("--rhs", type=Path, help="NumPy .npy RHS; default: deterministic random vector")
    parser.add_argument("--size", type=int, default=10000)
    parser.add_argument("--cpu-backend", choices=("superlu", "umfpack"), default="superlu")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--atol", type=float, default=1e-9)
    parser.add_argument("--rtol", type=float, default=1e-9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.size < 1:
        parser.error("--size must be positive")
    matrix = sp.load_npz(args.matrix) if args.matrix else sp.diags(
        [-np.ones(args.size - 1), 4 * np.ones(args.size), -np.ones(args.size - 1)],
        [-1, 0, 1], format="csc")
    rhs = np.load(args.rhs, allow_pickle=False) if args.rhs else np.random.default_rng(42).standard_normal(matrix.shape[0])
    report = compare_linear_systems(matrix, rhs, cpu_backend=args.cpu_backend,
                                    repeats=args.repeats, atol=args.atol, rtol=args.rtol)
    report["input_matrix"] = str(args.matrix.resolve()) if args.matrix else "synthetic_tridiagonal"
    output = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
    print(output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
