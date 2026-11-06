"""Measure FP64 factorization, reused RHS and numeric refactorization separately."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time

import numpy as np
import scipy.sparse as sp

from histra.solver.resources import inspect_process_resources, validate_native_blas
from histra.types.linear_system import LinearSystem


def measure(matrix, rhs, backend):
    cpu = time.process_time()
    started = time.perf_counter()
    with LinearSystem(matrix.shape[0], backend=backend, precision="accurate") as system:
        system.k = matrix.copy()
        system.solve(rhs=rhs)
        first = time.perf_counter() - started
        solution = system.x.copy()
        factor_cpu = time.process_time() - cpu
        started = time.perf_counter()
        system.solve(rhs=rhs)
        reused = time.perf_counter() - started
        system.k = matrix.copy()
        system.k.data *= 1.001
        started = time.perf_counter()
        system.solve(rhs=rhs)
        refactor = time.perf_counter() - started
        refactor_solution = system.x.copy()
        selected = system._factor_backend
    return {"first_seconds": first, "reuse_seconds": reused, "refactor_seconds": refactor,
            "cpu_seconds": factor_cpu, "backend": selected,
            "residual_linf": float(np.max(np.abs(matrix @ solution - rhs))),
            "refactor_residual_linf": float(np.max(np.abs(1.001 * (matrix @ refactor_solution) - rhs))),
            "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, solution


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("rhs", type=Path)
    parser.add_argument("--backend", choices=("umfpack", "superlu", "cholmod", "cudss"), default="umfpack")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    validate_native_blas()
    matrix, rhs = sp.load_npz(args.matrix).tocsc(), np.load(args.rhs)
    if rhs.shape != (matrix.shape[0],) or not np.all(np.isfinite(rhs)) or not np.any(rhs):
        parser.error("RHS must be finite, nonzero and match the matrix")
    samples = []
    solution = None
    for _ in range(args.repeats):
        sample, solution = measure(matrix, rhs, args.backend)
        samples.append(sample)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": commit, "generator": "histra.tools.native_capacity_benchmark",
              "benchmark_id": "large-model-native-capacity", "resources": inspect_process_resources(),
              "matrix_sha256": hashlib.sha256(args.matrix.read_bytes()).hexdigest(),
              "rhs_sha256": hashlib.sha256(args.rhs.read_bytes()).hexdigest(),
              "dofs": matrix.shape[0], "nnz": matrix.nnz, "samples": samples,
              "median_seconds": {key: float(np.median([sample[key] for sample in samples]))
                                 for key in ("first_seconds", "reuse_seconds", "refactor_seconds")}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    np.save(args.output.with_suffix(".npy"), solution)
    print(json.dumps(report["median_seconds"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
