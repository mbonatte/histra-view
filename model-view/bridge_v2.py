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
from result_fields import complete_field_set

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


def _resolve_entry(entries, output_path, analysis_name, default_case=None):
    if not entries:
        raise ValueError("The bridge bundle contains no field-backed analyses.")
    if analysis_name:
        for entry in entries:
            summary = _summary_for(entry, output_path)
            meta = summary["metadata"]
            if analysis_name in (entry["case_id"], meta.get("analysis_name"), meta.get("load_case")):
                return entry, summary
    if default_case:
        for entry in entries:
            summary = _summary_for(entry, output_path)
            meta = summary["metadata"]
            if default_case in (entry["case_id"], meta.get("analysis_name"), meta.get("load_case")):
                return entry, summary
    # Prefer the previous viewer default, then the last non-baseline case.
    for entry in entries:
        summary = _summary_for(entry, output_path)
        if summary["metadata"].get("analysis_name") == "Pushover_Span2_Quarter":
            return entry, summary
    non_baseline = [e for e in entries if e["case_id"] != "P_Delta_Vert"]
    entry = (non_baseline or entries)[-1]
    return entry, _summary_for(entry, output_path)


def _hrx_geometry(hrx_path, hrx_model=None):
    model = hrx_model if hrx_model is not None else parse_hrx(Path(hrx_path).read_bytes(), Path(hrx_path).name)
    nodes = {int(n["key"]): [float(x) for x in n["point"]] for n in model["nodes"]}
    quads = {int(q["key"]): q for q in model["quads"]}
    materials = [{"key": str(m["key"]), "name": str(m.get("name", m["key"])),
                  "color": m.get("color", "#6fb7ff")} for m in model["materials"]]
    return model, nodes, quads, materials


def _mesh(hrx_path, z, hrx_model=None):
    model, hrx_nodes, hrx_quads, materials = _hrx_geometry(hrx_path, hrx_model)
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
    if len(nodes_out) != len(node_keys) or len(quads_out) != len(quad_keys):
        raise ValueError("Bridge mesh projection lost nodes or Quads.")
    if len(interfaces) != len(z["mesh/interface_keys"]):
        raise ValueError("Bridge mesh projection lost interfaces.")
    if not thrust_pairs:
        raise ValueError("Bridge mesh has no opposite-face thrust pairs.")
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


def _stress_fields(z, mesh=None, include_face_grids=True):
    """Build the C# stress maps from the final interface-spring snapshot.

    C# ``ComputationalElement.GetTensorPrepare`` builds an interface tensor with
    M22 = normal spring stress, M12 = in-plane sliding stress and
    M23 = out-of-plane sliding stress, transforms it to global axes and
    evaluates the requested component at the Quad face. The v2 bundle exposes
    only the final spring snapshot, so every field is a final-step map. At each
    contact-line endpoint the out-of-plane spring follows the C# left/right half
    rule.

    The two C# surface paths are represented explicitly: global tensor fields
    use the transformed interface tensor, while local stress maps use the saved
    normal and sliding spring values on the interface edges. Strain and plastic
    strain are not present in the v2 bundle and remain disabled descriptors.
    """
    keys = z["mesh/interface_keys"].astype(int)
    index = {int(key): i for i, key in enumerate(keys)}
    node_keys = z["mesh/interface_node_keys"].astype(int)
    node_xyz = z["mesh/interface_node_xyz"].astype(float)
    e1s = z["mesh/interface_e1"].astype(float)
    e3s = z["mesh/interface_e3"].astype(float)
    origins = z["mesh/interface_origin"].astype(float)
    interface_vint = z["mesh/interface_vint"].astype(float)
    rows = z["mesh/interface_nrow"].astype(int)
    cols = z["mesh/interface_ncol"].astype(int)
    t_offsets = z["springs/transverse_offsets"].astype(int)
    t_stress = z["springs/transverse_stress"].astype(float)
    t_valid = z["springs/transverse_stress_valid"].astype(bool)
    s_offsets = z["springs/sliding_offsets"].astype(int)
    s_stress = z["springs/sliding_stress"].astype(float)

    def endpoint_data(i, endpoint):
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
        return {
            "tensor": rotation @ local @ rotation.T,
            "normal": sigma,
            "inPlane": tau_in,
            "outOfPlane": tau_out,
        }

    interface_endpoints = [
        (endpoint_data(i, 0), endpoint_data(i, 1))
        for i in range(len(keys))
    ]

    quad_keys = z["mesh/quad_keys"].astype(int)
    conn = z["mesh/quad_conn"].astype(int)
    face_offsets = z["mesh/quad_face_interface_offsets"].astype(int)
    face_keys = z["mesh/quad_face_interface_keys"].astype(int)
    mesh_positions = {int(key): xyz for key, xyz in zip(z["mesh/node_keys"].astype(int), z["mesh/nodes_xyz"].astype(float))}
    corner_links = []
    for qi, quad_key in enumerate(quad_keys):
        qpoints = np.array([mesh_positions[int(nk)] for nk in conn[qi]], dtype=float)
        links = [[], [], [], []]
        for side in range(4):
            start = int(face_offsets[qi * 6 + side])
            stop = int(face_offsets[qi * 6 + side + 1])
            first, last = side, (side + 1) % 4
            for raw_key in face_keys[start:stop]:
                key = int(raw_key)
                if key not in index:
                    continue
                i = index[key]
                first_data, last_data = interface_endpoints[i]
                if first_data is None and last_data is None:
                    continue
                p0, p1 = node_xyz[i, 0], node_xyz[i, 1]
                forward = np.linalg.norm(p0 - qpoints[first]) + np.linalg.norm(p1 - qpoints[last])
                reverse = np.linalg.norm(p0 - qpoints[last]) + np.linalg.norm(p1 - qpoints[first])
                if forward <= reverse:
                    if first_data is not None:
                        links[first].append(first_data)
                    if last_data is not None:
                        links[last].append(last_data)
                else:
                    if last_data is not None:
                        links[first].append(last_data)
                    if first_data is not None:
                        links[last].append(first_data)
        corner_links.append(links)

    face_values = {}
    if mesh is not None:
        # C# evaluates a tensor on each of the six physical Quad faces, not
        # only the four side faces. Build corner tensors from the interface
        # spring grids, including the through-thickness faces, and then map
        # them onto the top/bottom/side face corners used by the renderer.
        interface_corner_data = []
        interface_cell_centers = []
        interface_cell_sigma = []
        interface_cell_valid = []
        interface_cell_tau_in = []
        interface_local_vint = []
        lookup = {}
        for i in range(len(keys)):
            start, stop = int(t_offsets[i]), int(t_offsets[i + 1])
            nrow, ncol = int(rows[i]), int(cols[i])
            if stop - start != nrow * ncol:
                interface_corner_data.append([None] * 4)
                interface_cell_centers.append(np.empty((0, 3)))
                interface_cell_sigma.append(np.empty(0))
                interface_cell_valid.append(np.empty(0, dtype=bool))
                interface_cell_tau_in.append(np.empty(0))
                interface_local_vint.append(np.empty((0, 2)))
                continue
            normal = t_stress[start:stop].reshape(nrow, ncol)
            valid = t_valid[start:stop].reshape(nrow, ncol)
            sstart = int(s_offsets[i])
            if s_offsets[i + 1] - sstart < 3:
                interface_corner_data.append([None] * 4)
                interface_cell_centers.append(np.empty((0, 3)))
                interface_cell_sigma.append(np.empty(0))
                interface_cell_valid.append(np.empty(0, dtype=bool))
                interface_cell_tau_in.append(np.empty(0))
                interface_local_vint.append(np.empty((0, 2)))
                continue
            tau_in = float(s_stress[sstart])
            e1 = e1s[i]
            e3 = e3s[i]
            e2 = np.cross(e3, e1)
            norm = float(np.linalg.norm(e2))
            if norm <= 1e-12:
                interface_corner_data.append([None] * 4)
                interface_cell_centers.append(np.empty((0, 3)))
                interface_cell_sigma.append(np.empty(0))
                interface_cell_valid.append(np.empty(0, dtype=bool))
                interface_cell_tau_in.append(np.empty(0))
                interface_local_vint.append(np.empty((0, 2)))
                continue
            e2 = e2 / norm
            rotation = np.column_stack([e1, e2, e3])
            entries = []
            for corner in range(4):
                row = 0 if corner in (0, 1) else nrow - 1
                col = 0 if corner in (0, 3) else ncol - 1
                if valid[row, col]:
                    sigma = float(normal[row, col])
                else:
                    samples = normal[:, col][valid[:, col]]
                    sigma = float(samples.mean()) if samples.size else float(normal[row, col])
                tau_out = float(s_stress[sstart + 1 + (0 if corner in (0, 3) else 1)])
                local = np.array([
                    [0.0, tau_in, 0.0],
                    [tau_in, sigma, tau_out],
                    [0.0, tau_out, 0.0],
                ], dtype=float)
                entries.append({
                    "tensor": rotation @ local @ rotation.T,
                    "normalStress": sigma,
                    "inPlaneStress": tau_in,
                    "outOfPlaneStress": tau_out,
                    "e1": e1,
                    "e3": e3,
                    "e2": e2,
                })
            interface_corner_data.append(entries)
            u = (np.arange(ncol) + 0.5) * 2.0 / ncol - 1.0
            v = (np.arange(nrow) + 0.5) * 2.0 / nrow - 1.0
            uu, vv = np.meshgrid(u, v)
            vint = interface_vint[i]
            centers = 0.25 * (
                (1 - uu)[..., None] * (1 - vv)[..., None] * vint[0]
                + (1 + uu)[..., None] * (1 - vv)[..., None] * vint[1]
                + (1 + uu)[..., None] * (1 + vv)[..., None] * vint[2]
                + (1 - uu)[..., None] * (1 + vv)[..., None] * vint[3]
            )
            interface_cell_centers.append(centers.reshape(-1, 3))
            origin = origins[i]
            interface_local_vint.append(np.column_stack([
                (vint - origin) @ e1s[i],
                (vint - origin) @ e3s[i],
            ]))
            interface_cell_sigma.append(normal.reshape(-1))
            interface_cell_valid.append(valid.reshape(-1))
            interface_cell_tau_in.append(np.full(nrow * ncol, tau_in))
            for corner, point in enumerate(interface_vint[i]):
                lookup.setdefault(tuple(round(float(v), 3) for v in point), []).append((i, corner))

        mesh_nodes = {int(node["key"]): np.asarray(node["point"], dtype=float) for node in mesh["nodes"]}
        mesh_quads = {int(quad["key"]): quad for quad in mesh["quads"]}
        quad_face_sets = []
        for qi in range(len(quad_keys)):
            quad_face_sets.append([
                {int(face_keys[offset]) for offset in range(
                    int(face_offsets[qi * 6 + face]),
                    int(face_offsets[qi * 6 + face + 1]),
                )}
                for face in range(6)
            ])
        face_tensors = []
        quad_face_grids = []
        face_scalars = {"normalStress": [], "inPlaneStress": [], "outOfPlaneStress": []}
        face_refs = (
            (("t", 0), ("t", 1), ("t", 2), ("t", 3)),
            (("b", 0), ("b", 1), ("b", 2), ("b", 3)),
            (("t", 0), ("t", 1), ("b", 1), ("b", 0)),
            (("t", 1), ("t", 2), ("b", 2), ("b", 1)),
            (("t", 2), ("t", 3), ("b", 3), ("b", 2)),
            (("t", 3), ("t", 0), ("b", 0), ("b", 3)),
        )
        # The edge faces and opposite face are the C# mappings used by
        # Quad.GetColorMapValues: top uses faces 0..3 and Interface5=5,
        # bottom uses 0..3 and 4, and the four side faces use the remaining
        # edge/through-thickness combinations.
        face_edge_faces = (
            (0, 1, 2, 3), (0, 1, 2, 3),
            (5, 1, 4, 3), (5, 2, 4, 0),
            (5, 3, 4, 1), (5, 0, 4, 2),
        )
        face_opposite = (5, 4, 0, 1, 2, 3)
        corner_edges = ((3, 0), (0, 1), (1, 2), (2, 3))

        def inverse_bilinear(vertices, point):
            u = 0.0
            v = 0.0
            for _ in range(10):
                a = (1 - u) * (1 - v) * 0.25
                b = (1 + u) * (1 - v) * 0.25
                c = (1 + u) * (1 + v) * 0.25
                d = (1 - u) * (1 + v) * 0.25
                value = a * vertices[0] + b * vertices[1] + c * vertices[2] + d * vertices[3]
                residual = point - value
                du = 0.25 * (-(1 - v) * vertices[0] + (1 - v) * vertices[1]
                             + (1 + v) * vertices[2] - (1 + v) * vertices[3])
                dv = 0.25 * (-(1 - u) * vertices[0] - (1 + u) * vertices[1]
                             + (1 + u) * vertices[2] + (1 - u) * vertices[3])
                det = du[0] * dv[1] - du[1] * dv[0]
                if abs(det) <= 1e-14:
                    break
                delta_u = (residual[0] * dv[1] - residual[1] * dv[0]) / det
                delta_v = (du[0] * residual[1] - du[1] * residual[0]) / det
                u += delta_u
                v += delta_v
                if abs(delta_u) + abs(delta_v) < 1e-10:
                    break
            return u, v

        def sample_interface(i, point, sign=1.0):
            centers = interface_cell_centers[i]
            if centers.size == 0:
                return None
            e1 = e1s[i]
            e3 = e3s[i]
            e2 = np.cross(e3, e1)
            norm = float(np.linalg.norm(e2))
            if norm <= 1e-12:
                return None
            local_point = np.array([
                float((point - origins[i]) @ e1),
                float((point - origins[i]) @ e3),
            ])
            u, v = inverse_bilinear(interface_local_vint[i], local_point)
            if abs(u) > 1.08 or abs(v) > 1.08:
                return None
            column = int(np.floor((u + 1.0) * 0.5 * int(cols[i])))
            row = int(np.floor((v + 1.0) * 0.5 * int(rows[i])))
            column = min(max(column, 0), int(cols[i]) - 1)
            row = min(max(row, 0), int(rows[i]) - 1)
            index = row * int(cols[i]) + column
            if not interface_cell_valid[i][index]:
                sigma = 0.0
            else:
                sigma = float(interface_cell_sigma[i][index])
            tau_in = float(interface_cell_tau_in[i][index])
            sstart = int(s_offsets[i])
            tau_out = sign * float(s_stress[sstart + 1 + (0 if u < 0.0 else 1)])
            e2 = e2 / norm
            local = np.array([
                [0.0, tau_in, 0.0],
                [tau_in, sigma, tau_out],
                [0.0, tau_out, 0.0],
            ], dtype=float)
            rotation = np.column_stack([e1, e2, e3])
            return {
                "tensor": rotation @ local @ rotation.T,
                "normalStress": sigma,
                "inPlaneStress": tau_in,
                "outOfPlaneStress": tau_out,
                "e1": e1,
                "e3": e3,
                "e2": e2,
            }

        def sample_face(face, point, quad_index, sign=1.0):
            found = None
            for raw_key in quad_face_sets[quad_index][face]:
                i = index.get(int(raw_key))
                if i is None:
                    continue
                value = sample_interface(i, point, sign)
                if value is not None:
                    found = value
            return found

        def interpolate_tensor(points, tensors, point):
            distances = [float(np.linalg.norm(point - p)) for p in points]
            if all(d > 0 for d in distances):
                total = 0.0
                weighted = np.zeros((3, 3), dtype=float)
                for distance, tensor in zip(distances, tensors):
                    if tensor is None:
                        continue
                    weighted += tensor / distance
                    total += 1.0 / distance
                if total:
                    return weighted / total
            for a, b in ((0, 3), (0, 1), (2, 1), (2, 3)):
                if distances[a] == 0.0 and distances[b] == 0.0:
                    if tensors[a] is not None and tensors[b] is not None:
                        return 0.5 * (tensors[a] + tensors[b])
            for distance, tensor in zip(distances, tensors):
                if distance == 0.0 and tensor is not None:
                    return tensor
            return None

        def interpolate_scalar(points, values, point, direction=None):
            distances = [float(np.linalg.norm(point - p)) for p in points]
            if direction in ("x", "y"):
                a, b = (0, 2) if direction == "y" else (1, 3)
                d_start, d_end = distances[a], distances[b]
                if (values[a] is not None and values[b] is not None
                        and np.isfinite(values[a]) and np.isfinite(values[b])):
                    length = float(np.linalg.norm(points[a] - points[b]))
                    fraction = round(d_start / length, 8) if length > 0 else 0.0
                    return float(values[a] + (values[b] - values[a]) * fraction)
            finite = [(distance, value) for distance, value in zip(distances, values)
                      if value is not None and np.isfinite(value)]
            if not finite:
                return 0.0
            close = [value for distance, value in finite if distance == 0.0]
            if close:
                return float(np.mean(close))
            total = sum(1.0 / distance for distance, _ in finite)
            return float(sum(value / distance for distance, value in finite) / total) if total else 0.0

        for quad_index, quad_key in enumerate(quad_keys):
            quad = mesh_quads.get(int(quad_key))
            if quad is None:
                face_tensors.append([[None] * 4 for _ in range(6)])
                quad_face_grids.append([None] * 6)
                for name in face_scalars:
                    face_scalars[name].append([[0.0] * 4 for _ in range(6)])
                continue
            base = np.asarray([mesh_nodes[int(node)] for node in quad["nodeKeys"]], dtype=float)
            normals = np.asarray([quad["normals"][index] for index in range(4)], dtype=float)
            thickness = np.asarray(quad["thicknesses"], dtype=float)
            top = base + 0.5 * thickness[:, None] * normals
            bottom = base - 0.5 * thickness[:, None] * normals
            points = {"t": top, "b": bottom}
            face_points = [
                np.asarray([points[side][index] for side, index in refs], dtype=float)
                for refs in face_refs
            ]

            def quad_area(points):
                return 0.5 * float(np.linalg.norm(
                    np.cross(points[2] - points[0], points[3] - points[1])
                ))

            face_use_opposite = []
            for face in range(6):
                face_area = quad_area(face_points[face])
                opposite_area = sum(
                    quad_area(interface_vint[index[int(key)]])
                    for key in quad_face_sets[quad_index][face_opposite[face]]
                    if int(key) in index
                )
                face_use_opposite.append(face_area > 0.0 and opposite_area / face_area > 0.9)
            quad_grids_for_quad = [None] * 6
            tensor_corners = {}
            scalar_corners = {name: {} for name in face_scalars}
            all_tensors = []
            for side_name, side_points in points.items():
                for node_index, point in enumerate(side_points):
                    entries = lookup.get(tuple(round(float(v), 3) for v in point), [])
                    values = [interface_corner_data[i][corner] for i, corner in entries]
                    values = [value for value in values if value is not None]
                    all_tensors.extend(value["tensor"] for value in values)
                    tensor_corners[(side_name, node_index)] = (
                        np.mean([value["tensor"] for value in values], axis=0) if values else None
                    )
                    for name in face_scalars:
                        scalar_corners[name][(side_name, node_index)] = (
                            float(np.mean([value[name] for value in values])) if values else 0.0
                        )
            fallback_tensor = np.mean(all_tensors, axis=0) if all_tensors else None

            def entries_at(ref, allowed):
                side_name, index = ref
                point = points[side_name][index]
                return [
                    interface_corner_data[i][corner]
                    for i, corner in lookup.get(tuple(round(float(v), 3) for v in point), [])
                    if int(keys[i]) in allowed and interface_corner_data[i][corner] is not None
                ]

            quad_faces = []
            quad_scalars = {name: [] for name in face_scalars}
            for face, refs in enumerate(face_refs):
                face_tensor = []
                face_scalar = {name: [] for name in face_scalars}
                for corner, ref in enumerate(refs):
                    edge_entries = {}
                    edge_tensors = {}
                    opposite_entries = entries_at(
                        ref, quad_face_sets[quad_index][face_opposite[face]]
                    )
                    for edge in corner_edges[corner]:
                        allowed = quad_face_sets[quad_index][face_edge_faces[face][edge]]
                        values = entries_at(ref, allowed)
                        edge_entries[edge] = values
                        if values:
                            tensor = np.mean([value["tensor"] for value in values], axis=0)
                            reference = values[0]
                            edge_e1 = np.asarray(reference["e1"], dtype=float)
                            edge_e3 = np.asarray(reference["e3"], dtype=float)
                            edge_e2 = np.cross(edge_e3, edge_e1)
                            length = float(np.linalg.norm(edge_e2))
                            if length > 1e-12:
                                edge_e2 /= length
                                for item in opposite_entries:
                                    normal = np.asarray(item["e2"], dtype=float)
                                    for axis in (edge_e1, edge_e2, edge_e3):
                                        tensor += (abs(float(np.dot(normal, axis)))
                                                   * float(item["normalStress"])
                                                   * np.outer(axis, axis))
                                    shear = (
                                        float(item["inPlaneStress"])
                                        * (np.dot(item["e1"], edge_e1) + np.dot(item["e1"], edge_e3))
                                        + float(item["outOfPlaneStress"])
                                        * (np.dot(item["e3"], edge_e1) + np.dot(item["e3"], edge_e3))
                                    )
                                    tensor += shear * (
                                        np.outer(edge_e1, edge_e3) + np.outer(edge_e3, edge_e1)
                                    )
                            edge_tensors[edge] = tensor
                    adjacent = [tensor for tensor in edge_tensors.values() if tensor is not None]
                    if adjacent:
                        corner_tensor = np.mean(adjacent, axis=0)
                    else:
                        corner_tensor = tensor_corners.get(ref, fallback_tensor)
                    opposite = opposite_entries
                    if opposite:
                        corner_tensor = (corner_tensor + np.mean(
                            [value["tensor"] for value in opposite], axis=0
                        )) if corner_tensor is not None else np.mean(
                            [value["tensor"] for value in opposite], axis=0
                        )
                    face_tensor.append(corner_tensor)
                    for name in face_scalars:
                        if name == "normalStress":
                            edge = (1 if face in (3, 5) else 0) if corner in (0, 1) else (
                                3 if face in (3, 5) else 2
                            )
                        else:
                            edge = (2 if face in (3, 5) else 1) if corner in (1, 2) else (
                                0 if face in (3, 5) else 3
                            )
                        scalar_sources = (
                            opposite_entries if face_use_opposite[face]
                            else edge_entries.get(edge, [])
                        )
                        scalar_values = [
                            value[name] for value in scalar_sources
                            if value.get(name) is not None
                        ]
                        if scalar_values:
                            scalar = float(np.mean(scalar_values))
                        else:
                            scalar = scalar_corners[name].get(ref, 0.0)
                        face_scalar[name].append(scalar)
                quad_faces.append(face_tensor)
                for name in face_scalars:
                    quad_scalars[name].append(face_scalar[name])
            face_tensors.append(quad_faces)
            for name in face_scalars:
                face_scalars[name].append(quad_scalars[name])
            base_lengths = [
                float(np.linalg.norm(base[(index + 1) % 4] - base[index]))
                for index in range(4)
            ]
            resolution = max(20.0, min(base_lengths) / 8.0)
            for face in range(6):
                if not include_face_grids:
                    continue
                face_point = face_points[face]
                n = max(2, min(32, int(np.floor(
                    max(np.linalg.norm(face_point[1] - face_point[0]),
                        np.linalg.norm(face_point[3] - face_point[2])) / resolution + 0.5
                ))))
                m = max(2, min(32, int(np.floor(
                    max(np.linalg.norm(face_point[2] - face_point[1]),
                        np.linalg.norm(face_point[3] - face_point[0])) / resolution + 0.5
                ))))
                if n <= 2 and m <= 2:
                    continue
                edge_points = []
                for edge in range(4):
                    if edge in (0, 2):
                        uv = [(-1.0 + 2.0 * index / (m - 1), -1.0 if edge == 0 else 1.0)
                              for index in range(m)]
                    else:
                        uv = [(1.0 if edge == 1 else -1.0, -1.0 + 2.0 * index / (n - 1))
                              for index in range(n)]
                    edge_points.append([
                        (1 - u) * (1 - v) / 4.0 * face_point[0]
                        + (1 + u) * (1 - v) / 4.0 * face_point[1]
                        + (1 + u) * (1 + v) / 4.0 * face_point[2]
                        + (1 - u) * (1 + v) / 4.0 * face_point[3]
                        for u, v in uv
                    ])
                def edge_e1(edge):
                    for raw_key in quad_face_sets[quad_index][face_edge_faces[face][edge]]:
                        i = index.get(int(raw_key))
                        if i is not None:
                            return e1s[i]
                    return None

                sign0 = 1.0
                sign1 = 1.0
                edge0_axis, edge2_axis = edge_e1(0), edge_e1(2)
                edge1_axis, edge3_axis = edge_e1(1), edge_e1(3)
                if edge0_axis is not None and edge2_axis is not None:
                    if float(np.dot(edge0_axis, edge2_axis)) < 0.0:
                        sign0 = -1.0
                if edge1_axis is not None and edge3_axis is not None:
                    if float(np.dot(edge1_axis, edge3_axis)) < 0.0:
                        sign1 = -1.0
                edge_samples = [
                    [sample_face(
                        face_edge_faces[face][edge], point, quad_index,
                        sign0 if edge == 0 else sign1 if edge == 1 else 1.0,
                    ) for point in edge_points[edge]]
                    for edge in range(4)
                ]
                for edge, opposite in ((0, 2), (1, 3), (2, 0), (3, 1)):
                    if not any(value is not None for value in edge_samples[edge]):
                        source = edge_samples[opposite]
                        if any(value is not None for value in source):
                            edge_samples[edge] = [
                                source[index % len(source)] for index in range(len(edge_samples[edge]))
                            ]
                scalar_edge_samples = [list(values) for values in edge_samples]
                if face_use_opposite[face]:
                    for edge in range(4):
                        for sample_index, point in enumerate(edge_points[edge]):
                            value = sample_face(face_opposite[face], point, quad_index)
                            if value is not None:
                                scalar_edge_samples[edge][sample_index] = value
                for edge, opposite in ((0, 2), (1, 3), (2, 0), (3, 1)):
                    if not any(value is not None for value in scalar_edge_samples[edge]):
                        source = scalar_edge_samples[opposite]
                        if any(value is not None for value in source):
                            scalar_edge_samples[edge] = [
                                source[index % len(source)] for index in range(len(scalar_edge_samples[edge]))
                            ]
                # C# AddTensorOnEdge: the opposite-face normal stress is
                # superposed on each edge tensor before the final interpolation.
                for edge in range(4):
                    reference = next((value for value in edge_samples[edge] if value is not None), None)
                    if reference is None:
                        continue
                    edge_e1 = np.asarray(reference["e1"], dtype=float)
                    edge_e3 = np.asarray(reference["e3"], dtype=float)
                    edge_e2 = np.cross(edge_e3, edge_e1)
                    norm = float(np.linalg.norm(edge_e2))
                    if norm <= 1e-12:
                        continue
                    edge_e2 /= norm
                    edge_axes = (edge_e1, edge_e2, edge_e3)
                    for sample, point in zip(edge_samples[edge], edge_points[edge]):
                        opposite = sample_face(face_opposite[face], point, quad_index)
                        if sample is None or opposite is None:
                            continue
                        normal = np.asarray(opposite["e2"], dtype=float)
                        correction = np.zeros((3, 3), dtype=float)
                        for axis in edge_axes:
                            correction += (abs(float(np.dot(normal, axis)))
                                           * float(opposite["normalStress"])
                                           * np.outer(axis, axis))
                        shear = (
                            float(opposite["inPlaneStress"])
                            * (np.dot(opposite["e1"], edge_e1) + np.dot(opposite["e1"], edge_e3))
                            + float(opposite["outOfPlaneStress"])
                            * (np.dot(opposite["e3"], edge_e1) + np.dot(opposite["e3"], edge_e3))
                        )
                        correction += shear * (
                            np.outer(edge_e1, edge_e3) + np.outer(edge_e3, edge_e1)
                        )
                        sample["tensor"] = sample["tensor"] + correction
                grid_tensors = []
                grid_scalars = {name: [] for name in face_scalars}
                for row in range(n):
                    for column in range(m):
                        u = -1.0 + 2.0 * column / (m - 1)
                        v = -1.0 + 2.0 * row / (n - 1)
                        point = (
                            (1 - u) * (1 - v) / 4.0 * face_point[0]
                            + (1 + u) * (1 - v) / 4.0 * face_point[1]
                            + (1 + u) * (1 + v) / 4.0 * face_point[2]
                            + (1 - u) * (1 + v) / 4.0 * face_point[3]
                        )
                        edge_tensors = [
                            edge_samples[0][column], edge_samples[1][row],
                            edge_samples[2][column], edge_samples[3][row],
                        ]
                        edge_locations = [
                            edge_points[0][column], edge_points[1][row],
                            edge_points[2][column], edge_points[3][row],
                        ]
                        if face in (3, 5):
                            # C# GetValueForColorMapTextureTensor(tipoFace=1)
                            # rotates the four edges by one position.
                            edge_tensors = edge_tensors[1:] + edge_tensors[:1]
                            edge_locations = edge_locations[1:] + edge_locations[:1]
                        tensor = interpolate_tensor(
                            edge_locations,
                            [value["tensor"] if value is not None else None
                             for value in edge_tensors],
                            point,
                        )
                        opposite = sample_face(face_opposite[face], point, quad_index)
                        if opposite is not None:
                            tensor = (tensor + opposite["tensor"]) if tensor is not None else opposite["tensor"]
                        grid_tensors.append(tensor)
                        for name in face_scalars:
                            values = [
                                scalar_edge_samples[0][column],
                                scalar_edge_samples[1][row],
                                scalar_edge_samples[2][column],
                                scalar_edge_samples[3][row],
                            ]
                            locations = [
                                edge_points[0][column], edge_points[1][row],
                                edge_points[2][column], edge_points[3][row],
                            ]
                            if face in (3, 5):
                                values = values[1:] + values[:1]
                                locations = locations[1:] + locations[:1]
                            direction = (
                                "y" if name == "normalStress"
                                else "x" if name in ("inPlaneStress", "outOfPlaneStress")
                                else None
                            )
                            grid_scalars[name].append(interpolate_scalar(
                                locations,
                                [value[name] if value is not None else None for value in values],
                                point,
                                direction,
                            ))
                quad_grids_for_quad[face] = {
                    "n": n, "m": m,
                    "tensors": grid_tensors,
                    "scalars": grid_scalars,
                }
            quad_face_grids.append(quad_grids_for_quad)

        def face_principal(tensor, which):
            if tensor is None:
                return 0.0
            eigenvalues = np.linalg.eigvalsh(tensor)
            value = float(eigenvalues[-1] if which == "max" else eigenvalues[0])
            if which == "max" and value < 0.0:
                return 0.0
            if which == "min" and value > 0.0:
                return 0.0
            return value

        def face_von_mises(tensor):
            if tensor is None:
                return 0.0
            s11, s22, s33 = tensor[0, 0], tensor[1, 1], tensor[2, 2]
            s12, s23, s13 = tensor[0, 1], tensor[1, 2], tensor[0, 2]
            return float(np.sqrt(max(0.0, s11 * s11 + s22 * s22 + s33 * s33
                                     - s11 * s22 - s11 * s33 - s22 * s33
                                     + 3.0 * (s12 * s12 + s23 * s23 + s13 * s13))))

        def face_tensor_values(evaluator):
            output = []
            for faces in face_tensors:
                output.append([
                    [float(evaluator(tensor)) if tensor is not None else 0.0 for tensor in face]
                    for face in faces
                ])
            return output

        def face_scalar_values(name):
            return [
                [[float(value) for value in face] for face in quad_faces]
                for quad_faces in face_scalars[name]
            ]

        face_grid_values = {}
        if include_face_grids and any(face is not None for quad in quad_face_grids for face in quad):
            def face_grid_tensor_values(evaluator):
                output = []
                for quad in quad_face_grids:
                    faces = []
                    for face in quad:
                        if face is None:
                            faces.append(None)
                            continue
                        faces.append({
                            "n": face["n"],
                            "m": face["m"],
                            "values": [
                                round(float(evaluator(tensor)), 6) if tensor is not None else 0.0
                                for tensor in face["tensors"]
                            ],
                        })
                    output.append(faces)
                return output

            def face_grid_scalar_values(name):
                output = []
                for quad in quad_face_grids:
                    faces = []
                    for face in quad:
                        if face is None:
                            faces.append(None)
                            continue
                        faces.append({
                            "n": face["n"],
                            "m": face["m"],
                            "values": [round(float(value), 6) for value in face["scalars"][name]],
                        })
                    output.append(faces)
                return output

            face_grid_values = {
                "globalStressX": face_grid_tensor_values(lambda tensor: tensor[0, 0]),
                "globalStressY": face_grid_tensor_values(lambda tensor: tensor[1, 1]),
                "globalStressZ": face_grid_tensor_values(lambda tensor: tensor[2, 2]),
                "globalStressXY": face_grid_tensor_values(lambda tensor: tensor[0, 1]),
                "globalStressXZ": face_grid_tensor_values(lambda tensor: tensor[0, 2]),
                "globalStressYZ": face_grid_tensor_values(lambda tensor: tensor[1, 2]),
                "principalTensile": face_grid_tensor_values(lambda tensor: face_principal(tensor, "max")),
                "principalCompressive": face_grid_tensor_values(lambda tensor: face_principal(tensor, "min")),
                "vonMises": face_grid_tensor_values(face_von_mises),
                "localStressNormal": face_grid_scalar_values("normalStress"),
                "localStressInPlane": face_grid_scalar_values("inPlaneStress"),
                "localStressOutOfPlane": face_grid_scalar_values("outOfPlaneStress"),
            }

        face_values = {
            "globalStressX": face_tensor_values(lambda tensor: tensor[0, 0]),
            "globalStressY": face_tensor_values(lambda tensor: tensor[1, 1]),
            "globalStressZ": face_tensor_values(lambda tensor: tensor[2, 2]),
            "globalStressXY": face_tensor_values(lambda tensor: tensor[0, 1]),
            "globalStressXZ": face_tensor_values(lambda tensor: tensor[0, 2]),
            "globalStressYZ": face_tensor_values(lambda tensor: tensor[1, 2]),
            "principalTensile": face_tensor_values(lambda tensor: face_principal(tensor, "max")),
            "principalCompressive": face_tensor_values(lambda tensor: face_principal(tensor, "min")),
            "vonMises": face_tensor_values(face_von_mises),
            "localStressNormal": face_scalar_values("normalStress"),
            "localStressInPlane": face_scalar_values("inPlaneStress"),
            "localStressOutOfPlane": face_scalar_values("outOfPlaneStress"),
        }

    def tensor_field(evaluator):
        values = []
        for links in corner_links:
            all_data = [data for link in links for data in link]
            fallback = np.mean([data["tensor"] for data in all_data], axis=0) if all_data else None
            corners = []
            for adjacent in links:
                tensor = np.mean([data["tensor"] for data in adjacent], axis=0) if adjacent else fallback
                corners.append(float(evaluator(tensor)) if tensor is not None else 0.0)
            values.append(corners)
        return values

    def scalar_field(name):

        values = []
        for links in corner_links:
            all_values = [data[name] for link in links for data in link]
            fallback = float(np.mean(all_values)) if all_values else 0.0
            corners = []
            for adjacent in links:
                corners.append(float(np.mean([data[name] for data in adjacent])) if adjacent else fallback)
            values.append(corners)
        return values

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

    def von_mises(tensor):
        if tensor is None:
            return 0.0
        s11, s22, s33 = tensor[0, 0], tensor[1, 1], tensor[2, 2]
        s12, s23, s13 = tensor[0, 1], tensor[1, 2], tensor[0, 2]
        return float(np.sqrt(max(0.0, s11 * s11 + s22 * s22 + s33 * s33
                                 - s11 * s22 - s11 * s33 - s22 * s33
                                 + 3.0 * (s12 * s12 + s23 * s23 + s13 * s13))))

    values = {
        "globalStressX": tensor_field(lambda tensor: tensor[0, 0]),
        "globalStressY": tensor_field(lambda tensor: tensor[1, 1]),
        "globalStressZ": tensor_field(lambda tensor: tensor[2, 2]),
        "globalStressXY": tensor_field(lambda tensor: tensor[0, 1]),
        "globalStressXZ": tensor_field(lambda tensor: tensor[0, 2]),
        "globalStressYZ": tensor_field(lambda tensor: tensor[1, 2]),
        "principalTensile": tensor_field(lambda tensor: principal(tensor, "max")),
        "principalCompressive": tensor_field(lambda tensor: principal(tensor, "min")),
        "vonMises": tensor_field(von_mises),
        "localStressNormal": scalar_field("normal"),
        "localStressInPlane": scalar_field("inPlane"),
        "localStressOutOfPlane": scalar_field("outOfPlane"),
    }
    step = int(z["steps/step_index"][-1])
    fields = complete_field_set(
        values, step,
        "C# interface-spring stress tensor · final v2 snapshot",
        "The bridge v2 bundle stores final spring stresses, not strains or plastic strains.",
    )
    if face_values:
        for field in fields:
            face_array = face_values.get(field["id"])
            if face_array is None:
                continue
            array = np.asarray(face_array, dtype=float)
            if not np.isfinite(array).all():
                continue
            field["quadFaceValues"] = np.round(array, 6).tolist()
            values_for_range = [array]
            grid_values = face_grid_values.get(field["id"])
            if grid_values and any(face is not None for quad in grid_values for face in quad):
                field["quadFaceGrids"] = grid_values
                for quad in grid_values:
                    for face in quad:
                        if face is not None:
                            values_for_range.append(np.asarray(face["values"], dtype=float))
            combined = np.concatenate([values.ravel() for values in values_for_range])
            field["min"] = float(combined.min())
            field["max"] = float(combined.max())
    von_mises_field = next(field for field in fields if field["id"] == "vonMises")
    return fields, von_mises_field


def _von_mises_field(z):
    """Backward-compatible Von Mises-only view of :func:`_stress_fields`."""
    return _stress_fields(z)[1]


STRESS_FIELD_SOURCE = "C# interface-spring stress tensor · final v2 snapshot"
STRESS_FIELD_REASON = "The bridge v2 bundle stores final spring stresses, not strains or plastic strains."
STRESS_FIELD_IDS = {
    "globalStressX", "globalStressY", "globalStressZ",
    "globalStressXY", "globalStressXZ", "globalStressYZ",
    "principalTensile", "principalCompressive", "vonMises",
    "localStressNormal", "localStressInPlane", "localStressOutOfPlane",
}


def _stress_field_descriptors(step):
    """Cheap menu descriptors for a source whose values are fetched lazily."""
    fields = complete_field_set({}, step, STRESS_FIELD_SOURCE, STRESS_FIELD_REASON)
    for field in fields:
        if field["id"] in STRESS_FIELD_IDS:
            field["available"] = True
            field["lazy"] = True
            field.pop("reason", None)
    return fields


def _analysis(entry, summary, mesh, z, include_face_grids=True,
              include_stress_fields=True):
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
    if include_stress_fields:
        stress_fields, von_mises_field = _stress_fields(
            z, mesh, include_face_grids=include_face_grids
        )
    else:
        stress_fields = _stress_field_descriptors(int(z["steps/step_index"][-1]))
        von_mises_field = None
    return {
        "name": summary["metadata"].get("analysis_name", entry["case_id"]),
        "caseId": entry["case_id"],
        "outcome": summary.get("metrics", {}).get("outcome", "completed"),
        "steps": steps,
        "diagnostics": {"equilibriumCheckedSteps": 0, "equilibriumFailedSteps": 0},
        "interfaces": _interfaces_summary(z, interface_order),
        "interfaceOrder": interface_order,
        "finalStress": von_mises_field,
        "stressFields": stress_fields,
        "curveOnly": False,
    }


def _catalog_and_case(raw, output_path, analysis_name):
    entries = _case_entries(raw)
    catalog = _catalog(entries, output_path)
    entry, summary = _resolve_entry(entries, output_path, analysis_name, raw.get("default_case"))
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
    return _resolve_entry(entries, output_path, analysis_name, raw.get("default_case"))


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


def _contours_payload(z, entry, summary):
    """Build the contour payload from an already-loaded v2 field mapping."""
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
        "phaseNames": PHASE_NAMES,
        "positions": _encode_float32(positions.reshape(-1)),
        "stress": _encode_float32(stress),
        "force": _encode_float32(force),
        "area": _encode_float32(area),
        "displacement": _encode_float32(np.zeros(len(stress), dtype=np.float32)),
        "strain": _encode_float32(np.zeros(len(stress), dtype=np.float32)),
        "phase": base64.b64encode(phases.astype("u1").tobytes()).decode("ascii"),
    }


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


def _interface_payload(z, entry, summary, key):
    """Build one interface detail payload from an already-loaded field mapping."""
    key = int(key)
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
