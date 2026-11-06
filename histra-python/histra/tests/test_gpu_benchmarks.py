"""Comparison reports must reject missing states and nonlinear branch differences."""
from pathlib import Path
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.sparse as sp

from histra.solver.outcomes import AnalysisStep
from histra.tools.gpu_analysis_benchmark import _attempt_chain, _run_chain, compare_histories
from histra.tools.gpu_solver_benchmark import compare_linear_systems, error_metrics


def test_sparse_benchmark_reports_timing_and_precision_for_all_phases():
    matrix = sp.diags([-np.ones(9), np.full(10, 4.), np.ones(9)], [-1, 0, 1], format="csc")
    report = compare_linear_systems(matrix, np.arange(10.), candidate_backend="superlu", repeats=2)
    assert report["passed"]
    assert len(report["precision"]["superlu"]) == 3  # cold plus every warmed sample
    assert set(report["precision"]["superlu"][0]) == {"first", "reused", "refactored"}
    assert report["runs"]["superlu"]["median_seconds"]["reused_rhs_seconds"] > 0
    json.dumps(report, allow_nan=False)


def test_sparse_benchmark_does_not_mutate_reference_with_umfpack_refactor():
    from histra.types.umfpack import find_umfpack_library

    if find_umfpack_library() is None:
        pytest.skip("native UMFPACK unavailable")
    matrix = sp.csc_matrix([[4., 1.], [2., -3.]])
    original = matrix.copy()
    report = compare_linear_systems(matrix, np.array([6., -4.]), cpu_backend="umfpack",
                                    candidate_backend="superlu", repeats=2, rtol=0)
    np.testing.assert_array_equal(matrix.data, original.data)
    assert report["passed"]


def test_sparse_benchmark_missing_gpu_records_error(monkeypatch):
    from histra.types import cudss

    def unavailable():
        raise cudss.CudssUnavailable("missing CUDA")

    monkeypatch.setattr(cudss, "_direct_solver_type", unavailable)
    report = compare_linear_systems(sp.eye(2), np.ones(2), repeats=1)
    assert not report["passed"]
    assert report["runs"]["cudss"]["status"] == "error"
    assert "missing CUDA" in report["runs"]["cudss"]["error"]
    assert report["runs"]["superlu"]["status"] == "ok"


@pytest.mark.parametrize("left, right", [([0.], [1e-6]), ([1.], [np.nan]), ([1.], [1., 2.])])
def test_precision_metric_rejects_invalid_or_excessive_difference(left, right):
    assert not error_metrics(left, right)["within_tolerance"]


def _history():
    step = AnalysisStep.from_mapping({"step": 1, "status": "OK", "u": [1., 2.],
                                     "iterations": 2, "reaction_z": 4., "equilibrium_ok": True})
    execution = SimpleNamespace(analysis_key=1, steps=[step], committed_steps=[step])
    return ({"analyses": [{"key": 1, "code": 0, "committed_steps": 1}]},
            [execution], [{"runtime/0": np.array([1., 2.]), "phase/test": np.array([0., 1.])}])


@pytest.mark.parametrize("change", ["displacement", "reaction", "phase", "stop", "missing", "equilibrium", "iterations"])
def test_history_comparison_rejects_response_and_behavior_changes(change):
    reference = _history()
    candidate = copy.deepcopy(reference)
    if change == "displacement":
        candidate[1][0].steps[0]["u"][0] += 1e-6
    elif change == "reaction":
        candidate[1][0].steps[0]["reaction_z"] += 1e-6
    elif change == "phase":
        candidate[2][0]["phase/test"][0] = 1
    elif change == "stop":
        candidate[0]["analyses"][0]["code"] = -2
    elif change == "missing":
        candidate[2].clear()
    elif change == "equilibrium":
        candidate[1][0].steps[0]["equilibrium_ok"] = False
    else:
        candidate[1][0].steps[0]["iterations"] += 1
    assert not compare_histories(reference, candidate)["passed"]


def test_matching_history_passes_and_empty_history_does_not():
    assert compare_histories(_history(), _history())["passed"]
    assert not compare_histories(({"analyses": []}, [], []), ({"analyses": []}, [], []))["passed"]


def test_fresh_compiled_cpu_chain_capture_smoke():
    path = Path(__file__).resolve().parents[1] / "model-live/model.hrx"
    first = _run_chain(path, "Vert", "superlu", 1)
    second = _run_chain(path, "Vert", "superlu", 1)
    comparison = compare_histories(first, second)
    assert first[0]["analyses"][0]["committed_steps"] == 1
    assert first[0]["capture_seconds"] > 0
    assert comparison["phase_mismatches"] == 0
    assert comparison["same_behavior"]
    assert comparison["within_tolerance"]


def test_isolated_worker_returns_compiled_history_and_snapshots():
    path = Path(__file__).resolve().parents[1] / "model-live/model.hrx"
    report = {}
    result = _attempt_chain(path, "Vert", "superlu", 1, report)
    assert result is not None, report
    summary, executions, frames = result
    assert summary["backend"] == "superlu"
    assert len(executions[0].committed_steps) == len(frames) == 1
    assert "phase/transverse" in frames[0]


@pytest.mark.gpu
def test_native_gpu_fresh_compiled_chain():
    from histra.types.cudss import probe_cudss

    available, error = probe_cudss()
    if not available:
        pytest.skip(error)
    path = Path(__file__).resolve().parents[1] / "model-live/model.hrx"
    cpu = _run_chain(path, "Vert", "superlu", 1)
    gpu = _run_chain(path, "Vert", "cudss", 1)
    comparison = compare_histories(cpu, gpu)
    assert comparison["same_behavior"]
    assert comparison["within_tolerance"]
    assert comparison["phase_mismatches"] == 0
    # This reference's Work criterion can accept a step with unsafe equilibrium.
    # Numerical agreement must not turn that known safety failure into a pass.
    if not comparison["equilibrium_ok"]:
        assert not comparison["passed"]
