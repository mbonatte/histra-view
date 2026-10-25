"""Strict C# comparison for the local Article Models benchmark suite.

Two runs are supported:

``authored``
    Preserve every HRX convergence setting.  This reproduces the C# numerical
    path and exposes states accepted by displacement/work criteria but rejected
    by the independent equilibrium audit.

``strict``
    Select the C# ``ForceMoment`` residual criterion for every nonlinear stage
    with the measured Standard Bisection strategy, use a consistent ArcLength
    line-search projection, and tighten (never loosen) its convergence
    tolerance to the unchanged equilibrium-audit residual limit.  The warning
    policy and warning tolerances are identical to the authored run.

The command intentionally returns compact metrics from worker processes rather
than complete displacement histories.  That keeps parallel runs fast and
avoids copying every global displacement vector back to the parent process.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import hashlib
from importlib import metadata
import os
from pathlib import Path
import platform
import sys
import sqlite3
import time
from typing import Any, Iterable, Mapping, Sequence
import warnings

import numpy as np

from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession
from histra.solver.equilibrium import UnsafeEquilibriumWarning
from histra.solver.model_manager import ModelManager
from histra.solver.output_projection import compute_model_point_displacements


AUDIT_FORCE_ABSOLUTE_TOLERANCE = 1.0e-3
AUDIT_FORCE_RELATIVE_TOLERANCE = 1.0e-5
AUDIT_RESIDUAL_TOLERANCE = 1.0e-4
PARITY_REACTION_ABSOLUTE_TOLERANCE = 0.1
PARITY_DISPLACEMENT_ABSOLUTE_TOLERANCE_MM = 0.05
# Increment whenever solver semantics or release-gate policy changes.  Resume
# checkpoints are diagnostic caches, never authorities across harness changes.
BENCHMARK_HARNESS_REVISION = 7


BENCHMARK_MODELS: tuple[dict[str, Any], ...] = (
    {"id": "3.1_coarse", "name": "Bridge_3.1_Coarse", "target": "Second", "specimen": "3.1", "variant": "coarse strip", "figures": [9], "capacity_kn": 540.0, "live_load_analyses": ["First", "Second"], "master_point": 1, "direction": "Uz"},
    {"id": "3.1_multiring", "name": "Bridge_3.1_Multiring", "target": "NewAnalysis", "specimen": "3.1", "variant": "multi-ring", "figures": [9], "capacity_kn": 540.0, "live_load_analyses": ["NewAnalysis"], "master_point": 5, "direction": "Uz"},
    {"id": "3.2", "name": "Bridge_3.2", "target": "NewAnalysis", "specimen": "3.2", "variant": "ring separation", "figures": [13], "capacity_kn": 360.0, "live_load_analyses": ["NewAnalysis"], "master_point": 5, "direction": "Uz"},
    {"id": "3.3_drucker", "name": "Bridge_3.3_2_Zhang_drucker", "target": "NewAnalysis", "specimen": "3.3", "variant": "Drucker configuration", "figures": [17], "capacity_kn": 600.0, "live_load_analyses": ["NewAnalysis"], "master_point": 15, "direction": "Uz"},
    {"id": "3.3_drucker_tol", "name": "Bridge_3.3_2_Zhang_drucker_tol", "target": "NewAnalysis", "specimen": "3.3", "variant": "Drucker tight tolerance", "figures": [17], "capacity_kn": 600.0, "live_load_analyses": ["NewAnalysis"], "master_point": 15, "direction": "Uz"},
    {"id": "3.4_zhang", "name": "Bridge_3.4_Zhang", "target": "NewAnalysis", "specimen": "3.4", "variant": "Zhang/ring separation", "figures": [20], "capacity_kn": 320.0, "live_load_analyses": ["NewAnalysis"], "master_point": 18, "direction": "Uz"},
    {"id": "3_abutment", "name": "Bridge_3_abutment", "target": "NewAnalysis", "specimen": "3 m series", "variant": "abutment staging", "figures": [9, 13], "capacity_kn": None, "live_load_analyses": ["ConcreteBlock", "NewAnalysis"], "master_point": 7, "direction": "Uz"},
    {"id": "5.1_coarse", "name": "Bridge_5.1_coarse", "target": "NewAnalysis", "specimen": "5.1", "variant": "bare-arch coarse", "figures": [12], "capacity_kn": 1720.0, "live_load_analyses": ["NewAnalysis"], "master_point": 5, "direction": "Uz"},
    {"id": "5.1_spandrel", "name": "Bridge_5.1_load_spandrel", "target": "NewAnalysis", "specimen": "5.1", "variant": "spandrel loading", "figures": [12], "capacity_kn": 1720.0, "live_load_analyses": ["NewAnalysis"], "master_point": 3, "direction": "Uz"},
    {"id": "5.1_backfill", "name": "Bridge_5.1_load_spandrel_backfill", "target": "NewAnalysis", "specimen": "5.1", "variant": "spandrel and backfill", "figures": [12], "capacity_kn": 1720.0, "live_load_analyses": ["NewAnalysis"], "master_point": 3, "direction": "Uz"},
    {"id": "5.2_coarse", "name": "Bridge_5.2_coarse", "target": "NewAnalysis", "specimen": "5.2", "variant": "ring separation coarse", "figures": [15], "capacity_kn": 500.0, "live_load_analyses": ["NewAnalysis"], "master_point": 5, "direction": "Uz"},
    {"id": "bridge_1", "name": "Bridge_1", "target": "NewAnalysis", "specimen": "MS1", "variant": "attached spandrels", "figures": [24], "capacity_kn": 455.0, "live_load_analyses": ["NewAnalysis"], "master_point": 7, "direction": "Uz"},
    {"id": "bridge_1_layers", "name": "Bridge_1_traversal_layers", "target": "NewAnalysis", "specimen": "MS3", "variant": "transversal joint layers", "figures": [25], "capacity_kn": 325.0, "live_load_analyses": ["NewAnalysis"], "master_point": 7, "direction": "Uz"},
    {"id": "bridge_2", "name": "Bridge_2", "target": "NewAnalysis", "specimen": "MS2", "variant": "detached spandrels", "figures": [22], "capacity_kn": 320.0, "live_load_analyses": ["NewAnalysis"], "master_point": 3, "direction": "Uz"},
)

ARTICLE_FIGURES = (9, 12, 13, 15, 17, 20, 22, 24, 25)
ARTICLE_TABLE_1_CAPACITIES_KN = {
    "3.1": 540.0, "3.2": 360.0, "3.3": 600.0, "3.4": 320.0,
    "5.1": 1720.0, "5.2": 500.0, "MS1": 455.0, "MS2": 320.0,
    "MS3": 325.0,
}

# The user-supplied ``Original_article_data.csv`` is an export of the
# ``Results`` workbook used by ``Graphs_HISTRA.ipynb``.  It has a two-row
# header beginning on CSV row 3: every named series starts a variable-width
# group of x/y (or z/x/f) columns.  Keeping this mapping in the harness makes
# the published-figure selection reviewable without duplicating or rounding
# the original data into nine hand-maintained CSV files.
ARTICLE_WORKBOOK_EXPORT = "Original_article_data.csv"
ARTICLE_GRAPH_NOTEBOOK = "Graphs_HISTRA.ipynb"
ARTICLE_SOURCE_SERIES: Mapping[int, tuple[Mapping[str, Any], ...]] = {
    9: (
        {"source": "3.1_Experimental", "cell": 9},
        {"source": "Bridge_3.1_Coarse", "cell": 9},
        {"source": "Bridge_3.1_Multiring", "cell": 9},
        {"source": "Bridge_3.1_Zhang", "cell": 9},
        {"source": "LimitAnalysis_3.1", "cell": 9},
    ),
    12: (
        {"source": "Bridge_5.1_Experimental", "cell": 37},
        {"source": "Bridge_5.1_Masonry_new", "cell": 37, "drop_last": 17},
        {"source": "Bridge_5.1_Load_spandrel", "cell": 37},
        {"source": "LimitAnalysis_5.1", "cell": 37},
    ),
    13: (
        {"source": "Bridge_3.2_Experimental", "cell": 13},
        {"source": "Bridge_3.2_Sand", "cell": 13},
    ),
    15: (
        {"source": "Bridge_5.2_Experimental", "cell": 39},
        {"source": "Bridge_5.2_Numerical_Coarse", "cell": 39},
        {"source": "LimitAnalysis_5.2", "cell": 39},
    ),
    17: (
        {"source": "3.3_Experimental", "cell": 15},
        {"source": "3.3_FEM (Zhang)", "cell": 15},
        {"source": "3.3_Numerical_drucker_z", "cell": 15},
    ),
    20: (
        {"source": "Bridge_3.4_Experimental", "cell": 33},
        {"source": "3-4_Numerical_new", "cell": 33},
        {"source": "3.3_Numerical_drucker_z", "cell": 33},
        {"source": "Bridge_3.2_extended", "cell": 33},
    ),
    22: (
        {"source": "Bridge_2_Experimental_Arch", "cell": 45, "location": "arch"},
        {"source": "Bridge_2_Numerical_Arch", "cell": 45, "location": "arch", "displacement": {"z": 0.916516, "x": 0.399998}, "load": "f"},
        {"source": "Bridge_2_Experimental_PierNorth", "cell": 47, "location": "pier-north"},
        {"source": "Bridge_2_Numerical_PierNorth", "cell": 47, "location": "pier-north"},
        {"source": "Bridge_2_Experimental_PierSouth", "cell": 47, "location": "pier-south"},
        {"source": "Bridge_2_Numerical_PierSouth", "cell": 47, "location": "pier-south"},
    ),
    24: (
        {"source": "Bridge_1_Experimental_PierNorth", "cell": 43, "location": "pier-north"},
        {"source": "Bridge_1_Experimental_PierSouth", "cell": 43, "location": "pier-south"},
    ),
    25: (
        {"source": "Bridge_3_Experimental_Arch", "cell": 52},
        {"source": "Bridge_3_Numerical_Zizi", "cell": 52},
        {"source": "Bridge_3_Backfill", "cell": 52},
    ),
}


def strict_convergence_tolerance(
    authored_tolerance: float,
    audit_residual_tolerance: float = AUDIT_RESIDUAL_TOLERANCE,
) -> float:
    """Return a safe ForceMoment tolerance without weakening either limit."""

    authored = float(authored_tolerance)
    audit = float(audit_residual_tolerance)
    if not np.isfinite(authored) or authored <= 0.0:
        raise ValueError("authored convergence tolerance must be finite and positive")
    if not np.isfinite(audit) or audit <= 0.0:
        raise ValueError("audit residual tolerance must be finite and positive")
    return min(authored, audit)


def _apply_strict_strategy(analysis: Any) -> None:
    """Apply the unqualified ForceMoment candidate used for strict evidence."""

    if int(getattr(analysis, "analysis_type", 0)) == 5:
        return
    analysis.adaptive_convergence_criteria = "ForceMoment"
    analysis.convergence_tolerance = strict_convergence_tolerance(
        float(analysis.convergence_tolerance)
    )
    analysis.method = "StandardBisectionLineSearch"
    analysis.csharp_line_search_compatibility = False
    if "arclength" not in str(getattr(analysis, "integration_method", "")).lower():
        analysis.als = True
    else:
        analysis.arc_length_max_cutbacks = 6
        analysis.arc_length_cutback_factor = 0.5
        analysis.desired_iterations = min(getattr(analysis, "desired_iterations", 10), 10)


def _read_csharp_reference(
    results_path: Path,
    analysis_keys: Iterable[int],
) -> tuple[
    dict[tuple[int, int], np.ndarray],
    dict[tuple[int, int, int], np.ndarray],
]:
    selected = {int(value) for value in analysis_keys}
    reactions: dict[tuple[int, int], np.ndarray] = {}
    displacements: dict[tuple[int, int, int], np.ndarray] = {}
    with sqlite3.connect(results_path) as db:
        for analysis, step, r1, r2, r3 in db.execute(
            "SELECT AnalysisKey,Step,R1,R2,R3 FROM ReactionSumStates"
        ):
            key = int(analysis)
            if key in selected:
                reactions[(key, int(step))] = np.asarray((r1, r2, r3), dtype=np.float64)
        for analysis, parent, step, ux, uy, uz in db.execute(
            "SELECT AnalysisKey,ParentKey,Step,Ux,Uy,Uz FROM DisplModelPoints"
        ):
            key = int(analysis)
            if key in selected:
                displacements[(key, int(step), int(parent))] = np.asarray(
                    (ux, uy, uz), dtype=np.float64
                )
    return reactions, displacements


def _max_steps_by_analysis(
    reactions: Mapping[tuple[int, int], np.ndarray],
) -> dict[int, int]:
    limits: dict[int, int] = {}
    for analysis, step in reactions:
        if step > 0:
            limits[analysis] = max(limits.get(analysis, 0), step)
    return limits


def _read_csharp_terminal_steps(
    results_path: Path,
    analysis_keys: Iterable[int],
) -> tuple[dict[int, int], dict[int, dict[int, int]]]:
    """Read terminal steps independently of sparse reaction/output sampling."""
    selected = {int(value) for value in analysis_keys}
    limits: dict[int, int] = {}
    phase_counts: dict[int, dict[int, int]] = {}
    with sqlite3.connect(results_path) as db:
        tables = {
            str(row[0])
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in ("ReactionSumStates", "DisplModelPoints", "SpringStates"):
            if table not in tables:
                continue
            for analysis, step in db.execute(
                f"SELECT AnalysisKey,MAX(Step) FROM {table} GROUP BY AnalysisKey"
            ):
                key = int(analysis)
                if key in selected and step is not None:
                    limits[key] = max(limits.get(key, 0), int(step))
        if "SpringStates" in tables:
            for analysis, step in limits.items():
                counts = {
                    int(phase): int(count)
                    for phase, count in db.execute(
                        "SELECT CAST(Phase AS INTEGER),COUNT(*) FROM SpringStates "
                        "WHERE AnalysisKey=? AND Step=? GROUP BY CAST(Phase AS INTEGER)",
                        (analysis, step),
                    )
                }
                if counts:
                    phase_counts[analysis] = counts
    return limits, phase_counts


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _default_article_pdf() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "docs/references/articles/Bonatte et al. - A discrete macro-element method for structural assessment of masonry arch bridges.pdf"
    )


def _read_article_workbook_export(path: Path) -> dict[str, dict[str, list[str]]]:
    """Read the variable-width, two-level CSV export without pandas.

    The workbook's curve columns deliberately have unequal lengths.  A row is
    therefore retained by the caller only when the fields selected for that
    curve are present and finite; blanks in another curve's group are normal.
    """
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    if len(rows) < 4:
        raise ValueError("workbook export requires at least four header/data rows")
    names = rows[2]
    fields = rows[3]
    starts = [index for index, name in enumerate(names) if name.strip()]
    if not starts:
        raise ValueError("workbook export has no named series in header row 3")
    result: dict[str, dict[str, list[str]]] = {}
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(names)
        name = names[start].strip()
        field_positions = [
            (index, fields[index].strip().casefold())
            for index in range(start, stop)
            if fields[index].strip()
        ]
        field_names = [field for _, field in field_positions]
        if not name or not field_names or len(set(field_names)) != len(field_names):
            raise ValueError(f"invalid field header for source series {name!r}")
        values = {field: [] for field in field_names}
        for row in rows[4:]:
            for index, field in field_positions:
                values[field].append(row[index].strip() if index < len(row) else "")
        if name in result:
            raise ValueError(f"duplicate workbook-export source series {name!r}")
        result[name] = values
    return result


def _workbook_curve(
    values: Mapping[str, list[str]], spec: Mapping[str, Any]
) -> tuple[list[tuple[float, float]], int]:
    coefficients = {
        str(field).casefold(): float(coefficient)
        for field, coefficient in dict(spec.get("displacement", {"x": 1.0})).items()
    }
    load_field = str(spec.get("load", "y")).casefold()
    required = set(coefficients) | {load_field}
    missing = sorted(required - set(values))
    if missing:
        raise ValueError(f"missing workbook field(s): {', '.join(missing)}")
    curve: list[tuple[float, float]] = []
    invalid = 0
    for index in range(len(values[load_field])):
        raw = {field: values[field][index] for field in required}
        if not all(raw.values()):
            continue
        try:
            displacement = sum(coefficients[field] * float(raw[field]) for field in coefficients)
            load = float(raw[load_field])
        except ValueError:
            invalid += 1
            continue
        if not np.isfinite(displacement) or not np.isfinite(load):
            invalid += 1
            continue
        curve.append((displacement, load))
    drop_last = int(spec.get("drop_last", 0))
    if drop_last:
        curve = curve[:-drop_last] if len(curve) > drop_last else []
    return curve, invalid


def _validate_workbook_source_data(
    directory: Path,
    issues: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the user's original workbook export and notebook selection."""
    export_path = directory / ARTICLE_WORKBOOK_EXPORT
    notebook_path = directory / ARTICLE_GRAPH_NOTEBOOK
    raw_sources: dict[str, Any] = {}
    for label, path in (("workbook_export", export_path), ("plot_notebook", notebook_path)):
        raw_sources[label] = {"path": str(path), "available": path.is_file()}
        if path.is_file():
            raw_sources[label].update({"bytes": path.stat().st_size, "sha256": _file_sha256(path)})
    if not export_path.is_file():
        issues.append(f"missing workbook export: {export_path}")
        return {}, raw_sources
    if not notebook_path.is_file():
        issues.append(f"missing plotting notebook: {notebook_path}")
    else:
        try:
            json.loads(notebook_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            issues.append(f"unable to read plotting notebook: {exc}")
    try:
        workbook = _read_article_workbook_export(export_path)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        issues.append(f"unable to read workbook export: {exc}")
        return {}, raw_sources

    figures: dict[str, Any] = {}
    for figure, specs in ARTICLE_SOURCE_SERIES.items():
        records: dict[str, Any] = {}
        invalid_rows = 0
        for spec in specs:
            source = str(spec["source"])
            values = workbook.get(source)
            if values is None:
                issues.append(f"Figure {figure} is missing workbook series {source!r}")
                continue
            try:
                curve, invalid = _workbook_curve(values, spec)
            except ValueError as exc:
                issues.append(f"Figure {figure} series {source!r}: {exc}")
                continue
            invalid_rows += invalid
            if len(curve) < 2:
                issues.append(f"Figure {figure} series {source!r} requires at least two points")
                continue
            record: dict[str, Any] = {
                "rows": len(curve),
                "provenance": f"{ARTICLE_WORKBOOK_EXPORT}:{source}; {ARTICLE_GRAPH_NOTEBOOK}:cell-{spec['cell']}",
            }
            if "location" in spec:
                record["location"] = spec["location"]
            if "displacement" in spec:
                record["displacement_formula"] = dict(spec["displacement"])
            if spec.get("drop_last"):
                record["drop_last"] = int(spec["drop_last"])
            records[source] = record
        if invalid_rows:
            issues.append(f"Figure {figure} contains {invalid_rows} non-finite workbook row(s)")
        figures[str(figure)] = {
            "path": str(export_path),
            "available": bool(records),
            "rows": sum(item["rows"] for item in records.values()),
            "series": {name: item["rows"] for name, item in sorted(records.items())},
            "series_provenance": records,
            "invalid_rows": invalid_rows,
        }
    return figures, raw_sources


def validate_article_source_data(
    directory: Path, *, article_pdf_path: Path | None = None
) -> dict[str, Any]:
    """Validate the user-supplied plotting data and Table 1 transcription."""
    directory = directory.resolve()
    issues: list[str] = []
    figures: dict[str, Any] = {}
    raw_sources: dict[str, Any] = {}
    use_workbook_export = (directory / ARTICLE_WORKBOOK_EXPORT).is_file()
    if use_workbook_export:
        figures, raw_sources = _validate_workbook_source_data(directory, issues)
    else:
        required_curve_columns = {
            "series", "displacement_mm", "load_kn", "provenance",
        }
        for figure in ARTICLE_FIGURES:
            path = directory / f"figure_{figure:02d}.csv"
            entry: dict[str, Any] = {"path": str(path), "available": path.is_file()}
            figures[str(figure)] = entry
            if not path.is_file():
                issues.append(f"missing Figure {figure} source file: {path}")
                continue
            try:
                with path.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    fields = set(reader.fieldnames or ())
                    missing_columns = sorted(required_curve_columns - fields)
                    rows = list(reader)
            except (OSError, UnicodeError, csv.Error) as exc:
                issues.append(f"unable to read Figure {figure} source file: {exc}")
                continue
            if missing_columns:
                issues.append(
                    f"Figure {figure} is missing columns: {', '.join(missing_columns)}"
                )
                continue
            series_counts: Counter[str] = Counter()
            invalid_rows = 0
            for row in rows:
                series = str(row.get("series", "")).strip()
                provenance = str(row.get("provenance", "")).strip()
                try:
                    displacement = float(row.get("displacement_mm", ""))
                    load = float(row.get("load_kn", ""))
                except (TypeError, ValueError):
                    invalid_rows += 1
                    continue
                if not series or not provenance or not np.isfinite(displacement) or not np.isfinite(load):
                    invalid_rows += 1
                    continue
                series_counts[series] += 1
            short_series = sorted(name for name, count in series_counts.items() if count < 2)
            if invalid_rows:
                issues.append(f"Figure {figure} contains {invalid_rows} invalid row(s)")
            if not series_counts:
                issues.append(f"Figure {figure} contains no valid series")
            if short_series:
                issues.append(
                    f"Figure {figure} series require at least two points: {', '.join(short_series)}"
                )
            entry.update({
                "bytes": path.stat().st_size,
                "sha256": _file_sha256(path),
                "rows": len(rows),
                "series": dict(sorted(series_counts.items())),
                "invalid_rows": invalid_rows,
            })

    table_path = directory / "table_01.csv"
    table: dict[str, Any] = {"path": str(table_path), "available": table_path.is_file()}
    if not table_path.is_file():
        if not use_workbook_export:
            issues.append(f"missing Table 1 source file: {table_path}")
        else:
            pdf_path = (article_pdf_path or _default_article_pdf()).resolve()
            table = {"path": str(pdf_path), "available": pdf_path.is_file()}
            if not pdf_path.is_file():
                issues.append(f"missing Article PDF needed for Table 1: {pdf_path}")
            else:
                table.update({
                    "bytes": pdf_path.stat().st_size,
                    "sha256": _file_sha256(pdf_path),
                    "rows": len(ARTICLE_TABLE_1_CAPACITIES_KN),
                    "capacities_kn": dict(ARTICLE_TABLE_1_CAPACITIES_KN),
                    "provenance": "Bonatte et al. (2026), Table 1",
                })
    else:
        try:
            with table_path.open("r", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = set(reader.fieldnames or ())
                rows = list(reader)
        except (OSError, UnicodeError, csv.Error) as exc:
            issues.append(f"unable to read Table 1 source file: {exc}")
            rows = []
            fields = set()
        required_table_columns = {"specimen", "capacity_kn", "provenance"}
        missing_columns = sorted(required_table_columns - fields)
        capacities: dict[str, float] = {}
        if missing_columns:
            issues.append(f"Table 1 is missing columns: {', '.join(missing_columns)}")
        else:
            for row in rows:
                specimen = str(row.get("specimen", "")).strip()
                provenance = str(row.get("provenance", "")).strip()
                try:
                    capacity = float(row.get("capacity_kn", ""))
                except (TypeError, ValueError):
                    capacity = float("nan")
                if (
                    not specimen or not provenance or not np.isfinite(capacity)
                    or specimen in capacities
                ):
                    issues.append(f"Table 1 contains an invalid or duplicate row for {specimen!r}")
                    continue
                capacities[specimen] = capacity
            for specimen, expected in ARTICLE_TABLE_1_CAPACITIES_KN.items():
                actual = capacities.get(specimen)
                if actual is None:
                    issues.append(f"Table 1 is missing specimen {specimen}")
                elif abs(actual - expected) > 0.1:
                    issues.append(
                        f"Table 1 specimen {specimen} is {actual:g} kN; expected {expected:g} kN"
                    )
        table.update({
            "bytes": table_path.stat().st_size,
            "sha256": _file_sha256(table_path),
            "rows": len(rows),
            "capacities_kn": capacities,
        })

    return {
        "directory": str(directory),
        "source_mode": "workbook-export" if use_workbook_export else "per-figure-csv",
        "raw_sources": raw_sources,
        "valid": not issues,
        "figures": figures,
        "table_1": table,
        "issues": issues,
    }


def _runtime_provenance(hrx_path: Path, results_path: Path) -> dict[str, Any]:
    from histra.types.linear_system import LinearSystem

    packages: dict[str, str] = {}
    for name in ("histra-python", "numpy", "scipy", "numba"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "packages": packages,
        # Resolve the same auto/explicit backend selected by nonlinear setup;
        # importing SciPy alone is not evidence that SuperLU was used.
        "solver_backend": f"Python/{LinearSystem(0).backend}",
        "requested_linear_solver_backend": LinearSystem(0).requested_backend,
        "inputs": {
            "hrx": {"name": hrx_path.name, "bytes": hrx_path.stat().st_size, "sha256": _file_sha256(hrx_path)},
            "csharp_results": {"name": results_path.name, "bytes": results_path.stat().st_size, "sha256": _file_sha256(results_path)},
        },
    }


def _python_phase_distribution(model: Any) -> dict[int, int]:
    counts: Counter[int] = Counter()
    collections = model.collections
    for quad in collections.quads.values():
        if quad.spring is not None:
            counts[int(getattr(quad.spring, "phase", 0))] += 1
    for interface in collections.interfaces.values():
        for group in (interface.trasv_1, interface.slid, interface.slid_out_plan):
            for spring in group:
                counts[int(getattr(spring, "phase", 0))] += 1
    return dict(sorted(counts.items()))


def compare_phase_distributions(
    reference: Mapping[int, int], actual: Mapping[int, int]
) -> dict[str, Any]:
    available = bool(reference)
    phases = sorted(set(reference) | set(actual))
    mismatches = {
        str(phase): {"csharp": int(reference.get(phase, 0)), "python": int(actual.get(phase, 0))}
        for phase in phases
        if int(reference.get(phase, 0)) != int(actual.get(phase, 0))
    }
    return {
        "available": available,
        "csharp_total": int(sum(reference.values())),
        "python_total": int(sum(actual.values())),
        "exact": available and not mismatches,
        "reason": None if available else "no C# SpringStates rows at the terminal step",
        "mismatches": mismatches,
    }


def compare_phase_checkpoint_at_physical_displacement(
    results_path: Path,
    execution: Any,
    analysis: Any,
    csharp_displacements: Mapping[tuple[int, int, int], np.ndarray],
    python_displacements: Mapping[tuple[int, int, int], np.ndarray],
    python_phase_counts: Mapping[int, int],
    *,
    combination: int = 1,
    maximum_displacement_error_mm: float = PARITY_DISPLACEMENT_ABSOLUTE_TOLERANCE_MM,
) -> dict[str, Any]:
    """Match strict spring phases at a physical model-point displacement.

    Strict continuation can have a different step count from C# authored Work.
    The closest C# model-point displacement in the requested direction is the
    only valid phase checkpoint; an ordinal solver step is deliberately never
    used as a substitute.
    """

    committed = tuple(execution.committed_steps)
    analysis_key = int(getattr(analysis, "key"))
    master_point = int(getattr(analysis, "master_point", -1))
    if not committed or master_point < 0:
        return {
            "available": False,
            "accepted": False,
            "reason": "analysis has no committed strict state or valid master point",
        }
    component = {"ux": 0, "uy": 1, "uz": 2}.get(
        str(getattr(analysis, "direction", "")).casefold()
    )
    if component is None:
        direction = np.asarray(
            (getattr(analysis, "dir_x", 0.0), getattr(analysis, "dir_y", 0.0), getattr(analysis, "dir_z", 0.0)),
            dtype=float,
        )
        if not np.any(direction):
            return {"available": False, "accepted": False, "reason": "analysis has no output direction"}
        component = int(np.argmax(np.abs(direction)))

    actual_step = int(committed[-1].step)
    actual_key = (analysis_key, actual_step, master_point)
    actual = python_displacements.get(actual_key)
    references = [
        (int(step), values)
        for (key, step, point), values in csharp_displacements.items()
        if int(key) == analysis_key and int(point) == master_point and int(step) > 0
    ]
    if actual is None or not references:
        return {
            "available": False,
            "accepted": False,
            "reason": "model-point displacement is unavailable for strict/C# checkpoint matching",
        }
    actual_mm = float(actual[component] * 10.0)
    reference_step, reference = min(
        references, key=lambda item: abs(float(item[1][component] * 10.0) - actual_mm)
    )
    reference_mm = float(reference[component] * 10.0)
    displacement_error = abs(actual_mm - reference_mm)
    if displacement_error > maximum_displacement_error_mm:
        return {
            "available": False,
            "accepted": False,
            "strict_step": actual_step,
            "csharp_step": reference_step,
            "direction": ("Ux", "Uy", "Uz")[component],
            "strict_displacement_mm": actual_mm,
            "csharp_displacement_mm": reference_mm,
            "displacement_absolute_error_mm": displacement_error,
            "displacement_allowed_mm": maximum_displacement_error_mm,
            "reason": "no C# spring checkpoint lies within the physical-displacement tolerance",
        }

    reference_counts: dict[int, int] = {}
    with sqlite3.connect(results_path) as db:
        tables = {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("SpringStatesTmp", "SpringStates"):
            if table not in tables:
                continue
            reference_counts = {
                int(phase): int(count)
                for phase, count in db.execute(
                    f"SELECT CAST(Phase AS INTEGER),COUNT(*) FROM {table} "
                    "WHERE AnalysisKey=? AND Combination=? AND Step=? "
                    "GROUP BY CAST(Phase AS INTEGER)",
                    (analysis_key, int(combination), reference_step),
                )
            }
            if reference_counts:
                break
    comparison = compare_phase_distributions(reference_counts, python_phase_counts)
    comparison.update(
        {
            "accepted": bool(comparison["exact"]),
            "strict_step": actual_step,
            "csharp_step": reference_step,
            "direction": ("Ux", "Uy", "Uz")[component],
            "strict_displacement_mm": actual_mm,
            "csharp_displacement_mm": reference_mm,
            "displacement_absolute_error_mm": displacement_error,
            "displacement_allowed_mm": maximum_displacement_error_mm,
            "comparison": "physical_displacement_phase_checkpoint_v1",
        }
    )
    return comparison


def _vector_error_metrics(
    reference: Mapping[Any, np.ndarray],
    actual: Mapping[Any, np.ndarray],
    *,
    scale: float = 1.0,
) -> dict[str, Any]:
    reference_keys = set(reference)
    actual_keys = set(actual)
    common = sorted(reference_keys & actual_keys)
    missing = sorted(reference_keys - actual_keys)
    extra = sorted(actual_keys - reference_keys)
    if not common:
        return {
            "reference_rows": len(reference_keys),
            "actual_rows": len(actual_keys),
            "matched_rows": 0,
            "missing_rows": len(missing),
            "extra_rows": len(extra),
            "max_absolute": None,
            "relative_l2": None,
            "worst_key": None,
        }

    expected = np.stack([np.asarray(reference[key], dtype=np.float64) for key in common])
    observed = np.stack([np.asarray(actual[key], dtype=np.float64) for key in common])
    delta = (observed - expected) * float(scale)
    absolute = np.abs(delta)
    flat_index = int(np.argmax(absolute))
    row, component = np.unravel_index(flat_index, absolute.shape)
    denominator = max(float(np.linalg.norm(expected * float(scale))), np.finfo(float).tiny)
    return {
        "reference_rows": len(reference_keys),
        "actual_rows": len(actual_keys),
        "matched_rows": len(common),
        "missing_rows": len(missing),
        "extra_rows": len(extra),
        "max_absolute": float(absolute[row, component]),
        "relative_l2": float(np.linalg.norm(delta) / denominator),
        "worst_key": [int(value) for value in common[row]],
        "worst_component": int(component),
        "reference_at_worst": float(expected[row, component] * float(scale)),
        "actual_at_worst": float(observed[row, component] * float(scale)),
    }


def compute_parity_metrics(
    csharp_reactions: Mapping[tuple[int, int], np.ndarray],
    python_reactions: Mapping[tuple[int, int], np.ndarray],
    csharp_displacements: Mapping[tuple[int, int, int], np.ndarray],
    python_displacements: Mapping[tuple[int, int, int], np.ndarray],
    *,
    expected_steps: Iterable[tuple[int, int]] | None = None,
    actual_steps: Iterable[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Compare signed reactions and every available model-point component."""

    reaction_reference = {key: value for key, value in csharp_reactions.items() if key[1] > 0}
    reaction_actual = {key: value for key, value in python_reactions.items() if key[1] > 0}
    displacement_reference = {
        key: value for key, value in csharp_displacements.items() if key[1] > 0
    }
    displacement_actual = {
        key: value for key, value in python_displacements.items() if key[1] > 0
    }
    reaction = _vector_error_metrics(reaction_reference, reaction_actual)
    displacement = _vector_error_metrics(
        displacement_reference,
        displacement_actual,
        scale=10.0,  # HRX/C# centimetres -> millimetres.
    )
    expected_step_keys = set(expected_steps or reaction_reference)
    actual_step_keys = set(actual_steps or reaction_actual)
    missing_steps = expected_step_keys - actual_step_keys
    extra_steps = actual_step_keys - expected_step_keys
    step_history = {
        "expected_steps": len(expected_step_keys),
        "actual_steps": len(actual_step_keys),
        "matched_steps": len(expected_step_keys & actual_step_keys),
        "missing_steps": len(missing_steps),
        "extra_steps": len(extra_steps),
    }
    complete = step_history["missing_steps"] == 0 and step_history["extra_steps"] == 0
    reference_outputs_complete = (
        reaction["missing_rows"] == 0 and displacement["missing_rows"] == 0
    )
    within_tolerance = bool(
        complete
        and reference_outputs_complete
        and reaction["max_absolute"] is not None
        and displacement["max_absolute"] is not None
        and reaction["max_absolute"] <= PARITY_REACTION_ABSOLUTE_TOLERANCE
        and displacement["max_absolute"] <= PARITY_DISPLACEMENT_ABSOLUTE_TOLERANCE_MM
    )
    return {
        "complete_step_history": complete,
        "reference_outputs_complete": reference_outputs_complete,
        "within_parity_tolerance": within_tolerance,
        "step_history": step_history,
        "reaction": reaction,
        "model_point_displacement_mm": displacement,
    }


def _curve_characteristics(displacement_mm: np.ndarray, load_kn: np.ndarray) -> dict[str, float]:
    """Return signed characteristics of an already-oriented monotonic curve."""
    x = np.asarray(displacement_mm, dtype=np.float64)
    y = np.asarray(load_kn, dtype=np.float64)
    if not len(x):
        return {"peak_load_kn": 0.0, "peak_displacement_mm": 0.0, "area": 0.0, "initial_stiffness_kn_per_mm": 0.0}
    peak_index = int(np.argmax(np.abs(y)))
    area = float(np.trapezoid(y, x)) if len(x) > 1 else 0.0
    positive = np.flatnonzero(x > np.finfo(float).eps)
    initial_indices = positive[: min(10, len(positive))]
    if len(initial_indices):
        xi, yi = x[initial_indices], y[initial_indices]
        denominator = float(np.dot(xi, xi))
        stiffness = float(np.dot(xi, yi) / denominator) if denominator else 0.0
    else:
        stiffness = 0.0
    return {
        "peak_load_kn": float(y[peak_index]),
        "peak_displacement_mm": float(x[peak_index]),
        "area": area,
        "initial_stiffness_kn_per_mm": stiffness,
    }


def compute_curve_metrics(
    reference_displacement_mm: Iterable[float],
    reference_load_kn: Iterable[float],
    actual_displacement_mm: Iterable[float],
    actual_load_kn: Iterable[float],
) -> dict[str, Any]:
    """Compare a signed, monotonic live-load response without branch erasure.

    The curve-error waiver is valid only for a known monotonic envelope. A
    descending, cyclic, reversed-sign, or repeated-displacement response must
    be compared using a path-aware reference instead; sorting absolute values
    would turn a physically wrong branch into an apparent match.
    """
    ref_x = np.asarray(tuple(reference_displacement_mm), dtype=np.float64)
    ref_y = np.asarray(tuple(reference_load_kn), dtype=np.float64)
    act_x = np.asarray(tuple(actual_displacement_mm), dtype=np.float64)
    act_y = np.asarray(tuple(actual_load_kn), dtype=np.float64)
    if (
        len(ref_x) < 2
        or len(act_x) < 2
        or len(ref_x) != len(ref_y)
        or len(act_x) != len(act_y)
        or not np.all(np.isfinite(np.concatenate((ref_x, ref_y, act_x, act_y))))
    ):
        return {
            "available": False,
            "range_covered": False,
            "within_curve_tolerance": False,
            "reason": "each finite curve requires at least two displacement/load rows",
        }

    reference_direction = float(ref_x[-1] - ref_x[0])
    if abs(reference_direction) <= np.finfo(float).eps:
        return {
            "available": False,
            "range_covered": False,
            "within_curve_tolerance": False,
            "reason": "reference curve has no signed displacement direction",
        }
    orientation = 1.0 if reference_direction > 0.0 else -1.0
    ref_x = (ref_x - ref_x[0]) * orientation
    act_x = (act_x - act_x[0]) * orientation
    monotonic_epsilon = max(1.0e-9, 1.0e-8 * float(np.max(ref_x)))
    reference_monotonic = bool(np.all(np.diff(ref_x) >= -monotonic_epsilon))
    actual_monotonic = bool(np.all(np.diff(act_x) >= -monotonic_epsilon))
    if not reference_monotonic or not actual_monotonic:
        return {
            "available": False,
            "range_covered": False,
            "within_curve_tolerance": False,
            "reference_monotonic": reference_monotonic,
            "actual_monotonic": actual_monotonic,
            "reason": "curve waiver applies only to signed monotonic paths; use path-aware comparison",
        }
    if len(np.unique(ref_x)) < 2 or len(np.unique(act_x)) < 2:
        return {
            "available": False,
            "range_covered": False,
            "within_curve_tolerance": False,
            "reason": "each curve requires at least two distinct displacements",
        }

    displacement_span = float(ref_x[-1] - ref_x[0])
    displacement_epsilon = max(1.0e-9, 1.0e-8 * displacement_span)
    # A branch-sensitive solver may terminate a fraction of a millimetre on
    # either side of the C# terminal point.  The V1 acceptance plan explicitly
    # permits max(0.1 mm, 2%) peak-displacement error, so requiring bit-level
    # endpoint coverage here contradicted the stated gate and rejected a
    # response that the later peak metric accepted.  This allowance is only
    # for the terminal range; no values are extrapolated outside the overlap.
    terminal_range_allowed = max(0.1, 0.02 * abs(displacement_span))
    range_shortfall_start = max(0.0, float(act_x[0] - ref_x[0]))
    range_shortfall_end = max(0.0, float(ref_x[-1] - act_x[-1]))
    range_covered = bool(
        range_shortfall_start <= terminal_range_allowed + displacement_epsilon
        and range_shortfall_end <= terminal_range_allowed + displacement_epsilon
    )
    overlap_min = max(float(ref_x[0]), float(act_x[0]))
    overlap_max = min(float(ref_x[-1]), float(act_x[-1]))
    if overlap_max <= overlap_min + displacement_epsilon:
        return {
            "available": False,
            "range_covered": False,
            "within_curve_tolerance": False,
            "reason": "reference and actual displacement ranges do not overlap",
        }

    # A fixed displacement grid makes RMSE, area and stiffness independent of
    # each solver's adaptive step count. Preserve all observed knots inside the
    # overlap as well so sharp peaks are not smoothed away by the regular grid.
    evaluation_x = np.unique(
        np.concatenate(
            (
                np.linspace(overlap_min, overlap_max, 201),
                ref_x[(ref_x >= overlap_min) & (ref_x <= overlap_max)],
                act_x[(act_x >= overlap_min) & (act_x <= overlap_max)],
            )
        )
    )
    ref_evaluated = np.interp(evaluation_x, ref_x, ref_y)
    act_evaluated = np.interp(evaluation_x, act_x, act_y)
    # Area/RMSE/stiffness use the shared physical interval.  Peak position and
    # magnitude must use each native terminal response, otherwise an accepted
    # shortfall is masked by clipping both curves to the overlap endpoint.
    ref_overlap = _curve_characteristics(evaluation_x, ref_evaluated)
    actual_overlap = _curve_characteristics(evaluation_x, act_evaluated)
    ref = _curve_characteristics(ref_x, ref_y)
    actual = _curve_characteristics(act_x, act_y)
    peak_scale = max(abs(ref["peak_load_kn"]), np.finfo(float).tiny)
    normalized_rmse = float(
        np.sqrt(np.mean((act_evaluated - ref_evaluated) ** 2)) / peak_scale
    )

    def relative_error(actual_value: float, reference_value: float) -> float:
        denominator = max(abs(reference_value), np.finfo(float).tiny)
        return abs(actual_value - reference_value) / denominator

    metrics = {
        "range_covered": range_covered,
        "reference_monotonic": reference_monotonic,
        "actual_monotonic": actual_monotonic,
        "displacement_orientation": orientation,
        "reference_displacement_range_mm": [float(ref_x[0]), float(ref_x[-1])],
        "actual_displacement_range_mm": [float(act_x[0]), float(act_x[-1])],
        "overlap_displacement_range_mm": [overlap_min, overlap_max],
        "terminal_range_allowed_mm": terminal_range_allowed,
        "terminal_range_shortfall_start_mm": range_shortfall_start,
        "terminal_range_shortfall_end_mm": range_shortfall_end,
        "evaluation_points": int(len(evaluation_x)),
        "peak_load_relative_error": relative_error(actual["peak_load_kn"], ref["peak_load_kn"]),
        "normalized_curve_rmse": normalized_rmse,
        "curve_area_relative_error": relative_error(actual_overlap["area"], ref_overlap["area"]),
        "initial_stiffness_relative_error": relative_error(actual_overlap["initial_stiffness_kn_per_mm"], ref_overlap["initial_stiffness_kn_per_mm"]),
        "peak_displacement_absolute_error_mm": abs(actual["peak_displacement_mm"] - ref["peak_displacement_mm"]),
        "peak_displacement_allowed_mm": max(0.1, 0.02 * abs(ref["peak_displacement_mm"])),
    }
    metrics["available"] = True
    metrics["reference"] = ref
    metrics["actual"] = actual
    metrics["within_curve_tolerance"] = bool(
        range_covered
        and metrics["peak_load_relative_error"] <= 0.01
        and normalized_rmse <= 0.01
        and metrics["curve_area_relative_error"] <= 0.02
        and metrics["initial_stiffness_relative_error"] <= 0.02
        and metrics["peak_displacement_absolute_error_mm"] <= metrics["peak_displacement_allowed_mm"]
    )
    return metrics


def _live_load_curve_metrics(
    model_info: Mapping[str, Any],
    chain: Iterable[Any],
    csharp_reactions: Mapping[tuple[int, int], np.ndarray],
    python_reactions: Mapping[tuple[int, int], np.ndarray],
    csharp_displacements: Mapping[tuple[int, int, int], np.ndarray],
    python_displacements: Mapping[tuple[int, int, int], np.ndarray],
) -> dict[str, Any]:
    chain_list = list(chain)
    live_names = {str(value).casefold() for value in model_info["live_load_analyses"]}
    live_keys = [int(item.key) for item in chain_list if str(item.name).casefold() in live_names]
    if not live_keys:
        return {"available": False, "within_curve_tolerance": False, "reason": "no live-load analysis in dependency chain"}
    first_live_index = next(index for index, item in enumerate(chain_list) if int(item.key) == live_keys[0])
    predecessor_key = int(chain_list[first_live_index - 1].key) if first_live_index else None
    master_point = int(model_info["master_point"])
    direction = {"ux": 0, "uy": 1, "uz": 2}[str(model_info["direction"]).casefold()]

    def baseline(mapping: Mapping[Any, np.ndarray], *, point: bool) -> np.ndarray:
        if predecessor_key is None:
            return np.zeros(3)
        candidates = [
            (key, value) for key, value in mapping.items()
            if int(key[0]) == predecessor_key and (not point or int(key[2]) == master_point)
        ]
        return np.asarray(max(candidates, key=lambda item: int(item[0][1]))[1]) if candidates else np.zeros(3)

    ref_r0 = baseline(csharp_reactions, point=False)
    py_r0 = baseline(python_reactions, point=False)
    ref_u0 = baseline(csharp_displacements, point=True)
    py_u0 = baseline(python_displacements, point=True)
    def live_rows(
        reactions: Mapping[tuple[int, int], np.ndarray],
        displacements: Mapping[tuple[int, int, int], np.ndarray],
        reaction0: np.ndarray,
        displacement0: np.ndarray,
    ) -> tuple[list[float], list[float]]:
        keys = sorted(
            (
                key for key in reactions
                if int(key[0]) in live_keys
                and key[1] > 0
                and (key[0], key[1], master_point) in displacements
            ),
            key=lambda key: (live_keys.index(int(key[0])), int(key[1])),
        )
        x = [0.0]
        y = [0.0]
        for key in keys:
            x.append(
                float(
                    (displacements[(key[0], key[1], master_point)][direction]
                    - displacement0[direction])
                    * 10.0
                )
            )
            y.append(float(reactions[key][direction] - reaction0[direction]))
        return x, y

    ref_x, ref_y = live_rows(
        csharp_reactions, csharp_displacements, ref_r0, ref_u0
    )
    py_x, py_y = live_rows(
        python_reactions, python_displacements, py_r0, py_u0
    )
    result = compute_curve_metrics(ref_x, ref_y, py_x, py_y)
    result.update({
        "reference_sample_rows": max(0, len(ref_x) - 1),
        "actual_sample_rows": max(0, len(py_x) - 1),
        "master_point": master_point,
        "direction": model_info["direction"],
        "baseline_analysis_key": predecessor_key,
    })
    return result


def _project_python_history(
    model: Any,
    executions: Iterable[Any],
) -> tuple[
    dict[tuple[int, int], np.ndarray],
    dict[tuple[int, int, int], np.ndarray],
]:
    reactions: dict[tuple[int, int], np.ndarray] = {}
    displacements: dict[tuple[int, int, int], np.ndarray] = {}
    for execution in executions:
        analysis = int(execution.analysis_key)
        for step in execution.output_steps:
            if (
                step.reaction_x is not None
                and step.reaction_y is not None
                and step.reaction_z is not None
            ):
                reactions[(analysis, step.step)] = np.asarray(
                    (step.reaction_x, step.reaction_y, step.reaction_z),
                    dtype=np.float64,
                )
            for point in compute_model_point_displacements(model, step.u, step=step.step):
                displacements[(analysis, step.step, point.parent_key)] = np.asarray(
                    (point.ux, point.uy, point.uz), dtype=np.float64
                )
    return reactions, displacements


def run_model(
    model_info: Mapping[str, Any],
    models_dir: Path,
    run_mode: str,
) -> dict[str, Any]:
    """Run one model and return only compact verification evidence."""

    name = str(model_info["name"])
    hrx_path = models_dir / f"{name}.hrx"
    results_path = models_dir / f"{name}.Results"
    started = time.perf_counter()
    model = load_model(hrx_path)
    preparation_started = time.perf_counter()
    preparation = ModelManager.prepare_model(model, force=True)
    preparation_seconds = time.perf_counter() - preparation_started

    session = AnalysisSession(
        model,
        equilibrium_policy="error" if run_mode == "strict" else "warn",
        equilibrium_force_absolute_tolerance=AUDIT_FORCE_ABSOLUTE_TOLERANCE,
        equilibrium_force_relative_tolerance=AUDIT_FORCE_RELATIVE_TOLERANCE,
        equilibrium_residual_tolerance=AUDIT_RESIDUAL_TOLERANCE,
        strategy_policy="off",
    )
    chain = session.dependency_chain(str(model_info["target"]))
    chain_keys = tuple(int(analysis.key) for analysis in chain)
    csharp_reactions, csharp_displacements = _read_csharp_reference(
        results_path, chain_keys
    )
    step_limits, csharp_phase_counts = _read_csharp_terminal_steps(
        results_path, chain_keys
    )

    settings: list[dict[str, Any]] = []
    executions: list[Any] = []
    phase_evidence: dict[int, dict[str, Any]] = {}
    python_phase_counts: dict[int, dict[int, int]] = {}
    captured_warnings: list[warnings.WarningMessage]
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", UnsafeEquilibriumWarning)
        for analysis in chain:
            authored_criterion = str(analysis.adaptive_convergence_criteria)
            authored_tolerance = float(analysis.convergence_tolerance)
            authored_method = str(analysis.method)
            if run_mode == "strict":
                _apply_strict_strategy(analysis)
            settings.append(
                {
                    "analysis_key": int(analysis.key),
                    "analysis_name": str(analysis.name),
                    "authored_method": authored_method,
                    "authored_criterion": authored_criterion,
                    "authored_tolerance": authored_tolerance,
                    "effective_method": str(analysis.method),
                    "csharp_line_search_compatibility": bool(
                        getattr(analysis, "csharp_line_search_compatibility", True)
                    ),
                    "effective_criterion": str(analysis.adaptive_convergence_criteria),
                    "effective_tolerance": float(analysis.convergence_tolerance),
                    "csharp_steps": int(step_limits.get(int(analysis.key), 0)),
                }
            )
            execution = session.run(
                analysis,
                max_committed_steps=step_limits.get(int(analysis.key)),
            )
            executions.append(execution)
            phase_counts = _python_phase_distribution(model)
            python_phase_counts[int(analysis.key)] = phase_counts
            phase_evidence[int(analysis.key)] = compare_phase_distributions(
                csharp_phase_counts.get(int(analysis.key), {}), phase_counts
            )
            if not execution.completed:
                break
        captured_warnings = list(captured)

    python_reactions, python_displacements = _project_python_history(model, executions)
    expected_steps = {
        (analysis, step)
        for analysis, limit in step_limits.items()
        for step in range(1, limit + 1)
    }
    actual_steps = {
        (int(execution.analysis_key), int(step.step))
        for execution in executions
        for step in execution.committed_steps
    }
    parity = compute_parity_metrics(
        csharp_reactions,
        python_reactions,
        csharp_displacements,
        python_displacements,
        expected_steps=expected_steps,
        actual_steps=actual_steps,
    )
    curve = _live_load_curve_metrics(
        model_info,
        chain,
        csharp_reactions,
        python_reactions,
        csharp_displacements,
        python_displacements,
    )
    strict_phase_checkpoints = (
        {
            int(execution.analysis_key): compare_phase_checkpoint_at_physical_displacement(
                results_path,
                execution,
                next(item for item in chain if int(item.key) == int(execution.analysis_key)),
                csharp_displacements,
                python_displacements,
                python_phase_counts.get(int(execution.analysis_key), {}),
            )
            for execution in executions
        }
        if run_mode == "strict"
        else None
    )
    unsafe_steps = [
        step
        for execution in executions
        for step in execution.committed_steps
        if step.equilibrium_ok is False
    ]
    unsafe_criteria = Counter(str(step.get("convergence_criterion", "")) for step in unsafe_steps)
    outcomes = [
        {
            "analysis_key": int(execution.analysis_key),
            "analysis_name": execution.analysis_name,
            "outcome": execution.outcome.value,
            "exit_code": int(execution.code),
            "committed_steps": len(execution.committed_steps),
            "runtime_seconds": float(execution.runtime_seconds),
        }
        for execution in executions
    ]
    complete_chain = len(executions) == len(chain) and all(
        execution.completed for execution in executions
    )
    phase_distributions_agree = bool(phase_evidence) and all(
        evidence["exact"] for evidence in phase_evidence.values()
    )
    if run_mode == "authored":
        response_accepted = bool(parity["within_parity_tolerance"])
        release_gate_pass = bool(
            complete_chain
            and parity["complete_step_history"]
            and parity["reference_outputs_complete"]
            and response_accepted
            and phase_distributions_agree
        )
        response_comparison = "authored_stepwise_parity"
    else:
        # ForceMoment and a production-safe line-search path can legitimately
        # select different intermediate equilibria.  C#'s authored Work rows
        # are therefore *not* a pointwise strict reference.  Strict response
        # acceptance is curve-based over the physical displacement range.
        response_accepted = bool(curve.get("within_curve_tolerance", False))
        strict_phase_checkpoints_accepted = bool(strict_phase_checkpoints) and all(
            item.get("accepted", False)
            for item in strict_phase_checkpoints.values()
        )
        release_gate_pass = bool(
            complete_chain
            and response_accepted
            and not unsafe_steps
            and strict_phase_checkpoints_accepted
        )
        response_comparison = "strict_curve_response"
    return {
        "id": str(model_info["id"]),
        "name": name,
        "run_mode": run_mode,
        "gdl": int(model.gdl),
        "interfaces": int(preparation.interfaces),
        "preparation_seconds": preparation_seconds,
        "total_seconds": time.perf_counter() - started,
        "provenance": _runtime_provenance(hrx_path, results_path),
        "registry": {
            key: model_info.get(key)
            for key in ("specimen", "variant", "figures", "capacity_kn", "master_point", "direction")
        },
        "audit_tolerances": {
            "force_absolute": AUDIT_FORCE_ABSOLUTE_TOLERANCE,
            "force_relative": AUDIT_FORCE_RELATIVE_TOLERANCE,
            "residual": AUDIT_RESIDUAL_TOLERANCE,
        },
        "settings": settings,
        "outcomes": outcomes,
        "warning_count": sum(
            issubclass(item.category, UnsafeEquilibriumWarning)
            for item in captured_warnings
        ),
        "unsafe_step_count": len(unsafe_steps),
        "unsafe_steps_by_criterion": dict(sorted(unsafe_criteria.items())),
        "parity": parity,
        "stepwise_parity_applicable": run_mode == "authored",
        "response_comparison": response_comparison,
        "strict_phase_checkpoint_comparison": (
            strict_phase_checkpoints
        ),
        "live_load_curve": curve,
        "spring_phase_distributions": phase_evidence,
        "complete_dependency_chain": complete_chain,
        "release_gate_pass": release_gate_pass,
    }


def _worker(task: tuple[dict[str, Any], str, str]) -> dict[str, Any]:
    model_info, models_dir, run_mode = task
    try:
        return run_model(model_info, Path(models_dir), run_mode)
    except Exception as exc:
        return {
            "id": str(model_info["id"]),
            "name": str(model_info["name"]),
            "run_mode": run_mode,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _markdown_report(
    results: Sequence[Mapping[str, Any]],
    source_data: Mapping[str, Any] | None = None,
    expected_tasks: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> str:
    lines = [
        "# Article Models: Python vs C# verification",
        "",
        "Warning tolerances are unchanged: force absolute `1e-3`, force relative "
        "`1e-5`, active-residual L2 `1e-4`.",
        "",
        "| Mode | Model | Steps | Unsafe | Comparable response | Status |",
        "|---|---|---:|---:|---|---|",
    ]
    seen_pairs: set[tuple[str, str]] = set()
    for result in sorted(results, key=lambda item: (item["run_mode"], item["name"])):
        seen_pairs.add((result["run_mode"], str(result.get("id"))))
        if "error" in result:
            lines.append(
                f"| {result['run_mode']} | {result['name']} | - | - | - | "
                f"ERROR: {result['error']} |"
            )
            continue
        parity = result["parity"]
        step_history = parity["step_history"]
        steps = f"{step_history['actual_steps']}/{step_history['expected_steps']}"
        status = "PASS" if result["release_gate_pass"] else "NOT RELEASE-READY"
        if result.get("response_comparison", "authored_stepwise_parity" if result["run_mode"] == "authored" else "strict_curve_response") == "authored_stepwise_parity":
            reaction_error = parity["reaction"]["max_absolute"]
            displacement_error = parity["model_point_displacement_mm"]["max_absolute"]
            reaction_text = "n/a" if reaction_error is None else f"{reaction_error:.6g}"
            displacement_text = "n/a" if displacement_error is None else f"{displacement_error:.6g}"
            response_text = f"row parity: dR={reaction_text} kN; du={displacement_text} mm"
        else:
            curve = result.get("live_load_curve", {})
            if curve.get("available"):
                response_text = (
                    "curve: RMSE="
                    f"{float(curve.get('normalized_curve_rmse', float('nan'))):.3e}; "
                    f"pass={bool(curve.get('within_curve_tolerance', False))}"
                )
            else:
                response_text = f"curve: n/a ({curve.get('reason', 'unavailable')})"
        lines.append(
            f"| {result['run_mode']} | {result['name']} | {steps} | "
            f"{result['unsafe_step_count']} | {response_text} | {status} |"
        )

    if expected_tasks is not None:
        for mode, model_info in expected_tasks:
            if (mode, str(model_info["id"])) not in seen_pairs:
                lines.append(
                    f"| {mode} | {model_info['name']} | - | - | - | "
                    "MISSING EVIDENCE (NOT RUN) |"
                )

    lines.append("")
    lines.append(
        "`authored` is judged by stored C# rows. `strict` is judged only by its "
        "physical load--displacement curve, safe committed states, and physical-"
        "displacement spring checkpoints; it is never judged by C# authored row number."
    )
    if source_data is not None:
        lines.extend((
            "",
            "## Article source data",
            "",
            "PASS" if source_data.get("valid") else "NOT RELEASE-READY",
        ))
        for issue in source_data.get("issues", ()):
            lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"


def _select_models(target: str) -> list[dict[str, Any]]:
    if target.casefold() == "all":
        return [dict(item) for item in BENCHMARK_MODELS]
    selected = [
        dict(item)
        for item in BENCHMARK_MODELS
        if target.casefold() in {str(item["id"]).casefold(), str(item["name"]).casefold()}
    ]
    if not selected:
        raise ValueError(f"unknown article benchmark model: {target!r}")
    return selected


def _checkpoint_path(output_dir: Path, model_info: Mapping[str, Any], run_mode: str) -> Path:
    return output_dir / "checkpoints" / f"{run_mode}_{model_info['id']}.json"


def _load_checkpoint(
    output_dir: Path,
    model_info: Mapping[str, Any],
    run_mode: str,
    models_dir: Path,
) -> dict[str, Any] | None:
    """Load an intact diagnostic checkpoint whose input sizes still match."""
    path = _checkpoint_path(output_dir, model_info, run_mode)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = payload["result"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if (
        payload.get("schema_version") != 3
        or payload.get("harness_revision") != BENCHMARK_HARNESS_REVISION
        or result.get("id") != str(model_info["id"])
        or result.get("name") != str(model_info["name"])
        or result.get("run_mode") != run_mode
        or "error" in result
    ):
        return None
    inputs = result.get("provenance", {}).get("inputs", {})
    for key, suffix in (("hrx", ".hrx"), ("csharp_results", ".Results")):
        source = models_dir / f"{model_info['name']}{suffix}"
        evidence = inputs.get(key, {})
        if evidence.get("name") != source.name or evidence.get("bytes") != source.stat().st_size:
            return None
    # An absent C# terminal distribution is missing evidence, not an all-zero
    # physical state.
    for evidence in result.get("spring_phase_distributions", {}).values():
        available = int(evidence.get("csharp_total", 0)) > 0
        evidence["available"] = available
        evidence["exact"] = available and bool(evidence.get("exact", False))
        evidence["reason"] = (
            None if available else "no C# SpringStates rows at the terminal step"
        )
    return result


def _progress_line(result: Mapping[str, Any], *, resumed: bool = False) -> str:
    prefix = "resumed " if resumed else ""
    if "error" in result:
        return f"[{result['run_mode']}] {prefix}{result['name']}: {result['error']}"
    parity = result["parity"]
    step_history = parity["step_history"]
    if result.get("response_comparison", "authored_stepwise_parity" if result["run_mode"] == "authored" else "strict_curve_response") == "strict_curve_response":
        curve = result.get("live_load_curve", {})
        if curve.get("available"):
            response_text = f"curve RMSE={float(curve.get('normalized_curve_rmse', float('nan'))):.3e}"
        else:
            response_text = "curve=n/a"
    else:
        reaction_error = parity["reaction"].get("max_absolute")
        reaction_text = "n/a" if reaction_error is None else f"{float(reaction_error):.6g} kN"
        response_text = f"dR={reaction_text}"
    return (
        f"[{result['run_mode']}] {prefix}{result['name']}: "
        f"steps={step_history['actual_steps']}/{step_history['expected_steps']}, "
        f"unsafe={result['unsafe_step_count']}, {response_text}, "
        f"time={result['total_seconds']:.2f}s"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, required=True)
    parser.add_argument("--model", default="all")
    parser.add_argument("--run-mode", choices=("authored", "strict", "both"), default="both")
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--source-data-dir",
        type=Path,
        help="Figure CSVs and table_01.csv; defaults to OUTPUT-DIR/../article-source-data.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse intact non-error checkpoints with matching input file sizes.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Return success while collecting diagnostic evidence from a failing gate.",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Compile report from existing checkpoints without scheduling missing tasks.",
    )
    args = parser.parse_args()

    selected = _select_models(args.model)
    modes = ("authored", "strict") if args.run_mode == "both" else (args.run_mode,)
    for model_info in selected:
        for suffix in (".hrx", ".Results"):
            source = args.models_dir / f"{model_info['name']}{suffix}"
            if not source.is_file():
                parser.error(f"missing benchmark input: {source}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    source_data_dir = args.source_data_dir or args.output_dir.parent / "article-source-data"
    source_data = validate_article_source_data(source_data_dir)
    (args.output_dir / "article_source_data_validation.json").write_text(
        json.dumps(source_data, indent=2) + "\n", encoding="utf-8"
    )
    if not source_data["valid"] and not args.allow_incomplete:
        print("Article source-data gate failed:", file=sys.stderr)
        for issue in source_data["issues"]:
            print(f"- {issue}", file=sys.stderr)
        return 2
    results: list[dict[str, Any]] = []
    tasks: list[tuple[dict[str, Any], str, str]] = []
    for mode in modes:
        for model in selected:
            checkpoint = (
                _load_checkpoint(args.output_dir, model, mode, args.models_dir)
                if args.resume else None
            )
            if checkpoint is None:
                tasks.append((model, str(args.models_dir.resolve()), mode))
            else:
                results.append(checkpoint)
                print(_progress_line(checkpoint, resumed=True), flush=True)
    if args.aggregate_only:
        tasks = []
    # These models can each retain several GiB of constitutive state. Four
    # concurrent workers measured faster than eight or fourteen on the 32-GiB
    # reference workstation because the larger pools exhausted swap.
    workers = args.max_workers or min(4, max(1, len(tasks)), os.cpu_count() or 1)
    if workers < 1 or workers > 4:
        parser.error("--max-workers must be between 1 and 4 for the release-candidate gate")
    started = time.perf_counter()
    if tasks:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_worker, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                model_info, _models_dir, run_mode = futures[future]
                _checkpoint_path(args.output_dir, model_info, run_mode).write_text(
                    json.dumps(
                        {
                            "schema_version": 3,
                            "harness_revision": BENCHMARK_HARNESS_REVISION,
                            "result": result,
                        },
                        indent=2,
                    ) + "\n",
                    encoding="utf-8",
                )
                print(_progress_line(result), flush=True)

    expected_tasks = [(mode, model) for mode in modes for model in selected]
    actual_pairs = {(res.get("run_mode"), str(res.get("id"))): res for res in results}
    missing_tasks = [
        (mode, model)
        for mode, model in expected_tasks
        if (mode, str(model["id"])) not in actual_pairs
    ]
    if missing_tasks:
        print(f"Notice: {len(missing_tasks)} expected task(s) missing from results:", file=sys.stderr)
        for mode, model in missing_tasks:
            print(f"  - [{mode}] {model['name']}", file=sys.stderr)

    payload = {
        "schema_version": 3,
        "harness_revision": BENCHMARK_HARNESS_REVISION,
        "article_figures": ARTICLE_FIGURES,
        "article_table_1_capacities_kn": ARTICLE_TABLE_1_CAPACITIES_KN,
        "article_source_data": source_data,
        "model_registry": [dict(item) for item in BENCHMARK_MODELS],
        "expected_task_count": len(expected_tasks),
        "loaded_result_count": len(results),
        "missing_task_count": len(missing_tasks),
        "missing_tasks": [f"{mode}:{model['name']}" for mode, model in missing_tasks],
        "wall_seconds": time.perf_counter() - started,
        "workers": workers,
        "results": sorted(results, key=lambda item: (item["run_mode"], item["name"])),
    }
    (args.output_dir / "article_models_csharp_verification.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "article_models_csharp_verification.md").write_text(
        _markdown_report(results, source_data, expected_tasks=expected_tasks), encoding="utf-8"
    )
    failed = (
        not source_data["valid"]
        or bool(missing_tasks)
        or not results
        or any(
            "error" in result or not result.get("release_gate_pass", False)
            for result in results
        )
    )
    return 0 if args.allow_incomplete else int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
