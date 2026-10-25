from __future__ import annotations

from enum import Enum
from types import SimpleNamespace

import numpy as np

from histra.solver.state_snapshot import (
    _copy_array,
    _copy_state_dict,
    _copy_object_state,
    _restore_array,
    _restore_state_dict,
    _restore_object_state,
)


class Marker(Enum):
    A = 1


def test_copy_state_dict_is_lossless_and_detached() -> None:
    source = {
        "none": None,
        "bool": True,
        "int": 4,
        "float": 3.25,
        "complex": 1 + 2j,
        "text": "spring",
        "bytes": b"state",
        "enum": Marker.A,
        "array": np.array([1.0, 2.0]),
        "list": [1.0, 2.0],
        "nested_list": [[1.0], {"a": np.array([3.0])}],
        "tuple": (1.0, 2.0),
        "nested_tuple": ([1.0], np.array([2.0])),
        "dict": {"x": [5.0]},
        "set": {1, 2},
        "object": SimpleNamespace(value=[7.0]),
    }

    copied = _copy_state_dict(source)

    assert copied.keys() == source.keys()
    assert copied["array"] is not source["array"]
    assert np.array_equal(copied["array"], source["array"])
    assert copied["list"] is not source["list"]
    assert copied["nested_list"] is not source["nested_list"]
    assert copied["nested_list"][1]["a"] is not source["nested_list"][1]["a"]
    assert copied["tuple"] is source["tuple"]
    assert copied["nested_tuple"] is not source["nested_tuple"]
    assert copied["object"] is not source["object"]

    source["array"][0] = 99.0
    source["list"][0] = 99.0
    source["nested_list"][1]["a"][0] = 99.0
    source["object"].value[0] = 99.0

    assert copied["array"][0] == 1.0
    assert copied["list"][0] == 1.0
    assert copied["nested_list"][1]["a"][0] == 3.0
    assert copied["object"].value[0] == 7.0


def test_restore_state_dict_preserves_compatible_container_aliases() -> None:
    array = np.array([9.0, 9.0])
    values = [9.0, 9.0]
    nested = {"array": np.array([9.0])}
    target = {
        "array": array,
        "list": values,
        "nested": nested,
        "obsolete": "remove me",
    }
    saved = {
        "array": np.array([1.0, 2.0]),
        "list": [3.0, 4.0],
        "nested": {"array": np.array([5.0]), "new": 6.0},
        "created": [7.0],
    }

    _restore_state_dict(target, saved)

    assert target["array"] is array
    assert target["list"] is values
    assert target["nested"] is nested
    assert np.array_equal(array, [1.0, 2.0])
    assert values == [3.0, 4.0]
    assert np.array_equal(nested["array"], [5.0])
    assert nested["new"] == 6.0
    assert "obsolete" not in target

    # Restored containers must not alias the immutable snapshot payload.
    target["array"][0] = 100.0
    target["list"][0] = 100.0
    target["nested"]["array"][0] = 100.0
    target["created"][0] = 100.0
    assert saved["array"][0] == 1.0
    assert saved["list"][0] == 3.0
    assert saved["nested"]["array"][0] == 5.0
    assert saved["created"][0] == 7.0


def test_restore_array_replaces_incompatible_array_shape() -> None:
    shape_target = np.zeros(3)
    shape_saved = np.ones(2)
    restored_shape = _restore_array(shape_target, shape_saved)
    assert restored_shape is not shape_target
    assert restored_shape is not shape_saved
    assert np.array_equal(restored_shape, shape_saved)

    # Preserve the previous rollback semantics: equal-shaped arrays restore
    # through the existing target even when NumPy must cast the saved dtype.
    dtype_target = np.zeros(2, dtype=np.float32)
    dtype_saved = np.ones(2, dtype=np.float64)
    restored_dtype = _restore_array(dtype_target, dtype_saved)
    assert restored_dtype is dtype_target
    assert restored_dtype.dtype == np.float32
    assert np.array_equal(restored_dtype, dtype_saved)


def test_copy_array_handles_scalar_tuple_without_allocation() -> None:
    value = (1, 2.0, "x", Marker.A)
    assert _copy_array(value) is value


def test_slotted_spring_object_state_roundtrip_is_lossless() -> None:
    from histra.springs.hysteretic import SpringHysteretic
    from histra.types.phase_enum import PhaseEnum

    spring = SpringHysteretic(type_of="HiStrA.Objects.SpringHysteretic")
    spring.k = 1234.5
    spring.fy[:] = [6.25, -17.5]
    spring.kt[:] = [2.0, -3.0]
    spring.ur[:] = [0.0125, -0.025]
    spring.umax[:] = [0.01, -0.02]
    spring._cstress = 4.75
    spring._cstrain = 0.003
    spring.phase = PhaseEnum.Plastic_t
    spring.custom_probe = {"history": [1.0, 2.0]}

    saved = _copy_object_state(spring)
    original_fy = spring.fy
    original_probe = spring.custom_probe

    spring.k = -1.0
    spring.fy[:] = [99.0, 98.0]
    spring.kt[:] = [97.0, 96.0]
    spring.ur[:] = [95.0, 94.0]
    spring.umax[:] = [93.0, 92.0]
    spring._cstress = -88.0
    spring._cstrain = -77.0
    spring.phase = PhaseEnum.Rupture
    spring.custom_probe["history"][0] = 123.0
    spring.created_after_snapshot = "remove"

    _restore_object_state(spring, saved)

    assert spring.k == 1234.5
    assert spring.fy is original_fy
    assert spring.fy == [6.25, -17.5]
    assert spring.kt == [2.0, -3.0]
    assert spring.ur == [0.0125, -0.025]
    assert spring.umax == [0.01, -0.02]
    assert spring._cstress == 4.75
    assert spring._cstrain == 0.003
    assert spring.phase == PhaseEnum.Plastic_t
    assert spring.custom_probe is original_probe
    assert spring.custom_probe == {"history": [1.0, 2.0]}
    assert "created_after_snapshot" not in spring.__dict__

    # Mutating the restored object must not mutate the immutable snapshot.
    spring.fy[0] = 500.0
    spring.custom_probe["history"][0] = 500.0
    assert saved["fy"][0] == 6.25
    assert saved["custom_probe"]["history"][0] == 1.0


def test_solver_state_snapshot_unmanaged_spring_filtering() -> None:
    from histra.solver.state_snapshot import SolverStateSnapshot
    from histra.types.linear_system import LinearSystem
    from histra.solver.program import Program
    from histra.solver.load_control import LoadControl

    # Create dummy model with no unmanaged springs and a batch runtime stub
    model = SimpleNamespace(
        collections=SimpleNamespace(
            quads={},
            interfaces={},
        )
    )
    p = Program()
    ls = LinearSystem(1, backend="superlu")
    integrator = LoadControl()
    integrator.state = SimpleNamespace()

    snapshot = SolverStateSnapshot.capture(model, p, ls, integrator)
    assert snapshot.spring_state == []

