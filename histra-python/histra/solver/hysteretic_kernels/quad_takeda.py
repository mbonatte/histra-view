"""Compiled Quad diagonal kernels (native Coulomb, elastic and hysteretic laws).

The Quad diagonal spring state machine translated from C# ``Quad``: tau limit
and shear ultimate strain helpers, trial revert, tangent reload branches, the
positive/negative yield-increment state updates and the batch evaluator and
commit kernels.

The dense state/parameter column constants below (``QFY0`` .. ``QUAD_PARAM_SIZE``,
``QUAD_SUBLAW_*``, ``QUAD_HYSTERETIC_*``, ``QUAD_FRACTURE_*``) are part of the
compiled contract; the state layout deliberately keeps committed and trial
values in one contiguous row so rejected Newton/ArcLength trials can be
reverted without touching Python attributes.

No ``fastmath`` is used anywhere (parity-sensitive reductions).
"""
from __future__ import annotations

import numpy as np

from histra.model.shear_law import (
    ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION,
    ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED,
)
from histra.solver.hysteretic_kernels.transverse import (
    ELASTIC,
    TRANSVERSE_PARAM_SIZE,
    _evaluate_linear_serial_batch,
    PLASTIC_C,
    PLASTIC_T,
    RELOAD_C,
    RELOAD_T,
    RUPTURE,
    RUPTURE_C,
    RUPTURE_T,
    UNLOAD_C,
    UNLOAD_T,
)

try:  # optional acceleration dependency
    from numba import njit
except Exception:  # pragma: no cover - exercised when numba is unavailable
    njit = None


# Dense state for Quad diagonal SpringCoulomb03 (Takeda, Coulomb law, no
# fracture-energy material callback).  The layout deliberately contains both
# committed and trial values because rejected Newton/ArcLength trials must be
# reversible without touching thousands of Python attributes.
QFY0, QFY1 = 0, 1
QUMAX0, QUMAX1 = 2, 3
QCROT_PU, QCROT_NU, QCROT_LIM_PU, QCROT_LIM_NU = 4, 5, 6, 7
QCROT_YP, QCROT_YN, QCMOM_MAX, QCMOM_MIN = 8, 9, 10, 11
QCLOAD, QCPLAST_T, QCPLAST_C, QCUNLOAD_T, QCUNLOAD_C = 12, 13, 14, 15, 16
QCUP, QCENERGY, QCSTRESS, QCSTRAIN = 17, 18, 19, 20
QCSTRESS_NORMAL, QCSTRESS_NORMAL_PREV, QCCONTACT = 21, 22, 23
QPHASE, QTANG_RELOAD_T, QTANG_RELOAD_C, QKTANG_COMMITTED = 24, 25, 26, 27
QTROT_MAX, QTROT_MIN, QTROT_PU, QTROT_NU = 28, 29, 30, 31
QTROT_LIM_PU, QTROT_LIM_NU, QTROT_YP, QTROT_YN = 32, 33, 34, 35
QTMOM_MAX, QTMOM_MIN, QTLOAD = 36, 37, 38
QTPLAST_T, QTPLAST_C, QTUNLOAD_T, QTUNLOAD_C = 39, 40, 41, 42
QTENERGY, QTUP, QTSTRESS, QTSTRAIN = 43, 44, 45, 46
QTSTRESS_NORMAL, QTCONTACT, QTPHASE, QKTANG = 47, 48, 49, 50
QMOM1P, QROT1P, QMOM2P, QROT2P, QMOM3P, QROT3P = 51, 52, 53, 54, 55, 56
QMOM1N, QROT1N, QMOM2N, QROT2N, QMOM3N, QROT3N = 57, 58, 59, 60, 61, 62
QUR0, QUR1, QDN = 63, 64, 65
# Append the shared hysteretic layouts; keep existing Coulomb indices stable.
QHCOMMITTED = 66
QHTRIAL = QHCOMMITTED + 9
QUAD_STATE_SIZE = QHTRIAL + 10

QPCOHESION, QPMU = 0, 1
QPE1P, QPE2P, QPE3P = 2, 3, 4
QPE1N, QPE2N, QPE3N = 5, 6, 7
QPEUP, QPEUN, QPPLASTIC_STRAIN, QPENABLED = 8, 9, 10, 11
QPK = 12
QPSUBLAW = 13
QPBCACOVIC = 14
QPFRACTURE_MODE = 15
QPFRACTURE_ENERGY = 16
QPHYSTERETIC_TYPE = 17
QPH = 18
QHPARAMS = 19
QUAD_PARAM_SIZE = QHPARAMS + TRANSVERSE_PARAM_SIZE


QUAD_SUBLAW_COULOMB = 0
QUAD_SUBLAW_CACOVIC = 1
QUAD_SUBLAW_ELASTIC = 2
QUAD_SUBLAW_HYSTERETIC = 3
QUAD_HYSTERETIC_TAKEDA = 0
QUAD_HYSTERETIC_INITIAL = 1
QUAD_FRACTURE_NONE = 0
QUAD_FRACTURE_FIXED = ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED
QUAD_FRACTURE_INTERPOLATED = ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION


if njit is not None:
    @njit(cache=True, inline="always")
    def _mirror_hysteretic_quad(row):
        c, t = QHCOMMITTED, QHTRIAL
        for target, source in ((QUMAX0,0),(QUMAX1,1),(QCROT_PU,2),(QCROT_NU,3),
                               (QCENERGY,4),(QCLOAD,5),(QCSTRESS,6),(QCSTRAIN,7),(QPHASE,8)):
            row[target] = row[c + source]
        for target, source in ((QTROT_MAX,0),(QTROT_MIN,1),(QTROT_PU,2),(QTROT_NU,3),
                               (QTENERGY,4),(QTLOAD,5),(QTSTRESS,6),(QTSTRAIN,7),(QTPHASE,8),(QKTANG,9)):
            row[target] = row[t + source]

    @njit(cache=True, inline="always")
    def _revert_hysteretic_quad(row):
        # Native history restore retains the current trial tangent.
        for j in range(9):
            row[QHTRIAL + j] = row[QHCOMMITTED + j]
        _mirror_hysteretic_quad(row)

    @njit(cache=True, inline="always")
    def _quad_tau_limit(par, normal_stress):
        cohesion = par[QPCOHESION]
        if int(par[QPSUBLAW]) == QUAD_SUBLAW_CACOVIC:
            value = 1.0 + normal_stress / (1.5 * cohesion)
            if value < 0.0:
                return 0.0
            return 1.5 / par[QPBCACOVIC] * cohesion * np.sqrt(value)
        value = cohesion + par[QPMU] * normal_stress
        return value if value > 0.0 else 0.0

    @njit(cache=True, inline="always")
    def _quad_interpolated_shear_energy(sigma):
        # C# MasonryMaterial.GetShearUltimateStrain interpolates at -sigma.
        x = -sigma
        if x <= 0.05:
            return 0.0012385
        if x >= 0.07:
            return 0.0001699
        if x <= 0.055:
            return 0.0012385 + (0.0007775 - 0.0012385) * (x - 0.05) / 0.005
        if x <= 0.06:
            return 0.0007775 + (0.0004402 - 0.0007775) * (x - 0.055) / 0.005
        return 0.0004402 + (0.0001699 - 0.0004402) * (x - 0.06) / 0.01

    @njit(cache=True, inline="always")
    def _quad_shear_ultimate_strain(par, f_limit, yield_strain, volume, sigma):
        mode = int(par[QPFRACTURE_MODE])
        if mode == QUAD_FRACTURE_INTERPOLATED:
            energy = _quad_interpolated_shear_energy(sigma)
        else:
            energy = par[QPFRACTURE_ENERGY]
        if f_limit == 0.0:
            numerator = energy * volume
            if numerator == 0.0:
                return np.nan
            return np.inf if numerator > 0.0 else -np.inf
        return energy * volume / f_limit + 0.5 * yield_strain

    @njit(cache=True, inline="always")
    def _quad_revert_trial(row):
        row[QFY0] = -row[QFY1]
        row[QTROT_MAX] = row[QUMAX0]
        row[QTROT_MIN] = row[QUMAX1]
        row[QTROT_PU] = row[QCROT_PU]
        row[QTROT_NU] = row[QCROT_NU]
        row[QTENERGY] = row[QCENERGY]
        row[QTLOAD] = row[QCLOAD]
        row[QTSTRESS] = row[QCSTRESS]
        row[QTSTRAIN] = row[QCSTRAIN]
        row[QTSTRESS_NORMAL] = row[QCSTRESS_NORMAL]
        row[QTCONTACT] = row[QCCONTACT]
        row[QTUP] = row[QCUP]
        row[QTPHASE] = row[QPHASE]
        row[QTMOM_MAX] = row[QCMOM_MAX]
        row[QTMOM_MIN] = row[QCMOM_MIN]
        row[QTROT_LIM_PU] = row[QCROT_LIM_PU]
        row[QTROT_LIM_NU] = row[QCROT_LIM_NU]
        row[QTROT_YP] = row[QCROT_YP]
        row[QTROT_YN] = row[QCROT_YN]
        row[QTPLAST_T] = row[QCPLAST_T]
        row[QTPLAST_C] = row[QCPLAST_C]
        row[QTUNLOAD_T] = row[QCUNLOAD_T]
        row[QTUNLOAD_C] = row[QCUNLOAD_C]

    @njit(cache=True, inline="always")
    def _quad_tangent_reload_t(row, par):
        """C# SpringCoulomb03.TangentReload_t getter semantics."""
        minimum = 1.0e-4 * par[QPK]
        stored = row[QTANG_RELOAD_T]
        return minimum if stored < minimum else stored

    @njit(cache=True, inline="always")
    def _quad_tangent_reload_c(row, par):
        """C# SpringCoulomb03.TangentReload_c getter semantics."""
        minimum = 1.0e-4 * par[QPK]
        stored = row[QTANG_RELOAD_C]
        return minimum if stored < minimum else stored

    @njit(cache=True, inline="always")
    def _quad_yield_tension(row, par, phase_unload, dstrain):
        if row[QTPLAST_T] == 0.0:
            num2 = row[QMOM1P]
            num3 = row[QROT1P]
        else:
            num2 = row[QCMOM_MAX]
            num3 = row[QUMAX0]
        if dstrain < 0.0:
            return num3
        phase = int(row[QTPHASE])
        if phase == 10:
            return row[QTROT_MAX]
        if phase == ELASTIC or phase == PLASTIC_T:
            return row[QUMAX0]
        if phase == PLASTIC_C:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_T or phase_unload == RELOAD_T:
                num4 = row[QCSTRAIN] - row[QCSTRESS] / par[QPE1N]
                num5 = _quad_tangent_reload_t(row, par) if num2 <= 0.0 else num2 / (num3 - num4)
                return row[QMOM1P] / num5 + num4
        if phase == UNLOAD_T:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_T:
                return row[QTROT_PU] + row[QMOM1P] / par[QPE1P]
            if phase_unload == RELOAD_T:
                if row[QTSTRAIN] < row[QTROT_LIM_PU]:
                    return row[QTROT_PU] + row[QMOM1P] / par[QPE1P]
                return row[QTROT_NU] + row[QMOM1P] / _quad_tangent_reload_t(row, par)
        if phase == UNLOAD_C:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_T or phase_unload == RELOAD_T:
                num5 = _quad_tangent_reload_t(row, par) if num2 <= 0.0 else num2 / (num3 - row[QTROT_NU])
                return row[QTROT_NU] + row[QMOM1P] / num5
        if phase == RELOAD_T:
            if phase_unload == ELASTIC or phase_unload == RELOAD_T:
                num5 = _quad_tangent_reload_t(row, par)
                num = row[QTROT_NU] + row[QMOM1P] / num5
                if par[QPE3P] < 0.0:
                    val = (row[QTROT_NU] * num5 - row[QROT3P] * par[QPE3P]) / (num5 - par[QPE3P])
                    if val < num:
                        num = val
                return num
        if phase == RELOAD_C:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_T:
                num4 = row[QCSTRAIN] - row[QCSTRESS] / par[QPE1N]
                num5 = _quad_tangent_reload_t(row, par) if num2 <= 0.0 else num2 / (num3 - num4)
                return num4 + row[QMOM1P] / num5
            if phase_unload == RELOAD_T:
                if int(row[QTUNLOAD_C]) == RELOAD_C:
                    num4 = row[QCSTRAIN] - row[QCSTRESS] / par[QPE1N]
                    num5 = _quad_tangent_reload_t(row, par) if num2 <= 0.0 else num2 / (num3 - num4)
                    return row[QTROT_NU] + row[QMOM1P] / num5
                return row[QTROT_NU] + row[QMOM1P] / _quad_tangent_reload_t(row, par)
        return num3

    @njit(cache=True, inline="always")
    def _quad_yield_compression(row, par, phase_unload, dstrain):
        if row[QTPLAST_C] == 0.0:
            num2 = row[QMOM1N]
            num3 = row[QROT1N]
        else:
            num2 = row[QCMOM_MIN]
            num3 = row[QUMAX1]
        if dstrain > 0.0:
            return num3
        phase = int(row[QTPHASE])
        if phase == 10:
            return row[QTROT_MIN]
        if phase == ELASTIC or phase == PLASTIC_C:
            return row[QUMAX1]
        if phase == PLASTIC_T:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_C or phase_unload == RELOAD_C:
                num4 = row[QCSTRAIN] - row[QCSTRESS] / par[QPE1P]
                tc = _quad_tangent_reload_c(row, par) if num2 == 0.0 else num2 / (num3 - num4)
                return row[QMOM1N] / tc + num4
        if phase == UNLOAD_T:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_C or phase_unload == RELOAD_C:
                tc = _quad_tangent_reload_c(row, par) if num2 == 0.0 else num2 / (num3 - row[QTROT_PU])
                return row[QTROT_PU] + row[QMOM1N] / tc
        if phase == UNLOAD_C:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_C:
                return row[QTROT_NU] + row[QMOM1N] / par[QPE1N]
            if phase_unload == RELOAD_C:
                if row[QTSTRAIN] > row[QTROT_LIM_NU]:
                    return row[QTROT_NU] + row[QMOM1N] / par[QPE1N]
                return row[QTROT_PU] + row[QMOM1N] / _quad_tangent_reload_c(row, par)
        if phase == RELOAD_T:
            if phase_unload == ELASTIC:
                return num3
            if phase_unload == PLASTIC_C:
                num4 = row[QCSTRAIN] - row[QCSTRESS] / par[QPE1P]
                tc = _quad_tangent_reload_c(row, par) if num2 == 0.0 else num2 / (num3 - num4)
                return num4 + row[QMOM1N] / tc
            if phase_unload == RELOAD_C:
                if int(row[QTUNLOAD_T]) == RELOAD_T:
                    num4 = row[QCSTRAIN] - row[QCSTRESS] / par[QPE1P]
                    tc = _quad_tangent_reload_c(row, par) if num2 == 0.0 else num2 / (num3 - num4)
                    return num4 + row[QMOM1N] / tc
                return row[QTROT_PU] + row[QMOM1N] / _quad_tangent_reload_c(row, par)
        if phase == RELOAD_C:
            if phase_unload == ELASTIC or phase_unload == RELOAD_C:
                tc = _quad_tangent_reload_c(row, par)
                num = row[QTROT_PU] + row[QMOM1N] / tc
                if par[QPE3N] < 0.0:
                    val = (row[QTROT_PU] * tc - row[QROT3N] * par[QPE3N]) / (tc - par[QPE3N])
                    if val > num:
                        num = val
                return num
        return num3

    @njit(cache=True, inline="always")
    def _quad_positive_increment(row, par, dstrain):
        if int(row[QTLOAD]) == 2:
            if (int(row[QTUNLOAD_C]) == RELOAD_C
                    and row[QTMOM_MIN] > row[QCSTRESS] and row[QCSTRESS] < 0.0):
                row[QTMOM_MIN] = row[QCSTRESS]
                row[QTROT_MIN] = row[QCSTRAIN]
                row[QTROT_NU] = row[QCSTRAIN] - row[QCSTRESS] / par[QPEUN]
            if int(row[QTUNLOAD_C]) == RELOAD_C and int(row[QTPHASE]) == RELOAD_C:
                row[QTROT_LIM_NU] = row[QCSTRAIN]
            row[QTLOAD] = 1.0
            if row[QCSTRESS] <= 0.0:
                row[QTROT_NU] = row[QCSTRAIN] - row[QCSTRESS] / par[QPEUN]
                row[QTROT_MAX] = row[QUMAX0]
        row[QTLOAD] = 1.0
        if row[QTPLAST_T] == 0.0:
            row[QTROT_MAX] = row[QROT1P]
            row[QTMOM_MAX] = row[QMOM1P]
        tmom_max = row[QTMOM_MAX]
        trot_nu = row[QTROT_NU]
        if row[QTSTRAIN] < trot_nu:
            row[QKTANG] = par[QPE1N]
            row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
            if row[QTSTRESS] < row[QMOM1N]:
                row[QTSTRESS] = row[QMOM1N]
            if row[QTSTRESS] >= 0.0:
                row[QTSTRESS] = 0.0
                row[QKTANG] = par[QPEUN] * 1e-9
            return
        phase = int(row[QTPHASE])
        if phase == PLASTIC_C:
            row[QKTANG] = tmom_max / (row[QTROT_MAX] - trot_nu)
            row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_nu)
        elif phase == ELASTIC or phase == UNLOAD_C:
            if int(row[QTUNLOAD_C]) == ELASTIC:
                row[QKTANG] = tmom_max / (row[QTROT_MAX] - trot_nu)
                row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
            elif int(row[QTUNLOAD_C]) == PLASTIC_C or int(row[QTUNLOAD_C]) == RELOAD_C:
                row[QKTANG] = tmom_max / (row[QTROT_MAX] - trot_nu)
                row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_nu)
        elif phase == UNLOAD_T:
            if int(row[QTUNLOAD_T]) == ELASTIC or int(row[QTUNLOAD_T]) == PLASTIC_T:
                row[QKTANG] = par[QPE1P]
                row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
            elif int(row[QTUNLOAD_T]) == RELOAD_T:
                if row[QTSTRAIN] < row[QTROT_LIM_PU]:
                    row[QKTANG] = par[QPE1P]
                    row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
                else:
                    row[QKTANG] = _quad_tangent_reload_t(row, par)
                    row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_nu)
        elif phase == RELOAD_C:
            row[QKTANG] = tmom_max / (row[QTROT_MAX] - trot_nu)
            row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_nu)
        elif phase == RELOAD_T:
            row[QKTANG] = _quad_tangent_reload_t(row, par)
            row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_nu)

    @njit(cache=True, inline="always")
    def _quad_negative_increment(row, par, dstrain):
        if int(row[QTLOAD]) == 1:
            if (int(row[QTUNLOAD_T]) == RELOAD_T
                    and row[QTMOM_MAX] < row[QCSTRESS] and row[QCSTRESS] > 0.0):
                row[QTMOM_MAX] = row[QCSTRESS]
                row[QTROT_MAX] = row[QCSTRAIN]
                row[QTROT_PU] = row[QCSTRAIN] - row[QCSTRESS] / par[QPEUP]
            if int(row[QTUNLOAD_T]) == RELOAD_T and int(row[QTPHASE]) == RELOAD_T:
                row[QTROT_LIM_PU] = row[QCSTRAIN]
            row[QTLOAD] = 2.0
            if row[QCSTRESS] >= 0.0:
                row[QTROT_PU] = row[QCSTRAIN] - row[QCSTRESS] / par[QPEUP]
                row[QTROT_MIN] = row[QUMAX1]
        row[QTLOAD] = 2.0
        if row[QTPLAST_C] == 0.0:
            row[QTROT_MIN] = row[QROT1N]
            row[QTMOM_MIN] = row[QMOM1N]
        tmom_min = row[QTMOM_MIN]
        trot_pu = row[QTROT_PU]
        if row[QTSTRAIN] > trot_pu:
            row[QKTANG] = par[QPE1P]
            row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
            if row[QTSTRESS] > row[QMOM1P]:
                row[QTSTRESS] = row[QMOM1P]
            if row[QTSTRESS] <= 0.0:
                row[QTSTRESS] = 0.0
                row[QKTANG] = par[QPEUP] * 1e-9
            return
        phase = int(row[QTPHASE])
        if phase == PLASTIC_T:
            row[QKTANG] = tmom_min / (row[QTROT_MIN] - trot_pu)
            row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_pu)
        elif phase == ELASTIC or phase == UNLOAD_T:
            if int(row[QTUNLOAD_T]) == ELASTIC:
                row[QKTANG] = tmom_min / (row[QTROT_MIN] - trot_pu)
                row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
            elif int(row[QTUNLOAD_T]) == PLASTIC_T or int(row[QTUNLOAD_T]) == RELOAD_T:
                row[QKTANG] = tmom_min / (row[QTROT_MIN] - trot_pu)
                row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_pu)
        elif phase == UNLOAD_C:
            if int(row[QTUNLOAD_C]) == ELASTIC or int(row[QTUNLOAD_C]) == PLASTIC_C:
                row[QKTANG] = par[QPE1N]
                row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
            elif int(row[QTUNLOAD_C]) == RELOAD_C:
                if row[QTSTRAIN] > row[QTROT_LIM_NU]:
                    row[QKTANG] = par[QPE1N]
                    row[QTSTRESS] = row[QCSTRESS] + row[QKTANG] * dstrain
                else:
                    row[QKTANG] = _quad_tangent_reload_c(row, par)
                    row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_pu)
        elif phase == RELOAD_T:
            row[QKTANG] = tmom_min / (row[QTROT_MIN] - trot_pu)
            row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_pu)
        elif phase == RELOAD_C:
            row[QKTANG] = _quad_tangent_reload_c(row, par)
            row[QTSTRESS] = row[QKTANG] * (row[QTSTRAIN] - trot_pu)

    @njit(cache=True, nogil=True)
    def _evaluate_quad_takeda_batch(params, state, strains, dns, volumes, sigma_initial):
        for i in range(state.shape[0]):
            row = state[i]
            par = params[i]
            if par[QPENABLED] == 0.0:
                continue
            strain = strains[i]
            if int(par[QPSUBLAW]) == QUAD_SUBLAW_HYSTERETIC:
                _evaluate_linear_serial_batch(
                    params[i:i+1, QHPARAMS:], state[i:i+1, QHCOMMITTED:QHTRIAL],
                    state[i:i+1, QHTRIAL:], strains[i:i+1], par[QPENABLED:QPENABLED+1],
                )
                _mirror_hysteretic_quad(row)
                continue
            if int(par[QPSUBLAW]) == QUAD_SUBLAW_ELASTIC:
                row[QDN] = 0.0
                row[QTSTRAIN] = strain
                row[QTSTRESS] = par[QPK] * strain
                row[QKTANG] = par[QPK]
                row[QTPHASE] = ELASTIC
                continue
            dn = dns[i]
            row[QDN] = dn
            if int(row[QTLOAD]) == 0 and strain == 0.0:
                continue
            _quad_revert_trial(row)
            row[QTSTRAIN] = strain
            dstrain = strain - row[QCSTRAIN]
            if int(par[QPHYSTERETIC_TYPE]) == QUAD_HYSTERETIC_INITIAL:
                phase = int(row[QPHASE])
                tphase = phase
                cstress = row[QCSTRESS]
                tstress = cstress
                ktang = row[QKTANG_COMMITTED]
                h = par[QPH]
                k = par[QPK]
                cohesion = par[QPCOHESION]
                mu = par[QPMU]
                e1p = par[QPE1P]
                e2p = par[QPE2P]
                tstress_normal = row[QTSTRESS_NORMAL]

                if phase == RUPTURE:
                    row[QTSTRESS] = cstress
                    row[QTSTRESS_NORMAL] += dn
                    row[QTENERGY] = row[QCENERGY]
                    row[QTPHASE] = tphase
                    row[QKTANG] = ktang
                    continue

                mom1p = _quad_tau_limit(par, tstress_normal)
                c_hard = cohesion + h * abs(row[QCUP])
                fy0 = max(0.0, c_hard + mu * tstress_normal) if cohesion != 0.0 else 0.0
                rot1p = mom1p / e1p if e1p != 0.0 else 0.0
                if e2p < 0.0:
                    mom2p = 0.0
                    rot2p = rot1p - mom1p / e2p
                else:
                    rot2p = rot1p
                    mom2p = mom1p
                rot3p = rot2p * 1.0001
                mom1n = -mom1p
                rot1n = -rot1p
                mom2n = -mom2p
                rot2n = -rot2p
                rot3n = -rot3p
                if phase == RUPTURE and mom1p == 0.0:
                    row[QTSTRESS] = 0.0
                    row[QKTANG] = 0.0
                    row[QTSTRESS_NORMAL] += dn
                    row[QTENERGY] = row[QCENERGY]
                    continue

                num3 = cstress + k * dstrain
                if abs(num3) - fy0 > 0.0:
                    if num3 > 0.0:
                        tphase = PLASTIC_T
                        sign = 1.0
                    else:
                        tphase = PLASTIC_C
                        sign = -1.0
                    num5 = (abs(num3) - fy0) / k if k != 0.0 else 0.0
                    num6 = k * num5 / (h + k) if (h + k) != 0.0 else 0.0
                    fy0 += h * num6
                    tstress = fy0 * sign
                    if tphase == PLASTIC_T and tstress < 0.0:
                        tphase = RUPTURE
                        tstress = 0.0
                        ktang = 0.0
                    elif tphase == PLASTIC_C and tstress > 0.0:
                        tphase = RUPTURE
                        tstress = 0.0
                        ktang = 0.0
                    else:
                        row[QTUP] += num6
                        ktang = e2p
                else:
                    tstress = num3
                    ktang = k
                    tphase = ELASTIC

                row[QTENERGY] = row[QCENERGY] + 0.5 * (cstress + tstress) * dstrain
                row[QTSTRESS_NORMAL] += dn
                row[QFY0] = fy0
                row[QFY1] = -fy0
                row[QTSTRESS] = tstress
                row[QTPHASE] = tphase
                row[QKTANG] = ktang
                row[QMOM1P] = mom1p
                row[QMOM1N] = mom1n
                row[QROT1P] = rot1p
                row[QROT1N] = rot1n
                row[QMOM2P] = mom2p
                row[QMOM2N] = mom2n
                row[QROT2P] = rot2p
                row[QROT2N] = rot2p
                row[QROT3P] = rot3p
                row[QROT3N] = rot3n
                continue
            tau = _quad_tau_limit(par, row[QTSTRESS_NORMAL])
            rot1p = tau / par[QPE1P] if par[QPE1P] != 0.0 else 0.0
            if int(par[QPFRACTURE_MODE]) in (
                QUAD_FRACTURE_FIXED, QUAD_FRACTURE_INTERPOLATED
            ):
                ultimate = _quad_shear_ultimate_strain(
                    par, tau, rot1p, volumes[i], sigma_initial[i]
                )
                row[QUR0] = ultimate
                row[QUR1] = -ultimate
                row[QMOM1P] = tau
                row[QMOM2P] = tau
                row[QROT1P] = rot1p
                row[QROT2P] = max(ultimate, rot1p * 1.0001)
                row[QROT3P] = max(ultimate, row[QROT2P] * 1.0001)
            else:
                row[QMOM1P] = tau
                row[QROT1P] = rot1p
                if par[QPE3P] < 0.0:
                    rot2p = par[QPPLASTIC_STRAIN]
                    candidate = rot1p * 1.0001
                    if candidate > rot2p:
                        rot2p = candidate
                    row[QROT2P] = rot2p
                    row[QROT3P] = rot2p - row[QMOM2P] / par[QPE3P]
                if row[QROT2P] < rot1p:
                    row[QROT2P] = rot1p * 1.0001
                if row[QROT3P] < row[QROT2P]:
                    row[QROT3P] = row[QROT2P] * 1.0001
                row[QMOM2P] = tau + par[QPE2P] * (row[QROT2P] - rot1p)
            row[QMOM1N] = -row[QMOM1P]
            row[QROT1N] = -row[QROT1P]
            row[QMOM2N] = -row[QMOM2P]
            row[QROT2N] = -row[QROT2P]
            row[QROT3N] = -row[QROT3P]
            row[QFY0] = row[QMOM1P]
            row[QFY1] = row[QMOM1N]
            if row[QMOM1P] == 0.0:
                row[QTPHASE] = 10.0
                row[QTSTRESS] = 0.0
                row[QKTANG] = 0.0
                row[QTENERGY] = row[QCENERGY] + 0.5 * (row[QCSTRESS] + row[QTSTRESS]) * dstrain
                row[QTSTRESS_NORMAL] += dn
                continue
            if int(row[QPHASE]) == 10:
                row[QTLOAD] = 0.0
                row[QTPHASE] = ELASTIC
                row[QTPLAST_T] = 1.0
                row[QTPLAST_C] = 1.0
                row[QTROT_NU] = row[QCSTRAIN]
                row[QTROT_PU] = row[QCSTRAIN]
                row[QKTANG] = par[QPE2P]
                row[QTANG_RELOAD_C] = row[QKTANG]
                row[QTANG_RELOAD_T] = row[QKTANG]
                row[QTSTRESS] = row[QKTANG] * dstrain
                row[QTROT_MAX] = row[QCSTRAIN] + row[QROT1P]
                row[QTMOM_MAX] = row[QKTANG] * row[QROT1P]
                row[QTROT_MIN] = row[QCSTRAIN] + row[QROT1N]
                row[QTMOM_MIN] = row[QKTANG] * row[QROT1N]
                if dstrain > 0.0:
                    row[QTLOAD] = 1.0
                    row[QTPHASE] = RELOAD_T
                else:
                    row[QTPHASE] = RELOAD_C
                    row[QTLOAD] = 2.0
                if abs(row[QTSTRESS]) - row[QMOM1P] > 0.0:
                    sign = 1.0 if row[QTSTRESS] > 0.0 else -1.0
                    row[QTSTRESS] = row[QMOM1P] * sign
                    if sign > 0.0:
                        row[QTPHASE] = PLASTIC_T
                        row[QTMOM_MAX] = row[QTSTRESS]
                        row[QTROT_MAX] = row[QTSTRAIN]
                    else:
                        row[QTPHASE] = PLASTIC_C
                        row[QTMOM_MIN] = row[QTSTRESS]
                        row[QTROT_MIN] = row[QTSTRAIN]
                row[QTENERGY] = row[QCENERGY] + 0.5 * (row[QCSTRESS] + row[QTSTRESS]) * dstrain
                row[QTSTRESS_NORMAL] += dn
                continue
            if int(row[QPHASE]) == RUPTURE_T or int(row[QPHASE]) == RUPTURE_C:
                row[QTSTRESS] = 0.0
                row[QKTANG] = 0.0
                row[QTENERGY] = row[QCENERGY] + 0.5 * row[QCSTRESS] * dstrain
                row[QTSTRESS_NORMAL] += dn
                continue
            row[QTROT_YP] = _quad_yield_tension(row, par, int(row[QCUNLOAD_T]), dstrain)
            row[QTROT_YN] = _quad_yield_compression(row, par, int(row[QCUNLOAD_C]), dstrain)
            if int(row[QTLOAD]) == 0:
                row[QTLOAD] = 1.0 if dstrain >= 0.0 else 2.0
            if row[QTSTRAIN] >= row[QTROT_YP] and dstrain > 0.0:
                row[QTROT_MAX] = row[QTSTRAIN]
                yp = row[QTROT_YP] if row[QTPLAST_T] != 0.0 else row[QROT1P]
                if row[QTSTRAIN] < yp:
                    row[QTPHASE] = ELASTIC
                    row[QKTANG] = par[QPE1P]
                elif row[QTSTRAIN] <= row[QROT2P]:
                    row[QTPHASE] = PLASTIC_T
                    row[QKTANG] = par[QPE2P]
                elif row[QTSTRAIN] <= row[QROT3P]:
                    row[QTPHASE] = PLASTIC_T
                    row[QKTANG] = par[QPE3P]
                else:
                    row[QTPHASE] = RUPTURE_T
                    row[QKTANG] = par[QPE1P] * 1e-9
                if row[QTSTRAIN] < yp:
                    row[QTSTRESS] = par[QPE1P] * row[QTSTRAIN]
                elif row[QTSTRAIN] <= row[QROT2P]:
                    row[QTSTRESS] = row[QMOM1P] + par[QPE2P] * (row[QTSTRAIN] - yp)
                elif row[QTSTRAIN] <= row[QROT3P]:
                    row[QTSTRESS] = row[QMOM2P] + par[QPE3P] * (row[QTSTRAIN] - row[QROT2P])
                else:
                    row[QTSTRESS] = row[QMOM3P]
                row[QTLOAD] = 1.0
                num5 = (row[QTSTRESS] - row[QCSTRESS]) / par[QPE1P] if par[QPE1P] != 0.0 else 0.0
                row[QTUP] += dstrain - num5
                if int(row[QTPHASE]) == PLASTIC_T:
                    row[QTPLAST_T] = 1.0
                row[QTMOM_MAX] = row[QTSTRESS]
            elif row[QTSTRAIN] <= row[QTROT_YN] and dstrain < 0.0:
                row[QTROT_MIN] = row[QTSTRAIN]
                yn = row[QTROT_YN] if int(row[QTUNLOAD_C]) != ELASTIC else row[QROT1N]
                if row[QTSTRAIN] > row[QTROT_PU]:
                    row[QKTANG] = par[QPE1N] * 1e-9
                elif row[QTSTRAIN] > yn:
                    row[QTPHASE] = ELASTIC
                    row[QKTANG] = par[QPE1N]
                elif row[QTSTRAIN] >= row[QROT2N]:
                    row[QTPHASE] = PLASTIC_C
                    row[QKTANG] = par[QPE2N]
                elif row[QTSTRAIN] >= row[QROT3N]:
                    row[QTPHASE] = PLASTIC_C
                    row[QKTANG] = par[QPE3N]
                else:
                    row[QTPHASE] = RUPTURE_C
                    row[QKTANG] = par[QPE1N] * 1e-9
                yn2 = row[QTROT_YN] if row[QTPLAST_C] != 0.0 else row[QROT1N]
                if row[QTSTRAIN] > yn2:
                    row[QTSTRESS] = par[QPE1N] * row[QTSTRAIN]
                elif row[QTSTRAIN] >= row[QROT2N]:
                    row[QTSTRESS] = row[QMOM1N] + par[QPE2N] * (row[QTSTRAIN] - yn2)
                elif row[QTSTRAIN] >= row[QROT3N]:
                    row[QTSTRESS] = row[QMOM2N] + par[QPE3N] * (row[QTSTRAIN] - row[QROT2N])
                else:
                    row[QTSTRESS] = row[QMOM3N]
                row[QTLOAD] = 2.0
                num6 = (row[QTSTRESS] - row[QCSTRESS]) / par[QPE1N] if par[QPE1N] != 0.0 else 0.0
                row[QTUP] += dstrain - num6
                if int(row[QTPHASE]) == PLASTIC_C:
                    row[QTPLAST_C] = 1.0
                row[QTMOM_MIN] = row[QTSTRESS]
            elif dstrain < 0.0:
                _quad_negative_increment(row, par, dstrain)
                if row[QTSTRESS] > 0.0:
                    row[QTPHASE] = UNLOAD_T
                elif int(row[QTPHASE]) == UNLOAD_C:
                    row[QTPHASE] = UNLOAD_C
                    if row[QTSTRAIN] <= row[QTROT_LIM_NU] and int(row[QCUNLOAD_C]) == RELOAD_C:
                        row[QTPHASE] = RELOAD_C
                else:
                    row[QTPHASE] = RELOAD_C
            elif dstrain > 0.0:
                _quad_positive_increment(row, par, dstrain)
                if row[QTSTRESS] < 0.0:
                    row[QTPHASE] = UNLOAD_C
                elif int(row[QTPHASE]) == UNLOAD_T:
                    row[QTPHASE] = UNLOAD_T
                    if row[QTSTRAIN] >= row[QTROT_LIM_PU] and int(row[QCUNLOAD_T]) == RELOAD_T:
                        row[QTPHASE] = RELOAD_T
                else:
                    row[QTPHASE] = RELOAD_T
            row[QTENERGY] = row[QCENERGY] + 0.5 * (row[QCSTRESS] + row[QTSTRESS]) * dstrain
            row[QTSTRESS_NORMAL] += dn

    @njit(cache=True, nogil=True)
    def _commit_quad_takeda_batch(params, state):
        for i in range(state.shape[0]):
            if params[i, QPENABLED] == 0.0:
                continue
            row = state[i]
            if int(params[i, QPSUBLAW]) == QUAD_SUBLAW_HYSTERETIC:
                for j in range(9):
                    row[QHCOMMITTED + j] = row[QHTRIAL + j]
                row[QKTANG_COMMITTED] = row[QHTRIAL + 9]
                _mirror_hysteretic_quad(row)
                continue
            row[QFY1] = -row[QFY0]
            row[QCUP] = row[QTUP]
            row[QUMAX0] = row[QTROT_MAX]
            row[QUMAX1] = row[QTROT_MIN]
            row[QCROT_PU] = row[QTROT_PU]
            row[QCROT_NU] = row[QTROT_NU]
            row[QCENERGY] = row[QTENERGY]
            row[QCLOAD] = row[QTLOAD]
            row[QCSTRESS_NORMAL_PREV] = row[QCSTRESS_NORMAL]
            row[QCSTRESS] = row[QTSTRESS]
            row[QCSTRAIN] = row[QTSTRAIN]
            row[QCSTRESS_NORMAL] = row[QTSTRESS_NORMAL]
            row[QCCONTACT] = row[QTCONTACT]
            row[QDN] = 0.0
            row[QKTANG_COMMITTED] = row[QKTANG]
            row[QPHASE] = row[QTPHASE]
            row[QCMOM_MAX] = row[QTMOM_MAX]
            row[QCMOM_MIN] = row[QTMOM_MIN]
            row[QCROT_LIM_PU] = row[QTROT_LIM_PU]
            row[QCROT_LIM_NU] = row[QTROT_LIM_NU]
            row[QCROT_YP] = row[QTROT_YP]
            row[QCROT_YN] = row[QTROT_YN]
            phase = int(row[QPHASE])
            if phase == PLASTIC_T:
                row[QTUNLOAD_T] = phase
            elif phase == PLASTIC_C:
                row[QTUNLOAD_C] = phase
            elif phase == RELOAD_T:
                if row[QTPLAST_T] == 0.0 and row[QTPLAST_C] == 0.0:
                    row[QTUNLOAD_T] = ELASTIC
                else:
                    row[QTUNLOAD_T] = phase
                    row[QTPLAST_T] = 1.0
                row[QTANG_RELOAD_T] = row[QKTANG]
            elif phase == RELOAD_C:
                if row[QTPLAST_T] == 0.0 and row[QTPLAST_C] == 0.0:
                    row[QTUNLOAD_C] = ELASTIC
                else:
                    row[QTUNLOAD_C] = phase
                    row[QTPLAST_C] = 1.0
                row[QTANG_RELOAD_C] = row[QKTANG]
            row[QCPLAST_C] = row[QTPLAST_C]
            row[QCPLAST_T] = row[QTPLAST_T]
            row[QCUNLOAD_T] = row[QTUNLOAD_T]
            row[QCUNLOAD_C] = row[QTUNLOAD_C]


else:  # pragma: no cover - exercised when numba is unavailable
    _quad_tau_limit = None
    _mirror_hysteretic_quad = None
    _revert_hysteretic_quad = None
    _quad_interpolated_shear_energy = None
    _quad_shear_ultimate_strain = None
    _evaluate_quad_takeda_batch = None
    _commit_quad_takeda_batch = None
