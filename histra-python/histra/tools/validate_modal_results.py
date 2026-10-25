"""Compare Python modal results with a C# HiStrA SQLite ``.Results`` file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from histra.io.hr_loader import load_model
from histra.solver.modal import solve_modal_analysis
from histra.validation.modal_results import (
    ModalComparisonTolerances,
    compare_modal_result_to_csharp,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hrx", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--analysis-key", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rtol", type=float, default=5.0e-3)
    parser.add_argument("--atol", type=float, default=1.0e-4)
    parser.add_argument("--frequency-rtol", type=float, default=1.0e-4)
    parser.add_argument("--frequency-atol", type=float, default=1.0e-6)
    parser.add_argument("--mass-rtol", type=float, default=1.0e-4)
    parser.add_argument("--mass-atol", type=float, default=1.0e-6)
    parser.add_argument("--min-mac", type=float, default=0.999)
    parser.add_argument("--no-compare-shapes", action="store_true")
    args = parser.parse_args()

    model = load_model(args.hrx)
    try:
        analysis = model.collections.analyses[args.analysis_key]
    except KeyError as exc:
        raise SystemExit(f"Analysis key {args.analysis_key} is absent from the HRX.") from exc
    result = solve_modal_analysis(model, analysis, results_path=args.results)
    report = compare_modal_result_to_csharp(
        result,
        args.results,
        tolerances=ModalComparisonTolerances(
            relative=args.rtol,
            absolute=args.atol,
            frequency_relative=args.frequency_rtol,
            frequency_absolute=args.frequency_atol,
            mass_relative=args.mass_rtol,
            mass_absolute=args.mass_atol,
            minimum_mac=args.min_mac,
        ),
        compare_shapes=not args.no_compare_shapes,
    )

    text = json.dumps(report, indent=2)
    print(text)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
