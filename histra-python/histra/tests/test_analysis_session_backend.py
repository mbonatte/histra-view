from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from histra.solver.cancellation import CANCELLED_EXIT_CODE
from histra.solver.outcomes import AnalysisOutcome
from histra.solver.session import AnalysisSession, AnalysisSessionError

pytestmark = pytest.mark.filterwarnings(
    "ignore::histra.solver.strategy.SuboptimalSolverStrategyWarning"
)


def _model() -> SimpleNamespace:
    root = SimpleNamespace(key=1, name="Root", initial_analysis_key=-100, max_u=1.0)
    child = SimpleNamespace(key=2, name="Child", initial_analysis_key=1, max_u=1.0)
    collections = SimpleNamespace(analyses={1: root, 2: child})
    return SimpleNamespace(collections=collections, gdl=2)


def test_session_exposes_step_zero_and_committed_state(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model()

    def fake_solve(*args, **kwargs):
        return 0, [
            {
                "step": 1,
                "status": "OK",
                "exit_code": 0,
                "u": np.array([1.0, 2.0]),
                "reaction_x": 10.0,
                "reaction_y": 20.0,
                "reaction_z": 30.0,
            }
        ]

    monkeypatch.setattr("histra.solver.session.solve_static_nonlinear", fake_solve)
    session = AnalysisSession(model)

    execution = session.run("Root")

    assert execution.outcome is AnalysisOutcome.COMPLETED
    assert execution.initial_step is not None
    assert execution.initial_step.step == 0
    assert np.array_equal(execution.initial_step.u, np.zeros(2))
    assert session.current_analysis_key == 1
    assert np.array_equal(session.current_displacement, np.array([1.0, 2.0]))


def test_session_uses_predecessor_state_for_chained_step_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model()
    calls = 0

    def fake_solve(*args, **kwargs):
        nonlocal calls
        calls += 1
        return 0, [
            {
                "step": 1,
                "status": "OK",
                "exit_code": 0,
                "u": np.array([float(calls), float(calls + 1)]),
                "reaction_x": float(calls),
                "reaction_y": float(calls + 10),
                "reaction_z": float(calls + 20),
            }
        ]

    monkeypatch.setattr("histra.solver.session.solve_static_nonlinear", fake_solve)
    monkeypatch.setattr(
        "histra.solver.session.compute_total_reaction",
        lambda model: SimpleNamespace(x=7.0, y=8.0, z=9.0),
    )
    session = AnalysisSession(model)
    root = session.run("Root")
    child = session.run("Child")

    assert child.initial_step is not None
    assert np.array_equal(child.initial_step.u, root.committed_steps[-1].u)
    assert child.initial_step.reaction_x == 7.0
    assert child.initial_step.reaction_y == 8.0
    assert child.initial_step.reaction_z == 9.0


def test_incomplete_execution_invalidates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _model()

    def fake_solve(*args, **kwargs):
        return CANCELLED_EXIT_CODE, [
            {
                "step": 1,
                "status": "CANCELLED",
                "exit_code": CANCELLED_EXIT_CODE,
                "u": np.zeros(2),
            }
        ]

    monkeypatch.setattr("histra.solver.session.solve_static_nonlinear", fake_solve)
    session = AnalysisSession(model)

    execution = session.run("Root")

    assert execution.outcome is AnalysisOutcome.CANCELLED
    assert not session.usable
    with pytest.raises(AnalysisSessionError, match="cannot be reused"):
        session.run("Root")


def test_session_dispatches_modal_analysis_without_changing_physical_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal = SimpleNamespace(
        key=30,
        name="Modal",
        initial_analysis_key=-100,
        analysis_type=5,
        max_u=1.0,
    )
    model = SimpleNamespace(
        collections=SimpleNamespace(analyses={30: modal}),
        gdl=3,
    )
    modal_result = SimpleNamespace(converged_modes=2)

    monkeypatch.setattr(
        "histra.solver.session.solve_modal_analysis",
        lambda *args, **kwargs: modal_result,
    )
    session = AnalysisSession(model)

    execution = session.run("Modal")

    assert execution.completed
    assert execution.modal_result is modal_result
    assert execution.steps == ()
    assert session.current_analysis_key == 30
    assert np.array_equal(session.current_displacement, np.zeros(3))
