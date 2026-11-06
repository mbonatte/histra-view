"""Read native wall Results without copying computational objects into Python."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from tools.benchmarks.masonry_spring_fingerprint import FIELDS, IDENTITY, fingerprint
from tools.benchmarks.build_masonry_reference_models import CASE_NAMES


def export_state(db, table, key, combination, step):
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    fields = [field for field in FIELDS if field in columns]
    rows = db.execute(
        f"SELECT {','.join(IDENTITY + tuple(fields))} FROM {table} "
        f"WHERE AnalysisKey=? AND Combination=? AND Step=? ORDER BY {','.join(IDENTITY)}",
        (key, combination, step),
    ).fetchall()
    if not rows:
        return None
    keys = [row[:4] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate spring identities")
    unavailable = [field for i, field in enumerate(fields) if any(row[4+i] is None for row in rows)]
    selected = [i for i, field in enumerate(fields) if field not in unavailable]
    values = [[row[4+i] for i in selected] for row in rows]
    return {"fields": [fields[i] for i in selected], "unavailable_fields": unavailable,
            **fingerprint(keys, values)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "generator": "tools/benchmarks/export_masonry_static_reference.py",
              "benchmark_id": "four-wall-static-spring-history-2026.1.1",
              "unavailable": "Native NULL spring energies and absent intermediate private histories are not qualified.",
              "cases": {}}
    for name in CASE_NAMES:
        source = args.kit / name / (name + ".hrx")
        reference = args.kit / name / "csharp" / (name + ".Results")
        case = {"input_lf_sha256": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                "results_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(), "states": []}
        report["cases"][name] = case
        with sqlite3.connect(reference.resolve().as_uri() + "?mode=ro", uri=True) as db:
            for key, combination, step in db.execute(
                "SELECT DISTINCT AnalysisKey,Combination,Step FROM SpringStatesTmp "
                "WHERE AnalysisKey IN (1,2) AND Step>0 ORDER BY AnalysisKey,Combination,Step"
            ):
                state = {"analysis": key, "combination": combination, "step": step, "tables": {}}
                for table in ("SpringStatesTmp", "SpringStates"):
                    result = export_state(db, table, key, combination, step)
                    if result is not None:
                        state["tables"][table] = result
                case["states"].append(state)
        if hashlib.sha256(reference.read_bytes()).hexdigest() != case["results_sha256"]:
            raise RuntimeError("Native Results changed during read-only export")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
