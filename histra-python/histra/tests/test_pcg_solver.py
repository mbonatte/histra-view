"""Tests for Preconditioned Conjugate Gradient (PCG) iterative linear solver."""
from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from histra.types.linear_system import LinearSolveError, LinearSystem
from histra.types.pcg import (
    PCGConvergenceError,
    PCGFactorization,
    PCGResult,
    pcg_solve,
)


def _make_spd_laplacian(n: int) -> sp.csc_matrix:
    diag = np.full(n, 20.0, dtype=np.float64)
    off = np.full(n - 1, -5.0, dtype=np.float64)
    return sp.diags([off, diag, off], [-1, 0, 1], shape=(n, n), format="csc", dtype=np.float64)


def test_pcg_solve_jacobi_and_ssor():
    n = 30
    k = _make_spd_laplacian(n)
    b = np.arange(1, n + 1, dtype=np.float64)
    x_direct = spsolve(k, b)

    # Jacobi preconditioner
    res_jac = pcg_solve(k, b, tol=1e-7, maxiter=200, preconditioner="jacobi")
    assert res_jac.converged is True
    assert res_jac.residual_norm <= 1e-7
    np.testing.assert_allclose(res_jac.x, x_direct, rtol=1e-5, atol=1e-5)

    # SSOR preconditioner
    res_ssor = pcg_solve(k, b, tol=1e-7, maxiter=200, preconditioner="ssor", omega=1.0)
    assert res_ssor.converged is True
    assert res_ssor.residual_norm <= 1e-7
    np.testing.assert_allclose(res_ssor.x, x_direct, rtol=1e-5, atol=1e-5)

    # Identity / None
    res_none = pcg_solve(k, b, tol=1e-7, maxiter=200, preconditioner="none")
    assert res_none.converged is True
    np.testing.assert_allclose(res_none.x, x_direct, rtol=1e-5, atol=1e-5)

    # AMG preconditioner (via PyAMG)
    res_amg = pcg_solve(k, b, tol=1e-7, maxiter=200, preconditioner="amg")
    assert res_amg.converged is True
    assert res_amg.residual_norm <= 1e-7
    np.testing.assert_allclose(res_amg.x, x_direct, rtol=1e-5, atol=1e-5)



def test_pcg_zero_rhs():
    n = 10
    k = _make_spd_laplacian(n)
    b = np.zeros(n, dtype=np.float64)
    res = pcg_solve(k, b)
    assert res.converged is True
    assert res.iterations == 0
    assert np.all(res.x == 0.0)


def test_pcg_factorization_wrapper():
    n = 25
    k = _make_spd_laplacian(n)
    b = np.ones(n, dtype=np.float64)
    x_expected = spsolve(k, b)

    with PCGFactorization(k, tol=1e-7, maxiter=200) as factor:
        x = factor.solve(b)
        np.testing.assert_allclose(x, x_expected, rtol=1e-5, atol=1e-5)

        # In-place solve
        out = np.empty_like(b)
        factor.solve(b, out=out)
        np.testing.assert_allclose(out, x_expected, rtol=1e-5, atol=1e-5)

        # Refactor numeric with updated values
        k2 = k * 2.0
        assert factor.refactor_numeric(k2) is True
        x2 = factor.solve(b)
        np.testing.assert_allclose(x2, x_expected / 2.0, rtol=1e-5, atol=1e-5)


def test_linear_system_pcg_backend():
    n = 20
    ls = LinearSystem(n, backend="pcg")
    assert ls.backend == "pcg"
    assert ls.requested_backend == "pcg"

    k = _make_spd_laplacian(n)
    ls.k = k
    ls.b[:] = np.arange(1, n + 1, dtype=np.float64)

    status = ls.solve()
    assert status == 0
    assert ls.solve_count == 1
    assert ls.factorization_count == 1

    x_expected = spsolve(k, ls.b)
    np.testing.assert_allclose(ls.x, x_expected, rtol=1e-5, atol=1e-5)

    # Re-solve with updated b
    ls.b[:] *= 2.0
    status = ls.solve()
    assert status == 0
    assert ls.solve_count == 2
    assert ls.factorization_count == 1
    np.testing.assert_allclose(ls.x, x_expected * 2.0, rtol=1e-5, atol=1e-5)


def test_pcg_fallback_to_direct_solver():
    # Construct an ill-conditioned system where maxiter=1 is insufficient
    n = 30
    k = _make_spd_laplacian(n)
    b = np.ones(n, dtype=np.float64)

    # Setting maxiter=1 forces PCG not to converge, which triggers direct solver fallback
    factor = PCGFactorization(k, tol=1e-12, maxiter=1)
    x = factor.solve(b)
    assert factor.fallback_used is True

    x_expected = spsolve(k, b)
    np.testing.assert_allclose(x, x_expected, rtol=1e-10, atol=1e-10)
    factor.close()
