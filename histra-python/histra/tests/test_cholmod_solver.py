"""Tests for native CHOLMOD sparse linear solver backend."""
from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from histra.types.cholmod import (
    CholmodError,
    CholmodFactorization,
    CholmodUnavailable,
    find_cholmod_library,
    is_cholmod_available,
)
from histra.types.linear_system import LinearSolveError, LinearSystem


@pytest.fixture(autouse=True)
def require_cholmod():
    if not is_cholmod_available():
        pytest.skip("SuiteSparse CHOLMOD library is not available in this environment")


def test_cholmod_library_discovery():
    path = find_cholmod_library()
    assert path is not None
    assert "cholmod" in path.lower()
    assert is_cholmod_available() is True


def test_cholmod_solve_spd_system():
    # 5x5 symmetric positive definite matrix
    a = np.array([
        [10.0, 1.0, 2.0, 0.0, 0.0],
        [1.0, 12.0, 0.0, 3.0, 1.0],
        [2.0, 0.0, 15.0, 1.0, 2.0],
        [0.0, 3.0, 1.0, 11.0, 0.0],
        [0.0, 1.0, 2.0, 0.0, 9.0],
    ], dtype=np.float64)
    k = sp.csc_matrix(a)
    b = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)

    with CholmodFactorization(k) as chol:
        x = chol.solve(b)
        x_expected = np.linalg.solve(a, b)
        np.testing.assert_allclose(x, x_expected, rtol=1e-13, atol=1e-13)

        # In-place solve
        out = np.empty_like(b)
        res = chol.solve(b, out=out)
        assert res is out
        np.testing.assert_allclose(out, x_expected, rtol=1e-13, atol=1e-13)


def test_cholmod_numeric_refactorization():
    n = 6
    rng = np.random.default_rng(42)
    # Generate random SPD matrix
    m = rng.standard_normal((n, n))
    a1 = m @ m.T + np.eye(n) * 2.0
    k1 = sp.csc_matrix(a1)
    b = rng.standard_normal(n)

    chol = CholmodFactorization(k1)
    x1 = chol.solve(b)
    np.testing.assert_allclose(x1, np.linalg.solve(a1, b), rtol=1e-13, atol=1e-13)

    # Modify values keeping the exact same sparsity pattern
    a2 = a1 * 1.5 + np.eye(n) * 0.5
    k2 = sp.csc_matrix(a2)
    refactored = chol.refactor_numeric(k2)
    assert refactored is True

    x2 = chol.solve(b)
    np.testing.assert_allclose(x2, np.linalg.solve(a2, b), rtol=1e-13, atol=1e-13)
    chol.close()


def test_cholmod_not_positive_definite():
    # Matrix with negative eigenvalue
    a = np.array([
        [-5.0, 1.0],
        [1.0, 2.0],
    ], dtype=np.float64)
    k = sp.csc_matrix(a)

    with pytest.raises(CholmodError, match="not positive definite"):
        CholmodFactorization(k)


def test_cholmod_singular_matrix():
    # Matrix with zero pivot
    a = np.array([
        [0.0, 0.0],
        [0.0, 2.0],
    ], dtype=np.float64)
    k = sp.csc_matrix(a)

    with pytest.raises(CholmodError, match="singular or not positive definite"):
        CholmodFactorization(k)


def test_cholmod_invalid_dimensions():
    # Non-square matrix
    k = sp.csc_matrix(np.ones((3, 4)))
    with pytest.raises(ValueError, match="square matrix"):
        CholmodFactorization(k)


def test_linear_system_with_cholmod_backend():
    n = 8
    ls = LinearSystem(n, backend="cholmod")
    assert ls.backend == "cholmod"
    assert ls.requested_backend == "cholmod"

    # Assemble simple 1D Laplacian
    main_diag = np.full(n, 20.0)
    off_diag = np.full(n - 1, -5.0)
    k = sp.diags([off_diag, main_diag, off_diag], [-1, 0, 1], format="csc")
    ls.k = k
    ls.b[:] = np.arange(1, n + 1, dtype=np.float64)

    status = ls.solve()
    assert status == 0
    assert ls.factorization_count == 1
    assert ls.solve_count == 1

    x_expected = spsolve(k, ls.b)
    np.testing.assert_allclose(ls.x, x_expected, rtol=1e-13, atol=1e-13)

    # Subsequent solve with different rhs reuses factorization
    ls.b[:] *= 2.0
    status = ls.solve()
    assert status == 0
    assert ls.factorization_count == 1
    assert ls.solve_count == 2
    np.testing.assert_allclose(ls.x, x_expected * 2.0, rtol=1e-13, atol=1e-13)

    # Modified stiffness triggers refactorization
    ls.k = k * 3.0
    status = ls.solve()
    assert status == 0
    assert ls.factorization_count == 2
    assert ls.solve_count == 3
    np.testing.assert_allclose(ls.x, (x_expected * 2.0) / 3.0, rtol=1e-13, atol=1e-13)


def test_linear_system_cholmod_singular_raises_linearsolveerror():
    ls = LinearSystem(4, backend="cholmod")
    ls.k = sp.csc_matrix((4, 4), dtype=np.float64)  # singular
    ls.b[:] = 1.0

    with pytest.raises(LinearSolveError, match="Unable to solve stiffness system with cholmod"):
        ls.solve()


def test_cholmod_umfpack_parity_random_spd():
    n = 50
    rng = np.random.default_rng(12345)
    # Banded symmetric positive definite matrix
    diagonals = [
        np.full(n, 40.0),
        rng.uniform(-2.0, 2.0, n - 1),
        rng.uniform(-1.0, 1.0, n - 2),
    ]
    k = sp.diags([diagonals[2], diagonals[1], diagonals[0], diagonals[1], diagonals[2]],
                 [-2, -1, 0, 1, 2], format="csc")
    b = rng.standard_normal(n)

    ls_chol = LinearSystem(n, backend="cholmod")
    ls_chol.k = k
    ls_chol.solve(rhs=b)

    ls_umf = LinearSystem(n, backend="umfpack")
    ls_umf.k = k
    ls_umf.solve(rhs=b)

    np.testing.assert_allclose(ls_chol.x, ls_umf.x, rtol=1e-12, atol=1e-12)
