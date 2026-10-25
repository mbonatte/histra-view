"""Run one or many HRX modal analyses and optionally compare with C# results.

Single model:
    python -m histra.tools.run_modal bridge.hrx --analysis 30 \
        --output modal.json --shapes modal_shapes.npz

Batch folder/wildcard (C# ``<model>.Results`` files are discovered automatically):
    python -m histra.tools.run_modal my_model\\modal-tests\\* --analysis 30
    python -m histra.tools.run_modal my_model/modal-tests --analysis 30
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np

from histra.io.hr_loader import load_model
from histra.io.results_reader import find_results_path
from histra.solver.modal import ModalAnalysisResult, solve_modal_analysis
from histra.solver.model_manager import ModelManager
from histra.validation.modal_results import (
    ModalComparisonTolerances,
    compare_modal_result_to_csharp,
)


def _resolve_analysis(model: Any, selector: str) -> Any:
    if selector.lstrip("-").isdigit():
        key = int(selector)
        try:
            return model.collections.analyses[key]
        except KeyError as exc:
            raise ValueError(f"Analysis key {key} is absent from the HRX.") from exc
    matches = [
        analysis
        for analysis in model.collections.analyses.values()
        if str(analysis.name).casefold() == selector.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one analysis named {selector!r}; found {len(matches)}."
        )
    return matches[0]


def _has_glob_magic(value: str) -> bool:
    return glob.has_magic(value)


def _hrx_files_from_path(path: Path, *, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.casefold() == ".hrx" else []
    if path.is_dir():
        candidates = path.rglob("*") if recursive else path.iterdir()
        return [
            candidate
            for candidate in candidates
            if candidate.is_file() and candidate.suffix.casefold() == ".hrx"
        ]
    return []


def discover_hrx_inputs(specifications: Iterable[str], *, recursive: bool = False) -> list[Path]:
    """Expand HRX files, folders, and shell-independent wildcard specifications."""

    found: dict[str, Path] = {}
    for original in specifications:
        expanded = os.path.expandvars(os.path.expanduser(str(original)))
        path = Path(expanded)
        candidates: list[Path] = []
        if path.exists():
            candidates.extend(_hrx_files_from_path(path, recursive=recursive))
        elif _has_glob_magic(expanded):
            for match in glob.glob(expanded, recursive=recursive):
                matched = Path(match)
                if matched.is_file() and matched.suffix.casefold() == ".hrx":
                    candidates.append(matched)
                elif recursive and matched.is_dir():
                    candidates.extend(_hrx_files_from_path(matched, recursive=True))
        else:
            raise FileNotFoundError(f"Input does not exist and is not a matching wildcard: {original}")

        for candidate in candidates:
            try:
                key = str(candidate.resolve()).casefold()
            except OSError:
                key = str(candidate.absolute()).casefold()
            found[key] = candidate

    files = sorted(found.values(), key=lambda item: str(item).casefold())
    if not files:
        joined = ", ".join(str(item) for item in specifications)
        raise FileNotFoundError(f"No .hrx files found for: {joined}")
    return files


def _case_insensitive_results(path: Path) -> Path | None:
    direct = find_results_path(path)
    if direct is not None:
        return direct
    wanted = (path.stem + ".Results").casefold()
    if not path.parent.exists():
        return None
    for candidate in path.parent.iterdir():
        if candidate.is_file() and candidate.name.casefold() == wanted:
            return candidate
    return None


def _results_for_model(
    hrx: Path,
    *,
    explicit_results: Path | None,
    results_dir: Path | None,
    batch: bool,
) -> Path | None:
    if explicit_results is not None:
        if batch:
            if not explicit_results.is_dir():
                raise ValueError("--results must be a directory in batch mode; use --results-dir instead.")
            results_dir = explicit_results
        else:
            return explicit_results
    if results_dir is not None:
        candidate = results_dir / f"{hrx.stem}.Results"
        if candidate.exists():
            return candidate
        wanted = candidate.name.casefold()
        if results_dir.exists():
            for item in results_dir.iterdir():
                if item.is_file() and item.name.casefold() == wanted:
                    return item
        return None
    return _case_insensitive_results(hrx)


def _write_modal_outputs(
    result: ModalAnalysisResult,
    *,
    summary_path: Path | None,
    shapes_path: Path | None,
) -> None:
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(result.as_dict(include_shapes=False), indent=2),
            encoding="utf-8",
        )
        print(f"Modal summary written to {summary_path}")

    if shapes_path is not None:
        shapes_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            shapes_path,
            mode_shapes=result.mode_shapes,
            frequencies=result.frequencies,
            angular_frequencies=result.angular_frequencies,
            periods=result.periods,
            eigenvalues=np.asarray([mode.eigenvalue for mode in result.modes]),
        )
        print(f"Mode shapes written to {shapes_path}")


def _print_modal_table(result: ModalAnalysisResult) -> None:
    print(
        f"Completed {result.analysis_name}: {result.converged_modes}/"
        f"{result.requested_modes} modes, {result.dof_count} DOFs, "
        f"{result.runtime_seconds:.3f} s"
    )
    print("Mode       Fn [Hz]          T [s]       Mx [%]       My [%]       Mz [%]")
    for mode in result.modes:
        print(
            f"{mode.mode_number:4d}  {mode.frequency:14.8f}  {mode.period:13.8f}  "
            f"{mode.mass_percent_x:11.6f}  {mode.mass_percent_y:11.6f}  "
            f"{mode.mass_percent_z:11.6f}"
        )


def _common_root(paths: list[Path]) -> Path:
    # Use absolute lexical paths rather than resolve(); resolving symlinks can
    # move a batch root outside the directory the user actually selected.
    parents = [str(path.absolute().parent) for path in paths]
    try:
        return Path(os.path.commonpath(parents))
    except ValueError:
        return Path.cwd()


def _safe_relative_model_dir(hrx: Path, root: Path) -> Path:
    try:
        relative = hrx.absolute().relative_to(root.absolute())
    except ValueError:
        relative = Path(hrx.name)
    return relative.with_suffix("")


def _write_batch_csv(path: Path, models: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "model",
        "status",
        "python_runtime_seconds",
        "python_mode_count",
        "csharp_mode_count",
        "max_abs_frequency_error_hz",
        "max_abs_relative_frequency_error",
        "minimum_diagonal_mac",
        "results_path",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for item in models:
            comparison = item.get("comparison") or {}
            writer.writerow(
                {
                    "model": item.get("hrx"),
                    "status": item.get("status"),
                    "python_runtime_seconds": item.get("python_runtime_seconds"),
                    "python_mode_count": item.get("python_mode_count"),
                    "csharp_mode_count": comparison.get("csharp_mode_count"),
                    "max_abs_frequency_error_hz": comparison.get(
                        "maximum_absolute_frequency_error_hz"
                    ),
                    "max_abs_relative_frequency_error": comparison.get(
                        "maximum_absolute_relative_frequency_error"
                    ),
                    "minimum_diagonal_mac": comparison.get("minimum_diagonal_mac"),
                    "results_path": item.get("results_path"),
                    "error": item.get("error"),
                }
            )


def _prepare_for_modal_validation(model: Any, mode: str) -> bool:
    """Apply the requested preprocessing policy and return solver auto-prepare."""

    if mode == "force":
        print("Regenerating computational interfaces/springs with Python preprocessing.")
        ModelManager.prepare_model(model, force=True)
        return False
    if mode == "stored":
        return False
    return True


def _run_single(args: argparse.Namespace, hrx: Path) -> int:
    model = load_model(hrx)
    try:
        analysis = _resolve_analysis(model, args.analysis)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    results = _results_for_model(
        hrx,
        explicit_results=args.results,
        results_dir=args.results_dir,
        batch=False,
    )
    auto_prepare = _prepare_for_modal_validation(model, args.preprocessing_mode)
    result = solve_modal_analysis(
        model,
        analysis,
        results_path=results,
        on_log=None if args.quiet_solver else print,
        auto_prepare=auto_prepare,
    )
    _print_modal_table(result)
    _write_modal_outputs(result, summary_path=args.output, shapes_path=args.shapes)

    if args.compare or (args.results is not None and results is not None):
        if results is None:
            raise SystemExit(f"No sibling C# Results file found for {hrx}.")
        report = compare_modal_result_to_csharp(
            result,
            results,
            tolerances=args.tolerances,
            compare_shapes=not args.no_compare_shapes,
        )
        print(
            f"C# comparison: {report['status']} | "
            f"max |dF|={report['maximum_absolute_frequency_error_hz']:.6g} Hz | "
            f"max |dF/F|={report['maximum_absolute_relative_frequency_error']:.6g}"
            + (
                f" | min MAC={report['minimum_diagonal_mac']:.8f}"
                if report["minimum_diagonal_mac"] is not None
                else ""
            )
        )
        if args.comparison_output is not None:
            args.comparison_output.parent.mkdir(parents=True, exist_ok=True)
            args.comparison_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"Comparison report written to {args.comparison_output}")
        return 0 if report["passed"] else 1
    return 0


def _run_batch(args: argparse.Namespace, hrx_files: list[Path]) -> int:
    root = _common_root(hrx_files)
    output_dir = args.output_dir or (root / "modal-comparison")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = args.report_json or (output_dir / "comparison.json")
    report_csv = args.report_csv or (output_dir / "comparison.csv")

    records: list[dict[str, Any]] = []
    for index, hrx in enumerate(hrx_files, start=1):
        print("\n" + "=" * 88)
        print(f"[{index}/{len(hrx_files)}] {hrx}")
        print("=" * 88)
        record: dict[str, Any] = {"hrx": str(hrx), "status": "ERROR"}
        try:
            model = load_model(hrx)
            analysis = _resolve_analysis(model, args.analysis)
            results = _results_for_model(
                hrx,
                explicit_results=args.results,
                results_dir=args.results_dir,
                batch=True,
            )
            record["analysis_key"] = int(analysis.key)
            record["analysis_name"] = str(analysis.name)
            record["results_path"] = str(results) if results is not None else None

            auto_prepare = _prepare_for_modal_validation(model, args.preprocessing_mode)
            record["preprocessing_mode"] = args.preprocessing_mode
            result = solve_modal_analysis(
                model,
                analysis,
                results_path=results,
                on_log=None if args.quiet_solver else print,
                auto_prepare=auto_prepare,
            )
            record["python_runtime_seconds"] = result.runtime_seconds
            record["python_mode_count"] = result.converged_modes
            _print_modal_table(result)

            model_dir = output_dir / "models" / _safe_relative_model_dir(hrx, root)
            _write_modal_outputs(
                result,
                summary_path=model_dir / "python-modal-summary.json",
                shapes_path=(model_dir / "python-modal-shapes.npz") if args.save_shapes else None,
            )

            if results is None:
                record["status"] = "NO_REFERENCE"
                record["error"] = f"No matching {hrx.stem}.Results file found."
                print(f"C# comparison: NO_REFERENCE - {record['error']}")
            else:
                comparison = compare_modal_result_to_csharp(
                    result,
                    results,
                    tolerances=args.tolerances,
                    compare_shapes=not args.no_compare_shapes,
                )
                record["comparison"] = comparison
                record["status"] = comparison["status"]
                (model_dir / "comparison.json").write_text(
                    json.dumps(comparison, indent=2), encoding="utf-8"
                )
                message = (
                    f"C# comparison: {comparison['status']} | "
                    f"max |dF|={comparison['maximum_absolute_frequency_error_hz']:.6g} Hz | "
                    f"max |dF/F|={comparison['maximum_absolute_relative_frequency_error']:.6g}"
                )
                if comparison["minimum_diagonal_mac"] is not None:
                    message += f" | min MAC={comparison['minimum_diagonal_mac']:.8f}"
                print(message)
        except (Exception, KeyboardInterrupt) as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            record["status"] = "ERROR"
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR: {record['error']}", file=sys.stderr)
            if args.fail_fast:
                records.append(record)
                break
        records.append(record)

    counts = {
        status: sum(1 for item in records if item["status"] == status)
        for status in ("PASS", "FAIL", "NO_REFERENCE", "ERROR")
    }
    batch_passed = len(records) == len(hrx_files) and counts["PASS"] == len(hrx_files)
    batch_report = {
        "status": "PASS" if batch_passed else "FAIL",
        "passed": batch_passed,
        "analysis_selector": args.analysis,
        "preprocessing_mode": args.preprocessing_mode,
        "model_count": len(hrx_files),
        "processed_count": len(records),
        "counts": counts,
        "tolerances": {
            "relative": args.tolerances.relative,
            "absolute": args.tolerances.absolute,
            "frequency_relative": args.tolerances.frequency_relative,
            "frequency_absolute": args.tolerances.frequency_absolute,
            "mass_relative": args.tolerances.mass_relative,
            "mass_absolute": args.tolerances.mass_absolute,
            "minimum_mac": args.tolerances.minimum_mac,
        },
        "compare_shapes": not args.no_compare_shapes,
        "models": records,
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(batch_report, indent=2), encoding="utf-8")
    _write_batch_csv(report_csv, records)

    print("\n" + "=" * 88)
    print(
        f"BATCH {batch_report['status']}: {counts['PASS']} passed, {counts['FAIL']} failed, "
        f"{counts['NO_REFERENCE']} without C# Results, {counts['ERROR']} errors."
    )
    print(f"JSON report: {report_json}")
    print(f"CSV report:  {report_csv}")
    print(f"Per-model outputs: {output_dir / 'models'}")
    return 0 if batch_passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="+",
        help="HRX file(s), folder(s), or wildcard(s). Wildcards are expanded by Python on Windows.",
    )
    parser.add_argument("--analysis", required=True, help="Modal analysis key or exact name")
    parser.add_argument(
        "--results",
        type=Path,
        help=(
            "Single C# .Results database. In batch mode this may instead be a directory "
            "containing same-stem .Results files."
        ),
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Directory containing C# <HRX-stem>.Results files for batch comparison.",
    )
    parser.add_argument("--recursive", action="store_true", help="Recurse into input directories.")
    parser.add_argument(
        "--preprocessing",
        choices=("auto", "force", "stored"),
        help=(
            "Computational-model policy. Batch default: force (regenerate Python springs so "
            "the comparison is end-to-end). Single-model default: auto. Use stored to test "
            "only the solver with already-prepared HRX springs."
        ),
    )

    # Backward-compatible single-model outputs.
    parser.add_argument("--output", type=Path, help="Single model: write modal summary JSON.")
    parser.add_argument("--shapes", type=Path, help="Single model: write compressed NPZ mode shapes.")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Single model: compare automatically with its sibling C# .Results file.",
    )
    parser.add_argument(
        "--comparison-output",
        type=Path,
        help="Single model: write the C#/Python comparison JSON.",
    )

    # Batch outputs.
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Batch output directory (default: <models-root>/modal-comparison).",
    )
    parser.add_argument("--report-json", type=Path, help="Batch consolidated JSON report path.")
    parser.add_argument("--report-csv", type=Path, help="Batch consolidated CSV report path.")
    parser.add_argument(
        "--save-shapes",
        action="store_true",
        help="Batch: also save Python mode-shape NPZ files for every model.",
    )
    parser.add_argument(
        "--no-compare-shapes",
        action="store_true",
        help="Skip ModalShapeValues/MAC comparison (faster and less I/O).",
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=5.0e-3,
        help="Relative tolerance for modal participation/effective quantities (default: 5e-3).",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=1.0e-4,
        help="Absolute tolerance for modal participation/effective quantities (default: 1e-4).",
    )
    parser.add_argument(
        "--frequency-rtol",
        type=float,
        default=1.0e-4,
        help="Relative tolerance for Wn/Fn/Tn (default: 1e-4).",
    )
    parser.add_argument(
        "--frequency-atol",
        type=float,
        default=1.0e-6,
        help="Absolute tolerance for Wn/Fn/Tn (default: 1e-6).",
    )
    parser.add_argument(
        "--mass-rtol",
        type=float,
        default=1.0e-4,
        help="Relative tolerance for total directional masses (default: 1e-4).",
    )
    parser.add_argument(
        "--mass-atol",
        type=float,
        default=1.0e-6,
        help="Absolute tolerance for total directional masses (default: 1e-6).",
    )
    parser.add_argument(
        "--min-mac",
        type=float,
        default=0.999,
        help="Minimum diagonal Modal Assurance Criterion for mode shapes (default: 0.999).",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop batch at the first error.")
    parser.add_argument(
        "--quiet-solver",
        action="store_true",
        help="Hide preprocessing/eigensolver iteration log messages.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.tolerances = ModalComparisonTolerances(
            relative=args.rtol,
            absolute=args.atol,
            frequency_relative=args.frequency_rtol,
            frequency_absolute=args.frequency_atol,
            mass_relative=args.mass_rtol,
            mass_absolute=args.mass_atol,
            minimum_mac=args.min_mac,
        )
        hrx_files = discover_hrx_inputs(args.inputs, recursive=args.recursive)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    input_implies_batch = len(args.inputs) != 1 or any(
        _has_glob_magic(value) or Path(value).is_dir() for value in args.inputs
    )
    batch = input_implies_batch or len(hrx_files) > 1
    args.preprocessing_mode = args.preprocessing or ("force" if batch else "auto")
    if batch and (args.output is not None or args.shapes is not None or args.comparison_output is not None):
        parser.error(
            "--output, --shapes and --comparison-output are single-model options. "
            "Use --output-dir/--report-json/--report-csv in batch mode."
        )
    if not batch and args.save_shapes:
        parser.error("--save-shapes is a batch option; use --shapes for a single model.")

    if batch:
        return _run_batch(args, hrx_files)
    return _run_single(args, hrx_files[0])


if __name__ == "__main__":
    raise SystemExit(main())
