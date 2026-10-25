"""Helpers for decoding masonry diagonal-shear constitutive settings.

HiStrA stores most ``MasonryMaterial`` fields as HRX template attributes.  The
compiled Quad runtime needs two values from that attribute set without importing
preprocessing internals:

* the C# constitutive-law enum code; and
* the shear fracture energy, rounded through ``System.Single`` semantics.

Keeping these conversions in a small model helper avoids duplicating slightly
different string/numeric handling in solver backends.
"""
from __future__ import annotations

from enum import Enum
import math
import re
from typing import Any

import numpy as np

# C# ConstitutiveLawMasonryShear enum values used by the solver before the
# Python helper was introduced.  Do not renumber: dense batch arrays persist
# and compare these integer codes.
ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED = 4
ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION = 5

_NO_FRACTURE_ENERGY = 0
_LAW_CODES = {
    "elastic": 0,
    "elastoplastic": 1,
    "elastoplasticductilityfixed": 2,
    "elastoplasticandsoftening": 3,
    "elastoplasticfractureenergyfixed": 4,
    "elastoplasticenergysigmainterpolation": 5,
}
_LAW_PROPERTY = "ConstitutiveLawMasonryShear"
_ENERGY_PROPERTY = "FractureEnergyShear"


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _material_value(material: Any, name: str, default: Any) -> Any:
    """Read a material value from current and legacy representations."""
    if material is None:
        return default

    value_method = getattr(material, "value", None)
    if callable(value_method):
        try:
            return value_method(name, default)
        except (TypeError, ValueError):
            return default

    properties = getattr(material, "properties", None)
    if isinstance(properties, dict):
        if name in properties:
            return properties[name]
        folded_name = name.casefold()
        for key, value in properties.items():
            if str(key).casefold() == folded_name:
                return value

    for attribute_name in (name, _snake_case(name)):
        if hasattr(material, attribute_name):
            return getattr(material, attribute_name)
    return default


def _law_token(value: Any) -> str:
    if isinstance(value, Enum):
        # Enum values in translated code may be either the C# integer or name.
        value = value.value
    return "".join(character for character in str(value).casefold() if character.isalnum())


def masonry_shear_law_code(material: Any) -> int:
    """Return the C# masonry-shear constitutive-law code.

    An absent value uses the C# default (``Elastic``).  An explicitly stored
    unknown value is rejected: silently treating it as elastic could change
    the physical law while still producing plausible results.
    """
    raw = _material_value(material, _LAW_PROPERTY, "")

    if isinstance(raw, Enum):
        raw = raw.value
    if isinstance(raw, (int, float, np.integer, np.floating)) and not isinstance(raw, bool):
        numeric = float(raw)
        if math.isfinite(numeric) and numeric.is_integer():
            code = int(numeric)
            if code in _LAW_CODES.values():
                return code
        raise ValueError(
            f"Unsupported {_LAW_PROPERTY} value {raw!r}; expected a C# enum value 0..5."
        )

    text = str(raw).strip()
    if text:
        try:
            numeric = float(text)
        except ValueError:
            numeric = math.nan
        if math.isfinite(numeric) and numeric.is_integer():
            code = int(numeric)
            if code in _LAW_CODES.values():
                return code
            raise ValueError(
                f"Unsupported {_LAW_PROPERTY} value {raw!r}; expected a C# enum value 0..5."
            )

    token = _law_token(raw)
    if not token:
        return _NO_FRACTURE_ENERGY
    for name, code in _LAW_CODES.items():
        if token.endswith(name):
            return code
    raise ValueError(
        f"Unsupported {_LAW_PROPERTY} value {raw!r}; expected one of "
        f"{sorted(_LAW_CODES)}."
    )


def fracture_energy_shear(material: Any) -> float:
    """Return shear fracture energy with C# ``System.Single`` rounding."""
    raw = _material_value(material, _ENERGY_PROPERTY, 0.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return float(np.float32(value))
