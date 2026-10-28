"""Scalar result-field descriptors shared by the saved-result adapters.

The C# viewer exposes several interface-spring-derived stress and strain maps on
the Quad surface.  The browser receives them as scalar values at the four Quad
corners, with explicit units and availability so unsupported maps stay visible
but disabled instead of being silently mislabeled.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

FIELD_DEFS = {
    "globalStressX": {
        "label": "Global stress σX", "unit": "MPa", "kind": "stress", "order": 10,
    },
    "globalStressY": {
        "label": "Global stress σY", "unit": "MPa", "kind": "stress", "order": 20,
    },
    "globalStressZ": {
        "label": "Global stress σZ", "unit": "MPa", "kind": "stress", "order": 30,
    },
    "globalStressXY": {
        "label": "Global shear τXY", "unit": "MPa", "kind": "stress", "order": 40,
    },
    "globalStressXZ": {
        "label": "Global shear τXZ", "unit": "MPa", "kind": "stress", "order": 50,
    },
    "globalStressYZ": {
        "label": "Global shear τYZ", "unit": "MPa", "kind": "stress", "order": 60,
    },
    "principalTensile": {
        "label": "Principal tensile stress", "unit": "MPa", "kind": "stress", "order": 70,
    },
    "principalCompressive": {
        "label": "Principal compressive stress", "unit": "MPa", "kind": "stress", "order": 80,
    },
    "vonMises": {
        "label": "Von Mises stress", "unit": "MPa", "kind": "stress", "order": 90,
    },
    "localStressNormal": {
        "label": "Local Y-dir stress σn (interface normal)", "unit": "MPa", "kind": "stress", "order": 100,
    },
    "localStressInPlane": {
        "label": "Local X-dir shear τ12 (interface in-plane)", "unit": "MPa", "kind": "stress", "order": 110,
    },
    "localStressOutOfPlane": {
        "label": "Local out-of-plane shear τ23", "unit": "MPa", "kind": "stress", "order": 120,
    },
    "localStrainNormal": {
        "label": "Local Y-dir strain εn (interface normal)", "unit": "–", "kind": "strain", "order": 200,
    },
    "localStrainInPlane": {
        "label": "Local X-dir strain γ12 (interface in-plane)", "unit": "–", "kind": "strain", "order": 210,
    },
    "localStrainOutOfPlane": {
        "label": "Local out-of-plane strain γ23", "unit": "–", "kind": "strain", "order": 220,
    },
    "plasticStrainNormal": {
        "label": "Plastic strain εp (normal, dir1/dir2)", "unit": "–", "kind": "plastic", "order": 300,
    },
    "plasticStrainRatioNormal": {
        "label": "Plastic/ultimate strain ratio", "unit": "–", "kind": "plastic", "order": 310,
    },
    "quadDiagonalSigma": {
        "label": "Quad diagonal sigma", "unit": "MPa", "kind": "stress", "order": 400,
    },
    "quadDiagonalPhase": {
        "label": "Quad diagonal phase", "unit": "–", "kind": "phase", "order": 410,
    },
}


def _field(field_id: str, step: int, source: str, *, available: bool,
           values=None, reason: str | None = None, partial: bool = False):
    definition = FIELD_DEFS[field_id]
    record = {
        "id": field_id,
        **definition,
        "step": int(step),
        "source": source,
        "available": bool(available),
        "partial": bool(partial),
    }
    if reason:
        record["reason"] = reason
    if not available or values is None:
        return record
    corners = np.asarray(values, dtype=np.float64)
    if corners.ndim != 2 or corners.shape[1] != 4:
        raise ValueError(f"Field {field_id} requires four corner values per Quad.")
    if not np.isfinite(corners).all():
        raise ValueError(f"Field {field_id} contains nonfinite values.")
    record["quadCornerValues"] = np.round(corners, 6).tolist()
    record["min"] = float(np.min(corners))
    record["max"] = float(np.max(corners))
    return record


def available_field(field_id: str, values, step: int, source: str, *, partial: bool = False):
    field = _field(field_id, step, source, available=True, values=values, partial=partial)
    return field


def unavailable_field(field_id: str, step: int, source: str, reason: str):
    return _field(field_id, step, source, available=False, reason=reason)


def sorted_definitions(field_ids: Iterable[str] | None = None):
    if field_ids is None:
        field_ids = FIELD_DEFS
    return sorted(FIELD_DEFS.keys() if field_ids is None else field_ids,
                  key=lambda key: FIELD_DEFS[key]["order"])


def complete_field_set(values: dict[str, object], step: int, source: str,
                       unavailable_reason: str, *, partial_fields: Iterable[str] = ()):
    """Build the C# menu order and retain unsupported maps as disabled entries."""
    partial_fields = set(partial_fields)
    output = []
    for field_id in sorted_definitions():
        if field_id in values:
            output.append(available_field(field_id, values[field_id], step, source,
                                          partial=field_id in partial_fields))
        else:
            output.append(unavailable_field(field_id, step, source, unavailable_reason))
    return output
