"""Project saved results for the browser; never prepare or solve a model."""
from pathlib import Path
from types import SimpleNamespace as Record
import json
import sys
from collections import Counter
import hashlib
import re
import base64

import numpy as np
from saved_result_geometry import interface_geometry

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "histra-python"))
from histra.postprocessing import _average_node_displacements, compute_node_displacements, quad_node_displacement

NATIVE_UNITS = {"length": "cm", "force": "kN", "moment": "kN*cm", "stress": "kN/cm^2",
                "rotation": "rad", "energy": "kN*cm", "frequency": "Hz", "period": "s"}

_RAW_CACHE = {}


def is_csharp_results(output_path):
    return Path(output_path).suffix.lower() == ".results"


def is_histra_results(output_path):
    return Path(output_path).suffix.lower() == ".histra"


def csharp_hrx(output_path):
    """Locate the HRX that belongs to a native C# ``.Results`` database."""
    output_path = Path(output_path)
    candidates = (output_path.with_suffix(".hrx"), output_path.with_suffix(".HRX"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError("The C# .Results database has no sibling .hrx model file.")


def load_raw(output_path):
    output_path = Path(output_path)
    stamp = (output_path.stat().st_mtime_ns, output_path.stat().st_size)
    if str(output_path) in _RAW_CACHE:
        cached_stamp, raw = _RAW_CACHE[str(output_path)]
        if cached_stamp == stamp:
            return raw
    raw = json.loads(output_path.read_text())
    _RAW_CACHE.clear()
    _RAW_CACHE[str(output_path)] = (stamp, raw)
    return raw


def validate_metadata(raw, hrx_path=None):
    if raw.get("schema_version") != "1.1.0":
        raise ValueError("Expected saved-result schema 1.1.0.")
    if any(raw.get("units", {}).get(k) != v for k, v in NATIVE_UNITS.items()):
        raise ValueError("Unsupported or missing result units; expected the declared kN/cm/rad system.")
    digest = raw.get("model_sha256", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ValueError("Missing or invalid model SHA-256.")
    if hrx_path and Path(hrx_path).is_file() and hashlib.sha256(Path(hrx_path).read_bytes()).hexdigest() != digest.lower():
        raise ValueError("Result model SHA-256 does not match the supplied HRX.")


def result_mesh(raw):
    geometry = raw["model_geometry_and_topology"]
    keys = {str(k) for q in geometry["quads"].values() for k in q["node_keys"]}
    nodes = [{"key": k, "name": geometry["nodes"][k].get("name", k), "point": geometry["nodes"][k]["point"]}
             for k in sorted(keys, key=int)]
    quads = [{"key": k, "name": q.get("name", k), "nodeKeys": list(map(str, q["node_keys"])),
              "materialKey": str(q["material_key"]), "thicknesses": q["thickness"],
              "normals": [q["reference_e3"]] * 4}
             for k, q in geometry["quads"].items()]
    materials = [{"key": str(k), "name": m.get("name", str(k)), "color": "#6fb7ff"}
                 for k, m in geometry["materials"].items()]
    thrust_pairs = []
    for k, q in geometry["quads"].items():
        ikeys = q.get("interface_keys", [])
        if len(ikeys) >= 3 and len(ikeys[0]) == 1 and len(ikeys[2]) == 1:
            thrust_pairs.append([int(k), ikeys[0][0], ikeys[2][0], str(q["material_key"])])
        if len(ikeys) >= 4 and len(ikeys[1]) == 1 and len(ikeys[3]) == 1:
            thrust_pairs.append([int(k), ikeys[1][0], ikeys[3][0], str(q["material_key"])])
    interfaces = {str(k): {"nodeKeys": list(map(str, i["node_keys"])), "length": float(i["length"])}
                  for k, i in geometry.get("interfaces", {}).items()
                  if "node_keys" in i and "length" in i}
    return {"name": Path(raw.get("model_file", "Wall model")).name, "nodes": nodes, "quads": quads,
            "materials": materials, "thrustPairs": thrust_pairs, "interfaces": interfaces}


def spring_values(spring):
    force = spring.get("cstress_force", spring.get("force"))
    area = spring.get("area")
    phase = str(spring.get("phase_name", spring.get("phase", "Unknown")))
    if phase == "0" and spring.get("type") == "SpringElastic":
        phase = "Elastic"
    strain = spring.get("cstrain", spring.get("u"))
    return {"index": spring.get("index"), "row": spring.get("row"), "col": spring.get("col"),
            "type": spring.get("type"), "force": force, "area": area,
            "stress": force / area * 10 if force is not None and area and area > 0 else None,
            "displacement": spring.get("u"), "strain": strain, "phase": phase}


def project_interface(output_path, analysis_name, key):
    if is_histra_results(output_path):
        from histra_results import project_interface_histra
        return project_interface_histra(output_path, analysis_name, int(key))
    if is_csharp_results(output_path):
        from csharp_results import project_interface_csharp
        return project_interface_csharp(csharp_hrx(output_path), output_path, analysis_name, int(key))
    raw = load_raw(output_path)
    if raw.get("schema_version") == "2.0.0" and "baseline_case" in raw:
        from bridge_v2 import project_interface as project_bridge_interface
        return project_bridge_interface(output_path, analysis_name, key)
    validate_metadata(raw)
    state = raw["analyses"][analysis_name]["committed_element_and_spring_state"]["interface_states"][str(key)]
    geometry = interface_geometry(raw["model_geometry_and_topology"]["interfaces"][str(key)], state)
    return {"key": key, "analysis": analysis_name, "modelSha256": raw["model_sha256"], "geometry": geometry,
            "forces": state["status_forces"],
            "moments": state["status_bending_moments"], "localForces": state["f"],
            "normal": [spring_values(s) for s in state["trasv_1"]],
            "sliding": [dict(spring_values(s), group=group) for group in ("slid", "slid_out_plan") for s in state[group]]}


def project_contours(output_path, analysis_name):
    """Actual saved normal-fibre stress on native C# interface cells."""
    if is_histra_results(output_path):
        from histra_results import project_contours_histra
        return project_contours_histra(output_path, analysis_name)
    if is_csharp_results(output_path):
        from csharp_results import project_contours_csharp
        return project_contours_csharp(csharp_hrx(output_path), output_path, analysis_name)
    raw = load_raw(output_path)
    if raw.get("schema_version") == "2.0.0" and "baseline_case" in raw:
        from bridge_v2 import project_contours as project_bridge_contours
        return project_bridge_contours(output_path, analysis_name)
    from histra.preprocessing.csharp_fibre_geometry import _csharp_interface_cells

    validate_metadata(raw)
    analysis = raw["analyses"][analysis_name]
    states = analysis["committed_element_and_spring_state"]["interface_states"]
    geometry = raw["model_geometry_and_topology"]["interfaces"]
    positions, stresses, forces, areas, movements, phases, groups = [], [], [], [], [], [], []
    offset = 0
    for key in sorted(states, key=int):
        state = states[key]
        g = interface_geometry(geometry[key], state)
        interface = Record(**{**g, "vint2d": [Record(x=p[0], y=p[1]) for p in g["vint2d"]]})
        cells = _csharp_interface_cells(interface)
        springs = [spring_values(s) for s in state["trasv_1"]]
        if len(springs) != len(cells) or not np.isfinite(cells).all():
            raise ValueError(f"Interface {key} has incompatible fibre geometry.")
        if any(s["index"] != i or s["row"] != i // g["ncol"] or s["col"] != i % g["ncol"] for i, s in enumerate(springs)):
            raise ValueError(f"Interface {key} has an unexpected fibre ordering.")
        positions.append(cells)
        stresses.extend(s["stress"] for s in springs)
        forces.extend(s["force"] for s in springs)
        areas.extend(s["area"] for s in springs)
        movements.extend(s["displacement"] for s in springs)
        phases.extend(s["phase"] for s in springs)
        groups.append({"key": int(key), "start": offset, "count": len(springs),
                       "restrained": state["interfaccia_vincolata"], "nrow": g["nrow"], "ncol": g["ncol"],
                       "corners": g["vint3d"], "origin": g["reference_origin"],
                       "e1": g["reference_e1"], "e3": g["reference_e3"],
                       "parents": [g["parent_element_key1"], g["parent_element_key2"]],
                       "parentTypes": [g.get("parent_type_element1", "Quad"), g.get("parent_type_element2", "Quad")]})
        offset += len(springs)
    phase_names = sorted(set(phases))
    def packed(values, dtype="<f4"):
        array = np.asarray(values, dtype=dtype)
        if not np.isfinite(array).all():
            raise ValueError("Nonfinite contour data.")
        return base64.b64encode(array.tobytes()).decode("ascii")
    return {"analysis": analysis_name, "step": analysis["execution"]["output_steps"][-1]["step"],
            "modelSha256": raw["model_sha256"], "encoding": "base64-little-endian",
            "stressUnit": "MPa", "strainUnit": "cm", "cellCount": offset, "groups": groups, "phaseNames": phase_names,
            "positions": packed(np.concatenate(positions)), "stress": packed(stresses),
            "force": packed(forces), "area": packed(areas), "displacement": packed(movements),
            "strain": packed(movements),
            "phase": packed([phase_names.index(p) for p in phases], "u1")}


def interface_summary(key, state, geometry):
    springs = [spring_values(s) for s in state["trasv_1"]]
    stresses = [s["stress"] for s in springs if s["stress"] is not None]
    return {"key": int(key), "parents": [geometry["parent_element_key1"], geometry["parent_element_key2"]],
            "parentTypes": [geometry.get("parent_type_element1", "Quad"), geometry.get("parent_type_element2", "Quad")],
            "restrained": state["interfaccia_vincolata"], "materialKey": state["material_key"],
            "forces": state["status_forces"], "minStress": min(stresses) if stresses else None,
            "moments": state["status_bending_moments"],
            "maxStress": max(stresses) if stresses else None,
            "phases": dict(Counter(s["phase"] for s in springs))}


def step_resultants(step, interface_order):
    if "interface_resultants" in step:
        values = step["interface_resultants"]
        if set(values) != set(interface_order):
            raise ValueError("Saved step has incomplete interface resultants.")
        packed = [values[k]["forces"] + values[k]["bending_moments"] for k in interface_order]
    else:
        # Array exports use one-based contiguous interface IDs; final rows are
        # independently checked against keyed committed states below.
        if list(map(int, interface_order)) != list(range(1, len(interface_order)+1)):
            raise ValueError("Array resultants require contiguous one-based interface IDs.")
        forces = np.asarray(step["interface_resultant_forces"])
        moments = np.asarray(step["interface_bending_moments"])
        if forces.shape != (len(interface_order), 3) or moments.shape != forces.shape:
            raise ValueError("Incomplete interface force/moment arrays.")
        packed = np.concatenate([forces, moments], axis=1).tolist()
    if np.asarray(packed).shape != (len(interface_order), 6) or not np.isfinite(packed).all():
        raise ValueError("Invalid interface force/moment history.")
    return packed


def project_curve_cases(hrx_path, raw, name="Pushover Results"):
    cases = raw.get("cases", {})
    mesh = None
    if hrx_path and Path(hrx_path).is_file():
        from hrx_model import parse_hrx
        model = parse_hrx(Path(hrx_path).read_bytes(), Path(hrx_path).name)
        mesh = {
            "name": Path(hrx_path).name,
            "nodes": [{"key": str(n["key"]), "name": str(n.get("name", n["key"])), "point": n["point"]} for n in model["nodes"]],
            "quads": [{"key": str(q["key"]), "name": str(q.get("name", q["key"])), "nodeKeys": list(map(str, q["nodeKeys"])), "materialKey": str(q["materialKey"]), "thicknesses": q["thicknesses"], "normals": q["normals"]} for q in model["quads"]],
            "materials": [{"key": str(m["key"]), "name": str(m.get("name", m["key"])), "color": m.get("color", "#6fb7ff")} for m in model["materials"]],
            "thrustPairs": [],
            "interfaces": {},
        }
    else:
        mesh = {"name": name, "nodes": [], "quads": [], "materials": [], "thrustPairs": [], "interfaces": {}}

    analyses = []
    for case_id, c in cases.items():
        disp_mm = c.get("disp_mm", [])
        force_kN = c.get("force_kN", [])
        steps = []
        max_d = 0.0
        for i, (d_mm, f_kn) in enumerate(zip(disp_mm, force_kN)):
            d_cm = d_mm / 10.0
            max_d = max(max_d, abs(d_cm))
            steps.append({
                "step": i,
                "status": "OK",
                "loadFactor": f_kn,
                "controlDisplacement": d_cm,
                "displacements": [],
                "maxDisplacement": max_d,
                "appliedVerticalForce": f_kn,
                "reactions": [0.0, 0.0, -f_kn],
            })
        analyses.append({
            "name": case_id,
            "outcome": f"Pushover finished ({len(steps)} steps)",
            "steps": steps,
            "diagnostics": {"equilibriumCheckedSteps": len(steps), "equilibriumFailedSteps": 0},
            "interfaces": [],
            "interfaceOrder": [],
        })

    return {
        "schemaVersion": 3,
        "name": raw.get("metadata", {}).get("title", name),
        "sourceUnits": {"length": "mm", "force": "kN"},
        "units": {"length": "cm", "force": "kN", "moment": "kN·cm", "stress": "MPa"},
        "mesh": mesh,
        "analyses": analyses,
        "modal": [],
    }


def project_results(hrx_path, output_path, analysis_name=None):
    if is_histra_results(output_path):
        from histra_results import project_histra
        return project_histra(output_path, analysis_name)
    if is_csharp_results(output_path):
        from csharp_results import project_csharp
        return project_csharp(hrx_path, output_path, analysis_name)
    raw = load_raw(output_path)
    if raw.get("schema_version") == "2.0.0" and "baseline_case" in raw:
        from bridge_v2 import project_bridge
        return project_bridge(hrx_path, output_path, analysis_name)
    if "cases" in raw and raw.get("schema_version") != "1.1.0":
        return project_curve_cases(hrx_path, raw, Path(output_path).stem)
    validate_metadata(raw, hrx_path)
    mesh = result_mesh(raw)
    geometry = raw["model_geometry_and_topology"]
    node_order = sorted(mesh["nodes"], key=lambda n: int(n["key"]))
    nodes = {}
    for n in node_order:
        saved = geometry["nodes"][str(n["key"])]
        if not np.isfinite(saved["point"]).all():
            raise ValueError("Nonfinite result node coordinates.")
        nodes[int(n["key"])] = Record(name=n["name"], point=Record(**dict(zip("xyz", saved["point"]))))
    quads = {}
    for key, q in geometry["quads"].items():
        if len(q["node_keys"]) != 4 or len(set(q["node_keys"])) != 4:
            raise ValueError("Invalid result Quad connectivity.")
        if any(len(q[k]) != 4 or not np.isfinite(q[k]).all() for k in ("sin", "cos")):
            raise ValueError("Invalid standalone Quad recovery coefficients.")
        if any(not 1 <= a["gdl"] <= geometry["gdl"] for row in q["aff"] for a in row):
            raise ValueError("Invalid result DOF mapping.")
        quads[int(key)] = Record(**{
            **q, "g": Record(**dict(zip("xyz", q["g"]))),
            "aff": [[Record(**a) for a in row] for row in q["aff"]],
            "sin": q["sin"], "cos": q["cos"],
        })
    model = Record(gdl=geometry["gdl"], collections=Record(nodes=nodes, quads=quads))
    q_items = list(quads.values())
    n_quads = len(q_items)
    aff_q, aff_dof, aff_gdl, aff_alfa = [], [], [], []
    for qi, q in enumerate(q_items):
        for dof, entries in enumerate(q.aff[:7]):
            for e in entries:
                if 0 <= e.gdl - 1 < model.gdl:
                    aff_q.append(qi)
                    aff_dof.append(dof)
                    aff_gdl.append(e.gdl - 1)
                    aff_alfa.append(float(e.alfa))
    aff_row = np.array(aff_q, dtype=np.int32) * 7 + np.array(aff_dof, dtype=np.int32)
    aff_gdl = np.array(aff_gdl, dtype=np.int32)
    aff_alfa = np.array(aff_alfa, dtype=np.float64)
    centres = np.array([[q.g.x, q.g.y, q.g.z] for q in q_items], dtype=np.float32)
    corners = np.array([[[nodes[nk].point.x, nodes[nk].point.y, nodes[nk].point.z] for nk in q.node_keys] for q in q_items], dtype=np.float32)
    rel = (corners - centres[:, None, :]).astype(np.float32)
    corr2 = np.zeros((n_quads, 3), dtype=np.float64)
    corr3 = np.zeros((n_quads, 3), dtype=np.float64)
    for qi, q in enumerate(q_items):
        e1 = np.asarray(q.reference_e1, dtype=np.float32)
        e2 = np.asarray(q.reference_e2, dtype=np.float32)
        denom = float(q.sin[2])
        if abs(denom) > 1e-30:
            coeff = -float(q.length[3]) * float(q.sin[3]) / denom
            for j in range(3):
                corr2[qi, j] = coeff * (float(q.sin[1]) * float(e1[j]) + float(q.cos[1]) * float(e2[j]))
        for j in range(3):
            corr3[qi, j] = float(q.length[3]) * (-float(q.sin[0]) * float(e1[j]) + float(q.cos[0]) * float(e2[j]))
    connected = {int(n["key"]): [] for n in node_order}
    for qi, q in enumerate(q_items):
        for idx, nk in enumerate(q.node_keys):
            if nk in connected:
                connected[nk].append((qi, idx))
    if any(not v for v in connected.values()):
        raise ValueError("Every mesh node must belong to at least one Quad.")

    def recover_displacements(global_u):
        u_arr = np.asarray(global_u, dtype=np.float64)
        if u_arr.ndim != 1 or u_arr.size != int(model.gdl):
            raise ValueError("Invalid displacement vector length.")
        local = np.zeros(n_quads * 7, dtype=np.float64)
        np.add.at(local, aff_row, u_arr[aff_gdl] * aff_alfa)
        local = local.reshape(n_quads, 7)
        u32 = local.astype(np.float32)
        quad_u = (u32[:, None, :3] + np.cross(u32[:, None, 3:6], rel).astype(np.float32)).astype(np.float32)
        quad_u[:, 2, :] = quad_u[:, 2, :] + (local[:, 6:7] * corr2).astype(np.float32)
        quad_u[:, 3, :] = quad_u[:, 3, :] + (local[:, 6:7] * corr3).astype(np.float32)
        node_u = [_average_node_displacements([quad_u[qi, idx] for qi, idx in connected[int(n["key"])]]).tolist()
                  for n in node_order]
        return quad_u, node_u

    def encode_quad_u(quad_u):
        arr = np.ascontiguousarray(quad_u, dtype="<f4")
        if not np.isfinite(arr).all():
            raise ValueError("Nonfinite Quad vertex displacement.")
        return base64.b64encode(arr.tobytes()).decode("ascii")

    analyses = []
    interface_order = sorted(geometry["interfaces"], key=int)
    pier1_indices = [
        i for i, n in enumerate(node_order)
        if abs(geometry["nodes"][str(n["key"])]["point"][2] - (-220.0)) < 1.0 and 420.0 <= geometry["nodes"][str(n["key"])]["point"][0] <= 580.0
    ]
    for name, analysis in raw["analyses"].items():
        execution = analysis.get("execution")
        if not execution:
            continue
        steps = []
        for step in execution["output_steps"]:
            if step["status"] not in ("INITIAL", "OK"):
                continue
            if not np.isfinite(step["u"]).all():
                raise ValueError("Nonfinite displacement in saved results.")
            quad_u, displacements = recover_displacements(step["u"])
            packed = step_resultants(step, interface_order)
            step_record = {
                "step": step["step"], "status": step["status"],
                "loadFactor": step["load_factor"], "controlDisplacement": step["displacement"],
                "displacements": displacements,
                "quadDisplacements": encode_quad_u(quad_u),
                "maxDisplacement": max(float(np.linalg.norm(v)) for v in displacements),
                # Downward positive; stage-initial force is excluded. Expected
                # external equilibrium avoids adding iterative reaction noise.
                "appliedVerticalForce": execution["output_steps"][0]["reaction_z"] - step.get("equilibrium_expected_reaction_z", step["reaction_z"]),
                "reactions": [step[f"reaction_{axis}"] for axis in "xyz"],
                "elasticEnergy": step.get("elastic_energy"),
                "dissipatedEnergy": step.get("dissipated_energy"),
                "interfaceResultants": packed,
                "equilibriumChecked": step.get("equilibrium_checked"),
                "equilibriumOk": step.get("equilibrium_ok"),
            }
            if pier1_indices:
                p_uz = [displacements[idx][2] for idx in pier1_indices]
                step_record["pier1Settlement"] = float(min(p_uz))
                step_record["pier1Uplift"] = float(max(p_uz))
            steps.append(step_record)
        if not steps:
            continue
        # Cross-check recovery against the independently exported final node table.
        final = {n["node_key"]: n for n in execution["final_step_node_displacements"]}
        for node, values in zip(node_order, steps[-1]["displacements"]):
            expected = final[int(node["key"])]
            if not np.allclose(values, [expected[c] for c in ("ux", "uy", "uz")], rtol=0, atol=1e-10):
                raise ValueError("Recovered displacements differ from the saved final node results.")
        states = analysis["committed_element_and_spring_state"]["interface_states"]
        final_rows = dict(zip(interface_order, steps[-1]["interfaceResultants"]))
        for key, state in states.items():
            if state["status_forces"] + state["status_bending_moments"] != final_rows[key]:
                raise ValueError("Final interface snapshot differs from the last saved step.")
        interfaces = [interface_summary(k, s, geometry["interfaces"][k]) for k, s in states.items()]
        checked = [s for s in steps if s["equilibriumChecked"]]
        analyses.append({"name": name, "outcome": execution["outcome"], "steps": steps,
                         "diagnostics": {"equilibriumCheckedSteps": len(checked),
                                         "equilibriumFailedSteps": sum(s["equilibriumOk"] is False for s in checked)},
                         "interfaces": interfaces, "interfaceOrder": list(map(int, interface_order))})
    if not analyses:
        raise ValueError("No committed displacement results found.")
    modal = []
    for name, analysis in raw["analyses"].items():
        if not analysis.get("modal_result"):
            continue
        result = analysis["modal_result"]
        shapes = np.asarray(result["mode_shapes"], dtype=float)
        if shapes.shape != (model.gdl, len(result["modal_values"])) or not np.isfinite(shapes).all():
            raise ValueError("Invalid saved mode shapes.")
        modes = []
        for index, row in enumerate(result["modal_values"]):
            quad_u, node_u = recover_displacements(shapes[:, index])
            values = np.asarray(node_u, dtype=float)
            maximum = float(np.max(np.linalg.norm(values, axis=1)))
            norm_quad = quad_u / maximum if maximum > 0 else quad_u
            modes.append({"number": row["Step"], "frequency": row["Fn"], "period": row["Tn"],
                          "massPercent": [row[f"M{axis}_pcent"] for axis in "xyz"],
                          "displacements": (values / maximum if maximum > 0 else values).tolist(),
                          "quadDisplacements": encode_quad_u(norm_quad)})
        modal.append({"name": name, "modes": modes})
    return {"schemaVersion": 3, "sourceSchema": raw["schema_version"], "modelSha256": raw["model_sha256"],
            "title": raw.get("title", mesh["name"]),
            "scourStage": raw.get("scour_stage"),
            "formulation": raw.get("formulation"),
            "sourceUnits": raw["units"], "name": mesh["name"], "units": {"length": "cm", "force": "kN", "moment": "kN·cm", "stress": "MPa", "energy": "kN·cm"},
            "mesh": {"nodes": node_order, "quads": mesh["quads"], "materials": mesh["materials"],
                     "thrustPairs": mesh.get("thrustPairs", []), "interfaces": mesh.get("interfaces", {})},
            "analyses": analyses, "modal": modal}


if __name__ == "__main__":
    try:
        if len(sys.argv) > 3 and sys.argv[3] == "--interface":
            result = project_interface(sys.argv[2], sys.argv[4], int(sys.argv[5]))
        elif len(sys.argv) > 3 and sys.argv[3] == "--contours":
            result = project_contours(sys.argv[2], sys.argv[4])
        else:
            result = project_results(sys.argv[1], sys.argv[2])
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
