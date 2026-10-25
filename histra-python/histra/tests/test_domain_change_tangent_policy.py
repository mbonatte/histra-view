from types import SimpleNamespace

from histra.solver.continuation import _domain_change_requires_tangent_refresh


def test_standard_method_retains_algorithm_tangent_at_segment_boundary() -> None:
    analysis = SimpleNamespace(method="StandardInitialInterpolatedLineSearch")

    assert not _domain_change_requires_tangent_refresh(analysis)


def test_modified_method_refreshes_tangent_at_segment_boundary() -> None:
    analysis = SimpleNamespace(method="ModifiedRegulaFalsiLineSearch")

    assert _domain_change_requires_tangent_refresh(analysis)
