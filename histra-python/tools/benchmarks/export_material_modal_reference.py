"""Export read-only original GUI results, preserving failed/absent stages."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import xml.etree.ElementTree as E

from tools.benchmarks.build_material_modal_reference_models import CASES
from tools.benchmarks.export_masonry_static_reference import export_state


def trace_history(kit: Path, final_u: list[float]) -> dict:
    """Identify the trace by its saved displacement prefix, not wall-clock order."""
    matches = []
    for path in sorted(kit.glob("*.tsv")):
        analysis, history, matched = None, {}, False
        for line in path.read_text().splitlines():
            if "/enter" not in line or "arg0=" not in line:
                continue
            fields = dict(s.split("=", 1) for s in line.split("\t")[2:] if "=" in s)
            message = fields["arg0"]
            if message.startswith("Start analysis: "):
                analysis = message.removeprefix("Start analysis: ")
                history[analysis] = []
                if analysis == "Modal_loaded_B" and fields.get("integrator.U", "null") != "null":
                    prefix = json.loads(fields["integrator.U"])
                    matched = bool(prefix) and prefix == final_u[:len(prefix)]
            step = re.match(r"Step (\d+) converged at iteration (\d+)", message)
            if step and analysis:
                history[analysis].append({"step": int(step[1]), "iterations": int(step[2])})
        if matched:
            matches.append({"file": path.name, "match": "Cycle_B terminal displacement prefix equals native Results", "analyses": history})
    if len(matches) != 1:
        raise ValueError(f"Expected one unambiguous native trace; found {len(matches)}")
    return matches[0]


def export_reference(kit: Path, exported_models: Path) -> dict:
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "generator": "tools/benchmarks/export_material_modal_reference.py",
        "benchmark_id": "gui-loaded-foundation-material-return-2026.1.1",
        "limitations": [
            "Step zero is initialization, never a committed static step.",
            "NULL/absent private histories are unavailable, not validated zeros.",
            "Elastic cross-law GUI restart skips incompatible saved spring rows; Python rejects this transition.",
        ],
        "cases": {},
    }
    for case in CASES:
        source = kit / case / f"{case}.hrx"
        results = kit / case / "csharp" / f"{case}.Results"
        binary = results.with_suffix(".hrb")
        exported = exported_models / case / "csharp" / f"{case}.hrx"
        root = E.parse(exported).getroot()
        hashes = {"input_lf_sha256": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                  "results_sha256": hashlib.sha256(results.read_bytes()).hexdigest(),
                  "saved_hrb_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                  "exported_hrx_sha256": hashlib.sha256(exported.read_bytes()).hexdigest()}
        entry = {**hashes, "native_version": root.get("version"), "states": [], "modal": {},
                 "analysis_states": {}, "reaction_history": []}
        report["cases"][case] = entry
        for analysis in root.findall("Analysis"):
            entry["analysis_states"][analysis.get("Key")] = [dict(s.attrib) for s in analysis.findall(".//State")]
        with sqlite3.connect(results.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            final_u = [row[1] for row in db.execute(
                "SELECT DISTINCT Dof,U FROM DynamicVectorsState WHERE AnalysisKey=2 AND Combination=1 AND Step=32 ORDER BY Dof")]
            entry["trace"] = trace_history(kit, final_u)
            for key, combination, step in db.execute(
                "SELECT DISTINCT AnalysisKey,Combination,Step FROM SpringStatesTmp "
                "WHERE AnalysisKey IN (1,2,6) AND Step>0 ORDER BY AnalysisKey,Combination,Step"
            ):
                state = {"analysis": key, "combination": combination, "step": step, "tables": {}}
                for table in ("SpringStatesTmp", "SpringStates"):
                    value = export_state(db, table, key, combination, step)
                    if value is not None:
                        state["tables"][table] = value
                entry["states"].append(state)
            for row in db.execute("SELECT * FROM ReactionSumStates WHERE Step>0 ORDER BY AnalysisKey,Combination,Step"):
                entry["reaction_history"].append({k: row[k] for k in row.keys() if k != "Id" and row[k] is not None})
            for key in (3, 4, 5, 7):
                modes = []
                entry["modal"][str(key)] = modes
                for row in db.execute("SELECT * FROM ModalValues WHERE AnalysisKey=? ORDER BY Step", (key,)):
                    shape = [v[0] for v in db.execute(
                        "SELECT Val FROM ModalShapeValues WHERE AnalysisKey=? AND Step=? ORDER BY Dof", (key, row["Step"]))]
                    modes.append({"values": {k: row[k] for k in row.keys() if k != "Id" and row[k] is not None}, "shape": shape})
        if hashlib.sha256(results.read_bytes()).hexdigest() != hashes["results_sha256"]:
            raise RuntimeError("Native results changed during export")
    report["logs"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(kit.glob("*.tsv"))}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    parser.add_argument("exported_models", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(export_reference(args.kit, args.exported_models), stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
