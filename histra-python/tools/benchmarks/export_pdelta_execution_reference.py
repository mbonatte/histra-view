"""Export native P-Delta chains with both update and output-save intervals."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from tools.benchmarks.export_masonry_static_reference import export_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "generator": "tools/benchmarks/export_pdelta_execution_reference.py",
              "benchmark_id": "native-pdelta-full-execution-2026.1.1", "cases": {}}
    for mode in ("EachStep", "EachIteration"):
        for save in (1, 2):
            suffix = mode + ("-save2" if save == 2 else "")
            source = args.directory / f"pdelta-{suffix}-input.hrx"
            directory = args.directory / f"native-pdelta-{suffix}"
            reference = directory / "native.Results"
            case = {"mode": mode, "step_save": save,
                    "input_lf_sha256": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                    "results_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                    "native_execution": json.loads((directory / "execution.json").read_text(encoding="utf-8-sig")),
                    "states": [], "committed_steps": {}}
            with sqlite3.connect(reference.resolve().as_uri() + "?mode=ro", uri=True) as db:
                # The final private state can be beyond AnalysisState.Step,
                # which C# truncates to the last regular StepSave boundary.
                for key, step in db.execute(
                    "SELECT AnalysisKey,Step FROM SpringStatesTmp WHERE Step>0 "
                    "UNION SELECT AnalysisKey,Step FROM SpringStates WHERE Step>0 ORDER BY AnalysisKey,Step"
                ):
                    state = {"analysis": key, "step": step, "tables": {}}
                    for table in ("SpringStatesTmp", "SpringStates"):
                        result = export_state(db, table, key, 1, step)
                        if result is not None:
                            state["tables"][table] = result
                    case["states"].append(state)
                    case["committed_steps"][str(key)] = max(step, case["committed_steps"].get(str(key), 0))
            report["cases"][f"{mode}-save{save}"] = case
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
