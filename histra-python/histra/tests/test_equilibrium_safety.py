"""Regression tests for nonlinear convergence and equilibrium safety."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pytest

from histra.postprocessing import ReactionResult
from histra.solver.equilibrium import (
    applied_force_resultant,
    audit_static_equilibrium,
    normalize_equilibrium_policy,
)
from histra.solver.backend_api import run_python_solver_job
from histra.types.convergence_test import ConvergenceTest
from histra.types.linear_system import LinearSystem


def test_work_can_pass_with_a_large_residual() -> None:
    system = LinearSystem(2)
    system.x[:] = [1.0e-4, 0.0]
    system.b[:] = [32.0, 2.0]
    test = ConvergenceTest(tolerance=0.005, criterion="Work")

    # Work = 0.5 * 1e-4 * 32 = 0.0016, even though ||b|| > 32.
    assert test._raw_error(system) == pytest.approx(0.0016)
    assert system.get_b_norm() == pytest.approx(np.hypot(32.0, 2.0))


def test_wall_step_one_audit_exposes_92_kn_vertical_imbalance() -> None:
    audit = audit_static_equilibrium(
        reaction=ReactionResult(0.0, 0.0, -312.352360964),
        reference_reaction=ReactionResult(0.0, 0.0, -112.244969038),
        target_force=np.array([0.0, 0.0, -0.44]),
        load_factor_increment=245.404999,
        residual=np.array([32.078]),
        force_absolute_tolerance=1.0e-3,
        force_relative_tolerance=1.0e-5,
        residual_tolerance=0.005,
    )

    assert audit.expected_reaction[2] == pytest.approx(-220.223168598)
    assert audit.force_error[2] == pytest.approx(-92.129192366)
    assert audit.force_error_max == pytest.approx(92.129192366)
    assert not audit.force_ok
    assert not audit.residual_ok
    assert not audit.safe


def test_equilibrated_state_passes_absolute_and_relative_force_limits() -> None:
    audit = audit_static_equilibrium(
        reaction=ReactionResult(1.0, -2.0, -220.2231687),
        reference_reaction=ReactionResult(1.0, -2.0, -112.244969038),
        target_force=np.array([0.0, 0.0, -0.44]),
        load_factor_increment=245.404999,
        residual=np.array([1.0e-5, -2.0e-5]),
        force_absolute_tolerance=1.0e-3,
        force_relative_tolerance=1.0e-5,
        residual_tolerance=0.005,
    )

    assert audit.force_ok
    assert audit.residual_ok
    assert audit.safe


def test_applied_force_resultant_sums_only_rigid_translations() -> None:
    model = SimpleNamespace(
        collections=SimpleNamespace(
            quads={
                1: SimpleNamespace(status=SimpleNamespace(p=[1, 2, 3, 100, 200, 300, 9])),
                2: SimpleNamespace(status=SimpleNamespace(p=[-4, 5, -6, 400, 500, 600, 8])),
            }
        )
    )
    assert np.array_equal(applied_force_resultant(model), [-3.0, 7.0, -3.0])


@pytest.mark.parametrize(
    ("value", "expected"),
    [("warn", "warn"), ("strict", "error"), ("raise", "error"), ("none", "off")],
)
def test_equilibrium_policy_aliases(value: str, expected: str) -> None:
    assert normalize_equilibrium_policy(value) == expected


def test_relative_work_is_not_silently_treated_as_force_convergence() -> None:
    with pytest.raises(ValueError, match="no convergence-test implementation"):
        ConvergenceTest(criterion="RelativeWork")


def test_production_job_api_defaults_to_strict_equilibrium() -> None:
    parameter = inspect.signature(run_python_solver_job).parameters[
        "equilibrium_policy"
    ]
    assert parameter.default == "error"
