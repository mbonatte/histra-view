"""C#-compatible scalar and NumPy-batched spring construction."""

from __future__ import annotations

from typing import Any

import copy
import math

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover
    njit = None

from histra.preprocessing.constitutive_laws import (
    CoulombLaw as _CoulombLaw,
    HystereticLaw as _HystereticLaw,
)
from histra.preprocessing.errors import ModelPreparationError
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.transverse_fiber_group import TransverseFiberGroup


def _new_hysteretic_spring() -> SpringHysteretic:
    """Return an independent virgin programmatic hysteretic spring."""
    return SpringHysteretic(type_of="HiStrA.Objects.SpringHysteretic")


def _series(k1: float, k2: float, restrained: bool) -> float:
    if restrained and (k1 == -1.0 or k2 == -1.0):
        return k2 if k1 == -1.0 else k1
    if k1 != 0.0 or k2 != 0.0:
        denominator = k1 + k2
        return k1 * k2 / denominator if denominator != 0.0 else 0.0
    return 0.0


def _configure_coulomb(
    *, k: float, area: float, length: float, law: _CoulombLaw,
    cohesion_force: float | None = None, mu: float | None = None,
    ur: float | None = None, hysteretic_type: str | None = None,
    plastic_strain: float | None = None, use_second_branch: bool = False,
    sub_law: str | None = None,
) -> SpringCoulomb03:
    """Create the virgin C# SpringCoulomb03 envelope.

    C# ``Set``/``Set2`` use constitutive-law ratios to construct the envelope
    but, somewhat surprisingly, do not copy most of those ratios into the
    spring's serialized properties.  The spring therefore retains its class
    defaults (0.0001, 0.8, 1.0) while the initial envelope can have a different
    tangent.  Preserving that behavior matters when normal force later causes
    the Coulomb envelope to be rebuilt.
    """
    spring = SpringCoulomb03(type_of="HiStrA.Objects.SpringCoulomb03")
    spring.k = float(k)
    spring.area = float(area)
    spring.length = float(length)
    spring.cohesion = float(law.cohesion * area if cohesion_force is None else cohesion_force)
    spring.mu = float(law.mu if mu is None else mu)
    spring.sub_law = sub_law or law.sub_law
    spring.hysteretic_type = hysteretic_type or law.hysteretic_type
    spring.bcacovic = float(law.bcacovic)

    ultimate = float(law.ductility if ur is None else ur)
    if ultimate <= 0.0:
        ultimate = 100000.0
    ktan = spring.k * law.plastic_stiffness_ratio
    ktan2 = spring.k * law.plastic_stiffness_ratio2
    mom1p = max(1.0e-9, spring.cohesion)
    rot1p = mom1p / spring.k if spring.k else 0.0

    if use_second_branch and ktan2 < 0.0:
        ps = float(ultimate if plastic_strain is None else plastic_strain)
        spring.plastic_strain_ratio = ps  # Set2 is the one C# path that stores it.
        rot2p = max(ps, rot1p * 1.0001)
        mom2p = mom1p + ktan * (rot2p - rot1p)
        if law.is_ductility_fixed:
            rot3p = max(ultimate, rot2p * 1.0001)
            mom3p = 0.0
        else:
            mom3p = 0.0
            rot3p = rot1p - mom1p / ktan2
    elif ktan < 0.0:
        if law.is_ductility_fixed:
            rot2p = max(ultimate, rot1p * 1.0001)
            mom2p = 0.0
        else:
            mom2p = 0.0
            rot2p = rot1p - mom1p / ktan
        rot3p = 1.0001 * rot2p
        mom3p = 0.0
    else:
        rot2p = max(ultimate, rot1p * 1.0001)
        mom2p = mom1p + ktan * (rot2p - rot1p)
        rot3p = 1.0001 * rot2p
        mom3p = 0.0 if law.is_ductility_fixed else mom1p + ktan * (rot3p - rot1p)

    spring.mom1p, spring.rot1p = mom1p, rot1p
    spring.mom2p, spring.rot2p = mom2p, rot2p
    spring.mom3p, spring.rot3p = mom3p, rot3p
    spring.mom1n, spring.rot1n = -mom1p, -rot1p
    spring.mom2n, spring.rot2n = -mom2p, -rot2p
    spring.mom3n, spring.rot3n = -mom3p, -rot3p
    spring.fy = [spring.cohesion, -spring.cohesion]
    spring.ur = [ultimate, -ultimate]
    spring.umax = [spring.cohesion / spring.k if spring.k else 0.0,
                   -spring.cohesion / spring.k if spring.k else 0.0]
    spring._set_envelope()
    spring.energy_a = 0.5 * (
        rot1p*mom1p + (rot2p-rot1p)*(mom2p+mom1p)
        + (rot3p-rot2p)*(mom3p+mom2p)
        + spring.rot1n*spring.mom1n
        + (spring.rot2n-spring.rot1n)*(spring.mom2n+spring.mom1n)
        + (spring.rot3n-spring.rot2n)*(spring.mom3n+spring.mom2n)
    )
    spring.revert_to_start()
    spring.revert_to_last_commit()
    return spring


def _set_coulomb_ultimate(
    spring: SpringCoulomb03, law1: _CoulombLaw, law2: _CoulombLaw
) -> None:
    """Port ``SpringCoulomb03.SetUltimateDisplacement``."""
    energies = [law.G for law in (law1, law2) if law.fracture_energy]
    if not energies or spring.area == 0.0 or spring.fy[0] == 0.0:
        return
    spring.hysteretic_type = "Initial"
    spring.check_contact_area = law1.check_contact_area or law2.check_contact_area
    energy = sum(energies) / len(energies)
    ur = 2.0 * energy / (spring.fy[0] / spring.area) + spring.fy[0] / spring.k
    ur = max(ur, spring.fy[0] / spring.k * 1.0001)
    spring.ur = [ur, -ur]
    spring.rot2p = ur
    spring.mom2p = 0.0
    spring.rot3p = 1.01 * ur
    spring.mom3p = 0.0
    spring.rot2n = -ur
    spring.mom2n = 0.0
    spring.rot3n = -1.01 * ur
    spring.mom3n = 0.0
    spring._set_envelope()
    spring.revert_to_start()
    spring.revert_to_last_commit()

def _configure_hysteretic(k: float, area: float, length: float, law: _HystereticLaw) -> SpringHysteretic | SpringElastic:
    if not math.isfinite(k) or k <= 0.0:
        raise ModelPreparationError(
            f"Cannot create a transverse hysteretic spring with stiffness K={k!r}."
        )
    if not math.isfinite(area) or area <= 0.0:
        raise ModelPreparationError(
            f"Cannot create a transverse hysteretic spring with area={area!r}."
        )
    if not math.isfinite(length) or length <= 0.0:
        raise ModelPreparationError(
            f"Cannot create a transverse hysteretic spring with length={length!r}."
        )
    if law.is_elastic:
        return SpringElastic(type_of="HiStrA.Objects.SpringLinearElastic",
                             k=float(k), k_tang=float(k), area=float(area), length=float(length))
    spring = _new_hysteretic_spring()
    spring.k = float(k)
    spring.area = float(area)
    # Original SpringHysteretic.SetQuadTrasvSpring does not assign Length.
    spring.length = 0.0
    spring.tensile_curve_type = law.tensile_curve
    spring.compressive_curve_type = law.compressive_curve
    spring.fy = [area * law.fy_t, -area * law.fy_c]
    spring.kt = [0.0, 0.0]
    if law.tensile_curve == "Elastic":
        spring.fy[0] = k * 100000000.0
        spring.kt[0] = k
    elif law.tensile_curve == "LinearHardening":
        spring.kt[0] = k * law.ratio_et_t
    if law.compressive_curve == "Elastic":
        spring.fy[1] = -k * 100000000.0
        spring.kt[1] = k
    elif law.compressive_curve == "LinearHardening":
        spring.kt[1] = k * law.ratio_et_c
    spring.alfar = [law.alfa_r_t, law.alfa_r_c]
    spring.alfau = [law.alfa_u_t, law.alfa_u_c]
    # Temporary values; _set_ultimate_displacement reproduces the post-series
    # C# call and then initialize() rebuilds the envelope.
    spring.ur = [max(spring.fy[0] / k if k else 0.0, law.eps_u_t * length),
                 min(spring.fy[1] / k if k else 0.0, -law.eps_u_c * length)]
    _set_ultimate_displacement(spring, law, law)
    # initialize() already resets both trial and committed state.
    spring.initialize()
    return spring


def _set_ultimate_displacement(spring: SpringHysteretic, law1: _HystereticLaw, law2: _HystereticLaw) -> None:
    # Exact fracture-energy branches used by the supplied materials.  Keep the
    # law-1/law-2 evaluation order of the former list-based implementation,
    # but avoid allocating four short Python lists for every generated fibre.
    h1 = not (law1.tensile_curve == law1.compressive_curve == "Elastic")
    h2 = not (law2.tensile_curve == law2.compressive_curve == "Elastic")
    gt1 = law1.tensile_curve in {"LinearSoftening", "Exponential"}
    gt2 = law2.tensile_curve in {"LinearSoftening", "Exponential"}
    if (gt1 or gt2) and spring.area and spring.fy[0]:
        if gt1:
            g = (law1.G_t + law2.G_t) / 2 if gt2 else law1.G_t
        else:
            g = law2.G_t
        if spring.tensile_curve_type == "LinearSoftening":
            spring.ur[0] = 2.0 * g / (spring.fy[0] / spring.area) + spring.fy[0] / spring.k
            spring.kt[0] = -spring.fy[0] / (spring.ur[0] - spring.fy[0] / spring.k)
        elif spring.tensile_curve_type == "Exponential":
            spring.ur[0] = g / (spring.fy[0] / spring.area) + spring.fy[0] / spring.k
        spring.ur[0] = max(spring.ur[0], spring.fy[0] / spring.k)
    else:
        if h1 and h2:
            selected = law1
            if law2.fy_t < law1.fy_t or (
                    law2.fy_t == law1.fy_t and law2.eps_u_t < law1.eps_u_t):
                selected = law2
        elif h1 and law1.tensile_curve != "Elastic":
            selected = law1
        elif h2 and law2.tensile_curve != "Elastic":
            selected = law2
        else:
            selected = None
        if selected is not None and selected.fy_t and selected.E:
            spring.ur[0] = (spring.fy[0] / spring.k * selected.eps_u_t
                              / (selected.fy_t / selected.E))

    gc1 = law1.compressive_curve in {"LinearSoftening", "Parabolic"}
    gc2 = law2.compressive_curve in {"LinearSoftening", "Parabolic"}
    if (gc1 or gc2) and spring.area and spring.fy[1]:
        if gc1:
            g = (law1.G_c + law2.G_c) / 2 if gc2 else law1.G_c
        else:
            g = law2.G_c
        if spring.compressive_curve_type == "LinearSoftening":
            spring.ur[1] = 2.0 * g / (spring.fy[1] / spring.area) + spring.fy[1] / spring.k
            spring.kt[1] = -spring.fy[1] / (spring.ur[1] - spring.fy[1] / spring.k)
        elif spring.compressive_curve_type == "Parabolic":
            spring.ur[1] = 3.0 * g / (2.0 * spring.fy[1] / spring.area) + 5.0 * spring.fy[1] / (3.0 * spring.k)
        spring.ur[1] = min(spring.ur[1], spring.fy[1] / spring.k)
    else:
        if h1 and h2:
            selected = law1
            if law2.fy_c < law1.fy_c or (
                    law2.fy_c == law1.fy_c and law2.eps_u_c < law1.eps_u_c):
                selected = law2
        elif h1 and law1.compressive_curve != "Elastic":
            selected = law1
        elif h2 and law2.compressive_curve != "Elastic":
            selected = law2
        else:
            selected = None
        if selected is not None and selected.fy_c and selected.E:
            spring.ur[1] = (spring.fy[1] / spring.k * selected.eps_u_c
                              / (selected.fy_c / selected.E))


def _hysteretic_side_definition(
    k: float, area: float, length: float, law: _HystereticLaw,
) -> tuple[
    float, float, float, float, float, float, float,
    float, float, float, float, str, str,
]:
    if not math.isfinite(k) or k <= 0.0:
        raise ModelPreparationError(
            f"Cannot create a transverse hysteretic spring with stiffness K={k!r}."
        )
    if not math.isfinite(area) or area <= 0.0:
        raise ModelPreparationError(
            f"Cannot create a transverse hysteretic spring with area={area!r}."
        )
    if not math.isfinite(length) or length <= 0.0:
        raise ModelPreparationError(
            f"Cannot create a transverse hysteretic spring with length={length!r}."
        )

    fy_t = area * law.fy_t
    fy_c = -area * law.fy_c
    kt_t = 0.0
    kt_c = 0.0
    if law.tensile_curve == "Elastic":
        fy_t = k * 100000000.0
        kt_t = k
    elif law.tensile_curve == "LinearHardening":
        kt_t = k * law.ratio_et_t
    if law.compressive_curve == "Elastic":
        fy_c = -k * 100000000.0
        kt_c = k
    elif law.compressive_curve == "LinearHardening":
        kt_c = k * law.ratio_et_c

    # _configure_hysteretic calls _set_ultimate_displacement before the two
    # side springs are combined. Linear-softening laws therefore contribute
    # their fracture-energy tangent, not the initial zero placeholder.
    if law.tensile_curve == "LinearSoftening" and area and fy_t:
        ultimate_t = 2.0 * law.G_t / (fy_t / area) + fy_t / k
        kt_t = -fy_t / (ultimate_t - fy_t / k)
    if law.compressive_curve == "LinearSoftening" and area and fy_c:
        ultimate_c = 2.0 * law.G_c / (fy_c / area) + fy_c / k
        kt_c = -fy_c / (ultimate_c - fy_c / k)

    return (
        float(k), float(area), 0.0,
        float(fy_t), float(fy_c), float(kt_t), float(kt_c),
        float(law.alfa_r_t), float(law.alfa_r_c),
        float(law.alfa_u_t), float(law.alfa_u_c),
        law.tensile_curve, law.compressive_curve,
    )


def _configure_combined_hysteretic(
    k1: float, area1: float, length1: float, law1: _HystereticLaw,
    k2: float, area2: float, length2: float, law2: _HystereticLaw,
) -> SpringHysteretic:
    """Create the final Quad/Quad fibre spring without temporary objects.

    This is algebraically identical to configuring two side springs and calling
    ``_combine_hysteretic``.  It avoids two temporary SpringHysteretic objects
    and two full envelope initializations per generated fibre.
    """
    if law1.is_elastic or law2.is_elastic:
        return _combine_hysteretic(
            _configure_hysteretic(k1, area1, length1, law1),
            _configure_hysteretic(k2, area2, length2, law2), False, law1, law2,
        )
    (
        s1_k, s1_area, s1_length, s1_fy_t, s1_fy_c, s1_kt_t, s1_kt_c,
        s1_alfa_r_t, s1_alfa_r_c, s1_alfa_u_t, s1_alfa_u_c,
        s1_tensile_curve, s1_compressive_curve,
    ) = _hysteretic_side_definition(k1, area1, length1, law1)
    (
        s2_k, s2_area, s2_length, s2_fy_t, s2_fy_c, s2_kt_t, s2_kt_c,
        s2_alfa_r_t, s2_alfa_r_c, s2_alfa_u_t, s2_alfa_u_c,
        s2_tensile_curve, s2_compressive_curve,
    ) = _hysteretic_side_definition(k2, area2, length2, law2)
    out = _new_hysteretic_spring()
    out.k = _series(s1_k, s2_k, False)

    if s1_fy_t <= s2_fy_t:
        out.fy[0] = s1_fy_t
        out.tensile_curve_type = s1_tensile_curve
    else:
        out.fy[0] = s2_fy_t
        out.tensile_curve_type = s2_tensile_curve

    if s1_fy_c <= s2_fy_c:
        out.fy[1] = s2_fy_c
        out.area = s2_area
    else:
        out.fy[1] = s1_fy_c
        out.area = s1_area
    out.compressive_curve_type = (
        s1_compressive_curve if s1_fy_c >= s2_fy_c else s2_compressive_curve
    )
    out.length = s1_length + s2_length
    out.alfau = [
        max(s1_alfa_u_t, s2_alfa_u_t),
        max(s1_alfa_u_c, s2_alfa_u_c),
    ]
    out.alfar = [
        max(s1_alfa_r_t, s2_alfa_r_t),
        max(s1_alfa_r_c, s2_alfa_r_c),
    ]
    out.kt = [
        out.k if out.tensile_curve_type == "Elastic" else _series(s1_kt_t, s2_kt_t, False),
        out.k if out.compressive_curve_type == "Elastic" else _series(s1_kt_c, s2_kt_c, False),
    ]
    out.ur = [
        max(out.fy[0] / out.k if out.k else 0.0, 0.0),
        min(out.fy[1] / out.k if out.k else 0.0, 0.0),
    ]
    _set_ultimate_displacement(out, law1, law1)
    ur1_t, ur1_c = out.ur
    _set_ultimate_displacement(out, law2, law2)
    ur2_t, ur2_c = out.ur
    if ur1_t < ur2_t and ur1_t != 0.0:
        out.ur[0] = ur1_t
        out.tensile_curve_type = law1.tensile_curve
    elif ur2_t < ur1_t and ur2_t != 0.0:
        out.ur[0] = ur2_t
        out.tensile_curve_type = law2.tensile_curve
    if ur1_c > ur2_c and ur1_c != 0.0:
        out.ur[1] = ur1_c
        out.compressive_curve_type = law1.compressive_curve
    elif ur2_c > ur1_c and ur2_c != 0.0:
        out.ur[1] = ur2_c
        out.compressive_curve_type = law2.compressive_curve
    # initialize() already resets both trial and committed state.
    out.initialize()
    return out



def _series_array(k1: np.ndarray, k2: np.ndarray) -> np.ndarray:
    """Vector form of ``_series(..., restrained=False)``."""
    denominator = k1 + k2
    result = np.zeros_like(denominator, dtype=np.float64)
    np.divide(k1 * k2, denominator, out=result, where=denominator != 0.0)
    return result


def _hysteretic_side_arrays(
    props: np.ndarray,
    law: _HystereticLaw,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute side yielding/tangent arrays for one interface in bulk.

    ``props`` has columns ``K, area, length`` and has already passed the exact
    scalar validity checks.  Material-law branches are invariant for every
    fibre on this side, so evaluating them once per NumPy array avoids hundreds
    of thousands of repeated Python calls and attribute lookups.
    """
    k = props[:, 0]
    area = props[:, 1]

    if law.tensile_curve == "Elastic":
        fy_t = k * 100000000.0
        kt_t = k.copy()
    else:
        fy_t = area * law.fy_t
        if law.tensile_curve == "LinearHardening":
            kt_t = k * law.ratio_et_t
        elif law.tensile_curve == "LinearSoftening" and law.fy_t != 0.0:
            # Preserve scalar operation order: fy_t is first formed from
            # area*law.fy_t and then divided by area again.
            ultimate_t = 2.0 * law.G_t / (fy_t / area) + fy_t / k
            kt_t = -fy_t / (ultimate_t - fy_t / k)
        else:
            kt_t = np.zeros_like(k)

    if law.compressive_curve == "Elastic":
        fy_c = -k * 100000000.0
        kt_c = k.copy()
    else:
        fy_c = -area * law.fy_c
        if law.compressive_curve == "LinearHardening":
            kt_c = k * law.ratio_et_c
        elif law.compressive_curve == "LinearSoftening" and law.fy_c != 0.0:
            # Preserve scalar operation order for the same reason as tension.
            ultimate_c = 2.0 * law.G_c / (fy_c / area) + fy_c / k
            kt_c = -fy_c / (ultimate_c - fy_c / k)
        else:
            kt_c = np.zeros_like(k)

    return fy_t, fy_c, kt_t, kt_c


def _apply_ultimate_displacement_arrays(
    *,
    law: _HystereticLaw,
    k: np.ndarray,
    area: np.ndarray,
    fy_t: np.ndarray,
    fy_c: np.ndarray,
    tensile_linear_softening: np.ndarray,
    tensile_exponential: np.ndarray,
    compressive_linear_softening: np.ndarray,
    compressive_parabolic: np.ndarray,
    ur_t: np.ndarray,
    ur_c: np.ndarray,
    kt_t: np.ndarray,
    kt_c: np.ndarray,
) -> None:
    """Vector equivalent of ``_set_ultimate_displacement(out, law, law)``."""
    base_t = fy_t / k
    if law.tensile_curve in {"LinearSoftening", "Exponential"}:
        active = (area != 0.0) & (fy_t != 0.0)
        mask = active & tensile_linear_softening
        if np.any(mask):
            value = 2.0 * law.G_t / (fy_t[mask] / area[mask]) + base_t[mask]
            ur_t[mask] = value
            kt_t[mask] = -fy_t[mask] / (value - base_t[mask])
        mask = active & tensile_exponential
        if np.any(mask):
            ur_t[mask] = (
                law.G_t / (fy_t[mask] / area[mask]) + base_t[mask]
            )
        # Scalar code applies this clamp for every active row even when the
        # selected combined curve family is neither softening nor exponential.
        if np.any(active):
            ur_t[active] = np.maximum(ur_t[active], base_t[active])
    elif not (law.tensile_curve == law.compressive_curve == "Elastic") and law.fy_t and law.E:
        ur_t[:] = base_t * law.eps_u_t / (law.fy_t / law.E)

    base_c = fy_c / k
    if law.compressive_curve in {"LinearSoftening", "Parabolic"}:
        active = (area != 0.0) & (fy_c != 0.0)
        mask = active & compressive_linear_softening
        if np.any(mask):
            value = 2.0 * law.G_c / (fy_c[mask] / area[mask]) + base_c[mask]
            ur_c[mask] = value
            kt_c[mask] = -fy_c[mask] / (value - base_c[mask])
        mask = active & compressive_parabolic
        if np.any(mask):
            ur_c[mask] = (
                3.0 * law.G_c / (2.0 * fy_c[mask] / area[mask])
                + 5.0 * fy_c[mask] / (3.0 * k[mask])
            )
        if np.any(active):
            ur_c[active] = np.minimum(ur_c[active], base_c[active])
    elif not (law.tensile_curve == law.compressive_curve == "Elastic") and law.fy_c and law.E:
        ur_c[:] = base_c * law.eps_u_c / (law.fy_c / law.E)


_TENSILE_CURVE_MAP = {"Elastic": 0, "LinearHardening": 1, "LinearSoftening": 2, "Exponential": 3}
_COMPRESSIVE_CURVE_MAP = {"Elastic": 0, "LinearHardening": 1, "LinearSoftening": 2, "Parabolic": 3}

if njit is not None:
    @njit(cache=True, inline="always")
    def _series_nb(k1: float, k2: float) -> float:
        s = k1 + k2
        if s == 0.0:
            return 0.0
        return (k1 * k2) / s

    @njit(cache=True, nogil=True)
    def _hysteretic_kernel_nb(
        p1: np.ndarray,
        p2: np.ndarray,
        law1_t_curve: int,
        law1_c_curve: int,
        law1_E: float,
        law1_fy_t: float,
        law1_fy_c: float,
        law1_ratio_et_t: float,
        law1_ratio_et_c: float,
        law1_G_t: float,
        law1_G_c: float,
        law1_eps_u_t: float,
        law1_eps_u_c: float,
        law2_t_curve: int,
        law2_c_curve: int,
        law2_E: float,
        law2_fy_t: float,
        law2_fy_c: float,
        law2_ratio_et_t: float,
        law2_ratio_et_c: float,
        law2_G_t: float,
        law2_G_c: float,
        law2_eps_u_t: float,
        law2_eps_u_c: float,
        batch_params: np.ndarray,
        k_out: np.ndarray,
        area_out: np.ndarray,
        tension_from_1_out: np.ndarray,
        compression_from_1_out: np.ndarray,
        fy_out: np.ndarray,
        kt_out: np.ndarray,
        ur_out: np.ndarray,
    ) -> None:
        n = p1.shape[0]
        for i in range(n):
            k1 = p1[i, 0]
            area1 = p1[i, 1]
            length1 = p1[i, 2]

            k2 = p2[i, 0]
            area2 = p2[i, 1]
            length2 = p2[i, 2]

            # Side 1
            if law1_t_curve == 0:  # Elastic
                fy1_t = k1 * 100000000.0
                kt1_t = k1
            else:
                fy1_t = area1 * law1_fy_t
                if law1_t_curve == 1:  # LinearHardening
                    kt1_t = k1 * law1_ratio_et_t
                elif law1_t_curve == 2 and law1_fy_t != 0.0:  # LinearSoftening
                    ult_t = 2.0 * law1_G_t / (fy1_t / area1) + fy1_t / k1
                    kt1_t = -fy1_t / (ult_t - fy1_t / k1)
                else:
                    kt1_t = 0.0

            if law1_c_curve == 0:  # Elastic
                fy1_c = -k1 * 100000000.0
                kt1_c = k1
            else:
                fy1_c = -area1 * law1_fy_c
                if law1_c_curve == 1:  # LinearHardening
                    kt1_c = k1 * law1_ratio_et_c
                elif law1_c_curve == 2 and law1_fy_c != 0.0:  # LinearSoftening
                    ult_c = 2.0 * law1_G_c / (fy1_c / area1) + fy1_c / k1
                    kt1_c = -fy1_c / (ult_c - fy1_c / k1)
                else:
                    kt1_c = 0.0

            # Side 2
            if law2_t_curve == 0:  # Elastic
                fy2_t = k2 * 100000000.0
                kt2_t = k2
            else:
                fy2_t = area2 * law2_fy_t
                if law2_t_curve == 1:  # LinearHardening
                    kt2_t = k2 * law2_ratio_et_t
                elif law2_t_curve == 2 and law2_fy_t != 0.0:  # LinearSoftening
                    ult_t = 2.0 * law2_G_t / (fy2_t / area2) + fy2_t / k2
                    kt2_t = -fy2_t / (ult_t - fy2_t / k2)
                else:
                    kt2_t = 0.0

            if law2_c_curve == 0:  # Elastic
                fy2_c = -k2 * 100000000.0
                kt2_c = k2
            else:
                fy2_c = -area2 * law2_fy_c
                if law2_c_curve == 1:  # LinearHardening
                    kt2_c = k2 * law2_ratio_et_c
                elif law2_c_curve == 2 and law2_fy_c != 0.0:  # LinearSoftening
                    ult_c = 2.0 * law2_G_c / (fy2_c / area2) + fy2_c / k2
                    kt2_c = -fy2_c / (ult_c - fy2_c / k2)
                else:
                    kt2_c = 0.0

            k = _series_nb(k1, k2)
            k_out[i] = k

            tension_from_1 = (fy1_t <= fy2_t)
            fy_t = fy1_t if tension_from_1 else fy2_t
            tension_curve_1 = tension_from_1

            compression_area_from_2 = (fy1_c <= fy2_c)
            fy_c = fy2_c if compression_area_from_2 else fy1_c
            area = area2 if compression_area_from_2 else area1
            area_out[i] = area
            compression_curve_1 = (fy1_c >= fy2_c)

            tensile_elastic = (law1_t_curve == 0) if tension_curve_1 else (law2_t_curve == 0)
            tensile_linear_softening = (law1_t_curve == 2) if tension_curve_1 else (law2_t_curve == 2)
            tensile_exponential = (law1_t_curve == 3) if tension_curve_1 else (law2_t_curve == 3)

            compressive_elastic = (law1_c_curve == 0) if compression_curve_1 else (law2_c_curve == 0)
            compressive_linear_softening = (law1_c_curve == 2) if compression_curve_1 else (law2_c_curve == 2)
            compressive_parabolic = (law1_c_curve == 3) if compression_curve_1 else (law2_c_curve == 3)

            series_kt_t = _series_nb(kt1_t, kt2_t)
            series_kt_c = _series_nb(kt1_c, kt2_c)
            kt_t = k if tensile_elastic else series_kt_t
            kt_c = k if compressive_elastic else series_kt_c

            ur_t = max(fy_t / k, 0.0) if k != 0.0 else 0.0
            ur_c = min(fy_c / k, 0.0) if k != 0.0 else 0.0

            # _apply_ultimate_displacement_arrays for law1
            base_t = fy_t / k if k != 0.0 else 0.0
            if law1_t_curve in (2, 3):
                if area != 0.0 and fy_t != 0.0:
                    if tensile_linear_softening:
                        val = 2.0 * law1_G_t / (fy_t / area) + base_t
                        ur_t = val
                        kt_t = -fy_t / (val - base_t)
                    elif tensile_exponential:
                        ur_t = law1_G_t / (fy_t / area) + base_t
                    ur_t = max(ur_t, base_t)
            elif not (law1_t_curve == 0 and law1_c_curve == 0) and law1_fy_t != 0.0 and law1_E != 0.0:
                ur_t = base_t * law1_eps_u_t / (law1_fy_t / law1_E)

            base_c = fy_c / k if k != 0.0 else 0.0
            if law1_c_curve in (2, 3):
                if area != 0.0 and fy_c != 0.0:
                    if compressive_linear_softening:
                        val = 2.0 * law1_G_c / (fy_c / area) + base_c
                        ur_c = val
                        kt_c = -fy_c / (val - base_c)
                    elif compressive_parabolic:
                        ur_c = 3.0 * law1_G_c / (2.0 * fy_c / area) + 5.0 * fy_c / (3.0 * k)
                    ur_c = min(ur_c, base_c)
            elif not (law1_t_curve == 0 and law1_c_curve == 0) and law1_fy_c != 0.0 and law1_E != 0.0:
                ur_c = base_c * law1_eps_u_c / (law1_fy_c / law1_E)

            ur1_t = ur_t
            ur1_c = ur_c

            # _apply_ultimate_displacement_arrays for law2
            if law2_t_curve in (2, 3):
                if area != 0.0 and fy_t != 0.0:
                    if tensile_linear_softening:
                        val = 2.0 * law2_G_t / (fy_t / area) + base_t
                        ur_t = val
                        kt_t = -fy_t / (val - base_t)
                    elif tensile_exponential:
                        ur_t = law2_G_t / (fy_t / area) + base_t
                    ur_t = max(ur_t, base_t)
            elif not (law2_t_curve == 0 and law2_c_curve == 0) and law2_fy_t != 0.0 and law2_E != 0.0:
                ur_t = base_t * law2_eps_u_t / (law2_fy_t / law2_E)

            if law2_c_curve in (2, 3):
                if area != 0.0 and fy_c != 0.0:
                    if compressive_linear_softening:
                        val = 2.0 * law2_G_c / (fy_c / area) + base_c
                        ur_c = val
                        kt_c = -fy_c / (val - base_c)
                    elif compressive_parabolic:
                        ur_c = 3.0 * law2_G_c / (2.0 * fy_c / area) + 5.0 * fy_c / (3.0 * k)
                    ur_c = min(ur_c, base_c)
            elif not (law2_t_curve == 0 and law2_c_curve == 0) and law2_fy_c != 0.0 and law2_E != 0.0:
                ur_c = base_c * law2_eps_u_c / (law2_fy_c / law2_E)

            ur2_t = ur_t
            ur2_c = ur_c

            first_t = (ur1_t < ur2_t) and (ur1_t != 0.0)
            second_t = (ur2_t < ur1_t) and (ur2_t != 0.0)
            first_c = (ur1_c > ur2_c) and (ur1_c != 0.0)
            second_c = (ur2_c > ur1_c) and (ur2_c != 0.0)
            previous_c_linear = not (compressive_elastic or compressive_parabolic)

            if first_t:
                tension_curve_1 = True
            elif second_t:
                tension_curve_1 = False

            if first_c:
                compression_curve_1 = True
            elif second_c:
                compression_curve_1 = False

            ur_t = ur1_t if first_t else ur2_t
            ur_c = ur1_c if first_c else ur2_c

            tension_from_1_out[i] = 1 if tension_curve_1 else 0
            compression_from_1_out[i] = 1 if compression_curve_1 else 0

            # Resolved curve types for this fiber:
            t_curve = law1_t_curve if tension_curve_1 else law2_t_curve
            c_curve = law1_c_curve if compression_curve_1 else law2_c_curve

            # Populate envelope points
            rot1p = 0.0; mom1p = 0.0; rot2p = 0.0; mom2p = 0.0; rot3p = 0.0; mom3p = 0.0
            e1p = 0.0; e2p = 0.0; e3p = 0.0
            if t_curve == 0:  # Elastic
                mom1p = 1e19 * fy_t
                rot1p = mom1p / k if k != 0.0 else 0.0
                rot2p = rot1p
                rot3p = rot1p
                mom2p = mom1p
                mom3p = mom1p
                e1p = mom1p / rot1p if rot1p != 0.0 else k
            elif t_curve in (1, 2):  # LinearHardening, LinearSoftening
                mom1p = fy_t
                rot1p = fy_t / k if k != 0.0 else 0.0
                mom2p = mom1p + (ur_t - rot1p) * kt_t
                rot2p = ur_t
                mom3p = 0.0
                rot3p = ur_t * 1.01
                e1p = mom1p / rot1p if rot1p != 0.0 else k
                d2 = rot2p - rot1p
                e2p = (mom2p - mom1p) / d2 if d2 != 0.0 else 0.0
                d3 = rot3p - rot2p
                e3p = (mom3p - mom2p) / d3 if d3 != 0.0 else 0.0
            elif t_curve == 3:  # Exponential
                mom1p = fy_t
                rot1p = fy_t / k if k != 0.0 else 0.0
                rot2p = ur_t
                e1p = mom1p / rot1p if rot1p != 0.0 else k

            rot1n = 0.0; mom1n = 0.0; rot2n = 0.0; mom2n = 0.0; rot3n = 0.0; mom3n = 0.0
            e1n = 0.0; e2n = 0.0; e3n = 0.0
            if c_curve == 0:  # Elastic
                mom1n = 1e19 * fy_c
                rot1n = mom1n / k if k != 0.0 else 0.0
                e1n = mom1n / rot1n if rot1n != 0.0 else k
            elif c_curve in (1, 2):  # LinearHardening, LinearSoftening
                mom1n = fy_c
                rot1n = fy_c / k if k != 0.0 else 0.0
                mom2n = mom1n + (ur_c - rot1n) * kt_c
                rot2n = ur_c
                mom3n = 0.0
                rot3n = ur_c * 1.01
                e1n = mom1n / rot1n if rot1n != 0.0 else k
                d2 = rot2n - rot1n
                e2n = (mom2n - mom1n) / d2 if d2 != 0.0 else 0.0
                d3 = rot3n - rot2n
                e3n = (mom3n - mom2n) / d3 if d3 != 0.0 else 0.0
            elif c_curve == 3:  # Parabolic
                mom1n = fy_c / 3.0
                rot1n = fy_c / (3.0 * k) if k != 0.0 else 0.0
                mom2n = fy_c
                rot2n = 5.0 * fy_c / (3.0 * k) if k != 0.0 else 0.0
                mom3n = 0.0
                rot3n = ur_c
                e1n = mom1n / rot1n if rot1n != 0.0 else k
                if previous_c_linear:
                    prev_rot1 = fy_c / k if k != 0.0 else 0.0
                    prev_mom2 = fy_c + (ur2_c - prev_rot1) * kt_c
                    prev_d2 = ur2_c - prev_rot1
                    prev_d3 = ur2_c * 1.01 - ur2_c
                    e2n = (prev_mom2 - fy_c) / prev_d2 if prev_d2 != 0.0 else 0.0
                    e3n = (-prev_mom2) / prev_d3 if prev_d3 != 0.0 else 0.0

            eup = max(e1p, max(e2p, e3p))
            eun = max(e1n, max(e2n, e3n))

            batch_params[i, 0] = rot1p
            batch_params[i, 1] = mom1p
            batch_params[i, 2] = rot2p
            batch_params[i, 3] = mom2p
            batch_params[i, 4] = rot3p
            batch_params[i, 5] = mom3p
            batch_params[i, 6] = mom1n
            batch_params[i, 7] = rot1n
            batch_params[i, 8] = rot2n
            batch_params[i, 9] = mom2n
            batch_params[i, 10] = rot3n
            batch_params[i, 11] = mom3n
            batch_params[i, 12] = e1n
            batch_params[i, 13] = e1p
            batch_params[i, 14] = e2n
            batch_params[i, 15] = e2p
            batch_params[i, 16] = e3n
            batch_params[i, 17] = e3p
            batch_params[i, 18] = eun
            batch_params[i, 19] = eup

            fy_out[i, 0] = fy_t
            fy_out[i, 1] = fy_c
            kt_out[i, 0] = kt_t
            kt_out[i, 1] = kt_c
            ur_out[i, 0] = ur_t
            ur_out[i, 1] = ur_c
else:
    _hysteretic_kernel_nb = None


def _configure_combined_hysteretic_batch(
    props1: np.ndarray,
    law1: _HystereticLaw,
    props2: np.ndarray,
    law2: _HystereticLaw,
    *,
    interface_key: int,
    interface: Any | None = None,
) -> list[SpringHysteretic]:
    """Create all Quad/Quad transverse springs for one interface numerically.

    This is the array form of repeated ``_configure_combined_hysteretic``.
    Constitutive arithmetic remains float64 and follows the same operation
    sequence.  The unavoidable Python work is reduced to constructing and
    publishing the final spring objects.
    """
    p1 = np.asarray(props1, dtype=np.float64)
    p2 = np.asarray(props2, dtype=np.float64)
    if p1.shape != p2.shape or p1.ndim != 2 or p1.shape[1] != 3:
        raise ValueError(
            f"Expected matching (n, 3) transverse-property arrays; "
            f"received {p1.shape} and {p2.shape}"
        )
    n = p1.shape[0]
    if n == 0:
        return []
    if law1.is_elastic or law2.is_elastic:
        if interface is not None:
            interface._transverse_batch_params = None
            interface._transverse_k = None
        springs = []
        for index, (side1, side2) in enumerate(zip(p1, p2)):
            spring = _configure_combined_hysteretic(*map(float, side1), law1, *map(float, side2), law2)
            spring.key, spring.parent_key = index, interface_key
            spring.parent_type, spring.spring_purpose = "Interface", "Transversal1"
            springs.append(spring)
        return springs

    # Fast path: skip expensive column_stack and flatnonzero if all properties are positive and finite.
    p1_min = float(np.min(p1))
    p2_min = float(np.min(p2))
    if not (
        p1_min > 0.0
        and p2_min > 0.0
        and math.isfinite(p1_min)
        and math.isfinite(p2_min)
        and math.isfinite(float(np.max(p1)))
        and math.isfinite(float(np.max(p2)))
    ):
        invalid = np.column_stack((
            (~np.isfinite(p1[:, 0])) | (p1[:, 0] <= 0.0),
            (~np.isfinite(p1[:, 1])) | (p1[:, 1] <= 0.0),
            (~np.isfinite(p1[:, 2])) | (p1[:, 2] <= 0.0),
            (~np.isfinite(p2[:, 0])) | (p2[:, 0] <= 0.0),
            (~np.isfinite(p2[:, 1])) | (p2[:, 1] <= 0.0),
            (~np.isfinite(p2[:, 2])) | (p2[:, 2] <= 0.0),
        ))
        bad = np.flatnonzero(invalid)
        if bad.size:
            flat = int(bad[0])
            index, field = divmod(flat, 6)
            side = p1 if field < 3 else p2
            component = field if field < 3 else field - 3
            value = side[index, component]
            if component == 0:
                detail = (
                    "Cannot create a transverse hysteretic spring with "
                    f"stiffness K={value!r}."
                )
            elif component == 1:
                detail = (
                    "Cannot create a transverse hysteretic spring with "
                    f"area={value!r}."
                )
            else:
                detail = (
                    "Cannot create a transverse hysteretic spring with "
                    f"length={value!r}."
                )
            raise ModelPreparationError(
                f"Interface {interface_key}, transverse cell {index}: {detail}"
            )

    if _hysteretic_kernel_nb is not None:
        batch_params = np.empty((n, 20), dtype=np.float64)
        k_out = np.empty(n, dtype=np.float64)
        area_out = np.empty(n, dtype=np.float64)
        t_out = np.empty(n, dtype=np.uint8)
        c_out = np.empty(n, dtype=np.uint8)
        fy_out = np.empty((n, 2), dtype=np.float64)
        kt_out = np.empty((n, 2), dtype=np.float64)
        ur_out = np.empty((n, 2), dtype=np.float64)

        _hysteretic_kernel_nb(
            p1, p2,
            _TENSILE_CURVE_MAP[law1.tensile_curve], _COMPRESSIVE_CURVE_MAP[law1.compressive_curve],
            float(law1.E), float(law1.fy_t), float(law1.fy_c), float(law1.ratio_et_t), float(law1.ratio_et_c),
            float(law1.G_t), float(law1.G_c), float(law1.eps_u_t), float(law1.eps_u_c),
            _TENSILE_CURVE_MAP[law2.tensile_curve], _COMPRESSIVE_CURVE_MAP[law2.compressive_curve],
            float(law2.E), float(law2.fy_t), float(law2.fy_c), float(law2.ratio_et_t), float(law2.ratio_et_c),
            float(law2.G_t), float(law2.G_c), float(law2.eps_u_t), float(law2.eps_u_c),
            batch_params, k_out, area_out, t_out, c_out, fy_out, kt_out, ur_out
        )

        alfau_t = max(float(law1.alfa_u_t), float(law2.alfa_u_t))
        alfau_c = max(float(law1.alfa_u_c), float(law2.alfa_u_c))
        alfar_t = max(float(law1.alfa_r_t), float(law2.alfa_r_t))
        alfar_c = max(float(law1.alfa_r_c), float(law2.alfa_r_c))

        if interface is not None:
            interface._transverse_batch_params = batch_params
            interface._transverse_k = k_out

        if law1.tensile_curve == law2.tensile_curve:
            t_uniform = law1.tensile_curve
            t_seq = None
            t_curve = t_uniform
        else:
            t_seq = [law1.tensile_curve if t_out[idx] else law2.tensile_curve for idx in range(n)]
            t_curve = law1.tensile_curve if t_out[0] else law2.tensile_curve

        if law1.compressive_curve == law2.compressive_curve:
            c_uniform = law1.compressive_curve
            c_seq = None
            c_curve = c_uniform
        else:
            c_seq = [law1.compressive_curve if c_out[idx] else law2.compressive_curve for idx in range(n)]
            c_curve = law1.compressive_curve if c_out[0] else law2.compressive_curve

        return TransverseFiberGroup(
            batch_params,
            k=k_out,
            area=area_out,
            tensile_curve_type=t_curve,
            compressive_curve_type=c_curve,
            parent_key=interface_key,
            betap=alfau_t,
            betan=alfau_c,
            tensile_curve_types=t_seq,
            compressive_curve_types=c_seq,
            fy=fy_out,
            kt=kt_out,
            ur=ur_out,
            alfar=(alfar_t, alfar_c),
        )

    k1, area1, length1 = p1[:, 0], p1[:, 1], p1[:, 2]
    k2, area2, length2 = p2[:, 0], p2[:, 1], p2[:, 2]
    fy1_t, fy1_c, kt1_t, kt1_c = _hysteretic_side_arrays(p1, law1)
    fy2_t, fy2_c, kt2_t, kt2_c = _hysteretic_side_arrays(p2, law2)

    k = _series_array(k1, k2)

    tension_from_1 = fy1_t <= fy2_t
    fy_t = np.where(tension_from_1, fy1_t, fy2_t)
    tension_curve_1 = tension_from_1

    # Preserve the two distinct C# tie conditions from the scalar code.
    compression_area_from_2 = fy1_c <= fy2_c
    fy_c = np.where(compression_area_from_2, fy2_c, fy1_c)
    area = np.where(compression_area_from_2, area2, area1)
    compression_curve_1 = fy1_c >= fy2_c

    if law1.tensile_curve == law2.tensile_curve:
        tensile_linear_softening = (law1.tensile_curve == "LinearSoftening")
        tensile_exponential = (law1.tensile_curve == "Exponential")
        tensile_elastic = (law1.tensile_curve == "Elastic")
    else:
        tensile_linear_softening = np.where(
            tension_curve_1,
            law1.tensile_curve == "LinearSoftening",
            law2.tensile_curve == "LinearSoftening",
        )
        tensile_exponential = np.where(
            tension_curve_1,
            law1.tensile_curve == "Exponential",
            law2.tensile_curve == "Exponential",
        )
        tensile_elastic = np.where(
            tension_curve_1,
            law1.tensile_curve == "Elastic",
            law2.tensile_curve == "Elastic",
        )

    if law1.compressive_curve == law2.compressive_curve:
        compressive_linear_softening = (law1.compressive_curve == "LinearSoftening")
        compressive_parabolic = (law1.compressive_curve == "Parabolic")
        compressive_elastic = (law1.compressive_curve == "Elastic")
    else:
        compressive_linear_softening = np.where(
            compression_curve_1,
            law1.compressive_curve == "LinearSoftening",
            law2.compressive_curve == "LinearSoftening",
        )
        compressive_parabolic = np.where(
            compression_curve_1,
            law1.compressive_curve == "Parabolic",
            law2.compressive_curve == "Parabolic",
        )
        compressive_elastic = np.where(
            compression_curve_1,
            law1.compressive_curve == "Elastic",
            law2.compressive_curve == "Elastic",
        )

    series_kt_t = _series_array(kt1_t, kt2_t)
    series_kt_c = _series_array(kt1_c, kt2_c)
    kt_t = np.where(tensile_elastic, k, series_kt_t)
    kt_c = np.where(compressive_elastic, k, series_kt_c)

    ur_t = np.maximum(fy_t / k, 0.0)
    ur_c = np.minimum(fy_c / k, 0.0)

    _apply_ultimate_displacement_arrays(
        law=law1, k=k, area=area, fy_t=fy_t, fy_c=fy_c,
        tensile_linear_softening=tensile_linear_softening,
        tensile_exponential=tensile_exponential,
        compressive_linear_softening=compressive_linear_softening,
        compressive_parabolic=compressive_parabolic,
        ur_t=ur_t, ur_c=ur_c, kt_t=kt_t, kt_c=kt_c,
    )
    ur1_t = ur_t.copy()
    ur1_c = ur_c.copy()
    _apply_ultimate_displacement_arrays(
        law=law2, k=k, area=area, fy_t=fy_t, fy_c=fy_c,
        tensile_linear_softening=tensile_linear_softening,
        tensile_exponential=tensile_exponential,
        compressive_linear_softening=compressive_linear_softening,
        compressive_parabolic=compressive_parabolic,
        ur_t=ur_t, ur_c=ur_c, kt_t=kt_t, kt_c=kt_c,
    )
    ur2_t = ur_t
    ur2_c = ur_c
    # Literal Interface.SetSpring selection, including ties and zero values.
    first_t = (ur1_t < ur2_t) & (ur1_t != 0.0)
    second_t = (ur2_t < ur1_t) & (ur2_t != 0.0)
    first_c = (ur1_c > ur2_c) & (ur1_c != 0.0)
    second_c = (ur2_c > ur1_c) & (ur2_c != 0.0)
    previous_c_linear = np.logical_not(np.logical_or(compressive_elastic, compressive_parabolic))
    tension_curve_1 = np.where(first_t, True, np.where(second_t, False, tension_curve_1))
    compression_curve_1 = np.where(first_c, True, np.where(second_c, False, compression_curve_1))
    ur_t = np.where(first_t, ur1_t, ur2_t)
    ur_c = np.where(first_c, ur1_c, ur2_c)

    alfau_t = max(float(law1.alfa_u_t), float(law2.alfa_u_t))
    alfau_c = max(float(law1.alfa_u_c), float(law2.alfa_u_c))
    alfar_t = max(float(law1.alfa_r_t), float(law2.alfa_r_t))
    alfar_c = max(float(law1.alfa_r_c), float(law2.alfa_r_c))
    total_length = length1 + length2

    if law1.tensile_curve == law2.tensile_curve:
        t_uniform = law1.tensile_curve
        is_t_elastic = (t_uniform == "Elastic")
        is_t_linear = (t_uniform in ("LinearHardening", "LinearSoftening"))
        is_t_expo = (t_uniform == "Exponential")
    else:
        t_uniform = None
        t_curve_arr = np.where(tension_curve_1, law1.tensile_curve, law2.tensile_curve)
        is_t_elastic = (t_curve_arr == "Elastic")
        is_t_linear = np.isin(t_curve_arr, ("LinearHardening", "LinearSoftening"))
        is_t_expo = (t_curve_arr == "Exponential")

    if law1.compressive_curve == law2.compressive_curve:
        c_uniform = law1.compressive_curve
        is_c_elastic = (c_uniform == "Elastic")
        is_c_linear = (c_uniform in ("LinearHardening", "LinearSoftening"))
        is_c_para = (c_uniform == "Parabolic")
    else:
        c_uniform = None
        c_curve_arr = np.where(compression_curve_1, law1.compressive_curve, law2.compressive_curve)
        is_c_elastic = (c_curve_arr == "Elastic")
        is_c_linear = np.isin(c_curve_arr, ("LinearHardening", "LinearSoftening"))
        is_c_para = (c_curve_arr == "Parabolic")

    batch_params = np.zeros((n, 20), dtype=np.float64)
    rot1p = batch_params[:, 0]
    mom1p = batch_params[:, 1]
    rot2p = batch_params[:, 2]
    mom2p = batch_params[:, 3]
    rot3p = batch_params[:, 4]
    mom3p = batch_params[:, 5]
    mom1n = batch_params[:, 6]
    rot1n = batch_params[:, 7]
    rot2n = batch_params[:, 8]
    mom2n = batch_params[:, 9]
    rot3n = batch_params[:, 10]
    mom3n = batch_params[:, 11]
    e1n = batch_params[:, 12]
    e1p = batch_params[:, 13]
    e2n = batch_params[:, 14]
    e2p = batch_params[:, 15]
    e3n = batch_params[:, 16]
    e3p = batch_params[:, 17]

    if np.any(is_t_elastic):
        m = is_t_elastic
        mom1p[m] = 1e19 * fy_t[m]
        rot1p[m] = np.where(k[m] != 0.0, mom1p[m] / k[m], 0.0)
        rot2p[m] = rot1p[m]
        rot3p[m] = rot1p[m]
        mom2p[m] = mom1p[m]
        mom3p[m] = mom1p[m]
        rot_nonzero = (rot1p[m] != 0.0)
        e1p_m = k[m].copy()
        np.divide(mom1p[m], rot1p[m], out=e1p_m, where=rot_nonzero)
        e1p[m] = e1p_m

    if np.any(is_t_linear):
        m = is_t_linear
        mom1p[m] = fy_t[m]
        rot1p[m] = np.where(k[m] != 0.0, fy_t[m] / k[m], 0.0)
        mom2p[m] = mom1p[m] + (ur_t[m] - rot1p[m]) * kt_t[m]
        rot2p[m] = ur_t[m]
        mom3p[m] = 0.0
        rot3p[m] = ur_t[m] * 1.01
        rot_nonzero = (rot1p[m] != 0.0)
        e1p_m = k[m].copy()
        np.divide(mom1p[m], rot1p[m], out=e1p_m, where=rot_nonzero)
        e1p[m] = e1p_m
        denom2 = rot2p[m] - rot1p[m]
        denom2_nonzero = (denom2 != 0.0)
        e2p_m = np.zeros_like(denom2)
        np.divide(mom2p[m] - mom1p[m], denom2, out=e2p_m, where=denom2_nonzero)
        e2p[m] = e2p_m
        denom3 = rot3p[m] - rot2p[m]
        denom3_nonzero = (denom3 != 0.0)
        e3p_m = np.zeros_like(denom3)
        np.divide(mom3p[m] - mom2p[m], denom3, out=e3p_m, where=denom3_nonzero)
        e3p[m] = e3p_m

    if np.any(is_t_expo):
        m = is_t_expo
        mom1p[m] = fy_t[m]
        rot1p[m] = np.where(k[m] != 0.0, fy_t[m] / k[m], 0.0)
        rot2p[m] = ur_t[m]
        rot_nonzero = (rot1p[m] != 0.0)
        e1p_m = k[m].copy()
        np.divide(mom1p[m], rot1p[m], out=e1p_m, where=rot_nonzero)
        e1p[m] = e1p_m

    if np.any(is_c_elastic):
        m = is_c_elastic
        mom1n[m] = 1e19 * fy_c[m]
        rot1n[m] = np.where(k[m] != 0.0, mom1n[m] / k[m], 0.0)
        rot_nonzero = (rot1n[m] != 0.0)
        e1n_m = k[m].copy()
        np.divide(mom1n[m], rot1n[m], out=e1n_m, where=rot_nonzero)
        e1n[m] = e1n_m

    if np.any(is_c_linear):
        m = is_c_linear
        mom1n[m] = fy_c[m]
        rot1n[m] = np.where(k[m] != 0.0, fy_c[m] / k[m], 0.0)
        mom2n[m] = mom1n[m] + (ur_c[m] - rot1n[m]) * kt_c[m]
        rot2n[m] = ur_c[m]
        mom3n[m] = 0.0
        rot3n[m] = ur_c[m] * 1.01
        rot_nonzero = (rot1n[m] != 0.0)
        e1n_m = k[m].copy()
        np.divide(mom1n[m], rot1n[m], out=e1n_m, where=rot_nonzero)
        e1n[m] = e1n_m
        denom2 = rot2n[m] - rot1n[m]
        denom2_nonzero = (denom2 != 0.0)
        e2n_m = np.zeros_like(denom2)
        np.divide(mom2n[m] - mom1n[m], denom2, out=e2n_m, where=denom2_nonzero)
        e2n[m] = e2n_m
        denom3 = rot3n[m] - rot2n[m]
        denom3_nonzero = (denom3 != 0.0)
        e3n_m = np.zeros_like(denom3)
        np.divide(mom3n[m] - mom2n[m], denom3, out=e3n_m, where=denom3_nonzero)
        e3n[m] = e3n_m

    if np.any(is_c_para):
        m = is_c_para
        mom1n[m] = fy_c[m] / 3.0
        rot1n[m] = np.where(k[m] != 0.0, fy_c[m] / (3.0 * k[m]), 0.0)
        mom2n[m] = fy_c[m]
        rot2n[m] = np.where(k[m] != 0.0, 5.0 * fy_c[m] / (3.0 * k[m]), 0.0)
        mom3n[m] = 0.0
        rot3n[m] = ur_c[m]
        rot_nonzero = (rot1n[m] != 0.0)
        e1n_m = k[m].copy()
        np.divide(mom1n[m], rot1n[m], out=e1n_m, where=rot_nonzero)
        e1n[m] = e1n_m

    preserve_c = np.logical_and(is_c_para, previous_c_linear)
    if np.any(preserve_c):
        mask = preserve_c
        previous_rot1 = fy_c[mask] / k[mask]
        previous_mom2 = fy_c[mask] + (ur2_c[mask] - previous_rot1) * kt_c[mask]
        previous_delta2 = ur2_c[mask] - previous_rot1
        previous_delta3 = ur2_c[mask] * 1.01 - ur2_c[mask]
        previous_e2 = np.zeros_like(previous_delta2)
        previous_e3 = np.zeros_like(previous_delta3)
        np.divide(previous_mom2 - fy_c[mask], previous_delta2, out=previous_e2, where=previous_delta2 != 0.0)
        np.divide(-previous_mom2, previous_delta3, out=previous_e3, where=previous_delta3 != 0.0)
        e2n[mask] = previous_e2
        e3n[mask] = previous_e3

    eup = np.maximum(np.maximum(e1p, e2p), e3p)
    eun = np.maximum(np.maximum(e1n, e2n), e3n)
    batch_params[:, 18] = eun
    batch_params[:, 19] = eup

    energy_a = 0.5 * (
        rot1p * mom1p
        + (rot2p - rot1p) * (mom2p + mom1p)
        + (rot3p - rot2p) * (mom3p + mom2p)
        + rot1n * mom1n
        + (rot2n - rot1n) * (mom2n + mom1n)
        + (rot3n - rot2n) * (mom3n + mom2n)
    )

    if interface is not None:
        interface._transverse_batch_params = batch_params
        interface._transverse_k = k

    t_seq = (
        None
        if t_uniform is not None
        else [law1.tensile_curve if tension_curve_1[idx] else law2.tensile_curve for idx in range(n)]
    )
    c_seq = (
        None
        if c_uniform is not None
        else [law1.compressive_curve if compression_curve_1[idx] else law2.compressive_curve for idx in range(n)]
    )
    t_curve = t_uniform or (law1.tensile_curve if tension_curve_1[0] else law2.tensile_curve)
    c_curve = c_uniform or (law1.compressive_curve if compression_curve_1[0] else law2.compressive_curve)

    return TransverseFiberGroup(
        batch_params,
        k=k,
        area=area,
        tensile_curve_type=t_curve,
        compressive_curve_type=c_curve,
        parent_key=interface_key,
        betap=alfau_t,
        betan=alfau_c,
        tensile_curve_types=t_seq,
        compressive_curve_types=c_seq,
        fy=np.column_stack((fy_t, fy_c)),
        kt=np.column_stack((kt_t, kt_c)),
        ur=np.column_stack((ur_t, ur_c)),
        alfar=(alfar_t, alfar_c),
    )

def _copy_hysteretic_spring(sp: SpringHysteretic | SpringElastic) -> SpringHysteretic | SpringElastic:
    """Copy one configured hysteretic spring without recursive deepcopy.

    All non-scalar mutable state in ``SpringHysteretic`` is held by the base
    ``extra`` mapping and the seven list-backed constitutive/state fields
    below.  C# restraint-side combination needs an independent spring object,
    but recursively walking dozens of immutable scalar attributes is wasted
    work during preprocessing.
    """
    out = copy.copy(sp)
    out.extra = sp.extra.copy()
    if isinstance(sp, SpringElastic):
        return out
    out.fy = sp.fy.copy()
    out.kt = sp.kt.copy()
    out.ur = sp.ur.copy()
    out.alfau = sp.alfau.copy()
    out.alfar = sp.alfar.copy()
    out.umax = sp.umax.copy()
    out.uy_corr = sp.uy_corr.copy()
    return out


def _copy_coulomb_spring(sp: SpringCoulomb03) -> SpringCoulomb03:
    """Copy one configured Coulomb spring with independent mutable state."""
    out = copy.copy(sp)
    out.extra = sp.extra.copy()
    out.fy = sp.fy.copy()
    out.ur = sp.ur.copy()
    out.umax = sp.umax.copy()
    return out


def _combine_hysteretic(sp1: SpringHysteretic | SpringElastic, sp2: SpringHysteretic | SpringElastic, restrained: bool,
                        law1: _HystereticLaw, law2: _HystereticLaw) -> SpringHysteretic | SpringElastic:
    if isinstance(sp1, SpringElastic) and isinstance(sp2, SpringElastic):
        k = _series(sp1.k, sp2.k, restrained)
        return SpringElastic(type_of="HiStrA.Objects.SpringLinearElastic", k=k, k_tang=k, area=sp1.area,
                             length=sp1.length + sp2.length)
    if sp1.k == -1.0:
        out = _copy_hysteretic_spring(sp2)
    elif sp2.k == -1.0:
        out = _copy_hysteretic_spring(sp1)
    elif isinstance(sp1, SpringElastic) or isinstance(sp2, SpringElastic):
        elastic, nonlinear = (sp1, sp2) if isinstance(sp1, SpringElastic) else (sp2, sp1)
        out = _new_hysteretic_spring()
        out.k = _series(elastic.k, nonlinear.k, restrained)
        out.fy, out.area = nonlinear.fy.copy(), nonlinear.area
        out.alfar, out.alfau = nonlinear.alfar.copy(), nonlinear.alfau.copy()
        out.tensile_curve_type, out.compressive_curve_type = nonlinear.tensile_curve_type, nonlinear.compressive_curve_type
        out.kt = [out.k if curve == "Elastic" else _series(kt, elastic.k, restrained)
                  for curve, kt in zip((out.tensile_curve_type, out.compressive_curve_type), nonlinear.kt)]
        out.length = sp1.length + sp2.length
    else:
        out = _new_hysteretic_spring()
        out.k = _series(sp1.k, sp2.k, restrained)
        # C# SetSpringYieldingForce: weakest tension and least-compressive
        # compression, carrying the associated area.
        if sp1.fy[0] <= sp2.fy[0]:
            out.fy[0], area_t = sp1.fy[0], sp1.area
        else:
            out.fy[0], area_t = sp2.fy[0], sp2.area
        if sp1.fy[1] <= sp2.fy[1]:
            out.fy[1], area_c = sp2.fy[1], sp2.area
        else:
            out.fy[1], area_c = sp1.fy[1], sp1.area
        out.area = area_c
        out.length = sp1.length + sp2.length
        out.alfau = [max(sp1.alfau[0], sp2.alfau[0]), max(sp1.alfau[1], sp2.alfau[1])]
        out.alfar = [max(sp1.alfar[0], sp2.alfar[0]), max(sp1.alfar[1], sp2.alfar[1])]
        # The current materials use matching curve families. Preserve the
        # weaker spring's family for mixed cases, matching the C# switch.
        out.tensile_curve_type = sp1.tensile_curve_type if sp1.fy[0] <= sp2.fy[0] else sp2.tensile_curve_type
        out.compressive_curve_type = sp1.compressive_curve_type if sp1.fy[1] >= sp2.fy[1] else sp2.compressive_curve_type
        out.kt = [
            out.k if out.tensile_curve_type == "Elastic" else _series(sp1.kt[0], sp2.kt[0], restrained),
            out.k if out.compressive_curve_type == "Elastic" else _series(sp1.kt[1], sp2.kt[1], restrained),
        ]
        out.ur = [max(out.fy[0] / out.k if out.k else 0.0, 0.0), min(out.fy[1] / out.k if out.k else 0.0, 0.0)]
        _set_ultimate_displacement(out, law1, law1)
        ur1 = out.ur[:]
        _set_ultimate_displacement(out, law2, law2)
        ur2 = out.ur[:]
        # Interface.SetSpring reselects the family after the two separate
        # SetUltimateDisplacement calls; strict comparisons are intentional.
        if ur1[0] < ur2[0] and ur1[0] != 0.0:
            out.ur[0] = ur1[0]
            out.tensile_curve_type = law1.tensile_curve
        elif ur2[0] < ur1[0] and ur2[0] != 0.0:
            out.ur[0] = ur2[0]
            out.tensile_curve_type = law2.tensile_curve
        if ur1[1] > ur2[1] and ur1[1] != 0.0:
            out.ur[1] = ur1[1]
            out.compressive_curve_type = law1.compressive_curve
        elif ur2[1] > ur1[1] and ur2[1] != 0.0:
            out.ur[1] = ur2[1]
            out.compressive_curve_type = law2.compressive_curve
        # initialize() already resets both trial and committed state.
        out.initialize()
        return out
    _set_ultimate_displacement(out, law1, law2)
    # initialize() already resets both trial and committed state.
    out.initialize()
    return out


def _combine_coulomb(
    sp1: SpringCoulomb03,
    sp2: SpringCoulomb03,
    restrained: bool,
    *,
    preserve_single_side_identity: bool = False,
) -> SpringCoulomb03:
    # C# has two relevant dispatch paths here.  A normal restraint interface
    # combines a LinearElastic restraint-side placeholder with the active
    # Coulomb spring, which returns a new object.  A custom-material restraint
    # (the Soil mutation used by scour/Vert) has Coulomb03 on both sides; its
    # specialised overload returns the *existing* non-rigid-side object when
    # the opposite side has K == -1.  Keep the default clone semantics for the
    # ordinary path and opt into identity preservation only for that custom
    # Coulomb03/Coulomb03 path.
    if sp1.k == -1.0:
        return sp2 if preserve_single_side_identity else _copy_coulomb_spring(sp2)
    if sp2.k == -1.0:
        return sp1 if preserve_single_side_identity else _copy_coulomb_spring(sp1)
    k = _series(sp1.k, sp2.k, restrained)
    cohesion = min(sp1.cohesion, sp2.cohesion)
    area = sp1.area if sp1.cohesion <= sp2.cohesion else sp2.area
    mu = min(sp1.mu, sp2.mu)
    ur = min(sp1.ur[0], sp2.ur[0])
    # C# CombinationSpring(SpringCoulomb03, ...) uses each temporary
    # spring's *actual* hardening modulus H, not the serialized class
    # property PlasticStiffnessRatio.  SetQuadSlidSpring intentionally leaves
    # that property at its SpringCoulomb03 default (1e-4), while the envelope
    # tangent E2p is built from the material ratio.  Using the property here
    # introduced an artificial softening branch for the common material value
    # SlidingPlasticStiffnessRatio=0 and changed the committed Vert phase of
    # near-zero-capacity in-plane sliders.
    h1 = sp1.h
    h2 = sp2.h
    h = min(h1, h2)
    ktan = -k * h / (k - h) if k != h else 0.0
    ratio = ktan / k if k else 0.0
    law = _CoulombLaw(
        E=0.0, cohesion=0.0, mu=mu, plastic_stiffness_ratio=ratio,
        max_tensile_ratio=min(sp1.max_tensile_ratio, sp2.max_tensile_ratio),
        sub_law=sp1.sub_law, hysteretic_type=sp1.hysteretic_type,
        ductility=ur, is_ductility_fixed=True,
    )
    out = _configure_coulomb(k=k, area=area, length=sp1.length + sp2.length, law=law,
                             cohesion_force=cohesion, mu=mu, ur=ur,
                             hysteretic_type=sp1.hysteretic_type)
    return out


def _combine_sliding(
    sp1: SpringCoulomb03 | SpringElastic,
    sp2: SpringCoulomb03 | SpringElastic,
    restrained: bool,
    *,
    preserve_single_side_identity: bool = False,
) -> SpringCoulomb03 | SpringElastic:
    """Dispatch the C# sliding-spring overloads without changing spring type."""
    if isinstance(sp1, SpringElastic) and isinstance(sp2, SpringElastic):
        k = _series(sp1.k, sp2.k, restrained)
        return SpringElastic(
            type_of="HiStrA.Objects.SpringLinearElastic",
            k=k,
            k_tang=k,
            area=sp1.area,
        )

    if isinstance(sp1, SpringElastic) or isinstance(sp2, SpringElastic):
        elastic = sp1 if isinstance(sp1, SpringElastic) else sp2
        coulomb = sp2 if isinstance(sp1, SpringElastic) else sp1
        assert isinstance(coulomb, SpringCoulomb03)
        k = _series(elastic.k, coulomb.k, restrained)
        h = coulomb.h
        ktan = -k * h / (k - h) if k != h else 0.0
        law = _CoulombLaw(
            E=0.0,
            cohesion=0.0,
            mu=coulomb.mu,
            plastic_stiffness_ratio=ktan / k if k else 0.0,
            max_tensile_ratio=coulomb.max_tensile_ratio,
            sub_law=coulomb.sub_law,
            hysteretic_type=coulomb.hysteretic_type,
            ductility=coulomb.ur[0],
            is_ductility_fixed=True,
        )
        return _configure_coulomb(
            k=k,
            area=coulomb.area,
            length=elastic.length + coulomb.length,
            law=law,
            cohesion_force=coulomb.cohesion,
            mu=coulomb.mu,
            ur=coulomb.ur[0],
            hysteretic_type=coulomb.hysteretic_type,
        )

    return _combine_coulomb(
        sp1,
        sp2,
        restrained,
        preserve_single_side_identity=preserve_single_side_identity,
    )
