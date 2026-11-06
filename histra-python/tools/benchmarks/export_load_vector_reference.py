"""Package successful fresh native load-oracle outputs for portable tests."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    cases = []
    for path in sorted(args.run_directory.glob("*/unrun.hrx")):
        root = ET.parse(path).getroot()
        condition = root.find("LoadCondition")
        analysis = root.find("Analysis")
        vectors = {}
        for key in (1, 2, 3, 4):
            binary = path.parent / str(key) / "native-Vert-Ptarget.bin"
            vectors[str(key)] = np.fromfile(binary, dtype=np.float64).tolist()
            if len(vectors[str(key)]) != 28:
                raise ValueError(f"Incomplete oracle output: {binary}")
        cases.append({
            "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "input_lf_sha256": hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "fractional_direction": float(analysis.get("DirX")) != 0.0,
            "mass_factors": [float(condition.get(f"MassInDir{axis}")) for axis in "XYZ"],
            "vectors": vectors,
        })
    if len(cases) != 4:
        raise ValueError("Expected all four successful fractional/mass-factor cases")
    report = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "generator": "tools/benchmarks/export_load_vector_reference.py",
        "benchmark_id": "native-fresh-load-precision-2026.1.1",
        "native_generator": "tools/csharp-diagnostics/Invoke-FreshConstructionOracle.ps1",
        "cases": cases,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
