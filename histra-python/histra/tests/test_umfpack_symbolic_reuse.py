from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from histra.types.linear_system import LinearSystem
from histra.types.umfpack import UmfpackFactorization, find_umfpack_library


def test_umfpack_refactor_numeric() -> None:
    if find_umfpack_library() is None:
        return

    # Two matrices with identical sparsity pattern
    indptr = np.array([0, 2, 3], dtype=np.int32)
    indices = np.array([0, 1, 1], dtype=np.int32)
    data1 = np.array([4.0, 1.0, 3.0], dtype=np.float64)
    data2 = np.array([8.0, 2.0, 6.0], dtype=np.float64)

    k1 = sp.csc_matrix((data1, indices, indptr), shape=(2, 2))
    k2 = sp.csc_matrix((data2, indices, indptr), shape=(2, 2))
    b = np.array([1.0, 2.0], dtype=np.float64)

    fac = UmfpackFactorization(k1)
    try:
        assert fac.can_refactor_numeric(k2)

        # Different pattern matrix
        k_diff = sp.csc_matrix(np.eye(2))
        assert not fac.can_refactor_numeric(k_diff)

        sol1 = fac.solve(b).copy()
        expected1 = sp.linalg.spsolve(k1, b)
        assert np.allclose(sol1, expected1)

        refactored = fac.refactor_numeric(k2)
        assert refactored

        sol2 = fac.solve(b).copy()
        expected2 = sp.linalg.spsolve(k2, b)
        assert np.allclose(sol2, expected2)
    finally:
        fac.close()


def test_linear_system_symbolic_reuse() -> None:
    if find_umfpack_library() is None:
        return

    ls = LinearSystem(2, backend="umfpack")

    indptr = np.array([0, 2, 3], dtype=np.int32)
    indices = np.array([0, 1, 1], dtype=np.int32)
    data1 = np.array([4.0, 1.0, 3.0], dtype=np.float64)
    data2 = np.array([8.0, 2.0, 6.0], dtype=np.float64)

    ls.k = sp.csc_matrix((data1, indices, indptr), shape=(2, 2))
    ls.b[:] = [1.0, 2.0]
    ls.solve()
    assert np.allclose(ls.x, sp.linalg.spsolve(ls.k, ls.b))
    assert ls.factorization_count == 1

    orig_fac = ls._factorization
    assert isinstance(orig_fac, UmfpackFactorization)
    orig_sym_ptr = orig_fac._symbolic.value

    # Update k with new numerical values
    ls.k = sp.csc_matrix((data2, indices, indptr), shape=(2, 2))
    ls.b[:] = [1.0, 2.0]
    ls.solve()
    assert np.allclose(ls.x, sp.linalg.spsolve(ls.k, ls.b))
    assert ls.factorization_count == 2
    # Factorization object and symbolic pointer must be preserved!
    assert ls._factorization is orig_fac
    assert orig_fac._symbolic.value == orig_sym_ptr

    # set_zero followed by new matrix (simulates assemble_k with set_zero=True)
    ls.set_zero()
    ls.k = sp.csc_matrix((data1, indices, indptr), shape=(2, 2))
    ls.b[:] = [1.0, 2.0]
    ls.solve()
    assert np.allclose(ls.x, sp.linalg.spsolve(ls.k, ls.b))
    assert ls.factorization_count == 3
    assert ls._factorization is orig_fac
    assert orig_fac._symbolic.value == orig_sym_ptr


def test_model_manager_assemble_k_symbolic_reuse() -> None:
    if find_umfpack_library() is None:
        return
    from pathlib import Path
    from histra.io.hr_loader import load_model
    from histra.solver.model_manager import ModelManager

    model_path = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"
    if not model_path.exists():
        return
    model = load_model(model_path)
    ModelManager.prepare_model(model, force=True)

    ls = LinearSystem(model.gdl, backend="umfpack")
    ModelManager.compute_ktang(model, ls, 0.0)
    ls.b[:] = np.ones(model.gdl)
    ls.solve()

    orig_fac = ls._factorization
    assert isinstance(orig_fac, UmfpackFactorization)
    orig_sym_ptr = orig_fac._symbolic.value
    assert ls.factorization_count == 1

    # Re-assemble tangent stiffness matrix with alfa=1.0 (tangent refresh)
    ModelManager.compute_ktang(model, ls, 1.0)
    ls.b[:] = np.ones(model.gdl)
    ls.solve()

    assert ls.factorization_count == 2
    assert ls._factorization is orig_fac
    assert orig_fac._symbolic.value == orig_sym_ptr


def test_failed_numeric_refactor_is_not_repeated_with_fresh_symbolic(monkeypatch):
    import pytest
    import histra.types.linear_system as module
    from histra.types.linear_system import LinearSolveError

    if find_umfpack_library() is None:
        pytest.skip("Native UMFPACK is not available")

    class CountingFactorization(UmfpackFactorization):
        constructions = 0

        def __init__(self, *args, **kwargs):
            type(self).constructions += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(module, "UmfpackFactorization", CountingFactorization)
    system = LinearSystem(2, backend="umfpack", precision="accurate", ordering="amd")
    good = sp.csc_matrix([[2., 1.], [1., 2.]])
    system.k = good.copy()
    system.b[:] = [3., 5.]
    system.solve()
    expected = system.x.copy()
    # No zero columns: this exercises the native numerical singularity path.
    system.k = sp.csc_matrix([[1., 1.], [1., 1.]])
    with pytest.raises(LinearSolveError):
        system.solve()
    assert CountingFactorization.constructions == 1
    assert system._factorization is None
    # A changed matrix can still recover after the failed attempt.
    system.k = good.copy()
    system.solve()
    np.testing.assert_array_equal(system.x, expected)
    assert CountingFactorization.constructions == 2
