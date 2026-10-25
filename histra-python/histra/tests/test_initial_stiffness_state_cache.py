from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from histra.solver.assembler import assemble_global_k
from histra.solver.model_manager import ModelManager


class _Element:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def compute_k(self, alfa: float) -> None:
        self.calls.append(float(alfa))


def _model() -> SimpleNamespace:
    return SimpleNamespace(
        collections=SimpleNamespace(
            quads={1: _Element(), 2: _Element()},
            interfaces={10: _Element(), 11: _Element(), 12: _Element()},
        )
    )


def test_repeated_initial_stiffness_reuses_exact_element_blocks() -> None:
    model = _model()

    ModelManager.compute_k(model, 0.0)
    ModelManager.compute_k(model, 0.0)

    assert [element.calls for element in model.collections.quads.values()] == [
        [0.0],
        [0.0],
    ]
    assert [element.calls for element in model.collections.interfaces.values()] == [
        [0.0],
        [0.0],
        [0.0],
    ]


def test_initial_stiffness_recomputes_only_explicitly_dirty_interfaces() -> None:
    model = _model()
    ModelManager.compute_k(model, 0.0)
    model._perf_initial_stiffness_dirty_interfaces = {10, 12}

    ModelManager.compute_k(model, 0.0)

    assert [element.calls for element in model.collections.quads.values()] == [
        [0.0],
        [0.0],
    ]
    assert [element.calls for element in model.collections.interfaces.values()] == [
        [0.0, 0.0],
        [0.0],
        [0.0, 0.0],
    ]
    assert model._perf_initial_stiffness_dirty_interfaces == set()


def test_noninitial_tangent_forces_next_initial_stiffness_full_refresh() -> None:
    model = _model()
    ModelManager.compute_k(model, 0.0)
    ModelManager.compute_k(model, 1.0)
    ModelManager.compute_k(model, 0.0)

    assert [element.calls for element in model.collections.quads.values()] == [
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    assert [element.calls for element in model.collections.interfaces.values()] == [
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
    ]


def test_selective_refresh_preserves_global_stiffness_matrix_exactly() -> None:
    entry = SimpleNamespace(gdl=1, alfa=1.0)

    quad = SimpleNamespace(
        status=SimpleNamespace(k=0.0),
        aff=[[], [], [], [], [], [], [entry]],
    )
    quad.compute_k = lambda alfa: setattr(quad.status, "k", 4.0 + float(alfa))

    interface = SimpleNamespace(
        key=10,
        dim_aff=[1, 0, 0],
        status=SimpleNamespace(k=[[0.0]], kslid=[], kslid_out_plan=[]),
        aff=[[entry]],
        slid=[],
        slid_out_plan=[],
    )
    interface.compute_k = lambda alfa: setattr(
        interface.status, "k", [[7.0 + float(alfa)]]
    )
    model = SimpleNamespace(
        gdl=1,
        collections=SimpleNamespace(quads={1: quad}, interfaces={10: interface}),
    )

    ModelManager.compute_k(model, 0.0)
    baseline = assemble_global_k(
        model, alfa=0.0, recompute_elements=False
    ).toarray()
    model._perf_initial_stiffness_dirty_interfaces = {10}
    ModelManager.compute_k(model, 0.0)
    selective = assemble_global_k(
        model, alfa=0.0, recompute_elements=False
    ).toarray()

    np.testing.assert_array_equal(selective, baseline)
