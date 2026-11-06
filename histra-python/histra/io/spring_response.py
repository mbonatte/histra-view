"""Vectorized read-only projections of C# Spring response getters.

Source: Spring.GetStrain; SpringHysteretic and SpringCoulomb03 GetUp,
GetStrainPlastic, GetUpOverUr. These are response projections, not constitutive
updates. Undefined native divisions are represented by zero plus validity masks.
"""
from __future__ import annotations

import numpy as np

from histra.types.phase_enum import PhaseEnum

ELASTIC, HYSTERETIC, COULOMB = 1, 8, 12
SPRING_RESPONSE_METADATA = {
    "scope": "committed_stage_end",
    "units": {"displacement": "cm", "length": "cm", "plastic_displacement": "cm",
              "strain": "1", "plastic_strain": "1", "plastic_ratio": "C# GetUpOverUr",
              "initial_stiffness": "kN/cm", "tangent_stiffness": "kN/cm"},
    "undefined": "zero placeholder with the corresponding *_valid mask equal to 0",
    "damage": "native phase, is_plastic, is_ruptured and is_slipping; no universal scalar damage",
    "plastic_ratio": "native demand measure, not bounded to [0,1]; Hysteretic unlimited branches return cm",
}


SPRING_RESPONSE_FIELDS = (
    "force", "stress", "phase", "area", "stress_valid", "displacement", "length", "spring_type",
    "initial_stiffness", "tangent_stiffness", "strain", "strain_valid", "plastic_displacement",
    "plastic_displacement_valid", "plastic_strain", "plastic_strain_valid", "plastic_ratio",
    "plastic_ratio_valid", "plastic_ratio_is_normalized", "is_plastic", "is_ruptured", "is_slipping", "plastic_history_valid",
    "plastic_tension_indicator", "plastic_compression_indicator",
)


def _finite_projection(value, dtype):
    with np.errstate(over='ignore', invalid='ignore'):
        projected = np.asarray(value, dtype=dtype)
    valid = np.isfinite(projected)
    return np.where(valid, projected, 0), valid.astype(np.uint8)


def project_spring_response(displacement, force, stiffness, yield_force, ultimate_displacement,
                            length, spring_type, phase, tangent):
    """Use original doubles for calculations, and native Single getter boundaries."""
    u, f, k, fy, ur, length = (np.asarray(v, np.float64) for v in
                              (displacement, force, stiffness, yield_force, ultimate_displacement, length))
    kind, phase = np.asarray(spring_type), np.asarray(phase)
    positive = u >= 0
    side_fy = np.where(positive, fy[:, 0], fy[:, 1])
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        yield_u = side_fy / k
        hysteretic_up = np.where(np.abs(u) < np.abs(yield_u), 0.0, np.abs(u) - np.abs(yield_u))
        coulomb_up = u - f / k
        coulomb_up = np.where(np.abs(coulomb_up) <= np.abs(yield_u) * 1e-5, 0.0, coulomb_up)
        up = np.where(kind == HYSTERETIC, hysteretic_up, np.where(kind == COULOMB, coulomb_up, 0.0))
        ratio, normalized = _plastic_ratio(u, up, ur, kind)
        values = {"plastic_displacement": up, "strain": u / length,
                  "plastic_strain": np.where(kind == ELASTIC, 0.0, up / length),
                  "plastic_ratio": ratio}
    fields = {"displacement": u.copy(), "length": length.copy(), "initial_stiffness": k.copy(),
              "tangent_stiffness": np.asarray(tangent, np.float64).copy(), "spring_type": kind.astype(np.uint8)}
    for name, value in values.items():
        fields[name], fields[f"{name}_valid"] = _finite_projection(value, np.float64 if name == 'plastic_displacement' else np.float32)
    fields["plastic_ratio_is_normalized"] = (normalized & fields["plastic_ratio_valid"].astype(bool)).astype(np.uint8)
    fields.update(_phase_flags(phase))
    return fields


def _plastic_ratio(u, up, ur, kind):
    # C#'s unlimited Hysteretic branch deliberately returns displacement, not a
    # normalized ratio. Preserve it instead of inventing a capped damage index.
    positive = u >= 0
    side_ur = np.where(positive, ur[:, 0], ur[:, 1])
    ratio = up / side_ur
    hysteretic_ratio = np.where(positive,
                               np.where(side_ur < 100000.0, ratio, up),
                               np.where(-side_ur < 100000.0, np.abs(ratio), np.abs(up)))
    normalized = (kind != HYSTERETIC) | np.where(positive, side_ur < 100000.0, -side_ur < 100000.0)
    return np.where(kind == HYSTERETIC, hysteretic_ratio, np.where(kind == COULOMB, ratio, 0.0)), normalized


def _phase_flags(phase):
    return {
        "is_plastic": np.isin(phase, (int(PhaseEnum.Plastic_t), int(PhaseEnum.Plastic_c))).astype(np.uint8),
        "is_ruptured": np.isin(phase, (int(PhaseEnum.Rupture), int(PhaseEnum.RuptureTraz), int(PhaseEnum.RuptureComp))).astype(np.uint8),
        "is_slipping": (phase == int(PhaseEnum.Slip)).astype(np.uint8),
    }
