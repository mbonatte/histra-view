"""Export native wall modal rows read-only; no native mesh enters Python solves."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import sqlite3
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_commit": commit,
        "generator": "tools/benchmarks/export_masonry_modal_reference.py",
        "benchmark_id": "four-wall-masonry-2026.1.1",
        "native_version": "2026.1.1",
        "cases": {},
    }
    for folder in sorted(p for p in args.kit.iterdir() if p.is_dir()):
        name = folder.name
        source = folder / (name + ".hrx")
        reference = folder / "csharp" / (name + ".Results")
        case = {
            "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "results_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "analyses": {},
        }
        report["cases"][name] = case
        with sqlite3.connect(reference.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            for key in (3, 4):
                modes = []
                case["analyses"][str(key)] = {"requested_modes": 6, "modes": modes}
                for row in db.execute(
                    "SELECT * FROM ModalValues WHERE AnalysisKey=? ORDER BY Step", (key,)
                ):
                    shape = [v[0] for v in db.execute(
                        "SELECT Val FROM ModalShapeValues WHERE AnalysisKey=? AND Step=? ORDER BY Dof",
                        (key, row["Step"]),
                    )]
                    modes.append({
                        "values": {k: row[k] for k in row.keys() if row[k] is not None},
                        "shape": shape,
                    })
        if hashlib.sha256(reference.read_bytes()).hexdigest() != case["results_sha256"]:
            raise RuntimeError(f"Native reference changed during export: {reference}")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
