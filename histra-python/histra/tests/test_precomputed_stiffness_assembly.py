from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from histra.solver.assembler import assemble_global_k


def _entry(gdl: int, alfa: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(gdl=gdl, alfa=alfa)


def test_assemble_global_k_reuses_precomputed_element_stiffness() -> None:
    def must_not_recompute(_alfa: float) -> None:
        raise AssertionError("element stiffness was recomputed during assembly")

    quad = SimpleNamespace(
        status=SimpleNamespace(k=4.0),
        aff=[[], [], [], [], [], [], [_entry(1), _entry(2, 0.5)]],
        compute_k=must_not_recompute,
    )
    interface = SimpleNamespace(
        dim_aff=[1, 2, 0],
        status=SimpleNamespace(
            k=[[10.0]],
            kslid=[[3.0, -3.0], [-3.0, 3.0]],
            kslid_out_plan=[],
        ),
        aff=[[_entry(1)], [_entry(2)], [_entry(3)]],
        slid=[object()],
        slid_out_plan=[],
    )
    model = SimpleNamespace(
        gdl=3,
        collections=SimpleNamespace(
            quads={1: quad},
            interfaces={1: interface},
        ),
    )

    matrix = assemble_global_k(
        model, alfa=0.0, recompute_elements=False
    ).toarray()

    expected = np.array(
        [
            [14.0, 2.0, 0.0],
            [2.0, 4.0, -3.0],
            [0.0, -3.0, 3.0],
        ]
    )
    np.testing.assert_array_equal(matrix, expected)


def test_standalone_assembly_delegates_local_stiffness_once_per_element() -> None:
    calls: list[tuple[str, float]] = []

    quad = SimpleNamespace(
        status=SimpleNamespace(k=np.nan),
        aff=[[], [], [], [], [], [], [_entry(1), _entry(2, 0.5)]],
    )

    def compute_quad(alfa: float) -> None:
        calls.append(("quad", alfa))
        quad.status.k = 4.0

    quad.compute_k = compute_quad

    interface = SimpleNamespace(
        dim_aff=[1, 2, 2],
        status=SimpleNamespace(
            k=[[np.nan]],
            kslid=[[np.nan, np.nan], [np.nan, np.nan]],
            kslid_out_plan=[[np.nan, np.nan], [np.nan, np.nan]],
        ),
        aff=[
            [_entry(1)],
            [_entry(2)],
            [_entry(3)],
            [_entry(4)],
            [_entry(5)],
        ],
        slid=[object()],
        slid_out_plan=[object(), object()],
    )

    def compute_interface(alfa: float) -> None:
        calls.append(("interface", alfa))
        interface.status.k = [[10.0]]
        interface.status.kslid = [[3.0, -3.0], [-3.0, 3.0]]
        interface.status.kslid_out_plan = [[5.0, -5.0], [-5.0, 5.0]]

    interface.compute_k = compute_interface
    model = SimpleNamespace(
        gdl=5,
        collections=SimpleNamespace(
            quads={1: quad},
            interfaces={1: interface},
        ),
    )

    matrix = assemble_global_k(model, alfa=0.37).toarray()

    assert calls == [("quad", 0.37), ("interface", 0.37)]
    np.testing.assert_array_equal(
        matrix,
        np.array(
            [
                [14.0, 2.0, 0.0, 0.0, 0.0],
                [2.0, 4.0, -3.0, 0.0, 0.0],
                [0.0, -3.0, 3.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 5.0, -5.0],
                [0.0, 0.0, 0.0, -5.0, 5.0],
            ]
        ),
    )
