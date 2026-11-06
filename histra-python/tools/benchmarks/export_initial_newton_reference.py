"""Export the first native current-tangent Newton system from binary tracing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("execution", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    provenance = json.loads(args.execution.read_text(encoding="utf-8-sig"))
    arrays = {}
    hashes = {}
    for field in ("Ap", "Ai", "Ax", "b", "x"):
        # NewGraphError(0) follows initial residual assembly; (1) follows the
        # first update/residual, retaining the actual solved matrix and LS.x.
        frame = 0 if field == "b" else 1
        path = args.capture / f"newton-{frame:05d}-{field}.bin"
        arrays[field] = np.fromfile(path, dtype="<i4" if field in ("Ap", "Ai") else "<f8").tolist()
        hashes[field] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "generator": "tools/benchmarks/export_initial_newton_reference.py",
              "benchmark_id": "native-isotropic-first-current-tangent-newton-2026.1.1",
              "native_execution": provenance, "binary_sha256": hashes, "arrays": arrays}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
