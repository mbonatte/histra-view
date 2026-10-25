from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

import histra.solver.hysteretic_batch as batch
from histra.elements.interface import Interface
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.hysteretic import SpringHysteretic
from histra.types.afference_entry import AfferenceEntry
from histra.types.phase_enum import PhaseEnum
from histra.types.point import Point


def _hysteretic(seed: int, stiffness: float) -> SpringHysteretic:
    spring = SpringHysteretic(
        key=seed,
        k=stiffness,
        k_tang=0.75 * stiffness,
        e1p=stiffness,
        e1n=stiffness,
        e2p=0.1 * stiffness,
        e2n=0.1 * stiffness,
        betap=1.0,
        betan=0.0,
        tensile_curve_type="LinearSoftening",
        compressive_curve_type="LinearSoftening",
    )
    spring.revert_to_start()
    spring.umax[:] = [1.0e-4 * seed, -2.0e-4 * seed]
    spring._crot_pu = 3.0e-5 * seed
    spring._crot_nu = -4.0e-5 * seed
    spring.cenergy_d = 5.0e-3 * seed
    spring._cload_indicator = seed % 3
    spring._cstress = 0.25 * seed
    spring._cstrain = 2.0e-5 * seed
    spring.phase = PhaseEnum.Elastic
    spring.k_tang_committed = 0.75 * stiffness
    spring.revert_to_last_commit()
    spring.k_tang = spring.k_tang_committed
    spring.f = spring._cstress
    spring.u = spring._cstrain
    return spring


def _coulomb(seed: int, stiffness: float) -> SpringCoulomb03:
    spring = SpringCoulomb03(
        key=seed,
        k=stiffness,
        k_tang=0.8 * stiffness,
        e1p=stiffness,
        e1n=stiffness,
        e2p=0.05 * stiffness,
        e2n=0.05 * stiffness,
        hysteretic_type="Initial",
        sub_law="Coulomb",
        area=1.0 + 0.1 * seed,
        mu=0.35,
        cohesion=0.75,
    )
    spring.revert_to_start()
    spring.fy[:] = [1.2 + seed, -(1.2 + seed)]
    spring._cup = 1.0e-5 * seed
    spring._cstress = 0.4 * seed
    spring._cstrain = 3.0e-5 * seed
    spring._cstress_normal = -2.0 * seed
    spring._cstress_normal_prev = -1.5 * seed
    spring._ccontact_area = spring.area
    spring.cenergy_d = 2.0e-3 * seed
    spring.phase = PhaseEnum.Elastic
    spring.k_tang_committed = 0.8 * stiffness
    spring.revert_to_last_commit()
    spring.k_tang = spring.k_tang_committed
    spring.f = spring._cstress
    spring.u = spring._cstrain
    return spring


def _interface(key: int, gdl_offset: int) -> Interface:
    interface = Interface(
        key=key,
        length=2.0,
        thickness=[1.0, 1.0],
        nrow=2,
        ncol=2,
        nspring=4,
    )
    interface.vint2d = [
        Point(0.0, 0.0, 0.0),
        Point(2.0, 0.0, 0.0),
        Point(2.0, 1.0, 0.0),
        Point(0.0, 1.0, 0.0),
    ]
    interface.trasv_1 = [
        _hysteretic(100 * key + index + 1, 10.0 + key + index)
        for index in range(4)
    ]
    interface.slid = [_coulomb(1000 * key + 1, 20.0 + key)]
    interface.slid_out_plan = [
        _coulomb(1000 * key + 2, 30.0 + key),
        _coulomb(1000 * key + 3, 40.0 + key),
    ]
    for local_dof in range(12):
        interface.aff[local_dof] = [
            AfferenceEntry(gdl=gdl_offset + local_dof + 1, alfa=1.0)
        ]
    interface.status.u[:] = [1.0e-6 * (key + index) for index in range(12)]
    interface.status.normal_increment = 0.5 * key
    interface.status.committed_normal_force = -0.25 * key
    interface.status.max_spring_displacement = 1.0e-4 * key
    return interface


def _model() -> SimpleNamespace:
    first = _interface(1, 0)
    second = _interface(2, 12)
    return SimpleNamespace(
        gdl=24,
        collections=SimpleNamespace(
            interfaces={1: first, 2: second},
            quads={},
            materials={},
        ),
    )


def _replace_definition(interface: Interface, factor: float) -> None:
    transverse: list[SpringHysteretic] = []
    for old in interface.trasv_1:
        spring = deepcopy(old)
        spring.k *= factor
        spring.e1p *= factor
        spring.e1n *= factor
        spring.e2p *= factor
        spring.e2n *= factor
        transverse.append(spring)
    interface.trasv_1 = transverse

    slid: list[SpringCoulomb03] = []
    for old in interface.slid:
        spring = deepcopy(old)
        spring.k *= factor
        spring.e1p *= factor
        spring.e1n *= factor
        spring.e2p *= factor
        spring.e2n *= factor
        spring.cohesion *= 0.5
        slid.append(spring)
    interface.slid = slid

    out: list[SpringCoulomb03] = []
    for old in interface.slid_out_plan:
        spring = deepcopy(old)
        spring.k *= factor
        spring.e1p *= factor
        spring.e1n *= factor
        spring.e2p *= factor
        spring.e2n *= factor
        spring.mu *= 0.8
        out.append(spring)
    interface.slid_out_plan = out


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_incremental_material_update_matches_fresh_full_runtime_exactly() -> None:
    incremental_model = _model()
    full_model = deepcopy(incremental_model)
    incremental = batch.HystereticBatchRuntime(incremental_model)
    assert incremental._compact_simple_params is True
    assert incremental._compact_linear_params is True
    assert incremental._params.shape[1] == batch.LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE
    assert (
        incremental.params[0, batch.TENSILE_CURVE_TYPE_PARAM]
        == batch.TENSILE_LINEAR
    )

    persistent_arrays = {
        name: id(getattr(incremental, name))
        for name in (
            "params", "_params", "committed", "trial", "targets", "enabled",
            "coulomb_params", "coulomb_state", "coulomb_targets",
            "_di", "_dj", "_ecc", "_aff_offsets", "_aff_gdls",
            "_aff_coefficients", "_local_u", "_local_full_forces",
        )
    }
    unaffected_before = incremental._params[4:8].copy()
    unaffected_objects = tuple(incremental.springs[4:8])

    _replace_definition(incremental_model.collections.interfaces[1], 1.7)
    _replace_definition(full_model.collections.interfaces[1], 1.7)

    assert incremental.try_update_material_interfaces(
        [incremental_model.collections.interfaces[1]]
    ) is True
    rebuilt = batch.HystereticBatchRuntime(full_model)

    for name in (
        "params", "committed", "trial", "targets", "enabled",
        "_transverse_k", "coulomb_params", "coulomb_state",
        "coulomb_targets", "coulomb_dns", "coulomb_enabled",
        "_di", "_dj", "_ecc", "_record_index", "_starts", "_stops",
        "_dist", "_dist_for", "_aff_offsets", "_aff_gdls",
        "_aff_coefficients", "_local_u", "_local_full_forces",
        "_global_resisting_force", "_max_u_cache",
    ):
        np.testing.assert_array_equal(getattr(incremental, name), getattr(rebuilt, name))

    assert incremental._simple_hysteretic == rebuilt._simple_hysteretic
    assert tuple(incremental.springs[4:8]) == unaffected_objects
    np.testing.assert_array_equal(incremental._params[4:8], unaffected_before)
    for name, object_id in persistent_arrays.items():
        assert id(getattr(incremental, name)) == object_id


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_incremental_material_update_rejects_changed_transverse_layout_without_mutation() -> None:
    model = _model()
    runtime = batch.HystereticBatchRuntime(model)
    params_before = runtime.params.copy()
    springs_before = tuple(runtime.springs)

    interface = model.collections.interfaces[1]
    interface.trasv_1 = interface.trasv_1[:-1]

    assert runtime.try_update_material_interfaces([interface]) is False
    np.testing.assert_array_equal(runtime.params, params_before)
    assert tuple(runtime.springs) == springs_before


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_incremental_material_update_rejects_incompatible_coulomb_layout_without_mutation() -> None:
    model = _model()
    runtime = batch.HystereticBatchRuntime(model)
    state_before = runtime.coulomb_state.copy()
    springs_before = tuple(runtime.coulomb_springs)

    interface = model.collections.interfaces[1]
    replacement = deepcopy(interface.slid[0])
    replacement.hysteretic_type = "Takeda"
    interface.slid = [replacement]

    assert runtime.try_update_material_interfaces([interface]) is False
    np.testing.assert_array_equal(runtime.coulomb_state, state_before)
    assert tuple(runtime.coulomb_springs) == springs_before


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_incremental_material_update_rejects_unsupported_oop_alias_split() -> None:
    model = _model()
    interface = model.collections.interfaces[1]
    interface.slid_out_plan[1] = interface.slid_out_plan[0]
    runtime = batch.HystereticBatchRuntime(model)
    state_before = runtime.coulomb_state.copy()
    springs_before = tuple(runtime.coulomb_springs)

    first = deepcopy(interface.slid_out_plan[0])
    second = deepcopy(interface.slid_out_plan[0])
    second.hysteretic_type = "Takeda"
    interface.slid_out_plan = [first, second]

    assert runtime.try_update_material_interfaces([interface]) is False
    np.testing.assert_array_equal(runtime.coulomb_state, state_before)
    assert tuple(runtime.coulomb_springs) == springs_before


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_incremental_material_update_rejects_unsynchronized_object_state() -> None:
    model = _model()
    runtime = batch.HystereticBatchRuntime(model)
    params_before = runtime.params.copy()
    _replace_definition(model.collections.interfaces[1], 1.5)
    runtime._objects_trial_synced = False

    assert runtime.try_update_material_interfaces([model.collections.interfaces[1]]) is False
    np.testing.assert_array_equal(runtime.params, params_before)


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_compact_parameter_runtime_promotes_once_for_non_simple_material_update() -> None:
    model = _model()
    rebuilt_model = deepcopy(model)
    runtime = batch.HystereticBatchRuntime(model)
    assert runtime._compact_simple_params is True
    assert runtime._compact_linear_params is True
    assert runtime._params.shape[1] == batch.LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE

    persistent_ids = {
        name: id(getattr(runtime, name))
        for name in (
            "committed", "trial", "targets", "enabled", "_transverse_k",
            "coulomb_params", "coulomb_state", "_di", "_dj", "_ecc",
            "_aff_offsets", "_aff_gdls", "_aff_coefficients", "_local_u",
            "_local_full_forces",
        )
    }
    compact_params_id = id(runtime._params)

    interface = model.collections.interfaces[1]
    rebuilt_interface = rebuilt_model.collections.interfaces[1]
    replacement = [deepcopy(spring) for spring in interface.trasv_1]
    rebuilt_replacement = [deepcopy(spring) for spring in rebuilt_interface.trasv_1]
    replacement[0].pinch_xp = 0.2
    rebuilt_replacement[0].pinch_xp = 0.2
    interface.trasv_1 = replacement
    rebuilt_interface.trasv_1 = rebuilt_replacement

    assert runtime.try_update_material_interfaces([interface]) is True
    assert runtime._compact_simple_params is False
    assert runtime._params.shape[1] == batch.TRANSVERSE_PARAM_SIZE
    assert id(runtime._params) != compact_params_id

    rebuilt = batch.HystereticBatchRuntime(rebuilt_model)
    assert rebuilt._compact_simple_params is False
    for name in (
        "params", "committed", "trial", "targets", "enabled",
        "_transverse_k", "coulomb_params", "coulomb_state",
        "coulomb_targets", "coulomb_dns", "coulomb_enabled",
        "_di", "_dj", "_ecc", "_record_index", "_starts", "_stops",
        "_dist", "_dist_for", "_aff_offsets", "_aff_gdls",
        "_aff_coefficients", "_local_u", "_local_full_forces",
        "_global_resisting_force", "_max_u_cache",
    ):
        np.testing.assert_array_equal(getattr(runtime, name), getattr(rebuilt, name))

    for name, object_id in persistent_ids.items():
        assert id(getattr(runtime, name)) == object_id

    # A later non-simple material mutation reuses the already-promoted 33-column
    # matrix instead of allocating/rebuilding another full dense runtime.
    full_params_id = id(runtime._params)
    second = model.collections.interfaces[2]
    second_rebuilt = rebuilt_model.collections.interfaces[2]
    second_replacement = [deepcopy(spring) for spring in second.trasv_1]
    second_rebuilt_replacement = [deepcopy(spring) for spring in second_rebuilt.trasv_1]
    second_replacement[1].damfc1p = 0.15
    second_rebuilt_replacement[1].damfc1p = 0.15
    second.trasv_1 = second_replacement
    second_rebuilt.trasv_1 = second_rebuilt_replacement

    assert runtime.try_update_material_interfaces([second]) is True
    assert id(runtime._params) == full_params_id

    rebuilt_again = batch.HystereticBatchRuntime(rebuilt_model)
    for name in (
        "params", "committed", "trial", "targets", "enabled",
        "_transverse_k", "coulomb_params", "coulomb_state",
        "coulomb_targets", "coulomb_dns", "coulomb_enabled",
        "_local_u", "_local_full_forces", "_global_resisting_force",
    ):
        np.testing.assert_array_equal(
            getattr(runtime, name), getattr(rebuilt_again, name)
        )


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_force_general_uses_full_transverse_parameter_layout(monkeypatch) -> None:
    monkeypatch.setenv("HISTRA_FORCE_GENERAL_HYSTERETIC_BATCH", "1")
    runtime = batch.HystereticBatchRuntime(_model())

    assert runtime._compact_simple_params is False
    assert runtime._simple_hysteretic is False
    assert runtime._params.shape[1] == batch.TRANSVERSE_PARAM_SIZE

@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_repeated_incremental_material_updates_match_repeated_full_rebuilds() -> None:
    incremental_model = _model()
    full_model = deepcopy(incremental_model)
    incremental = batch.HystereticBatchRuntime(incremental_model)
    params_id = id(incremental._params)
    committed_id = id(incremental.committed)

    for key, factor in ((1, 1.2), (1, 0.85), (2, 1.4), (1, 1.1)):
        _replace_definition(incremental_model.collections.interfaces[key], factor)
        _replace_definition(full_model.collections.interfaces[key], factor)

        assert incremental.try_update_material_interfaces(
            [incremental_model.collections.interfaces[key]]
        ) is True
        rebuilt = batch.HystereticBatchRuntime(full_model)

        for name in (
            "params", "committed", "trial", "targets", "enabled",
            "_transverse_k", "coulomb_params", "coulomb_state",
            "coulomb_targets", "coulomb_dns", "coulomb_enabled",
            "_local_u", "_local_full_forces", "_global_resisting_force",
        ):
            np.testing.assert_array_equal(
                getattr(incremental, name), getattr(rebuilt, name)
            )
        assert id(incremental._params) == params_id
        assert id(incremental.committed) == committed_id


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_transverse_parameter_import_matches_scalar_attribute_reference_exactly() -> None:
    model = _model()
    runtime = batch.HystereticBatchRuntime(model)

    for index, spring in enumerate(runtime.springs):
        if runtime._compact_simple_params:
            expected = np.asarray(
                [float(getattr(spring, name)) for name in batch.SIMPLE_PARAM_NAMES],
                dtype=np.float64,
            )
            np.testing.assert_array_equal(
                runtime._params[index, : len(batch.SIMPLE_PARAM_NAMES)], expected
            )
        else:
            expected = np.asarray(
                [float(getattr(spring, name)) for name in batch._PARAM_NAMES],
                dtype=np.float64,
            )
            np.testing.assert_array_equal(
                runtime._params[index, : len(batch._PARAM_NAMES)], expected
            )


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_compact_runtime_preserves_legacy_logical_parameter_columns() -> None:
    model = _model()
    promoted = model.collections.interfaces[1].trasv_1[0]
    promoted.tensile_curve_type = "Exponential"

    runtime = batch.HystereticBatchRuntime(model)

    assert runtime._compact_simple_params is True
    assert runtime._params.shape[1] == batch.SIMPLE_TRANSVERSE_PARAM_SIZE
    assert runtime.params.shape[1] == batch.TRANSVERSE_PARAM_SIZE
    assert runtime.params[0, batch.TENSILE_CURVE_TYPE_PARAM] == batch.TENSILE_EXPONENTIAL
    assert (
        runtime._params[0, batch.SIMPLE_TENSILE_CURVE_TYPE_PARAM]
        == batch.TENSILE_EXPONENTIAL
    )

    expected = np.asarray(
        [float(getattr(promoted, name)) for name in batch._PARAM_NAMES]
        + [float(batch.TENSILE_EXPONENTIAL), 0.0],
        dtype=np.float64,
    )
    np.testing.assert_array_equal(runtime.params[0], expected)


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_parabolic_compression_uses_generic_compiled_state_machine_exactly() -> None:
    """The compiled path must retain the scalar parabolic backbone and history."""
    model = _model()
    spring = model.collections.interfaces[1].trasv_1[0]
    spring.tensile_curve_type = "LinearSoftening"
    spring.compressive_curve_type = "Parabolic"
    spring.rot1p, spring.mom1p = 0.01, 10.0
    spring.rot2p, spring.mom2p = 0.03, 12.0
    spring.rot3p, spring.mom3p = 0.05, 0.0
    spring.rot1n, spring.mom1n = -0.01, -10.0
    spring.rot2n, spring.mom2n = -0.05, -30.0
    spring.rot3n, spring.mom3n = -0.08, 0.0
    spring.e1p, spring.e1n = 1000.0, 1000.0
    spring.e2p, spring.e2n = 100.0, -500.0
    spring.e3p, spring.e3n = -600.0, 1000.0
    spring.eup, spring.eun = 1000.0, 1000.0
    spring.energy_a = 1.0
    spring.revert_to_start()
    spring.revert_to_last_commit()

    runtime = batch.HystereticBatchRuntime(model)
    assert runtime._compact_simple_params is False
    assert runtime._simple_hysteretic is False
    assert runtime.params[0, batch.COMPRESSIVE_CURVE_TYPE_PARAM] == batch.COMPRESSIVE_PARABOLIC

    # Envelope, post-peak loading, compression unloading and a reversal all
    # exercise the generic compiled state machine rather than only a formula.
    for target in (-0.005, -0.02, -0.06, -0.03, 0.002):
        spring.set_trial_strain(target)
        runtime.targets[0] = target
        runtime.evaluate()
        expected_trial = np.asarray(
            [
                spring._trot_max,
                spring._trot_min,
                spring._trot_pu,
                spring._trot_nu,
                spring._tenergy_d,
                spring._tload_indicator,
                spring._tstress,
                spring._tstrain,
                spring.t_phase,
                spring.k_tang,
            ],
            dtype=np.float64,
        )
        np.testing.assert_allclose(runtime.trial[0], expected_trial, rtol=0.0, atol=1.0e-12)
        spring.commit()
        runtime.committed[0, :] = runtime.trial[0, :9]


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_parabolic_material_update_promotes_compact_runtime_and_keeps_coverage() -> None:
    incremental_model = _model()
    rebuilt_model = deepcopy(incremental_model)
    incremental = batch.HystereticBatchRuntime(incremental_model)
    assert incremental._compact_simple_params is True

    for model in (incremental_model, rebuilt_model):
        for spring in model.collections.interfaces[1].trasv_1:
            spring.compressive_curve_type = "Parabolic"

    assert incremental.try_update_material_interfaces(
        [incremental_model.collections.interfaces[1]]
    ) is True
    rebuilt = batch.HystereticBatchRuntime(rebuilt_model)

    assert incremental._compact_simple_params is False
    assert incremental._simple_hysteretic is False
    np.testing.assert_array_equal(incremental.params, rebuilt.params)
    np.testing.assert_array_equal(incremental.committed, rebuilt.committed)
    assert np.all(
        incremental.params[:4, batch.COMPRESSIVE_CURVE_TYPE_PARAM]
        == batch.COMPRESSIVE_PARABOLIC
    )


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_compact_simple_parameter_layout_is_bit_exact_with_full_layout() -> None:
    full = np.zeros((1, batch.TRANSVERSE_PARAM_SIZE), dtype=np.float64)
    full[0, 8] = 1.0  # BetaP; all other simple-law discriminator values are zero.
    full[0, 10:30] = np.asarray(
        [
            0.01, 10.0, 0.03, 6.0, 0.05, 0.0,
            -10.0, -0.01, -0.03, -6.0, -0.05, 0.0,
            1000.0, 1000.0, -200.0, -200.0,
            -120.0, -120.0, 800.0, 800.0,
        ],
        dtype=np.float64,
    )
    full[0, batch.TENSILE_CURVE_TYPE_PARAM] = batch.TENSILE_LINEAR
    compact = np.empty((1, batch.SIMPLE_TRANSVERSE_PARAM_SIZE), dtype=np.float64)
    compact[0, : len(batch.SIMPLE_PARAM_NAMES)] = full[0, 10:30]
    compact[0, batch.SIMPLE_TENSILE_CURVE_TYPE_PARAM] = batch.TENSILE_LINEAR
    linear_compact = compact[:, :batch.LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE].copy()

    committed_full = np.zeros((1, 9), dtype=np.float64)
    trial_full = np.zeros((1, 10), dtype=np.float64)
    committed_compact = committed_full.copy()
    committed_linear_compact = committed_full.copy()
    trial_compact = trial_full.copy()
    trial_linear_compact = trial_full.copy()
    targets_full = np.zeros(1, dtype=np.float64)
    targets_compact = np.zeros(1, dtype=np.float64)
    enabled = np.ones(1, dtype=np.bool_)

    for target in (0.005, 0.02, 0.008, -0.018, -0.004, 0.025):
        targets_full[0] = target
        targets_compact[0] = target
        batch._evaluate_simple_linear_batch(
            full, committed_full, trial_full, targets_full, enabled
        )
        batch._evaluate_simple_linear_batch(
            compact, committed_compact, trial_compact, targets_compact, enabled
        )
        batch._evaluate_simple_linear_batch(
            linear_compact,
            committed_linear_compact,
            trial_linear_compact,
            targets_compact,
            enabled,
        )
        np.testing.assert_array_equal(trial_compact, trial_full)
        np.testing.assert_array_equal(trial_linear_compact, trial_full)

        # Commit exactly the dense fields copied by HystereticBatchRuntime.
        committed_full[0, :] = trial_full[0, :9]
        committed_compact[0, :] = trial_compact[0, :9]
        committed_linear_compact[0, :] = trial_linear_compact[0, :9]

@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_incremental_material_update_rebuilds_only_coulomb_storage_when_oop_alias_splits() -> None:
    incremental_model = _model()
    rebuilt_model = deepcopy(incremental_model)

    # Fixed/restraint-style interfaces can reference the same Coulomb object in
    # both out-of-plane positions. Soil replacement creates two independent
    # springs. This identity-topology change must not force a 550k-row
    # transverse runtime rebuild.
    for model in (incremental_model, rebuilt_model):
        interface = model.collections.interfaces[1]
        interface.slid_out_plan[1] = interface.slid_out_plan[0]

    runtime = batch.HystereticBatchRuntime(incremental_model)
    transverse_ids = {
        name: id(getattr(runtime, name))
        for name in (
            "_params", "committed", "trial", "targets", "enabled",
            "_transverse_k", "_di", "_dj", "_ecc", "_record_index",
            "_starts", "_stops", "_aff_offsets", "_aff_gdls",
            "_aff_coefficients", "_local_u", "_local_full_forces",
        )
    }
    transverse_before = {
        name: np.asarray(getattr(runtime, name)).copy()
        for name in ("_params", "committed", "trial", "targets", "enabled", "_transverse_k")
    }

    _replace_definition(incremental_model.collections.interfaces[1], 1.7)
    _replace_definition(rebuilt_model.collections.interfaces[1], 1.7)
    assert (
        incremental_model.collections.interfaces[1].slid_out_plan[0]
        is not incremental_model.collections.interfaces[1].slid_out_plan[1]
    )

    assert runtime.try_update_material_interfaces(
        [incremental_model.collections.interfaces[1]]
    ) is True
    rebuilt = batch.HystereticBatchRuntime(rebuilt_model)

    # The expensive transverse/geometry storage survives the alias split.
    for name, object_id in transverse_ids.items():
        assert id(getattr(runtime, name)) == object_id

    # The changed interface's transverse rows are imported in place, while the
    # unaffected rows and all runtime topology stay exact.
    for name in (
        "_params", "committed", "trial", "targets", "enabled", "_transverse_k",
        "coulomb_params", "coulomb_state", "coulomb_targets", "coulomb_dns",
        "coulomb_enabled", "_slid_index", "_oop0_index", "_oop1_index",
    ):
        np.testing.assert_array_equal(getattr(runtime, name), getattr(rebuilt, name))

    np.testing.assert_array_equal(runtime._params[4:8], transverse_before["_params"][4:8])
    np.testing.assert_array_equal(runtime.committed[4:8], transverse_before["committed"][4:8])
    np.testing.assert_array_equal(runtime.trial[4:8], transverse_before["trial"][4:8])


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_coulomb_topology_rebuild_reimports_only_changed_record_objects(monkeypatch) -> None:
    model = _model()
    changed = model.collections.interfaces[1]
    changed.slid_out_plan[1] = changed.slid_out_plan[0]
    runtime = batch.HystereticBatchRuntime(model)

    # Force a topology split using fresh compatible objects, matching the
    # fixed-restraint -> soil transition used by scour material replacement.
    _replace_definition(changed, 1.7)
    calls: list[int] = []
    original = runtime._read_coulomb_object

    def counted(index: int, spring: SpringCoulomb03) -> None:
        calls.append(id(spring))
        original(index, spring)

    monkeypatch.setattr(runtime, "_read_coulomb_object", counted)
    assert runtime.try_update_material_interfaces([changed]) is True

    # All three Coulomb objects on the changed record are authoritative and
    # re-imported. The three untouched objects on interface 2 are copied from
    # synchronized dense storage rather than traversed through Python again.
    assert calls == [id(changed.slid[0]), *(id(s) for s in changed.slid_out_plan)]

@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_bulk_initial_transverse_import_matches_scalar_rows_exactly() -> None:
    model = _model()
    runtime = batch.HystereticBatchRuntime(model)
    expected = {
        name: np.asarray(getattr(runtime, name)).copy()
        for name in (
            "_params", "committed", "trial", "targets", "enabled", "_transverse_k"
        )
    }

    runtime._params.fill(np.nan)
    runtime.committed.fill(np.nan)
    runtime.trial.fill(np.nan)
    runtime.targets.fill(np.nan)
    runtime.enabled.fill(False)
    runtime._transverse_k.fill(np.nan)
    for index, spring in enumerate(runtime.springs):
        runtime._read_transverse_object(index, spring)

    for name, values in expected.items():
        np.testing.assert_array_equal(getattr(runtime, name), values)
