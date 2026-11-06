"""Adapter lifecycle tests run on CPU; native differentials require CUDA."""
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from histra.types import cudss
from histra.types.linear_system import LinearSolveError, LinearSystem


@pytest.fixture
def simulated_cuda(monkeypatch):
    instances = []

    class DirectSolver:
        def __init__(self, a, b, *, execution, options):
            assert execution == "cuda"
            assert options["blocking"] is True
            self.a, self.b = a.copy(), b.copy()
            self.plans = self.factors = self.frees = 0
            instances.append(self)

        def plan(self):
            self.plans += 1

        def factorize(self):
            self.factors += 1
            self.factor = splu(self.a.tocsc())
            return SimpleNamespace(info=0)

        def reset_operands(self, *, a=None, b=None):
            if a is not None:
                self.a = a.copy()
            if b is not None:
                self.b = b.copy()

        def solve(self):
            return self.factor.solve(self.b)

        def free(self):
            self.frees += 1

    monkeypatch.setattr(cudss, "_direct_solver_type", lambda: DirectSolver)
    monkeypatch.setattr(cudss, "_configure_solver", lambda solver, mode: None)
    return instances


def test_cuda_factor_reuse_numeric_rebuild_and_topology_change(simulated_cuda):
    with LinearSystem(2, backend="cudss") as system:
        system.k = sp.csc_matrix([[4., 1.], [2., -3.]])
        system.b[:] = [6., -4.]
        system.solve()
        np.testing.assert_allclose(system.x, [1., 2.], atol=1e-14)
        system.solve(rhs=2 * system.b)
        np.testing.assert_allclose(system.x, [2., 4.], atol=1e-14)
        assert system.factorization_count == 1
        system.k = 2 * system.k
        system.solve()
        np.testing.assert_allclose(system.x, [.5, 1.], atol=1e-14)
        assert len(simulated_cuda) == 1
        assert simulated_cuda[0].plans == 1
        assert simulated_cuda[0].factors == 2
        system.set_zero()
        np.testing.assert_array_equal(system.b, [6., -4.])
        system.k = sp.eye(2, format="csc")
        system.solve()
        np.testing.assert_array_equal(system.x, system.b)
        assert len(simulated_cuda) == 2
        assert simulated_cuda[0].frees == 1
    assert simulated_cuda[1].frees == 1


def test_cuda_missing_dependency_fails_without_cpu_fallback(monkeypatch):
    def unavailable():
        raise cudss.CudssUnavailable("install histra-python[gpu-cu12]")

    monkeypatch.setattr(cudss, "_direct_solver_type", unavailable)
    with LinearSystem(1, backend="cudss") as system:
        system.k = sp.eye(1, format="csc")
        with pytest.raises(LinearSolveError, match="gpu-cu12"):
            system.solve(rhs=np.ones(1))
        assert system._factorization is None
        assert system.solve_count == 0
    from histra.solver.backend_coverage import _resolve_linear_solver_backend

    requested, actual, available, error = _resolve_linear_solver_backend("cudss")
    assert (requested, actual, available) == ("cudss", "cudss", False)
    assert "gpu-cu12" in error


def test_cuda_failure_frees_resources_and_can_restart(simulated_cuda):
    with LinearSystem(2, backend="cudss") as system:
        system.k = sp.csc_matrix((2, 2))
        with pytest.raises(LinearSolveError):
            system.solve(rhs=np.ones(2))
        assert simulated_cuda[0].frees == 1
        system.k = sp.eye(2, format="csc")
        system.solve(rhs=np.ones(2))
        np.testing.assert_array_equal(system.x, np.ones(2))


def test_cuda_bad_numeric_status_is_not_accepted(simulated_cuda, monkeypatch):
    solver_type = cudss._direct_solver_type()
    original = solver_type.factorize

    def factorize(self):
        original(self)
        return SimpleNamespace(info=2)

    monkeypatch.setattr(solver_type, "factorize", factorize)
    with pytest.raises(cudss.CudssError, match="info=2"):
        cudss.CudssFactorization(sp.eye(2))
    assert simulated_cuda[0].frees == 1


def test_cuda_nonfinite_result_rejected(simulated_cuda, monkeypatch):
    monkeypatch.setattr(cudss._direct_solver_type(), "solve", lambda self: np.array([np.nan]))
    with LinearSystem(1, backend="cudss") as system:
        system.k = sp.eye(1, format="csc")
        with pytest.raises(LinearSolveError, match="non-finite"):
            system.solve(rhs=np.ones(1))


def test_cuda_explicit_selection_does_not_change_auto(monkeypatch, simulated_cuda):
    monkeypatch.setenv("HISTRA_LINEAR_SOLVER", "cudss")
    assert LinearSystem(1).backend == "cudss"
    assert LinearSystem(1, backend="auto").backend != "cudss"
    assert not simulated_cuda


def test_simple_cpu_gpu_backend_aliases(monkeypatch, simulated_cuda):
    monkeypatch.setenv("HISTRA_LINEAR_SOLVER", "gpu")
    assert LinearSystem(1).backend == "cudss"
    assert LinearSystem(1, backend="gpu").backend == "cudss"
    assert LinearSystem(1, backend="cpu").backend in {"umfpack", "superlu"}
    assert not simulated_cuda


def test_invalid_cuda_mode_fails_without_constructing_solver(monkeypatch, simulated_cuda):
    monkeypatch.setenv("HISTRA_CUDSS_MODE", "unsupported")
    with pytest.raises(ValueError, match="HISTRA_CUDSS_MODE"):
        cudss.CudssFactorization(sp.eye(1))
    assert not simulated_cuda


def test_refinement_profile_sets_three_corrections_without_determinism():
    solver = SimpleNamespace(solution_config=SimpleNamespace(ir_num_steps=0))
    cudss._configure_solver(solver, "refined")
    assert solver.solution_config.ir_num_steps == 3


@pytest.mark.gpu
@pytest.mark.parametrize("mode", ["deterministic", "refined"])
@pytest.mark.parametrize("values", [
    [[4., 1.], [1., 3.]], [[2., 1.], [1., -2.]], [[4., 1.], [2., -3.]],
])
def test_native_cuda_cpu_differential(values, mode, monkeypatch):
    monkeypatch.setenv("HISTRA_CUDSS_MODE", mode)
    available, error = cudss.probe_cudss()
    if not available:
        pytest.skip(error)
    matrix = sp.csc_matrix(values)
    rhs = np.array([1., 2.])
    with LinearSystem(2, backend="cudss") as gpu, LinearSystem(2, backend="superlu") as cpu:
        for scale in (1., 2.):
            cpu.k, gpu.k = scale * matrix, scale * matrix
            for load in (rhs, -rhs):
                cpu.solve(rhs=load)
                gpu.solve(rhs=load)
                np.testing.assert_allclose(gpu.x, cpu.x, atol=1e-9, rtol=1e-9)
                np.testing.assert_allclose(gpu.k @ gpu.x, load, atol=1e-9, rtol=1e-9)


@pytest.mark.gpu
def test_native_cuda_deterministic_repeats_match_bits(monkeypatch):
    monkeypatch.setenv("HISTRA_CUDSS_MODE", "deterministic")
    available, error = cudss.probe_cudss()
    if not available:
        pytest.skip(error)
    n = 128
    matrix = sp.diags([-np.ones(n-1), np.full(n, 4.), np.ones(n-1)], [-1, 0, 1], format="csc")
    rhs = np.random.default_rng(42).standard_normal(n)
    solutions = []
    for _ in range(3):
        factor = cudss.CudssFactorization(matrix)
        try:
            solutions.append(factor.solve(rhs))
        finally:
            factor.close()
    for result in solutions[1:]:
        np.testing.assert_array_equal(result.view(np.uint64), solutions[0].view(np.uint64))
