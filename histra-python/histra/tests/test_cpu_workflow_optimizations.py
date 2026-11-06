"""Differential loading, runtime lifecycle and process isolation contracts."""
from pathlib import Path

import numpy as np
import pytest

from histra import (
    AnalysisSession, PythonAnalysisRequest, PythonSolverJob, load_model,
    load_solver_model, run_parallel_solver_jobs, run_python_solver_job,
)
from histra.solver.model_manager import ModelManager
from histra.solver.parallel_jobs import _worker_limit

MODEL = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"


def _solve(model):
    session = AnalysisSession(model, equilibrium_policy="off", strategy_policy="off")
    execution = session.run("Vert", max_committed_steps=2)
    runtime = ModelManager.hysteretic_batch_for(model)
    assert session.backend_coverage.is_compiled_ready
    return execution, tuple(array.copy() for array in runtime.snapshot())


def test_solver_loader_preserves_fresh_response_and_source():
    source = MODEL.read_bytes()
    reference, fast = load_model(MODEL), load_solver_model(MODEL)
    assert reference.collections.interfaces
    assert not fast.collections.interfaces
    assert fast.requires_python_preparation
    assert len(reference.collections.quads) == len(fast.collections.quads)
    for key, quad in reference.collections.quads.items():
        other = fast.collections.quads[key]
        assert other.node_keys == quad.node_keys
        assert other.reference_e1 == quad.reference_e1
        assert other.reference_e2 == quad.reference_e2
        assert other.reference_e3 == quad.reference_e3
    left, left_states = _solve(reference)
    right, right_states = _solve(fast)
    assert left.code == right.code
    assert len(left.steps) == len(right.steps)
    for a, b in zip(left.steps, right.steps):
        for name in ("u", "load_factor", "reaction_x", "reaction_y", "reaction_z", "iterations"):
            np.testing.assert_array_equal(a.get(name), b.get(name))
    for a, b in zip(left_states, right_states):
        np.testing.assert_array_equal(a, b)
    assert MODEL.read_bytes() == source


def test_virgin_session_constructs_runtime_once(monkeypatch):
    import histra.solver.hysteretic_runtime as runtime_module

    original = runtime_module.HystereticBatchRuntime.__init__
    instances = []

    def capture(self, *args, **kwargs):
        instances.append(self)
        original(self, *args, **kwargs)

    monkeypatch.setattr(runtime_module.HystereticBatchRuntime, "__init__", capture)
    _solve(load_solver_model(MODEL))
    assert len(instances) == 1


def test_solver_loader_still_rejects_unsupported_elements(tmp_path):
    path = tmp_path / "unsupported.hrx"
    path.write_text('<HiStrA><Interface Key="1"><Frame Key="2"/></Interface></HiStrA>')
    from histra.solver.capabilities import inspect_solver_capabilities

    report = inspect_solver_capabilities(load_solver_model(path), [])
    assert not report.supported


def test_parallel_jobs_isolate_state_preserve_order_and_report_errors(monkeypatch):
    monkeypatch.setenv("HISTRA_NUMBA_THREADS", "1")
    requests = (PythonAnalysisRequest("Vert", None, 120),)
    baseline = run_python_solver_job(MODEL, requests, timeout_seconds=120,
                                     equilibrium_policy="off", strategy_policy="off")
    good = PythonSolverJob(MODEL, requests, 120, equilibrium_policy="off", strategy_policy="off")
    missing = PythonSolverJob(MODEL.with_name("missing.hrx"), requests, 120)
    outcomes = run_parallel_solver_jobs([good, missing, good], max_workers=2)
    assert outcomes[0].completed and outcomes[2].completed
    assert not outcomes[1].completed and "FileNotFoundError" in outcomes[1].error
    assert len({outcome.process_id for outcome in outcomes}) == 3
    for outcome in (outcomes[0], outcomes[2]):
        coverage = outcome.result.metadata["backend_coverage"]
        assert coverage.is_compiled_ready
        assert coverage.numba_threads == 1
        assert coverage.linear_solver_backend != "cudss"
        for left, right in zip(baseline.executions[0].steps, outcome.result.executions[0].steps):
            np.testing.assert_array_equal(left.get("u"), right.get("u"))
            assert left.get("iterations") == right.get("iterations")


def test_batch_limits_and_timeout():
    assert _worker_limit(4, 1, 3000, 2000) == 1
    with pytest.raises(ValueError, match="both"):
        run_parallel_solver_jobs([], memory_budget_mb=100)
    with pytest.raises(ValueError, match="positive integer"):
        run_parallel_solver_jobs([], max_workers=0)
    job = PythonSolverJob(MODEL, (PythonAnalysisRequest("Vert", None, 120),), .001)
    outcome, = run_parallel_solver_jobs([job])
    assert not outcome.completed and "TimeoutExpired" in outcome.error
