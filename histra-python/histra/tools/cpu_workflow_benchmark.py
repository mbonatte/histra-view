"""Measure cold/warm CPU workflow phases and save exact history audit arrays.

Run this file directly with --source-root to compare separate source revisions
using the same interpreter, inputs and benchmark harness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time


def _run(path, fast, max_steps):
    import numpy as np
    from histra import AnalysisSession, load_model
    from histra.solver import ModelManager

    if fast:
        from histra import load_solver_model
        loader = load_solver_model
    else:
        loader = load_model
    started = time.perf_counter()
    model = loader(path)
    loaded = time.perf_counter()
    ModelManager.prepare_model(model, force=True)
    prepared = time.perf_counter()
    session = AnalysisSession(model, equilibrium_policy="off", strategy_policy="off")
    result = session.run("Vert", max_committed_steps=max_steps)
    finished = time.perf_counter()
    arrays = {}
    for index, step in enumerate(result.steps):
        for key in ("u", "load_factor", "reaction_x", "reaction_y", "reaction_z",
                    "iterations", "residual_norm", "convergence_error", "elastic_energy",
                    "dissipated_energy", "equilibrium_residual_norm"):
            value = step.get(key)
            if value is not None:
                arrays[f"step/{index}/{key}"] = np.asarray(value)
    batch = ModelManager.hysteretic_batch_for(model)
    arrays.update({f"runtime/{i}": array.copy() for i, array in enumerate(batch.snapshot())})
    return {"load_seconds": loaded-started, "prepare_seconds": prepared-loaded,
            "solve_seconds": finished-prepared, "total_seconds": finished-started,
            "steps": len(result.committed_steps), "code": result.code,
            "quads": len(model.collections.quads), "dofs": model.gdl}, arrays


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    loaded_package = sys.modules.get("histra")
    if loaded_package is not None:
        loaded_root = Path(loaded_package.__file__).resolve().parents[1]
        if loaded_root != args.source_root.resolve():
            parser.error("Run this file directly to benchmark a different --source-root")
    sys.path.insert(0, str(args.source_root.resolve()))
    import numpy as np

    cold, arrays = _run(args.model, args.fast, args.max_steps)
    samples = [_run(args.model, args.fast, args.max_steps)[0] for _ in range(args.repeats)]
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "generator": "histra.tools.cpu_workflow_benchmark", "benchmark_id": "cpu-workflow",
              "source_root": str(args.source_root.resolve()), "fast_loader": args.fast,
              "model": str(args.model.resolve()), "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
              "cold": cold, "samples": samples,
              "median_seconds": {key: statistics.median(s[key] for s in samples)
                                 for key in cold if key.endswith("seconds")}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    np.savez_compressed(args.output.with_suffix(".npz"), **arrays)
    print(json.dumps(report["median_seconds"]))


if __name__ == "__main__":
    main()
