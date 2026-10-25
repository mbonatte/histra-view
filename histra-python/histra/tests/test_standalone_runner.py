"""Standalone Vert -> Live Load execution and output regressions."""
from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.postprocessing import compute_node_displacements, compute_total_reaction
from histra.solver.arc_length import ArcLength
from histra.solver.line_search import RegulaFalsiLineSearch
from histra.solver.restart import restore_committed_analysis_state
from histra.solver.solve import solve_static_nonlinear
from histra.tools.run_vert_live import _resolve_analysis
from histra.types.linear_system import LinearSystem

pytestmark = pytest.mark.filterwarnings(
    "ignore::histra.solver.equilibrium.UnsafeEquilibriumWarning"
)

ROOT = Path(__file__).resolve().parents[1]
HRX = ROOT / "model-live" / "model.hrx"
RESULTS = ROOT / "model-live" / "model.Results"


def _restore_vert_final():
    model = load_model(HRX)
    u = np.zeros(model.gdl)
    v = np.zeros(model.gdl)
    ls = LinearSystem(model.gdl)
    restore_committed_analysis_state(model, RESULTS, 1, 1, u, v, ls)
    return model, u


def test_total_reaction_matches_csharp_reaction_sum_exactly():
    model, _u = _restore_vert_final()
    reaction = compute_total_reaction(model)
    with sqlite3.connect(RESULTS) as connection:
        reference = connection.execute(
            "SELECT R1, R2, R3 FROM ReactionSumStates "
            "WHERE AnalysisKey=1 AND Combination=1 AND Step=5"
        ).fetchone()

    assert (reaction.x, reaction.y, reaction.z) == reference
    assert reaction.balancing_z == -reference[2]


def test_node_displacements_export_global_xyz_for_every_model_node():
    model, u = _restore_vert_final()
    rows = compute_node_displacements(model, u)

    assert len(rows) == len(model.collections.nodes)
    assert all(row.contributing_quads > 0 for row in rows)
    assert all(
        np.isfinite(
            [row.x, row.y, row.z, row.ux, row.uy, row.uz,
             row.deformed_x, row.deformed_y, row.deformed_z]
        ).all()
        for row in rows
    )
    assert max(abs(row.uz) for row in rows) > 0.0


def test_in_memory_live_restart_does_not_read_results_database(monkeypatch):
    model, vert_u = _restore_vert_final()
    original_commit = ArcLength.commit

    def stop_after_first(self, model_, analysis, disp, dof, changed):
        original_commit(self, model_, analysis, disp, dof, changed)
        return True

    monkeypatch.setattr(ArcLength, "commit", stop_after_first)
    monkeypatch.setattr(
        "histra.solver.solve.find_results_path",
        lambda _path: (_ for _ in ()).throw(AssertionError("database lookup used")),
    )

    code, rows = solve_static_nonlinear(
        model,
        copy.deepcopy(model.collections.analyses[22]),
        1,
        initial_displacement=vert_u,
        restart_from_current_state=True,
    )

    assert code == 0
    assert len(rows) == 1
    assert rows[0]["status"] == "OK"
    assert rows[0]["iterations"] == 54
    assert np.isfinite(rows[0]["reaction_z"])


def test_analysis_autoselection_prefers_vert_and_primary_live_load():
    model = load_model(HRX)
    assert _resolve_analysis(model, None, "vert").key == 1
    assert _resolve_analysis(model, None, "live").key == 22
    assert _resolve_analysis(model, "LiveLoad_1", "live").key == 22
    assert _resolve_analysis(model, "22", "live").name == "LiveLoad_1"


def test_regula_falsi_replays_csharp_sign_cycle_exactly():
    class FakeLS:
        def __init__(self):
            self.x = np.array([1.0])
            self.b = np.array([0.0])

        def set_x_vector(self, value):
            self.x = np.asarray(value, dtype=float).copy()

    class FakeIntegrator:
        def __init__(self, ls):
            self.ls = ls
            self.eta = 1.0
            self.update_calls = 0

        def update(self, _model, _p, _an):
            self.eta += float(self.ls.x[0])
            self.update_calls += 1
            return 0

        def form_unbalance(self, _p, _model, _an):
            # Positive trial dU.R opposes the stored negative s1 and remains
            # above tolerance, triggering the C# endpoint cycle.
            self.ls.b[:] = 0.9

    ls = FakeLS()
    integrator = FakeIntegrator(ls)
    search = RegulaFalsiLineSearch()
    search.tolerance = 0.8
    search.max_eta = 10.0
    search.min_eta = 0.1
    search.max_iter = 1000

    eta = search.search(None, None, ls, integrator, None, np.array([1.0]), -1.0, -0.99)

    assert eta == pytest.approx(1.0)
    assert integrator.eta == pytest.approx(1.0)
    # The C# implementation does not collapse this endpoint cycle.  Replaying
    # all 61 updates matters because each incremental operation can perturb a
    # nearly symmetric nonlinear state at the last-bit level.
    assert integrator.update_calls == 61
    assert ls.x == pytest.approx([1.0])


def test_configured_displacement_limit_uses_model_wide_max_not_graph_dof():
    from histra.tools.run_vert_live import _analysis_status

    class Analysis:
        max_u = 1.0

    rows = [
        {
            "step": 88,
            "status": "FAILED",
            "displacement": 1.0e-12,
            "max_element_displacement": 1.000006,
        }
    ]
    assert _analysis_status(-3, rows, Analysis()) == "completed_at_configured_displacement_limit"


def test_step_csv_explains_total_and_incremental_reaction(tmp_path):
    import csv
    from types import SimpleNamespace
    from histra.tools.run_vert_live import _initial_record, _write_step_csv

    initial = _initial_record(np.zeros(1), (0.0, 0.0, -10.0))
    current = dict(initial)
    current.update(
        step=1,
        status="OK",
        exit_code=5,
        reaction_z=-14.0,
        balancing_reaction_z=14.0,
        max_element_displacement=0.25,
        max_element_type="Quad",
        max_element_key=7,
    )
    path = tmp_path / "steps.csv"
    _write_step_csv(path, SimpleNamespace(key=22, name="LiveLoad_1"), [initial, current])

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[1]["convergence_result_code"] == "5"
    assert float(rows[1]["histra_reaction_sum_z"]) == -14.0
    assert float(rows[1]["total_support_reaction_z"]) == 14.0
    assert float(rows[1]["incremental_support_reaction_z"]) == 4.0
    assert float(rows[1]["max_element_displacement"]) == 0.25
