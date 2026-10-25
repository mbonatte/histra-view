from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

import histra.solver.hysteretic_batch as batch
from histra.io.hr_loader import load_model
from histra.solver.hysteretic_batch import (
    _evaluate_linear_batch,
    build_hysteretic_batch,
)
from histra.solver.model_manager import ModelManager
from histra.springs.elastic import SpringElastic

MODEL = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"
ELASTIC_QUAD_MODEL = (
    Path(__file__).resolve().parents[2]
    / "my_model" / "benchmark_3_Pdelta" / "benchmark_virgin.hrx"
)


@pytest.mark.skipif(_evaluate_linear_batch is None, reason="Numba is unavailable")
def test_compiled_hysteretic_batch_matches_scalar_state_machine(monkeypatch):
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL)
    runtime = build_hysteretic_batch(model)
    assert runtime is not None
    scalar = [deepcopy(spring) for spring in runtime.springs]

    rot_p = np.asarray([spring.rot1p for spring in scalar])
    rot_n = np.asarray([spring.rot1n for spring in scalar])
    history = (
        0.8 * rot_p,
        1.2 * rot_p,
        0.4 * rot_p,
        0.5 * rot_n,
        1.1 * rot_n,
        -0.2 * rot_n,
    )

    for targets in history:
        runtime.targets[:] = targets
        runtime.evaluate()
        for index, (spring, target) in enumerate(zip(scalar, targets)):
            spring.set_trial_strain(float(target))
            expected = np.asarray(
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
                dtype=float,
            )
            np.testing.assert_array_equal(runtime.trial[index], expected)
        for spring in scalar:
            spring.commit()
        runtime.commit()


@pytest.mark.skipif(batch.njit is None, reason="Numba is unavailable")
def test_compiled_quad_reload_tangents_use_csharp_minimum():
    """The dense Takeda path must not bypass SpringCoulomb03 getters."""
    row = np.zeros(batch.QUAD_STATE_SIZE, dtype=np.float64)
    params = np.zeros(batch.QUAD_PARAM_SIZE, dtype=np.float64)
    params[batch.QPK] = 10_000.0
    params[batch.QPE3P] = -100.0
    params[batch.QPE3N] = -100.0

    # C# stores the raw values, but every read returns max(0.0001*K, value).
    row[batch.QTANG_RELOAD_T] = 0.0
    row[batch.QTANG_RELOAD_C] = 0.0
    assert batch._quad_tangent_reload_t(row, params) == 1.0
    assert batch._quad_tangent_reload_c(row, params) == 1.0

    # Exercise the same compression branch that failed in the scalar path.
    row[batch.QTPHASE] = batch.RELOAD_C
    row[batch.QTROT_PU] = 0.0
    row[batch.QMOM1N] = -100.0
    row[batch.QROT3N] = -1.0
    yn = batch._quad_yield_compression(
        row, params, batch.ELASTIC, -1.0e-6
    )
    assert np.isfinite(yn)
    assert yn == pytest.approx(-100.0 / 101.0)

    # Exercise the symmetric tension branch.
    row[batch.QTPHASE] = batch.RELOAD_T
    row[batch.QTROT_NU] = 0.0
    row[batch.QMOM1P] = 100.0
    row[batch.QROT3P] = 1.0
    yp = batch._quad_yield_tension(
        row, params, batch.ELASTIC, 1.0e-6
    )
    assert np.isfinite(yp)
    assert yp == pytest.approx(100.0 / 101.0)

@pytest.mark.skipif(_evaluate_linear_batch is None, reason="Numba is unavailable")
def test_compiled_hysteretic_batch_can_force_general_kernel(monkeypatch):
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    monkeypatch.setenv("HISTRA_FORCE_GENERAL_HYSTERETIC_BATCH", "1")
    model = load_model(MODEL)
    runtime = build_hysteretic_batch(model)
    assert runtime is not None
    assert runtime._simple_hysteretic is False


@pytest.mark.skipif(_evaluate_linear_batch is None, reason="Numba is unavailable")
def test_managed_interface_batches_elastic_sliding_exactly(monkeypatch):
    """Dense elastic sliding must match scalar trial/commit/restore state."""
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    model = load_model(MODEL)
    interface = next(iter(model.collections.interfaces.values()))

    def committed_elastic(stiffness: float, strain: float) -> SpringElastic:
        spring = SpringElastic(k=stiffness, k_tang=stiffness)
        spring.set_trial_strain(strain)
        spring.commit()
        return spring

    interface.slid = [committed_elastic(17.0, 0.03)]
    interface.slid_out_plan = [
        committed_elastic(19.0, -0.02),
        committed_elastic(23.0, 0.01),
    ]
    reference = deepcopy(interface)
    runtime = build_hysteretic_batch(model)
    assert runtime is not None
    assert runtime.manages(interface)
    record_index = runtime._record_by_id[id(interface)]
    assert runtime._slid_index[record_index] >= 0
    assert runtime._oop0_index[record_index] >= 0
    assert runtime._oop1_index[record_index] >= 0
    counts = runtime.performance_counts()
    assert counts["managed_interface_elastic_springs"] == 3
    assert runtime._unmanaged_sliding_record_indices.size == 0

    def assert_sliding_state_equal(actual, expected) -> None:
        actual_springs = [*actual.slid, *actual.slid_out_plan]
        expected_springs = [*expected.slid, *expected.slid_out_plan]
        for actual_spring, expected_spring in zip(
            actual_springs, expected_springs, strict=True
        ):
            assert actual_spring._cstress == expected_spring._cstress
            assert actual_spring._cstrain == expected_spring._cstrain
            assert actual_spring._tstress == expected_spring._tstress
            assert actual_spring._tstrain == expected_spring._tstrain
            assert actual_spring.k_tang == expected_spring.k_tang
            assert actual_spring.f == expected_spring.f
            assert actual_spring.u == expected_spring.u

    # The restored/initial resisting force must already include all three
    # scalar springs before any new displacement is applied.
    reference.set_resisting_force()
    np.testing.assert_array_equal(runtime.local_force_for(interface), reference.f)

    increment = np.linspace(-2.0e-5, 3.0e-5, int(model.gdl))
    state = type("State", (), {"step": 1})()
    runtime.update_domain(increment, state)
    reference.update_domain(increment, state)
    reference.set_resisting_force()

    np.testing.assert_allclose(
        runtime.local_force_for(interface), reference.f, rtol=0.0, atol=2.0e-15
    )
    runtime.sync_interface_trial_to_objects(interface)
    assert_sliding_state_equal(interface, reference)

    runtime.commit(sync_objects=True)
    reference.commit()
    assert_sliding_state_equal(interface, reference)

    reversal = -2.5 * increment
    runtime.update_domain(reversal, state)
    reference.update_domain(reversal, state)
    reference.set_resisting_force()
    np.testing.assert_allclose(
        runtime.local_force_for(interface), reference.f, rtol=0.0, atol=2.0e-15
    )

    snapshot = runtime.snapshot()
    reference_snapshot = deepcopy(reference)
    runtime.update_domain(0.75 * increment, state)
    runtime.restore(snapshot)
    reference_snapshot.set_resisting_force()
    np.testing.assert_allclose(
        runtime.local_force_for(interface),
        reference_snapshot.f,
        rtol=0.0,
        atol=2.0e-15,
    )
    assert_sliding_state_equal(interface, reference_snapshot)


@pytest.mark.skipif(_evaluate_linear_batch is None, reason="Numba is unavailable")
def test_compiled_hysteretic_batch_can_disable_quad_batch(monkeypatch):
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    monkeypatch.setenv("HISTRA_DISABLE_COMPILED_QUADS", "1")
    model = load_model(MODEL)
    runtime = build_hysteretic_batch(model)
    assert runtime is not None
    assert runtime.quad_records == []
    assert len(runtime.unmanaged_quads) == len(model.collections.quads)
    assert runtime._quad_local_du.shape == (0, 7)
    assert runtime._quad_local_u.shape == (0, 7)
    assert runtime._quad_edge_areas.shape == (0, 4)

    # Numba type-checks the complete fused kernel, including the Quad branch,
    # even though there are no managed Quads. Exercise the interface-only
    # update to ensure every empty Quad array retains its production rank.
    runtime.update_domain(
        np.zeros(int(model.gdl), dtype=np.float64),
        type("State", (), {"step": 1})(),
    )


@pytest.mark.skipif(
    _evaluate_linear_batch is None or not ELASTIC_QUAD_MODEL.exists(),
    reason="Numba or Benchmark 3 is unavailable",
)
def test_compiled_elastic_quads_match_scalar_force_exactly(monkeypatch):
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_SPRINGS", raising=False)
    monkeypatch.delenv("HISTRA_DISABLE_COMPILED_QUADS", raising=False)
    model = load_model(ELASTIC_QUAD_MODEL)
    ModelManager.prepare_model(model)
    runtime = build_hysteretic_batch(model)
    assert runtime is not None
    assert len(runtime.quad_records) == len(model.collections.quads) == 260
    assert runtime.unmanaged_quads == ()

    x = np.linspace(-1.0e-7, 1.0e-7, int(model.gdl), dtype=np.float64)
    initial_u = runtime._quad_local_u.copy()
    runtime.update_domain(x, type("State", (), {"step": 2})())

    quad_max_value, quad_max_key = runtime.cached_quad_max_u()
    expected_quad_index = int(np.argmax(np.abs(runtime._quad_local_u)) // 7)
    assert quad_max_value == np.max(np.abs(runtime._quad_local_u))
    assert quad_max_key == runtime.quad_records[expected_quad_index].key

    for index, quad in enumerate(runtime.quad_records):
        local_increment = np.asarray(
            [
                sum(x[entry.gdl - 1] * entry.alfa for entry in entries)
                for entries in quad.aff[:7]
            ],
            dtype=np.float64,
        )
        np.testing.assert_array_equal(
            runtime._quad_local_u[index], initial_u[index] + local_increment
        )
        expected_strain = (
            quad.d_alfa_2d_diag() * runtime._quad_local_u[index, 6]
        )
        assert runtime.quad_state[index, batch.QTSTRAIN] == expected_strain
        assert runtime.quad_state[index, batch.QTSTRESS] == (
            quad.spring.k * expected_strain
        )

def test_compiled_hysteretic_batch_can_be_disabled(monkeypatch):
    monkeypatch.setenv("HISTRA_DISABLE_COMPILED_SPRINGS", "1")
    model = load_model(MODEL)
    assert build_hysteretic_batch(model) is None


def test_sync_tangents_to_objects_matches_sync_all_to_objects():
    model = load_model(MODEL)
    ModelManager.prepare_model(model)
    runtime = build_hysteretic_batch(model)
    assert runtime is not None

    # Apply displacement to drive trial states
    x = np.linspace(-1.0e-5, 1.0e-5, int(model.gdl), dtype=np.float64)
    runtime.update_domain(x, type("State", (), {"step": 1})())

    # Call sync_tangents_to_objects
    runtime.sync_tangents_to_objects()
    tangent_k_transverse = [s.k_tang for s in runtime.springs]
    tangent_k_coulomb = [s.k_tang for s in runtime.coulomb_springs]
    tangent_k_quad = [q.spring.k_tang for q in runtime.quad_records if q.spring is not None]

    # Reset all k_tang to zero
    for s in runtime.springs:
        s.k_tang = 0.0
    for s in runtime.coulomb_springs:
        s.k_tang = 0.0
    for q in runtime.quad_records:
        if q.spring is not None:
            q.spring.k_tang = 0.0

    # Call sync_all_to_objects
    runtime.sync_all_to_objects()
    all_k_transverse = [s.k_tang for s in runtime.springs]
    all_k_coulomb = [s.k_tang for s in runtime.coulomb_springs]
    all_k_quad = [q.spring.k_tang for q in runtime.quad_records if q.spring is not None]

    assert tangent_k_transverse == all_k_transverse
    assert tangent_k_coulomb == all_k_coulomb
    assert tangent_k_quad == all_k_quad

