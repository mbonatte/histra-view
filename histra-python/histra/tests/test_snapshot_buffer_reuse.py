"""Reusable storage must preserve complete reversible constitutive state."""
from pathlib import Path
import numpy as np
import pytest
from histra.io.hr_loader import load_model
from histra.solver.model_manager import ModelManager
from histra.solver.hysteretic_runtime import build_hysteretic_batch


@pytest.fixture
def runtime():
    model = load_model(Path(__file__).resolve().parents[1] / "model-live/model.hrx")
    ModelManager.prepare_model(model, force=True)
    result = build_hysteretic_batch(model)
    assert result is not None
    return result


def test_reused_snapshot_matches_fresh_snapshot_and_reverts_trial(runtime):
    buffers = runtime.snapshot()
    independent = runtime.snapshot()
    original = tuple(value.copy() for value in independent)
    state = type("State", (), {"step": 1})()
    increment = np.linspace(-1e-4, 2e-4, runtime.model.gdl)
    # Include committed history, reversal and subsequent rejected trial.
    runtime.update_domain(increment, state)
    runtime.commit(sync_objects=False)
    runtime.update_domain(-2.5 * increment, state)
    expected = runtime.snapshot()
    captured = runtime.snapshot(reuse=buffers)
    assert captured is buffers
    for actual, reference in zip(captured, expected):
        np.testing.assert_array_equal(actual, reference)
    for actual, reference in zip(independent, original):
        np.testing.assert_array_equal(actual, reference)
    runtime.update_domain(0.75 * increment, state)
    runtime.restore(captured)
    for actual, reference in zip(runtime.snapshot(), expected):
        np.testing.assert_array_equal(actual, reference)


@pytest.mark.parametrize("invalid", ["count", "shape", "dtype", "readonly", "live", "overlap"])
def test_invalid_reuse_is_rejected_before_modifying_buffers(runtime, invalid):
    buffers = list(runtime.snapshot())
    if invalid == "count":
        buffers.pop()
    elif invalid == "shape":
        buffers[-1] = np.empty((1,))
    elif invalid == "dtype":
        wrong_dtype = np.float64 if buffers[-1].dtype == np.float32 else np.float32
        buffers[-1] = buffers[-1].astype(wrong_dtype)
    elif invalid == "readonly":
        buffers[-1].flags.writeable = False
    elif invalid == "live":
        buffers[0] = runtime.committed
    else:
        # Equal-sized slices of one backing allocation are invalid storage.
        size = max(buffers[0].size, buffers[1].size)
        shared = np.empty(size)
        buffers[0] = shared[:buffers[0].size].reshape(buffers[0].shape)
        buffers[1] = shared[:buffers[1].size].reshape(buffers[1].shape)
    before = [value.copy() for value in buffers]
    with pytest.raises(ValueError, match="Snapshot buffer"):
        runtime.snapshot(reuse=tuple(buffers))
    for actual, reference in zip(buffers, before):
        np.testing.assert_array_equal(actual, reference)


@pytest.mark.parametrize("minimum_bytes, expected_reuse", [(0, True), (1 << 20, False)])
def test_newton_selects_lossless_iteration_storage(monkeypatch, minimum_bytes, expected_reuse):
    import warnings
    from histra.solver.state_snapshot import SolverStateSnapshot
    from histra.solver.session import AnalysisSession
    from histra.solver.equilibrium import UnsafeEquilibriumWarning

    import histra.solver.newton_raphson as newton_module

    monkeypatch.setattr(newton_module, "_BATCH_SNAPSHOT_REUSE_MIN_BYTES", minimum_bytes)
    original = SolverStateSnapshot.capture.__func__
    reused = []
    iteration_states = []

    def capture(cls, model, *args, **kwargs):
        buffers = kwargs.get("reuse_batch_state")
        result = original(cls, model, *args, **kwargs)
        if "reuse_batch_state" in kwargs:
            iteration_states.append(result.batch_state)
        if buffers is not None:
            reused.append(buffers)
            assert result.batch_state is buffers
            runtime = ModelManager.hysteretic_batch_for(model)
            for actual, expected in zip(result.batch_state, runtime.snapshot()):
                np.testing.assert_array_equal(actual, expected)
        return result

    monkeypatch.setattr(SolverStateSnapshot, "capture", classmethod(capture))
    model = load_model(Path(__file__).resolve().parents[1] / "model-live/model.hrx")
    analysis = next(a for a in model.collections.analyses.values() if a.name == "Vert")
    analysis.method = "ModifiedNewtonRaphson"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UnsafeEquilibriumWarning)
        execution = AnalysisSession(
            model, equilibrium_policy="warn", linear_solver_backend="superlu",
            strategy_policy="off",
        ).run("Vert", max_committed_steps=1)
    assert len(execution.committed_steps) == 1
    assert len(iteration_states) > 1
    assert bool(reused) is expected_reuse
    if not expected_reuse:
        for previous, current in zip(iteration_states, iteration_states[1:]):
            for before, after in zip(previous, current):
                assert not np.shares_memory(before, after)
