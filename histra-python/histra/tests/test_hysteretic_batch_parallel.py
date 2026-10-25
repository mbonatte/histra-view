from __future__ import annotations

import numpy as np
import pytest

from histra.solver import hysteretic_batch as hb

pytestmark = pytest.mark.skipif(
    hb._evaluate_simple_linear_batch is None,
    reason="Numba is unavailable",
)


def _simple_params(count: int) -> np.ndarray:
    params = np.zeros((count, hb.SIMPLE_TRANSVERSE_PARAM_SIZE), dtype=np.float64)
    params[:, 0] = 1.0e-3
    params[:, 1] = 1.0
    params[:, 2] = 2.0e-3
    params[:, 3] = 0.8
    params[:, 4] = 3.0e-3
    params[:, 6] = -1.0
    params[:, 7] = -1.0e-3
    params[:, 8] = -2.0e-3
    params[:, 9] = -0.8
    params[:, 10] = -3.0e-3
    params[:, 12] = 1000.0
    params[:, 13] = 1000.0
    params[:, 14] = -200.0
    params[:, 15] = -200.0
    params[:, 16] = -100.0
    params[:, 17] = -100.0
    params[:, 18] = 1000.0
    params[:, 19] = 1000.0
    return params


@pytest.mark.parametrize(
    ("interfaces", "springs", "expected"),
    [
        (100, 8_000, 1),
        (682, 55_242, 2),
        (3_000, 240_000, 4),
        (10_000, 800_000, 8),
    ],
)
def test_numba_thread_policy_scales_with_nonlinear_workload(
    interfaces: int, springs: int, expected: int
) -> None:
    assert hb.recommended_numba_threads(
        interfaces, springs, 20, environ={}
    ) == expected


def test_numba_thread_policy_honours_overrides() -> None:
    assert hb.recommended_numba_threads(
        682, 55_242, 20, environ={"HISTRA_NUMBA_THREADS": "6"}
    ) == 6
    assert hb.recommended_numba_threads(
        682, 55_242, 4, environ={"HISTRA_NUMBA_THREADS": "20"}
    ) == 4
    assert hb.recommended_numba_threads(
        682, 55_242, 20, environ={"NUMBA_NUM_THREADS": "12"}
    ) == 20


def test_parallel_simple_hysteretic_matches_scalar_loop_exactly() -> None:
    count = 257
    rng = np.random.default_rng(734)
    params = _simple_params(count)
    committed = np.zeros((count, 9), dtype=np.float64)
    committed[:, 0] = 2.0e-4
    committed[:, 1] = -2.0e-4
    committed[:, 6] = rng.normal(0.0, 0.1, count)
    committed[:, 7] = rng.normal(0.0, 1.0e-4, count)
    trial_reference = np.zeros((count, 10), dtype=np.float64)
    trial_reference[:, 9] = 1000.0
    trial_parallel = trial_reference.copy()
    targets = rng.normal(0.0, 3.0e-4, count)
    enabled = np.ones(count, dtype=np.bool_)

    hb._evaluate_simple_linear_batch.py_func(
        params.copy(), committed.copy(), trial_reference, targets.copy(), enabled.copy()
    )
    hb._evaluate_simple_linear_batch(
        params.copy(), committed.copy(), trial_parallel, targets.copy(), enabled.copy()
    )

    np.testing.assert_array_equal(trial_parallel, trial_reference)


def test_parallel_interface_reduction_preserves_spring_order_exactly() -> None:
    records = 7
    springs_per_record = 19
    count = records * springs_per_record
    rng = np.random.default_rng(991)
    trial = np.zeros((count, 10), dtype=np.float64)
    committed = np.zeros((count, 9), dtype=np.float64)
    trial[:, 6] = rng.normal(size=count)
    trial[:, 7] = rng.normal(scale=1.0e-4, size=count)
    committed[:, 6] = rng.normal(size=count)
    di = np.tile(np.linspace(0.03, 0.97, springs_per_record), records)
    dj = 1.0 - di
    ecc = np.tile(np.linspace(-0.3, 0.3, springs_per_record), records)
    lengths = np.linspace(0.7, 1.3, records)
    starts = np.arange(records, dtype=np.int32) * springs_per_record
    stops = starts + springs_per_record
    constrained = np.asarray([False, True, False, True, False, True, False])

    reference = [
        np.zeros((records, 6), dtype=np.float64),
        np.zeros(records, dtype=np.float64),
        np.zeros(records, dtype=np.float64),
        np.zeros(records, dtype=np.float64),
    ]
    parallel = [array.copy() for array in reference]

    hb._finish_transverse_batch.py_func(
        trial, committed, di, dj, ecc, lengths, starts, stops, constrained, *reference
    )
    hb._finish_transverse_batch(
        trial, committed, di, dj, ecc, lengths, starts, stops, constrained, *parallel
    )

    for actual, expected in zip(parallel, reference):
        np.testing.assert_array_equal(actual, expected)


def test_parallel_general_hysteretic_matches_scalar_loop_exactly() -> None:
    count = 257
    rng = np.random.default_rng(735)
    params = np.zeros((count, hb.TRANSVERSE_PARAM_SIZE), dtype=np.float64)
    compact = _simple_params(count)
    params[:, 8] = 1.0
    params[:, 10:30] = compact[:, :20]
    params[:, 31] = 1000.0
    params[:, hb.TENSILE_CURVE_TYPE_PARAM] = compact[:, hb.SIMPLE_TENSILE_CURVE_TYPE_PARAM]
    committed = np.zeros((count, 9), dtype=np.float64)
    committed[:, 0] = 2.0e-4
    committed[:, 1] = -2.0e-4
    committed[:, 6] = rng.normal(0.0, 0.1, count)
    committed[:, 7] = rng.normal(0.0, 1.0e-4, count)
    reference = np.zeros((count, 10), dtype=np.float64)
    reference[:, 9] = 1000.0
    parallel = reference.copy()
    targets = rng.normal(0.0, 3.0e-4, count)
    enabled = np.ones(count, dtype=np.bool_)

    hb._evaluate_linear_batch.py_func(
        params.copy(), committed.copy(), reference, targets.copy(), enabled.copy()
    )
    hb._evaluate_linear_batch(
        params.copy(), committed.copy(), parallel, targets.copy(), enabled.copy()
    )
    np.testing.assert_array_equal(parallel, reference)


def test_parallel_initial_coulomb_matches_scalar_loop_bit_exactly() -> None:
    count = 257
    rng = np.random.default_rng(742)
    params = np.empty((count, 7), dtype=np.float64)
    params[:, :] = (1000.0, 10.0, 0.2, 0.3, 1.0, 1000.0, -100.0)
    state = np.zeros((count, hb.COULOMB_STATE_SIZE), dtype=np.float64)
    state[:, hb.CFY1] = -0.2
    state[:, hb.CCUP] = rng.normal(0.0, 1.0e-5, count)
    state[:, hb.CCSTRESS] = rng.normal(0.0, 0.05, count)
    state[:, hb.CCSTRAIN] = rng.normal(0.0, 1.0e-4, count)
    state[:, hb.CCSTRESS_NORMAL] = rng.normal(1.0, 0.1, count)
    state[:, hb.CCENERGY] = rng.normal(0.0, 1.0e-5, count)
    state[:, hb.CCPHASE] = hb.ELASTIC
    state[::29, hb.CCPHASE] = hb.RUPTURE
    state[:, hb.CKTANG] = 1000.0
    state[:, hb.CROT2P] = 2.0e-3
    state[:, hb.CROT3P] = 3.0e-3
    targets = rng.normal(0.0, 3.0e-4, count)
    dns = rng.normal(0.0, 0.01, count)
    enabled = np.ones(count, dtype=np.bool_)
    enabled[::31] = False
    reference = state.copy()
    parallel = state.copy()

    hb._evaluate_initial_coulomb_batch.py_func(
        params, reference, targets, dns, enabled
    )
    hb._evaluate_initial_coulomb_batch(
        params, parallel, targets, dns, enabled
    )

    np.testing.assert_array_equal(
        parallel.view(np.uint64), reference.view(np.uint64)
    )


def test_parallel_full_interface_force_assembly_matches_previous_path_exactly() -> None:
    records = 97
    coulomb_count = records * 3
    rng = np.random.default_rng(744)
    transverse = rng.normal(size=(records, 6))
    coulomb_state = np.zeros(
        (coulomb_count, hb.COULOMB_STATE_SIZE), dtype=np.float64
    )
    coulomb_state[:, hb.CTSTRESS] = rng.normal(size=coulomb_count)
    slid = np.arange(records, dtype=np.int32)
    oop0 = np.arange(records, records * 2, dtype=np.int32)
    oop1 = np.arange(records * 2, records * 3, dtype=np.int32)
    slid[::19] = -1
    oop0[::23] = -1
    oop1[::23] = -1
    dist = rng.random((records, 2))
    targets = rng.normal(size=coulomb_count)
    initial_max = rng.random(records)
    expected_forces = np.empty((records, 12), dtype=np.float64)
    expected_max = initial_max.copy()

    expected_forces[:, :] = 0.0
    expected_forces[:, :6] = transverse
    for index in range(records):
        max_u = expected_max[index]
        s = slid[index]
        if s >= 0:
            force = coulomb_state[s, hb.CTSTRESS]
            expected_forces[index, 6] += force
            expected_forces[index, 7] -= force
            max_u = max(max_u, abs(targets[s]))
        a = oop0[index]
        b = oop1[index]
        if a >= 0 and b >= 0:
            di, dj = dist[index]
            force0 = coulomb_state[a, hb.CTSTRESS]
            force1 = coulomb_state[b, hb.CTSTRESS]
            first = dj * force0 + di * force1
            second = di * force0 + dj * force1
            expected_forces[index, 8] += first
            expected_forces[index, 9] += second
            expected_forces[index, 10] -= first
            expected_forces[index, 11] -= second
            max_u = max(max_u, abs(targets[a]), abs(targets[b]))
        expected_max[index] = max_u

    actual_forces = np.empty_like(expected_forces)
    actual_max = initial_max.copy()
    hb._assemble_full_interface_forces(
        transverse,
        coulomb_state,
        slid,
        oop0,
        oop1,
        dist,
        actual_forces,
        actual_max,
        targets,
    )

    np.testing.assert_array_equal(
        actual_forces.view(np.uint64), expected_forces.view(np.uint64)
    )
    np.testing.assert_array_equal(
        actual_max.view(np.uint64), expected_max.view(np.uint64)
    )


def test_force_by_dof_topology_matches_ordered_scatter_bit_exactly() -> None:
    rng = np.random.default_rng(748)
    global_count = 251
    interface_count = 97
    quad_count = 43
    interface_local_count = interface_count * 12

    interface_counts = rng.integers(0, 5, interface_local_count, dtype=np.int32)
    interface_offsets = np.empty(interface_local_count + 1, dtype=np.int32)
    interface_offsets[0] = 0
    np.cumsum(interface_counts, out=interface_offsets[1:])
    interface_gdls = rng.integers(
        -2, global_count + 2, interface_offsets[-1], dtype=np.int32
    )
    interface_coefficients = rng.normal(size=interface_offsets[-1])

    quad_counts = rng.integers(0, 4, quad_count, dtype=np.int32)
    quad_offsets = np.empty(quad_count + 1, dtype=np.int32)
    quad_offsets[0] = 0
    np.cumsum(quad_counts, out=quad_offsets[1:])
    quad_gdls = rng.integers(
        -2, global_count + 2, quad_offsets[-1], dtype=np.int32
    )
    quad_coefficients = rng.normal(size=quad_offsets[-1])

    interface_forces = rng.normal(size=(interface_count, 12))
    interface_forces.ravel()[::37] = 0.0
    quad_d_alfa = rng.normal(size=quad_count)
    quad_state = np.zeros((quad_count, hb.QUAD_STATE_SIZE), dtype=np.float64)
    quad_state[:, hb.QTSTRESS] = rng.normal(size=quad_count)
    old_quad_forces = np.empty((quad_count, 1), dtype=np.float64)
    new_quad_forces = np.empty_like(old_quad_forces)
    expected = np.empty(global_count, dtype=np.float64)
    actual = np.empty_like(expected)

    hb._refresh_global_resisting_force(
        quad_d_alfa,
        quad_state,
        old_quad_forces,
        quad_offsets,
        quad_gdls,
        quad_coefficients,
        interface_forces,
        interface_offsets,
        interface_gdls,
        interface_coefficients,
        expected,
    )
    global_offsets, force_indices, force_coefficients, interface_force_size = (
        hb._build_force_by_dof_topology(
            global_count,
            interface_offsets,
            interface_gdls,
            interface_coefficients,
            quad_offsets,
            quad_gdls,
            quad_coefficients,
        )
    )
    hb._refresh_global_resisting_force_by_dof(
        quad_d_alfa,
        quad_state,
        new_quad_forces,
        interface_forces,
        global_offsets,
        force_indices,
        force_coefficients,
        interface_force_size,
        actual,
    )

    np.testing.assert_array_equal(
        new_quad_forces.view(np.uint64), old_quad_forces.view(np.uint64)
    )
    np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))


def test_fused_interface_mapping_and_kinematics_matches_two_pass_path_exactly() -> None:
    rng = np.random.default_rng(751)
    records = 97
    width = 12
    global_count = 251
    local_count = records * width
    counts = rng.integers(0, 5, local_count, dtype=np.int32)
    offsets = np.empty(local_count + 1, dtype=np.int32)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])
    gdls = rng.integers(-2, global_count + 2, offsets[-1], dtype=np.int32)
    coefficients = rng.normal(size=offsets[-1])
    x = rng.normal(size=global_count)
    initial_u = rng.normal(size=(records, width))
    lengths = rng.random(records) + 0.5
    constrained = (np.arange(records) % 7) == 0
    d0s = np.full(records, 6, dtype=np.int32)
    d1s = np.full(records, 2, dtype=np.int32)

    expected = (
        np.empty((records, width), dtype=np.float64),
        initial_u.copy(),
        np.empty(records, dtype=np.float64),
        np.empty(records, dtype=np.float64),
        np.empty(records, dtype=np.float64),
        np.empty((records, 3), dtype=np.float64),
    )
    actual = tuple(array.copy() for array in expected)
    hb._map_global_to_local(
        x, offsets, gdls, coefficients, expected[0], expected[1]
    )
    hb._prepare_interface_kinematics(
        expected[0], expected[1], lengths, constrained, d0s, d1s,
        expected[2], expected[3], expected[4], expected[5], False,
    )
    hb._map_and_prepare_interface_kinematics(
        x, offsets, gdls, coefficients, actual[0], actual[1], lengths,
        constrained, d0s, d1s, actual[2], actual[3], actual[4], actual[5],
    )

    for actual_array, expected_array in zip(actual, expected, strict=True):
        np.testing.assert_array_equal(
            actual_array.view(np.uint64), expected_array.view(np.uint64)
        )


def test_parallel_target_update_is_exact() -> None:
    records = 11
    springs_per_record = 13
    count = records * springs_per_record
    rng = np.random.default_rng(736)
    trial = rng.normal(size=(count, 10))
    record_index = np.repeat(np.arange(records, dtype=np.int32), springs_per_record)
    num = rng.normal(size=records)
    num2 = rng.normal(size=records)
    di = rng.random(count)
    dj = 1.0 - di
    lengths = rng.random(records) + 0.5
    delta_flex = rng.normal(size=records)
    ecc = rng.normal(size=count)
    reference = np.empty(count, dtype=np.float64)
    parallel = np.empty(count, dtype=np.float64)

    hb._advance_transverse_targets.py_func(
        trial, record_index, num, num2, di, dj, lengths, delta_flex, ecc, reference
    )
    hb._advance_transverse_targets(
        trial, record_index, num, num2, di, dj, lengths, delta_flex, ecc, parallel
    )
    np.testing.assert_array_equal(parallel, reference)


def test_fused_target_and_simple_hysteretic_matches_separate_kernels_exactly() -> None:
    records = 17
    springs_per_record = 23
    count = records * springs_per_record
    rng = np.random.default_rng(737)

    params = _simple_params(count)
    committed = np.zeros((count, 9), dtype=np.float64)
    committed[:, 0] = 2.5e-4
    committed[:, 1] = -2.5e-4
    committed[:, 4] = rng.normal(0.0, 1.0e-5, count)
    committed[:, 5] = rng.integers(0, 3, size=count)
    committed[:, 6] = rng.normal(0.0, 0.1, count)
    committed[:, 7] = rng.normal(0.0, 1.0e-4, count)
    committed[:, 8] = hb.ELASTIC

    trial_reference = np.zeros((count, 10), dtype=np.float64)
    trial_reference[:, 5] = committed[:, 5]
    trial_reference[:, 6] = committed[:, 6]
    trial_reference[:, 7] = committed[:, 7]
    trial_reference[:, 8] = committed[:, 8]
    trial_reference[:, 9] = 1000.0
    trial_fused = trial_reference.copy()

    record_index = np.repeat(np.arange(records, dtype=np.int32), springs_per_record)
    num = rng.normal(0.0, 2.0e-4, records)
    num2 = rng.normal(0.0, 2.0e-4, records)
    di = rng.random(count)
    dj = 1.0 - di
    lengths = rng.random(records) + 0.5
    delta_flex = rng.normal(0.0, 2.0e-4, records)
    ecc = rng.normal(0.0, 0.2, count)
    enabled = np.ones(count, dtype=np.bool_)
    enabled[::31] = False

    targets_reference = np.empty(count, dtype=np.float64)
    targets_fused = np.empty(count, dtype=np.float64)

    hb._advance_transverse_targets(
        trial_reference,
        record_index,
        num,
        num2,
        di,
        dj,
        lengths,
        delta_flex,
        ecc,
        targets_reference,
    )
    hb._evaluate_simple_linear_batch(
        params,
        committed,
        trial_reference,
        targets_reference,
        enabled,
    )

    hb._advance_and_evaluate_simple_linear_batch(
        params,
        committed,
        trial_fused,
        targets_fused,
        enabled,
        record_index,
        num,
        num2,
        di,
        dj,
        lengths,
        delta_flex,
        ecc,
    )

    np.testing.assert_array_equal(targets_fused, targets_reference)
    np.testing.assert_array_equal(trial_fused, trial_reference)


def test_fused_simple_update_and_reduction_matches_two_pass_path_bit_exactly() -> None:
    records = 17
    springs_per_record = 23
    count = records * springs_per_record
    rng = np.random.default_rng(739)

    params = _simple_params(count)
    committed = np.zeros((count, 9), dtype=np.float64)
    committed[:, 0] = 2.5e-4
    committed[:, 1] = -2.5e-4
    committed[:, 4] = rng.normal(0.0, 1.0e-5, count)
    committed[:, 5] = rng.integers(0, 3, size=count)
    committed[:, 6] = rng.normal(0.0, 0.1, count)
    committed[:, 7] = rng.normal(0.0, 1.0e-4, count)
    committed[:, 8] = hb.ELASTIC

    separate_trial = np.zeros((count, 10), dtype=np.float64)
    separate_trial[:, 5] = committed[:, 5]
    separate_trial[:, 6] = committed[:, 6]
    separate_trial[:, 7] = committed[:, 7]
    separate_trial[:, 8] = committed[:, 8]
    separate_trial[:, 9] = 1000.0
    fused_trial = separate_trial.copy()

    record_index = np.repeat(np.arange(records, dtype=np.int32), springs_per_record)
    num = rng.normal(0.0, 2.0e-4, records)
    num2 = rng.normal(0.0, 2.0e-4, records)
    di = rng.random(count)
    dj = 1.0 - di
    lengths = rng.random(records) + 0.5
    delta_flex = rng.normal(0.0, 2.0e-4, records)
    ecc = rng.normal(0.0, 0.2, count)
    enabled = np.ones(count, dtype=np.bool_)
    enabled[::31] = False
    starts = np.arange(records, dtype=np.int32) * springs_per_record
    stops = starts + springs_per_record
    constrained = np.asarray([(index % 3) == 0 for index in range(records)])

    separate_targets = np.empty(count, dtype=np.float64)
    fused_targets = np.empty(count, dtype=np.float64)
    separate_outputs = (
        np.empty((records, 6), dtype=np.float64),
        np.empty(records, dtype=np.float64),
        np.empty(records, dtype=np.float64),
        np.empty(records, dtype=np.float64),
    )
    fused_outputs = tuple(array.copy() for array in separate_outputs)

    hb._advance_and_evaluate_simple_linear_batch(
        params,
        committed,
        separate_trial,
        separate_targets,
        enabled,
        record_index,
        num,
        num2,
        di,
        dj,
        lengths,
        delta_flex,
        ecc,
    )
    hb._finish_transverse_batch(
        separate_trial,
        committed,
        di,
        dj,
        ecc,
        lengths,
        starts,
        stops,
        constrained,
        *separate_outputs,
    )

    hb._advance_evaluate_and_finish_simple_linear_batch(
        params,
        committed,
        fused_trial,
        fused_targets,
        enabled,
        record_index,
        num,
        num2,
        di,
        dj,
        lengths,
        delta_flex,
        ecc,
        starts,
        stops,
        constrained,
        *fused_outputs,
    )

    for actual, expected in (
        (fused_targets, separate_targets),
        (fused_trial, separate_trial),
        *zip(fused_outputs, separate_outputs),
    ):
        np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))


def _finish_transverse_reference(
    trial: np.ndarray,
    committed: np.ndarray,
    di: np.ndarray,
    dj: np.ndarray,
    ecc: np.ndarray,
    lengths: np.ndarray,
    starts: np.ndarray,
    stops: np.ndarray,
    constrained: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pre-optimization force reduction, kept as a bit-exact oracle."""
    local_forces = np.zeros((starts.size, 6), dtype=np.float64)
    normal_increments = np.zeros(starts.size, dtype=np.float64)
    committed_forces = np.zeros(starts.size, dtype=np.float64)
    max_displacements = np.zeros(starts.size, dtype=np.float64)

    for record_index in range(starts.size):
        start = int(starts[record_index])
        stop = int(stops[record_index])
        normal_increment = 0.0
        committed_force = 0.0
        max_displacement = 0.0
        for spring_index in range(start, stop):
            force = trial[spring_index, 6]
            committed_value = committed[spring_index, 6]
            normal_increment -= force - committed_value
            committed_force += force - (force - committed_value)
            displacement = abs(trial[spring_index, 7])
            if displacement > max_displacement:
                max_displacement = displacement

            length = lengths[record_index]
            if not constrained[record_index]:
                local_forces[record_index, 3] += force * dj[spring_index] / length
                local_forces[record_index, 2] += force * di[spring_index] / length
                local_forces[record_index, 0] += (0.0 - force) * dj[spring_index] / length
                local_forces[record_index, 1] += (0.0 - force) * di[spring_index] / length
            else:
                local_forces[record_index, 3] += force * dj[spring_index] / length
                local_forces[record_index, 2] += force * di[spring_index] / length
                local_forces[record_index, 0] += (
                    (0.0 - force) * di[spring_index] / length
                    - force * dj[spring_index] / length
                )
                local_forces[record_index, 1] += 0.5 * length * (
                    force * dj[spring_index] / length
                    - force * di[spring_index] / length
                )
            local_forces[record_index, 4] += force * ecc[spring_index]
            local_forces[record_index, 5] += (0.0 - force) * ecc[spring_index]

        normal_increments[record_index] = normal_increment
        committed_forces[record_index] = committed_force
        max_displacements[record_index] = max_displacement

    return local_forces, normal_increments, committed_forces, max_displacements


def test_interface_reduction_hoisted_invariants_match_previous_loop_exactly() -> None:
    records = 13
    springs_per_record = 27
    count = records * springs_per_record
    rng = np.random.default_rng(738)
    trial = np.zeros((count, 10), dtype=np.float64)
    committed = np.zeros((count, 9), dtype=np.float64)
    trial[:, 6] = rng.normal(size=count)
    trial[::17, 6] = 0.0
    trial[:, 7] = rng.normal(scale=1.0e-4, size=count)
    committed[:, 6] = rng.normal(size=count)
    di = rng.random(count)
    dj = 1.0 - di
    ecc = rng.normal(scale=0.3, size=count)
    lengths = rng.random(records) + 0.5
    starts = np.arange(records, dtype=np.int32) * springs_per_record
    stops = starts + springs_per_record
    constrained = (np.arange(records) % 2 == 0)

    expected = _finish_transverse_reference(
        trial, committed, di, dj, ecc, lengths, starts, stops, constrained
    )
    actual = (
        np.zeros((records, 6), dtype=np.float64),
        np.zeros(records, dtype=np.float64),
        np.zeros(records, dtype=np.float64),
        np.zeros(records, dtype=np.float64),
    )

    hb._finish_transverse_batch(
        trial,
        committed,
        di,
        dj,
        ecc,
        lengths,
        starts,
        stops,
        constrained,
        *actual,
    )

    for actual_array, expected_array in zip(actual, expected):
        np.testing.assert_array_equal(
            actual_array.view(np.uint64),
            expected_array.view(np.uint64),
        )
