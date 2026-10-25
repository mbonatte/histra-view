"""Source-derived control tests; native whole-Execute validation is separate."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from histra.solver.secant_stiffness import SecantStiffnessPolicy


def analysis(**changes):
    return SimpleNamespace(**(dict(check_secant_stiffness=True, integration_method="ArcLength",
                                   method="StandardNewtonRaphson", secant_stiffness_ratio=0.1) | changes))


def test_native_source_policy_tracks_graph_slope_and_refreshes_only_on_change():
    policy = SecantStiffnessPolicy(analysis(), [100.0, 20.0])
    program = SimpleNamespace(log=Mock())
    integrator = SimpleNamespace(update_k=Mock())
    # The initial slope is measured relative to the predecessor, not zero.
    alpha = policy.update(1, [110.0, 21.0, 999.0], 1.0, program, None, integrator)
    assert policy.initial_stiffness == 10.0
    integrator.update_k.assert_not_called()
    for step, values, expected in (
        (2, [110.5, 22.0], 0.0),  # softening
        (3, [110.0, 23.0], 0.0),  # negative slope, already initial
        (4, [120.0, 24.0], 1.0),  # recover current stiffness
    ):
        alpha = policy.update(step, values, alpha, program, None, integrator)
        assert alpha == expected
    assert [call.args[2] for call in integrator.update_k.call_args_list] == [0.0, 1.0]


@pytest.mark.parametrize("changes", [dict(check_secant_stiffness=False),
    dict(integration_method="LoadControl"), dict(integration_method="ArcLengthLinear"),
    dict(method="ModifiedNewtonRaphson")])
def test_native_source_gate_preserves_other_strategies(changes):
    policy = SecantStiffnessPolicy(analysis(**changes), [0.0, 0.0])
    assert policy.update(2, [-1.0, 1.0], 1.0, None, None, None) == 1.0


@pytest.mark.parametrize("offset, expected", [(-1, 0.0), (0, 1.0), (1, 1.0)])
def test_single_threshold_and_strict_comparison(offset, expected):
    policy = SecantStiffnessPolicy(analysis(), [0.0, 0.0])
    program = SimpleNamespace(log=Mock())
    integrator = SimpleNamespace(update_k=Mock())
    policy.update(1, [1.0, 1.0], 1.0, program, None, integrator)
    boundary = 1.0 + float(np.float32(0.1))
    force = np.nextafter(boundary, -np.inf if offset < 0 else np.inf) if offset else boundary
    assert policy.update(2, [force, 2.0], 1.0, program, None, integrator) == expected


@pytest.mark.parametrize("values, expected", [([0.0, 1.0], 1.0), ([1.0, 1.0], 1.0), ([-1.0, 1.0], 0.0)])
def test_zero_increment_follows_dotnet_division(values, expected):
    policy = SecantStiffnessPolicy(analysis(), [0.0, 0.0])
    program = SimpleNamespace(log=Mock())
    integrator = SimpleNamespace(update_k=Mock())
    policy.update(1, [0.0, 1.0], 1.0, program, None, integrator)
    assert policy.update(2, values, 1.0, program, None, integrator) == expected


def test_update_k_fallback_propagates_native_ref_alpha():
    policy = SecantStiffnessPolicy(analysis(), [0.0, 0.0])
    program = SimpleNamespace(log=Mock(), static_tangent_alpha=0.0)
    integrator = SimpleNamespace(update_k=Mock())
    policy.update(1, [1.0, 1.0], 0.0, program, None, integrator)
    assert policy.update(2, [2.0, 2.0], 0.0, program, None, integrator) == 0.0
    integrator.update_k.assert_called_once_with(program, None, 1.0)
