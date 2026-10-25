from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.solver.hysteretic_batch import (
    TENSILE_CURVE_TYPE_PARAM,
    TENSILE_EXPONENTIAL,
    TRANSVERSE_PARAM_SIZE,
    _PARAM_NAMES,
    _evaluate_linear_batch,
    _evaluate_simple_linear_batch,
    _pos_rotlim_typed,
    build_hysteretic_batch,
)
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.hysteretic import SpringHysteretic
from histra.types.phase_enum import PhaseEnum


MODEL = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"
pytestmark = pytest.mark.skipif(
    _evaluate_linear_batch is None, reason="Numba is unavailable"
)


def _enable_production_batch(monkeypatch) -> None:
    for name in (
        "HISTRA_DISABLE_COMPILED_SPRINGS",
        "HISTRA_DISABLE_COMPILED_QUADS",
        "HISTRA_FORCE_GENERAL_HYSTERETIC_BATCH",
    ):
        monkeypatch.delenv(name, raising=False)


def _make_exponential_spring(*, damage_and_pinching: bool = False) -> SpringHysteretic:
    spring = SpringHysteretic()
    spring.k = 1_000.0
    spring.tensile_curve_type = "Exponential"
    spring.compressive_curve_type = "LinearSoftening"

    spring.rot1p = 0.01
    spring.mom1p = 10.0
    spring.rot2p = 0.05
    spring.mom2p = 0.0
    spring.rot3p = 0.05
    spring.mom3p = 0.0
    spring.e1p = 1_000.0
    spring.e2p = 0.0
    spring.e3p = 0.0
    spring.eup = 1_000.0

    spring.rot1n = -0.01
    spring.mom1n = -10.0
    spring.rot2n = -0.03
    spring.mom2n = -5.0
    spring.rot3n = -0.05
    spring.mom3n = 0.0
    spring.e1n = 1_000.0
    spring.e2n = -250.0
    spring.e3n = -250.0
    spring.eun = 1_000.0

    if damage_and_pinching:
        spring.pinch_xp = 0.25
        spring.pinch_yp = 0.40
        spring.pinch_xn = 0.30
        spring.pinch_yn = 0.50
        spring.damfc1p = 0.05
        spring.damfc2p = 0.02
        spring.damfc1n = 0.04
        spring.damfc2n = 0.01
        spring.betap = 1.0
        spring.betan = 0.5
        spring.energy_a = 100.0
    else:
        spring.betap = 1.0
        spring.betan = 0.0
        spring.energy_a = 100.0

    spring.is_on = True
    spring.revert_to_start()
    spring.revert_to_last_commit()
    return spring


def _trial_state(spring: SpringHysteretic) -> np.ndarray:
    return np.asarray(
        [
            spring._trot_max,
            spring._trot_min,
            spring._trot_pu,
            spring._trot_nu,
            spring._tenergy_d,
            spring._tload_indicator,
            spring._tstress,
            spring._tstrain,
            int(spring.t_phase),
            spring.k_tang,
        ],
        dtype=np.float64,
    )


class _DenseSpring:
    def __init__(self, spring: SpringHysteretic, evaluator) -> None:
        self.scalar = spring
        self.evaluator = evaluator
        self.params = np.empty((1, TRANSVERSE_PARAM_SIZE), dtype=np.float64)
        self.params[0, :len(_PARAM_NAMES)] = [
            float(getattr(spring, name)) for name in _PARAM_NAMES
        ]
        self.params[0, TENSILE_CURVE_TYPE_PARAM] = TENSILE_EXPONENTIAL
        self.committed = np.asarray(
            [[
                spring.umax[0],
                spring.umax[1],
                spring._crot_pu,
                spring._crot_nu,
                spring.cenergy_d,
                spring._cload_indicator,
                spring._cstress,
                spring._cstrain,
                int(spring.phase),
            ]],
            dtype=np.float64,
        )
        self.trial = _trial_state(spring).reshape(1, -1)
        self.targets = np.asarray([spring._tstrain], dtype=np.float64)
        self.enabled = np.asarray([True], dtype=np.bool_)

    def trial_at(self, target: float) -> None:
        self.targets[0] = target
        self.evaluator(
            self.params, self.committed, self.trial, self.targets, self.enabled
        )
        self.scalar.set_trial_strain(target)
        expected = _trial_state(self.scalar)
        np.testing.assert_allclose(
            self.trial[0, :8], expected[:8], rtol=2.0e-14, atol=2.0e-14
        )
        assert int(self.trial[0, 8]) == int(expected[8])
        assert self.trial[0, 9] == pytest.approx(
            expected[9], rel=2.0e-14, abs=2.0e-14
        )

    def commit(self) -> None:
        self.scalar.commit()
        self.committed[0, :] = self.trial[0, :9]

    def revert_to_last_commit(self) -> None:
        self.scalar.revert_to_last_commit()
        self.trial[0, :9] = self.committed[0, :]
        self.targets[0] = self.committed[0, 7]
        np.testing.assert_allclose(
            self.trial[0, :9], _trial_state(self.scalar)[:9], rtol=0.0, atol=0.0
        )


@pytest.mark.parametrize(
    "evaluator", [_evaluate_linear_batch, _evaluate_simple_linear_batch]
)
def test_exponential_virgin_loading_uses_csharp_envelope_and_secant(
    evaluator,
) -> None:
    dense = _DenseSpring(_make_exponential_spring(), evaluator)

    dense.trial_at(0.005)
    assert dense.trial[0, 6] == pytest.approx(5.0)
    assert dense.trial[0, 9] == pytest.approx(1_000.0)
    assert int(dense.trial[0, 8]) == int(PhaseEnum.Elastic)

    for target in (0.03, 0.075):
        dense.trial_at(target)
        expected_stress = 10.0 * np.exp(
            -(target - 0.01) / (0.05 - 0.01)
        )
        assert dense.trial[0, 6] == pytest.approx(expected_stress)
        assert dense.trial[0, 9] == pytest.approx(expected_stress / target)
        assert int(dense.trial[0, 8]) == int(PhaseEnum.Plastic_t)


def test_exponential_positive_zero_stress_rotation_is_unbounded() -> None:
    limit = _pos_rotlim_typed(
        TENSILE_EXPONENTIAL,
        0.03,
        0.01,
        10.0,
        0.05,
        0.0,
        -250.0,
        0.0,
        0.05,
        0.0,
        1_000.0,
    )
    assert np.isinf(limit)


@pytest.mark.parametrize(
    "evaluator", [_evaluate_linear_batch, _evaluate_simple_linear_batch]
)
def test_multiple_exponential_trials_and_newton_retrials_match_scalar(
    evaluator,
) -> None:
    dense = _DenseSpring(_make_exponential_spring(), evaluator)

    for target in (0.015, 0.025, 0.040):
        dense.trial_at(target)

    dense.trial_at(0.020)
    dense.commit()
    for target in (0.030, 0.024, 0.035, 0.028):
        # No commit between these calls: each is a new Newton trial from the
        # same committed state, exactly like SpringHysteretic.set_trial_strain.
        dense.trial_at(target)


@pytest.mark.parametrize(
    "evaluator", [_evaluate_linear_batch, _evaluate_simple_linear_batch]
)
def test_exponential_unload_reverse_and_reload_match_scalar(evaluator) -> None:
    dense = _DenseSpring(_make_exponential_spring(), evaluator)

    dense.trial_at(0.030)
    dense.commit()
    dense.trial_at(0.015)  # unloading from the exponential branch
    dense.commit()
    dense.trial_at(-0.018)  # reversal into linear-softening compression
    dense.commit()
    dense.trial_at(0.022)  # reload into exponential tension


def test_exponential_damage_and_pinching_history_matches_scalar() -> None:
    dense = _DenseSpring(
        _make_exponential_spring(damage_and_pinching=True),
        _evaluate_linear_batch,
    )

    for target in (0.030, 0.012, -0.020, -0.008, 0.028, 0.006, -0.025, 0.032):
        dense.trial_at(target)
        dense.commit()


@pytest.mark.parametrize(
    "evaluator", [_evaluate_linear_batch, _evaluate_simple_linear_batch]
)
def test_exponential_commit_and_revert_to_last_commit_match_scalar(
    evaluator,
) -> None:
    dense = _DenseSpring(_make_exponential_spring(), evaluator)

    dense.trial_at(0.026)
    dense.commit()
    committed = dense.committed.copy()
    dense.trial_at(0.041)
    assert not np.array_equal(dense.trial[0, :9], committed[0])
    dense.revert_to_last_commit()
    np.testing.assert_array_equal(dense.committed, committed)
    dense.trial_at(0.031)


def _compatible_coulomb_springs(interface) -> list[SpringCoulomb03]:
    candidates = []
    if interface.slid:
        candidates.append(interface.slid[0])
    if len(interface.slid_out_plan) >= 2:
        candidates.extend(
            (interface.slid_out_plan[0], interface.slid_out_plan[1])
        )
    return [
        spring
        for spring in candidates
        if isinstance(spring, SpringCoulomb03)
        and spring.hysteretic_type == "Initial"
        and spring.sub_law == "Coulomb"
        and not spring.check_contact_area
    ]


def _is_promotable_reference_spring(spring) -> bool:
    return (
        isinstance(spring, SpringHysteretic)
        and spring.tensile_curve_type
        in {"LinearHardening", "LinearSoftening", "Exponential"}
        and spring.compressive_curve_type
        in {"LinearHardening", "LinearSoftening"}
        and np.isfinite(spring.rot1p)
        and np.isfinite(spring.rot2p)
        and np.isfinite(spring.mom1p)
        and np.isfinite(spring.e1p)
        and spring.rot1p > 0.0
        and spring.rot2p > spring.rot1p
        and spring.mom1p > 0.0
    )


def _reference_hrx_exponential_fixture():
    """Return a fresh HRX model with one real spring using exponential tension.

    The checked-in reference HRX currently generates only linear tensile
    envelopes.  Requiring a naturally exponential spring therefore tests an
    accidental fixture property rather than batch support.  Select an actual
    generated interface that is already eligible for the complete transverse,
    Coulomb and Quad batch path, then change only the tensile-law discriminator
    of one of its real springs.  Geometry, calibration parameters, connectivity
    and all dependent records remain those produced from the reference HRX.
    """
    selector_model = load_model(MODEL)
    selector_runtime = build_hysteretic_batch(selector_model)
    assert selector_runtime is not None

    interface_keys = {
        id(interface): key
        for key, interface in selector_model.collections.interfaces.items()
    }
    quad_edge_records = {
        int(index) for index in selector_runtime._quad_edge_records.tolist()
    }

    selected = None
    for record_index, record in enumerate(selector_runtime.records):
        if record_index not in quad_edge_records:
            continue
        interface = record.interface
        compatible_coulomb = _compatible_coulomb_springs(interface)
        if not compatible_coulomb:
            continue
        for spring_index, spring in enumerate(interface.trasv_1):
            if _is_promotable_reference_spring(spring):
                selected = (
                    interface_keys[id(interface)],
                    spring_index,
                    len(compatible_coulomb),
                )
                break
        if selected is not None:
            break

    assert selected is not None, (
        "Reference HRX contains no batch-compatible real interface with a "
        "promotable transverse spring, compatible Coulomb spring and managed "
        "Quad dependency"
    )

    interface_key, spring_index, expected_coulomb_count = selected
    model = load_model(MODEL)
    interface = model.collections.interfaces[interface_key]
    spring = interface.trasv_1[spring_index]
    assert _is_promotable_reference_spring(spring)

    spring.tensile_curve_type = "Exponential"
    spring.revert_to_start()
    spring.revert_to_last_commit()
    return model, interface, spring, expected_coulomb_count


def test_reference_hrx_exponential_springs_are_managed_and_match_scalar(
    monkeypatch,
) -> None:
    _enable_production_batch(monkeypatch)
    model, exponential_interface, promoted_spring, expected_coulomb_count = (
        _reference_hrx_exponential_fixture()
    )

    runtime = build_hysteretic_batch(model)
    assert runtime is not None
    assert id(exponential_interface) in runtime.interface_ids

    promoted_indices = [
        index
        for index, spring in enumerate(runtime.springs)
        if spring is promoted_spring
    ]
    assert len(promoted_indices) == 1
    promoted_index = promoted_indices[0]
    assert runtime.params[promoted_index, TENSILE_CURVE_TYPE_PARAM] == (
        TENSILE_EXPONENTIAL
    )
    assert promoted_spring._histra_batch_managed

    record_index = next(
        index
        for index, record in enumerate(runtime.records)
        if record.interface is exponential_interface
    )

    compatible_coulomb = _compatible_coulomb_springs(exponential_interface)
    assert len(compatible_coulomb) == expected_coulomb_count
    assert all(
        getattr(spring, "_histra_batch_managed", False)
        for spring in compatible_coulomb
    )

    assert runtime._quad_edge_records.size
    assert record_index in {
        int(index) for index in runtime._quad_edge_records.tolist()
    }, "No managed Quad depends on the promoted exponential interface"

    # Exercise the real generated spring independently against the authoritative
    # scalar object state machine.
    real = deepcopy(promoted_spring)
    evaluator = (
        _evaluate_simple_linear_batch
        if runtime._simple_hysteretic
        else _evaluate_linear_batch
    )
    dense = _DenseSpring(real, evaluator)
    for factor in (0.8, 1.2, 1.8, 0.6, -0.5, 1.4):
        target = factor * (real.rot1p if factor >= 0.0 else abs(real.rot1n))
        dense.trial_at(target)
        dense.commit()


def test_reference_hrx_snapshot_restore_and_object_sync_for_exponential(
    monkeypatch,
) -> None:
    _enable_production_batch(monkeypatch)
    model, _, promoted_spring, _ = _reference_hrx_exponential_fixture()
    runtime = build_hysteretic_batch(model)
    assert runtime is not None

    promoted_indices = np.asarray(
        [
            index
            for index, spring in enumerate(runtime.springs)
            if spring is promoted_spring
        ],
        dtype=np.int64,
    )
    assert promoted_indices.size == 1

    snapshot = runtime.snapshot()
    runtime.targets[:] = runtime.committed[:, 7]
    runtime.targets[promoted_indices] = np.asarray(
        [1.5 * promoted_spring.rot1p], dtype=np.float64
    )
    runtime.evaluate()
    assert np.any(
        runtime.trial[promoted_indices, 7]
        != snapshot[1][promoted_indices, 7]
    )

    runtime.restore(snapshot)
    restored = runtime.snapshot()
    for expected, actual in zip(snapshot, restored):
        np.testing.assert_array_equal(actual, expected)

    runtime.sync_all_to_objects()
    index = int(promoted_indices[0])
    spring = runtime.springs[index]
    assert spring._tstress == runtime.trial[index, 6]
    assert spring._tstrain == runtime.trial[index, 7]
    assert int(spring.t_phase) == int(runtime.trial[index, 8])
    assert spring.k_tang == runtime.trial[index, 9]


def test_spring_repr_and_batch_lifecycle() -> None:
    from histra.io.hr_loader import load_model
    from histra.solver.model_manager import ModelManager
    from histra.springs.elastic import SpringElastic

    spring = SpringElastic()
    assert repr(spring)

    model = load_model(MODEL)
    ModelManager.prepare_model(model)
    batch = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
    assert batch is not None

    for interface in model.collections.interfaces.values():
        springs = (
            list(interface.trasv_1)
            + list(interface.trasv_2)
            + list(interface.slid)
            + list(interface.slid_out_plan)
        )
        for spring in springs:
            assert repr(spring)

    for quad in model.collections.quads.values():
        if quad.spring:
            assert repr(quad.spring)

    ModelManager.clear_hysteretic_batch()

    for interface in model.collections.interfaces.values():
        springs = (
            list(interface.trasv_1)
            + list(interface.trasv_2)
            + list(interface.slid)
            + list(interface.slid_out_plan)
        )
        for spring in springs:
            assert repr(spring)
            assert not spring._histra_batch_managed

    for quad in model.collections.quads.values():
        if quad.spring:
            assert repr(quad.spring)
