from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.sparse as sp

from histra.solver.diagnostics import DiagnosticOptions, SolverDiagnostics
from histra.types.linear_system import LinearSolveError, LinearSystem
from histra.types.umfpack import find_umfpack_library


def test_superlu_backend_solves_known_system() -> None:
    system = LinearSystem(2, backend="superlu")
    system.k = sp.csc_matrix([[4.0, 1.0], [1.0, 3.0]])

    system.solve(rhs=np.array([1.0, 2.0]))

    assert system.backend == "superlu"
    assert system.x == pytest.approx([1.0 / 11.0, 7.0 / 11.0])

def test_default_backend_resolves_to_auto(monkeypatch) -> None:
    monkeypatch.delenv("HISTRA_LINEAR_SOLVER", raising=False)
    expected = "umfpack" if find_umfpack_library() is not None else "superlu"
    assert LinearSystem(1).backend == expected


def test_linear_solver_backend_validation() -> None:
    with pytest.raises(ValueError, match="auto, umfpack, superlu, cholmod, pcg"):
        LinearSystem(1, backend="dense")


def test_requested_umfpack_has_actionable_error_when_native_library_is_absent() -> None:
    if find_umfpack_library() is not None:
        pytest.skip("native UMFPACK is available in this environment")
    system = LinearSystem(1, backend="umfpack")
    system.k = sp.eye(1, format="csc")

    with pytest.raises(LinearSolveError, match="HISTRA_UMFPACK_LIBRARY"):
        system.solve(rhs=np.ones(1))


def test_diagnostics_write_deterministic_jsonl_and_vector_snapshot(tmp_path) -> None:
    model = SimpleNamespace(
        collections=SimpleNamespace(interfaces={}, quads={}),
    )
    diagnostics = SolverDiagnostics(
        DiagnosticOptions(tmp_path, capture_vectors=True, spring_details=False),
        model,
    )
    system = LinearSystem(2, backend="superlu")
    system.b[:] = [3.0, -4.0]
    system.x[:] = [0.25, -0.5]
    program = SimpleNamespace(u=np.array([1.0, 2.0]), ls=system)

    snapshot = diagnostics.capture_state(
        label="test", step=2, iteration=3, program=program, model=model
    )
    diagnostics.emit(
        "iteration",
        step=2,
        iteration=3,
        **diagnostics.vector_metrics(system),
    )
    diagnostics.close()

    assert snapshot == "vectors/event_000001_step_00002_iter_00003_test.npz"
    with np.load(tmp_path / snapshot) as values:
        assert values["u"] == pytest.approx([1.0, 2.0])
        assert values["du"] == pytest.approx([0.25, -0.5])
        assert values["residual"] == pytest.approx([3.0, -4.0])

    rows = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == ["iteration", "diagnostics_closed"]
    assert rows[0]["residual_norm"] == pytest.approx(5.0)
    assert rows[0]["max_residual_dof"] == 1
    assert rows[0]["max_correction_dof"] == 1


def test_diagnostics_keep_distinct_retry_snapshots(tmp_path) -> None:
    model = SimpleNamespace(collections=SimpleNamespace(interfaces={}, quads={}))
    diagnostics = SolverDiagnostics(
        DiagnosticOptions(tmp_path, capture_vectors=True, spring_details=False),
        model,
    )
    system = LinearSystem(1, backend="superlu")
    program = SimpleNamespace(u=np.zeros(1), ls=system)

    first = diagnostics.capture_state(
        label="newton", step=1, iteration=1, program=program, model=model
    )
    diagnostics.emit("iteration")
    second = diagnostics.capture_state(
        label="newton", step=1, iteration=1, program=program, model=model
    )
    diagnostics.close()

    assert first != second
    assert (tmp_path / first).is_file()
    assert (tmp_path / second).is_file()
