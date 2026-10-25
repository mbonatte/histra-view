"""Compiled transverse hysteretic kernels (C# SpringHysteretic state machine).

The nonlinear benchmark updates thousands of independent transverse springs on
nearly every Newton correction, so the supported linear and
exponential-tension hysteretic laws are evaluated in one compiled loop over
dense parameter/state arrays. The generic evaluator
(``_evaluate_linear_batch``), the zero-pinching/zero-damage specialization
(``_evaluate_simple_linear_batch`` and its fused advance/finish variants) and
the shared float64 stress/tangent/rotation-limit envelopes live here.

Numerical notes that must survive any refactor:

* kernels preserve complete state-array differentials, not only final forces;
* no ``fastmath`` is used anywhere (parity-sensitive reductions);
* ``prange`` scheduling was measured slower than serial loops at the current
  batch sizes, so the parallel loops here are deliberate and covered by
  regression ceilings;
* the dense parameter/state column constants below are part of the compiled
  contract; changing them changes every kernel.
"""
from __future__ import annotations

import numpy as np

from histra.types.phase_enum import PhaseEnum

try:  # optional acceleration dependency
    from numba import njit, prange
except Exception:  # pragma: no cover - exercised when numba is unavailable
    njit = None
    prange = None


ELASTIC = int(PhaseEnum.Elastic)
PLASTIC_T = int(PhaseEnum.Plastic_t)
PLASTIC_C = int(PhaseEnum.Plastic_c)
UNLOAD_T = int(PhaseEnum.Unload_t)
UNLOAD_C = int(PhaseEnum.Unload_c)
RELOAD_T = int(PhaseEnum.Reload_t)
RELOAD_C = int(PhaseEnum.Reload_c)
RUPTURE = int(PhaseEnum.Rupture)
RUPTURE_T = int(PhaseEnum.RuptureTraz)
RUPTURE_C = int(PhaseEnum.RuptureComp)

# Positive-envelope dispatch stored in the final dense parameter column.
# Existing numeric parameter indices remain unchanged.
TENSILE_ELASTIC = -1  # SpringLinearElastic, without hysteretic phase/history.
TENSILE_LINEAR = 0
TENSILE_EXPONENTIAL = 1
TENSILE_CURVE_TYPE_PARAM = 32
COMPRESSIVE_LINEAR = 0
COMPRESSIVE_PARABOLIC = 1
COMPRESSIVE_CURVE_TYPE_PARAM = 33
TRANSVERSE_PARAM_SIZE = 34


_PARAM_NAMES = (
    "pinch_xp", "pinch_yp", "pinch_xn", "pinch_yn",
    "damfc1p", "damfc2p", "damfc1n", "damfc2n", "betap", "betan",
    "rot1p", "mom1p", "rot2p", "mom2p", "rot3p", "mom3p",
    "mom1n", "rot1n", "rot2n", "mom2n", "rot3n", "mom3n",
    "e1n", "e1p", "e2n", "e2p", "e3n", "e3p", "eun", "eup",
    "energy_a", "k",
)

# Generated masonry interface fibres use the zero-pinching/zero-damage
# specialization below.  The specialized kernel never reads parameter columns
# 0..9 (pinching/damage/beta), ``energy_a`` (column 30), or ``k`` (column 31).
# Keeping those twelve float64 values for every one of the ~550k transverse
# fibres in a representative bridge costs about 50 MiB with no numerical use.
# A compact runtime therefore stores only columns 10..29 plus the tensile-law
# discriminator.  The generic layout remains unchanged for non-simple springs
# and for the diagnostic force-general switch.
SIMPLE_PARAM_NAMES = _PARAM_NAMES[10:30]
SIMPLE_TENSILE_CURVE_TYPE_PARAM = len(SIMPLE_PARAM_NAMES)
LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE = len(SIMPLE_PARAM_NAMES)
SIMPLE_TRANSVERSE_PARAM_SIZE = SIMPLE_TENSILE_CURVE_TYPE_PARAM + 1


if njit is not None:
    @njit(cache=True, inline="always")
    def _pos_stress(strain, rot1p, mom1p, rot2p, mom2p, rot3p, mom3p, e1p, e2p, e3p):
        if strain <= 0.0:
            return 0.0
        if strain <= rot1p:
            return e1p * strain
        if strain <= rot2p:
            return mom1p + e2p * (strain - rot1p)
        if strain <= rot3p or e3p > 0.0:
            return mom2p + e3p * (strain - rot2p)
        return mom3p

    @njit(cache=True, inline="always")
    def _pos_stress_typed(
        curve_type, strain, rot1p, mom1p, rot2p, mom2p, rot3p, mom3p,
        e1p, e2p, e3p,
    ):
        if curve_type == TENSILE_EXPONENTIAL:
            if strain <= 0.0:
                return 0.0
            if strain <= rot1p:
                return e1p * strain
            denominator = rot2p - rot1p
            # C# floating-point evaluation tends to zero for the degenerate
            # positive-increment case; avoid a Numba ZeroDivisionError.
            if denominator == 0.0:
                return 0.0
            return mom1p * np.exp(-(strain - rot1p) / denominator)
        return _pos_stress(
            strain, rot1p, mom1p, rot2p, mom2p, rot3p, mom3p,
            e1p, e2p, e3p,
        )

    @njit(cache=True, inline="always")
    def _neg_stress(strain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n):
        if strain >= 0.0:
            return 0.0
        if strain >= rot1n:
            return e1n * strain
        if strain >= rot2n:
            return mom1n + e2n * (strain - rot1n)
        if strain >= rot3n or e3n > 0.0:
            return mom2n + e3n * (strain - rot2n)
        return mom3n

    @njit(cache=True, inline="always")
    def _neg_stress_typed(
        curve_type, strain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
        e1n, e2n, e3n,
    ):
        if curve_type == COMPRESSIVE_PARABOLIC:
            if strain >= 0.0:
                return 0.0
            if strain >= rot1n:
                return mom1n * strain / rot1n if rot1n != 0.0 else 0.0
            if strain >= rot2n:
                denominator = rot2n - rot1n
                r = (strain - rot1n) / denominator if denominator != 0.0 else 0.0
                return mom1n * (1.0 + 4.0 * r - 2.0 * r * r)
            if strain >= rot3n:
                denominator = rot3n - rot2n
                r = (strain - rot2n) / denominator if denominator != 0.0 else 0.0
                return mom2n * (1.0 - r * r)
            return 0.0
        return _neg_stress(
            strain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n
        )

    @njit(cache=True, inline="always")
    def _pos_tangent(strain, rot1p, rot2p, rot3p, e1p, e2p, e3p):
        if strain < 0.0:
            return e1p * 1.0e-9, ELASTIC
        if strain <= rot1p:
            return e1p, ELASTIC
        if strain <= rot2p:
            return e2p, PLASTIC_T
        if strain <= rot3p or e3p > 0.0:
            return e3p, PLASTIC_T
        return e1p * 1.0e-9, RUPTURE_T

    @njit(cache=True, inline="always")
    def _pos_tangent_typed(
        curve_type, strain, rot1p, rot2p, rot3p, e1p, e2p, e3p,
        tstress, cstress, cstrain,
    ):
        if curve_type == TENSILE_EXPONENTIAL:
            if strain < 0.0:
                return e1p * 1.0e-9, ELASTIC
            if strain <= rot1p:
                return e1p, ELASTIC
            dstrain = strain - cstrain
            if dstrain != 0.0:
                return (tstress - cstress) / dstrain, PLASTIC_T
            # The scalar Python implementation protects this otherwise
            # undefined repeated-trial case while retaining Plastic_t phase.
            return e1p, PLASTIC_T
        return _pos_tangent(strain, rot1p, rot2p, rot3p, e1p, e2p, e3p)

    @njit(cache=True, inline="always")
    def _neg_tangent(strain, rot1n, rot2n, rot3n, e1n, e2n, e3n):
        if strain > 0.0:
            return e1n * 1.0e-9, ELASTIC
        if strain >= rot1n:
            return e1n, ELASTIC
        if strain >= rot2n:
            return e2n, PLASTIC_C
        if strain >= rot3n or e3n > 0.0:
            return e3n, PLASTIC_C
        return e1n * 1.0e-9, RUPTURE_C

    @njit(cache=True, inline="always")
    def _neg_tangent_typed(
        curve_type, strain, rot1n, rot2n, rot3n, e1n, e2n, e3n,
        tstress, cstress, cstrain,
    ):
        if curve_type == COMPRESSIVE_PARABOLIC:
            if strain > 0.0:
                return e1n * 1.0e-9, ELASTIC
            if strain >= rot1n:
                return e1n, ELASTIC
            if strain >= rot2n:
                dstrain = strain - cstrain
                if dstrain != 0.0:
                    return (tstress - cstress) / dstrain, ELASTIC
                return e1n, ELASTIC
            if strain >= rot3n:
                dstrain = strain - cstrain
                if dstrain != 0.0:
                    return (tstress - cstress) / dstrain, PLASTIC_C
                return e1n, PLASTIC_C
            return e1n * 1.0e-9, RUPTURE_C
        return _neg_tangent(strain, rot1n, rot2n, rot3n, e1n, e2n, e3n)

    @njit(cache=True, inline="always")
    def _pos_rotlim(strain, rot1p, mom1p, rot2p, mom2p, e2p, e3p,
                    rot3p, mom3p, e1p):
        result = np.inf
        if strain <= rot1p:
            return result
        if strain <= rot2p and e2p < 0.0 and e2p != 0.0:
            result = rot1p - mom1p / e2p
        if strain > rot2p and e3p < 0.0 and e3p != 0.0:
            result = rot2p - mom2p / e3p
        if np.isinf(result):
            return result
        if _pos_stress(result, rot1p, mom1p, rot2p, mom2p, rot3p, mom3p, e1p, e2p, e3p) > 0.0:
            return np.inf
        return result

    @njit(cache=True, inline="always")
    def _pos_rotlim_typed(
        curve_type, strain, rot1p, mom1p, rot2p, mom2p, e2p, e3p,
        rot3p, mom3p, e1p,
    ):
        result = np.inf
        if strain <= rot1p:
            return result
        if strain <= rot2p and e2p < 0.0 and e2p != 0.0:
            result = rot1p - mom1p / e2p
        if strain > rot2p and e3p < 0.0 and e3p != 0.0:
            result = rot2p - mom2p / e3p
        if np.isinf(result):
            return result
        if _pos_stress_typed(
            curve_type, result, rot1p, mom1p, rot2p, mom2p, rot3p,
            mom3p, e1p, e2p, e3p,
        ) > 0.0:
            return np.inf
        return result

    @njit(cache=True, inline="always")
    def _neg_rotlim(strain, mom1n, rot1n, rot2n, mom2n, e2n, e3n,
                    rot3n, mom3n, e1n):
        result = -np.inf
        if strain >= rot1n:
            return result
        if strain >= rot2n and e2n < 0.0 and e2n != 0.0:
            result = rot1n - mom1n / e2n
        if strain < rot2n and e3n < 0.0 and e3n != 0.0:
            result = rot2n - mom2n / e3n
        if np.isinf(result):
            return result
        if _neg_stress(result, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n) < 0.0:
            return -np.inf
        return result

    @njit(cache=True, inline="always")
    def _neg_rotlim_typed(
        curve_type, strain, mom1n, rot1n, rot2n, mom2n, e2n, e3n,
        rot3n, mom3n, e1n,
    ):
        # C# ``negEnvlpRotlim`` uses only the linear envelope slopes.  The
        # parabolic branch has no such zero-crossing slope and therefore keeps
        # the historical -infinity limit.
        if curve_type == COMPRESSIVE_PARABOLIC:
            return -np.inf
        return _neg_rotlim(
            strain, mom1n, rot1n, rot2n, mom2n, e2n, e3n,
            rot3n, mom3n, e1n,
        )

    @njit(cache=True, nogil=True, parallel=True)
    def _evaluate_linear_batch(params, committed, trial, targets, enabled):
        n = targets.size
        for i in prange(n):
            if not enabled[i]:
                continue
            if (params.shape[1] > TENSILE_CURVE_TYPE_PARAM
                    and params[i, TENSILE_CURVE_TYPE_PARAM] == TENSILE_ELASTIC):
                # Original SpringLinearElastic.setTrialStrain is incremental.
                trial[i, 6] = committed[i, 6] + trial[i, 9] * (targets[i] - committed[i, 7])
                trial[i, 7] = targets[i]
                trial[i, 8] = ELASTIC
                continue
            previous_tload = int(trial[i, 5])
            strain = targets[i]
            if previous_tload == 0 and strain == 0.0:
                continue

            pinch_xp, pinch_yp, pinch_xn, pinch_yn = params[i, 0], params[i, 1], params[i, 2], params[i, 3]
            damfc1p, damfc2p, damfc1n, damfc2n = params[i, 4], params[i, 5], params[i, 6], params[i, 7]
            betap, betan = params[i, 8], params[i, 9]
            rot1p, mom1p, rot2p, mom2p = params[i, 10], params[i, 11], params[i, 12], params[i, 13]
            rot3p, mom3p = params[i, 14], params[i, 15]
            mom1n, rot1n, rot2n, mom2n = params[i, 16], params[i, 17], params[i, 18], params[i, 19]
            rot3n, mom3n = params[i, 20], params[i, 21]
            e1n, e1p, e2n, e2p = params[i, 22], params[i, 23], params[i, 24], params[i, 25]
            e3n, e3p, eun, eup = params[i, 26], params[i, 27], params[i, 28], params[i, 29]
            energy_a = params[i, 30]
            tensile_curve_type = TENSILE_LINEAR
            if params.shape[1] > TENSILE_CURVE_TYPE_PARAM:
                tensile_curve_type = int(params[i, TENSILE_CURVE_TYPE_PARAM])
            compressive_curve_type = COMPRESSIVE_LINEAR
            if params.shape[1] > COMPRESSIVE_CURVE_TYPE_PARAM:
                compressive_curve_type = int(params[i, COMPRESSIVE_CURVE_TYPE_PARAM])

            umax_p, umax_n = committed[i, 0], committed[i, 1]
            trot_pu, trot_nu = committed[i, 2], committed[i, 3]
            cenergy = committed[i, 4]
            tload = int(committed[i, 5])
            cstress, cstrain = committed[i, 6], committed[i, 7]
            phase = int(committed[i, 8])

            trot_max, trot_min = umax_p, umax_n
            tstress, tstrain, tphase = cstress, strain, phase
            ktang = trial[i, 9]
            dstrain = tstrain - cstrain
            if tload == 0:
                tload = 1 if dstrain >= 0.0 else 2

            if phase == RUPTURE or phase == RUPTURE_C or phase == RUPTURE_T:
                tstress = 0.0
                ktang = 0.0
                if tstrain >= umax_p:
                    trot_max = tstrain
                elif tstrain <= umax_n:
                    trot_min = tstrain

            if tstrain >= umax_p:
                trot_max = tstrain
                tstress = _pos_stress_typed(
                    tensile_curve_type, tstrain, rot1p, mom1p, rot2p, mom2p,
                    rot3p, mom3p, e1p, e2p, e3p,
                )
                ktang, tphase = _pos_tangent_typed(
                    tensile_curve_type, tstrain, rot1p, rot2p, rot3p,
                    e1p, e2p, e3p, tstress, cstress, cstrain,
                )
                tload = 1
            elif tstrain <= umax_n:
                trot_min = tstrain
                tstress = _neg_stress_typed(compressive_curve_type, tstrain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n)
                ktang, tphase = _neg_tangent_typed(compressive_curve_type, tstrain, rot1n, rot2n, rot3n, e1n, e2n, e3n, tstress, cstress, cstrain)
                tload = 2
            elif dstrain < 0.0:
                tphase = UNLOAD_T if tstress > 0.0 else RELOAD_C
                num = (umax_n / rot1n) ** betan if rot1n != 0.0 else 0.0
                if num <= 1.0:
                    num = 1.0
                else:
                    env = _neg_stress_typed(compressive_curve_type, umax_n, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n)
                    num = env / mom1n / num if num != 0.0 else 1.0
                num2 = (umax_p / rot1p) ** betap if rot1p != 0.0 else 0.0
                if num2 <= 1.0:
                    num2 = 1.0
                else:
                    env = _pos_stress_typed(
                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                    )
                    num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                if tload == 1:
                    tload = 2
                    if cstress >= 0.0:
                        denom = eup * num2
                        trot_pu = cstrain - cstress / denom if denom != 0.0 else 0.0
                        if _pos_stress_typed(
                            tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                            mom2p, rot3p, mom3p, e1p, e2p, e3p,
                        ) == 0.0:
                            trot_pu = 0.0
                        num3 = cenergy - 0.5 * cstress / denom * cstress if denom != 0.0 else cenergy
                        num4 = 0.0
                        if umax_p > rot1p:
                            num4 = damfc2n * num3 / energy_a if energy_a != 0.0 else 0.0
                            num4 += damfc1n * (umax_p - rot1p) / rot1p if rot1p != 0.0 else 0.0
                        trot_min = umax_n * (1.0 + num4)
                tload = 2
                if trot_min > rot1n:
                    trot_min = rot1n
                num5 = _neg_stress_typed(compressive_curve_type, trot_min, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n)
                num6 = _pos_rotlim_typed(
                    tensile_curve_type, umax_p, rot1p, mom1p, rot2p, mom2p,
                    e2p, e3p, rot3p, mom3p, e1p,
                )
                num7 = num6 if num6 < trot_pu else trot_pu
                denom = eun * num
                num8 = trot_min - (1.0 - pinch_yn) * num5 / denom if denom != 0.0 else trot_min
                if num == 0.0:
                    num8 = trot_min
                num9 = num7 + (num8 - num7) * pinch_xn
                if tstrain >= trot_pu:
                    ktang = eup * num2
                    tstress = cstress + ktang * dstrain
                    if tstress <= 0.0:
                        tstress = 0.0
                elif tstrain <= trot_pu and tstrain > num9:
                    if tstrain >= num7:
                        tstress = 0.0
                    else:
                        denom9 = num9 - num7
                        ktang = num5 * pinch_yn / denom9 if denom9 != 0.0 else 0.0
                        num10 = cstress + eun * num * dstrain
                        num11 = (tstrain - num7) * ktang
                        if num10 > num11:
                            tstress = num10
                            ktang = eun * num
                        else:
                            tstress = num11
                else:
                    denom9 = trot_min - num9
                    ktang = (1.0 - pinch_yn) * num5 / denom9 if denom9 != 0.0 else 0.0
                    num10 = cstress + eun * num * dstrain
                    num11 = pinch_yn * num5 + (tstrain - num9) * ktang
                    if num10 > num11:
                        tstress = num10
                        ktang = eun * num
                    else:
                        tstress = num11
                    if cstrain > trot_pu and tstrain < trot_pu:
                        ktang = eup * num2
                        tstress = cstress + ktang * (trot_pu - cstrain)
                        ktang = (1.0 - pinch_yn) * num5 / denom9 if denom9 != 0.0 else 0.0
                        tstress += ktang * (tstrain - trot_pu)
            elif dstrain > 0.0:
                tphase = RELOAD_T if tstress > 0.0 else UNLOAD_C
                num = (umax_n / rot1n) ** betan if rot1n != 0.0 else 0.0
                if num <= 1.0:
                    num = 1.0
                else:
                    env = _neg_stress_typed(compressive_curve_type, umax_n, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n)
                    num = env / mom1n / num if num != 0.0 else 1.0
                num2 = (umax_p / rot1p) ** betap if rot1p != 0.0 else 0.0
                if num2 <= 1.0:
                    num2 = 1.0
                else:
                    env = _pos_stress_typed(
                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                    )
                    num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                if tload == 2:
                    tload = 1
                    if cstress <= 0.0:
                        denom = eun * num
                        trot_nu = cstrain - cstress / denom if denom != 0.0 else 0.0
                        if _neg_stress_typed(compressive_curve_type, umax_n, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n, e1n, e2n, e3n) == 0.0:
                            trot_nu = 0.0
                        num3 = cenergy - 0.5 * cstress / denom * cstress if denom != 0.0 else cenergy
                        num4 = 0.0
                        if umax_n < rot1n:
                            num4 = damfc2p * num3 / energy_a if energy_a != 0.0 else 0.0
                            num4 += damfc1p * (umax_n - rot1n) / rot1n if rot1n != 0.0 else 0.0
                        trot_max = umax_p * (1.0 + num4)
                tload = 1
                if trot_max < rot1p:
                    trot_max = rot1p
                num5 = _pos_stress_typed(
                    tensile_curve_type, trot_max, rot1p, mom1p, rot2p, mom2p,
                    rot3p, mom3p, e1p, e2p, e3p,
                )
                num6 = _neg_rotlim_typed(compressive_curve_type, umax_n, mom1n, rot1n, rot2n, mom2n, e2n, e3n, rot3n, mom3n, e1n)
                num7 = num6 if num6 > trot_nu else trot_nu
                denom = eup * num2
                num8 = trot_max - (1.0 - pinch_yp) * num5 / denom if denom != 0.0 else trot_max
                if num2 == 0.0:
                    num8 = trot_max
                num9 = num7 + (num8 - num7) * pinch_xp
                if tstrain <= trot_nu:
                    ktang = eun * num
                    tstress = cstress + ktang * dstrain
                    if tstress >= 0.0:
                        tstress = 0.0
                elif trot_nu < tstrain < num9:
                    if tstrain <= num7:
                        tstress = 0.0
                    else:
                        denom9 = num9 - num7
                        ktang = num5 * pinch_yp / denom9 if denom9 != 0.0 else 0.0
                        num10 = cstress + eup * num2 * dstrain
                        num11 = (tstrain - num7) * ktang
                        if num10 < num11:
                            tstress = num10
                            ktang = eup * num2
                        else:
                            tstress = num11
                else:
                    denom9 = trot_max - num9
                    ktang = (1.0 - pinch_yp) * num5 / denom9 if denom9 != 0.0 else 0.0
                    num10 = cstress + eup * num2 * dstrain
                    num11 = pinch_yp * num5 + (tstrain - num9) * ktang
                    if num10 < num11:
                        tstress = num10
                        ktang = eup * num2
                    else:
                        tstress = num11
                    if cstrain < trot_nu and tstrain > trot_nu:
                        ktang = eun * num
                        tstress = cstress + ktang * (trot_nu - cstrain)
                        ktang = (1.0 - pinch_yp) * num5 / denom9 if denom9 != 0.0 else 0.0
                        tstress += ktang * (tstrain - trot_nu)

            tenergy = cenergy + 0.5 * (cstress + tstress) * dstrain
            trial[i, 0] = trot_max
            trial[i, 1] = trot_min
            trial[i, 2] = trot_pu
            trial[i, 3] = trot_nu
            trial[i, 4] = tenergy
            trial[i, 5] = tload
            trial[i, 6] = tstress
            trial[i, 7] = tstrain
            trial[i, 8] = tphase
            trial[i, 9] = ktang

    # Reuse the state machine without launching a parallel team for one row.
    _evaluate_linear_serial_batch = njit(cache=False, nogil=True)(_evaluate_linear_batch.py_func)

    @njit(cache=True, nogil=True, parallel=True)
    def _evaluate_simple_linear_batch(params, committed, trial, targets, enabled):
        """Specialized C# Hysteretic path for generated masonry fibers.

        PrepareModel creates these springs with zero pinching/damage,
        BetaP=1 and BetaN=0.  Algebraically removing the inactive pinching and
        damage branches avoids hundreds of millions of redundant operations
        while retaining the same state-transition ordering and envelope calls.
        """
        # Runtime-built simple batches may use the compact 21-column layout;
        # direct/unit callers can still pass the historical 33-column layout.
        # Only the storage indices differ.  The constitutive arithmetic below
        # is intentionally unchanged.
        compact = params.shape[1] <= SIMPLE_TRANSVERSE_PARAM_SIZE
        parameter_offset = 0 if compact else 10
        tensile_curve_column = (
            SIMPLE_TENSILE_CURVE_TYPE_PARAM
            if compact else TENSILE_CURVE_TYPE_PARAM
        )

        for i in prange(targets.size):
            if not enabled[i]:
                continue
            previous_tload = int(trial[i, 5])
            strain = targets[i]
            if previous_tload == 0 and strain == 0.0:
                continue

            rot1p, mom1p, rot2p, mom2p = (
                params[i, parameter_offset],
                params[i, parameter_offset + 1],
                params[i, parameter_offset + 2],
                params[i, parameter_offset + 3],
            )
            rot3p, mom3p = (
                params[i, parameter_offset + 4],
                params[i, parameter_offset + 5],
            )
            mom1n, rot1n, rot2n, mom2n = (
                params[i, parameter_offset + 6],
                params[i, parameter_offset + 7],
                params[i, parameter_offset + 8],
                params[i, parameter_offset + 9],
            )
            rot3n, mom3n = (
                params[i, parameter_offset + 10],
                params[i, parameter_offset + 11],
            )
            e1n, e1p, e2n, e2p = (
                params[i, parameter_offset + 12],
                params[i, parameter_offset + 13],
                params[i, parameter_offset + 14],
                params[i, parameter_offset + 15],
            )
            e3n, e3p, eun, eup = (
                params[i, parameter_offset + 16],
                params[i, parameter_offset + 17],
                params[i, parameter_offset + 18],
                params[i, parameter_offset + 19],
            )
            tensile_curve_type = TENSILE_LINEAR
            if params.shape[1] > tensile_curve_column:
                tensile_curve_type = int(params[i, tensile_curve_column])

            umax_p, umax_n = committed[i, 0], committed[i, 1]
            trot_pu, trot_nu = committed[i, 2], committed[i, 3]
            cenergy = committed[i, 4]
            tload = int(committed[i, 5])
            cstress, cstrain = committed[i, 6], committed[i, 7]
            phase = int(committed[i, 8])

            trot_max, trot_min = umax_p, umax_n
            tstress, tstrain, tphase = cstress, strain, phase
            ktang = trial[i, 9]
            dstrain = tstrain - cstrain
            if tload == 0:
                tload = 1 if dstrain >= 0.0 else 2

            if phase == RUPTURE or phase == RUPTURE_C or phase == RUPTURE_T:
                tstress = 0.0
                ktang = 0.0
                if tstrain >= umax_p:
                    trot_max = tstrain
                elif tstrain <= umax_n:
                    trot_min = tstrain

            if tstrain >= umax_p:
                trot_max = tstrain
                tstress = _pos_stress_typed(
                    tensile_curve_type, tstrain, rot1p, mom1p, rot2p,
                    mom2p, rot3p, mom3p, e1p, e2p, e3p,
                )
                ktang, tphase = _pos_tangent_typed(
                    tensile_curve_type, tstrain, rot1p, rot2p, rot3p,
                    e1p, e2p, e3p, tstress, cstress, cstrain,
                )
                tload = 1
            elif tstrain <= umax_n:
                trot_min = tstrain
                tstress = _neg_stress(
                    tstrain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
                    e1n, e2n, e3n,
                )
                ktang, tphase = _neg_tangent(
                    tstrain, rot1n, rot2n, rot3n, e1n, e2n, e3n,
                )
                tload = 2
            elif dstrain < 0.0:
                tphase = UNLOAD_T if tstress > 0.0 else RELOAD_C
                num = 1.0
                num2 = (umax_p / rot1p) ** 1.0 if rot1p != 0.0 else 0.0
                if num2 <= 1.0:
                    num2 = 1.0
                else:
                    env = _pos_stress_typed(
                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                    )
                    num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                if tload == 1:
                    tload = 2
                    if cstress >= 0.0:
                        denom = eup * num2
                        trot_pu = cstrain - cstress / denom if denom != 0.0 else 0.0
                        if _pos_stress_typed(
                            tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                            mom2p, rot3p, mom3p, e1p, e2p, e3p,
                        ) == 0.0:
                            trot_pu = 0.0
                        trot_min = umax_n
                tload = 2
                if trot_min > rot1n:
                    trot_min = rot1n
                num5 = _neg_stress(
                    trot_min, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
                    e1n, e2n, e3n,
                )
                num6 = _pos_rotlim_typed(
                    tensile_curve_type, umax_p, rot1p, mom1p, rot2p, mom2p,
                    e2p, e3p, rot3p, mom3p, e1p,
                )
                num7 = num6 if num6 < trot_pu else trot_pu
                if tstrain >= trot_pu:
                    ktang = eup * num2
                    tstress = cstress + ktang * dstrain
                    if tstress <= 0.0:
                        tstress = 0.0
                elif tstrain > num7:
                    tstress = 0.0
                else:
                    denom9 = trot_min - num7
                    ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                    num10 = cstress + eun * num * dstrain
                    num11 = (tstrain - num7) * ktang
                    if num10 > num11:
                        tstress = num10
                        ktang = eun * num
                    else:
                        tstress = num11
                    if cstrain > trot_pu and tstrain < trot_pu:
                        ktang = eup * num2
                        tstress = cstress + ktang * (trot_pu - cstrain)
                        ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                        tstress += ktang * (tstrain - trot_pu)
            elif dstrain > 0.0:
                tphase = RELOAD_T if tstress > 0.0 else UNLOAD_C
                num = 1.0
                num2 = (umax_p / rot1p) ** 1.0 if rot1p != 0.0 else 0.0
                if num2 <= 1.0:
                    num2 = 1.0
                else:
                    env = _pos_stress_typed(
                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                    )
                    num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                if tload == 2:
                    tload = 1
                    if cstress <= 0.0:
                        denom = eun * num
                        trot_nu = cstrain - cstress / denom if denom != 0.0 else 0.0
                        if _neg_stress(
                            umax_n, mom1n, rot1n, rot2n, mom2n,
                            rot3n, mom3n, e1n, e2n, e3n,
                        ) == 0.0:
                            trot_nu = 0.0
                        trot_max = umax_p
                tload = 1
                if trot_max < rot1p:
                    trot_max = rot1p
                num5 = _pos_stress_typed(
                    tensile_curve_type, trot_max, rot1p, mom1p, rot2p,
                    mom2p, rot3p, mom3p, e1p, e2p, e3p,
                )
                num6 = _neg_rotlim(
                    umax_n, mom1n, rot1n, rot2n, mom2n, e2n, e3n,
                    rot3n, mom3n, e1n,
                )
                num7 = num6 if num6 > trot_nu else trot_nu
                if tstrain <= trot_nu:
                    ktang = eun * num
                    tstress = cstress + ktang * dstrain
                    if tstress >= 0.0:
                        tstress = 0.0
                elif tstrain < num7:
                    tstress = 0.0
                else:
                    denom9 = trot_max - num7
                    ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                    num10 = cstress + eup * num2 * dstrain
                    num11 = (tstrain - num7) * ktang
                    if num10 < num11:
                        tstress = num10
                        ktang = eup * num2
                    else:
                        tstress = num11
                    if cstrain < trot_nu and tstrain > trot_nu:
                        ktang = eun * num
                        tstress = cstress + ktang * (trot_nu - cstrain)
                        ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                        tstress += ktang * (tstrain - trot_nu)

            tenergy = cenergy + 0.5 * (cstress + tstress) * dstrain
            trial[i, 0] = trot_max
            trial[i, 1] = trot_min
            trial[i, 2] = trot_pu
            trial[i, 3] = trot_nu
            trial[i, 4] = tenergy
            trial[i, 5] = tload
            trial[i, 6] = tstress
            trial[i, 7] = tstrain
            trial[i, 8] = tphase
            trial[i, 9] = ktang

    @njit(cache=True, nogil=True, parallel=True)
    def _advance_and_evaluate_simple_linear_batch(
        params, committed, trial, targets, enabled,
        record_index, kin_num, kin_num2, di, dj, lengths, delta_flex, ecc,
    ):
        """Advance transverse target strain and evaluate the simple law in one pass.

        The target expression and constitutive arithmetic are intentionally the
        same as the separate production kernels. ``targets`` is still populated
        so snapshots/diagnostics retain the historical dense state.
        """
        # Runtime-built simple batches may use the compact 21-column layout;
        # direct/unit callers can still pass the historical 33-column layout.
        # Only the storage indices differ.  The constitutive arithmetic below
        # is intentionally unchanged.
        compact = params.shape[1] <= SIMPLE_TRANSVERSE_PARAM_SIZE
        parameter_offset = 0 if compact else 10
        tensile_curve_column = (
            SIMPLE_TENSILE_CURVE_TYPE_PARAM
            if compact else TENSILE_CURVE_TYPE_PARAM
        )

        for i in prange(targets.size):
            # Target kinematics are advanced for every managed fibre.  The
            # historical two-kernel path only applies ``enabled`` to the
            # constitutive evaluation, so keep that ordering exactly.
            ri = record_index[i]
            strain = trial[i, 7] + (
                (kin_num[ri] * dj[i] + kin_num2[ri] * di[i]) / lengths[ri]
                - delta_flex[ri] * ecc[i]
            )
            targets[i] = strain
            if not enabled[i]:
                continue
            previous_tload = int(trial[i, 5])
            if previous_tload == 0 and strain == 0.0:
                continue

            rot1p, mom1p, rot2p, mom2p = (
                params[i, parameter_offset],
                params[i, parameter_offset + 1],
                params[i, parameter_offset + 2],
                params[i, parameter_offset + 3],
            )
            rot3p, mom3p = (
                params[i, parameter_offset + 4],
                params[i, parameter_offset + 5],
            )
            mom1n, rot1n, rot2n, mom2n = (
                params[i, parameter_offset + 6],
                params[i, parameter_offset + 7],
                params[i, parameter_offset + 8],
                params[i, parameter_offset + 9],
            )
            rot3n, mom3n = (
                params[i, parameter_offset + 10],
                params[i, parameter_offset + 11],
            )
            e1n, e1p, e2n, e2p = (
                params[i, parameter_offset + 12],
                params[i, parameter_offset + 13],
                params[i, parameter_offset + 14],
                params[i, parameter_offset + 15],
            )
            e3n, e3p, eun, eup = (
                params[i, parameter_offset + 16],
                params[i, parameter_offset + 17],
                params[i, parameter_offset + 18],
                params[i, parameter_offset + 19],
            )
            tensile_curve_type = TENSILE_LINEAR
            if params.shape[1] > tensile_curve_column:
                tensile_curve_type = int(params[i, tensile_curve_column])

            umax_p, umax_n = committed[i, 0], committed[i, 1]
            trot_pu, trot_nu = committed[i, 2], committed[i, 3]
            cenergy = committed[i, 4]
            tload = int(committed[i, 5])
            cstress, cstrain = committed[i, 6], committed[i, 7]
            phase = int(committed[i, 8])

            trot_max, trot_min = umax_p, umax_n
            tstress, tstrain, tphase = cstress, strain, phase
            ktang = trial[i, 9]
            dstrain = tstrain - cstrain
            if tload == 0:
                tload = 1 if dstrain >= 0.0 else 2

            if phase == RUPTURE or phase == RUPTURE_C or phase == RUPTURE_T:
                tstress = 0.0
                ktang = 0.0
                if tstrain >= umax_p:
                    trot_max = tstrain
                elif tstrain <= umax_n:
                    trot_min = tstrain

            if tstrain >= umax_p:
                trot_max = tstrain
                tstress = _pos_stress_typed(
                    tensile_curve_type, tstrain, rot1p, mom1p, rot2p,
                    mom2p, rot3p, mom3p, e1p, e2p, e3p,
                )
                ktang, tphase = _pos_tangent_typed(
                    tensile_curve_type, tstrain, rot1p, rot2p, rot3p,
                    e1p, e2p, e3p, tstress, cstress, cstrain,
                )
                tload = 1
            elif tstrain <= umax_n:
                trot_min = tstrain
                tstress = _neg_stress(
                    tstrain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
                    e1n, e2n, e3n,
                )
                ktang, tphase = _neg_tangent(
                    tstrain, rot1n, rot2n, rot3n, e1n, e2n, e3n,
                )
                tload = 2
            elif dstrain < 0.0:
                tphase = UNLOAD_T if tstress > 0.0 else RELOAD_C
                num = 1.0
                num2 = (umax_p / rot1p) ** 1.0 if rot1p != 0.0 else 0.0
                if num2 <= 1.0:
                    num2 = 1.0
                else:
                    env = _pos_stress_typed(
                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                    )
                    num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                if tload == 1:
                    tload = 2
                    if cstress >= 0.0:
                        denom = eup * num2
                        trot_pu = cstrain - cstress / denom if denom != 0.0 else 0.0
                        if _pos_stress_typed(
                            tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                            mom2p, rot3p, mom3p, e1p, e2p, e3p,
                        ) == 0.0:
                            trot_pu = 0.0
                        trot_min = umax_n
                tload = 2
                if trot_min > rot1n:
                    trot_min = rot1n
                num5 = _neg_stress(
                    trot_min, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
                    e1n, e2n, e3n,
                )
                num6 = _pos_rotlim_typed(
                    tensile_curve_type, umax_p, rot1p, mom1p, rot2p, mom2p,
                    e2p, e3p, rot3p, mom3p, e1p,
                )
                num7 = num6 if num6 < trot_pu else trot_pu
                if tstrain >= trot_pu:
                    ktang = eup * num2
                    tstress = cstress + ktang * dstrain
                    if tstress <= 0.0:
                        tstress = 0.0
                elif tstrain > num7:
                    tstress = 0.0
                else:
                    denom9 = trot_min - num7
                    ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                    num10 = cstress + eun * num * dstrain
                    num11 = (tstrain - num7) * ktang
                    if num10 > num11:
                        tstress = num10
                        ktang = eun * num
                    else:
                        tstress = num11
                    if cstrain > trot_pu and tstrain < trot_pu:
                        ktang = eup * num2
                        tstress = cstress + ktang * (trot_pu - cstrain)
                        ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                        tstress += ktang * (tstrain - trot_pu)
            elif dstrain > 0.0:
                tphase = RELOAD_T if tstress > 0.0 else UNLOAD_C
                num = 1.0
                num2 = (umax_p / rot1p) ** 1.0 if rot1p != 0.0 else 0.0
                if num2 <= 1.0:
                    num2 = 1.0
                else:
                    env = _pos_stress_typed(
                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                    )
                    num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                if tload == 2:
                    tload = 1
                    if cstress <= 0.0:
                        denom = eun * num
                        trot_nu = cstrain - cstress / denom if denom != 0.0 else 0.0
                        if _neg_stress(
                            umax_n, mom1n, rot1n, rot2n, mom2n,
                            rot3n, mom3n, e1n, e2n, e3n,
                        ) == 0.0:
                            trot_nu = 0.0
                        trot_max = umax_p
                tload = 1
                if trot_max < rot1p:
                    trot_max = rot1p
                num5 = _pos_stress_typed(
                    tensile_curve_type, trot_max, rot1p, mom1p, rot2p,
                    mom2p, rot3p, mom3p, e1p, e2p, e3p,
                )
                num6 = _neg_rotlim(
                    umax_n, mom1n, rot1n, rot2n, mom2n, e2n, e3n,
                    rot3n, mom3n, e1n,
                )
                num7 = num6 if num6 > trot_nu else trot_nu
                if tstrain <= trot_nu:
                    ktang = eun * num
                    tstress = cstress + ktang * dstrain
                    if tstress >= 0.0:
                        tstress = 0.0
                elif tstrain < num7:
                    tstress = 0.0
                else:
                    denom9 = trot_max - num7
                    ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                    num10 = cstress + eup * num2 * dstrain
                    num11 = (tstrain - num7) * ktang
                    if num10 < num11:
                        tstress = num10
                        ktang = eup * num2
                    else:
                        tstress = num11
                    if cstrain < trot_nu and tstrain > trot_nu:
                        ktang = eun * num
                        tstress = cstress + ktang * (trot_nu - cstrain)
                        ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                        tstress += ktang * (tstrain - trot_nu)

            tenergy = cenergy + 0.5 * (cstress + tstress) * dstrain
            trial[i, 0] = trot_max
            trial[i, 1] = trot_min
            trial[i, 2] = trot_pu
            trial[i, 3] = trot_nu
            trial[i, 4] = tenergy
            trial[i, 5] = tload
            trial[i, 6] = tstress
            trial[i, 7] = tstrain
            trial[i, 8] = tphase
            trial[i, 9] = ktang


    @njit(cache=True, nogil=True, parallel=True)
    def _advance_evaluate_and_finish_simple_linear_batch(
        params, committed, trial, targets, enabled,
        record_index, kin_num, kin_num2, di, dj, lengths, delta_flex, ecc,
        starts, stops, constrained, local_forces,
        normal_increments, committed_forces, max_displacements,
    ):
        """Fuse the linear-tensile simple update and ordered reduction.

        Rows remain independent during constitutive evaluation, while every
        interface reduction retains the original increasing spring order.
        """
        compact = params.shape[1] <= SIMPLE_TRANSVERSE_PARAM_SIZE
        parameter_offset = 0 if compact else 10
        tensile_curve_column = (
            SIMPLE_TENSILE_CURVE_TYPE_PARAM
            if compact else TENSILE_CURVE_TYPE_PARAM
        )

        for reduction_index in prange(starts.size):
            start = starts[reduction_index]
            stop = stops[reduction_index]
            for local_dof in range(6):
                local_forces[reduction_index, local_dof] = 0.0
            normal_increment = 0.0
            committed_force = 0.0
            max_displacement = 0.0
            length = lengths[reduction_index]
            kin_num_value = kin_num[reduction_index]
            kin_num2_value = kin_num2[reduction_index]
            delta_flex_value = delta_flex[reduction_index]
            is_constrained = constrained[reduction_index]
            force_3 = 0.0
            force_2 = 0.0
            force_4 = 0.0

            for i in range(start, stop):
                strain = trial[i, 7] + (
                    (kin_num_value * dj[i] + kin_num2_value * di[i]) / length
                    - delta_flex_value * ecc[i]
                )
                targets[i] = strain
                if enabled[i]:
                    previous_tload = int(trial[i, 5])
                    if not (previous_tload == 0 and strain == 0.0):
                        rot1p, mom1p, rot2p, mom2p = (
                            params[i, parameter_offset],
                            params[i, parameter_offset + 1],
                            params[i, parameter_offset + 2],
                            params[i, parameter_offset + 3],
                        )
                        rot3p, mom3p = (
                            params[i, parameter_offset + 4],
                            params[i, parameter_offset + 5],
                        )
                        mom1n, rot1n, rot2n, mom2n = (
                            params[i, parameter_offset + 6],
                            params[i, parameter_offset + 7],
                            params[i, parameter_offset + 8],
                            params[i, parameter_offset + 9],
                        )
                        rot3n, mom3n = (
                            params[i, parameter_offset + 10],
                            params[i, parameter_offset + 11],
                        )
                        e1n, e1p, e2n, e2p = (
                            params[i, parameter_offset + 12],
                            params[i, parameter_offset + 13],
                            params[i, parameter_offset + 14],
                            params[i, parameter_offset + 15],
                        )
                        e3n, e3p, eun, eup = (
                            params[i, parameter_offset + 16],
                            params[i, parameter_offset + 17],
                            params[i, parameter_offset + 18],
                            params[i, parameter_offset + 19],
                        )
                        tensile_curve_type = TENSILE_LINEAR
                        if params.shape[1] > tensile_curve_column:
                            tensile_curve_type = int(params[i, tensile_curve_column])

                        umax_p, umax_n = committed[i, 0], committed[i, 1]
                        trot_pu, trot_nu = committed[i, 2], committed[i, 3]
                        cenergy = committed[i, 4]
                        tload = int(committed[i, 5])
                        cstress, cstrain = committed[i, 6], committed[i, 7]
                        phase = int(committed[i, 8])

                        trot_max, trot_min = umax_p, umax_n
                        tstress, tstrain, tphase = cstress, strain, phase
                        ktang = trial[i, 9]
                        dstrain = tstrain - cstrain
                        if tload == 0:
                            tload = 1 if dstrain >= 0.0 else 2

                        if phase == RUPTURE or phase == RUPTURE_C or phase == RUPTURE_T:
                            tstress = 0.0
                            ktang = 0.0
                            if tstrain >= umax_p:
                                trot_max = tstrain
                            elif tstrain <= umax_n:
                                trot_min = tstrain

                        if tstrain >= umax_p:
                            trot_max = tstrain
                            tstress = _pos_stress_typed(
                                tensile_curve_type, tstrain, rot1p, mom1p, rot2p,
                                mom2p, rot3p, mom3p, e1p, e2p, e3p,
                            )
                            ktang, tphase = _pos_tangent_typed(
                                tensile_curve_type, tstrain, rot1p, rot2p, rot3p,
                                e1p, e2p, e3p, tstress, cstress, cstrain,
                            )
                            tload = 1
                        elif tstrain <= umax_n:
                            trot_min = tstrain
                            tstress = _neg_stress(
                                tstrain, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
                                e1n, e2n, e3n,
                            )
                            ktang, tphase = _neg_tangent(
                                tstrain, rot1n, rot2n, rot3n, e1n, e2n, e3n,
                            )
                            tload = 2
                        elif dstrain < 0.0:
                            tphase = UNLOAD_T if tstress > 0.0 else RELOAD_C
                            num = 1.0
                            num2 = (umax_p / rot1p) ** 1.0 if rot1p != 0.0 else 0.0
                            if num2 <= 1.0:
                                num2 = 1.0
                            else:
                                env = _pos_stress_typed(
                                    tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                                    mom2p, rot3p, mom3p, e1p, e2p, e3p,
                                )
                                num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                            if tload == 1:
                                tload = 2
                                if cstress >= 0.0:
                                    denom = eup * num2
                                    trot_pu = cstrain - cstress / denom if denom != 0.0 else 0.0
                                    if _pos_stress_typed(
                                        tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                                        mom2p, rot3p, mom3p, e1p, e2p, e3p,
                                    ) == 0.0:
                                        trot_pu = 0.0
                                    trot_min = umax_n
                            tload = 2
                            if trot_min > rot1n:
                                trot_min = rot1n
                            num5 = _neg_stress(
                                trot_min, mom1n, rot1n, rot2n, mom2n, rot3n, mom3n,
                                e1n, e2n, e3n,
                            )
                            num6 = _pos_rotlim_typed(
                                tensile_curve_type, umax_p, rot1p, mom1p, rot2p, mom2p,
                                e2p, e3p, rot3p, mom3p, e1p,
                            )
                            num7 = num6 if num6 < trot_pu else trot_pu
                            if tstrain >= trot_pu:
                                ktang = eup * num2
                                tstress = cstress + ktang * dstrain
                                if tstress <= 0.0:
                                    tstress = 0.0
                            elif tstrain > num7:
                                tstress = 0.0
                            else:
                                denom9 = trot_min - num7
                                ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                                num10 = cstress + eun * num * dstrain
                                num11 = (tstrain - num7) * ktang
                                if num10 > num11:
                                    tstress = num10
                                    ktang = eun * num
                                else:
                                    tstress = num11
                                if cstrain > trot_pu and tstrain < trot_pu:
                                    ktang = eup * num2
                                    tstress = cstress + ktang * (trot_pu - cstrain)
                                    ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                                    tstress += ktang * (tstrain - trot_pu)
                        elif dstrain > 0.0:
                            tphase = RELOAD_T if tstress > 0.0 else UNLOAD_C
                            num = 1.0
                            num2 = (umax_p / rot1p) ** 1.0 if rot1p != 0.0 else 0.0
                            if num2 <= 1.0:
                                num2 = 1.0
                            else:
                                env = _pos_stress_typed(
                                    tensile_curve_type, umax_p, rot1p, mom1p, rot2p,
                                    mom2p, rot3p, mom3p, e1p, e2p, e3p,
                                )
                                num2 = env / mom1p / num2 if num2 != 0.0 else 1.0
                            if tload == 2:
                                tload = 1
                                if cstress <= 0.0:
                                    denom = eun * num
                                    trot_nu = cstrain - cstress / denom if denom != 0.0 else 0.0
                                    if _neg_stress(
                                        umax_n, mom1n, rot1n, rot2n, mom2n,
                                        rot3n, mom3n, e1n, e2n, e3n,
                                    ) == 0.0:
                                        trot_nu = 0.0
                                    trot_max = umax_p
                            tload = 1
                            if trot_max < rot1p:
                                trot_max = rot1p
                            num5 = _pos_stress_typed(
                                tensile_curve_type, trot_max, rot1p, mom1p, rot2p,
                                mom2p, rot3p, mom3p, e1p, e2p, e3p,
                            )
                            num6 = _neg_rotlim(
                                umax_n, mom1n, rot1n, rot2n, mom2n, e2n, e3n,
                                rot3n, mom3n, e1n,
                            )
                            num7 = num6 if num6 > trot_nu else trot_nu
                            if tstrain <= trot_nu:
                                ktang = eun * num
                                tstress = cstress + ktang * dstrain
                                if tstress >= 0.0:
                                    tstress = 0.0
                            elif tstrain < num7:
                                tstress = 0.0
                            else:
                                denom9 = trot_max - num7
                                ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                                num10 = cstress + eup * num2 * dstrain
                                num11 = (tstrain - num7) * ktang
                                if num10 < num11:
                                    tstress = num10
                                    ktang = eup * num2
                                else:
                                    tstress = num11
                                if cstrain < trot_nu and tstrain > trot_nu:
                                    ktang = eun * num
                                    tstress = cstress + ktang * (trot_nu - cstrain)
                                    ktang = num5 / denom9 if denom9 != 0.0 else 0.0
                                    tstress += ktang * (tstrain - trot_nu)

                        tenergy = cenergy + 0.5 * (cstress + tstress) * dstrain
                        trial[i, 0] = trot_max
                        trial[i, 1] = trot_min
                        trial[i, 2] = trot_pu
                        trial[i, 3] = trot_nu
                        trial[i, 4] = tenergy
                        trial[i, 5] = tload
                        trial[i, 6] = tstress
                        trial[i, 7] = tstrain
                        trial[i, 8] = tphase
                        trial[i, 9] = ktang

                force = trial[i, 6]
                committed_value = committed[i, 6]
                normal_increment -= force - committed_value
                committed_force += force - (force - committed_value)
                displacement = abs(trial[i, 7])
                if displacement > max_displacement:
                    max_displacement = displacement

                if not is_constrained:
                    force_3 += force * dj[i] / length
                    force_2 += force * di[i] / length
                    force_4 += force * ecc[i]
                else:
                    local_forces[reduction_index, 3] += force * dj[i] / length
                    local_forces[reduction_index, 2] += force * di[i] / length
                    local_forces[reduction_index, 0] += (
                        (0.0 - force) * di[i] / length
                        - force * dj[i] / length
                    )
                    local_forces[reduction_index, 1] += 0.5 * length * (
                        force * dj[i] / length
                        - force * di[i] / length
                    )
                    local_forces[reduction_index, 4] += force * ecc[i]
                    local_forces[reduction_index, 5] += (0.0 - force) * ecc[i]

            if not is_constrained:
                local_forces[reduction_index, 3] = force_3
                local_forces[reduction_index, 2] = force_2
                local_forces[reduction_index, 4] = force_4
                local_forces[reduction_index, 0] = (
                    0.0 if force_3 == 0.0 else -force_3
                )
                local_forces[reduction_index, 1] = (
                    0.0 if force_2 == 0.0 else -force_2
                )
                local_forces[reduction_index, 5] = (
                    0.0 if force_4 == 0.0 else -force_4
                )
            normal_increments[reduction_index] = normal_increment
            committed_forces[reduction_index] = committed_force
            max_displacements[reduction_index] = max_displacement


    @njit(cache=True, nogil=True, parallel=True)
    def _advance_transverse_targets(
        trial, record_index, num, num2, di, dj, lengths, delta_flex, ecc, targets,
    ):
        """Update transverse trial strains with one independent row per fibre.

        Each output row depends only on immutable geometry and its owning
        interface kinematics, so parallel execution cannot change reduction
        order or constitutive history.
        """
        for i in prange(targets.size):
            ri = record_index[i]
            targets[i] = trial[i, 7] + (
                (num[ri] * dj[i] + num2[ri] * di[i]) / lengths[ri]
                - delta_flex[ri] * ecc[i]
            )

    @njit(cache=True, nogil=True, parallel=True)
    def _finish_transverse_batch(
        trial, committed, di, dj, ecc, lengths,
        starts, stops, constrained, local_forces,
        normal_increments, committed_forces, max_displacements,
    ):
        for record_index in prange(starts.size):
            start = starts[record_index]
            stop = stops[record_index]
            for local_dof in range(6):
                local_forces[record_index, local_dof] = 0.0
            normal_increment = 0.0
            committed_force = 0.0
            max_displacement = 0.0
            # These values are constant for all fibres in the interface.  Keep
            # the spring accumulation order unchanged while avoiding two dense
            # array reads for every transverse spring.
            length = lengths[record_index]
            is_constrained = constrained[record_index]
            if not is_constrained:
                # Quad/Quad components 0/1/5 are exact antisymmetric
                # counterparts of 3/2/4. Accumulate each ordered reduction
                # once, then mirror it without changing spring order.
                force_3 = 0.0
                force_2 = 0.0
                force_4 = 0.0
                for spring_index in range(start, stop):
                    force = trial[spring_index, 6]
                    committed_value = committed[spring_index, 6]
                    normal_increment -= force - committed_value
                    committed_force += force - (force - committed_value)
                    displacement = abs(trial[spring_index, 7])
                    if displacement > max_displacement:
                        max_displacement = displacement

                    force_3 += force * dj[spring_index] / length
                    force_2 += force * di[spring_index] / length
                    force_4 += force * ecc[spring_index]

                local_forces[record_index, 3] = force_3
                local_forces[record_index, 2] = force_2
                local_forces[record_index, 4] = force_4
                # The original accumulators start at positive zero.
                local_forces[record_index, 0] = 0.0 if force_3 == 0.0 else -force_3
                local_forces[record_index, 1] = 0.0 if force_2 == 0.0 else -force_2
                local_forces[record_index, 5] = 0.0 if force_4 == 0.0 else -force_4
            else:
                # Restraint interfaces use a different transformation; keep
                # their original C#-ordered arithmetic verbatim.
                for spring_index in range(start, stop):
                    force = trial[spring_index, 6]
                    committed_value = committed[spring_index, 6]
                    normal_increment -= force - committed_value
                    committed_force += force - (force - committed_value)
                    displacement = abs(trial[spring_index, 7])
                    if displacement > max_displacement:
                        max_displacement = displacement

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


else:  # pragma: no cover - exercised when numba is unavailable
    _pos_stress_typed = None
    _pos_tangent_typed = None
    _pos_rotlim_typed = None
    _neg_stress_typed = None
    _neg_tangent_typed = None
    _neg_rotlim_typed = None
    _evaluate_linear_batch = None
    _evaluate_linear_serial_batch = None
    _advance_transverse_targets = None
    _evaluate_simple_linear_batch = None
    _advance_and_evaluate_simple_linear_batch = None
    _advance_evaluate_and_finish_simple_linear_batch = None
    _finish_transverse_batch = None
