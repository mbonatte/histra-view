"""Inputs for native masonry backbone and committed-state transfer checks.

These are SpringHysteretic backbones, not SpringMultiLinearPlastic. Only the
three positive and three negative envelope points supported by that class
are represented. Expected responses must come from the original assemblies.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def envelope(k, positive_u, positive_f):
    return {"k": k, "u": positive_u, "f": positive_f}


def reference_inputs():
    first = envelope(1000.0, [0.01, 0.02, 0.03], [10.0, 15.0, 5.0])
    second = envelope(2000.0, [0.005, 0.015, 0.03], [10.0, 20.0, 0.0])
    replacement = envelope(2300.0, [0.01, 0.03, 0.05], [23.0, 28.0, 0.0])
    third = envelope(700.0, [0.02, 0.04, 0.06], [14.0, 16.0, 0.0])
    return {
        "backbones": [
            {"name": "hardening-softening", "definition": first,
             "strains": [0.002, 0.005, 0.008, 0.015, 0.025, 0.01, -0.02, -0.025, 0.0]},
            {"name": "asymmetric-step-sizes", "definition": second,
             "strains": [0.001, 0.004, 0.010, 0.020, -0.010, -0.025, 0.0]},
            {"name": "linear-backbone", "definition": envelope(
                5000.0, [0.002, 0.004, 0.006], [10.0, 20.0, 30.0]),
             "strains": [0.0002, 0.0005, 0.001, 0.002, 0.005, -0.001]},
        ],
        "transfers": [
            {"name": "virgin", "definition": first, "strains": [],
             "targets": [replacement], "continuations": [[0.001, 0.015, -0.02]]},
            {"name": "tensile-plastic", "definition": first,
             "strains": [0.005, 0.015, 0.025], "targets": [replacement],
             "continuations": [[0.025, 0.01, -0.02, 0.0, 0.03]]},
            {"name": "reversed-repeated-reset", "definition": second,
             "strains": [0.01, -0.02, 0.005], "f0": 0.125,
             "targets": [replacement, third],
             "continuations": [[0.012, -0.025], [-0.01, 0.02, 0.0]]},
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(reference_inputs(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
