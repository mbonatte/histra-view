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
    return {"schemaVersion": 1, "name": name, "metadata": dict(root.attrib),
            "units": "HRX native units", "nodes": list(nodes.values()), "quads": quads,
            "materials": materials, "materialLibrary": material_library,
            "layers": [record(e) for e in root.findall("Layer")],
            "restraints": restraints, "loads": loads,
            "loadConditions": [record(e) for e in root.findall("LoadCondition")],
            "loadTemplates": [{**record(e), "items": [dict(i.attrib) for i in e.iter("LoadTemplateItem")]} for e in templates.values() if "LoadTemplate" in e.get("TypeOf", "")],
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
            result.append({**record(e), "id": f"{tag}:{e.get('Key')}", "type": tag,
                           "points": points, "dofs": {d: e.get(f"{d}mechBehaviourType", "Unspecified") for d in ("U1", "U2", "U3", "R1", "R2", "R3")},
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
