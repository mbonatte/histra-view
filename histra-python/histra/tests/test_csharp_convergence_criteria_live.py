"""Analytical exact-output regressions for production convergence criteria.

These simple Euclidean-norm/dot-product expectations are not independent live
C# captures. Original routine/control fixtures provide separate native checks;
storing an analytical result as integer bits does not broaden that coverage.
"""
from types import SimpleNamespace
import numpy as np
import pytest

from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem


@pytest.fixture
def mock_solver_environment():
    """Minimal mock model and program for isolated convergence testing."""
    mock_model = SimpleNamespace(collections=SimpleNamespace(quads={}))
    mock_program = SimpleNamespace(max_u=0.0)
    return mock_program, mock_model


@pytest.mark.parametrize(
    ("residual", "tol", "expected_converged", "expected_error_bits"),
    [
        ([3.0, 4.0], 10.0, True, 4617315517961601024),      # Norm is 5.0 <= 10.0
        ([3.0, 4.0], 1.0, False, 4617315517961601024),      # Norm is 5.0 > 1.0
        ([1.0, -2.0, 2.0], 5.0, True, 4613937818241073152), # Norm is 3.0 <= 5.0
        ([0.0, 0.0, 0.0], 1e-6, True, 0),                   # Zero residual
        ([12.0, 5.0], 12.5, False, 4623507967449235456),    # Norm is 13.0 > 12.5
    ],
)
def test_csharp_convergence_unbalance_live(
    mock_solver_environment,
    residual: list[float],
    tol: float,
    expected_converged: bool,
    expected_error_bits: int,
):
    """Check simple ForceMoment cases against analytical Euclidean norms."""
    mock_program, mock_model = mock_solver_environment

    ls = LinearSystem(len(residual))
    ls.b = np.asarray(residual, dtype=np.float64)

    ct = ConvergenceTest(tolerance=tol, criterion="ForceMoment")
    ct.start(ls)
    py_code = ct.test(mock_program, mock_model, ls)

    assert (py_code >= 0) == expected_converged
    py_bits = int(np.asarray([ct._error], dtype=np.float64).view(np.int64)[0])
    assert py_bits == expected_error_bits, f"Unbalance error_bits mismatch: py={py_bits}, cs={expected_error_bits}"


@pytest.mark.parametrize(
    ("displacement", "tol", "expected_converged", "expected_error_bits"),
    [
        ([0.03, 0.04], 0.05, True, 4587366580439587226),            # Norm is 0.05 <= 0.05
        ([0.03, 0.04], 0.01, False, 4587366580439587226),           # Norm is 0.05 > 0.01
        ([0.001, 0.002, -0.002], 0.01, True, 4569063951553953529),  # Norm is 0.003 <= 0.01
        ([0.0, 0.0], 1e-8, True, 0),                                # Zero displacement
    ],
)
def test_csharp_convergence_displacement_live(
    mock_solver_environment,
    displacement: list[float],
    tol: float,
    expected_converged: bool,
    expected_error_bits: int,
):
    """Check simple DispRotation cases against analytical Euclidean norms."""
    mock_program, mock_model = mock_solver_environment

    ls = LinearSystem(len(displacement))
    ls.x = np.asarray(displacement, dtype=np.float64)

    ct = ConvergenceTest(tolerance=tol, criterion="DispRotation")
    ct.start(ls)
    py_code = ct.test(mock_program, mock_model, ls)

    assert (py_code >= 0) == expected_converged
    py_bits = int(np.asarray([ct._error], dtype=np.float64).view(np.int64)[0])
    assert py_bits == expected_error_bits, f"Displacement error_bits mismatch: py={py_bits}, cs={expected_error_bits}"


@pytest.mark.parametrize(
    ("residual", "displacement", "tol", "expected_converged", "expected_error_bits"),
    [
        ([2.0, 3.0], [0.1, 0.2], 1.0, True, 4600877379321698714),    # Work = 0.5 * (0.2 + 0.6) = 0.4 <= 1.0
        ([2.0, 3.0], [0.1, 0.2], 0.1, False, 4600877379321698714),   # Work = 0.4 > 0.1
        ([10.0, -5.0], [0.02, 0.04], 0.001, True, 0),                 # Work = 0.5 * abs(0.2 - 0.2) = 0.0 <= 0.001
        ([4.0, 6.0], [1.0, 2.0], 5.0, False, 4620693217682128896),   # Work = 0.5 * (4 + 12) = 8.0 > 5.0
    ],
)
def test_csharp_convergence_energy_live(
    mock_solver_environment,
    residual: list[float],
    displacement: list[float],
    tol: float,
    expected_converged: bool,
    expected_error_bits: int,
):
    """Check simple Work cases against analytical half-dot-product values."""
    mock_program, mock_model = mock_solver_environment

    ls = LinearSystem(len(residual))
    ls.b = np.asarray(residual, dtype=np.float64)
    ls.x = np.asarray(displacement, dtype=np.float64)

    ct = ConvergenceTest(tolerance=tol, criterion="Work")
    ct.start(ls)
    py_code = ct.test(mock_program, mock_model, ls)

    assert (py_code >= 0) == expected_converged
    py_bits = int(np.asarray([ct._error], dtype=np.float64).view(np.int64)[0])
    assert py_bits == expected_error_bits, f"Energy error_bits mismatch: py={py_bits}, cs={expected_error_bits}"
