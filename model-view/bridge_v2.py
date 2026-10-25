"""Project the native v2.0.0 bridge result bundle for the browser viewer.

The bundle has an aggregate manifest plus one summary JSON and one NPZ field
file per P-Delta case. The viewer consumes one analysis at a time; the
aggregate manifest supplies the analysis catalog and the case files supply the
mesh, per-step fields and final spring state.
"""
from pathlib import Path
import base64
import hashlib
import json

import numpy as np

from hrx_model import parse_hrx

PHASE_NAMES = [
    "Elastic", "Plastic_t", "Plastic_c", "Unload_t", "Unload_c",
    "Reload_t", "Reload_c", "Rupture", "RuptureTraz", "RuptureComp", "Slip",
]
NATIVE_UNITS = {
    "length": "cm", "displacement": "cm", "force": "kN",
    "moment": "kN*cm", "stress": "MPa", "rotation": "rad",
}
VIEWER_UNITS = {
    "length": "cm", "force": "kN", "moment": "kN·cm",
    "stress": "MPa", "energy": "kN·cm",
}


def is_bridge_v2(raw):
    return raw.get("schema_version") == "2.0.0" and "baseline_case" in raw


def load_json(path):
    return json.loads(Path(path).read_text())


def _round(values, digits=6):
    return np.round(np.asarray(values, dtype=np.float64), digits).tolist()


def _phase_counts(codes):
    counts = {}
    for code in np.asarray(codes, dtype=np.int16).ravel():
        name = PHASE_NAMES[int(code)] if 0 <= int(code) < len(PHASE_NAMES) else "Unknown"
        counts[name] = counts.get(name, 0) + 1
    return counts


def _phase_names(codes):
    used = sorted({int(c) for c in np.asarray(codes).ravel()})
    return [PHASE_NAMES[c] if 0 <= c < len(PHASE_NAMES) else "Unknown" for c in used], used


def _validate_manifest(raw, hrx_path=None):
    if not is_bridge_v2(raw):
        raise ValueError("Expected a bridge result schema 2.0.0 aggregate.")
    if raw.get("units") != NATIVE_UNITS:
        raise ValueError("Unsupported or missing bridge result units; expected cm/kN/kN*cm/MPa/rad.")
    model = raw.get("metadata", {}).get("models", {}).get("P_Delta", {})
    digest = str(model.get("sha256", "")).lower()
    if len(digest) != 64:
        raise ValueError("Missing bridge result model SHA-256.")
    if hrx_path and Path(hrx_path).is_file():
        actual = hashlib.sha256(Path(hrx_path).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError("Bridge result model SHA-256 does not match the supplied HRX.")


def _case_entries(raw):
    files = raw.get("files", {})
    cases = raw.get("cases", {})
    entries = []
    for case_id, case in cases.items():
        entry = files.get(case_id) or {}
        summary_path = entry.get("summary")
        fields_path = entry.get("fields")
        if not summary_path or not fields_path:
            continue
        entries.append({
            "case_id": case_id,
            "summary": summary_path,
            "fields": fields_path,
            "curve_only": bool(case.get("curve_only", False)),
        })
    return entries


def _summary_for(entry, output_path):
    return load_json(Path(output_path).parent / entry["summary"])


def _fields_for(entry, output_path):
    return np.load(Path(output_path).parent / entry["fields"], allow_pickle=False)


def _catalog(entries, output_path):
    catalog = []
    for entry in entries:
        if entry["curve_only"]:
            continue
        summary = _summary_for(entry, output_path)
        meta = summary["metadata"]
        name = meta.get("analysis_name", entry["case_id"])
        load_case = meta.get("load_case", meta.get("analysis_name", entry["case_id"]))
        formulation = meta.get("formulation", "P_Delta")
        catalog.append({
            "name": name,
            "label": f"{formulation} · {load_case}",
            "caseId": entry["case_id"],
            "steps": summary.get("metrics", {}).get("total_steps", len(summary.get("curve", {}).get("step", []))),
        })
    return catalog


def _resolve_entry(entries, output_path, analysis_name):
    if not entries:
        raise ValueError("The bridge bundle contains no field-backed analyses.")
    if analysis_name:
        for entry in entries:
            summary = _summary_for(entry, output_path)
            meta = summary["metadata"]
            if analysis_name in (entry["case_id"], meta.get("analysis_name"), meta.get("load_case")):
                return entry, summary
    # Prefer the previous viewer default, then the last non-baseline case.
    for entry in entries:
        summary = _summary_for(entry, output_path)
        if summary["metadata"].get("analysis_name") == "Pushover_Span2_Quarter":
            return entry, summary
    non_baseline = [e for e in entries if e["case_id"] != "P_Delta_Vert"]
    entry = (non_baseline or entries)[-1]
    return entry, _summary_for(entry, output_path)


def _hrx_geometry(hrx_path):
    model = parse_hrx(Path(hrx_path).read_bytes(), Path(hrx_path).name)
    nodes = {int(n["key"]): [float(x) for x in n["point"]] for n in model["nodes"]}
    quads = {int(q["key"]): q for q in model["quads"]}
    materials = [{"key": str(m["key"]), "name": str(m.get("name", m["key"])),
                  "color": m.get("color", "#6fb7ff")} for m in model["materials"]]
    return model, nodes, quads, materials


def _mesh(hrx_path, z):
    model, hrx_nodes, hrx_quads, materials = _hrx_geometry(hrx_path)
    node_keys = z["mesh/node_keys"].astype(int)
    node_xyz = z["mesh/nodes_xyz"].astype(float)
    quad_keys = z["mesh/quad_keys"].astype(int)
    quad_conn = z["mesh/quad_conn"].astype(int)
    quad_materials = z["mesh/quad_material_keys"].astype(int)
    quad_thickness = z["mesh/quad_thickness"].astype(float)
    interfaces = {}
    for key, nodes, length, points in zip(
            z["mesh/interface_keys"].astype(int),
            z["mesh/interface_node_keys"].astype(int),
            z["mesh/interface_length"].astype(float),
            z["mesh/interface_node_xyz"].astype(float)):
        interfaces[str(int(key))] = {
            "nodeKeys": [str(int(nodes[0])), str(int(nodes[1]))],
            "length": float(length),
            "points": [[float(v) for v in points[0]], [float(v) for v in points[1]]],
        }
    thrust_pairs = []
    faces = z["mesh/quad_interface_keys"]
    offsets = z["mesh/quad_face_interface_offsets"]
    for i, (quad, face_keys, material) in enumerate(zip(quad_keys, faces, quad_materials)):
        counts = [int(offsets[i * 6 + f + 1] - offsets[i * 6 + f]) for f in range(6)]
        for first, second in ((0, 2), (1, 3)):
            if face_keys[first] > 0 and face_keys[second] > 0 and counts[first] == 1 and counts[second] == 1:
                thrust_pairs.append([int(quad), int(face_keys[first]), int(face_keys[second]), str(int(material))])
    nodes_out = [
        {"key": str(int(key)), "name": str(int(key)), "point": [float(v) for v in xyz]}
        for key, xyz in zip(node_keys, node_xyz)
    ]
    # HRX node records carry names separately; recover them without changing order.
    names = {int(n["key"]): str(n.get("name", n["key"])) for n in model["nodes"]}
    for item in nodes_out:
        item["name"] = names.get(int(item["key"]), item["key"])
    quads_out = []
    for key, conn, material, thickness in zip(quad_keys, quad_conn, quad_materials, quad_thickness):
        hrx = hrx_quads.get(int(key), {})
        quads_out.append({
            "key": str(int(key)),
            "name": str(hrx.get("name", key)),
            "nodeKeys": [str(int(n)) for n in conn],
            "materialKey": str(int(material)),
            "thicknesses": [float(v) for v in thickness],
            "normals": hrx.get("normals", [[0, 0, 1]] * 4),
        })
    if len(nodes_out) != 3216 or len(quads_out) != 2520 or len(interfaces) != 6762:
        raise ValueError("Bridge mesh counts do not match the expected 3216/2520/6762 topology.")
    if len(thrust_pairs) != 3752:
        raise ValueError(f"Bridge thrust topology has {len(thrust_pairs)} pairs; expected 3752.")
    return {
        "name": Path(hrx_path).name,
        "nodes": nodes_out,
        "quads": quads_out,
        "materials": materials,
        "thrustPairs": thrust_pairs,
        "interfaces": interfaces,
    }


def _encode_float32(values):
    arr = np.ascontiguousarray(values, dtype="<f4")
    if not np.isfinite(arr).all():
        raise ValueError("Nonfinite bridge field array.")
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _interfaces_summary(z, interface_order):
    forces = z["fields/interface_resultants"][-1].astype(float)
    moments = z["fields/interface_moments"][-1].astype(float)
    keys = z["mesh/interface_keys"].astype(int)
    index = {int(key): i for i, key in enumerate(keys)}
    parents = z["mesh/interface_parents"].astype(int)
    materials = z["mesh/interface_material_keys"].astype(int)
    restrained = z["mesh/interface_restrained"].astype(int)
    offsets = z["springs/transverse_offsets"].astype(int)
    stress = z["springs/transverse_stress"].astype(float)
    phase = z["springs/transverse_phase"].astype(np.int16)
    out = []
    for key in interface_order:
        i = index[int(key)]
        start, stop = int(offsets[i]), int(offsets[i + 1])
        values = stress[start:stop]
        out.append({
            "key": int(key),
            "parents": [int(parents[i, 0]), int(parents[i, 1])],
            "parentTypes": ["Quad", "Quad"],
            "restrained": bool(restrained[i]),
            "materialKey": str(int(materials[i])),
            "forces": _round(forces[i]),
            "minStress": float(np.min(values)) if values.size else None,
            "moments": _round(moments[i]),
            "maxStress": float(np.max(values)) if values.size else None,
            "phases": _phase_counts(phase[start:stop]),
        })
    return out


def _von_mises_field(z):
    """Interface-spring stress tensor -> global tensor -> Von Mises per Quad corner.

    C# ``ComputationalElement.GetTensorPrepare`` builds an interface tensor with
    M22 = normal spring stress, M12 = in-plane sliding stress and
    M23 = out-of-plane sliding stress, transforms it to global axes and
    interpolates it over the Quad face. The v2 bundle has the final spring
    snapshot only, so this is a final-step map. At each contact-line endpoint
    the out-of-plane spring is selected by the C# left/right half rule.
    """
    keys = z["mesh/interface_keys"].astype(int)
    index = {int(key): i for i, key in enumerate(keys)}
    node_keys = z["mesh/interface_node_keys"].astype(int)
    node_xyz = z["mesh/interface_node_xyz"].astype(float)
    e1s = z["mesh/interface_e1"].astype(float)
    e3s = z["mesh/interface_e3"].astype(float)
    rows = z["mesh/interface_nrow"].astype(int)
    cols = z["mesh/interface_ncol"].astype(int)
    t_offsets = z["springs/transverse_offsets"].astype(int)
    t_stress = z["springs/transverse_stress"].astype(float)
    t_valid = z["springs/transverse_stress_valid"].astype(bool)
    s_offsets = z["springs/sliding_offsets"].astype(int)
    s_stress = z["springs/sliding_stress"].astype(float)

    def tensor_at(i, endpoint):
        start, stop = int(t_offsets[i]), int(t_offsets[i + 1])
        nrow, ncol = int(rows[i]), int(cols[i])
        if stop - start != nrow * ncol:
            return None
        normal = t_stress[start:stop].reshape(nrow, ncol)
        valid = t_valid[start:stop].reshape(nrow, ncol)
        column = 0 if endpoint == 0 else ncol - 1
        values = normal[:, column][valid[:, column]]
        if not values.size:
            return None
        sigma = float(values.mean())
        sstart = int(s_offsets[i])
        if s_offsets[i + 1] - sstart < 3:
            return None
        tau_in = float(s_stress[sstart])
        tau_out = float(s_stress[sstart + 1 + endpoint])
        e1 = e1s[i]
        e3 = e3s[i]
        e2 = np.cross(e3, e1)
        norm = float(np.linalg.norm(e2))
        if norm <= 1e-12:
            return None
        e2 = e2 / norm
        local = np.array([
            [0.0, tau_in, 0.0],
            [tau_in, sigma, tau_out],
            [0.0, tau_out, 0.0],
        ], dtype=float)
        rotation = np.column_stack([e1, e2, e3])
        return rotation @ local @ rotation.T

    def von_mises(tensor):
        if tensor is None:
            return 0.0
        s11, s22, s33 = tensor[0, 0], tensor[1, 1], tensor[2, 2]
        s12, s23, s13 = tensor[0, 1], tensor[1, 2], tensor[0, 2]
        return float(np.sqrt(max(0.0, s11 * s11 + s22 * s22 + s33 * s33
                                 - s11 * s22 - s11 * s33 - s22 * s33
                                 + 3.0 * (s12 * s12 + s23 * s23 + s13 * s13))))

    interface_tensors = []
    for i in range(len(keys)):
        interface_tensors.append((tensor_at(i, 0), tensor_at(i, 1)))

    quad_keys = z["mesh/quad_keys"].astype(int)
    conn = z["mesh/quad_conn"].astype(int)
    face_offsets = z["mesh/quad_face_interface_offsets"].astype(int)
    face_keys = z["mesh/quad_face_interface_keys"].astype(int)
    quad_corners = []
    mesh_positions = {int(key): xyz for key, xyz in zip(z["mesh/node_keys"].astype(int), z["mesh/nodes_xyz"].astype(float))}
    for qi, quad_key in enumerate(quad_keys):
        qpoints = np.array([mesh_positions[int(nk)] for nk in conn[qi]], dtype=float)
        corner_tensors = [[], [], [], []]
        for side in range(4):
            start = int(face_offsets[qi * 6 + side])
            stop = int(face_offsets[qi * 6 + side + 1])
            first, last = side, (side + 1) % 4
            for raw_key in face_keys[start:stop]:
                key = int(raw_key)
                if key not in index:
                    continue
                i = index[key]
                t0, t1 = interface_tensors[i]
                if t0 is None and t1 is None:
                    continue
                p0, p1 = node_xyz[i, 0], node_xyz[i, 1]
                forward = np.linalg.norm(p0 - qpoints[first]) + np.linalg.norm(p1 - qpoints[last])
                reverse = np.linalg.norm(p0 - qpoints[last]) + np.linalg.norm(p1 - qpoints[first])
                if forward <= reverse:
                    if t0 is not None: corner_tensors[first].append(t0)
                    if t1 is not None: corner_tensors[last].append(t1)
                else:
                    if t1 is not None: corner_tensors[first].append(t1)
                    if t0 is not None: corner_tensors[last].append(t0)
        corners = []
        all_tensors = [tensor for tensors in corner_tensors for tensor in tensors]
        quad_tensor = np.mean(all_tensors, axis=0) if all_tensors else None
        for corner in range(4):
            adjacent = corner_tensors[corner]
            tensor = np.mean(adjacent, axis=0) if adjacent else quad_tensor
            corners.append(von_mises(tensor) if tensor is not None else 0.0)
        quad_corners.append(corners)
    flat = [value for corners in quad_corners for value in corners]
    finite = [value for value in flat if np.isfinite(value)]
    minimum = float(min(finite)) if finite else 0.0
    maximum = float(max(finite)) if finite else 0.0
    return {
        "quadCornerValues": [[round(float(v), 6) for v in corners] for corners in quad_corners],
        "min": minimum,
        "max": maximum,
        "unit": "MPa",
        "step": int(z["steps/step_index"][-1]),
        "source": "interface spring stresses (normal + sliding)",
    }


def _analysis(entry, summary, mesh, z):
    interface_order = sorted(z["mesh/interface_keys"].astype(int).tolist())
    steps_index = z["steps/step_index"].astype(int)
    node_disp = z["fields/node_displacements"].astype(float)
    quad_disp = z["fields/quad_displacements"].astype(np.float32)
    resultants = np.concatenate(
        [z["fields/interface_resultants"].astype(float), z["fields/interface_moments"].astype(float)],
        axis=2,
    )
    reactions = z["steps/reactions"].astype(float)
    load_factor = z["steps/load_factor"].astype(float)
    curve = summary["curve"]
    steps = []
    for i, step_index in enumerate(steps_index):
        values = node_disp[i]
        steps.append({
            "step": int(step_index),
            "status": "INITIAL" if i == 0 else "OK",
            "loadFactor": float(load_factor[i]),
            "controlDisplacement": float(curve["displacement_cm"][i]),
            "displacements": _round(values),
            "quadDisplacements": _encode_float32(quad_disp[i]),
            "maxDisplacement": float(np.max(np.linalg.norm(values, axis=1))),
            "appliedVerticalForce": float(curve["total_force_kN"][i]),
            "reactions": _round(reactions[i, :3]),
            "elasticEnergy": curve["elastic_energy"][i],
            "dissipatedEnergy": curve["dissipated_energy"][i],
            "interfaceResultants": _round(resultants[i]),
        })
    return {
        "name": summary["metadata"].get("analysis_name", entry["case_id"]),
        "caseId": entry["case_id"],
        "outcome": summary.get("metrics", {}).get("outcome", "completed"),
        "steps": steps,
        "diagnostics": {"equilibriumCheckedSteps": 0, "equilibriumFailedSteps": 0},
        "interfaces": _interfaces_summary(z, interface_order),
        "interfaceOrder": interface_order,
        "finalStress": _von_mises_field(z),
        "curveOnly": False,
    }


def _catalog_and_case(raw, output_path, analysis_name):
    entries = _case_entries(raw)
    catalog = _catalog(entries, output_path)
    entry, summary = _resolve_entry(entries, output_path, analysis_name)
    return catalog, entry, summary


def project_bridge(hrx_path, output_path, analysis_name=None):
    raw = load_json(output_path)
    _validate_manifest(raw, hrx_path)
    catalog, entry, summary = _catalog_and_case(raw, output_path, analysis_name)
    with _fields_for(entry, output_path) as z:
        mesh = _mesh(hrx_path, z)
        analysis = _analysis(entry, summary, mesh, z)
    meta = summary["metadata"]
    return {
        "schemaVersion": 3,
        "sourceSchema": raw.get("schema_version"),
        "modelSha256": meta.get("model_sha256"),
        "title": raw.get("metadata", {}).get("title", mesh["name"]),
        "scourStage": meta.get("scour_stage"),
        "formulation": meta.get("formulation"),
        "sourceUnits": raw.get("units"),
        "name": mesh["name"],
        "units": VIEWER_UNITS,
        "mesh": mesh,
        "analyses": [analysis],
        "analysisCatalog": catalog,
        "defaultAnalysis": analysis["name"],
        "modal": [],
    }


def _resolve_case(raw, output_path, analysis_name):
    entries = _case_entries(raw)
    return _resolve_entry(entries, output_path, analysis_name)


def _cell_weights(nrow, ncol):
    """Bilinear weights for each cell corner, matching C# GetAreaTrasvSpring."""
    rows = []
    for row in range(nrow):
        for col in range(ncol):
            for corner in range(4):
                c = col + (1 if corner in (1, 2) else 0)
                r = row + (1 if corner in (2, 3) else 0)
                u = 2.0 * c / ncol - 1.0
                v = 2.0 * r / nrow - 1.0
                rows.append([
                    (1 - u) * (1 - v) / 4,
                    (1 + u) * (1 - v) / 4,
                    (1 + u) * (1 + v) / 4,
                    (1 - u) * (1 + v) / 4,
                ])
    return np.asarray(rows, dtype=np.float64).reshape(nrow * ncol, 4, 4)


def project_contours(output_path, analysis_name):
    raw = load_json(output_path)
    entry, summary = _resolve_case(raw, output_path, analysis_name)
    with _fields_for(entry, output_path) as z:
        keys = z["mesh/interface_keys"].astype(int)
        vint = z["mesh/interface_vint"].astype(np.float32)
        nrow = z["mesh/interface_nrow"].astype(int)
        ncol = z["mesh/interface_ncol"].astype(int)
        offsets = z["springs/transverse_offsets"].astype(int)
        stress = z["springs/transverse_stress"].astype(float)
        force = z["springs/transverse_force"].astype(float)
        area = z["springs/transverse_area"].astype(float)
        phases = z["springs/transverse_phase"].astype(int)
        parents = z["mesh/interface_parents"].astype(int)
        restrained = z["mesh/interface_restrained"].astype(int)
        origins = z["mesh/interface_origin"].astype(float)
        e1s = z["mesh/interface_e1"].astype(float)
        e3s = z["mesh/interface_e3"].astype(float)

        positions = np.empty((int(offsets[-1]), 4, 3), dtype=np.float32)
        groups = []
        cursor = 0
        weight_cache = {}
        for i, key in enumerate(keys):
            rows, cols = int(nrow[i]), int(ncol[i])
            corners = vint[i]
            count = int(offsets[i + 1] - offsets[i])
            if count != rows * cols:
                raise ValueError(f"Interface {int(key)} has inconsistent transverse offsets.")
            weights = weight_cache.get((rows, cols))
            if weights is None:
                weights = _cell_weights(rows, cols)
                weight_cache[(rows, cols)] = weights
            positions[cursor:cursor + count] = np.einsum("ckj,jd->ckd", weights, corners).astype(np.float32)
            groups.append({
                "key": int(key), "start": cursor, "count": count,
                "restrained": bool(restrained[i]), "nrow": rows, "ncol": cols,
                "corners": [[float(v) for v in p] for p in corners],
                "origin": [float(v) for v in origins[i]],
                "e1": [float(v) for v in e1s[i]],
                "e3": [float(v) for v in e3s[i]],
                "parents": [int(parents[i, 0]), int(parents[i, 1])],
                "parentTypes": ["Quad", "Quad"],
            })
            cursor += count
        if cursor != len(stress):
            raise ValueError("Bridge contour offsets do not cover the transverse arrays.")
        phase_names = PHASE_NAMES
        return {
            "analysis": summary["metadata"].get("analysis_name", entry["case_id"]),
            "caseId": entry["case_id"],
            "step": int(z["steps/step_index"][-1]),
            "modelSha256": summary["metadata"].get("model_sha256"),
            "encoding": "base64-little-endian",
            "stressUnit": "MPa",
            "strainUnit": "cm",
            "strainAvailable": False,
            "cellCount": int(offsets[-1]),
            "groups": groups,
            "phaseNames": phase_names,
            "positions": _encode_float32(positions.reshape(-1)),
            "stress": _encode_float32(stress),
            "force": _encode_float32(force),
            "area": _encode_float32(area),
            "displacement": _encode_float32(np.zeros(len(stress), dtype=np.float32)),
            "strain": _encode_float32(np.zeros(len(stress), dtype=np.float32)),
            "phase": base64.b64encode(phases.astype("u1").tobytes()).decode("ascii"),
        }


def project_interface(output_path, analysis_name, key):
    raw = load_json(output_path)
    entry, summary = _resolve_case(raw, output_path, analysis_name)
    key = int(key)
    with _fields_for(entry, output_path) as z:
        keys = z["mesh/interface_keys"].astype(int)
        if key not in keys:
            raise ValueError(f"Interface {key} is not present in the bridge results.")
        i = int(np.where(keys == key)[0][0])
        nrow, ncol = int(z["mesh/interface_nrow"][i]), int(z["mesh/interface_ncol"][i])
        offsets = z["springs/transverse_offsets"].astype(int)
        start, stop = int(offsets[i]), int(offsets[i + 1])
        normal_force = z["springs/transverse_force"].astype(float)
        normal_stress = z["springs/transverse_stress"].astype(float)
        normal_area = z["springs/transverse_area"].astype(float)
        normal_phase = z["springs/transverse_phase"].astype(int)
        sliding_offsets = z["springs/sliding_offsets"].astype(int)
        sliding_start, sliding_stop = int(sliding_offsets[i]), int(sliding_offsets[i + 1])
        sliding_force = z["springs/sliding_force"].astype(float)
        sliding_stress = z["springs/sliding_stress"].astype(float)
        sliding_area = z["springs/sliding_area"].astype(float)
        sliding_phase = z["springs/sliding_phase"].astype(int)
        corners = z["mesh/interface_vint"][i].astype(float)
        origin = z["mesh/interface_origin"][i].astype(float)
        e1 = z["mesh/interface_e1"][i].astype(float)
        e3 = z["mesh/interface_e3"][i].astype(float)
        e2 = np.cross(e3, e1)
        norm = float(np.linalg.norm(e2))
        e2 = e2 / norm if norm > 1e-12 else np.zeros(3)
        vint2d = [[float(np.dot(p - origin, e1)), float(np.dot(p - origin, e3))] for p in corners]
        forces = np.round(z["fields/interface_resultants"][-1, i].astype(float), 6)
        moments = np.round(z["fields/interface_moments"][-1, i].astype(float), 6)
        normal = []
        for idx in range(stop - start):
            code = int(normal_phase[start + idx])
            normal.append({
                "index": idx, "row": idx // ncol, "col": idx % ncol,
                "type": "Spring", "force": float(normal_force[start + idx]),
                "area": float(normal_area[start + idx]),
                "stress": float(normal_stress[start + idx]),
                "displacement": None, "strain": None,
                "phase": PHASE_NAMES[code] if 0 <= code < len(PHASE_NAMES) else "Unknown",
            })
        sliding = []
        for idx in range(sliding_stop - sliding_start):
            code = int(sliding_phase[sliding_start + idx])
            sliding.append({
                "index": idx, "row": None, "col": None,
                "group": "slid" if idx == 0 else "slid_out_plan",
                "type": "Spring", "force": float(sliding_force[sliding_start + idx]),
                "area": float(sliding_area[sliding_start + idx]),
                "stress": float(sliding_stress[sliding_start + idx]),
                "displacement": None, "strain": None,
                "phase": PHASE_NAMES[code] if 0 <= code < len(PHASE_NAMES) else "Unknown",
            })
        return {
            "key": key,
            "analysis": summary["metadata"].get("analysis_name", entry["case_id"]),
            "modelSha256": summary["metadata"].get("model_sha256"),
            "geometry": {
                "parent_element_key1": int(z["mesh/interface_parents"][i, 0]),
                "parent_element_key2": int(z["mesh/interface_parents"][i, 1]),
                "parent_type_element1": "Quad",
                "parent_type_element2": "Quad",
                "length": float(z["mesh/interface_length"][i]),
                "nrow": nrow, "ncol": ncol, "nspring": nrow * ncol,
                "reference_e1": [float(v) for v in e1],
                "reference_e2": [float(v) for v in e2],
                "reference_e3": [float(v) for v in e3],
                "reference_origin": [float(v) for v in origin],
                "vint2d": vint2d,
                "vint3d": [[float(v) for v in p] for p in corners],
                "material_key": int(z["mesh/interface_material_keys"][i]),
            },
            "forces": forces.tolist(),
            "moments": moments.tolist(),
            "localForces": None,
            "normal": normal,
            "sliding": sliding,
        }


def cache_stamp(output_path):
    """Return the mtime/size tuple of the aggregate and every referenced file."""
    output_path = Path(output_path)
    raw = load_json(output_path)
    if not is_bridge_v2(raw):
        return ()
    paths = {output_path}
    for entry in raw.get("files", {}).values():
        for name in entry.values():
            if name:
                paths.add(output_path.parent / name)
    baseline = raw.get("baseline_case", {})
    for name in baseline.values():
        if isinstance(name, str):
            paths.add(output_path.parent / name)
    return tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else (str(path), 0, 0)
        for path in sorted(paths)
    )
