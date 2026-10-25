import sqlite3
from types import SimpleNamespace

import pytest

from histra.tools.strategy_benchmark import (
    _apply_candidate_overrides,
    _path_response_metrics,
    aggregate_candidate_runs,
    qualify_candidates,
    read_csharp_reference_curve,
)


def _result(identifier: str, load: list[float], *, completed: bool = True, unsafe: int = 0):
    return {
        "id": identifier,
        "completed": completed,
        "unsafe_steps": unsafe,
        "curve": {
            "displacement_mm": [0.0, 1.0, 2.0],
            "load_kn": load,
        },
    }


def _accepted_evidence() -> dict[str, object]:
    return {
        "accepted": True,
        "source": "release-evidence/reference-path.json",
        "source_sha256": "0123456789abcdef",
    }


def test_qualification_is_correctness_first() -> None:
    results = [
        _result("baseline", [0.0, 10.0, 20.0]),
        _result("fast-safe", [0.0, 10.01, 20.01]),
        _result("unsafe", [0.0, 10.0, 20.0], unsafe=1),
        _result("drift", [0.0, 8.0, 15.0]),
    ]

    qualify_candidates(
        results,
        "baseline",
        reference_curve=results[0]["curve"],
        reference_evidence=_accepted_evidence(),
    )

    assert [item["qualifies"] for item in results] == [True, True, False, False]

    results[1]["range_covered"] = False
    qualify_candidates(
        results,
        "baseline",
        reference_curve=results[0]["curve"],
        reference_evidence=_accepted_evidence(),
    )
    assert not results[1]["qualifies"]


def test_qualification_requires_a_safe_baseline_and_traceable_reference() -> None:
    results = [
        _result("baseline", [0.0, 10.0, 20.0], completed=False, unsafe=1),
        _result("candidate", [0.0, 10.0, 20.0]),
    ]

    qualify_candidates(
        results,
        "baseline",
        reference_curve=results[1]["curve"],
        reference_evidence=_accepted_evidence(),
    )
    assert not results[0]["qualifies"]
    assert not results[1]["qualifies"]

    results[0] = _result("baseline", [0.0, 10.0, 20.0])
    qualify_candidates(results, "baseline")
    assert not results[0]["qualifies"]
    assert not results[1]["qualifies"]


def test_path_metrics_reject_sign_and_unloading_branch_changes() -> None:
    reference_x = [0.0, 1.0, 2.0, 1.0, 0.0]
    reference_y = [0.0, 10.0, 20.0, 8.0, 1.0]

    opposite_sign = _path_response_metrics(
        reference_x, reference_y,
        [0.0, 1.0, 2.0], [0.0, -10.0, -20.0],
    )
    wrong_unloading = _path_response_metrics(
        reference_x, reference_y,
        [0.0, 1.0, 2.0, 1.0, 0.0], [0.0, 10.0, 20.0, 100.0, 100.0],
    )

    assert opposite_sign["within_curve_tolerance"] is False
    assert opposite_sign["peak_sign_match"] is False
    assert wrong_unloading["within_curve_tolerance"] is False
    assert wrong_unloading["normalized_load_path_rmse"] > 0.01


def test_candidate_can_override_dependency_strategies_without_mutating_others() -> None:
    vert = SimpleNamespace(name="Vert", method="ModifiedNewtonRaphson")
    live = SimpleNamespace(
        name="Live", method="ModifiedNewtonRaphson",
        adaptive_convergence_criteria="Work",
        csharp_line_search_compatibility=True,
    )
    _apply_candidate_overrides(
        [vert, live],
        {
            "id": "safe",
            "method": "StandardRegulaFalsiLineSearch",
            "adaptive_convergence_criteria": "ForceMoment",
            "csharp_line_search_compatibility": False,
            "analysis_overrides": {
                "Vert": {"method": "StandardRegulaFalsiLineSearch"},
            },
        },
    )
    assert vert.method == "StandardRegulaFalsiLineSearch"
    assert live.method == "StandardRegulaFalsiLineSearch"
    assert live.adaptive_convergence_criteria == "ForceMoment"
    assert live.csharp_line_search_compatibility is False


def test_candidate_rejects_unknown_dependency_override() -> None:
    definition = SimpleNamespace(name="Vert")
    with pytest.raises(ValueError, match="Unsupported strategy override"):
        _apply_candidate_overrides(
            [definition],
            {"id": "bad", "analysis_overrides": {"Vert": {"future": 1}}},
        )


def test_repeated_runs_use_median_timing_but_fail_closed_on_any_unsafe_step() -> None:
    runs = [
        {**_result("candidate", [0.0, 10.0, 20.0]), "runtime_seconds": 3.0,
         "preparation_seconds": 1.0, "committed_steps": 3, "iterations": 9,
         "linear_solves": 9, "factorizations": 3, "peak_rss_bytes": 100},
        {**_result("candidate", [0.0, 10.0, 20.0], unsafe=1), "runtime_seconds": 1.0,
         "preparation_seconds": 1.0, "committed_steps": 3, "iterations": 9,
         "linear_solves": 9, "factorizations": 3, "peak_rss_bytes": 200},
        {**_result("candidate", [0.0, 10.0, 20.0]), "runtime_seconds": 2.0,
         "preparation_seconds": 1.0, "committed_steps": 3, "iterations": 9,
         "linear_solves": 9, "factorizations": 3, "peak_rss_bytes": None},
    ]

    result = aggregate_candidate_runs(runs)

    assert result["runtime_seconds"] == 2.0
    assert result["unsafe_steps"] == 1
    assert result["peak_rss_bytes"] == 200
    assert len(result["observations"]) == 3

    qualify_candidates(
        [result],
        "candidate",
        reference_curve=result["curve"],
        reference_evidence=_accepted_evidence(),
    )
    assert not result["qualifies"]


def test_csharp_reference_curve_uses_target_master_point_and_direction(tmp_path) -> None:
    results = tmp_path / "reference.Results"
    with sqlite3.connect(results) as db:
        db.execute(
            "CREATE TABLE ReactionSumStates (AnalysisKey INTEGER, Combination INTEGER, Step INTEGER, R1 REAL, R2 REAL, R3 REAL)"
        )
        db.execute(
            "CREATE TABLE DisplModelPoints (AnalysisKey INTEGER, Combination INTEGER, Step INTEGER, ParentKey INTEGER, Ux REAL, Uy REAL, Uz REAL)"
        )
        db.executemany(
            "INSERT INTO ReactionSumStates VALUES (?, ?, ?, ?, ?, ?)",
            [(1, 1, 0, 0, 0, 0), (1, 1, 1, 0, 0, -10), (1, 1, 2, 0, 0, -20)],
        )
        db.executemany(
            "INSERT INTO DisplModelPoints VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, 1, 0, 7, 0, 0, 0), (1, 1, 1, 7, 0, 0, -0.1), (1, 1, 2, 7, 0, 0, -0.2)],
        )
    analysis = SimpleNamespace(
        key=1, name="Vert", master_point=7, dir_x=0.0, dir_y=0.0, dir_z=-1.0
    )

    curve = read_csharp_reference_curve(results, [analysis])

    assert curve == {
        "displacement_mm": [0.0, -1.0, -2.0],
        "load_kn": [0.0, -10.0, -20.0],
    }
