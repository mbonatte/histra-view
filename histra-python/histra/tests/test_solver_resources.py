"""Resource budgets must apply before native imports without changing mechanics."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from histra import (
    PythonAnalysisRequest, PythonSolverJob, SolverResources, run_large_solver_job,
    run_python_solver_job, verify_bundle,
)
from histra.solver import resources as resource_module

MODEL = Path(__file__).resolve().parents[1] / "model-live/model.hrx"


def test_separate_budgets_preserve_parent_environment(monkeypatch):
    monkeypatch.setattr(resource_module, "available_cpu_count", lambda: 4)
    monkeypatch.setattr(resource_module, "discover_openblas_directory", lambda: None)
    parent = {"LD_LIBRARY_PATH": "/existing", "OPENBLAS_NUM_THREADS": "99"}
    environment = SolverResources(8, 2).environment(parent)
    assert environment["HISTRA_NUMBA_THREADS"] == "4"
    assert environment["NUMBA_NUM_THREADS"] == "4"
    assert environment["OPENBLAS_NUM_THREADS"] == "2"
    assert environment["LD_LIBRARY_PATH"] == "/existing"
    assert parent == {"LD_LIBRARY_PATH": "/existing", "OPENBLAS_NUM_THREADS": "99"}


@pytest.mark.parametrize("settings", [SolverResources(0, 1), SolverResources(1, -1), SolverResources(True, 1)])
def test_invalid_thread_budgets_fail_before_launch(settings):
    with pytest.raises(ValueError, match="positive integer"):
        settings.environment()


def test_incomplete_native_runtime_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="complete LP64 OpenBLAS"):
        SolverResources(1, 1, tmp_path).environment()


def test_ilp64_blas_is_rejected_before_sparse_solving(tmp_path, monkeypatch):
    import ctypes

    (tmp_path / "libopenblas.so.0").touch()
    monkeypatch.setenv("LD_LIBRARY_PATH", str(tmp_path))
    native = SimpleNamespace(openblas_get_config=Mock(return_value=b"OpenBLAS USE64BITINT"))
    monkeypatch.setattr(ctypes, "CDLL", lambda path: native)
    with pytest.raises(ValueError, match="ILP64"):
        resource_module.validate_native_blas()


def test_large_worker_preserves_complete_response_and_exports_bundle(tmp_path):
    requests = (PythonAnalysisRequest("Vert", None, 120),)
    baseline = run_python_solver_job(MODEL, requests, timeout_seconds=120,
                                     equilibrium_policy="off", strategy_policy="off")
    job = PythonSolverJob(MODEL, requests, 120, equilibrium_policy="off", strategy_policy="off",
                          output_directory=tmp_path)
    outcome = run_large_solver_job(job, resources=SolverResources(2, 2))
    assert outcome.completed, outcome.error
    result = outcome.result
    assert result.metadata["backend_coverage"].is_compiled_ready
    settings = result.metadata["resources"]
    assert settings["kernel_threads"] == "2"
    assert settings["blas_threads"] == "2"
    assert result.metadata["exported_results"]
    left, right = baseline.executions[0], result.executions[0]
    assert left.outcome == right.outcome
    assert len(left.steps) == len(right.steps)
    for a, b in zip(left.steps, right.steps):
        assert a["iterations"] == b["iterations"]
        for key in ("u", "load_factor", "reaction_x", "reaction_y", "reaction_z"):
            np.testing.assert_allclose(a.get(key), b.get(key), rtol=1e-9, atol=1e-9)
    for bundle in tmp_path.glob("*.histra"):
        verify_bundle(bundle)
    assert list(tmp_path.glob("*.histra"))


def test_native_benchmark_checks_refactorized_system():
    import scipy.sparse as sp
    from histra.tools.native_capacity_benchmark import measure

    matrix = sp.csc_matrix([[4., 1., 0.], [1., 5., 2.], [0., 2., 6.]])
    rhs = np.array([1., -2., 3.])
    report, solution = measure(matrix, rhs, "superlu")
    np.testing.assert_allclose(matrix @ solution, rhs, rtol=1e-13, atol=1e-13)
    assert report["refactor_residual_linf"] < 1e-13
    assert report["backend"] == "superlu"


def test_zero_rhs_cannot_masquerade_as_precision_validation(tmp_path):
    import scipy.sparse as sp
    from histra.tools.native_capacity_benchmark import main

    sp.save_npz(tmp_path / "matrix.npz", sp.eye(3, format="csc"))
    np.save(tmp_path / "rhs.npy", np.zeros(3))
    with pytest.raises(SystemExit) as failure:
        main([str(tmp_path / "matrix.npz"), str(tmp_path / "rhs.npy"),
              "--output", str(tmp_path / "report.json")])
    assert failure.value.code == 2
    assert not (tmp_path / "report.json").exists()


def test_cooperative_cancellation_keeps_committed_output(tmp_path):
    from histra import SimulationResults
    from histra.solver.cancellation import SolverCancelled

    cancelled = [False]

    def log(message):
        if message.startswith("Step 1: committed"):
            cancelled[0] = True

    with pytest.raises(SolverCancelled):
        run_python_solver_job(
            MODEL, (PythonAnalysisRequest("Vert", None, 120),), timeout_seconds=120,
            equilibrium_policy="off", strategy_policy="off", output_directory=tmp_path,
            should_cancel=lambda: cancelled[0], on_log=log,
        )
    bundle, = tmp_path.glob("*.histra")
    verify_bundle(bundle)
    with SimulationResults.load(bundle) as result:
        assert 1 in result.steps
