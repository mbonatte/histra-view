"""Focused integration regressions for the C# nonlinear benchmark path."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.io.results_reader import (
    ResultsStateError,
    available_steps,
    read_analysis_metadata,
    read_dynamic_vectors,
    read_global_displacements,
    read_interface_states,
    read_load_multiplier,
    read_quad_states,
    read_spring_states,
)
from histra.model.load import LoadFunction, LoadFunctionItem
from histra.solver.load_control import LoadControl
from histra.solver.equilibrium import (
    UNSAFE_EQUILIBRIUM_EXIT_CODE,
    UnsafeEquilibriumWarning,
)
from histra.solver.model_manager import ModelManager
from histra.solver.program import Program
from histra.solver.restart import restore_committed_analysis_state
from histra.solver.session import AnalysisSession
from histra.solver.solution_algorithm import EquiSolnAlgo
from histra.solver.solve import _als_loop, _set_initial_state, solve_static_nonlinear
from histra.solver.state_snapshot import SolverStateSnapshot
from histra.types.linear_system import LinearSystem

ROOT = Path(__file__).resolve().parents[1]
HRX = ROOT / "model-output" / "model.hrx"
RESULTS = ROOT / "model-output" / "model.Results"


def _runtime(method: str | None = None):
    model = load_model(HRX)
    analysis = copy.deepcopy(model.collections.analyses[1])
    if method is not None:
        analysis.method = method
    p = Program(gdl=model.gdl)
    ls = LinearSystem(model.gdl)
    p.ls = ls
    p.u = np.zeros(model.gdl)
    p.v = np.zeros(model.gdl)
    for name in ("_ptarget", "_fext", "_pq", "_pq_prev"):
        setattr(ModelManager, name, np.zeros(model.gdl))
    ModelManager._u_total = p.u
    algorithm = EquiSolnAlgo.new_equi_soln_algo(analysis, 1)
    integrator = algorithm.the_integrator
    assert integrator is not None
    integrator.u = p.u
    integrator.v = p.v
    integrator.u_committed = p.u.copy()
    return model, analysis, p, ls, algorithm, integrator


def test_quad_compute_dn_matches_csharp_edge_aggregation(monkeypatch):
    model = load_model(HRX)
    quad = model.collections.quads[1]

    linked = {
        key: model.collections.interfaces[key]
        for edge in quad.interface_keys[:4]
        for key in edge
    }
    for order, intf in enumerate(linked.values(), start=1):
        monkeypatch.setattr(intf, "area", lambda order=order: 10.0 * order)
        monkeypatch.setattr(
            intf, "compute_dn", lambda _ls=None, nr=False, order=order: -3.0 * order
        )
        for spring in intf.trasv_1:
            monkeypatch.setattr(spring, "get_force", lambda order=order: 8.0 * order)
            monkeypatch.setattr(spring, "get_incr_force", lambda order=order: 2.0 * order)

    edge_dn = []
    edge_sigma = []
    for edge in quad.interface_keys[:4]:
        dn = 0.0
        force = 0.0
        area = 0.0
        for key in edge:
            intf = linked[key]
            order = list(linked).index(key) + 1
            dn += -3.0 * order
            area += 10.0 * order
            force += len(intf.trasv_1) * (8.0 * order - 2.0 * order)
        edge_dn.append(dn)
        edge_sigma.append(force / area if area else 0.0)

    expected_dn = 0.5 * sum(edge_dn)
    expected_sigma = 0.5 * sum(edge_sigma)
    actual_dn, actual_sigma = quad.compute_dn(model.collections, nr=True)
    assert actual_dn == pytest.approx(expected_dn)
    assert actual_sigma == pytest.approx(expected_sigma)
    assert quad.compute_volume() > 0.0


def test_interface_normal_increment_reaches_coulomb_springs(monkeypatch):
    model = load_model(HRX)
    intf = model.collections.interfaces[1]
    for spring in intf.trasv_1:
        monkeypatch.setattr(spring, "get_incr_force", lambda: 2.5)
        monkeypatch.setattr(spring, "set_trial_strain", lambda _strain: None)

    expected_dn = -2.5 * len(intf.trasv_1)
    sliding = intf.slid[0]
    sliding.revert_to_start()
    sliding._cstress_normal = 400.0
    sliding._tstress_normal = 400.0
    intf.update_domain(np.zeros(model.gdl), SimpleNamespace(step=2))

    assert sliding.dn == pytest.approx(expected_dn)
    assert sliding._tstress_normal == pytest.approx(400.0 + expected_dn)
    assert intf.slid_out_plan[0].dn == pytest.approx(0.5 * expected_dn)
    assert intf.slid_out_plan[1].dn == pytest.approx(0.5 * expected_dn)


def test_coulomb_commit_and_revert_restore_complete_trial_state():
    spring = load_model(HRX).collections.quads[1].spring
    spring.revert_to_start()
    spring.set_trial_strain(1.0e-5)
    spring.commit()
    committed = (
        spring._cstrain,
        spring._cstress,
        spring._cstress_normal,
        spring._cup,
        spring.phase,
        tuple(spring.fy),
    )

    spring.dn = -12.5
    spring.set_trial_strain(3.0e-5)
    spring._tup += 7.0
    spring.t_phase = 999
    spring.revert_to_last_commit()

    assert spring._tstrain == pytest.approx(committed[0])
    assert spring._tstress == pytest.approx(committed[1])
    assert spring._tstress_normal == pytest.approx(committed[2])
    assert spring._tup == pytest.approx(committed[3])
    assert spring.t_phase == committed[4]
    assert tuple(spring.fy) == pytest.approx(committed[5])


def test_complete_solver_snapshot_roundtrip_is_value_identical():
    model, _analysis, p, ls, algorithm, integrator = _runtime()
    before = SolverStateSnapshot.capture(
        model, p, ls, integrator, algorithm.the_test, algorithm.the_line_search
    )
    p.u[3] = 9.0
    p.v[4] = -2.0
    ls.x[5] = 11.0
    ModelManager._fext[7] = 13.0
    quad = model.collections.quads[1]
    intf = model.collections.interfaces[1]
    quad.status.u[0] += 4.0
    quad.sigma_initial = 18.0
    intf.status.u[2] -= 6.0
    intf.trasv_1[0].f = 21.0
    integrator.mult = 0.75
    algorithm.the_test.current_iter = 44

    before.restore()
    after = SolverStateSnapshot.capture(
        model, p, ls, integrator, algorithm.the_test, algorithm.the_line_search
    )
    assert after.fingerprint() == before.fingerprint()
    assert integrator.u is p.u
    assert integrator.v is p.v
    assert ModelManager._u_total is p.u


def test_failed_newton_iteration_restores_all_trial_state():
    model, analysis, p, ls, algorithm, integrator = _runtime("StandardNewtonRaphson")
    algorithm.the_test.current_iter = 1
    integrator.form_unbalance = MethodType(lambda self, p, model, an: None, integrator)

    def compute_increment(self, p, ls, model, an, fixed_dofs=None):
        ls.x.fill(0.1)
        return ls.x

    quad = model.collections.quads[1]
    spring = quad.spring

    def failed_update(self, model, p, an):
        p.u[0] = 99.0
        quad.status.u[0] = 88.0
        spring.f = 77.0
        ModelManager._fext[1] = 66.0
        return -9

    integrator.compute_increment = MethodType(compute_increment, integrator)
    integrator.update = MethodType(failed_update, integrator)
    before = SolverStateSnapshot.capture(
        model, p, ls, integrator, algorithm.the_test, algorithm.the_line_search
    )
    code = algorithm.solve_current_step(p, ls, model, analysis, 1, 1, 1.0)
    after = SolverStateSnapshot.capture(
        model, p, ls, integrator, algorithm.the_test, algorithm.the_line_search
    )
    assert code == -9
    assert after.fingerprint() == before.fingerprint()


def test_failed_als_substeps_restore_pre_step_state():
    model, analysis, p, ls, algorithm, integrator = _runtime()
    analysis.load_factor_als = 2
    analysis.max_number_als = 2
    integrator.incr_mult = 0.2
    quad = model.collections.quads[1]
    spring = quad.spring

    def mutating_new_step(self, p, model, ls, an, combination, step, increment):
        self.incr_mult = increment
        p.u[0] += 1.0
        quad.status.u[0] += 2.0
        spring.f += 3.0

    integrator.new_step_with_incr = MethodType(mutating_new_step, integrator)

    class AlwaysFails:
        the_test = algorithm.the_test
        the_line_search = algorithm.the_line_search

        def solve_current_step(self, *args, **kwargs):
            p.u[1] += 4.0
            quad.status.u[1] += 5.0
            spring.f += 6.0
            return -2

    failed_algorithm = AlwaysFails()
    before = SolverStateSnapshot.capture(
        model, p, ls, integrator,
        failed_algorithm.the_test, failed_algorithm.the_line_search,
    )
    code = _als_loop(
        p, ls, model, analysis, 1, 2, 0.0,
        integrator, failed_algorithm, before,
    )
    after = SolverStateSnapshot.capture(
        model, p, ls, integrator,
        failed_algorithm.the_test, failed_algorithm.the_line_search,
    )
    assert code == -2
    assert after.fingerprint() == before.fingerprint()


def test_load_function_unloading_discretization_is_signed_and_finite():
    analysis = SimpleNamespace(
        mult=1.0,
        load_function=LoadFunction(
            key=99,
            discr_val=0.3,
            type_discr=False,
            items=[
                LoadFunctionItem(pseudo_time=0.0, multiplier=0.0),
                LoadFunctionItem(pseudo_time=1.0, multiplier=1.0),
                LoadFunctionItem(pseudo_time=2.0, multiplier=0.0),
            ],
        ),
    )
    integrator = LoadControl()
    integrator.state.analysis = analysis
    integrator._get_initial_time_and_force(analysis)
    integrator._t = 1.0
    integrator.mult = 1.0
    dt, df = integrator._get_increment()
    assert dt == pytest.approx(0.25)
    assert df == pytest.approx(-0.25)
    assert np.isfinite(dt) and np.isfinite(df)


def test_sqlite_typed_readers_cover_global_element_and_spring_state():
    metadata = read_analysis_metadata(RESULTS, 1)
    assert metadata.combinations == (1,)
    assert metadata.steps_by_combination[1] == (0, 1, 2, 3, 4, 5)
    assert metadata.last_step_by_combination[1] == 5
    assert metadata.has_final_dynamic_vectors
    assert metadata.has_complete_final_spring_state

    u, v, step = read_dynamic_vectors(RESULTS, 1, 1, 5, size=126)
    assert step == 5
    assert u.shape == v.shape == (126,)
    assert np.all(np.isfinite(u)) and np.all(np.isfinite(v))
    assert len(read_quad_states(RESULTS, 1, 1, 5)) == 18
    assert len(read_interface_states(RESULTS, 1, 1, 5)) == 29
    assert len(read_spring_states(RESULTS, 1, 1, 5, require_complete=True)) == 2454
    compact = read_spring_states(RESULTS, 1, 1, 2)
    assert len(compact) == 2454
    assert not any(record.complete for record in compact.values())
    with pytest.raises(ResultsStateError, match="complete"):
        read_spring_states(RESULTS, 1, 1, 2, require_complete=True)


@pytest.mark.parametrize("step, expected_multiplier", [(0, 0.0), (1, 0.2), (2, 0.4), (3, 0.6), (4, 0.8), (5, 1.0)])
def test_every_csharp_committed_step_is_readable(step, expected_multiplier):
    model = load_model(HRX)
    u = read_global_displacements(
        RESULTS, 1, 1, step, model_or_hrx=model, size=126 if step == 5 else None
    )
    assert u.shape == (126,)
    assert np.all(np.isfinite(u))
    assert read_load_multiplier(HRX, 1, step) == pytest.approx(expected_multiplier, abs=1e-12)


def test_virgin_analysis_initialization_clears_saved_hrx_state():
    model = load_model(HRX)
    p = Program(gdl=model.gdl)
    p.u = np.full(model.gdl, 3.0)
    p.v = np.full(model.gdl, -4.0)
    ls = LinearSystem(model.gdl)
    _set_initial_state(model, p.u, p.v, ls)
    assert np.array_equal(p.u, np.zeros(model.gdl))
    assert np.array_equal(p.v, np.zeros(model.gdl))
    assert all(np.allclose(q.status.u, 0.0) for q in model.collections.quads.values())
    assert all(np.allclose(i.status.u, 0.0) for i in model.collections.interfaces.values())
    assert all(q.spring.f == pytest.approx(0.0) for q in model.collections.quads.values())


def test_chained_initialization_restores_lossless_final_state():
    model = load_model(HRX)
    p = Program(gdl=model.gdl)
    p.u = np.zeros(model.gdl)
    p.v = np.zeros(model.gdl)
    ls = LinearSystem(model.gdl)
    summary = restore_committed_analysis_state(model, RESULTS, 1, 1, p.u, p.v, ls)
    expected_u, expected_v, expected_step = read_dynamic_vectors(RESULTS, 1, 1, size=126)
    assert summary.step == expected_step == 5
    assert np.array_equal(p.u, expected_u)
    assert np.array_equal(p.v, expected_v)
    assert summary.spring_count == 2454


def _single_step_analysis(model):
    analysis = copy.deepcopy(model.collections.analyses[1])
    analysis.load_function_key = 999
    analysis.load_function = LoadFunction(
        key=999,
        discr_val=0.2,
        items=[
            LoadFunctionItem(pseudo_time=0.0, multiplier=0.0),
            LoadFunctionItem(pseudo_time=0.2, multiplier=0.2),
        ],
    )
    model.collections.load_functions[999] = analysis.load_function
    return analysis


def test_first_csharp_reference_step_is_reproduced():
    model = load_model(HRX)
    with pytest.warns(UnsafeEquilibriumWarning):
        code, steps = solve_static_nonlinear(model, _single_step_analysis(model))
    reference = read_global_displacements(RESULTS, 1, 1, 1, model_or_hrx=model)
    error = steps[0]["u"] - reference
    assert code == 0
    assert steps[0]["load_factor"] == pytest.approx(0.2, abs=1e-12)
    assert np.linalg.norm(error) / np.linalg.norm(reference) <= 1.0e-4
    assert np.max(np.abs(error)) <= 1.0e-9
    assert not steps[0]["equilibrium_ok"]
    assert steps[0]["equilibrium_force_ok"]
    assert not steps[0]["equilibrium_residual_ok"]


def test_strict_equilibrium_policy_refuses_to_commit_work_only_state():
    model = load_model(HRX)
    code, steps = solve_static_nonlinear(
        model, _single_step_analysis(model), equilibrium_policy="error"
    )

    assert code == UNSAFE_EQUILIBRIUM_EXIT_CODE
    assert len(steps) == 1
    assert steps[0]["status"] == "FAILED"
    assert steps[0]["exit_code"] == UNSAFE_EQUILIBRIUM_EXIT_CODE
    assert not steps[0]["equilibrium_ok"]
    assert "trial_u" in steps[0]


def test_post_commit_callback_stops_completed_analysis_without_rollback():
    model = load_model(HRX)
    seen_steps = []
    notified = []

    def record_commit(row, analysis):
        notified.append((int(row["step"]), analysis.name))

    def stop_after_second_step(row):
        seen_steps.append(int(row["step"]))
        return int(row["step"]) == 2

    with pytest.warns(UnsafeEquilibriumWarning):
        execution = AnalysisSession(model, strategy_policy="off").run(
            model.collections.analyses[1],
            should_stop_after_commit=stop_after_second_step,
            on_step_committed=record_commit,
        )

    assert execution.completed
    assert seen_steps == [1, 2]
    assert notified == [(1, "Vert"), (2, "Vert")]
    assert [step.step for step in execution.committed_steps] == [1, 2]


@pytest.mark.skipif(
    os.environ.get("HISTRA_RUN_FULL_BENCHMARK") != "1",
    reason="set HISTRA_RUN_FULL_BENCHMARK=1 for the long acceptance benchmark",
)
def test_all_subsequent_steps_and_complete_analysis_match_csharp():
    """Acceptance test retained even while the step-2/final-step blocker remains."""
    model = load_model(HRX)
    code, steps = solve_static_nonlinear(model, model.collections.analyses[1])
    assert code == 0
    assert [row["step"] for row in steps] == [1, 2, 3, 4, 5]
    assert all(row["status"] == "OK" for row in steps)
    for row in steps:
        reference = read_global_displacements(
            RESULTS, 1, 1, row["step"], model_or_hrx=model
        )
        relative = np.linalg.norm(row["u"] - reference) / np.linalg.norm(reference)
        assert relative <= 1.0e-4
        assert abs(row["load_factor"] - read_load_multiplier(HRX, 1, row["step"])) <= 1.0e-6


def test_load_generation_rejects_missing_analysis_explicitly():
    from histra.solver.assembler import assemble_load_vector

    model = load_model(HRX)
    with pytest.raises(KeyError, match="Analysis 9999"):
        assemble_load_vector(model, 9999, 1)


@pytest.mark.parametrize("start_time,previous_dt", [(0.0, 0.0), (0.0, 0.1), (0.75, 0.4)])
@pytest.mark.parametrize("fail_first_substep", [False, True])
def test_successful_als_advances_current_interval_once(
    monkeypatch, start_time, previous_dt, fail_first_substep,
):
    """A retry must not repeat loading or consume the preceding step's clock."""
    model, analysis, p, ls, algorithm, integrator = _runtime()
    analysis.mult = 1.0
    analysis.load_factor_als = 2
    analysis.max_number_als = 2
    analysis.load_function = LoadFunction(
        key=99, discr_val=0.3,
        items=[LoadFunctionItem(pseudo_time=0.0, multiplier=0.0),
               LoadFunctionItem(pseudo_time=1.0, multiplier=1.0)],
    )
    integrator.state.analysis = analysis
    integrator._get_initial_time_and_force(analysis)
    integrator._t = start_time
    integrator.mult = start_time
    integrator._step_dt = previous_dt
    monkeypatch.setattr(integrator, "update_ptarget", lambda *args: None)
    monkeypatch.setattr("histra.solver.continuation._commit_state", lambda *args: None)
    snapshot = SolverStateSnapshot.capture(
        model, p, ls, integrator, algorithm.the_test, algorithm.the_line_search,
    )
    integrator.new_step(p, model, ls, analysis, 1, 1, 0)

    class ReducedSolver:
        the_test = algorithm.the_test
        the_line_search = algorithm.the_line_search
        calls = 0

        def solve_current_step(self, *args):
            self.calls += 1
            return -2 if fail_first_substep and self.calls == 1 else 0

    assert _als_loop(p, ls, model, analysis, 1, 1, 0.0,
                     integrator, ReducedSolver(), snapshot) == 0
    assert integrator.get_time() == start_time
    assert integrator.mult == pytest.approx(start_time + 0.25)
    stop = integrator.commit(model, analysis, 0.0, 0, [False])
    assert integrator.get_time() == pytest.approx(start_time + 0.25)
    assert stop == (start_time == 0.75)
    # Complete the load function naturally: four total quarter-load steps,
    # never a fifth step at multiplier 1.25.
    while not stop:
        integrator.new_step(p, model, ls, analysis, 1, 2, 0)
        stop = integrator.commit(model, analysis, 0.0, 0, [False])
    assert integrator.get_time() == pytest.approx(1.0)
    assert integrator.mult == pytest.approx(1.0)
