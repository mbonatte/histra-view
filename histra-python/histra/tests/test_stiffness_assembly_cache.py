from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import scipy.sparse as sp

from histra.elements.interface import Interface
from histra.solver.assembler import assemble_global_k
from histra.springs.base import Spring
from histra.types.afference_entry import AfferenceEntry


def _interface(key: int, *, gdl_count: int = 32) -> Interface:
    interface = Interface(key=key, dim_aff=[6, 2, 4], dim_aff_tot=12)
    interface.trasv_1 = [Spring(k=1.0)]
    interface.slid = [Spring(k=1.0)]
    interface.slid_out_plan = [Spring(k=1.0), Spring(k=1.0)]
    interface.status.k = [
        [0.2 + (row * 6 + col) * 0.001 for col in range(6)]
        for row in range(6)
    ]
    interface.status.kslid = [[1.1, -1.1], [-1.1, 1.1]]
    interface.status.kslid_out_plan = [
        [0.3 + (row * 4 + col) * 0.002 for col in range(4)]
        for row in range(4)
    ]
    interface.aff = []
    for local_dof in range(12):
        base = (key * 7 + local_dof * 3) % gdl_count
        interface.aff.append(
            [
                AfferenceEntry(gdl=base + 1, alfa=1.0),
                AfferenceEntry(gdl=((base + 5) % gdl_count) + 1, alfa=-0.125),
                AfferenceEntry(gdl=((base + 11) % gdl_count) + 1, alfa=0.03125),
            ]
        )
    return interface


def _model(count: int = 4) -> SimpleNamespace:
    interfaces = {key: _interface(key) for key in range(1, count + 1)}
    return SimpleNamespace(
        gdl=32,
        collections=SimpleNamespace(quads={}, interfaces=interfaces),
    )


def _assert_csc_bitwise_equal(actual, expected) -> None:
    np.testing.assert_array_equal(actual.indptr, expected.indptr)
    np.testing.assert_array_equal(actual.indices, expected.indices)
    np.testing.assert_array_equal(actual.data, expected.data)


def _assemble_csharp_reference(model: SimpleNamespace) -> sp.csc_matrix:
    """Small literal port of C# ComputeMaskK + Interface.AssembleK.

    The reference intentionally keeps structural zero entries in the mask and
    accumulates local upper-triangle terms sequentially, mirroring off-diagonal
    local terms immediately through LinearSystem.SumK(..., d:false).
    """
    n = model.gdl
    mask: set[tuple[int, int]] = {(i, i) for i in range(n)}

    def aff_pairs(interface: Interface, i: int, j: int):
        if i >= len(interface.aff) or j >= len(interface.aff):
            return
        for ei in interface.aff[i]:
            gi = ei.gdl - 1
            if not 0 <= gi < n:
                continue
            for ej in interface.aff[j]:
                gj = ej.gdl - 1
                if 0 <= gj < n:
                    yield gi, gj, float(ei.alfa), float(ej.alfa)

    # C# mask is symmetric even though Interface.ComputeMaskK emits only its
    # local upper triangle.
    for interface in model.collections.interfaces.values():
        d0, d1, d2 = interface.dim_aff
        for offset, size in ((0, d0), (d0, d1), (d0 + d1, d2)):
            for ii in range(size):
                for jj in range(ii, size):
                    i, j = offset + ii, offset + jj
                    for gi, gj, _ai, _aj in aff_pairs(interface, i, j):
                        mask.add((gi, gj))
                        mask.add((gj, gi))

    values = {entry: 0.0 for entry in mask}

    def add_block(interface: Interface, block, offset: int, size: int) -> None:
        for ii in range(size):
            for jj in range(ii, size):
                i, j = offset + ii, offset + jj
                kij = float(block[ii][jj])
                for gi, gj, ai, aj in aff_pairs(interface, i, j):
                    value = kij * ai * aj
                    values[(gi, gj)] += value
                    if i != j:
                        values[(gj, gi)] += value

    for interface in model.collections.interfaces.values():
        d0, d1, d2 = interface.dim_aff
        add_block(interface, interface.status.k, 0, d0)
        add_block(interface, interface.status.kslid, d0, d1)
        add_block(interface, interface.status.kslid_out_plan, d0 + d1, d2)

    indptr = [0]
    indices: list[int] = []
    data: list[float] = []
    for col in range(n):
        rows = sorted(row for row, c in mask if c == col)
        indices.extend(rows)
        data.extend(values[(row, col)] for row in rows)
        indptr.append(len(indices))
    return sp.csc_matrix(
        (
            np.asarray(data, dtype=np.float64),
            np.asarray(indices, dtype=np.int32),
            np.asarray(indptr, dtype=np.int32),
        ),
        shape=(n, n),
    )


def test_cached_stiffness_scatter_is_bitwise_equal_to_csharp_order() -> None:
    model = _model()
    expected = _assemble_csharp_reference(model)
    actual = assemble_global_k(model, recompute_elements=False)
    _assert_csc_bitwise_equal(actual, expected)


def test_cached_stiffness_scatter_reuses_topology_for_new_local_values() -> None:
    model = _model()
    assemble_global_k(model, recompute_elements=False)
    first_plan = model._perf_stiffness_assembly_plan

    target = model.collections.interfaces[2]
    target.status.k[2][3] = -7.125
    target.status.kslid[0][1] = 0.0
    target.status.kslid_out_plan[3][1] = 2.375

    expected = _assemble_csharp_reference(model)
    actual = assemble_global_k(model, recompute_elements=False)

    assert model._perf_stiffness_assembly_plan is first_plan
    _assert_csc_bitwise_equal(actual, expected)


def test_material_like_spring_replacement_keeps_scatter_plan() -> None:
    model = _model()
    assemble_global_k(model, recompute_elements=False)
    first_plan = model._perf_stiffness_assembly_plan

    target = model.collections.interfaces[3]
    target.trasv_1 = [Spring(k=9.0)]
    target.slid = [Spring(k=8.0)]
    target.slid_out_plan = [Spring(k=7.0), Spring(k=6.0)]

    actual = assemble_global_k(model, recompute_elements=False)
    expected = _assemble_csharp_reference(model)

    assert model._perf_stiffness_assembly_plan is first_plan
    _assert_csc_bitwise_equal(actual, expected)


def test_afference_replacement_invalidates_and_rebuilds_scatter_plan() -> None:
    model = _model()
    assemble_global_k(model, recompute_elements=False)
    first_plan = model._perf_stiffness_assembly_plan

    target = model.collections.interfaces[1]
    target.aff[0] = [
        AfferenceEntry(gdl=1, alfa=0.75),
        AfferenceEntry(gdl=9, alfa=-0.25),
    ]

    actual = assemble_global_k(model, recompute_elements=False)
    expected = _assemble_csharp_reference(model)

    assert model._perf_stiffness_assembly_plan is not first_plan
    _assert_csc_bitwise_equal(actual, expected)


def test_structural_mask_keeps_tiny_and_zero_entries_like_csharp() -> None:
    model = _model(1)
    target = model.collections.interfaces[1]
    # C# does not threshold AssembleK values and its fixed mask retains
    # structural slots even when the current coefficient is zero/tiny.
    target.status.k[0][0] = 5.0e-31
    target.status.k[0][1] = 2.0e-30

    actual = assemble_global_k(model, recompute_elements=False)
    expected = _assemble_csharp_reference(model)
    _assert_csc_bitwise_equal(actual, expected)


def test_cached_plan_preserves_csharp_interface_emission_order() -> None:
    from histra.solver.assembler import _build_stiffness_assembly_plan

    model = _model(2)

    # Exercise invalid-DOF filtering inside interface scatter.
    model.collections.interfaces[1].aff[0].insert(
        1, AfferenceEntry(gdl=0, alfa=9.5)
    )

    plan = _build_stiffness_assembly_plan(model)

    expected_rows: list[int] = []
    expected_cols: list[int] = []
    expected_terms: list[int] = []
    expected_alpha_i: list[float] = []
    expected_alpha_j: list[float] = []

    term_index = 0

    for interface in model.collections.interfaces.values():
        d0, d1, d2 = interface.dim_aff

        blocks = [(0, d0)]

        if interface.slid:
            blocks.append((d0, d1))

        if len(interface.slid_out_plan) >= 2:
            blocks.append((d0 + d1, d2))

        for offset, size in blocks:
            # Match C# AssembleK: consume only the local upper triangle.
            for i in range(size):
                for j in range(i, size):
                    local_i = offset + i
                    local_j = offset + j

                    if (
                        local_i < len(interface.aff)
                        and local_j < len(interface.aff)
                    ):
                        for ei in interface.aff[local_i]:
                            gi = int(ei.gdl) - 1

                            if gi < 0 or gi >= model.gdl:
                                continue

                            ai = float(ei.alfa)

                            for ej in interface.aff[local_j]:
                                gj = int(ej.gdl) - 1

                                if gj < 0 or gj >= model.gdl:
                                    continue

                                aj = float(ej.alfa)

                                # Original contribution.
                                expected_rows.append(gi)
                                expected_cols.append(gj)
                                expected_terms.append(term_index)
                                expected_alpha_i.append(ai)
                                expected_alpha_j.append(aj)

                                # C# SumK(..., d:false) immediately emits
                                # the symmetric global contribution for
                                # off-diagonal local terms.
                                if local_i != local_j:
                                    expected_rows.append(gj)
                                    expected_cols.append(gi)
                                    expected_terms.append(term_index)
                                    expected_alpha_i.append(ai)
                                    expected_alpha_j.append(aj)

                    term_index += 1

    # output_indices points into the fixed CSC data array. Reconstruct the
    # global row/column corresponding to every emitted contribution while
    # retaining contribution-stream order.
    actual_rows = plan.indices[plan.output_indices]

    actual_cols = np.searchsorted(
        plan.indptr[1:],
        plan.output_indices,
        side="right",
    ).astype(np.int32, copy=False)

    np.testing.assert_array_equal(
        actual_rows,
        np.asarray(expected_rows, dtype=np.int32),
    )
    np.testing.assert_array_equal(
        actual_cols,
        np.asarray(expected_cols, dtype=np.int32),
    )
    np.testing.assert_array_equal(
        plan.term_indices,
        np.asarray(expected_terms, dtype=np.int32),
    )
    np.testing.assert_array_equal(
        plan.alpha_i,
        np.asarray(expected_alpha_i, dtype=np.float64),
    )
    np.testing.assert_array_equal(
        plan.alpha_j,
        np.asarray(expected_alpha_j, dtype=np.float64),
    )

    assert plan.term_count == term_index
