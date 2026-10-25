"""C#-compatible masonry material to constitutive-law mappings.

The authoritative implementation is
``ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs``
and ``Objects.Material/MasonryMaterial.cs``.  Masonry properties are stored as
``System.Single`` in C#, so every numeric read is rounded to float32 before it
is promoted to Python's float.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from histra.model.masonry_material import MasonryMaterial


_TENSILE_CURVES = ("Elastic", "LinearHardening", "LinearSoftening", "Exponential")
_COMPRESSIVE_CURVES = ("Elastic", "LinearHardening", "LinearSoftening", "Parabolic")
_FLEX_LAWS = (
    "ElastoPlasticDuctilityFixed",
    "ElastoPlasticFracturalEnergyFixed",
    "Linear",
)
_SHEAR_LAWS = (
    "Elastic",
    "ElastoPlastic",
    "ElastoPlasticDuctilityFixed",
    "ElastoPlasticAndSoftening",
    "ElastoPlasticFractureEnergyFixed",
    "ElastoPlasticEnergySigmaInterpolation",
)
_SHEAR_DOMAINS = ("Linear", "Coulomb", "Cacovic")
_HYSTERETIC_TYPES = ("Initial", "Origin", "Takeda", "Mixed")


def material_enum(
    material: MasonryMaterial,
    name: str,
    values: tuple[str, ...],
    default: str,
) -> str:
    """Decode a named or numeric C# enum and reject unknown stored values."""
    raw = material.value(name, default)
    text = str(raw).strip()
    if not text:
        text = default
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and math.isfinite(numeric) and numeric.is_integer():
        index = int(numeric)
        if 0 <= index < len(values):
            return values[index]
    token = text.rsplit(".", 1)[-1].casefold()
    for value in values:
        if token == value.casefold():
            return value
    raise ValueError(
        f"MasonryMaterial {material.key} has unsupported {name}={raw!r}; "
        f"expected one of {values} or its numeric C# enum value."
    )


def validate_masonry_material_enums(material: MasonryMaterial) -> None:
    """Validate every V1 masonry enum that selects a constitutive branch."""
    for name in ("TensileCurveType", "TensileCurveTypeVertical"):
        material_enum(material, name, _TENSILE_CURVES, "LinearSoftening")
    for name in ("CompressiveCurveType", "CompressiveCurveTypeVertical"):
        material_enum(material, name, _COMPRESSIVE_CURVES, "LinearSoftening")
    material_enum(
        material,
        "ConstitutiveLawFlex",
        _FLEX_LAWS,
        "ElastoPlasticDuctilityFixed",
    )
    material_enum(
        material,
        "ConstitutiveLawMasonryShear",
        _SHEAR_LAWS,
        "Elastic",
    )
    material_enum(material, "CriterioSnervamento", _SHEAR_DOMAINS, "Linear")
    for name in (
        "SlidingYieldingDomainHor",
        "SlidingYieldingDomainVert",
        "SlidingYieldingDomainDir3",
    ):
        material_enum(material, name, _SHEAR_DOMAINS, "Linear")
    for name in (
        "UnloadShear",
        "UnloadTractionRockingHor",
        "UnloadCompressionRockingHor",
        "UnloadTractionRockingVer",
        "UnloadCompressionRockingVer",
    ):
        if name in material.properties:
            material_enum(material, name, _HYSTERETIC_TYPES, "Initial")


@dataclass(frozen=True)
class HystereticLaw:
    E: float
    fy_t: float
    fy_c: float
    tensile_curve: str
    compressive_curve: str
    ratio_et_t: float
    ratio_et_c: float
    alfa_r_t: float
    alfa_r_c: float
    alfa_u_t: float
    alfa_u_c: float
    G_t: float
    G_c: float
    eps_u_t: float
    eps_u_c: float
    law_type: str
    is_elastic: bool = False


@dataclass(frozen=True)
class CoulombLaw:
    E: float
    cohesion: float
    mu: float
    plastic_stiffness_ratio: float
    max_tensile_ratio: float
    reload_stiffness_ratio: float = 1.0
    plastic_stiffness_ratio2: float = 1.0
    plastic_strain: float = 1.0
    sub_law: str = "Coulomb"
    hysteretic_type: str = "Initial"
    fracture_energy: bool = False
    G: float = 0.0
    ductility: float = 100000.0
    is_ductility_fixed: bool = True
    check_contact_area: bool = False
    bcacovic: float = 0.0
    is_elastic: bool = False


def material_bool(
    material: MasonryMaterial, name: str, default: bool = False
) -> bool:
    return bool(material.value(name, default))


def material_float(
    material: MasonryMaterial, name: str, default: float = 0.0
) -> float:
    """Read a C# ``MasonryMaterial`` numeric property as ``System.Single``."""
    return float(np.float32(float(material.value(name, default))))


def _alfa_shear(material: MasonryMaterial) -> float:
    """Return C# ``MasonryMaterial.AlfaShear``'s clamped value."""
    value = material_float(material, "AlfaShearUser", 1.0)
    if value >= float(np.float32(0.99999)):
        return float(np.float32(0.99999))
    if value < float(np.float32(1.0e-5)):
        return float(np.float32(1.0e-5))
    return value


def flex_law(material: MasonryMaterial, *, vertical: bool = False) -> HystereticLaw:
    suffix = "Ver" if vertical else "Hor"
    curve_suffix = "Vertical" if vertical else ""
    tensile_curve = material_enum(
        material,
        f"TensileCurveType{curve_suffix}",
        _TENSILE_CURVES,
        "LinearSoftening",
    )
    compressive_curve = material_enum(
        material,
        f"CompressiveCurveType{curve_suffix}",
        _COMPRESSIVE_CURVES,
        "LinearSoftening",
    )
    law_type = material_enum(
        material,
        "ConstitutiveLawFlex",
        _FLEX_LAWS,
        "ElastoPlasticDuctilityFixed",
    )
    E = material_float(material, "Ever" if vertical else "Ehor")
    fy_t = material_float(material, f"Ftm{suffix}")
    fy_c = material_float(material, f"Fm{suffix}")
    duct_t = material_float(material, f"DuctTrazRocking{suffix}", 1.0)
    duct_c = material_float(material, f"DuctComprRocking{suffix}", 1.0)
    # ConstitutiveLawHysteretic uses IsDuct*=true for effectively unlimited
    # ultimate strain and false for a yield-strain-scaled ductility value.
    eps_t = (
        1.0e20
        if material_bool(material, "IsDuctTraz", True)
        else duct_t * fy_t / E
    )
    eps_c = (
        1.0e20
        if material_bool(material, "IsDuctCompr", False)
        else duct_c * fy_c / E
    )
    return HystereticLaw(
        E=E,
        fy_t=fy_t,
        fy_c=fy_c,
        tensile_curve=tensile_curve,
        compressive_curve=compressive_curve,
        ratio_et_t=material_float(material, "RatioEtTraction"),
        ratio_et_c=material_float(material, "RatioEtCompression"),
        alfa_r_t=1.0,
        alfa_r_c=1.0,
        alfa_u_t=material_float(material, f"BetaUnloadTractionRocking{suffix}"),
        alfa_u_c=material_float(material, f"BetaUnloadCompressionRocking{suffix}"),
        G_t=material_float(material, "GtVer" if vertical else "Gt"),
        G_c=material_float(material, "GcVer" if vertical else "Gc"),
        eps_u_t=eps_t,
        eps_u_c=eps_c,
        law_type=law_type,
        is_elastic=(tensile_curve == compressive_curve == "Elastic"),
    )


def diagonal_flex_law(material: MasonryMaterial) -> HystereticLaw:
    """Blend the actual masonry Hysteretic/Elastic laws used by Quad.

    ConstitutiveLawFlex names do not make these ConstitutiveLawElastoPlastic
    objects: current C# SetFlexionalConstitutiveLaw constructs Hysteretic
    unless both curves are Elastic. Use that runtime class's interpolation.
    """
    from .material_selection import _blend_hysteretic_laws
    from .csharp_math import csharp_pow

    vertical = flex_law(material, vertical=True)
    horizontal = flex_law(material, vertical=False)
    c = 0.5 * csharp_pow(2.0, 0.5)
    return _blend_hysteretic_laws(vertical, horizontal, c, c)


def shear_law(material: MasonryMaterial) -> CoulombLaw | HystereticLaw:
    law_type = material_enum(
        material,
        "ConstitutiveLawMasonryShear",
        _SHEAR_LAWS,
        "Elastic",
    )
    is_ductility = law_type in {"Elastic", "ElastoPlastic"}
    law = CoulombLaw(
        E=float(np.float32(np.float32(material_float(material, "Gd")) / np.float32(_alfa_shear(material)))),
        cohesion=material_float(material, "fvk0d"),
        mu=material_float(material, "FrictionRatioShear"),
        plastic_stiffness_ratio=material_float(
            material, "ShearPlasticStiffnessRatio"
        ),
        max_tensile_ratio=material_float(material, "ShearMaxTensileRatio", 0.5),
        reload_stiffness_ratio=material_float(
            material, "ShearReloadStiffnessRatio", 1.0
        ),
        plastic_stiffness_ratio2=material_float(
            material, "ShearPlasticStiffnessRatio2", 1.0
        ),
        plastic_strain=material_float(material, "ShearPlasticStrain", 100.0),
        sub_law=material_enum(
            material, "CriterioSnervamento", _SHEAR_DOMAINS, "Linear"
        ),
        hysteretic_type=material_enum(
            material, "UnloadShear", _HYSTERETIC_TYPES, "Initial"
        ),
        fracture_energy=(law_type == "ElastoPlasticFractureEnergyFixed"),
        G=material_float(material, "FractureEnergyShear"),
        ductility=(
            1.0e20
            if is_ductility
            else material_float(material, "DuctilityShear", 100.0)
        ),
        is_ductility_fixed=not is_ductility,
        check_contact_area=material_bool(material, "CheckContactArea", False),
        bcacovic=material_float(material, "Bcacovic"),
    )
    if law.sub_law == "Coulomb" and law.mu == 0.0:
        # Original SetShearConstitutiveLaw dispatches on Single friction.
        ultimate = material_float(material, "ShearUltimateStrain", 0.005)
        return HystereticLaw(
            E=law.E, fy_t=law.cohesion, fy_c=material_float(material, "FmHor"),
            tensile_curve="LinearSoftening", compressive_curve="LinearSoftening",
            ratio_et_t=material_float(material, "RatioEtTraction"),
            ratio_et_c=material_float(material, "RatioEtCompression"),
            alfa_r_t=1.0, alfa_r_c=1.0, alfa_u_t=0.0, alfa_u_c=0.0,
            G_t=0.0, G_c=0.0, eps_u_t=ultimate, eps_u_c=ultimate,
            law_type=law_type,
        )
    return law


def sliding_law(
    material: MasonryMaterial,
    *,
    out_of_plane: bool,
    direction: str,
) -> CoulombLaw:
    """Map one of C#'s horizontal, vertical or direction-3 sliding laws."""
    normalized = direction.casefold()
    if normalized not in {"hor", "vert", "dir3"}:
        raise ValueError(f"Unsupported sliding-law direction {direction!r}.")

    E = material_float(material, "Gd")
    if not out_of_plane and normalized != "dir3":
        E = float(np.float32(np.float32(2.0) * np.float32(E) / np.float32(np.float32(1.0) - np.float32(_alfa_shear(material)))))

    if normalized == "hor":
        suffix = "Hor"
        fracture_name = "SlidingFractureEnergy"
        energy_name = "Gs"
        max_tensile_name = "SlidingMaxTensileRatioHor"
    elif normalized == "vert":
        suffix = "Vert"
        fracture_name = "SlidingFractureEnergyVer"
        # C# out-of-plane vertical sliding deliberately uses Gs, not GsVer.
        energy_name = "Gs" if out_of_plane else "GsVer"
        max_tensile_name = "SlidingMaxTensileRatioVer"
    else:
        suffix = "Dir3"
        fracture_name = "SlidingFractureEnergyDir3"
        energy_name = "GsDir3"
        max_tensile_name = "SlidingMaxTensileRatioVer"

    enabled_name = {
        "hor": "scorrhor",
        "vert": "scorrvert",
        "dir3": "scorrDir3",
    }[normalized]
    sub_law_name = (
        "CriterioSnervamento"
        if out_of_plane
        else f"SlidingYieldingDomain{suffix}"
    )
    return CoulombLaw(
        E=E,
        cohesion=material_float(material, f"CohesionSliding{suffix}"),
        mu=material_float(material, f"FrictionRatioSliding{suffix}"),
        plastic_stiffness_ratio=material_float(
            material, "SlidingPlasticStiffnessRatioVer" if normalized == "vert" else f"SlidingPlasticStiffnessRatio{suffix}"
        ),
        max_tensile_ratio=material_float(material, max_tensile_name, 0.8),
        sub_law=material_enum(
            material, sub_law_name, _SHEAR_DOMAINS, "Linear"
        ),
        hysteretic_type="Initial",
        fracture_energy=material_bool(material, fracture_name, False),
        G=material_float(material, energy_name),
        # Native sliding constructors receive IsDuctility=True.
        ductility=1.0e20,
        is_ductility_fixed=False,
        check_contact_area=material_bool(material, "CheckContactArea", False),
        is_elastic=not material_bool(material, enabled_name, False),
    )


__all__ = [
    "CoulombLaw",
    "HystereticLaw",
    "diagonal_flex_law",
    "flex_law",
    "material_bool",
    "material_float",
    "material_enum",
    "shear_law",
    "sliding_law",
    "validate_masonry_material_enums",
]
