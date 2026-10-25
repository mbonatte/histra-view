"""Construct real masonry springs from native-oracle input definitions."""
from __future__ import annotations

import numpy as np

from histra.springs.hysteretic import SpringHysteretic
from histra.springs.transverse_fiber_group import TransverseFiberGroup
from histra.solver.hysteretic_kernels.transverse import SIMPLE_PARAM_NAMES
from histra.solver.hysteretic_topology import _extract_spring_committed, _extract_spring_trial


def masonry_spring(definition):
    u, f = definition["u"], definition["f"]
    spring = SpringHysteretic(
        k=definition["k"], tensile_curve_type="LinearHardening", compressive_curve_type="LinearHardening",
        mom1p=f[0], rot1p=u[0], mom2p=f[1], rot2p=u[1], mom3p=f[2], rot3p=u[2],
        mom1n=-f[0], rot1n=-u[0], mom2n=-f[1], rot2n=-u[1], mom3n=-f[2], rot3n=-u[2],
        fy=[f[0], -f[0]], uy_corr=[f[0] / definition["k"], -f[0] / definition["k"]],
    )
    spring._set_envelope()
    spring.revert_to_start()
    spring.revert_to_last_commit()
    return spring


def numeric_group(spring, *, cached=False):
    group = TransverseFiberGroup(
        np.array([[getattr(spring, name) for name in SIMPLE_PARAM_NAMES]]),
        np.array([spring.k]), np.ones(1), tensile_curve_type="LinearHardening",
        compressive_curve_type="LinearHardening", fy=np.array([spring.fy]),
    )
    group.sync_from_dense(np.array([_extract_spring_committed(spring)]),
                          np.array([_extract_spring_trial(spring)]))
    if spring.f0 != 0.0:
        group._f0 = np.array([spring.f0])
    if cached:
        group[0].f0 = spring.f0
    return group


def assert_native_state(spring, native, *, include_energy=True):
    values = {
        "K": spring.k, "K_tang": spring.k_tang, "U": spring.u, "F": spring.f,
        "Force": spring.get_force(), "Increment": spring.get_incr_force(),
        "Cstrain": spring._cstrain, "Cstress": spring._cstress,
        "Umax0": spring.umax[0], "Umax1": spring.umax[1],
        "Uy0": spring.uy_corr[0], "Uy1": spring.uy_corr[1],
        "Fy0": spring.fy[0], "Fy1": spring.fy[1], "CrotPu": spring._crot_pu,
        "CrotNu": spring._crot_nu, "CloadIndicator": spring._cload_indicator,
        "F0": spring.f0, "Phase": int(spring.phase), "TPhase": int(spring.t_phase),
        "TrotMax": spring._trot_max, "TrotMin": spring._trot_min,
        "TrotPu": spring._trot_pu, "TrotNu": spring._trot_nu,
        "Tstress": spring._tstress, "Tstrain": spring._tstrain,
        "TloadIndicator": spring._tload_indicator,
    }
    if include_energy:
        values.update(CenergyD=spring.cenergy_d, TenergyD=spring._tenergy_d)
    expected_fields = set(native["bits"])
    if not include_energy:
        expected_fields -= {"CenergyD", "TenergyD"}
    assert set(values) == expected_fields  # New native fields cannot pass unchecked.
    for field, value in values.items():
        actual = int(np.asarray([value], dtype=np.float64).view(np.int64)[0])
        assert actual == int(native["bits"][field]), (field, value, native["values"][field])


def assert_native_trial(trial, native, *, include_energy=True):
    fields = ["TrotMax", "TrotMin", "TrotPu", "TrotNu", "TenergyD",
              "TloadIndicator", "Tstress", "Tstrain", "TPhase", "K_tang"]
    columns = [i for i, field in enumerate(fields) if include_energy or field != "TenergyD"]
    np.testing.assert_array_equal(trial[0, columns].view(np.int64),
                                  [int(native["bits"][fields[i]]) for i in columns])
