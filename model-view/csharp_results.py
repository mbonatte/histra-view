"""Project native HiStrA C# ``.Results`` databases for the browser viewer.

The C# application stores local Quad states, local interface resultants,
model-point displacements and a compact spring snapshot for every public step.
This adapter reconstructs the same per-Quad vertex kinematics and averaged node
translations used by the C# response output.  It never prepares or solves the
model.

Only the built-in sources are addressed here: the HRX supplies the model and
the sibling ``.Results`` SQLite file supplies the saved states.
"""
from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import math
import sqlite3
import sys

import numpy as np

BASE = Path(__file__).resolve().parent
HISTRA = BASE.parent / "histra-python"
if str(HISTRA) not in sys.path:
    sys.path.insert(0, str(HISTRA))

from histra.io.hr_loader import load_model
from histra.postprocessing import _average_node_displacements, _quad_local_displacement
from hrx_model import parse_hrx
from result_fields import complete_field_set

PHASE_NAMES = [
    "Elastic", "Plastic_t", "Plastic_c", "Unload_t", "Unload_c",
    "Reload_t", "Reload_c", "Rupture", "RuptureTraz", "RuptureComp", "Slip",
]
VIEWER_UNITS = {
    "length": "cm", "force": "kN", "moment": "kN·cm",
    "stress": "MPa", "energy": "kN·cm",
}
SOURCE_UNITS = {
    "length": "cm", "force": "kN", "moment": "kN*cm",
    "stress": "kN/cm^2", "rotation": "rad", "energy": "kN*cm",
}
PARENT_INTERFACE = 102

_MODEL_CACHE: dict[str, tuple[tuple[int, int], object, object, str]] = {}


def _cached_models(hrx_path: str | Path):
    """Load one HRX once and retain the parsed C# model beside its geometry."""
    path = Path(hrx_path).resolve()
    stamp = (path.stat().st_mtime_ns, path.stat().st_size)
    key = str(path)
    cached = _MODEL_CACHE.get(key)
    if cached and cached[0] == stamp:
        return cached[1], cached[2], cached[3]
    data = path.read_bytes()
    viewer = parse_hrx(data, path.name)
    model = load_model(path)
    digest = hashlib.sha256(data).hexdigest()
    _MODEL_CACHE.clear()
    _MODEL_CACHE[key] = (stamp, model, viewer, digest)
    return model, viewer, digest


def _connect(results_path: str | Path):
    path = Path(results_path).resolve()
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _float(value) -> float:
    return float(value or 0.0)


def _tables(conn) -> set[str]:
    return {str(row[0]) for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


def _analysis_names(model) -> dict[int, str]:
    return {int(key): str(getattr(analysis, "name", key))
            for key, analysis in model.collections.analyses.items()}


def _static_catalog(conn, model) -> list[dict]:
    names = _analysis_names(model)
    rows = conn.execute(
        "SELECT AnalysisKey, COUNT(DISTINCT Step), MIN(Step), MAX(Step) "
        "FROM QuadStates GROUP BY AnalysisKey ORDER BY AnalysisKey"
    ).fetchall()
    catalog = []
    for analysis_key, step_count, first_step, last_step in rows:
        key = int(analysis_key)
        name = names.get(key, f"Analysis {key}")
        analysis = model.collections.analyses.get(key)
        if analysis is not None and int(getattr(analysis, "analysis_type", 0) or 0) == 5:
            continue
        if name.lower().startswith("modal"):
            continue
        catalog.append({
            "name": name,
            "label": name,
            "steps": int(step_count),
            "firstStep": int(first_step),
            "lastStep": int(last_step),
        })
    return catalog


def _resolve_static(catalog: list[dict], analysis_name: str | None):
    if not catalog:
        raise ValueError("This C# results database contains no static Quad states.")
    if analysis_name:
        requested = str(analysis_name).strip()
        for item in catalog:
            if requested == item["name"]:
                return item["name"]
        lowered = requested.lower()
        for item in catalog:
            if lowered == item["name"].lower():
                return item["name"]
    for preferred in ("LiveLoad_1", "Vert", "LiveLoad_0"):
        for item in catalog:
            if item["name"] == preferred:
                return item["name"]
    return catalog[0]["name"]


def _analysis_key(model, name: str) -> int:
    for key, analysis in model.collections.analyses.items():
        if str(getattr(analysis, "name", "")) == name:
            return int(key)
    raise ValueError(f"Analysis {name!r} is not present in the HRX model.")


def _combination(conn, analysis_key: int) -> int:
    rows = conn.execute(
        "SELECT DISTINCT Combination FROM QuadStates WHERE AnalysisKey=? ORDER BY Combination",
        (int(analysis_key),),
    ).fetchall()
    if not rows:
        raise ValueError(f"Analysis {analysis_key} has no saved Quad states.")
    return int(rows[0][0])


def _steps(conn, analysis_key: int, combination: int) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT Step FROM QuadStates WHERE AnalysisKey=? AND Combination=? ORDER BY Step",
        (int(analysis_key), int(combination)),
    ).fetchall()
    if not rows:
        raise ValueError(f"Analysis {analysis_key} has no committed steps.")
    return [int(row[0]) for row in rows]


def _read_quad_states(conn, analysis_key: int, combination: int):
    values: dict[int, dict[int, tuple[float, ...]]] = {}
    rows = conn.execute(
        "SELECT Step,ParentKey,U1,U2,U3,U4,U5,U6,U7 FROM QuadStates "
        "WHERE AnalysisKey=? AND Combination=? ORDER BY Step,ParentKey",
        (int(analysis_key), int(combination)),
    )
    for row in rows:
        step = int(row[0])
        local = tuple(_float(row[index]) for index in range(2, 9))
        values.setdefault(step, {})[int(row[1])] = local
    return values


def _read_interface_states(conn, analysis_key: int, combination: int):
    values: dict[int, dict[int, tuple[float, ...]]] = {}
    if "InterfaceStates" not in _tables(conn):
        return values
    rows = conn.execute(
        "SELECT Step,ParentKey,ForceX,ForceY,ForceZ,BendingMomentsX,BendingMomentsY,BendingMomentsZ "
        "FROM InterfaceStates WHERE AnalysisKey=? AND Combination=? ORDER BY Step,ParentKey",
        (int(analysis_key), int(combination)),
    )
    for row in rows:
        step = int(row[0])
        values.setdefault(step, {})[int(row[1])] = tuple(_float(row[index]) for index in range(2, 8))
    return values


def _read_reaction_states(conn, analysis_key: int, combination: int):
    values: dict[int, tuple[float, ...]] = {}
    if "ReactionSumStates" not in _tables(conn):
        return values
    rows = conn.execute(
        "SELECT Step,R1,R2,R3,Et,Eel,Ed FROM ReactionSumStates "
        "WHERE AnalysisKey=? AND Combination=? ORDER BY Step",
        (int(analysis_key), int(combination)),
    )
    for row in rows:
        values[int(row[0])] = tuple(_float(row[index]) for index in range(1, 7))
    return values


def _read_model_points(conn, analysis_key: int, combination: int):
    values: dict[int, dict[int, tuple[float, float, float]]] = {}
    if "DisplModelPoints" not in _tables(conn):
        return values
    rows = conn.execute(
        "SELECT Step,ParentKey,Ux,Uy,Uz FROM DisplModelPoints "
        "WHERE AnalysisKey=? AND Combination=? ORDER BY Step,ParentKey",
        (int(analysis_key), int(combination)),
    )
    for row in rows:
        values.setdefault(int(row[0]), {})[int(row[1])] = tuple(
            _float(row[index]) for index in range(2, 5)
        )
    return values


def _read_spring_states(conn, analysis_key: int, combination: int, step: int):
    """Read the compact per-step spring snapshot used by the C# view."""
    values: dict[tuple[int, int, int, int], tuple] = {}
    tables = _tables(conn)
    for table in ("SpringStatesTmp", "SpringStates"):
        if table not in tables:
            continue
        rows = conn.execute(
            f"SELECT ParentType,ParentKey,SpringPurpose,IdLocal,F,U,Phase,"
            f"Up1,Up2,Fy1,Fy2,SpringType FROM {table} "
            "WHERE AnalysisKey=? AND Combination=? AND Step=?",
            (int(analysis_key), int(combination), int(step)),
        )
        for row in rows:
            key = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            values[key] = (
                _float(row[4]), _float(row[5]), int(_float(row[6])),
                _float(row[7]), _float(row[8]), _float(row[9]), _float(row[10]),
                int(_float(row[11])),
            )
        if values:
            break
    return values


def _load_multiplier(analysis, step: int) -> float | None:
    """Reproduce LoadControl public-step multipliers; ArcLength is not saved."""
    if str(getattr(analysis, "integration_method", "")) != "LoadControl":
        return None
    function = getattr(analysis, "load_function", None)
    items = sorted((float(item.pseudo_time), float(item.multiplier))
                   for item in (function.items if function else []))
    if not items:
        return None
    t = items[0][0]
    multiplier = items[0][1] * float(getattr(analysis, "mult", 1.0) or 0.0)
    for _ in range(int(step)):
        if t >= items[-1][0] - 1e-12:
            break
        pair = next(((a, b) for a, b in zip(items, items[1:])
                     if t < b[0] - 1e-12), None)
        if pair is None:
            pair = (items[-2], items[-1])
        (t0, f0), (t1, f1) = pair
        discretization = abs(float(function.discr_val))
        if discretization <= 0.0:
            return None
        span = abs(f1 - f0) if bool(function.type_discr) else abs(t1 - t0)
        count = max(1, int(np.ceil(span / discretization)))
        dt = (t1 - t0) / count
        dt = min(dt, t1 - t) if dt >= 0 else max(dt, t1 - t)
        df = ((f1 - f0) * (dt / (t1 - t0)) * float(getattr(analysis, "mult", 1.0) or 0.0)
              if abs(t1 - t0) > 1e-30 else 0.0)
        t += dt
        multiplier += df
    return float(multiplier)


def _mesh(model, viewer):
    histogram_quads = model.collections.quads
    histogram_nodes = model.collections.nodes
    viewer_quads = {int(item["key"]): item for item in viewer["quads"]}
    viewer_nodes = {int(item["key"]): item for item in viewer["nodes"]}

    quad_keys = sorted(int(key) for key in histogram_quads)
    used_nodes = sorted({int(node) for key in quad_keys for node in histogram_quads[key].node_keys})
    nodes = []
    for key in used_nodes:
        item = viewer_nodes.get(key)
        if item is None:
            point = histogram_nodes[key].point
            point = [float(point.x), float(point.y), float(point.z)]
            name = str(getattr(histogram_nodes[key], "name", key))
        else:
            point = [float(value) for value in item["point"]]
            name = str(item.get("name", key))
        if not np.isfinite(point).all():
            raise ValueError(f"Node {key} has a nonfinite coordinate.")
        nodes.append({"key": str(key), "name": name, "point": point})

    quads = []
    for key in quad_keys:
        item = viewer_quads.get(key)
        if item is None:
            raise ValueError(f"Quad {key} is absent from the HRX geometry.")
        quads.append({
            "key": str(key),
            "name": str(item.get("name", key)),
            "nodeKeys": [str(int(node)) for node in item["nodeKeys"]],
            "materialKey": str(int(item["materialKey"])),
            "thicknesses": [float(value) for value in item["thicknesses"]],
            "normals": [[float(value) for value in normal] for normal in item["normals"]],
        })

    interfaces = {}
    thrust_pairs = []
    for key, interface in sorted(model.collections.interfaces.items(), key=lambda pair: int(pair[0])):
        node_keys = [int(node) for node in interface.node_keys]
        points = []
        for node_key in node_keys:
            node = histogram_nodes.get(node_key)
            if node is None:
                point = None
            else:
                point = node.point
            points.append([float(point.x), float(point.y), float(point.z)] if point is not None else None)
        interfaces[str(int(key))] = {
            "nodeKeys": [str(node) for node in node_keys],
            "length": float(interface.length),
            "points": points,
        }
    for quad_key in quad_keys:
        quad = histogram_quads[quad_key]
        face_keys = quad.interface_keys
        for first, second in ((0, 2), (1, 3)):
            if len(face_keys) <= max(first, second):
                continue
            if len(face_keys[first]) == 1 and len(face_keys[second]) == 1:
                thrust_pairs.append([
                    int(quad_key), int(face_keys[first][0]), int(face_keys[second][0]),
                    str(int(viewer_quads[quad_key]["materialKey"])),
                ])

    materials = [{
        "key": str(int(item["key"])),
        "name": str(item.get("name", item["key"])),
        "color": str(item.get("color", "#6fb7ff")),
    } for item in viewer["materials"]]

    return ({
        "name": Path(viewer.get("name", "model.hrx")).name,
        "nodes": nodes,
        "quads": quads,
        "materials": materials,
        "thrustPairs": thrust_pairs,
        "interfaces": interfaces,
    }, quad_keys, used_nodes)


def _recovery_data(model, quad_keys: list[int], node_keys: list[int]):
    """Precompute C# Quad vertex kinematics and shared-node contributions."""
    quads = model.collections.quads
    nodes = model.collections.nodes
    corners = []
    centres = []
    corr2 = []
    corr3 = []
    for key in quad_keys:
        quad = quads[key]
        centres.append([float(quad.g.x), float(quad.g.y), float(quad.g.z)])
        points = []
        for node_key in quad.node_keys:
            point = nodes[int(node_key)].point
            points.append([float(point.x), float(point.y), float(point.z)])
        corners.append(points)
        e1 = np.asarray(quad.reference_e1, dtype=np.float32)
        e2 = np.asarray(quad.reference_e2, dtype=np.float32)
        denominator = float(quad.sin[2])
        coefficient = 0.0
        if abs(denominator) > 1e-30:
            coefficient = -float(quad.length[3]) * float(quad.sin[3]) / denominator
        corr2.append([
            coefficient * (float(quad.sin[1]) * float(e1[j]) + float(quad.cos[1]) * float(e2[j]))
            for j in range(3)
        ])
        corr3.append([
            float(quad.length[3]) * (-float(quad.sin[0]) * float(e1[j]) + float(quad.cos[0]) * float(e2[j]))
            for j in range(3)
        ])
    centres = np.asarray(centres, dtype=np.float32)
    corners = np.asarray(corners, dtype=np.float32)
    rel = (corners - centres[:, None, :]).astype(np.float32)
    corr2 = np.asarray(corr2, dtype=np.float32)
    corr3 = np.asarray(corr3, dtype=np.float32)

    connected: dict[int, list[tuple[int, int]]] = {key: [] for key in node_keys}
    for qi, key in enumerate(quad_keys):
        for corner_index, node_key in enumerate(quads[key].node_keys):
            connected[int(node_key)].append((qi, corner_index))
    if any(not contributions for contributions in connected.values()):
        missing = [key for key, contributions in connected.items() if not contributions]
        raise ValueError(f"Mesh nodes have no Quad contribution: {missing[:5]}")
    return rel, corr2, corr3, connected


def _vertex_displacements(local: np.ndarray, rel, corr2, corr3):
    local = np.asarray(local, dtype=np.float32)
    if local.ndim != 2 or local.shape[1] != 7:
        raise ValueError("Invalid local Quad state.")
    values = (local[:, None, :3] + np.cross(local[:, None, 3:6], rel).astype(np.float32)).astype(np.float32)
    values[:, 2, :] = values[:, 2, :] + (local[:, 6:7] * corr2).astype(np.float32)
    values[:, 3, :] = values[:, 3, :] + (local[:, 6:7] * corr3).astype(np.float32)
    return values


def _node_displacements(quad_values, connected, node_keys):
    return np.asarray([
        _average_node_displacements([quad_values[qi, corner] for qi, corner in connected[key]])
        for key in node_keys
    ], dtype=float)


def _encode_float32(values):
    array = np.ascontiguousarray(values, dtype="<f4")
    if not np.isfinite(array).all():
        raise ValueError("Nonfinite result field.")
    return base64.b64encode(array.tobytes()).decode("ascii")


def _round(values, digits=6):
    return np.round(np.asarray(values, dtype=np.float64), digits).tolist()


def _cell_positions(corners, nrow: int, ncol: int):
    """Bilinear cell corners; equivalent to C# GetAreaTrasvSpring."""
    corners = np.asarray([
        [float(point.x), float(point.y), float(point.z)] if hasattr(point, "x") else point
        for point in corners
    ], dtype=np.float64)
    positions = np.empty((nrow * ncol, 4, 3), dtype=np.float32)
    for row in range(nrow):
        for col in range(ncol):
            index = row * ncol + col
            for corner in range(4):
                c = col + (1 if corner in (1, 2) else 0)
                r = row + (1 if corner in (2, 3) else 0)
                u = 2.0 * c / ncol - 1.0
                v = 2.0 * r / nrow - 1.0
                weights = np.array([
                    (1 - u) * (1 - v) / 4,
                    (1 + u) * (1 - v) / 4,
                    (1 + u) * (1 + v) / 4,
                    (1 - u) * (1 + v) / 4,
                ], dtype=np.float64)
                positions[index, corner] = (weights @ corners).astype(np.float32)
    return positions


def _spring_geometry(interface, purpose: int, index: int):
    groups = {
        1: getattr(interface, "trasv_1", []),
        11: getattr(interface, "slid", []),
        21: getattr(interface, "slid_out_plan", []),
    }
    group = groups.get(purpose, [])
    if index < 0 or index >= len(group):
        return None
    spring = group[index]
    return (
        float(getattr(spring, "area", 0.0) or 0.0),
        float(getattr(spring, "length", 0.0) or 0.0),
        spring,
    )


def _plastic_values(spring, spring_type: int, displacement: float, force: float,
                    up1: float, up2: float, fy1: float, fy2: float, length: float):
    """Reproduce the supported C# ``GetStrainPlastic``/``GetUpOverUr`` branches.

    The native database stores Up1/Up2, Fy1/Fy2 and the spring type for every
    public step, but not the initial stiffness or ultimate reference displacement.
    The initial stiffness and Ur are restored from the HRX spring where the
    selected C# spring type provides them.
    """
    if spring_type == 1:  # LinearElastic
        return 0.0, 0.0
    if length <= 0.0:
        return None, None
    up_value = None
    if spring_type == 2:  # ElastoPlastic: (|Up1| + |Up2|) / Length
        up_value = (abs(up1) + abs(up2)) / length
    elif spring_type in (3, 8, 10):
        stiffness = float(getattr(spring, "k", 0.0) or 0.0)
        if stiffness <= 0.0:
            return None, None
        if spring_type == 3:  # Coulomb02: |U| - |Fy / K|
            fy = fy1 if displacement >= 0.0 else fy2
            up_value = max(0.0, abs(displacement) - abs(fy / stiffness)) / length
        elif spring_type == 8:  # Hysteretic: |U| - |Fy / K|
            fy = fy1 if displacement >= 0.0 else fy2
            up_value = max(0.0, abs(displacement) - abs(fy / stiffness)) / length
        else:  # Coulomb03: U - F / K
            up_value = max(0.0, displacement - force / stiffness) / length
    if up_value is None:
        return None, None
    ur = getattr(spring, "ur", None)
    ratio = 0.0
    if ur is not None and hasattr(ur, "__len__") and len(ur) >= 2:
        reference = abs(float(ur[0] if displacement >= 0.0 else ur[1]))
        if reference > 0.0 and np.isfinite(reference):
            ratio = max(0.0, up_value / reference)
    return up_value, ratio


def _spring_values(interface, snapshot, purpose: int, index: int, group: str | None = None):
    geometry = _spring_geometry(interface, purpose, index)
    if geometry is None:
        area = length = 0.0
        spring = None
    else:
        area, length, spring = geometry
    stored = snapshot.get(
        (PARENT_INTERFACE, int(interface.key), int(purpose), int(index)),
        (0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 1),
    )
    force, displacement, phase = stored[:3]
    up1, up2, fy1, fy2, spring_type = stored[3:8]
    stress = force / area * 10.0 if area > 0 else 0.0
    csharp_strain = displacement / length if length > 0 else None
    plastic, plastic_ratio = _plastic_values(
        spring, int(spring_type), float(displacement), float(force),
        float(up1), float(up2), float(fy1), float(fy2), float(length),
    ) if spring is not None else (None, None)
    return {
        "index": int(index),
        "row": int(index // max(1, int(interface.ncol))) if group is None and purpose == 1 else None,
        "col": int(index % max(1, int(interface.ncol))) if group is None and purpose == 1 else None,
        "group": group,
        "type": "Spring",
        "force": float(force),
        "area": float(area),
        "stress": float(stress),
        "displacement": float(displacement),
        "strain": float(displacement),
        "csharpStrain": csharp_strain,
        "plasticStrain": plastic,
        "plasticStrainRatio": plastic_ratio,
        "phase": PHASE_NAMES[phase] if 0 <= phase < len(PHASE_NAMES) else "Unknown",
    }


def _interface_values(interface, snapshot):
    nrow, ncol = int(interface.nrow), int(interface.ncol)
    normal = [_spring_values(interface, snapshot, 1, index) for index in range(nrow * ncol)]
    sliding = [_spring_values(interface, snapshot, 11, 0, "slid")]
    sliding.extend(_spring_values(interface, snapshot, 21, index, "slid_out_plan")
                   for index in range(len(getattr(interface, "slid_out_plan", []))))
    return normal, sliding


def _interface_stress_arrays(interface, snapshot):
    normal, sliding = _interface_values(interface, snapshot)
    sigma = np.asarray([item["stress"] for item in normal], dtype=np.float64)
    tau = [item["stress"] for item in sliding]
    while len(tau) < 3:
        tau.append(0.0)
    return sigma.reshape(int(interface.nrow), int(interface.ncol)), tau[:3]


def _phase_counts(values):
    counts = {}
    for item in values:
        name = item["phase"]
        counts[name] = counts.get(name, 0) + 1
    return counts


def _interface_summary(interface, resultants, snapshot):
    normal, _ = _interface_values(interface, snapshot)
    stresses = [item["stress"] for item in normal]
    return {
        "key": int(interface.key),
        "parents": [int(interface.parent_element_key1), int(interface.parent_element_key2)],
        "parentTypes": [str(interface.parent_type_element1), str(interface.parent_type_element2)],
        "restrained": bool(interface.interfaccia_vincolata_computed()),
        "materialKey": str(int(getattr(interface, "material_key", 0) or 0)),
        "forces": [float(value) for value in resultants[:3]],
        "moments": [float(value) for value in resultants[3:]],
        "minStress": float(min(stresses)) if stresses else None,
        "maxStress": float(max(stresses)) if stresses else None,
        "phases": _phase_counts(normal),
    }


def _interface_tensor(interface, sigma_grid, tau):
    e1 = np.asarray(interface.reference_e1, dtype=float)
    e3 = np.asarray(interface.reference_e3, dtype=float)
    e2 = np.cross(e3, e1)
    norm = float(np.linalg.norm(e2))
    if norm <= 1e-12:
        return None, None
    e2 = e2 / norm
    if sigma_grid.size == 0:
        return None, None
    end_sigma = []
    for endpoint in (0, 1):
        column = 0 if endpoint == 0 else sigma_grid.shape[1] - 1
        end_sigma.append(float(np.mean(sigma_grid[:, column])))
    tensors = []
    for endpoint in (0, 1):
        local = np.array([
            [0.0, tau[0], 0.0],
            [tau[0], end_sigma[endpoint], tau[1 + endpoint]],
            [0.0, tau[1 + endpoint], 0.0],
        ], dtype=float)
        rotation = np.column_stack([e1, e2, e3])
        tensors.append(rotation @ local @ rotation.T)
    return tensors[0], tensors[1]


def _von_mises(tensor):
    if tensor is None:
        return 0.0
    s11, s22, s33 = tensor[0, 0], tensor[1, 1], tensor[2, 2]
    s12, s23, s13 = tensor[0, 1], tensor[1, 2], tensor[0, 2]
    return float(np.sqrt(max(0.0, s11 * s11 + s22 * s22 + s33 * s33
                             - s11 * s22 - s11 * s33 - s22 * s33
                             + 3.0 * (s12 * s12 + s23 * s23 + s13 * s13))))


def _face_values(model, mesh, interface_keys, interface_index, sigma_grids,
                  normal_values, sliding_values):
    """Project interface corner tensors onto the six physical Quad faces.

    This is the native-results equivalent of the bridge v2 face-aware level:
    it samples the saved normal/spring grid at the interface corners and maps
    top, bottom and side faces independently. It deliberately does not claim to
    be the C# edge-interpolated face texture; see RESULTS_FIDELITY.md.
    """
    nodes = {int(item["key"]): np.asarray(item["point"], dtype=float) for item in mesh["nodes"]}
    quads = {int(item["key"]): item for item in mesh["quads"]}
    interface_corner_data = []
    lookup = {}

    for key in interface_keys:
        interface = model.collections.interfaces[key]
        i = interface_index[key]
        sigma_grid = np.asarray(sigma_grids[i], dtype=float)
        normal = normal_values[i]
        sliding = sliding_values[i]
        tau_in = float(sliding[0]["stress"]) if sliding else 0.0
        tau_out = [
            float(sliding[1]["stress"]) if len(sliding) > 1 else 0.0,
            float(sliding[2]["stress"]) if len(sliding) > 2 else 0.0,
        ]
        e1 = np.asarray(interface.reference_e1, dtype=float)
        e3 = np.asarray(interface.reference_e3, dtype=float)
        e2 = np.cross(e3, e1)
        norm = float(np.linalg.norm(e2))
        if norm <= 1e-12 or sigma_grid.size == 0:
            interface_corner_data.append([None] * 4)
            continue
        e2 /= norm
        rotation = np.column_stack([e1, e2, e3])
        nrow, ncol = sigma_grid.shape
        entries = []
        for corner in range(4):
            row = 0 if corner in (0, 1) else nrow - 1
            col = 0 if corner in (0, 3) else ncol - 1
            sigma = float(sigma_grid[row, col])
            if not np.isfinite(sigma):
                sigma = float(np.nanmean(sigma_grid))
            tau = tau_out[0 if corner in (0, 3) else 1]
            local = np.array([
                [0.0, tau_in, 0.0],
                [tau_in, sigma, tau],
                [0.0, tau, 0.0],
            ], dtype=float)
            item = normal[row * ncol + col] if row * ncol + col < len(normal) else {}
            out_index = 1 + (0 if corner in (0, 3) else 1)
            entries.append({
                "key": int(key),
                "tensor": rotation @ local @ rotation.T,
                "e1": e1,
                "e3": e3,
                "e2": e2,
                "localStressNormal": sigma,
                "localStressInPlane": tau_in,
                "localStressOutOfPlane": tau,
                "localStrainNormal": item.get("csharpStrain"),
                "localStrainInPlane": sliding[0].get("csharpStrain") if sliding else None,
                "localStrainOutOfPlane": (sliding[out_index].get("csharpStrain")
                                          if len(sliding) > out_index else None),
                "plasticStrainNormal": item.get("plasticStrain"),
                "plasticStrainRatioNormal": item.get("plasticStrainRatio"),
            })
        interface_corner_data.append(entries)
        for corner, point in enumerate(interface.vint3d):
            lookup.setdefault(tuple(round(float(value), 3) for value in
                                    (point.x, point.y, point.z)), []).append((i, corner))

    face_refs = (
        (("t", 0), ("t", 1), ("t", 2), ("t", 3)),
        (("b", 0), ("b", 1), ("b", 2), ("b", 3)),
        (("t", 0), ("t", 1), ("b", 1), ("b", 0)),
        (("t", 1), ("t", 2), ("b", 2), ("b", 1)),
        (("t", 2), ("t", 3), ("b", 3), ("b", 2)),
        (("t", 3), ("t", 0), ("b", 0), ("b", 3)),
    )
    face_edge_faces = (
        (0, 1, 2, 3), (0, 1, 2, 3),
        (5, 1, 4, 3), (5, 2, 4, 0),
        (5, 3, 4, 1), (5, 0, 4, 2),
    )
    face_opposite = (5, 4, 0, 1, 2, 3)
    corner_edges = ((3, 0), (0, 1), (1, 2), (2, 3))
    tensor_values = {name: [] for name in (
        "globalStressX", "globalStressY", "globalStressZ",
        "globalStressXY", "globalStressXZ", "globalStressYZ",
        "principalTensile", "principalCompressive", "vonMises",
    )}
    scalar_values = {name: [] for name in (
        "localStressNormal", "localStressInPlane", "localStressOutOfPlane",
        "localStrainNormal", "localStrainInPlane", "localStrainOutOfPlane",
        "plasticStrainNormal", "plasticStrainRatioNormal",
    )}

    def principal(tensor, which):
        eigenvalues = np.linalg.eigvalsh(tensor)
        value = float(eigenvalues[-1] if which == "max" else eigenvalues[0])
        if which == "max":
            return max(0.0, value)
        return min(0.0, value)

    for quad_key in sorted(model.collections.quads):
        quad = quads.get(int(quad_key))
        if quad is None:
            for target in tensor_values.values():
                target.append([[0.0] * 4 for _ in range(6)])
            for target in scalar_values.values():
                target.append([[0.0] * 4 for _ in range(6)])
            continue
        base = np.asarray([nodes[int(node)] for node in quad["nodeKeys"]], dtype=float)
        normals = np.asarray(quad["normals"], dtype=float)
        thickness = np.asarray(quad["thicknesses"], dtype=float)
        top = base + 0.5 * thickness[:, None] * normals
        bottom = base - 0.5 * thickness[:, None] * normals
        face_points = [
            np.asarray([{"t": top, "b": bottom}[side][index] for side, index in refs], dtype=float)
            for refs in face_refs
        ]

        def quad_area(points):
            return 0.5 * float(np.linalg.norm(
                np.cross(points[2] - points[0], points[3] - points[1])
            ))

        model_quad = model.collections.quads[int(quad_key)]
        face_sets = [
            {int(key) for key in (model_quad.interface_keys[face]
                                  if face < len(model_quad.interface_keys) else [])}
            for face in range(6)
        ]
        face_use_opposite = []
        for face in range(6):
            face_area = quad_area(face_points[face])
            opposite_area = 0.0
            for key in face_sets[face_opposite[face]]:
                interface = model.collections.interfaces[key]
                points = np.asarray([[point.x, point.y, point.z] for point in interface.vint3d])
                opposite_area += quad_area(points)
            face_use_opposite.append(face_area > 0.0 and opposite_area / face_area > 0.9)
        corners = {}
        all_tensors = []
        all_quad_data = []
        for side_name, points in (("t", top), ("b", bottom)):
            for index, point in enumerate(points):
                entries = lookup.get(tuple(round(float(value), 3) for value in point), [])
                data = [interface_corner_data[i][corner] for i, corner in entries]
                data = [item for item in data if item is not None]
                all_tensors.extend(item["tensor"] for item in data)
                all_quad_data.extend(data)
                corners[(side_name, index)] = data
        fallback_tensor = np.mean(all_tensors, axis=0) if all_tensors else None

        corners_for_entries = {
            ref: [item for item in data if item is not None]
            for ref, data in corners.items()
        }

        face_tensors = []
        face_scalars = {name: [] for name in scalar_values}
        for face, refs in enumerate(face_refs):
            face_tensor = []
            face_scalar = {name: [] for name in scalar_values}
            for corner, ref in enumerate(refs):
                edge_entries = []
                edge_entries_by_edge = {}
                edge_tensors = []
                opposite = [
                    item for item in corners_for_entries.get(ref, [])
                    if item.get("key") in face_sets[face_opposite[face]]
                ]
                for edge in corner_edges[corner]:
                    allowed = face_sets[face_edge_faces[face][edge]]
                    values = [
                        item for item in corners_for_entries.get(ref, [])
                        if item.get("key") in allowed
                    ]
                    edge_entries.extend(values)
                    edge_entries_by_edge[edge] = values
                    if not values:
                        continue
                    edge_tensor = np.mean([item["tensor"] for item in values], axis=0)
                    reference = values[0]
                    edge_e1 = np.asarray(reference["e1"], dtype=float)
                    edge_e3 = np.asarray(reference["e3"], dtype=float)
                    edge_e2 = np.cross(edge_e3, edge_e1)
                    length = float(np.linalg.norm(edge_e2))
                    if length > 1e-12:
                        edge_e2 /= length
                        for item in opposite:
                            normal = np.asarray(item["e2"], dtype=float)
                            for axis in (edge_e1, edge_e2, edge_e3):
                                edge_tensor += (abs(float(np.dot(normal, axis)))
                                                * float(item["localStressNormal"])
                                                * np.outer(axis, axis))
                            shear = (
                                float(item["localStressInPlane"])
                                * (np.dot(item["e1"], edge_e1) + np.dot(item["e1"], edge_e3))
                                + float(item["localStressOutOfPlane"])
                                * (np.dot(item["e3"], edge_e1) + np.dot(item["e3"], edge_e3))
                            )
                            edge_tensor += shear * (
                                np.outer(edge_e1, edge_e3) + np.outer(edge_e3, edge_e1)
                            )
                    edge_tensors.append(edge_tensor)
                tensor = np.mean(edge_tensors, axis=0) if edge_tensors else fallback_tensor
                if opposite:
                    opposite_tensor = np.mean([item["tensor"] for item in opposite], axis=0)
                    tensor = (tensor + opposite_tensor) if tensor is not None else opposite_tensor
                face_tensor.append(tensor)
                for name in scalar_values:
                    type_face = face in (3, 5)
                    if name in ("localStressNormal", "localStrainNormal",
                                "plasticStrainNormal", "plasticStrainRatioNormal"):
                        edge = (1 if type_face else 0) if corner in (0, 1) else (
                            3 if type_face else 2
                        )
                    else:
                        edge = (2 if type_face else 1) if corner in (1, 2) else (
                            0 if type_face else 3
                        )
                    sources = opposite if face_use_opposite[face] else edge_entries_by_edge.get(edge, [])
                    values = [item.get(name) for item in sources
                              if item.get(name) is not None and np.isfinite(item.get(name))]
                    if values:
                        face_scalar[name].append(float(np.mean(values)))
                    else:
                        fallback_values = [item.get(name) for item in all_quad_data
                                           if item.get(name) is not None and np.isfinite(item.get(name))]
                        face_scalar[name].append(
                            float(np.mean(fallback_values)) if fallback_values else 0.0
                        )
            face_tensors.append(face_tensor)
            for name in scalar_values:
                face_scalars[name].append(face_scalar[name])
        for name in tensor_values:
            target = tensor_values[name]
            face = []
            for refs in face_tensors:
                output = []
                for tensor in refs:
                    if tensor is None:
                        output.append(0.0)
                    elif name == "globalStressX":
                        output.append(float(tensor[0, 0]))
                    elif name == "globalStressY":
                        output.append(float(tensor[1, 1]))
                    elif name == "globalStressZ":
                        output.append(float(tensor[2, 2]))
                    elif name == "globalStressXY":
                        output.append(float(tensor[0, 1]))
                    elif name == "globalStressXZ":
                        output.append(float(tensor[0, 2]))
                    elif name == "globalStressYZ":
                        output.append(float(tensor[1, 2]))
                    elif name == "principalTensile":
                        output.append(principal(tensor, "max"))
                    elif name == "principalCompressive":
                        output.append(principal(tensor, "min"))
                    else:
                        output.append(_von_mises(tensor))
                face.append(output)
            target.append(face)
        for name in scalar_values:
            target = scalar_values[name]
            target.append(face_scalars[name])

    result = dict(tensor_values)
    result.update(scalar_values)
    return result


def _stress_fields(model, snapshot, step: int, mesh=None, resultants=None):
    """Build the complete C# stress/strain menu from a native spring snapshot.

    Stress fields use the same interface tensor construction as the C# viewer:
    the normal spring supplies M22, the in-plane sliding spring supplies M12 and
    the endpoint-selected out-of-plane spring supplies M23. Local maps expose the
    same saved normal/sliding spring components directly. Strain fields are
    available where the HRX spring length is known; C# hysteretic springs do not
    serialize that length, so those fibres remain partial rather than being
    silently assigned a guessed value. Ratio-plastic-strain needs the ultimate
    displacement Ur, which ``SpringStatesTmp`` does not store.
    """
    interface_keys = sorted(int(key) for key in model.collections.interfaces)
    interface_index = {key: index for index, key in enumerate(interface_keys)}
    node_positions = {
        int(node_key): np.array([node.point.x, node.point.y, node.point.z], dtype=float)
        for node_key, node in model.collections.nodes.items()
    }
    interface_tensors = []
    interface_sigma = []
    interface_normal = []
    interface_sliding = []
    endpoint_values = {"normalStress": [], "inPlaneStress": [], "outOfPlaneStress": [],
                       "normalStrain": [], "inPlaneStrain": [], "outOfPlaneStrain": [],
                       "normalPlastic": [], "normalPlasticRatio": []}

    for key in interface_keys:
        interface = model.collections.interfaces[key]
        sigma, tau = _interface_stress_arrays(interface, snapshot)
        tensors = _interface_tensor(interface, sigma, tau)
        interface_tensors.append(tensors)
        interface_sigma.append(sigma)
        normal, sliding = _interface_values(interface, snapshot)
        interface_normal.append(normal)
        interface_sliding.append(sliding)
        nrow, ncol = int(interface.nrow), int(interface.ncol)
        sigma_grid = np.asarray([item["stress"] for item in normal], dtype=float).reshape(nrow, ncol)
        for name, target in (("csharpStrain", "normalStrain"),
                             ("plasticStrain", "normalPlastic"),
                             ("plasticStrainRatio", "normalPlasticRatio")):
            values = []
            for endpoint in (0, 1):
                column = 0 if endpoint == 0 else ncol - 1
                samples = [item[name] for item in normal if item["col"] == column and item[name] is not None]
                values.append(float(np.mean(samples)) if samples else None)
            endpoint_values[target].append(values)
        endpoint_values["normalStress"].append([
            float(np.mean(sigma_grid[:, 0])), float(np.mean(sigma_grid[:, -1])),
        ])
        sl = sliding
        endpoint_values["inPlaneStress"].append([sl[0]["stress"], sl[0]["stress"]])
        endpoint_values["outOfPlaneStress"].append([
            sl[1]["stress"] if len(sl) > 1 else 0.0,
            sl[2]["stress"] if len(sl) > 2 else 0.0,
        ])
        endpoint_values["inPlaneStrain"].append([sl[0]["csharpStrain"], sl[0]["csharpStrain"]])
        endpoint_values["outOfPlaneStrain"].append([
            sl[1]["csharpStrain"] if len(sl) > 1 else None,
            sl[2]["csharpStrain"] if len(sl) > 2 else None,
        ])

    corner_links = []
    for key in sorted(model.collections.quads):
        quad = model.collections.quads[key]
        quad_points = np.asarray([node_positions[int(node)] for node in quad.node_keys], dtype=float)
        links = [[], [], [], []]
        for side in range(4):
            face_keys = quad.interface_keys[side] if side < len(quad.interface_keys) else []
            first, last = side, (side + 1) % 4
            for raw_key in face_keys:
                interface_key = int(raw_key)
                if interface_key not in interface_index:
                    continue
                interface = model.collections.interfaces[interface_key]
                if len(interface.node_keys) != 2:
                    continue
                i = interface_index[interface_key]
                p0, p1 = node_positions[int(interface.node_keys[0])], node_positions[int(interface.node_keys[1])]
                forward = np.linalg.norm(p0 - quad_points[first]) + np.linalg.norm(p1 - quad_points[last])
                reverse = np.linalg.norm(p0 - quad_points[last]) + np.linalg.norm(p1 - quad_points[first])
                if forward <= reverse:
                    links[first].append((i, 0))
                    links[last].append((i, 1))
                else:
                    links[first].append((i, 1))
                    links[last].append((i, 0))
        corner_links.append(links)

    def tensor_field(evaluator):
        output = []
        for links in corner_links:
            data = [interface_tensors[i][endpoint] for i, endpoint in
                    (link for face in links for link in face)]
            data = [tensor for tensor in data if tensor is not None]
            fallback = np.mean(data, axis=0) if data else None
            corners = []
            for face in links:
                face_data = [interface_tensors[i][endpoint] for i, endpoint in face]
                face_data = [tensor for tensor in face_data if tensor is not None]
                tensor = np.mean(face_data, axis=0) if face_data else fallback
                corners.append(evaluator(tensor) if tensor is not None else 0.0)
            output.append(corners)
        return output

    def scalar_field(name):
        series = endpoint_values[name]
        output = []
        for links in corner_links:
            flat = [series[i][endpoint] for face in links for i, endpoint in face]
            valid = [value for value in flat if value is not None and np.isfinite(value)]
            fallback = float(np.mean(valid)) if valid else 0.0
            corners = []
            for face in links:
                face_values = [series[i][endpoint] for i, endpoint in face]
                face_values = [value for value in face_values if value is not None and np.isfinite(value)]
                corners.append(float(np.mean(face_values)) if face_values else fallback)
            output.append(corners)
        return output

    def missing_scalar(name):
        for values in endpoint_values[name]:
            if any(value is not None and np.isfinite(value) for value in values):
                return False
        return True

    def partial_scalar(name):
        for values in endpoint_values[name]:
            if any(value is None or not np.isfinite(value) for value in values):
                return True
        return False

    def principal(tensor, which):
        if tensor is None:
            return 0.0
        eigenvalues = np.linalg.eigvalsh(tensor)
        value = float(eigenvalues[-1] if which == "max" else eigenvalues[0])
        if which == "max" and value < 0.0:
            return 0.0
        if which == "min" and value > 0.0:
            return 0.0
        return value

    values = {
        "globalStressX": tensor_field(lambda tensor: tensor[0, 0]),
        "globalStressY": tensor_field(lambda tensor: tensor[1, 1]),
        "globalStressZ": tensor_field(lambda tensor: tensor[2, 2]),
        "globalStressXY": tensor_field(lambda tensor: tensor[0, 1]),
        "globalStressXZ": tensor_field(lambda tensor: tensor[0, 2]),
        "globalStressYZ": tensor_field(lambda tensor: tensor[1, 2]),
        "principalTensile": tensor_field(lambda tensor: principal(tensor, "max")),
        "principalCompressive": tensor_field(lambda tensor: principal(tensor, "min")),
        "vonMises": tensor_field(_von_mises),
        "localStressNormal": scalar_field("normalStress"),
        "localStressInPlane": scalar_field("inPlaneStress"),
        "localStressOutOfPlane": scalar_field("outOfPlaneStress"),
    }
    if resultants is not None:
        quad_diagonal_sigma = []
        quad_diagonal_phase = []
        has_diagonal_phase = False
        for quad_key in sorted(model.collections.quads):
            quad = model.collections.quads[quad_key]
            ratios = []
            for face in range(4):
                keys = quad.interface_keys[face] if face < len(quad.interface_keys) else []
                force = 0.0
                area = 0.0
                for raw_key in keys:
                    key = int(raw_key)
                    force += float(resultants.get(key, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))[1])
                    interface = model.collections.interfaces.get(key)
                    if interface is not None:
                        points = np.asarray([[point.x, point.y, point.z] for point in interface.vint3d])
                        area += 0.5 * float(np.linalg.norm(
                            np.cross(points[2] - points[0], points[3] - points[1])
                        ))
                ratios.append(force / area * 10.0 if area > 0 else 0.0)
            value = (ratios[0] + ratios[2]) * 0.5 + (ratios[1] + ratios[3]) * 0.5
            quad_diagonal_sigma.append([value] * 4)
            stored = snapshot.get((106, int(quad_key), 30, 0))
            phase = 0
            if stored is not None:
                has_diagonal_phase = True
                phase_index = int(stored[2])
                phase = phase_index if 0 <= phase_index < len(PHASE_NAMES) else 0
            quad_diagonal_phase.append([float(phase)] * 4)
        values["quadDiagonalSigma"] = quad_diagonal_sigma
        if has_diagonal_phase:
            values["quadDiagonalPhase"] = quad_diagonal_phase
    partial_fields = set()
    for field_id, name in (
        ("localStrainNormal", "normalStrain"),
        ("localStrainInPlane", "inPlaneStrain"),
        ("localStrainOutOfPlane", "outOfPlaneStrain"),
        ("plasticStrainNormal", "normalPlastic"),
        ("plasticStrainRatioNormal", "normalPlasticRatio"),
    ):
        if not missing_scalar(name):
            values[field_id] = scalar_field(name)
            if partial_scalar(name):
                partial_fields.add(field_id)
    fields = complete_field_set(
        values, step,
        "C# native .Results interface-spring fields · final step",
        "This native C# result does not contain the spring length or Ur needed for this map.",
        partial_fields=partial_fields,
    )
    if mesh is not None:
        face_values = _face_values(
            model, mesh, interface_keys, interface_index,
            interface_sigma, interface_normal, interface_sliding,
        )
        for field in fields:
            if not field.get("available"):
                continue
            face_array = face_values.get(field["id"])
            if face_array is None:
                continue
            array = np.asarray(face_array, dtype=float)
            if not np.isfinite(array).all():
                continue
            field["quadFaceValues"] = np.round(array, 6).tolist()
            field["min"] = float(array.min())
            field["max"] = float(array.max())
    von_mises_field = next(field for field in fields if field["id"] == "vonMises")
    return fields, von_mises_field


def _final_stress(model, snapshot, step: int):
    """Backward-compatible Von Mises descriptor."""
    return _stress_fields(model, snapshot, step)[1]


def _step_records(model, quad_keys, node_keys, rel, corr2, corr3, connected,
                  quad_states, interface_states, reactions, model_points):
    interface_order = [int(key) for key in sorted(model.collections.interfaces)]
    control_key = None
    if model_points:
        final_step = max(model_points)
        candidates = model_points.get(final_step, {})
        if candidates:
            control_key = max(candidates, key=lambda key: (
                math.sqrt(sum(value * value for value in candidates[key])), -key
            ))
    initial_reaction = None
    for step in sorted(quad_states):
        if step in reactions:
            initial_reaction = reactions[step][2]
            break
    records = []
    for step in sorted(quad_states):
        local_rows = np.asarray([
            quad_states[step].get(key, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
            for key in quad_keys
        ], dtype=np.float32)
        quad_values = _vertex_displacements(local_rows, rel, corr2, corr3)
        node_values = _node_displacements(quad_values, connected, node_keys)
        if control_key is not None and step in model_points and control_key in model_points[step]:
            control = math.sqrt(sum(value * value for value in model_points[step][control_key]))
        else:
            control = float(np.max(np.linalg.norm(node_values, axis=1))) if len(node_values) else 0.0
        reaction = reactions.get(step)
        if reaction is not None:
            applied = initial_reaction - reaction[2] if initial_reaction is not None else 0.0
            reaction_values = [float(reaction[0]), float(reaction[1]), float(reaction[2])]
            elastic = float(reaction[4])
            dissipated = float(reaction[5])
        else:
            applied = None
            reaction_values = [None, None, None]
            elastic = None
            dissipated = None
        resultants = [
            [float(value) for value in interface_states.get(step, {}).get(key, (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))]
            for key in interface_order
        ]
        records.append({
            "step": int(step),
            "status": "INITIAL" if step == min(quad_states) else "OK",
            "loadFactor": None,
            "controlDisplacement": control,
            "displacements": _round(node_values),
            "quadDisplacements": _encode_float32(quad_values),
            "maxDisplacement": float(np.max(np.linalg.norm(node_values, axis=1))) if len(node_values) else 0.0,
            "appliedVerticalForce": applied,
            "reactions": reaction_values,
            "elasticEnergy": elastic,
            "dissipatedEnergy": dissipated,
            "interfaceResultants": _round(resultants),
        })
    return records, interface_order


def _modal_results(conn, model, nrow_data):
    """Return all modal analyses whose mode shapes are stored in the database."""
    tables = _tables(conn)
    if "ModalValues" not in tables or "ModalShapeValues" not in tables:
        return []
    names = _analysis_names(model)
    rows = conn.execute(
        "SELECT DISTINCT AnalysisKey FROM ModalValues ORDER BY AnalysisKey"
    ).fetchall()
    modal = []
    for (analysis_key,) in rows:
        key = int(analysis_key)
        values = conn.execute(
            "SELECT Step,Wn,Fn,Tn,Mx_pcent,My_pcent,Mz_pcent FROM ModalValues "
            "WHERE AnalysisKey=? AND Combination=1 ORDER BY Step",
            (key,),
        ).fetchall()
        if not values:
            continue
        shape_rows = conn.execute(
            "SELECT Step,Dof,Val FROM ModalShapeValues WHERE AnalysisKey=? AND Combination=1 "
            "ORDER BY Step,Dof",
            (key,),
        ).fetchall()
        shapes: dict[int, dict[int, float]] = {}
        for step, dof, value in shape_rows:
            shapes.setdefault(int(step), {})[int(dof)] = float(value or 0.0)
        modes = []
        for step, _wn, frequency, period, mx, my, mz in values:
            shape = shapes.get(int(step), {})
            if len(shape) != int(model.gdl):
                continue
            global_u = np.asarray([shape.get(dof, 0.0) for dof in range(int(model.gdl))], dtype=float)
            local_rows = np.asarray([
                _quad_local_displacement(model.collections.quads[key_quad], global_u)
                for key_quad in sorted(model.collections.quads)
            ], dtype=np.float32)
            quad_values = _vertex_displacements(local_rows, *nrow_data["vertex"])
            node_values = _node_displacements(quad_values, nrow_data["connected"], nrow_data["node_keys"])
            maximum = float(np.max(np.linalg.norm(node_values, axis=1))) if len(node_values) else 0.0
            if maximum > 0:
                node_values = node_values / maximum
                quad_values = quad_values / maximum
            modes.append({
                "number": int(step),
                "frequency": float(frequency or 0.0),
                "period": float(period or 0.0),
                "massPercent": [float(mx or 0.0), float(my or 0.0), float(mz or 0.0)],
                "displacements": _round(node_values),
                "quadDisplacements": _encode_float32(quad_values),
            })
        if modes:
            modal.append({"name": names.get(key, f"Modal {key}"), "modes": modes})
    return modal


def _contours(model, snapshot, step: int, model_sha: str, analysis_name: str):
    positions = []
    stresses = []
    forces = []
    areas = []
    movements = []
    phases = []
    sliding_stresses = []
    sliding_out_stresses = []
    sliding_phases = []
    sliding_out_phases = []
    groups = []
    offset = 0
    for key, interface in sorted(model.collections.interfaces.items(), key=lambda pair: int(pair[0])):
        normal, sliding = _interface_values(interface, snapshot)
        cell_positions = _cell_positions(interface.vint3d, int(interface.nrow), int(interface.ncol))
        if len(normal) != int(interface.nrow) * int(interface.ncol):
            raise ValueError(f"Interface {key} has an unexpected transverse spring count.")
        positions.append(cell_positions)
        slide = sliding[0] if sliding else {"stress": 0.0, "phase": "Elastic"}
        slide_out = sliding[1] if len(sliding) > 1 else {"stress": 0.0, "phase": "Elastic"}
        for item in normal:
            stresses.append(item["stress"])
            forces.append(item["force"])
            areas.append(item["area"])
            movements.append(item["displacement"])
            phases.append(PHASE_NAMES.index(item["phase"]) if item["phase"] in PHASE_NAMES else 0)
            sliding_stresses.append(abs(float(slide["stress"])))
            sliding_out_stresses.append(abs(float(slide_out["stress"])))
            sliding_phases.append(PHASE_NAMES.index(slide["phase"]) if slide["phase"] in PHASE_NAMES else 0)
            sliding_out_phases.append(
                PHASE_NAMES.index(slide_out["phase"]) if slide_out["phase"] in PHASE_NAMES else 0
            )
        groups.append({
            "key": int(key),
            "start": offset,
            "count": len(normal),
            "restrained": bool(interface.interfaccia_vincolata_computed()),
            "nrow": int(interface.nrow),
            "ncol": int(interface.ncol),
            "corners": [[float(point.x), float(point.y), float(point.z)] for point in interface.vint3d],
            "origin": [float(interface.reference_origin.x), float(interface.reference_origin.y),
                       float(interface.reference_origin.z)],
            "e1": [float(value) for value in interface.reference_e1],
            "e3": [float(value) for value in interface.reference_e3],
            "parents": [int(interface.parent_element_key1), int(interface.parent_element_key2)],
            "parentTypes": [str(interface.parent_type_element1), str(interface.parent_type_element2)],
        })
        offset += len(normal)
    return {
        "analysis": analysis_name,
        "step": int(step),
        "modelSha256": model_sha,
        "encoding": "base64-little-endian",
        "stressUnit": "MPa",
        "strainUnit": "cm",
        "strainAvailable": True,
        "cellCount": offset,
        "groups": groups,
        "phaseNames": PHASE_NAMES,
        "positions": _encode_float32(np.concatenate(positions).reshape(-1)),
        "stress": _encode_float32(stresses),
        "force": _encode_float32(forces),
        "area": _encode_float32(areas),
        "displacement": _encode_float32(movements),
        "strain": _encode_float32(movements),
        "phase": base64.b64encode(np.asarray(phases, dtype="u1").tobytes()).decode("ascii"),
        "slidingStress": _encode_float32(sliding_stresses),
        "slidingOutOfPlaneStress": _encode_float32(sliding_out_stresses),
        "slidingPhase": base64.b64encode(np.asarray(sliding_phases, dtype="u1").tobytes()).decode("ascii"),
        "slidingOutOfPlanePhase": base64.b64encode(np.asarray(sliding_out_phases, dtype="u1").tobytes()).decode("ascii"),
    }


def _interface_detail(model, snapshot, interface_key: int, resultants, step: int, model_sha: str, analysis_name: str):
    interface = model.collections.interfaces.get(int(interface_key))
    if interface is None:
        raise ValueError(f"Interface {interface_key} is not present in the model.")
    normal, sliding = _interface_values(interface, snapshot)
    resultants = [float(round(value, 6)) for value in resultants]
    e1 = np.asarray(interface.reference_e1, dtype=float)
    e3 = np.asarray(interface.reference_e3, dtype=float)
    e2 = np.cross(e3, e1)
    norm = float(np.linalg.norm(e2))
    e2 = e2 / norm if norm > 1e-12 else np.zeros(3)
    return {
        "key": int(interface_key),
        "analysis": analysis_name,
        "modelSha256": model_sha,
        "step": int(step),
        "geometry": {
            "parent_element_key1": int(interface.parent_element_key1),
            "parent_element_key2": int(interface.parent_element_key2),
            "parent_type_element1": str(interface.parent_type_element1),
            "parent_type_element2": str(interface.parent_type_element2),
            "length": float(interface.length),
            "nrow": int(interface.nrow),
            "ncol": int(interface.ncol),
            "nspring": int(interface.nspring),
            "reference_e1": [float(value) for value in e1],
            "reference_e2": [float(value) for value in e2],
            "reference_e3": [float(value) for value in e3],
            "reference_origin": [float(interface.reference_origin.x), float(interface.reference_origin.y),
                                 float(interface.reference_origin.z)],
            "vint2d": [[float(point.x), float(point.y)] for point in interface.vint2d],
            "vint3d": [[float(point.x), float(point.y), float(point.z)] for point in interface.vint3d],
            "material_key": int(getattr(interface, "material_key", 0) or 0),
        },
        "forces": resultants[:3],
        "moments": resultants[3:],
        "localForces": None,
        "normal": normal,
        "sliding": sliding,
    }


def _field_descriptors(step: int, source: str):
    """Return the ordered C# field menu without computing any values."""
    from result_fields import FIELD_DEFS, sorted_definitions
    return [
        {
            "id": field_id,
            **FIELD_DEFS[field_id],
            "step": int(step),
            "source": source,
            "available": True,
            "partial": False,
        }
        for field_id in sorted_definitions()
    ]


def project_csharp(hrx_path: str | Path, results_path: str | Path,
                   analysis_name: str | None = None, include_stress_fields: bool = True):
    model, viewer, digest = _cached_models(hrx_path)
    results_path = Path(results_path)
    if not results_path.is_file():
        raise ValueError(f"C# results file not found: {results_path}")
    conn = _connect(results_path)
    try:
        catalog = _static_catalog(conn, model)
        name = _resolve_static(catalog, analysis_name)
        analysis_key = _analysis_key(model, name)
        combination = _combination(conn, analysis_key)
        steps = _steps(conn, analysis_key, combination)
        quad_states = _read_quad_states(conn, analysis_key, combination)
        interface_states = _read_interface_states(conn, analysis_key, combination)
        reactions = _read_reaction_states(conn, analysis_key, combination)
        model_points = _read_model_points(conn, analysis_key, combination)
        final_step = steps[-1]
        snapshot = _read_spring_states(conn, analysis_key, combination, final_step)
        mesh, quad_keys, node_keys = _mesh(model, viewer)
        rel, corr2, corr3, connected = _recovery_data(model, quad_keys, node_keys)
        vertex = (rel, corr2, corr3)
        records, interface_order = _step_records(
            model, quad_keys, node_keys, *vertex, connected,
            quad_states, interface_states, reactions, model_points,
        )
        # The step helper needs the resolved analysis for load-factor reconstruction.
        analysis = model.collections.analyses[analysis_key]
        for record in records:
            record["loadFactor"] = _load_multiplier(analysis, record["step"])
        final_resultants = interface_states.get(final_step, {})
        interfaces = [
            _interface_summary(model.collections.interfaces[key], final_resultants.get(key, (0.0,) * 6), snapshot)
            for key in interface_order
        ]
        if include_stress_fields:
            stress_fields, final_stress = _stress_fields(
                model, snapshot, final_step, mesh, final_resultants
            )
        else:
            stress_fields = _field_descriptors(final_step, "C# native .Results")
            final_stress = None
        modal = _modal_results(conn, model, {
            "vertex": vertex,
            "connected": connected,
            "node_keys": node_keys,
        })
    finally:
        conn.close()

    title = f"{Path(hrx_path).stem} · C# Results"
    return {
        "schemaVersion": 3,
        "sourceSchema": "csharp-results",
        "modelSha256": digest,
        "title": title,
        "name": Path(hrx_path).name,
        "sourceUnits": SOURCE_UNITS,
        "units": VIEWER_UNITS,
        "mesh": mesh,
        "analyses": [{
            "name": name,
            "outcome": f"C# Results · {len(records)} saved steps",
            "steps": records,
            "diagnostics": {"equilibriumCheckedSteps": 0, "equilibriumFailedSteps": 0},
            "interfaces": interfaces,
            "interfaceOrder": [int(key) for key in interface_order],
            "finalStress": final_stress,
            "stressFields": stress_fields,
            "curveOnly": False,
        }],
        "analysisCatalog": catalog,
        "defaultAnalysis": name,
        "modal": modal,
    }


def project_csharp_fields(hrx_path: str | Path, results_path: str | Path,
                          analysis_name: str | None = None, step: int | None = None):
    """Project the Quad stress fields for one saved C# step.

    The native `.Results` database stores per-step spring states. This endpoint
    keeps the expensive/specialized texture projection out of the main result
    payload while still allowing the browser to colour a non-final step.
    """
    model, viewer, digest = _cached_models(hrx_path)
    results_path = Path(results_path)
    if not results_path.is_file():
        raise ValueError(f"C# results file not found: {results_path}")
    conn = _connect(results_path)
    try:
        catalog = _static_catalog(conn, model)
        name = _resolve_static(catalog, analysis_name)
        analysis_key = _analysis_key(model, name)
        combination = _combination(conn, analysis_key)
        steps = _steps(conn, analysis_key, combination)
        if not steps:
            raise ValueError("The selected C# analysis has no saved steps.")
        selected = int(steps[-1] if step is None else step)
        if selected not in steps:
            raise ValueError(f"Step {selected} is not saved for this analysis.")
        snapshot = _read_spring_states(conn, analysis_key, combination, selected)
        interface_resultants = _read_interface_states(conn, analysis_key, combination).get(selected, {})
        mesh, _quad_keys, _node_keys = _mesh(model, viewer)
        fields, final_stress = _stress_fields(
            model, snapshot, selected, mesh, interface_resultants
        )
        return {
            "sourceId": "benchmark",
            "analysis": name,
            "step": selected,
            "modelSha256": digest,
            "stressFields": fields,
            "finalStress": final_stress,
        }
    finally:
        conn.close()


def project_contours_csharp(hrx_path: str | Path, results_path: str | Path,
                            analysis_name: str | None = None, step: int | None = None):
    model, _viewer, digest = _cached_models(hrx_path)
    conn = _connect(results_path)
    try:
        catalog = _static_catalog(conn, model)
        name = _resolve_static(catalog, analysis_name)
        analysis_key = _analysis_key(model, name)
        combination = _combination(conn, analysis_key)
        steps = _steps(conn, analysis_key, combination)
        selected = int(steps[-1] if step is None else step)
        if selected not in steps:
            raise ValueError(f"Step {selected} is not saved for this analysis.")
        snapshot = _read_spring_states(conn, analysis_key, combination, selected)
        return _contours(model, snapshot, selected, digest, name)
    finally:
        conn.close()


def project_interface_csharp(hrx_path: str | Path, results_path: str | Path,
                             analysis_name: str | None, key: int, step: int | None = None):
    model, _viewer, digest = _cached_models(hrx_path)
    conn = _connect(results_path)
    try:
        catalog = _static_catalog(conn, model)
        name = _resolve_static(catalog, analysis_name)
        analysis_key = _analysis_key(model, name)
        combination = _combination(conn, analysis_key)
        steps = _steps(conn, analysis_key, combination)
        selected = int(steps[-1] if step is None else step)
        if selected not in steps:
            raise ValueError(f"Step {selected} is not saved for this analysis.")
        resultants = _read_interface_states(conn, analysis_key, combination).get(
            selected, {}
        ).get(int(key), (0.0,) * 6)
        snapshot = _read_spring_states(conn, analysis_key, combination, selected)
        return _interface_detail(model, snapshot, int(key), resultants, selected, digest, name)
    finally:
        conn.close()
