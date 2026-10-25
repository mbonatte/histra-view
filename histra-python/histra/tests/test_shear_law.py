from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pytest

from histra.model.shear_law import (
    ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION,
    ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED,
    fracture_energy_shear,
    masonry_shear_law_code,
)
from histra.model.masonry_material import MasonryMaterial


@dataclass
class _Material:
    properties: dict[str, str] = field(default_factory=dict)

    def value(self, name: str, default):
        raw = self.properties.get(name)
        if raw is None:
            return default
        if isinstance(default, float):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return default
        return raw


class _Law(Enum):
    FIXED = ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED
    INTERPOLATED = ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION


_LAW_NAME = "ConstitutiveLawMasonryShear"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("ElastoPlasticFractureEnergyFixed", ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED),
        ("ElastoPlasticEnergySigmaInterpolation", ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION),
        ("Namespace.ElastoPlasticFractureEnergyFixed", ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED),
        ("4", ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED),
        (5, ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION),
        (_Law.FIXED, ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED),
        ("Elastic", 0),
        ("ElastoPlastic", 1),
        ("ElastoPlasticDuctilityFixed", 2),
        ("ElastoPlasticAndSoftening", 3),
        ("", 0),
        (None, 0),
    ],
)
def test_masonry_shear_law_code(stored, expected) -> None:
    material = _Material({_LAW_NAME: stored}) if stored is not None else None
    assert masonry_shear_law_code(material) == expected


@pytest.mark.parametrize("stored", ["Hysteretic", "6", -1, float("nan")])
def test_unknown_masonry_shear_law_is_rejected(stored) -> None:
    with pytest.raises(ValueError, match="Unsupported ConstitutiveLawMasonryShear"):
        masonry_shear_law_code(_Material({_LAW_NAME: stored}))


def test_fracture_energy_uses_system_single_rounding() -> None:
    source = "0.001238512345"
    material = _Material({"FractureEnergyShear": source})
    assert fracture_energy_shear(material) == float(np.float32(float(source)))


@pytest.mark.parametrize("stored", [None, "", "invalid", "nan", "inf"])
def test_invalid_fracture_energy_is_zero(stored) -> None:
    material = None if stored is None else _Material({"FractureEnergyShear": stored})
    assert fracture_energy_shear(material) == 0.0


def test_legacy_snake_case_attributes_are_supported() -> None:
    material = type(
        "LegacyMaterial",
        (),
        {
            "constitutive_law_masonry_shear": _Law.INTERPOLATED,
            "fracture_energy_shear": 0.25,
        },
    )()
    assert masonry_shear_law_code(material) == ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION
    assert fracture_energy_shear(material) == 0.25


@pytest.mark.parametrize(
    ("sigma", "expected_energy"),
    [
        (-0.04, 0.0012385),
        (-0.05, 0.0012385),
        (-0.0575, (0.0007775 + 0.0004402) / 2.0),
        (-0.07, 0.0001699),
        (-0.09, 0.0001699),
    ],
)
def test_masonry_material_interpolates_csharp_shear_energy(
    sigma: float, expected_energy: float
) -> None:
    material = MasonryMaterial(
        properties={
            "ConstitutiveLawMasonryShear": "ElastoPlasticEnergySigmaInterpolation"
        }
    )

    assert material.constitutive_law_masonry_shear == 5
    assert material.get_shear_ultimate_strain(2.0, 0.1, 4.0, sigma) == pytest.approx(
        expected_energy * 2.0 + 0.05
    )


def test_masonry_material_uses_csharp_fixed_fracture_energy() -> None:
    material = MasonryMaterial(
        properties={
            "ConstitutiveLawMasonryShear": "ElastoPlasticFractureEnergyFixed",
            "FractureEnergyShear": "0.125",
        }
    )

    assert material.constitutive_law_masonry_shear == 4
    assert material.get_shear_ultimate_strain(2.0, 0.1, 4.0, 0.0) == pytest.approx(
        0.3
    )
