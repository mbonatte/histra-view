from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

import numpy as np

from histra.elements.interface import Interface
from histra.types.afference_entry import AfferenceEntry


@dataclass
class _Spring:
    u: float = 0.0
    _cstress: float = 0.25
    _tstress: float = 0.25
    stiffness: float = 3.0

    def set_trial_strain(self, value: float) -> None:
        self._tstress = self._cstress + self.stiffness * value


def _old_update_domain(interface: Interface, x: np.ndarray) -> None:
    """The pre-optimization scalar path, retained as an exact oracle."""
    interface._ensure_performance_cache()
    local_du = [0.0] * interface.dim_aff_tot
    for i, pairs in enumerate(interface._perf_aff_pairs or ()):
        total = 0.0
        for gdl, coefficient in pairs:
            if 0 <= gdl < len(x):
                total += x[gdl] * coefficient
        local_du[i] = total
    for i, value in enumerate(local_du):
        interface.status.u[i] += float(value)
    if not interface.interfaccia_vincolata_computed():
        num = local_du[3] - local_du[0]
        num2 = local_du[2] - local_du[1]
    else:
        half_length = interface.length / 2.0
        num = local_du[3] - (local_du[0] - local_du[1] * half_length)
        num2 = local_du[2] - (local_du[0] + local_du[1] * half_length)
    delta_flex = local_du[5] - local_du[4]
    normal_increment = 0.0
    committed_normal_force = 0.0
    max_displacement = 0.0
    inv_length = 1.0 / interface.length
    for spring, di, dj, ecc in zip(
        interface.trasv_1,
        interface._perf_di or (),
        interface._perf_dj or (),
        interface._perf_ecc or (),
    ):
        increment = (num * dj + num2 * di) * inv_length - delta_flex * ecc
        new_u = spring.u + increment
        spring.u = new_u
        spring.set_trial_strain(new_u)
        if "get_incr_force" in spring.__dict__ or "get_force" in spring.__dict__:
            trial = float(spring.get_force())
            committed = trial - float(spring.get_incr_force())
        else:
            trial = float(spring._tstress)
            committed = float(spring._cstress)
        normal_increment -= trial - committed
        committed_normal_force += committed
        abs_u = abs(new_u)
        if abs_u > max_displacement:
            max_displacement = abs_u
    interface.status.normal_increment = normal_increment
    interface.status.committed_normal_force = committed_normal_force
    interface.status.max_spring_displacement = max_displacement


def _make_interface() -> Interface:
    interface = Interface(length=2.5, nrow=1, ncol=3, nspring=3)
    interface.trasv_1 = [_Spring(), _Spring(stiffness=4.0), _Spring(stiffness=5.0)]
    interface.aff = [[] for _ in range(12)]
    for local_dof in range(6):
        interface.aff[local_dof] = [
            AfferenceEntry(gdl=local_dof + 1, alfa=1.0),
            AfferenceEntry(gdl=12 - local_dof, alfa=-0.125),
        ]
    return interface


def test_cached_scalar_update_is_bitwise_equal_to_previous_path() -> None:
    expected = _make_interface()
    actual = deepcopy(expected)
    increment = np.asarray(
        [0.001, -0.002, 0.003, -0.004, 0.005, -0.006,
         0.007, -0.008, 0.009, -0.010, 0.011, -0.012],
        dtype=np.float64,
    )

    _old_update_domain(expected, increment)
    actual.update_domain(increment, object())

    np.testing.assert_array_equal(actual.status.u, expected.status.u)
    assert actual.status.normal_increment == expected.status.normal_increment
    assert actual.status.committed_normal_force == expected.status.committed_normal_force
    assert actual.status.max_spring_displacement == expected.status.max_spring_displacement
    for actual_spring, expected_spring in zip(actual.trasv_1, expected.trasv_1):
        assert actual_spring.u == expected_spring.u
        assert actual_spring._tstress == expected_spring._tstress


def test_local_increment_reuses_private_work_buffer() -> None:
    interface = _make_interface()
    first = interface._local_increment(np.ones(12, dtype=np.float64))
    first_id = id(first)
    second = interface._local_increment(np.zeros(12, dtype=np.float64))
    assert id(second) == first_id
    assert second == [0.0] * 12


def _old_compute_kfless(interface: Interface, alfa: float) -> list[list[float]]:
    """Pre-cache scalar stiffness path retained as a bitwise oracle."""
    d0 = interface.dim_aff[0] if interface.dim_aff else 6
    size = d0 if d0 > 4 else 6
    stiffness = [[0.0 for _ in range(size)] for _ in range(size)]
    nrow = max(interface.nrow, 1)
    ncol = max(interface.ncol, 1)

    num = num2 = num3 = 0.0
    for row in range(nrow):
        for col in range(ncol):
            spring_index = interface.idx(row, col)
            if spring_index >= len(interface.trasv_1):
                continue
            di = interface.get_di(row, col)
            dj = interface.get_dj(row, col)
            spring_k = interface.trasv_1[spring_index].get_k(alfa)
            num += spring_k * di * di
            num3 += spring_k * di * dj
            num2 += spring_k * dj * dj

    length = interface.length
    length2 = length * length
    if length2 > 1.0e-30:
        num /= length2
        num3 /= length2
        num2 /= length2

    constrained = interface.interfaccia_vincolata_computed()
    if constrained:
        num4 = num5 = num6 = 0.0
        for col in range(ncol):
            for row in range(nrow):
                spring_index = interface.idx(row, col)
                if spring_index >= len(interface.trasv_1):
                    continue
                di = interface.get_di(row, col)
                dm = interface.get_dm(row, col)
                spring_k = interface.trasv_1[spring_index].get_k(alfa)
                num4 += spring_k
                num5 -= spring_k * dm
                num6 += spring_k * dm * dm
        stiffness[0][0] = num4
        stiffness[0][1] = num5
        stiffness[1][1] = num6
        stiffness[0][2] = -num - num3
        stiffness[0][3] = -num3 - num2
        stiffness[1][2] = num3 * length / 2.0 - num * length / 2.0
        stiffness[1][3] = num2 * length / 2.0 - num3 * length / 2.0
        stiffness[2][2] = num
        stiffness[2][3] = num3
        stiffness[3][3] = num2
    else:
        stiffness[0][0] = num2
        stiffness[0][1] = num3
        stiffness[0][2] = -num3
        stiffness[0][3] = -num2
        stiffness[1][1] = num
        stiffness[1][2] = -num
        stiffness[1][3] = -num3
        stiffness[2][2] = num
        stiffness[2][3] = num3
        stiffness[3][3] = num2

    for row in range(4):
        for col in range(row + 1, 4):
            stiffness[col][row] = stiffness[row][col]

    d2 = interface.dim_aff[2] if len(interface.dim_aff) > 2 else 4
    if d2 <= 0:
        return stiffness

    num7 = 0.0
    for col in range(ncol):
        for row in range(nrow):
            spring_index = interface.idx(row, col)
            if spring_index >= len(interface.trasv_1):
                continue
            spring_k = interface.trasv_1[spring_index].get_k(alfa)
            ecc = interface.ecc_spring(row, col)
            num7 += spring_k * ecc * ecc
    stiffness[4][4] = num7
    stiffness[5][5] = num7
    stiffness[4][5] = -num7
    stiffness[5][4] = -num7

    num7 = 0.0
    num8 = 0.0
    for col in range(ncol):
        for row in range(nrow):
            spring_index = interface.idx(row, col)
            if spring_index >= len(interface.trasv_1):
                continue
            spring_k = interface.trasv_1[spring_index].get_k(alfa)
            di = interface.get_di(row, col)
            dj = interface.get_dj(row, col)
            ecc = interface.ecc_spring(row, col)
            num7 += spring_k * dj * ecc
            num8 += spring_k * di * ecc
    if length > 1.0e-30:
        num7 /= length
        num8 /= length

    if not constrained:
        stiffness[0][4] = -num7
        stiffness[1][4] = -num8
        stiffness[2][4] = num8
        stiffness[3][4] = num7
        stiffness[0][5] = num7
        stiffness[1][5] = num8
        stiffness[2][5] = -num8
        stiffness[3][5] = -num7
    else:
        stiffness[0][4] = -num7 - num8
        stiffness[1][4] = (-num8 + num7) * length / 2.0
        stiffness[2][4] = num8
        stiffness[3][4] = num7
        stiffness[0][5] = num7 + num8
        stiffness[1][5] = (num8 - num7) * length / 2.0
        stiffness[2][5] = -num8
        stiffness[3][5] = -num7

    for row in range(4):
        stiffness[4][row] = stiffness[row][4]
        stiffness[5][row] = stiffness[row][5]
    return stiffness


def _make_stiffness_interface(*, constrained: bool) -> Interface:
    from histra.springs.base import Spring
    from histra.types.point import Point

    interface = Interface(length=2.75, nrow=3, ncol=4, nspring=12)
    interface.vint2d = [
        Point(x=0.10, y=-0.85),
        Point(x=2.55, y=-0.70),
        Point(x=2.70, y=0.95),
        Point(x=0.05, y=0.80),
    ]
    interface.trasv_1 = [
        Spring(k=2.0 + 0.17 * index, k_tang=3.0 + 0.13 * index)
        for index in range(12)
    ]
    if constrained:
        interface.parent_type_element1 = "Restraint"
    return interface


def test_cached_flexural_stiffness_is_bitwise_equal_to_scalar_reference() -> None:
    for constrained in (False, True):
        for alfa in (0.0, 0.37, 1.0):
            interface = _make_stiffness_interface(constrained=constrained)
            expected = np.asarray(_old_compute_kfless(interface, alfa))

            interface._compute_kfless(alfa)
            actual = np.asarray(interface.status.k)

            np.testing.assert_array_equal(actual, expected)


def test_stiffness_geometry_cache_reuses_values_without_geometry_calls(monkeypatch) -> None:
    interface = _make_stiffness_interface(constrained=False)
    interface._compute_kfless(1.0)
    expected = np.asarray(interface.status.k).copy()

    def fail(*_args, **_kwargs):
        raise AssertionError("cached stiffness must not recompute spring geometry")

    monkeypatch.setattr(interface, "get_di", fail)
    monkeypatch.setattr(interface, "get_dj", fail)
    monkeypatch.setattr(interface, "get_dm", fail)
    monkeypatch.setattr(interface, "ecc_spring", fail)
    interface._compute_kfless(1.0)

    np.testing.assert_array_equal(np.asarray(interface.status.k), expected)


def test_flexural_stiffness_reads_each_transverse_tangent_once(monkeypatch) -> None:
    """Repeated stiffness sums must reuse the same pure ``Spring.get_k`` value."""
    from histra.springs.base import Spring

    interface = _make_stiffness_interface(constrained=True)
    calls = 0
    original = Spring.get_k

    def counted_get_k(self: Spring, alfa: float = 0.0) -> float:
        nonlocal calls
        calls += 1
        return original(self, alfa)

    monkeypatch.setattr(Spring, "get_k", counted_get_k)
    interface._compute_kfless(0.37)

    assert calls == len(interface.trasv_1)


def test_stiffness_geometry_cache_is_bitwise_equal_to_geometry_helpers() -> None:
    """Cache construction must preserve the scalar bilinear interpolation exactly."""
    from histra.springs.base import Spring
    from histra.types.point import Point

    cases = (
        (1, 1, 1, 2.75),
        (3, 4, 12, 2.75),
        (9, 9, 81, 342.4),
        (7, 11, 53, 139.8),
        (-2, -3, 6, 10.0),
    )
    points = [
        Point(x=0.123456789, y=-8.765432101),
        Point(x=139.71234567, y=-7.125678901),
        Point(x=141.03456789, y=336.9876543),
        Point(x=-0.456789012, y=342.1234567),
    ]

    for nrow, ncol, count, length in cases:
        interface = Interface(length=length, nrow=nrow, ncol=ncol, nspring=count)
        interface.vint2d = deepcopy(points)
        interface.trasv_1 = [Spring(k=1.0) for _ in range(count)]

        expected_di: list[float] = []
        expected_ecc: list[float] = []
        effective_ncol = max(ncol, 1)
        for index in range(count):
            row, col = divmod(index, effective_ncol)
            expected_di.append(interface.get_di(row, col))
            expected_ecc.append(interface.ecc_spring(row, col))
        expected_dj = [length - value for value in expected_di]

        interface._ensure_stiffness_geometry_cache()

        np.testing.assert_array_equal(interface._perf_di, expected_di)
        np.testing.assert_array_equal(interface._perf_dj, expected_dj)
        np.testing.assert_array_equal(interface._perf_ecc, expected_ecc)


def test_compute_kfless_uniform_fast_path_matches_non_uniform() -> None:
    """The uniform stiffness fast-path must match the non-uniform loop to machine precision."""
    from histra.springs.base import Spring
    from histra.types.point import Point

    points = [
        Point(x=0.0, y=0.0),
        Point(x=100.0, y=0.0),
        Point(x=100.0, y=50.0),
        Point(x=0.0, y=50.0),
    ]

    for constrained in (False, True):
        interface1 = Interface(length=100.0, nrow=3, ncol=4, nspring=12)
        interface1.vint2d = deepcopy(points)
        interface1.interfaccia_vincolata = constrained
        interface1.dim_aff = [6, 2, 4]
        interface1.trasv_1 = [Spring(k=500.0) for _ in range(12)]

        interface2 = deepcopy(interface1)
        # Interface 1 uses uniform fast-path
        interface1._compute_kfless(0.5)

        # Interface 2 is forced into non-uniform branch by slightly varying one spring's stiffness
        interface2.trasv_1[-1].k = 500.0 + 1e-12
        interface2._compute_kfless(0.5)

        k1 = np.array(interface1.status.k)
        k2 = np.array(interface2.status.k)
        np.testing.assert_allclose(k1, k2, rtol=1e-7, atol=1e-7)
