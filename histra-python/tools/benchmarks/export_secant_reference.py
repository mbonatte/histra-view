"""Export independent native ArcLength output and actual tangent choices."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from tools.benchmarks.export_masonry_static_reference import export_state


def newton_calls(path):
    calls = []
    active = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        label = parts[1]
        fields = dict(part.split("=", 1) for part in parts[2:] if "=" in part)
        if label == "SolverRuntime.NumericalProcedure.NewtonRaphson.solveCurrentStep/enter":
            active = {"analysis": int(fields["analysis.Key"]), "step": int(fields["arg5"]),
                      "alpha": float(fields["arg6"]), "iterations": 0}
            calls.append(active)
        elif label == "SolverRuntime.Program.NewGraphError/enter" and active is not None:
            active["iterations"] = max(active["iterations"], int(float(fields["arg1"])))
        elif label == "SolverRuntime.NumericalProcedure.NewtonRaphson.solveCurrentStep/exit":
            active = None
    return calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--current-trace", type=Path, required=True)
    parser.add_argument("--initial-trace", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "generator": "tools/benchmarks/export_secant_reference.py",
              "benchmark_id": "native-secant-stiffness-full-execution-2026.1.1", "cases": {}}
    for name, ratio, trace in (("current", 0.4, args.current_trace), ("initial", 1.1, args.initial_trace)):
        source = args.directory / f"secant-{name}-input.hrx"
        directory = args.directory / f"native-secant-{name}"
        reference = directory / "native.Results"
        case = {"ratio": ratio, "input_lf_sha256": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                "results_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(), "calls": newton_calls(trace),
                "native_execution": json.loads((directory / "execution.json").read_text(encoding="utf-8-sig")), "states": []}
        with sqlite3.connect(reference.resolve().as_uri() + "?mode=ro", uri=True) as db:
            for key, step in db.execute("SELECT DISTINCT AnalysisKey,Step FROM SpringStatesTmp WHERE Step>0 ORDER BY AnalysisKey,Step"):
                state = {"analysis": key, "step": step, "tables": {}}
                for table in ("SpringStatesTmp", "SpringStates"):
                    result = export_state(db, table, key, 1, step)
                    if result is not None:
                        state["tables"][table] = result
                case["states"].append(state)
        report["cases"][name] = case
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
