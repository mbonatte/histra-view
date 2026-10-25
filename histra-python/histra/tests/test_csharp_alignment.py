from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import scipy.sparse as sp

from histra.io.hr_loader import load_model
from histra.model.load import LoadFunction, LoadFunctionItem
from histra.solver.line_search import RegulaFalsiLineSearch
from histra.solver.load_control import LoadControl
from histra.solver.model_manager import ModelManager
from histra.solver.newton_line_search import NewtonLineSearch
from histra.solver.program import Program
from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem


def empty_model(n: int = 1):
    collections = SimpleNamespace(quads={}, interfaces={})
    return SimpleNamespace(gdl=n, collections=collections)


def test_linear_system_set_zero_preserves_vectors():
    ls = LinearSystem(2)
    ls.k = sp.eye(2, format="csc")
    ls.b[:] = [3.0, 4.0]
    ls.x[:] = [1.0, 2.0]
    ls.set_zero()
    assert ls.k.nnz == 0
    np.testing.assert_allclose(ls.b, [3.0, 4.0])
    np.testing.assert_allclose(ls.x, [1.0, 2.0])


def test_model_manager_assembles_requested_tangent(monkeypatch):
    seen = []

    def fake_assemble(model, alfa, *, recompute_elements=True):
        seen.append((alfa, recompute_elements))
        return sp.eye(model.gdl, format="csc") * (1.0 + alfa)

    monkeypatch.setattr("histra.solver.model_manager.assemble_global_k", fake_assemble)
    model = empty_model(2)
    ls = LinearSystem(2)
    ModelManager.compute_ktang(model, ls, 1.0)

    assert seen == [(1.0, False)]
    np.testing.assert_allclose(ls.k.diagonal(), [2.0, 2.0])


def test_regula_falsi_uses_eta_zero_one_bracket_and_keeps_state_consistent():
    ls = LinearSystem(1)
    p = SimpleNamespace(ls=ls)

    class DummyIntegrator:
        def __init__(self):
            self.position = 1.0  # full Newton step already applied

        def update(self, model, p, an):
            self.position += float(p.ls.x[0])
            return 0

        def form_unbalance(self, p, model, an):
            p.ls.b[:] = [1.0 - 2.0 * self.position]

    integrator = DummyIntegrator()
    search = RegulaFalsiLineSearch()
    search.tolerance = 1e-10
    search.min_eta = 0.0
    search.max_eta = 2.0
    dx = np.array([1.0])
    ls.x[:] = dx
    # At eta=0: R=1, s0=-1. At eta=1: R=-1, s1=+1.
    eta = search.search(None, p, ls, integrator, None, dx, -1.0, 1.0)
    assert eta == 0.5
    assert integrator.position == 0.5
    np.testing.assert_allclose(ls.x, [0.5])
    np.testing.assert_allclose(ls.b, [0.0])


def test_newton_line_search_uses_post_integrator_arc_length_direction():
    """Concrete C# searches read LS.X after ArcLength.Update combines it."""
    model = empty_model(1)
    ls = LinearSystem(1)
    p = Program(gdl=1, ls=ls, u=np.zeros(1), v=np.zeros(1))

    class ArcLengthLikeIntegrator:
        def form_unbalance(self, p, model, analysis):
            del model, analysis
            p.ls.b[:] = [0.0 if p.ls.x[0] == 3.0 else 2.0]

        def compute_increment(self, p, ls, model, analysis):
            del p, model, analysis
            ls.x[:] = [1.0]  # raw residual correction, delta_u_bar

        def update(self, model, p, analysis):
            del model, analysis
            p.ls.x[:] = [3.0]  # combined ArcLength correction
            return 0

    class CapturingSearch:
        def __init__(self):
            self.direction = None
            self.s0 = None
            self.s1 = None

        def new_step(self, p, ls):
            del p, ls

        def search(self, model, p, ls, integrator, analysis, direction, s0, s1):
            del model, p, ls, integrator, analysis
            self.direction = direction.copy()
            self.s0 = s0
            self.s1 = s1
            return 1.0

    search = CapturingSearch()
    algorithm = NewtonLineSearch()
    algorithm.the_integrator = ArcLengthLikeIntegrator()
    algorithm.the_line_search = search
    algorithm.the_test = ConvergenceTest(
        tolerance=1.0e-12, max_iter=2, criterion="ForceMoment"
    )
    analysis = SimpleNamespace(method="ModifiedBisectionLineSearch")

    result = algorithm.solve_current_step(
        p, ls, model, analysis, combination=1, step=1, alfa=0.0
    )

    assert result == 1
    np.testing.assert_allclose(search.direction, [3.0])
    assert search.s0 == -2.0  # C# projects the endpoint with raw delta_u_bar.
    assert search.s1 == 0.0


def test_production_line_search_projects_endpoints_on_combined_direction():
    model = empty_model(1)
    ls = LinearSystem(1)
    p = Program(gdl=1, ls=ls, u=np.zeros(1), v=np.zeros(1))

    class ArcLengthLikeIntegrator:
        def form_unbalance(self, p, model, analysis):
            del model, analysis
            p.ls.b[:] = [1.0 if p.ls.x[0] == 3.0 else 2.0]

        def compute_increment(self, p, ls, model, analysis):
            del p, model, analysis
            ls.x[:] = [1.0]

        def update(self, model, p, analysis):
            del model, analysis
            p.ls.x[:] = [3.0]
            return 0

    class CapturingSearch:
        def new_step(self, p, ls):
            del p, ls

        def search(self, model, p, ls, integrator, analysis, direction, s0, s1):
            del model, p, ls, integrator, analysis
            self.values = (direction.copy(), s0, s1)
            return 1.0

    search = CapturingSearch()
    algorithm = NewtonLineSearch()
    algorithm.the_integrator = ArcLengthLikeIntegrator()
    algorithm.the_line_search = search
    algorithm.the_test = ConvergenceTest(
        tolerance=2.0, max_iter=2, criterion="ForceMoment"
    )
    analysis = SimpleNamespace(
        method="ModifiedBisectionLineSearch",
        csharp_line_search_compatibility=False,
    )

    result = algorithm.solve_current_step(
        p, ls, model, analysis, combination=1, step=1, alfa=0.0
    )

    assert result == 1
    direction, s0, s1 = search.values
    np.testing.assert_allclose(direction, [3.0])
    assert s0 == -6.0
    assert s1 == -3.0


def test_load_control_preserves_total_displacement_between_steps():
    lf = LoadFunction(
        key=1,
        discr_val=0.5,
        items=[
            LoadFunctionItem(key=1, load_function_key=1, pseudo_time=0, multiplier=0),
            LoadFunctionItem(key=2, load_function_key=1, pseudo_time=1, multiplier=1),
        ],
    )
    analysis = SimpleNamespace(key=None, mult=1.0, load_function=lf, pdelta_effect="None")
    model = empty_model(1)
    ls = LinearSystem(1)
    p = Program(gdl=1, ls=ls, u=np.array([2.0]))
    ModelManager._ptarget = np.array([1.0])
    ModelManager._fext = np.array([0.0])

    integrator = LoadControl()
    integrator.state.analysis = analysis
    integrator.u = p.u
    integrator.u_committed = p.u.copy()
    integrator.domain_changed(p, model, 1)
    integrator.new_step(p, model, ls, analysis, 1, 1, 0)
    assert integrator.u[0] == 2.0
    ls.x[:] = [0.25]
    integrator.update(model, p, analysis)
    assert integrator.u[0] == 2.25


def test_rollback_uses_vector_setter():
    model = empty_model(2)
    ls = LinearSystem(2)
    integrator = LoadControl()
    integrator.u = np.array([4.0, 5.0])
    integrator.u_committed = np.array([1.0, 2.0])
    integrator.revert_to_last_commit(model, ls)
    np.testing.assert_allclose(integrator.u, [1.0, 2.0])
    np.testing.assert_allclose(ls.x, [-3.0, -3.0])


def test_convergence_criteria_and_max_u():
    class Element:
        def max_u(self):
            return 2.5

    model = SimpleNamespace(collections=SimpleNamespace(quads={1: Element()}, interfaces={}))
    p = Program(max_u=0.0)
    ls = LinearSystem(1)
    ls.b[:] = [0.2]
    test = ConvergenceTest(tolerance=0.1, max_iter=3, max_u=2.0, criterion="ForceMoment")
    test.start()
    assert test.test(p, model, ls) == -3
    assert test.get_error() == 0.2


def test_find_max_u_excludes_interface_displacements_like_csharp():
    quad = SimpleNamespace(key=11, max_u=lambda: 2.5)
    interface = SimpleNamespace(key=22, max_u=lambda: 9.0)
    model = SimpleNamespace(
        collections=SimpleNamespace(quads={11: quad}, interfaces={22: interface})
    )
    p = Program()

    ModelManager.clear_hysteretic_batch()
    ModelManager.find_max_u(model, p)

    assert p.max_u == 2.5
    assert p.elem_max_u_key == 11
    assert p.elem_max_u_type == "Quad"


def test_loader_attaches_csharp_load_function_items(tmp_path):
    path = tmp_path / "minimal.hrx"
    path.write_text(
        '''<HiStrA Version="1" GDL="0">
        <LoadFunction Key="5" Name="cycle" typeDiscr="true" DiscrVal="0.25" />
        <LoadFunctionItem Key="2" LoadFunctionKey="5" pseudoTime="1" multiplier="-1" />
        <LoadFunctionItem Key="1" LoadFunctionKey="5" pseudoTime="0" multiplier="0" />
        <Analysis Key="7" LoadFunctionKey="5" IntegrationMethod="LoadControl"
          Method="StandardNewtonRaphson" TargetDisplacement="3" Dr2="0.04"
          MaxU="9" />
        </HiStrA>'''
    )
    model = load_model(path)
    function = model.collections.load_functions[5]
    assert [(item.pseudo_time, item.multiplier) for item in function.items] == [(0.0, 0.0), (1.0, -1.0)]
    analysis = model.collections.analyses[7]
    assert analysis.load_function is function
    assert analysis.target_displacement == 3.0
    assert analysis.dr2 == 0.04
    assert analysis.max_u == 9.0


def test_load_control_force_discretization_handles_unloading():
    lf = LoadFunction(
        key=1,
        type_discr=True,
        discr_val=0.25,
        items=[
            LoadFunctionItem(key=1, load_function_key=1, pseudo_time=0, multiplier=0),
            LoadFunctionItem(key=2, load_function_key=1, pseudo_time=1, multiplier=1),
            LoadFunctionItem(key=3, load_function_key=1, pseudo_time=2, multiplier=0),
        ],
    )
    analysis = SimpleNamespace(mult=1.0, load_function=lf)
    integrator = LoadControl()
    integrator.state.analysis = analysis
    integrator._get_initial_time_and_force(analysis)
    integrator._t = 1.0
    integrator.mult = 1.0
    dt, df = integrator._get_increment()
    assert dt > 0.0
    assert df < 0.0


def test_arc_length_linear_predictor_and_commit():
    from histra.solver.arc_length import ArcLength

    lf = LoadFunction(
        key=1,
        items=[
            LoadFunctionItem(key=1, load_function_key=1, pseudo_time=0, multiplier=0),
            LoadFunctionItem(key=2, load_function_key=1, pseudo_time=1, multiplier=1),
        ],
    )
    analysis = SimpleNamespace(
        key=None,
        load_function=lf,
        pdelta_effect="None",
        target_displacement=0.1,
        dr2=0.01,
        arc_length_procedure="OnlyControlPoint",
        master_point=0,
        is_max_arc_length_ray=False,
        update_dr2=False,
    )
    model = empty_model(1)
    ls = LinearSystem(1)
    ls.k = sp.csc_matrix([[1.0]])
    p = Program(gdl=1, ls=ls, u=np.zeros(1), v=np.zeros(1))
    ModelManager._ptarget = np.array([1.0])
    ModelManager._fext = np.array([0.0])

    integrator = ArcLength()
    integrator.state.analysis = analysis
    integrator.state.combination = 1
    integrator.u = p.u
    integrator.u_committed = p.u.copy()
    integrator.domain_changed(p, model, 1)
    integrator.new_step(p, model, ls, analysis, 1, 1, 0)

    np.testing.assert_allclose(p.u, [0.1])
    np.testing.assert_allclose(ModelManager._fext, [0.1])
    assert integrator.mult == 0.1
    changed = [False]
    assert integrator.commit(model, analysis, 0.1, 0, changed) is True
