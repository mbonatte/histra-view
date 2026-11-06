"""Read-only HRX projection for viewing; never prepares or executes a solver."""
from __future__ import annotations

from collections import Counter
import math
import re
import xml.etree.ElementTree as ET


def number(raw, default=0.0):
    try:
        value = float(raw)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def vector(raw):
    if not raw:
        return None
    parts = raw.split(";")
    values = [number(part, None) for part in parts]
    return values if len(values) == 3 and None not in values else None


def record(element):
    return {"key": element.get("Key", element.get("Id", "")),
            "name": element.get("Name", ""), "attributes": dict(element.attrib)}


def color(raw):
    if re.fullmatch(r"#[0-9a-fA-F]{8}", raw or ""):
        return "#" + raw[-6:]
    return raw if re.fullmatch(r"#[0-9a-fA-F]{6}", raw or "") else "#7ca7c7"


def direction(item, target):
    """C# LoadTemplateItem.Dir: 0 is gravity, 4..6 are element-local axes."""
    mode = item.get("IdLoadDirection", "0")
    names = {"Gravity": "0", "GlobalX": "1", "GlobalY": "2", "GlobalZ": "3",
             "LocalX": "4", "LocalY": "5", "LocalZ": "6", "User": "7"}
    mode = names.get(mode, mode)
    value = {"0": [0, 0, -1], "1": [1, 0, 0], "2": [0, 1, 0], "3": [0, 0, 1]}.get(mode)
    if mode in ("4", "5", "6") and target is not None:
        reference = target.find("ReferenceSystem")
        value = vector(reference.get(f"E{int(mode) - 3}")) if reference is not None else None
    if mode == "7":
        value = [number(item.get(f"Dir{axis}")) for axis in "XYZ"]
    norm = math.sqrt(sum(v * v for v in value)) if value else 0
    return [v / norm for v in value] if norm > 0 else None


def geometry_points(element):
    points = [vector(element.get(f"Point{i}")) for i in range(1, 5)]
    points = [p for p in points if p is not None]
    if not points:
        point = vector(element.get("Point"))
        points = [point] if point is not None else []
    return points


ANALYSIS_TYPES = {
    "1": "Static linear",
    "2": "Static nonlinear",
    "3": "Dynamic linear",
    "4": "Dynamic nonlinear",
    "5": "Modal",
}

GAMMA_COEFFICIENTS = {
    "GammaFavEQU",
    "GammaUnfavEQU",
    "GammaFavSTR",
    "GammaUnfavSTR",
    "GammaFavGEO",
    "GammaUnfavGEO",
}


def _model_point_record(element):
    el_type = element.get("ElementType", "")
    el_key = element.get("ElementKey", element.get("IdElement", ""))
    id_vertex = element.get("IdVertex", "0")
    if el_type == "Node":
        pos_label = "Node"
    elif id_vertex in ("", "0"):
        pos_label = "Baricentric"
    else:
        pos_label = f"Node{id_vertex}"
    name = element.get("Name", "")
    description = element.get("Description", "")
    return {
        **record(element),
        "name": name or description,
        "description": description or name,
        "elementType": el_type,
        "elementKey": el_key,
        "idVertex": id_vertex,
        "elementLabel": f"{el_type} ({el_key})" if el_type or el_key else "",
        "positionLabel": pos_label if el_type else "",
        "point": vector(element.get("Point")),
        "pointRaw": element.get("Point", ""),
    }


def _resolve_combination_value(condition, type_data, secondary_type, val):
    """Replicate C# LoadTemplateManager.GetCoefficient(LoadCondition, CombinationCoefficientData)."""
    if type_data == "Number":
        return val
    if type_data in ("Psi0", "Psi1", "Psi2"):
        return val if secondary_type == "Number" else f"{secondary_type} * {val}"
    if type_data in GAMMA_COEFFICIENTS:
        base = condition.get(type_data, val) if condition is not None else val
        return base if secondary_type in ("", "Number") else f"{base} * {secondary_type}"
    return val


def _load_combinations(root):
    conditions = list(root.findall("LoadCondition"))
    cond_by_id = {c.get("Id", c.get("Key", "")): c for c in conditions}
    result = []
    for element in root.findall("LoadCombination"):
        rows = {}
        for item in element.findall("Item"):
            row_key = item.get("RowKey", "1")
            row = rows.setdefault(row_key, {
                "rowKey": row_key,
                "name": item.get("Name", row_key),
                "schema": item.get("Schema", ""),
                "position": item.get("Position", ""),
                "combination": item.get("Combination", ""),
                "items": [],
            })
            col_key = item.get("ColumnKey", "")
            cond = None
            try:
                idx = int(col_key) - 1
                if 0 <= idx < len(conditions):
                    cond = conditions[idx]
            except (TypeError, ValueError):
                pass
            if cond is None:
                cond = cond_by_id.get(col_key)
            type_data = item.get("TypeData", "")
            secondary = item.get("SecondaryTypeData", "")
            val = item.get("Val", "")
            row["items"].append({
                "columnKey": col_key,
                "conditionKey": cond.get("Id", cond.get("Key", col_key)) if cond is not None else col_key,
                "conditionName": cond.get("Name", f"Condition {col_key}") if cond is not None else f"Condition {col_key}",
                "coefficient": type_data,
                "secondaryTypeData": secondary,
                "val": val,
                "value": _resolve_combination_value(cond, type_data, secondary, val),
                "attributes": dict(item.attrib),
            })
        result.append({
            **record(element),
            "description": element.get("Description", ""),
            "limitState": element.get("LimitState", ""),
            "subCombinations": list(rows.values()),
        })
    return result


def _load_functions(root):
    items_by_fn = {}
    for item in root.findall("LoadFunctionItem"):
        fn_key = item.get("loadFunctionKey", item.get("LoadFunctionKey", ""))
        items_by_fn.setdefault(fn_key, []).append({
            "key": item.get("key", item.get("Key", "")),
            "loadFunctionKey": fn_key,
            "pseudoTime": item.get("pseudoTime", item.get("PseudoTime", "")),
            "multiplier": item.get("multiplier", item.get("Multiplier", "")),
            "attributes": dict(item.attrib),
        })
    result = []
    for element in root.findall("LoadFunction"):
        key = element.get("key", element.get("Key", ""))
        nested = [{
            "key": item.get("key", item.get("Key", "")),
            "loadFunctionKey": key,
            "pseudoTime": item.get("pseudoTime", item.get("PseudoTime", "")),
            "multiplier": item.get("multiplier", item.get("Multiplier", "")),
            "attributes": dict(item.attrib),
        } for item in element.findall("LoadFunctionItem")]
        result.append({
            "key": key,
            "typeDiscr": element.get("typeDiscr", element.get("TypeDiscr", "")),
            "discrVal": element.get("DiscrVal", element.get("discrVal", "")),
            "attributes": dict(element.attrib),
            "items": items_by_fn.get(key, nested),
        })
    return result


def _analyses(root, templates=None, load_combinations=None, load_functions=None, model_points=None):
    """Project analysis definitions and their saved execution state."""
    templates = templates or {e.get("Key"): e for e in root.findall("Template")}
    combo_list = load_combinations if load_combinations is not None else _load_combinations(root)
    combinations = {c["key"]: c for c in combo_list}
    fn_list = load_functions if load_functions is not None else _load_functions(root)
    functions = {f["key"]: f for f in fn_list}
    mp_list = model_points if model_points is not None else [_model_point_record(e) for e in root.findall("ModelPoint")]
    points = {p["key"]: p for p in mp_list}
    analyses = list(root.findall("Analysis"))
    names = {e.get("Key"): e.get("Name", "") for e in analyses}
    result = []
    for element in analyses:
        states = [dict(s.attrib) for s in element.findall("States/State")]
        state = states[-1] if states else {}
        is_executed = any(
            s.get("State") in ("ExecutedCompleted", "ExecutedNotCompleted", "ExecutedNotStarted")
            for s in states
        )
        combination = combinations.get(element.get("LoadCombinationKey"))
        function = functions.get(element.get("LoadFunctionKey"))
        master_key = element.get("MasterPoint", "")
        master = points.get(master_key)
        if master is not None:
            master_name = master.get("name") or master.get("description", "")
        elif master_key == "-10":
            master_name = "MaxDisplacement"
        else:
            master_name = ""
        active_list = [dict(item.attrib) for item in element.findall("ActiveModelPoints/ActiveModelPoint")]
        displ_list = [dict(item.attrib) for item in element.findall("DisplModelPoints/DisplModelPoint")]
        active_map = {item.get("Key", ""): item.get("Value", "") for item in active_list}
        displ_map = {item.get("Key", ""): item.get("Value", "") for item in displ_list}
        seen_mp_keys = list(dict.fromkeys(
            [p["key"] for p in mp_list] + list(active_map.keys()) + list(displ_map.keys())
        ))
        analysis_points = []
        for mp_key in seen_mp_keys:
            if not mp_key:
                continue
            base_mp = points.get(mp_key, {
                "key": mp_key, "name": "", "description": "", "elementType": "",
                "elementKey": "", "idVertex": "", "elementLabel": "", "positionLabel": "",
                "point": None, "pointRaw": "", "attributes": {},
            })
            analysis_points.append({
                **base_mp,
                "active": active_map.get(mp_key, "false"),
                "displacement": displ_map.get(mp_key, "0"),
                "isMaster": mp_key == master_key,
            })
        stage_defs = []
        for sd in element.findall("StageDefinitions/StageDefinition"):
            g1 = templates.get(sd.get("GroupKey1", ""))
            g2 = templates.get(sd.get("GroupKey2", ""))
            mat = templates.get(sd.get("MaterialKey", ""))
            stage_defs.append({
                **dict(sd.attrib),
                "groupName1": g1.get("Name", "-") if g1 is not None else "-",
                "groupName2": g2.get("Name", "-") if g2 is not None else "-",
                "materialName": mat.get("Name", "-") if mat is not None else "-",
            })
        main_group_key = element.get("MainGroupKey", "")
        main_group = templates.get(main_group_key)
        result.append({
            **record(element),
            "analysisType": element.get("AnalysisType", ""),
            "type": ANALYSIS_TYPES.get(element.get("AnalysisType", ""),
                                       f"Type {element.get('AnalysisType', '')}"),
            "description": element.get("Description", ""),
            "loadCombinationKey": element.get("LoadCombinationKey", ""),
            "loadCombinationName": combination.get("name", "") if combination is not None else "",
            "loadCombination": combination,
            "loadFunctionKey": element.get("LoadFunctionKey", ""),
            "loadFunctionDiscr": function.get("discrVal", "") if function is not None else "",
            "loadFunction": function,
            "initialAnalysisKey": element.get("InitialAnalysisKey", ""),
            "initialAnalysisName": names.get(element.get("InitialAnalysisKey"), ""),
            "pushModalAnalysisKey": element.get("PushModal_ModalAnalysisKey", ""),
            "pushModalAnalysisName": names.get(element.get("PushModal_ModalAnalysisKey"), ""),
            "mainGroupName": main_group.get("Name", "") if main_group is not None else "",
            "masterPoint": master_key,
            "masterPointName": master_name,
            "state": state,
            "states": states,
            "stateCount": len(states),
            "isExecuted": is_executed,
            "activeModelPoints": active_list,
            "displacementModelPoints": displ_list,
            "modelPoints": analysis_points,
            "dynamicLoads": [dict(item.attrib) for item in element.findall("DynamicLoads/DynamicLoad")],
            "stageDefinitions": stage_defs,
            "stageItems": [dict(item.attrib) for item in element.findall("StageItems/StageItem")],
            "adapticPhases": [dict(item.attrib) for item in element.findall("AdapticPhases/AdapticPhase")],
            "pushModalSettings": [dict(item.attrib) for item in element.findall("PushModalSettings/PushModalSet")],
        })
    return result


def parse_hrx(data: bytes, name="Model.hrx"):
    # Decode before rejecting declarations, including UTF-16 HRX exports.
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = data.decode(encoding)
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        raise ValueError("DTD/entity declarations are not supported.")
    root = ET.fromstring(text)
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    if root.tag != "HiStrA":
        raise ValueError("Expected a HiStrA HRX model.")
    warnings = []
    nodes = {}
    for e in root.findall("Node"):
        key, point = e.get("Key"), vector(e.get("Point"))
        if key in nodes:
            raise ValueError(f"Duplicate Node key {key}.")
        if point is None:
            raise ValueError(f"Node {key} has invalid coordinates.")
        nodes[key] = {**record(e), "point": point}
    quads = []
    seen = set()
    for e in root.findall("Quad"):
        key = e.get("Key")
        refs = [e.get(f"NodeKey{i}") for i in range(1, 5)]
        if key in seen or len(set(refs)) != 4 or any(k not in nodes for k in refs):
            raise ValueError(f"Quad {key} has duplicate keys or invalid node references.")
        seen.add(key)
        reference = e.find("ReferenceSystem")
        quads.append({**record(e), "nodeKeys": refs, "materialKey": e.get("MaterialKey", "0"),
                      "layerKey": e.get("LayerKey", "0"), "parentKey": e.get("ParentKey", "0"),
                      "parentTypeElement": e.get("ParentTypeElement", ""),
                      "thicknesses": [number(e.get(f"Thickness{i}")) for i in range(1, 5)],
                      "normals": [vector(e.get(f"Normal{i}")) for i in range(1, 5)],
                      "referenceSystem": dict(reference.attrib) if reference is not None else {}})
    if not quads:
        raise ValueError("No serialized Quad mesh found. Generate the mesh before viewing this model.")
    templates = {e.get("Key"): e for e in root.findall("Template")}
    used_materials = Counter(q["materialKey"] for q in quads)
    materials = []
    for key, count in used_materials.items():
        e = templates.get(key)
        if e is None:
            warnings.append(f"Material {key} is referenced but has no definition.")
        materials.append({**(record(e) if e is not None else {"key": key, "name": f"Material {key}", "attributes": {}}),
                          "color": color(e.get("Color")) if e is not None else "#7ca7c7", "quadCount": count})
    material_library = [{**record(e), "color": color(e.get("Color")),
                         "quadCount": used_materials.get(key, 0)}
                        for key, e in templates.items()
                        if "Material" in e.get("PurposeType", "") or "Material" in e.get("TypeOf", "")]
    known_keys = {m["key"] for m in material_library}
    material_library.extend(m for m in materials if m["key"] not in known_keys)
    restraints = _restraints(root, nodes, warnings)
    loads = _loads(root, templates, nodes, warnings)
    counts = Counter(e.tag for e in root)
    unsupported = {tag: counts[tag] for tag in ("Frame", "Truss", "Solid", "Vertex") if counts[tag]}
    if unsupported:
        warnings.append(f"This version renders Quad meshes; other element families are not drawn: {unsupported}.")
    points = [n["point"] for n in nodes.values()]
    load_combinations = _load_combinations(root)
    load_functions = _load_functions(root)
    model_points = [_model_point_record(e) for e in root.findall("ModelPoint")]
    wizard = root.find('WizardData')
    return {"schemaVersion": 1, "name": name, "metadata": dict(root.attrib),
            "pierCount": len(wizard.findall('Pier')) if wizard is not None else 0,
            "units": "HRX native units", "nodes": list(nodes.values()), "quads": quads,
            "materials": materials, "materialLibrary": material_library,
            "layers": [record(e) for e in root.findall("Layer")],
            "restraints": restraints, "loads": loads,
            "loadConditions": [record(e) for e in root.findall("LoadCondition")],
            "loadCombinations": load_combinations,
            "loadFunctions": load_functions,
            "loadTemplates": [{**record(e), "items": [dict(i.attrib) for i in e.iter("LoadTemplateItem")]} for e in templates.values() if "LoadTemplate" in e.get("TypeOf", "")],
            "analyses": _analyses(root, templates, load_combinations, load_functions, model_points),
            "modelPoints": model_points,
            "bounds": {"min": [min(p[i] for p in points) for i in range(3)],
                       "max": [max(p[i] for p in points) for i in range(3)]},
            "sourceCounts": dict(counts), "warnings": warnings}


def _restraints(root, nodes, warnings):
    result, represented = [], set()
    for tag in ("Restraint", "GeometryLineRestraint", "GeometryPointRestraint", "SurfaceRestraint"):
        for e in root.findall(tag):
            if (tag, e.get("Key")) in represented:
                continue
            points = geometry_points(e)
            if not points:
                points = [nodes[k]["point"] for k in (e.get("NodeKey1"), e.get("NodeKey2"), e.get("NodeKey")) if k in nodes]
            if not points:
                point = vector(e.get("G"))
                points = [point] if point is not None else []
            if not points:
                warnings.append(f"{tag} {e.get('Key')} has no display geometry.")
            stiffness = []
            dofs = {}
            for direction, index in zip(("U1", "U2", "U3", "R1", "R2", "R3"), range(6)):
                behaviour = e.get(f"{direction}mechBehaviourType", "Unspecified")
                attr = f"K{index + 1}" if index < 3 else f"Kr{index - 2}"
                raw = e.get(attr)
                value = float(raw) if raw not in (None, "") else None
                stiffness.append(value)
                dofs[direction] = (
                    "Elastic"
                    if behaviour == "Fixed" and value is not None and value > 0.0
                    else behaviour
                )
            result.append({**record(e), "id": f"{tag}:{e.get('Key')}", "type": tag,
                           "points": points, "dofs": dofs, "stiffness": stiffness,
                           "referenceSystem": dict(e.find("ReferenceSystem").attrib) if e.find("ReferenceSystem") is not None else {}})
            if tag == "Restraint":
                represented.add((e.get("ParentTypeElement"), e.get("ParentKey")))
    return result


def _loads(root, templates, nodes, warnings):
    targets = {(e.tag, e.get("Key")): e for e in root if e.get("Key")}
    result, assignments = [], []
    explicit = set()
    for e in root.findall("LoadElement"):
        target = targets.get((e.get("ElementType"), e.get("ElementKey")))
        kind = e.get("TypeOf", "").split(".")[-1].replace("Element", "")
        assignments.append((e, target, kind, e.get("IdLoadTemplate"), geometry_points(e), "LoadElement"))
        explicit.add((e.get("ElementType"), e.get("ElementKey"), e.get("IdLoadTemplate")))
    for q in root.findall("Quad"):
        for kind in ("Area", "Line", "Point"):
            template_key = q.get(f"LoadTemplate{kind}Key", "0")
            if template_key == "0" or ("Quad", q.get("Key"), template_key) in explicit:
                continue
            if kind == "Area":
                points = [nodes[q.get(f"NodeKey{i}")]["point"] for i in range(1, 5)]
            else:
                fields = ("LoadTemplateLinePoint1", "LoadTemplateLinePoint2") if kind == "Line" else ("LoadTemplatePointPoint",)
                points = [vector(q.get(f)) for f in fields]
                points = [p for p in points if p is not None]
            assignments.append((q, q, kind + "Load", template_key, points, "Quad assignment"))
    for source, target, kind, key, points, origin in assignments:
        template = templates.get(key)
        items = list(template.iter("LoadTemplateItem")) if template is not None else []
        if not items:
            warnings.append(f"Load on {source.tag} {source.get('Key')} has missing/empty template {key}.")
        for item in items:
            load_direction = direction(item, target)
            supported = kind in ("LineLoad", "PointLoad", "AreaLoad") and bool(points) and load_direction is not None and item.get("IdTypeLoad", "Force") == "Force"
            if not supported:
                warnings.append(f"Load {source.get('Key')} / template {key} is listed but cannot yet be drawn ({kind}, {item.get('IdTypeLoad')}).")
            result.append({"id": f"{origin}:{source.get('Key')}:{kind}:{item.get('Key')}",
                           "key": source.get("Key"), "name": template.get("Name", "") if template is not None else "Unknown load",
                           "kind": kind, "source": origin, "elementKey": target.get("Key") if target is not None else source.get("ElementKey"),
                           "elementType": target.tag if target is not None else source.get("ElementType"),
                           "templateKey": key, "conditionKey": item.get("IdLoadCondition", "0"),
                           "value": number(item.get("LoadValue")), "direction": load_direction,
                           "points": points, "drawable": supported, "attributes": dict(item.attrib)})
    return result
