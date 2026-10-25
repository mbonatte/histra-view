from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

import histra.solver.interface_material as interface_material
from histra.solver.interface_material import (
    InterfaceMaterialMutationError,
    _backup_interface,
    change_interface_materials,
)


class FakeSpring:
    def __init__(self, committed: float) -> None:
        self.committed = committed


def _interface(key: int, material_key: int = 1) -> SimpleNamespace:
    status = SimpleNamespace(
        u=[float(key)] * 12,
        k=[[float(key)] * 6 for _ in range(6)],
    )
    return SimpleNamespace(
        key=key,
        material_key=material_key,
        status=status,
        f=[float(key + index) for index in range(12)],
        trasv_1=[FakeSpring(10.0 + key), FakeSpring(20.0 + key)],
        slid=[FakeSpring(30.0 + key)],
        slid_out_plan=[FakeSpring(40.0 + key), FakeSpring(50.0 + key)],
        # Representative large/shared non-constitutive payload.  The optimized
        # backup must not duplicate any of it.
        aff=[[object() for _ in range(32)] for _ in range(12)],
        geometry=[object() for _ in range(128)],
        _perf_di=(1.0, 2.0),
        _perf_dj=(3.0, 4.0),
        _perf_ecc=(5.0, 6.0),
        _perf_aff_pairs=((1, 1.0),),
        _perf_dist=(1.0, 2.0),
        _perf_dist_for=(3.0, 4.0),
    )


def _model(*interfaces: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        collections=SimpleNamespace(
            interfaces={item.key: item for item in interfaces},
            materials={1: object(), 2: object()},
        )
    )


def test_backup_interface_is_shallow_except_force_vector() -> None:
    original = _interface(1)

    backup = _backup_interface(original)

    assert backup is not original
    assert backup.trasv_1 is original.trasv_1
    assert backup.slid is original.slid
    assert backup.slid_out_plan is original.slid_out_plan
    assert backup.status is original.status
    assert backup.aff is original.aff
    assert backup.geometry is original.geometry
    assert backup._perf_aff_pairs is original._perf_aff_pairs
    assert backup.f == original.f
    assert backup.f is not original.f


def test_change_interface_materials_reuses_law_caches_and_preserves_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _interface(1)
    second = _interface(2)
    model = _model(first, second)
    original_status_objects = {
        key: item.status for key, item in model.collections.interfaces.items()
    }
    original_status = {
        key: copy.deepcopy(item.status) for key, item in model.collections.interfaces.items()
    }
    original_forces = {
        key: list(item.f) for key, item in model.collections.interfaces.items()
    }
    rebuild_cache_ids: list[tuple[int, int]] = []
    clear_calls = 0

    def fake_rebuild(model_arg, intf, *, flex_law_cache=None, sliding_law_cache=None):
        assert model_arg is model
        assert flex_law_cache is not None
        assert sliding_law_cache is not None
        rebuild_cache_ids.append((id(flex_law_cache), id(sliding_law_cache)))
        intf.trasv_1 = [FakeSpring(-1.0), FakeSpring(-1.0)]
        intf.slid = [FakeSpring(-1.0)]
        intf.slid_out_plan = [FakeSpring(-1.0), FakeSpring(-1.0)]
        intf.status = SimpleNamespace(u=[999.0] * 12, k=[[999.0] * 6 for _ in range(6)])
        return intf

    def fake_transfer(source, target):
        target.committed = source.committed

    def fake_clear():
        nonlocal clear_calls
        clear_calls += 1

    monkeypatch.setattr(interface_material, "rebuild_interface_springs", fake_rebuild)
    monkeypatch.setattr(interface_material, "transfer_committed_spring_state", fake_transfer)
    monkeypatch.setattr(interface_material.ModelManager, "clear_hysteretic_batch", fake_clear)

    report = change_interface_materials(model, [1, 2], 2)

    assert report.interface_count == 2
    assert report.spring_count == 10
    assert len(set(rebuild_cache_ids)) == 1
    assert clear_calls == 1

    for key, intf in model.collections.interfaces.items():
        assert intf.material_key == 2
        assert intf.status == original_status[key]
        # Match the pre-optimization semantics: successful mutation restores an
        # independent copy of InterfaceState rather than the original object.
        assert intf.status is not original_status_objects[key]
        assert intf.f == original_forces[key]
        assert [spring.committed for spring in intf.trasv_1] == [10.0 + key, 20.0 + key]
        assert [spring.committed for spring in intf.slid] == [30.0 + key]
        assert [spring.committed for spring in intf.slid_out_plan] == [40.0 + key, 50.0 + key]


def test_change_interface_materials_rolls_back_atomically_without_deepcopying_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _interface(1)
    second = _interface(2)
    model = _model(first, second)
    expected = copy.deepcopy(model.collections.interfaces)
    original_spring_lists = {
        key: item.trasv_1 for key, item in model.collections.interfaces.items()
    }
    clear_calls = 0

    def fake_rebuild(_model, intf, **_kwargs):
        intf.trasv_1 = [FakeSpring(-1.0), FakeSpring(-1.0)]
        intf.slid = [FakeSpring(-1.0)]
        intf.slid_out_plan = [FakeSpring(-1.0), FakeSpring(-1.0)]
        intf.status = SimpleNamespace(u=[999.0] * 12)
        if intf.key == 2:
            raise RuntimeError("synthetic rebuild failure")
        return intf

    def fake_transfer(source, target):
        target.committed = source.committed

    def fake_clear():
        nonlocal clear_calls
        clear_calls += 1

    monkeypatch.setattr(interface_material, "rebuild_interface_springs", fake_rebuild)
    # The rollback test is intentionally about transaction atomicity, not the
    # detailed SpringHysteretic restart schema. Keep the tiny FakeSpring fixture
    # independent of restart.py's full production spring API.
    monkeypatch.setattr(interface_material, "transfer_committed_spring_state", fake_transfer)
    monkeypatch.setattr(interface_material.ModelManager, "clear_hysteretic_batch", fake_clear)

    with pytest.raises(RuntimeError, match="synthetic rebuild failure"):
        change_interface_materials(model, [1, 2], 2)

    assert clear_calls == 1
    for key, restored in model.collections.interfaces.items():
        assert restored.material_key == expected[key].material_key
        assert restored.status == expected[key].status
        assert restored.f == expected[key].f
        # Rollback restores the actual predecessor spring graph rather than a
        # third deep-copied graph.
        assert restored.trasv_1 is original_spring_lists[key]


def test_change_interface_materials_still_rejects_spring_count_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intf = _interface(1)
    model = _model(intf)

    def fake_rebuild(_model, target, **_kwargs):
        target.trasv_1 = [FakeSpring(-1.0)]
        target.slid = [FakeSpring(-1.0)]
        target.slid_out_plan = [FakeSpring(-1.0), FakeSpring(-1.0)]
        return target

    monkeypatch.setattr(interface_material, "rebuild_interface_springs", fake_rebuild)
    monkeypatch.setattr(interface_material.ModelManager, "clear_hysteretic_batch", lambda: None)

    with pytest.raises(InterfaceMaterialMutationError, match="spring count changed"):
        change_interface_materials(model, [1], 2)


def test_model_manager_keeps_compatible_hysteretic_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model(_interface(1))
    changed = tuple(model.collections.interfaces.values())
    received: list[tuple[object, ...]] = []
    clear_calls = 0

    class FakeRuntime:
        def __init__(self) -> None:
            self.model = model

        def try_update_material_interfaces(self, interfaces):
            received.append(tuple(interfaces))
            return True

    runtime = FakeRuntime()
    monkeypatch.setattr(interface_material.ModelManager, "_hysteretic_batch", runtime)
    monkeypatch.setattr(interface_material.ModelManager, "_hysteretic_batch_model_id", id(model))

    def fake_clear() -> None:
        nonlocal clear_calls
        clear_calls += 1

    monkeypatch.setattr(interface_material.ModelManager, "clear_hysteretic_batch", fake_clear)

    assert interface_material.ModelManager.update_hysteretic_batch_material_interfaces(
        model, changed
    ) is True
    assert received == [changed]
    assert clear_calls == 0


def test_model_manager_discards_incompatible_hysteretic_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model(_interface(1))
    changed = tuple(model.collections.interfaces.values())
    clear_calls = 0

    runtime = SimpleNamespace(
        model=model,
        try_update_material_interfaces=lambda _interfaces: False,
    )
    monkeypatch.setattr(interface_material.ModelManager, "_hysteretic_batch", runtime)
    monkeypatch.setattr(interface_material.ModelManager, "_hysteretic_batch_model_id", id(model))

    def fake_clear() -> None:
        nonlocal clear_calls
        clear_calls += 1

    monkeypatch.setattr(interface_material.ModelManager, "clear_hysteretic_batch", fake_clear)

    assert interface_material.ModelManager.update_hysteretic_batch_material_interfaces(
        model, changed
    ) is False
    assert clear_calls == 1


def test_model_manager_discards_runtime_if_incremental_refresh_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model(_interface(1))
    changed = tuple(model.collections.interfaces.values())
    clear_calls = 0

    def fail(_interfaces):
        raise RuntimeError("synthetic dense update failure")

    runtime = SimpleNamespace(model=model, try_update_material_interfaces=fail)
    monkeypatch.setattr(interface_material.ModelManager, "_hysteretic_batch", runtime)
    monkeypatch.setattr(interface_material.ModelManager, "_hysteretic_batch_model_id", id(model))

    def fake_clear() -> None:
        nonlocal clear_calls
        clear_calls += 1

    monkeypatch.setattr(interface_material.ModelManager, "clear_hysteretic_batch", fake_clear)

    assert interface_material.ModelManager.update_hysteretic_batch_material_interfaces(
        model, changed
    ) is False
    assert clear_calls == 1
