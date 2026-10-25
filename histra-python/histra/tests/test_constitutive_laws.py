"""Strict C# parity tests for masonry constitutive-law preprocessing."""

from dataclasses import asdict
import importlib

import numpy as np
import pytest

from histra.model.masonry_material import MasonryMaterial
from histra.preprocessing.constitutive_laws import (
    CoulombLaw,
    HystereticLaw,
    diagonal_flex_law,
    flex_law,
    material_float,
    shear_law,
    sliding_law,
)

prepare_model_module = importlib.import_module("histra.preprocessing.prepare_model")


def _material(**properties: object) -> MasonryMaterial:
    return MasonryMaterial(
        key=73,
        properties={
            name: str(value).lower() if isinstance(value, bool) else str(value)
            for name, value in properties.items()
        },
    )


def test_prepare_model_preserves_private_constitutive_compatibility_exports():
    assert prepare_model_module._CoulombLaw is CoulombLaw
    assert prepare_model_module._HystereticLaw is HystereticLaw
    assert prepare_model_module._flex_law is flex_law
    assert prepare_model_module._diagonal_flex_law is diagonal_flex_law
    assert prepare_model_module._shear_law is shear_law
    assert prepare_model_module._sliding_law is sliding_law


def test_material_numbers_are_rounded_through_csharp_system_single():
    material = _material(value="0.123456789012345")
    assert material_float(material, "value") == float(np.float32(0.123456789012345))


def test_horizontal_and_vertical_flex_laws_map_every_csharp_constructor_field():
    material = _material(
        Ehor=8.0,
        Ever=16.0,
        FtmHor=2.0,
        FtmVer=4.0,
        FmHor=6.0,
        FmVer=12.0,
        DuctTrazRockingHor=3.0,
        DuctTrazRockingVer=5.0,
        DuctComprRockingHor=7.0,
        DuctComprRockingVer=9.0,
        IsDuctTraz=False,
        IsDuctCompr=False,
        BetaUnloadTractionRockingHor=0.125,
        BetaUnloadTractionRockingVer=0.25,
        BetaUnloadCompressionRockingHor=0.375,
        BetaUnloadCompressionRockingVer=0.5,
        RatioEtTraction=0.625,
        RatioEtCompression=0.75,
        Gt=10.0,
        GtVer=20.0,
        Gc=30.0,
        GcVer=40.0,
        TensileCurveType="LinearSoftening",
        TensileCurveTypeVertical="Exponential",
        CompressiveCurveType="LinearHardening",
        CompressiveCurveTypeVertical="Parabolic",
        ConstitutiveLawFlex="ElastoPlasticDuctilityFixed",
    )

    assert asdict(flex_law(material)) == {
        "E": 8.0,
        "fy_t": 2.0,
        "fy_c": 6.0,
        "tensile_curve": "LinearSoftening",
        "compressive_curve": "LinearHardening",
        "ratio_et_t": 0.625,
        "ratio_et_c": 0.75,
        "alfa_r_t": 1.0,
        "alfa_r_c": 1.0,
        "alfa_u_t": 0.125,
        "alfa_u_c": 0.375,
        "G_t": 10.0,
        "G_c": 30.0,
        "eps_u_t": 0.75,
        "eps_u_c": 5.25,
        "law_type": "ElastoPlasticDuctilityFixed",
        "is_elastic": False,
    }
    assert asdict(flex_law(material, vertical=True)) == {
        "E": 16.0,
        "fy_t": 4.0,
        "fy_c": 12.0,
        "tensile_curve": "Exponential",
        "compressive_curve": "Parabolic",
        "ratio_et_t": 0.625,
        "ratio_et_c": 0.75,
        "alfa_r_t": 1.0,
        "alfa_r_c": 1.0,
        "alfa_u_t": 0.25,
        "alfa_u_c": 0.5,
        "G_t": 20.0,
        "G_c": 40.0,
        "eps_u_t": 1.25,
        "eps_u_c": 6.75,
        "law_type": "ElastoPlasticDuctilityFixed",
        "is_elastic": False,
    }


def test_diagonal_uses_actual_masonry_hysteretic_runtime_law():
    material = _material(
        Ehor=8.0,
        Ever=16.0,
        FtmHor=2.0,
        FtmVer=4.0,
        FmHor=6.0,
        FmVer=12.0,
        DuctTrazRockingHor=3.0,
        DuctTrazRockingVer=5.0,
        DuctComprRockingHor=7.0,
        DuctComprRockingVer=9.0,
        IsDuctTraz=False,
        IsDuctCompr=False,
        ConstitutiveLawFlex="ElastoPlasticDuctilityFixed",
    )
    diagonal = diagonal_flex_law(material)
    c = np.sqrt(2.0) / 2.0
    w = c * c

    assert diagonal.E == 12.000000000000004
    assert diagonal.eps_u_t == 0.75 * c * c + 1.25 * c * c
    assert diagonal.eps_u_c == 6.75 * c * c + 5.25 * c * c


@pytest.mark.parametrize(
    ("alpha", "expected"),
    [
        (0.0, float(np.float32(1.0e-5))),
        (0.5, 0.5),
        (1.0, float(np.float32(0.99999))),
    ],
)
def test_shear_modulus_uses_csharp_alfa_shear_clamp(alpha, expected):
    law = shear_law(_material(Gd=8.0, AlfaShearUser=alpha))
    assert law.E == float(np.float32(np.float32(8.0) / np.float32(expected)))


def test_shear_law_maps_every_csharp_coulomb_constructor_field():
    law = shear_law(
        _material(
            Gd=8.0,
            AlfaShearUser=0.5,
            fvk0d=2.0,
            FrictionRatioShear=0.25,
            ShearPlasticStiffnessRatio=0.125,
            ShearMaxTensileRatio=0.75,
            ShearReloadStiffnessRatio=0.625,
            ShearPlasticStiffnessRatio2=-0.5,
            ShearPlasticStrain=3.0,
            CriterioSnervamento="Cacovic",
            UnloadShear="Takeda",
            ConstitutiveLawMasonryShear="ElastoPlasticFractureEnergyFixed",
            FractureEnergyShear=4.0,
            DuctilityShear=5.0,
            CheckContactArea=True,
            Bcacovic=6.0,
        )
    )

    assert asdict(law) == {
        "E": 16.0,
        "cohesion": 2.0,
        "mu": 0.25,
        "plastic_stiffness_ratio": 0.125,
        "max_tensile_ratio": 0.75,
        "reload_stiffness_ratio": 0.625,
        "plastic_stiffness_ratio2": -0.5,
        "plastic_strain": 3.0,
        "sub_law": "Cacovic",
        "hysteretic_type": "Takeda",
        "fracture_energy": True,
        "G": 4.0,
        "ductility": 5.0,
        "is_ductility_fixed": True,
        "check_contact_area": True,
        "bcacovic": 6.0,
        "is_elastic": False,
    }


@pytest.mark.parametrize(
    ("law_type", "ductility", "fixed"),
    [
        ("Elastic", 1.0e20, False),
        ("ElastoPlastic", 1.0e20, False),
        ("ElastoPlasticDuctilityFixed", 0.125, True),
        ("ElastoPlasticFractureEnergyFixed", 0.125, True),
    ],
)
def test_shear_ductility_matches_csharp_constructor_inversion(
    law_type, ductility, fixed
):
    law = shear_law(
        _material(
            Gd=8.0,
            AlfaShearUser=0.5,
            ConstitutiveLawMasonryShear=law_type,
            DuctilityShear=0.125,
        )
    )
    assert law.ductility == ductility
    assert law.is_ductility_fixed is fixed


def test_out_of_plane_vertical_sliding_uses_csharp_domain_and_energy_fields():
    material = _material(
        Gd=8.0,
        AlfaShearUser=0.5,
        scorrvert=True,
        CohesionSlidingVert=2.0,
        FrictionRatioSlidingVert=0.25,
        SlidingPlasticStiffnessRatioVer=0.125,
        SlidingMaxTensileRatioVer=0.75,
        SlidingYieldingDomainVert="Coulomb",
        CriterioSnervamento="Cacovic",
        SlidingFractureEnergyVer=True,
        Gs=11.0,
        GsVer=22.0,
    )

    in_plane = sliding_law(material, out_of_plane=False, direction="vert")
    out_of_plane = sliding_law(material, out_of_plane=True, direction="vert")

    assert in_plane.E == 32.0
    assert in_plane.sub_law == "Coulomb"
    assert in_plane.G == 22.0
    assert out_of_plane.E == 8.0
    assert out_of_plane.sub_law == "Cacovic"
    assert out_of_plane.G == 11.0
    assert out_of_plane.fracture_energy is True


@pytest.mark.parametrize(
    ("out_of_plane", "direction", "expected_E", "expected_domain", "expected_G"),
    [
        (False, "hor", 32.0, "Coulomb", 10.0),
        (False, "vert", 32.0, "Cacovic", 20.0),
        (False, "dir3", 8.0, "Linear", 30.0),
        (True, "hor", 8.0, "Cacovic", 10.0),
        (True, "vert", 8.0, "Cacovic", 10.0),
        (True, "dir3", 8.0, "Cacovic", 30.0),
    ],
)
def test_all_six_csharp_sliding_slots_select_exact_directional_fields(
    out_of_plane, direction, expected_E, expected_domain, expected_G
):
    material = _material(
        Gd=8.0,
        AlfaShearUser=0.5,
        scorrhor=True,
        scorrvert=False,
        scorrDir3=True,
        CohesionSlidingHor=1.0,
        CohesionSlidingVert=2.0,
        CohesionSlidingDir3=3.0,
        FrictionRatioSlidingHor=0.125,
        FrictionRatioSlidingVert=0.25,
        FrictionRatioSlidingDir3=0.375,
        SlidingPlasticStiffnessRatioHor=0.5,
        SlidingPlasticStiffnessRatioVer=0.625,
        SlidingPlasticStiffnessRatioDir3=0.75,
        SlidingMaxTensileRatioHor=0.875,
        SlidingMaxTensileRatioVer=0.9375,
        SlidingYieldingDomainHor="Coulomb",
        SlidingYieldingDomainVert="Cacovic",
        SlidingYieldingDomainDir3="Linear",
        CriterioSnervamento="Cacovic",
        Gs=10.0,
        GsVer=20.0,
        GsDir3=30.0,
        CheckContactArea=True,
    )

    law = sliding_law(
        material, out_of_plane=out_of_plane, direction=direction
    )
    index = {"hor": 0, "vert": 1, "dir3": 2}[direction]

    assert law.E == expected_E
    assert law.cohesion == (1.0, 2.0, 3.0)[index]
    assert law.mu == (0.125, 0.25, 0.375)[index]
    assert law.plastic_stiffness_ratio == (0.5, 0.625, 0.75)[index]
    assert law.max_tensile_ratio == (0.875, 0.9375, 0.9375)[index]
    assert law.sub_law == expected_domain
    assert law.G == expected_G
    assert law.check_contact_area is True
    assert law.is_elastic is (direction == "vert")


def test_sliding_rejects_unknown_direction_instead_of_defaulting():
    with pytest.raises(ValueError, match="Unsupported sliding-law direction"):
        sliding_law(_material(), out_of_plane=False, direction="diagonal")


@pytest.mark.parametrize(
    ("property_name", "value"),
    [
        ("TensileCurveType", "FutureTension"),
        ("CompressiveCurveType", "FutureCompression"),
        ("ConstitutiveLawFlex", "FutureFlex"),
        ("CriterioSnervamento", "MohrCoulombMaybe"),
        ("UnloadShear", "FutureUnload"),
    ],
)
def test_unknown_material_enums_fail_instead_of_selecting_another_law(
    property_name, value
):
    material = _material(**{property_name: value})
    call = flex_law if property_name in {
        "TensileCurveType", "CompressiveCurveType", "ConstitutiveLawFlex"
    } else shear_law
    with pytest.raises(ValueError, match="unsupported"):
        call(material)
