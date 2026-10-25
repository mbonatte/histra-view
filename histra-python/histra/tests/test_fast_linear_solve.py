from __future__ import annotations

import os
from pathlib import Path
from unittest import mock
import numpy as np
import pytest
import scipy.sparse as sp

from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.types.linear_system import LinearSystem
from histra.types.umfpack import UmfpackFactorization, find_umfpack_library


def test_linear_system_precision_strict_vs_fast():
    n = 200
    diag = 4.0 * np.ones(n)
    off = -1.0 * np.ones(n - 1)
    k = sp.diags([off, diag, off], [-1, 0, 1], shape=(n, n), format="csc")
    b = np.sin(np.linspace(0.1, 3.0, n))

    ls_strict = LinearSystem(n, precision="strict")
    assert ls_strict.precision == "strict"
    assert ls_strict.irstep == 2
    ls_strict.k = k.copy()
    ls_strict.b[:] = b
    ls_strict.solve()

    ls_fast = LinearSystem(n, precision="fast")
    assert ls_fast.precision == "fast"
    assert ls_fast.irstep == 0
    ls_fast.k = k.copy()
    ls_fast.b[:] = b
    ls_fast.solve()

    max_diff = np.max(np.abs(ls_strict.x - ls_fast.x))
    assert max_diff < 1e-11


def test_linear_system_irstep_override():
    ls_default = LinearSystem(50)
    assert ls_default.precision == "fast"
    assert ls_default.irstep == 0

    ls = LinearSystem(50, irstep=1)
    assert ls.irstep == 1

    with mock.patch.dict(os.environ, {"HISTRA_LINEAR_SOLVER_PRECISION": "fast"}):
        ls_env = LinearSystem(50)
        assert ls_env.precision == "fast"
        assert ls_env.irstep == 0

    with mock.patch.dict(os.environ, {"HISTRA_UMFPACK_IRSTEP": "5"}):
        ls_env_step = LinearSystem(50, precision="strict")
        assert ls_env_step.irstep == 5


def test_umfpack_factorization_irstep():
    if find_umfpack_library() is None:
        return

    n = 50
    k = sp.eye(n, format="csc")
    b = np.ones(n)

    factor_strict = UmfpackFactorization(k, irstep=2)
    assert factor_strict.irstep == 2
    x_strict = factor_strict.solve(b)
    np.testing.assert_allclose(x_strict, b)

    factor_fast = UmfpackFactorization(k, irstep=0)
    assert factor_fast.irstep == 0
    x_fast = factor_fast.solve(b)
    np.testing.assert_allclose(x_fast, b)


def test_benchmark_1_fast_solve_session():
    benchmark_dir = Path(__file__).parents[2] / "my_model" / "benchmark_1"
    hrx_file = benchmark_dir / "benchmark_virgin.hrx"
    if not hrx_file.exists():
        pytest.skip("Benchmark 1 not found.")

    model = load_model(hrx_file)
    ModelManager.prepare_model(model)
    session = AnalysisSession(
        model,
        linear_solver_precision="fast",
        adaptive_tangent_refresh=True,
        strategy_policy="off",
    )
    assert session.linear_solver_precision == "fast"
    assert session.adaptive_tangent_refresh is True

    exec_vert = session.run("Vert")
    assert exec_vert.completed
    assert len(exec_vert.committed_steps) > 0


def test_cholmod_indefinite_fallback_to_umfpack():
    """Verify that LinearSystem with backend='cholmod' falls back on indefinite matrix."""
    from histra.types.cholmod import find_cholmod_library
    if find_cholmod_library() is None:
        pytest.skip("CHOLMOD not available")

    # Symmetric indefinite matrix: diag = [2, -1]
    k = sp.csc_matrix([[2.0, 0.0], [0.0, -1.0]])
    b = np.array([4.0, 3.0])

    ls = LinearSystem(2, backend="cholmod")
    assert ls.backend == "cholmod"
    ls.k = k.copy()
    ls.b[:] = b
    code = ls.solve()
    assert code == 0
    np.testing.assert_allclose(ls.x, [2.0, -3.0])
    assert ls._factor_backend == "umfpack"

