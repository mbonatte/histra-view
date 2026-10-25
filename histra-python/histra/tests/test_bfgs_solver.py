from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from histra import load_model
from histra.solver.bfgs import BFGSSolnAlgo
from histra.solver.solution_algorithm import EquiSolnAlgo, _new_line_search
from histra.solver.solve import solve_static_nonlinear
from histra.types.convergence_test import ConvergenceTest


def test_bfgs_instantiation_and_properties() -> None:
    algo = BFGSSolnAlgo(max_history=8)
    assert algo.max_history == 8
    assert len(algo._history) == 0
    algo._history.append((np.ones(3), np.ones(3), 1.0))
    algo.clear_history()
    assert len(algo._history) == 0


def test_bfgs_factory_dispatch() -> None:
    class FakeAnalysis:
        method = "BFGS"
        convergence_tolerance = 1e-4
        max_iterations = 25
        max_u = 1e10
        adaptive_convergence_criteria = "ForceMoment"
        integration_method = "LoadControl"
        quasi_newton_history_size = 12

    an = FakeAnalysis()
    algo = EquiSolnAlgo.new_equi_soln_algo(an, 1)
    assert isinstance(algo, BFGSSolnAlgo)
    assert algo.max_history == 12

    for name in ("QuasiNewton", "StandardBFGS", "BFGSLineSearch"):
        an.method = name
        algo_name = EquiSolnAlgo.new_equi_soln_algo(an, 1)
        assert isinstance(algo_name, BFGSSolnAlgo)


def test_matthies_strang_two_loop_matches_explicit_bfgs_inverse() -> None:
    """Verify Matthies-Strang two-loop recursion matches the explicit BFGS formula."""
    rng = np.random.default_rng(42)
    n = 6
    s = rng.standard_normal(n)
    y = rng.standard_normal(n)
    # Ensure positive curvature
    if np.dot(s, y) <= 0:
        y += s * (abs(float(np.dot(s, y))) + 1.0)
    rho = 1.0 / float(np.dot(s, y))

    q = rng.standard_normal(n)
    I = np.eye(n)
    # Explicit inverse BFGS update with H0 = I:
    # H1 = (I - rho * s y^T) (I - rho * y s^T) + rho * s s^T
    term1 = I - rho * np.outer(s, y)
    term2 = I - rho * np.outer(y, s)
    H1 = term1 @ term2 + rho * np.outer(s, s)
    expected_d = H1 @ q

    # Matthies-Strang two-loop recursion:
    alpha = rho * float(np.dot(s, q))
    q_mod = q - alpha * y
    r = q_mod  # H0 @ q_mod with H0 = I
    beta = rho * float(np.dot(y, r))
    actual_d = r + s * (alpha - beta)

    np.testing.assert_allclose(actual_d, expected_d, rtol=1e-12, atol=1e-12)


def test_bfgs_nonlinear_solve_step_convergence() -> None:
    benchmarks = [
        Path(__file__).resolve().parents[1] / "model-benchmark" / "model.hrx",
        Path("my_model/benchmark_1/benchmark_virgin.hrx"),
        Path(__file__).resolve().parents[1] / "model-live" / "model.hrx",
    ]
    model_path = next((p for p in benchmarks if p.exists()), None)
    if model_path is None:
        pytest.skip("No benchmark model found for BFGS step test")

    model = load_model(model_path)
    an = model.collections.analyses[1]
    an.method = "BFGS"
    an.adaptive_convergence_criteria = "ForceMoment"

    code, steps = solve_static_nonlinear(
        model, 1, max_committed_steps=2, auto_prepare=True
    )
    assert code == 0
    assert len(steps) >= 1
    for s in steps:
        assert s["status"] == "OK"
        assert s["equilibrium_ok"] is True
        assert s["equilibrium_force_relative_error"] < 1e-5
