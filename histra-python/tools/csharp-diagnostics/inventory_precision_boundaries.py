"""Inventory original numerical source types/casts without asserting parity.

The output is a review aid: declarations, implicit promotions, overloaded
operators and expression order still require inspection and native tests.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


SOURCE_TREES = (
    "SolverRuntime", "MatrixManager", "ModelLibrary/Objects",
    "ModelLibrary/ModelManagement/ComputationalElementsOperations",
    "ModelLibrary/ModelManagement/Load",
    "ModelLibrary/ModelManagement/Material", "ModelLibrary/CommonObjectManagement",
    "UtilityLibrary/Matematics",
)
BOUNDARY = re.compile(r"\b(float|double|Vector3|Point3d|ToSingle|ToDouble)\b")


def inventory(source_root: Path) -> list[dict]:
    files = []
    for tree in SOURCE_TREES:
        directory = source_root / tree
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        for path in sorted(directory.rglob("*.cs")):
            raw = path.read_bytes()
            lines = raw.decode("utf-8-sig").splitlines()
            boundaries = [{"line": number, "text": text.strip()}
                          for number, text in enumerate(lines, 1)
                          if BOUNDARY.search(text) and not text.lstrip().startswith("//")]
            files.append({"path": path.relative_to(source_root).as_posix(),
                          "sha256": hashlib.sha256(raw).hexdigest(),
                          "boundary_candidates": boundaries})
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    files = inventory(args.source_root)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "generator": "tools/csharp-diagnostics/inventory_precision_boundaries.py",
        "benchmark_id": "csharp-precision-boundary-inventory-2026.1.1",
        "qualification": "Inventory only; includes unsupported and presentation members. No automatic parity verdict.",
        "file_count": len(files),
        "candidate_count": sum(len(item["boundary_candidates"]) for item in files),
        "files": files,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Inventoried {report['file_count']} files and {report['candidate_count']} candidate lines")


if __name__ == "__main__":
    main()
