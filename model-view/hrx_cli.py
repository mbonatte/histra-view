#!/usr/bin/env python3
"""Agent-friendly CLI and library for creating, inspecting, and editing HiStrA .hrx files.

Run:
  .venv/bin/python hrx_cli.py catalog
  .venv/bin/python hrx_cli.py init-spec -o bridge.json
  .venv/bin/python hrx_cli.py create --spec bridge.json --set nl=200 -o bridge.hrx
  .venv/bin/python hrx_cli.py inspect bridge.hrx --section materials
  .venv/bin/python hrx_cli.py edit-material bridge.hrx --key 18 --set Ehor=1800 --set FmHor=3.2 -o bridge.hrx
  .venv/bin/python hrx_cli.py edit-analysis bridge.hrx --add-template "LiveLoad_1" --set MaxIterations=50 -o bridge.hrx
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import sys
from pathlib import Path
from typing import Any

import builder_api
from hrx_model import parse_hrx


MASONRY_ADVANCED_SCHEMA = {
    "units_note": "HRX native base units are kN and cm (stiffness/strength in kN/cm² = 10 MPa, specific weight w in kN/cm³, fracture energy in kN/cm).",
    "general": {
        "Name": "Material name",
        "Description": "Material description",
        "w": "Specific weight W [kN/cm³]",
        "Ehor": "Young's modulus E (local directions 1 & 3) [kN/cm²]",
        "Gd": "Shear modulus G [kN/cm²]",
        "FmHor": "Compressive strength fm (local directions 1 & 3) [kN/cm²]",
        "FtmHor": "Tensile strength ft (local directions 1 & 3) [kN/cm²]",
        "fvk0d": "Shear strength τ₀ [kN/cm²]",
        "CohesionSlidingHor": "Sliding cohesion c (direction 1) [kN/cm²]",
        "FrictionRatioSlidingHor": "Sliding friction coefficient μ (direction 1) [-]",
        "FrictionRatioShear": "Diagonal shear friction coefficient μ [-]",
    },
    "rocking": {
        "ortpf": {
            "description": "Rocking behavior: 'false' = Isotropic (uses Hor keys), 'true' = Orthotropic (uses Hor for Dir 1&3 and Ver/Vertical for Dir 2)",
            "values": ["false", "true"],
        },
        "elastic": ["Ehor", "Ever"],
        "tensile_laws": {
            "attribute": "TensileCurveType (and TensileCurveTypeVertical when ortpf='true')",
            "values": ["Elastic", "LinearHardening", "LinearSoftening", "Exponential"],
            "fields_by_law": {
                "Elastic": [],
                "LinearHardening": [
                    "FtmHor",
                    "RatioEtTraction",
                    "IsDuctTraz",
                    "DuctTrazRockingHor (active when IsDuctTraz='true')",
                    "UnloadTractionRockingHor",
                    "BetaUnloadTractionRockingHor (active when UnloadTractionRockingHor='Nothing')",
                ],
                "LinearSoftening": [
                    "FtmHor",
                    "Gt",
                    "UnloadTractionRockingHor",
                    "BetaUnloadTractionRockingHor (active when UnloadTractionRockingHor='Nothing')",
                ],
                "Exponential": [
                    "FtmHor",
                    "Gt",
                    "UnloadTractionRockingHor",
                    "BetaUnloadTractionRockingHor (active when UnloadTractionRockingHor='Nothing')",
                ],
            },
        },
        "compressive_laws": {
            "attribute": "CompressiveCurveType (and CompressiveCurveTypeVertical when ortpf='true')",
            "values": ["Elastic", "LinearHardening", "LinearSoftening", "Parabolic"],
            "fields_by_law": {
                "Elastic": [],
                "LinearHardening": [
                    "FmHor",
                    "RatioEtCompression",
                    "IsDuctCompr",
                    "DuctComprRockingHor (active when IsDuctCompr='true')",
                    "UnloadCompressionRockingHor",
                    "BetaUnloadCompressionRockingHor (active when UnloadCompressionRockingHor='Nothing')",
                    "RotationLimitRockingHor",
                ],
                "LinearSoftening": [
                    "FmHor",
                    "Gc",
                    "UnloadCompressionRockingHor",
                    "BetaUnloadCompressionRockingHor (active when UnloadCompressionRockingHor='Nothing')",
                    "RotationLimitRockingHor",
                ],
                "Parabolic": [
                    "FmHor",
                    "Gc",
                    "UnloadCompressionRockingHor",
                    "BetaUnloadCompressionRockingHor (active when UnloadCompressionRockingHor='Nothing')",
                    "RotationLimitRockingHor",
                ],
            },
        },
        "unload_values": {
            "Initial": "Initial stiffness unloading (β = 0)",
            "Origin": "Origin-oriented unloading (β = 1)",
            "Nothing": "Mixed unloading (0 < β < 1, uses BetaUnload* parameter)",
        },
    },
    "shear": {
        "attribute": "ConstitutiveLawMasonryShear",
        "values": [
            "Elastic",
            "ElastoPlastic",
            "ElastoPlasticDuctilityFixed",
            "ElastoPlasticAndSoftening",
            "ElastoPlasticFractureEnergyFixed",
            "ElastoPlasticEnergySigmaInterpolation",
        ],
        "yielding_domain": {
            "attribute": "CriterioSnervamento",
            "values": ["Coulomb", "Cacovic", "Linear"],
            "fields_by_domain": {
                "Coulomb": ["fvk0d", "FrictionRatioShear", "ShearReloadStiffnessRatio", "ShearMaxTensileRatio"],
                "Cacovic": ["fvk0d", "Bcacovic"],
                "Linear": ["fvk0d"],
            },
        },
        "fields_by_law": {
            "Elastic": ["Gd", "AlfaShearUser"],
            "ElastoPlastic": ["Gd", "AlfaShearUser", "fvk0d", "ShearPlasticStiffnessRatio"],
            "ElastoPlasticDuctilityFixed": ["Gd", "AlfaShearUser", "fvk0d", "ShearPlasticStiffnessRatio", "DuctilityShear", "ShearUltimateStrain"],
            "ElastoPlasticAndSoftening": [
                "Gd",
                "AlfaShearUser",
                "fvk0d",
                "ShearPlasticStiffnessRatio",
                "ShearPlasticStiffnessRatio2",
                "ShearPlasticStrain",
                "DuctilityShear",
                "ShearUltimateStrain",
            ],
            "ElastoPlasticFractureEnergyFixed": ["Gd", "AlfaShearUser", "fvk0d", "ShearPlasticStiffnessRatio", "FractureEnergyShear", "DuctilityShear"],
            "ElastoPlasticEnergySigmaInterpolation": ["Gd", "AlfaShearUser", "fvk0d", "ShearPlasticStiffnessRatio", "FractureEnergyShear", "DuctilityShear"],
        },
        "cyclic": [
            "HasKinCiclShear",
            "AkinCiclShear (when HasKinCiclShear='true')",
            "CiclShear",
            "AlfaCiclShear (when CiclShear='true')",
            "GammaCiclShear (when CiclShear='true')",
            "UnloadShear",
            "BetaUnloadShear (when UnloadShear='Nothing')",
        ],
    },
    "sliding": {
        "ortsc": {
            "description": "Sliding behavior: 'false' = Isotropic (Dir 1), 'true' = Orthotropic (Dir 1 = Hor, Dir 2 = Ver/Vert, Dir 3 = Dir3)",
            "values": ["false", "true"],
        },
        "CheckContactArea": "Update cohesive contact area during analysis ('true' or 'false')",
        "laws": {
            "Elastic": {"scorrhor": "false", "SlidingFractureEnergy": "false", "fields": []},
            "ElastoPlastic": {
                "scorrhor": "true",
                "SlidingFractureEnergy": "false",
                "fields": [
                    "SlidingYieldingDomainHor",
                    "CohesionSlidingHor",
                    "FrictionRatioSlidingHor (when Coulomb)",
                    "SlidingMaxTensileRatioHor (when Coulomb)",
                    "SlidingPlasticStiffnessRatioHor",
                ],
            },
            "LinearSoftening": {
                "scorrhor": "true",
                "SlidingFractureEnergy": "true",
                "fields": [
                    "SlidingYieldingDomainHor",
                    "CohesionSlidingHor",
                    "FrictionRatioSlidingHor (when Coulomb)",
                    "SlidingMaxTensileRatioHor (when Coulomb)",
                    "SlidingPlasticStiffnessRatioHor",
                    "Gs",
                ],
            },
        },
    },
}

ANALYSIS_ENUMS = {
    "AnalysisType": {
        "1": "Static linear",
        "2": "Static nonlinear",
        "3": "Dynamic linear",
        "4": "Dynamic nonlinear",
        "5": "Modal",
    },
    "Method": [
        "LinearStep",
        "DisplacementImposed",
        "IndirectDisplacementControl",
        "StandardNewtonRaphson",
        "ModifiedNewtonRaphson",
        "ArcLength",
        "ArcLengthModified",
        "StandardSecantLineSearch",
        "StandardRegulaFalsiLineSearch",
        "StandardBisectionLineSearch",
        "StandardInitialInterpolatedLineSearch",
        "ModifiedSecantLineSearch",
        "ModifiedRegulaFalsiLineSearch",
        "ModifiedBisectionLineSearch",
        "ModifiedInitialInterpolatedLineSearch",
        "KrylovNewton",
        "Broyden",
        "BFGS",
        "AcceleratedNewton",
        "PeriodicNewton",
    ],
    "IntegrationMethod": ["LoadControl", "ArcLength", "ArcLengthLinear", "NewmarkMethod", "HHTmethod", "WilsonMethod"],
    "ArcLengthProcedure": ["OnlyControlPoint", "OnlyModelPointsSelected", "AllDegreesOfFreedom"],
    "AdapticConvergenceCriteria": ["ForceMoment", "DispRotation", "Work"],
    "TypeLoadDistribution": ["Force", "Modal", "Triangular", "Adaptive", "ShearFloor", "LoadCombination"],
    "ModalProcedure": ["SubspaceIterations", "InverseIterations", "SparseBlockInverseSubspace"],
    "DampingCriterion": ["Rayleigh", "Stiffness", "Caughey"],
    "Typedirection": ["Simple", "Cartesian", "Polar"],
    "Direction": ["X", "Y", "Z", "Custom", "Total", "Analysis"],
    "PdeltaEffect": ["None", "EachStep", "EachIteration"],
    "PushModal_Type": ["Mass", "Single", "Custom"],
}


def is_masonry_record(item: dict[str, Any]) -> bool:
    attrs = item.get("attributes") or (item.get("nodes")[0]["attributes"] if item.get("nodes") else {})
    return attrs.get("PurposeType") == "MasonryMaterial" or "Ehor" in attrs


def get_catalog() -> dict[str, Any]:
    """Return full schema, starter bridge geometry, and masonry/analysis templates."""
    defaults = builder_api.defaults()
    geometry = {k: v for k, v in defaults.items() if k != "inspection"}
    cat = builder_api.catalog()
    masonry_templates = [
        m for m in cat["materials"]
        if not m.get("type") or m["type"].endswith(".MasonryMaterial")
    ]
    return {
        "geometry_defaults": geometry,
        "geometry_fields": {
            "name": "Model name",
            "nl": "Target finite element mesh size [cm] (>= 5)",
            "strips": "List of deck strips: {width, height, material_key}",
            "spans": "List of arch spans (1..12): {L, f, Tb, Tt, Asx, Adx, S1, S2, Dz, circolare, material_key, material_pulvino_key}. Set circolare=true for a true circular arch (Asx/Adx are then derived from L, S1, S2 and f).",
            "piers": "List of intermediate piers (len = len(spans)-1): {H, Hf, b2, B1f, B3f, W1f, W3f, material_key, material_foundation_key, Kz}",
            "left_abutment": "Left abutment: {H, Hf, b2, B1f, B3f, W1f, W3f, material_key, material_foundation_key, Kz}",
            "right_abutment": "Right abutment: {H, Hf, b2, B1f, B3f, W1f, W3f, material_key, material_foundation_key, Kz}",
            "elevation": "Backfill layers: {H1, H2, H3, layer1_material_key, layer2_material_key, layer3_material_key}",
        },
        "masonry_material_templates": masonry_templates,
        "analysis_templates": cat["analyses"],
        "masonry_advanced_schema": MASONRY_ADVANCED_SCHEMA,
        "analysis_enums": ANALYSIS_ENUMS,
    }


def _parse_scalar(val: str) -> Any:
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        if "." in val or "e" in low:
            return float(val)
        return int(val)
    except ValueError:
        return val


_MIRROR_PAIRS = [
    ("b1", "b3"), ("w1", "w3"), ("B1f", "B3f"), ("W1f", "W3f"),
    ("Hsp1", "Hsp2"), ("beta1", "beta2"),
    ("spinta_passiva_sx", "spinta_passiva_dx"),
    ("material_geo1_key", "material_geo2_key"),
    ("is_reinf_left", "is_reinf_right"),
    ("TreinfTopLeft", "TreinfTopRight"), ("TreinfBotLeft", "TreinfBotRight"),
    ("material_reinforcement_left_key", "material_reinforcement_right_key"),
]
_MIRROR = {key: value for a, b in _MIRROR_PAIRS for key, value in ((a, b), (b, a))}


def apply_dotted_overrides(payload: dict[str, Any], pairs: list[str], linked_groups: list[str] | None = None) -> dict[str, Any]:
    """Apply dotted key=value overrides (e.g. 'spans.0.L=800', 'nl=150') to a bridge payload."""
    result = copy.deepcopy(payload)
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Expected KEY=VALUE, got {pair!r}")
        path_str, raw_val = pair.split("=", 1)
        parts = path_str.strip().split(".")
        target: Any = result
        for part in parts[:-1]:
            if isinstance(target, list):
                idx = int(part)
                while len(target) <= idx:
                    target.append(copy.deepcopy(target[-1]) if target else {})
                target = target[idx]
            else:
                if part not in target or not isinstance(target[part], (dict, list)):
                    target[part] = {}
                target = target[part]
        last = parts[-1]
        val = _parse_scalar(raw_val)
        if isinstance(target, list):
            target[int(last)] = val
        else:
            target[last] = val
    if "spans" in result and "piers" in result and isinstance(result["spans"], list) and isinstance(result["piers"], list):
        needed_piers = max(0, len(result["spans"]) - 1)
        while len(result["piers"]) < needed_piers:
            template_pier = result["piers"][-1] if result["piers"] else {
                "H": 150, "Hf": 60, "b2": 70, "B1f": 30, "B3f": 30,
                "W1f": 20, "W3f": 20, "material_key": 18, "material_foundation_key": 141, "Kz": 0.1,
            }
            result["piers"].append(copy.deepcopy(template_pier))
        if len(result["piers"]) > needed_piers:
            result["piers"] = result["piers"][:needed_piers]
    links = set(linked_groups or [])
    if "all" in links:
        links.update(("abutments", "piers", "spans"))
    for pair in pairs:
        path, raw_value = pair.split("=", 1)
        parts = path.strip().split(".")
        value = _parse_scalar(raw_value)
        if len(parts) == 3 and parts[0] in ("spans", "piers") and parts[0] in links and parts[1].isdigit():
            for item in result[parts[0]]:
                item[parts[2]] = value
        elif len(parts) == 2 and parts[0] in ("left_abutment", "right_abutment") and "abutments" in links:
            source = parts[0]
            other = "right_abutment" if source == "left_abutment" else "left_abutment"
            result[source][parts[1]] = value
            result[other][_MIRROR.get(parts[1], parts[1])] = value
    return result


def create_bridge_hrx(
    spec: dict[str, Any] | None = None,
    overrides: list[str] | None = None,
    steps: list[dict[str, Any]] | None = None,
    linked_groups: list[str] | None = None,
) -> bytes:
    """Create a parametric bridge .hrx from a spec dictionary and optional overrides/steps."""
    defaults = builder_api.defaults()
    base_payload = {k: v for k, v in defaults.items() if k != "inspection"}
    if spec:
        for k, v in spec.items():
            if k not in ("inspection", "steps", "changes", "operations"):
                base_payload[k] = v
    if overrides:
        base_payload = apply_dotted_overrides(base_payload, overrides, linked_groups)
    req: dict[str, Any] = {
        "mode": "create",
        "payload": base_payload,
        "steps": steps or (spec.get("steps", []) if isinstance(spec, dict) else []),
        "changes": spec.get("changes", []) if isinstance(spec, dict) else [],
        "operations": spec.get("operations", []) if isinstance(spec, dict) else [],
    }
    return builder_api.build(req)


def _summarize_masonry_advanced(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes") or (item.get("nodes")[0]["attributes"] if item.get("nodes") else {})
    ort_rocking = attrs.get("ortpf") == "true"
    ort_sliding = attrs.get("ortsc") == "true"
    is_nl_sliding = attrs.get("scorrhor") == "true"
    is_soft_sliding = is_nl_sliding and attrs.get("SlidingFractureEnergy") == "true"
    sliding_law = "Elastic" if not is_nl_sliding else ("LinearSoftening" if is_soft_sliding else "ElastoPlastic")
    return {
        "key": item.get("key"),
        "name": item.get("name"),
        "general": {
            "Name": attrs.get("Name"),
            "Description": attrs.get("Description"),
            "w": attrs.get("w", attrs.get("Gamma")),
            "Ehor": attrs.get("Ehor"),
            "Gd": attrs.get("Gd"),
            "FmHor": attrs.get("FmHor"),
            "FtmHor": attrs.get("FtmHor"),
            "fvk0d": attrs.get("fvk0d"),
            "CohesionSlidingHor": attrs.get("CohesionSlidingHor"),
            "FrictionRatioSlidingHor": attrs.get("FrictionRatioSlidingHor"),
            "FrictionRatioShear": attrs.get("FrictionRatioShear"),
        },
        "rocking": {
            "ortpf": attrs.get("ortpf"),
            "behavior": "Orthotropic" if ort_rocking else "Isotropic",
            "Ehor": attrs.get("Ehor"),
            **({"Ever": attrs.get("Ever")} if ort_rocking else {}),
            "TensileCurveType": attrs.get("TensileCurveType"),
            "FtmHor": attrs.get("FtmHor"),
            "Gt": attrs.get("Gt"),
            "RatioEtTraction": attrs.get("RatioEtTraction"),
            "IsDuctTraz": attrs.get("IsDuctTraz"),
            "DuctTrazRockingHor": attrs.get("DuctTrazRockingHor"),
            "UnloadTractionRockingHor": attrs.get("UnloadTractionRockingHor"),
            "BetaUnloadTractionRockingHor": attrs.get("BetaUnloadTractionRockingHor"),
            "CompressiveCurveType": attrs.get("CompressiveCurveType"),
            "FmHor": attrs.get("FmHor"),
            "Gc": attrs.get("Gc"),
            "RatioEtCompression": attrs.get("RatioEtCompression"),
            "IsDuctCompr": attrs.get("IsDuctCompr"),
            "DuctComprRockingHor": attrs.get("DuctComprRockingHor"),
            "UnloadCompressionRockingHor": attrs.get("UnloadCompressionRockingHor"),
            "BetaUnloadCompressionRockingHor": attrs.get("BetaUnloadCompressionRockingHor"),
            "RotationLimitRockingHor": attrs.get("RotationLimitRockingHor"),
        },
        "shear": {
            "ConstitutiveLawMasonryShear": attrs.get("ConstitutiveLawMasonryShear"),
            "CriterioSnervamento": attrs.get("CriterioSnervamento"),
            "Gd": attrs.get("Gd"),
            "AlfaShearUser": attrs.get("AlfaShearUser"),
            "fvk0d": attrs.get("fvk0d"),
            "FrictionRatioShear": attrs.get("FrictionRatioShear"),
            "Bcacovic": attrs.get("Bcacovic"),
            "ShearPlasticStiffnessRatio": attrs.get("ShearPlasticStiffnessRatio"),
            "ShearPlasticStiffnessRatio2": attrs.get("ShearPlasticStiffnessRatio2"),
            "ShearReloadStiffnessRatio": attrs.get("ShearReloadStiffnessRatio"),
            "ShearMaxTensileRatio": attrs.get("ShearMaxTensileRatio"),
            "DuctilityShear": attrs.get("DuctilityShear"),
            "FractureEnergyShear": attrs.get("FractureEnergyShear"),
            "ShearPlasticStrain": attrs.get("ShearPlasticStrain"),
            "ShearUltimateStrain": attrs.get("ShearUltimateStrain"),
            "HasKinCiclShear": attrs.get("HasKinCiclShear"),
            "AkinCiclShear": attrs.get("AkinCiclShear"),
            "CiclShear": attrs.get("CiclShear"),
            "AlfaCiclShear": attrs.get("AlfaCiclShear"),
            "GammaCiclShear": attrs.get("GammaCiclShear"),
            "UnloadShear": attrs.get("UnloadShear"),
            "BetaUnloadShear": attrs.get("BetaUnloadShear"),
        },
        "sliding": {
            "ortsc": attrs.get("ortsc"),
            "behavior": "Orthotropic" if ort_sliding else "Isotropic",
            "CheckContactArea": attrs.get("CheckContactArea"),
            "constitutiveLawDir1": sliding_law,
            "scorrhor": attrs.get("scorrhor"),
            "SlidingFractureEnergy": attrs.get("SlidingFractureEnergy"),
            "SlidingYieldingDomainHor": attrs.get("SlidingYieldingDomainHor"),
            "CohesionSlidingHor": attrs.get("CohesionSlidingHor"),
            "FrictionRatioSlidingHor": attrs.get("FrictionRatioSlidingHor"),
            "SlidingPlasticStiffnessRatioHor": attrs.get("SlidingPlasticStiffnessRatioHor"),
            "SlidingMaxTensileRatioHor": attrs.get("SlidingMaxTensileRatioHor"),
            "Gs": attrs.get("Gs"),
        },
    }


def inspect_hrx_bytes(data: bytes, name: str = "model.hrx", section: str = "all") -> dict[str, Any]:
    """Inspect an HRX model and return structured JSON for agents."""
    encoded = base64.b64encode(data).decode("ascii")
    inspected = builder_api.inspect_source(encoded)
    parsed = parse_hrx(data, name)
    masonry_materials = [
        _summarize_masonry_advanced(item)
        for item in inspected["materials"]
        if is_masonry_record(item)
    ]
    summary = {
        "name": parsed["name"],
        "units": parsed["units"],
        "nodeCount": len(parsed["nodes"]),
        "quadCount": len(parsed["quads"]),
        "masonryMaterialCount": len(masonry_materials),
        "analysisCount": len(parsed.get("analyses", [])),
        "restraintCount": len(parsed.get("restraints", [])),
        "loadCount": len(parsed.get("loads", [])),
        "warnings": parsed.get("warnings", []),
    }
    if section == "summary":
        return {"summary": summary}
    if section == "materials":
        return {"summary": summary, "materials": masonry_materials}
    if section == "analyses":
        return {"summary": summary, "analyses": parsed.get("analyses", [])}
    if section == "loads":
        return {
            "summary": summary,
            "loadConditions": parsed.get("loadConditions", []),
            "loadCombinations": parsed.get("loadCombinations", []),
            "loadFunctions": parsed.get("loadFunctions", []),
        }
    return {
        "summary": summary,
        "materials": masonry_materials,
        "analyses": parsed.get("analyses", []),
        "loadConditions": parsed.get("loadConditions", []),
        "loadCombinations": parsed.get("loadCombinations", []),
        "loadFunctions": parsed.get("loadFunctions", []),
    }


def _resolve_collection_index(
    items: list[dict[str, Any]],
    *,
    key: str | None = None,
    name: str | None = None,
    index: int | None = None,
) -> int:
    if index is not None:
        if 0 <= index < len(items):
            return index
        raise ValueError(f"Index {index} out of range (0..{len(items) - 1}).")
    if key is not None:
        for idx, item in enumerate(items):
            if str(item.get("key")) == str(key):
                return idx
        raise ValueError(f"No entry found with key={key!r}. Available keys: {[i.get('key') for i in items]}")
    if name is not None:
        for idx, item in enumerate(items):
            if str(item.get("name", "")).lower() == str(name).lower():
                return idx
        raise ValueError(f"No entry found with name={name!r}. Available names: {[i.get('name') for i in items]}")
    raise ValueError("Specify one of key, name, or index.")


def edit_material_hrx(
    data: bytes,
    *,
    add_template: str | None = None,
    duplicate_key: str | None = None,
    delete_key: str | None = None,
    key: str | None = None,
    name: str | None = None,
    index: int | None = None,
    attributes: dict[str, str] | None = None,
    sliding_law: str | None = None,
    orthotropic_rocking: bool | None = None,
    orthotropic_sliding: bool | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Add, duplicate, delete, or edit a masonry material in Advanced mode."""
    encoded = base64.b64encode(data).decode("ascii")
    inspected = builder_api.inspect_source(encoded)
    materials = inspected["collections"]["material"]

    target_idx: int | None = None
    if add_template is not None:
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": [],
            "operations": [{"op": "add_material", "template": str(add_template)}],
        })
        encoded = res["source"]
        inspected = res["inspection"]
        materials = inspected["collections"]["material"]
        target_idx = len(materials) - 1
    elif duplicate_key is not None:
        dup_idx = _resolve_collection_index(materials, key=duplicate_key)
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": [],
            "operations": [{"op": "duplicate_material", "duplicate": dup_idx}],
        })
        encoded = res["source"]
        inspected = res["inspection"]
        materials = inspected["collections"]["material"]
        target_idx = len(materials) - 1
    elif delete_key is not None:
        del_idx = _resolve_collection_index(materials, key=delete_key)
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": [],
            "operations": [{"op": "delete_material", "index": del_idx}],
        })
        out_bytes = base64.b64decode(res["source"])
        return out_bytes, {"deleted_key": delete_key, "remaining_materials": len(res["inspection"]["materials"])}

    updates: dict[str, str] = {}
    if attributes:
        for k, v in attributes.items():
            updates[str(k)] = str(v)
    if orthotropic_rocking is not None:
        updates["ortpf"] = "true" if orthotropic_rocking else "false"
    if orthotropic_sliding is not None:
        updates["ortsc"] = "true" if orthotropic_sliding else "false"
    if sliding_law is not None:
        if sliding_law == "Elastic":
            updates["scorrhor"] = "false"
            updates["SlidingFractureEnergy"] = "false"
        elif sliding_law == "ElastoPlastic":
            updates["scorrhor"] = "true"
            updates["SlidingFractureEnergy"] = "false"
        elif sliding_law == "LinearSoftening":
            updates["scorrhor"] = "true"
            updates["SlidingFractureEnergy"] = "true"
        else:
            raise ValueError("sliding_law must be one of: Elastic, ElastoPlastic, LinearSoftening")

    if updates:
        if target_idx is None:
            target_idx = _resolve_collection_index(materials, key=key, name=name, index=index)
        root_attrs = materials[target_idx]["nodes"][0]["attributes"]
        if root_attrs.get("SimpleMode") == "true":
            updates.setdefault("SimpleMode", "false")
        changes = [
            {
                "collection": "material",
                "index": target_idx,
                "node": [],
                "attribute": attr_key,
                "value": str(attr_val),
            }
            for attr_key, attr_val in updates.items()
        ]
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": changes,
            "operations": [],
        })
        encoded = res["source"]
        inspected = res["inspection"]
        materials = inspected["collections"]["material"]

    out_bytes = base64.b64decode(encoded)
    if target_idx is None and (key is not None or name is not None or index is not None):
        target_idx = _resolve_collection_index(materials, key=key, name=name, index=index)
    summary = _summarize_masonry_advanced(materials[target_idx]) if target_idx is not None else {}
    return out_bytes, summary


def edit_analysis_hrx(
    data: bytes,
    *,
    add_template: str | None = None,
    duplicate_key: str | None = None,
    delete_key: str | None = None,
    key: str | None = None,
    name: str | None = None,
    index: int | None = None,
    node_path: list[int] | None = None,
    attributes: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Add, duplicate, delete, or edit an analysis in an HRX model."""
    encoded = base64.b64encode(data).decode("ascii")
    inspected = builder_api.inspect_source(encoded)
    analyses = inspected["collections"]["analysis"]

    target_idx: int | None = None
    if add_template is not None:
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": [],
            "operations": [{"op": "add_analysis", "template": str(add_template)}],
        })
        encoded = res["source"]
        inspected = res["inspection"]
        analyses = inspected["collections"]["analysis"]
        target_idx = len(analyses) - 1
    elif duplicate_key is not None:
        dup_idx = _resolve_collection_index(analyses, key=duplicate_key)
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": [],
            "operations": [{"op": "duplicate_analysis", "duplicate": dup_idx}],
        })
        encoded = res["source"]
        inspected = res["inspection"]
        analyses = inspected["collections"]["analysis"]
        target_idx = len(analyses) - 1
    elif delete_key is not None:
        del_idx = _resolve_collection_index(analyses, key=delete_key)
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": [],
            "operations": [{"op": "delete_analysis", "index": del_idx}],
        })
        out_bytes = base64.b64decode(res["source"])
        return out_bytes, {"deleted_key": delete_key, "remaining_analyses": len(res["inspection"]["analyses"])}

    if attributes:
        if target_idx is None:
            target_idx = _resolve_collection_index(analyses, key=key, name=name, index=index)
        changes = [
            {
                "collection": "analysis",
                "index": target_idx,
                "node": node_path or [],
                "attribute": str(attr_key),
                "value": str(attr_val),
            }
            for attr_key, attr_val in attributes.items()
        ]
        res = builder_api.apply_edits({
            "mode": "edit",
            "source": encoded,
            "changes": changes,
            "operations": [],
        })
        encoded = res["source"]
        inspected = res["inspection"]
        analyses = inspected["collections"]["analysis"]

    out_bytes = base64.b64decode(encoded)
    if target_idx is None and (key is not None or name is not None or index is not None):
        target_idx = _resolve_collection_index(analyses, key=key, name=name, index=index)
    selected_record = analyses[target_idx] if target_idx is not None else {}
    return out_bytes, {
        "key": selected_record.get("key"),
        "name": selected_record.get("name"),
        "attributes": selected_record.get("attributes", {}),
    }


def _parse_kv_pairs(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValueError(f"Expected ATTR=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hrx_cli.py",
        description="Create, inspect, and edit HiStrA .hrx bridge models, Advanced mode masonry materials, and analyses.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cat_p = sub.add_parser("catalog", help="Print available templates, geometry defaults, and valid enum schemas as JSON")
    cat_p.add_argument(
        "--section",
        choices=["all", "geometry", "materials", "analyses", "masonry-schema", "analysis-enums"],
        default="all",
        help="Optional catalog section to print",
    )

    init_p = sub.add_parser("init-spec", help="Write a starter parametric bridge JSON specification")
    init_p.add_argument("-o", "--output", help="Output JSON file path (prints to stdout if omitted)")

    create_p = sub.add_parser("create", help="Generate a .hrx bridge file from a JSON spec and/or dotted --set overrides")
    create_p.add_argument("--spec", help="Optional input JSON specification file")
    create_p.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="Override geometry parameter (e.g. --set nl=150 --set spans.0.L=800 --set spans.0.f=350)",
    )
    create_p.add_argument("--link", action="append", choices=("abutments", "piers", "spans", "all"), default=[], help="Apply geometry overrides to matching components; abutment sides are mirrored")
    create_p.add_argument("-o", "--output", required=True, help="Output .hrx file path")

    insp_p = sub.add_parser("inspect", help="Inspect an existing .hrx file and output structured JSON")
    insp_p.add_argument("hrx", help="Path to the .hrx file")
    insp_p.add_argument(
        "--section",
        choices=["all", "summary", "materials", "analyses", "loads"],
        default="all",
        help="Which section of the model to output",
    )

    mat_p = sub.add_parser("edit-material", help="Add, duplicate, delete, or configure a masonry material in Advanced mode")
    mat_p.add_argument("hrx", help="Input .hrx file path")
    mat_p.add_argument("-o", "--output", help="Output .hrx file path (defaults to updating input file in-place)")
    mat_p.add_argument("--add-template", help="Add a new masonry material from template key (see 'catalog --section materials')")
    mat_p.add_argument("--duplicate", help="Duplicate existing material by key")
    mat_p.add_argument("--delete", help="Delete unreferenced material by key")
    mat_p.add_argument("--key", help="Target material key to edit")
    mat_p.add_argument("--name", help="Target material name to edit")
    mat_p.add_argument("--index", type=int, help="Target material 0-based collection index to edit")
    mat_p.add_argument("--sliding-law", choices=["Elastic", "ElastoPlastic", "LinearSoftening"], help="Set Direction 1 sliding constitutive law")
    mat_p.add_argument("--orthotropic-rocking", choices=["true", "false"], help="Set rocking behavior (true=Orthotropic, false=Isotropic)")
    mat_p.add_argument("--orthotropic-sliding", choices=["true", "false"], help="Set sliding behavior (true=Orthotropic, false=Isotropic)")
    mat_p.add_argument(
        "--set",
        dest="attributes",
        action="append",
        default=[],
        metavar="ATTR=VALUE",
        help="Set material attribute (e.g. --set Ehor=1800 --set FmHor=3.2 --set TensileCurveType=LinearSoftening)",
    )

    ana_p = sub.add_parser("edit-analysis", help="Add, duplicate, delete, or configure an analysis")
    ana_p.add_argument("hrx", help="Input .hrx file path")
    ana_p.add_argument("-o", "--output", help="Output .hrx file path (defaults to updating input file in-place)")
    ana_p.add_argument("--add-template", help="Add a new analysis from template name (see 'catalog --section analyses')")
    ana_p.add_argument("--duplicate", help="Duplicate existing analysis by key")
    ana_p.add_argument("--delete", help="Delete unreferenced analysis by key")
    ana_p.add_argument("--key", help="Target analysis key to edit")
    ana_p.add_argument("--name", help="Target analysis name to edit")
    ana_p.add_argument("--index", type=int, help="Target analysis 0-based collection index to edit")
    ana_p.add_argument("--node-path", help="Optional dot-separated child node path (e.g. '0.1')")
    ana_p.add_argument(
        "--set",
        dest="attributes",
        action="append",
        default=[],
        metavar="ATTR=VALUE",
        help="Set analysis attribute (e.g. --set MaxIterations=50 --set ConvergenceTolerance=0.001)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            cat = get_catalog()
            section_map = {
                "all": cat,
                "geometry": {"geometry_defaults": cat["geometry_defaults"], "geometry_fields": cat["geometry_fields"]},
                "materials": cat["masonry_material_templates"],
                "analyses": cat["analysis_templates"],
                "masonry-schema": cat["masonry_advanced_schema"],
                "analysis-enums": cat["analysis_enums"],
            }
            print(json.dumps(section_map[args.section], indent=2, ensure_ascii=False))
            return 0

        if args.command == "init-spec":
            cat = get_catalog()
            text = json.dumps(cat["geometry_defaults"], indent=2, ensure_ascii=False) + "\n"
            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(text, encoding="utf-8")
                print(json.dumps({"written": str(out_path)}, indent=2))
            else:
                print(text, end="")
            return 0

        if args.command == "create":
            spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec else None
            hrx_bytes = create_bridge_hrx(spec=spec, overrides=args.overrides, linked_groups=args.link)
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(hrx_bytes)
            info = inspect_hrx_bytes(hrx_bytes, out_path.name, section="summary")
            print(json.dumps({"output": str(out_path), **info}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "inspect":
            hrx_path = Path(args.hrx)
            info = inspect_hrx_bytes(hrx_path.read_bytes(), hrx_path.name, section=args.section)
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return 0

        if args.command == "edit-material":
            in_path = Path(args.hrx)
            out_path = Path(args.output) if args.output else in_path
            updated_bytes, result = edit_material_hrx(
                in_path.read_bytes(),
                add_template=args.add_template,
                duplicate_key=args.duplicate,
                delete_key=args.delete,
                key=args.key,
                name=args.name,
                index=args.index,
                attributes=_parse_kv_pairs(args.attributes),
                sliding_law=args.sliding_law,
                orthotropic_rocking=(args.orthotropic_rocking == "true") if args.orthotropic_rocking else None,
                orthotropic_sliding=(args.orthotropic_sliding == "true") if args.orthotropic_sliding else None,
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(updated_bytes)
            print(json.dumps({"output": str(out_path), "material": result}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "edit-analysis":
            in_path = Path(args.hrx)
            out_path = Path(args.output) if args.output else in_path
            node_path = [int(p) for p in args.node_path.split(".") if p] if args.node_path else None
            updated_bytes, result = edit_analysis_hrx(
                in_path.read_bytes(),
                add_template=args.add_template,
                duplicate_key=args.duplicate,
                delete_key=args.delete,
                key=args.key,
                name=args.name,
                index=args.index,
                node_path=node_path,
                attributes=_parse_kv_pairs(args.attributes),
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(updated_bytes)
            print(json.dumps({"output": str(out_path), "analysis": result}, indent=2, ensure_ascii=False))
            return 0

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
