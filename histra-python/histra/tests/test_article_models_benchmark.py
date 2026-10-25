"""Strict tests for the compact Article Models benchmark harness."""
from __future__ import annotations

import csv
import json
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from histra.tools.article_models_benchmark import (
    ARTICLE_FIGURES,
    ARTICLE_SOURCE_SERIES,
    ARTICLE_TABLE_1_CAPACITIES_KN,
    AUDIT_RESIDUAL_TOLERANCE,
    BENCHMARK_HARNESS_REVISION,
    BENCHMARK_MODELS,
    compare_phase_distributions,
    compare_phase_checkpoint_at_physical_displacement,
    compute_curve_metrics,
    compute_parity_metrics,
    _markdown_report,
    _load_checkpoint,
    _progress_line,
    _apply_strict_strategy,
    _runtime_provenance,
    strict_convergence_tolerance,
    validate_article_source_data,
)


def test_registry_covers_all_models_article_figures_and_table_capacities() -> None:
    assert len(BENCHMARK_MODELS) == 14
    assert len({item["id"] for item in BENCHMARK_MODELS}) == 14
    assert set(ARTICLE_FIGURES) == {
        figure for item in BENCHMARK_MODELS for figure in item["figures"]
    }


def test_runtime_provenance_records_selected_sparse_backend(tmp_path) -> None:
    hrx = tmp_path / "Bridge.hrx"
    results = tmp_path / "Bridge.Results"
    hrx.write_bytes(b"hrx")
    results.write_bytes(b"results")

    provenance = _runtime_provenance(hrx, results)

    from histra.types.linear_system import LinearSystem

    assert provenance["solver_backend"] == f"Python/{LinearSystem(0).backend}"
    assert provenance["requested_linear_solver_backend"] == LinearSystem(0).requested_backend
    assert ARTICLE_TABLE_1_CAPACITIES_KN == {
        "3.1": 540.0, "3.2": 360.0, "3.3": 600.0, "3.4": 320.0,
        "5.1": 1720.0, "5.2": 500.0, "MS1": 455.0, "MS2": 320.0,
        "MS3": 325.0,
    }


@pytest.mark.parametrize(
    ("authored", "expected"),
    [
        (1.0e-2, 1.0e-4),
        (1.0e-4, 1.0e-4),
        (1.0e-6, 1.0e-6),
    ],
)
def test_strict_force_moment_tolerance_never_loosens_limits(
    authored: float,
    expected: float,
) -> None:
    actual = strict_convergence_tolerance(authored)
    assert actual == expected
    assert actual <= authored
    assert actual <= AUDIT_RESIDUAL_TOLERANCE


@pytest.mark.parametrize("invalid", [0.0, -1.0, np.inf, np.nan])
def test_strict_force_moment_tolerance_rejects_invalid_values(invalid: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        strict_convergence_tolerance(invalid)


def test_strict_strategy_selects_measured_bisection_without_looser_tolerance() -> None:
    analysis = type(
        "Analysis",
        (),
        {
            "analysis_type": 2,
            "method": "ModifiedRegulaFalsiLineSearch",
            "adaptive_convergence_criteria": "Work",
            "convergence_tolerance": 1.0e-2,
        },
    )()

    _apply_strict_strategy(analysis)

    assert analysis.method == "StandardBisectionLineSearch"
    assert analysis.adaptive_convergence_criteria == "ForceMoment"
    assert analysis.convergence_tolerance == AUDIT_RESIDUAL_TOLERANCE
    assert analysis.csharp_line_search_compatibility is False


def test_parity_compares_signed_all_component_vectors() -> None:
    csharp_reactions = {
        (1, 0): np.array([0.0, 0.0, 0.0]),
        (1, 1): np.array([1.0, -2.0, 3.0]),
        (2, 1): np.array([4.0, 5.0, -6.0]),
    }
    python_reactions = {
        (1, 0): np.array([999.0, 999.0, 999.0]),
        (1, 1): np.array([-1.0, -2.0, 3.0]),
        (2, 1): np.array([4.0, 5.0, -6.0]),
    }
    csharp_displacements = {
        (1, 1, 7): np.array([0.1, 0.2, -0.3]),
        (2, 1, 9): np.array([0.4, -0.5, 0.6]),
    }
    python_displacements = {
        (1, 1, 7): np.array([0.1, 0.2, -0.29]),
        (2, 1, 9): np.array([0.4, -0.5, 0.6]),
    }

    metrics = compute_parity_metrics(
        csharp_reactions,
        python_reactions,
        csharp_displacements,
        python_displacements,
    )

    assert metrics["complete_step_history"]
    assert not metrics["within_parity_tolerance"]
    assert metrics["reaction"]["max_absolute"] == 2.0
    assert metrics["reaction"]["worst_key"] == [1, 1]
    assert metrics["reaction"]["worst_component"] == 0
    assert metrics["model_point_displacement_mm"]["max_absolute"] == pytest.approx(0.1)
    assert metrics["model_point_displacement_mm"]["worst_key"] == [1, 1, 7]


def test_parity_fails_closed_on_missing_or_extra_history_rows() -> None:
    reference_reactions = {
        (1, 1): np.zeros(3),
        (1, 2): np.ones(3),
    }
    actual_reactions = {
        (1, 1): np.zeros(3),
        (1, 3): np.ones(3),
    }
    reference_displacements = {
        (1, 1, 5): np.zeros(3),
        (1, 2, 5): np.ones(3),
    }
    actual_displacements = {(1, 1, 5): np.zeros(3)}

    metrics = compute_parity_metrics(
        reference_reactions,
        actual_reactions,
        reference_displacements,
        actual_displacements,
    )

    assert not metrics["complete_step_history"]
    assert not metrics["within_parity_tolerance"]
    assert metrics["reaction"]["missing_rows"] == 1
    assert metrics["reaction"]["extra_rows"] == 1
    assert metrics["model_point_displacement_mm"]["missing_rows"] == 1
    assert metrics["model_point_displacement_mm"]["extra_rows"] == 0


def test_sparse_csharp_output_rows_do_not_look_like_missing_solver_steps() -> None:
    reference_reactions = {(1, 1): np.zeros(3), (1, 5): np.ones(3)}
    actual_reactions = {
        (1, step): np.zeros(3) if step == 1 else np.ones(3)
        for step in range(1, 6)
    }
    reference_displacements = {(1, 5, 7): np.ones(3)}
    actual_displacements = {
        (1, step, 7): np.ones(3)
        for step in range(1, 6)
    }

    metrics = compute_parity_metrics(
        reference_reactions,
        actual_reactions,
        reference_displacements,
        actual_displacements,
        expected_steps={(1, step) for step in range(1, 6)},
        actual_steps={(1, step) for step in range(1, 6)},
    )

    assert metrics["complete_step_history"]
    assert metrics["reference_outputs_complete"]
    assert metrics["within_parity_tolerance"]
    assert metrics["reaction"]["extra_rows"] == 3
    assert metrics["model_point_displacement_mm"]["extra_rows"] == 4


def test_curve_metrics_apply_release_acceptance_limits() -> None:
    reference_x = [0.0, 1.0, 2.0, 3.0]
    reference_y = [0.0, 10.0, 19.0, 20.0]
    passing = compute_curve_metrics(
        reference_x, reference_y, reference_x, [0.0, 10.02, 19.02, 20.02]
    )
    failing = compute_curve_metrics(
        reference_x, reference_y, reference_x, [0.0, 8.0, 15.0, 16.0]
    )
    assert passing["within_curve_tolerance"]
    assert not failing["within_curve_tolerance"]


def test_curve_metrics_interpolate_different_step_counts_on_displacement() -> None:
    reference_x = [0.0, 1.0, 2.0, 3.0]
    reference_y = [0.0, 10.0, 20.0, 30.0]
    actual_x = [0.0, 0.5, 1.5, 2.5, 3.0]
    actual_y = [0.0, 5.0, 15.0, 25.0, 30.0]

    metrics = compute_curve_metrics(reference_x, reference_y, actual_x, actual_y)

    assert metrics["range_covered"]
    assert metrics["within_curve_tolerance"]
    assert metrics["normalized_curve_rmse"] == pytest.approx(0.0, abs=1.0e-14)


def test_curve_metrics_reject_incomplete_displacement_range() -> None:
    metrics = compute_curve_metrics(
        [0.0, 1.0, 2.0, 3.0],
        [0.0, 10.0, 20.0, 30.0],
        [0.0, 1.0, 2.0],
        [0.0, 10.0, 20.0],
    )

    assert metrics["available"]
    assert not metrics["range_covered"]
    assert not metrics["within_curve_tolerance"]


def test_curve_metrics_accepts_terminal_shortfall_within_peak_displacement_limit() -> None:
    metrics = compute_curve_metrics(
        [0.0, 5.0, 10.0],
        [0.0, 50.0, 100.0],
        [0.0, 5.0, 9.95],
        [0.0, 50.0, 99.5],
    )

    assert metrics["range_covered"]
    assert metrics["terminal_range_shortfall_end_mm"] == pytest.approx(0.05)
    assert metrics["peak_displacement_absolute_error_mm"] == pytest.approx(0.05)
    assert metrics["within_curve_tolerance"]


def test_curve_metrics_rejects_reversed_signed_response() -> None:
    metrics = compute_curve_metrics(
        [0.0, 1.0, 2.0, 3.0],
        [0.0, 10.0, 20.0, 30.0],
        [0.0, -1.0, -2.0, -3.0],
        [0.0, -10.0, -20.0, -30.0],
    )

    assert not metrics["available"]
    assert not metrics["within_curve_tolerance"]
    assert metrics["actual_monotonic"] is False


def test_curve_metrics_rejects_descending_or_cyclic_path_waiver() -> None:
    metrics = compute_curve_metrics(
        [0.0, 1.0, 2.0, 1.0, 0.5],
        [0.0, 10.0, 20.0, 8.0, 1.0],
        [0.0, 1.0, 2.0, 1.0, 0.5],
        [0.0, 10.0, 20.0, 8.0, 1.0],
    )

    assert not metrics["available"]
    assert not metrics["within_curve_tolerance"]
    assert metrics["reference_monotonic"] is False


def test_phase_distribution_comparison_fails_closed() -> None:
    matched = compare_phase_distributions({0: 2, 4: 1}, {0: 2, 4: 1})
    assert matched["available"]
    assert matched["exact"]
    report = compare_phase_distributions({0: 2, 4: 1}, {0: 3})
    assert not report["exact"]
    assert report["mismatches"]["4"] == {"csharp": 1, "python": 0}

    missing = compare_phase_distributions({}, {0: 3})
    assert not missing["available"]
    assert not missing["exact"]
    assert missing["reason"] == "no C# SpringStates rows at the terminal step"


def test_strict_phase_checkpoint_matches_physical_displacement_not_step_number(tmp_path) -> None:
    results = tmp_path / "reference.Results"
    with sqlite3.connect(results) as db:
        db.execute(
            "CREATE TABLE SpringStatesTmp (AnalysisKey INTEGER, Combination INTEGER, Step INTEGER, Phase REAL)"
        )
        db.executemany(
            "INSERT INTO SpringStatesTmp VALUES (?, ?, ?, ?)",
            [(22, 1, 3, 0), (22, 1, 3, 0), (22, 1, 3, 4)],
        )
    analysis = SimpleNamespace(key=22, master_point=5, dir_x=0.0, dir_y=0.0, dir_z=-1.0)
    execution = SimpleNamespace(committed_steps=(SimpleNamespace(step=7),))

    result = compare_phase_checkpoint_at_physical_displacement(
        results,
        execution,
        analysis,
        {(22, 3, 5): np.array([0.0, 0.0, -0.3000])},
        {(22, 7, 5): np.array([0.0, 0.0, -0.3002])},
        {0: 2, 4: 1},
    )

    assert result["accepted"]
    assert result["strict_step"] == 7
    assert result["csharp_step"] == 3
    assert result["comparison"] == "physical_displacement_phase_checkpoint_v1"


def test_progress_line_handles_a_strict_run_without_comparable_rows() -> None:
    result = {
        "run_mode": "strict",
        "name": "Bridge",
        "unsafe_step_count": 0,
        "total_seconds": 1.25,
        "response_comparison": "strict_curve_response",
        "parity": {
            "step_history": {"actual_steps": 0, "expected_steps": 10},
            "reaction": {"max_absolute": 999.0},
        },
        "live_load_curve": {"available": False},
    }
    progress = _progress_line(result)
    assert "curve=n/a" in progress
    assert "dR=" not in progress


def test_markdown_report_uses_na_when_strict_run_has_no_comparable_rows() -> None:
    result = {
        "run_mode": "strict",
        "name": "Bridge",
        "unsafe_step_count": 0,
        "release_gate_pass": False,
        "response_comparison": "strict_curve_response",
        "parity": {
            "step_history": {"actual_steps": 0, "expected_steps": 10},
            "reaction": {"max_absolute": 999.0},
            "model_point_displacement_mm": {"max_absolute": 999.0},
        },
        "live_load_curve": {"available": False, "reason": "no completed live-load path"},
    }

    report = _markdown_report([result])

    assert "| strict | Bridge | 0/10 | 0 | curve: n/a (no completed live-load path) | NOT RELEASE-READY |" in report
    assert "999" not in report


def test_resume_rejects_checkpoint_from_older_harness_revision(tmp_path) -> None:
    model_info = {"id": "bridge", "name": "Bridge"}
    models_dir = tmp_path / "models"
    output_dir = tmp_path / "out"
    models_dir.mkdir()
    (output_dir / "checkpoints").mkdir(parents=True)
    (models_dir / "Bridge.hrx").write_bytes(b"hrx")
    (models_dir / "Bridge.Results").write_bytes(b"results")
    result = {
        "id": "bridge",
        "name": "Bridge",
        "run_mode": "strict",
        "provenance": {
            "inputs": {
                "hrx": {"name": "Bridge.hrx", "bytes": 3},
                "csharp_results": {"name": "Bridge.Results", "bytes": 7},
            }
        },
    }
    checkpoint = output_dir / "checkpoints" / "strict_bridge.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "harness_revision": BENCHMARK_HARNESS_REVISION - 1,
                "result": result,
            }
        ),
        encoding="utf-8",
    )

    assert _load_checkpoint(
        output_dir, model_info, "strict", models_dir
    ) is None


def test_article_source_data_validation_is_fail_closed_and_hashes_inputs(tmp_path) -> None:
    missing = validate_article_source_data(tmp_path)
    assert not missing["valid"]
    assert len(missing["issues"]) == len(ARTICLE_FIGURES) + 1

    for figure in ARTICLE_FIGURES:
        (tmp_path / f"figure_{figure:02d}.csv").write_text(
            "series,displacement_mm,load_kn,provenance\n"
            "experiment,0,0,user-original\n"
            "experiment,1,2,user-original\n",
            encoding="utf-8",
        )
    table_rows = "".join(
        f"{specimen},{capacity},user-original\n"
        for specimen, capacity in ARTICLE_TABLE_1_CAPACITIES_KN.items()
    )
    (tmp_path / "table_01.csv").write_text(
        "specimen,capacity_kn,provenance\n" + table_rows,
        encoding="utf-8",
    )

    report = validate_article_source_data(tmp_path)
    assert report["valid"]
    assert report["issues"] == []
    assert report["figures"]["9"]["rows"] == 2
    assert len(report["figures"]["9"]["sha256"]) == 64
    assert report["table_1"]["capacities_kn"]["MS1"] == 455.0


def test_article_workbook_export_is_a_first_class_original_data_source(tmp_path) -> None:
    """The original wide workbook export needs no lossy hand-transcription."""
    series_specs = {
        str(spec["source"]): spec
        for specs in ARTICLE_SOURCE_SERIES.values()
        for spec in specs
    }
    header_names: list[str] = []
    header_fields: list[str] = []
    columns: list[tuple[str, ...]] = []
    for source, spec in series_specs.items():
        fields = tuple(spec.get("displacement", {"x": 1.0})) + (str(spec.get("load", "y")),)
        header_names.extend((source, *([""] * (len(fields) - 1))))
        header_fields.extend(fields)
        columns.append(fields)
    export = tmp_path / "Original_article_data.csv"
    with export.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([])
        writer.writerow([])
        writer.writerow(header_names)
        writer.writerow(header_fields)
        for value in range(20):
            row: list[float] = []
            for fields in columns:
                row.extend(float(value + index + 1) for index in range(len(fields)))
            writer.writerow(row)
    (tmp_path / "Graphs_HISTRA.ipynb").write_text("{}", encoding="utf-8")
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"PDF source placeholder")

    report = validate_article_source_data(tmp_path, article_pdf_path=article_pdf)

    assert report["valid"]
    assert report["source_mode"] == "workbook-export"
    assert report["figures"]["9"]["series"]["Bridge_3.1_Coarse"] == 20
    assert report["figures"]["12"]["series"]["Bridge_5.1_Masonry_new"] == 3
    radial = report["figures"]["22"]["series_provenance"]["Bridge_2_Numerical_Arch"]
    assert radial["displacement_formula"] == {"z": 0.916516, "x": 0.399998}
    assert report["table_1"]["sha256"]
