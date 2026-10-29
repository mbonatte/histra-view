"""Project a native ``.histra`` result archive for the browser viewer.

A ``.histra`` file is a ZIP container with a ``manifest.json``, one HRX model
member and a content-addressed object store. Arrays use the documented
``byte-shuffle-v1`` encoding. The archive is read-only; no model preparation or
solver run is performed.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import copy
import hashlib
import io
import json
import zipfile

import numpy as np

from bridge_v2 import (
    VIEWER_UNITS,
    _analysis,
    _contours_payload,
    _interface_payload,
    _mesh,
)
from hrx_model import parse_hrx

DEFAULT_CASE = "Interface_Span2_Quarter"
_MANIFEST_CACHE: dict[str, tuple[tuple[int, int], dict, object]] = {}
_CASE_CACHE: OrderedDict[tuple[str, int, str], dict] = OrderedDict()
_CASE_CACHE_LIMIT = 4


def is_histra(path: str | Path) -> bool:
    return Path(path).suffix.lower() == ".histra"


def _stamp(path: Path):
    return (path.stat().st_mtime_ns, path.stat().st_size)


def _read_manifest(archive: Path, stamp):
    key = str(archive.resolve())
    cached = _MANIFEST_CACHE.get(key)
    if cached and cached[0] == stamp:
        return cached[1], cached[2]
    with zipfile.ZipFile(archive) as zf:
        raw = json.loads(zf.read("manifest.json").decode("utf-8"))
        if raw.get("format") != "histra-results":
            raise ValueError("Expected a histra-results archive.")
        if raw.get("schema_version") != "1.0.0":
            raise ValueError("Unsupported .histra result schema version.")
        if raw.get("array_encoding") != "byte-shuffle-v1":
            raise ValueError("Unsupported .histra array encoding.")
        models = raw.get("models") or {}
        if len(models) != 1:
            raise ValueError("Expected exactly one HRX model in the .histra archive.")
        model_info = next(iter(models.values()))
        member = model_info.get("member")
        if not member:
            raise ValueError("The .histra archive has no model member.")
        model_bytes = zf.read(member)
        expected = str(model_info.get("sha256", "")).lower()
        actual = hashlib.sha256(model_bytes).hexdigest()
        if expected and actual != expected:
            raise ValueError("The .histra model member does not match its declared SHA-256.")
        model = parse_hrx(model_bytes, str(model_info.get("filename", Path(member).name)))
    _MANIFEST_CACHE.clear()
    _MANIFEST_CACHE[key] = (stamp, raw, model)
    return raw, model


def _decode_object(zf: zipfile.ZipFile, manifest: dict, object_hash: str):
    metadata = manifest.get("objects", {}).get(object_hash)
    if metadata is None:
        raise ValueError(f"Missing .histra object metadata for {object_hash}.")
    member = f"objects/{object_hash}.bin"
    try:
        data = zf.read(member)
    except KeyError as exc:
        raise ValueError(f"Missing .histra object {object_hash}.") from exc
    dtype = np.dtype(metadata["dtype"])
    shape = tuple(int(value) for value in metadata.get("shape", []))
    nbytes = int(metadata["nbytes"])
    if len(data) != nbytes:
        raise ValueError(f".histra object {object_hash} has an unexpected byte length.")
    if dtype.kind in "US" or dtype.itemsize == 1:
        array = np.frombuffer(data, dtype=dtype)
    else:
        count = nbytes // dtype.itemsize
        if count * dtype.itemsize != nbytes:
            raise ValueError(f".histra object {object_hash} has an invalid dtype size.")
        shuffled = np.frombuffer(data, dtype=np.uint8)
        if shuffled.size != count * dtype.itemsize:
            raise ValueError(f".histra object {object_hash} is incomplete.")
        unshuffled = shuffled.reshape(dtype.itemsize, count).T.copy().tobytes()
        array = np.frombuffer(unshuffled, dtype=dtype)
    try:
        return array.reshape(shape)
    except ValueError as exc:
        raise ValueError(f".histra object {object_hash} has an invalid shape.") from exc


def _read_case(archive: Path, stamp, manifest: dict, case_id: str):
    key = (str(archive.resolve()), stamp[0], case_id)
    cached = _CASE_CACHE.get(key)
    if cached is not None:
        _CASE_CACHE.move_to_end(key)
        return cached
    case = (manifest.get("cases") or {}).get(case_id)
    if case is None:
        raise ValueError(f"Analysis {case_id!r} is not present in the .histra archive.")
    with zipfile.ZipFile(archive) as zf:
        arrays = {
            name: _decode_object(zf, manifest, object_hash)
            for name, object_hash in case.get("arrays", {}).items()
        }
    _CASE_CACHE[key] = arrays
    _CASE_CACHE.move_to_end(key)
    while len(_CASE_CACHE) > _CASE_CACHE_LIMIT:
        _CASE_CACHE.popitem(last=False)
    return arrays


def _catalog(manifest: dict):
    catalog = []
    for case_id, case in (manifest.get("cases") or {}).items():
        summary = case.get("summary") or {}
        curve = summary.get("curve") or {}
        steps = len(curve.get("step", []))
        if not steps:
            steps = int((summary.get("metrics") or {}).get("total_steps", 0) or 0)
        catalog.append({
            "name": case_id,
            "label": case_id,
            "steps": steps,
            "curveOnly": bool(case.get("curve_only", False)),
        })
    return catalog


def _resolve_case(manifest: dict, analysis_name: str | None):
    cases = manifest.get("cases") or {}
    if not cases:
        raise ValueError("The .histra archive contains no result cases.")
    if analysis_name:
        if analysis_name in cases:
            return analysis_name
        lowered = str(analysis_name).lower()
        for case_id in cases:
            if case_id.lower() == lowered:
                return case_id
    preferred = manifest.get("default_case") or DEFAULT_CASE
    if preferred in cases:
        return preferred
    return next(iter(cases))


def _case_context(archive: Path, analysis_name: str | None):
    archive = Path(archive)
    stamp = _stamp(archive)
    manifest, model = _read_manifest(archive, stamp)
    case_id = _resolve_case(manifest, analysis_name)
    arrays = _read_case(archive, stamp, manifest, case_id)
    case = manifest["cases"][case_id]
    summary = copy.deepcopy(case.get("summary") or {})
    summary.setdefault("metadata", {})
    summary["metadata"]["analysis_name"] = case_id
    summary["metadata"]["case_id"] = case_id
    summary["metadata"]["model_sha256"] = str(case.get("model_sha256", summary["metadata"].get("model_sha256", "")))
    entry = {"case_id": case_id}
    return archive, manifest, model, arrays, case, summary, entry, case_id




def _is_modal_arrays(arrays):
    return "modal/node_displacements" in arrays and "mesh/node_coordinates" in arrays


def _is_inline_modal_arrays(arrays):
    return "modal_mode_shapes" in arrays and "mesh/node_keys" in arrays


def _modal_mesh(archive: Path, model, arrays):
    keys = np.asarray(arrays["mesh/node_keys"]).astype(int)
    coordinates = np.asarray(arrays["mesh/node_coordinates"], dtype=float)
    if len(keys) != len(coordinates):
        raise ValueError("Modal mesh node keys and coordinates do not match.")
    nodes = []
    for key, point in zip(keys, coordinates):
        if not np.isfinite(point).all():
            raise ValueError(f"Node {key} has a nonfinite modal coordinate.")
        nodes.append({
            "key": str(int(key)),
            "name": str(int(key)),
            "point": [float(value) for value in point],
        })
    model_nodes = {int(node["key"]) for node in model["nodes"]}
    missing = [int(key) for key in keys if int(key) not in model_nodes]
    if missing:
        # The modal archive also stores interface-only nodes. They are valid
        # viewer nodes and do not invalidate the Quad mesh.
        pass
    quads = []
    for quad in model["quads"]:
        node_keys = [str(int(key)) for key in quad["nodeKeys"]]
        quads.append({
            "key": str(int(quad["key"])),
            "name": str(quad.get("name", quad["key"])),
            "nodeKeys": node_keys,
            "materialKey": str(int(quad["materialKey"])),
            "thicknesses": [float(value) for value in quad["thicknesses"]],
            "normals": [[float(value) for value in normal] for normal in quad["normals"]],
        })
    materials = [{
        "key": str(int(material["key"])),
        "name": str(material.get("name", material["key"])),
        "color": str(material.get("color", "#6fb7ff")),
    } for material in model.get("materials", [])]
    return {
        "name": archive.name,
        "nodes": nodes,
        "quads": quads,
        "materials": materials,
        "interfaces": {},
        "thrustPairs": [],
    }


def _modal_analysis(case_id, mesh, arrays, summary):
    keys = np.asarray(arrays["mesh/node_keys"]).astype(int)
    node_count = len(keys)
    displacement = np.asarray(arrays["modal/node_displacements"], dtype=np.float32)
    if displacement.ndim != 3 or displacement.shape[0] < 1 or displacement.shape[1] != node_count or displacement.shape[2] != 3:
        raise ValueError("Modal node displacements have an unexpected shape.")
    frequencies = np.asarray(arrays.get("modal/frequencies_hz", []), dtype=float)
    periods = np.asarray(arrays.get("modal/periods_s", []), dtype=float)
    numbers = np.asarray(arrays.get("modal/mode_numbers", np.arange(1, displacement.shape[0] + 1)), dtype=int)
    mass_x = np.asarray(arrays.get("modal/mass_percent_x", np.zeros(displacement.shape[0])), dtype=float)
    mass_y = np.asarray(arrays.get("modal/mass_percent_y", np.zeros(displacement.shape[0])), dtype=float)
    mass_z = np.asarray(arrays.get("modal/mass_percent_z", np.zeros(displacement.shape[0])), dtype=float)
    if not (len(frequencies) == len(periods) == len(numbers) == displacement.shape[0]):
        raise ValueError("Modal metadata does not match the mode-shape count.")
    modes = []
    for index in range(displacement.shape[0]):
        values = np.asarray(displacement[index], dtype=float)
        maximum = float(np.max(np.linalg.norm(values, axis=1))) if len(values) else 0.0
        if maximum > 0:
            values = values / maximum
        modes.append({
            "number": int(numbers[index]),
            "frequency": float(frequencies[index]),
            "period": float(periods[index]),
            "massPercent": [float(mass_x[index]), float(mass_y[index]), float(mass_z[index])],
            "displacements": np.round(values, 6).tolist(),
        })
    metadata = (summary or {}).get("metadata", {})
    modal_name = str(metadata.get("analysis_name") or "Modal")
    zero = [[0.0, 0.0, 0.0] for _ in range(node_count)]
    step = {
        "step": 0,
        "status": "Committed",
        "controlDisplacement": 0.0,
        "loadFactor": None,
        "displacements": zero,
        "quadDisplacements": None,
        "interfaceResultants": [],
        "reactions": [0.0, 0.0, 0.0],
        "energies": {"elastic": None, "dissipated": None},
    }
    analysis = {
        "name": case_id,
        "outcome": "Modal analysis",
        "steps": [step],
        "diagnostics": {"equilibriumCheckedSteps": 0, "equilibriumFailedSteps": 0},
        "interfaces": [],
        "interfaceOrder": [],
        "finalStress": None,
        "stressFields": [],
        "curveOnly": True,
    }
    return analysis, [{"name": modal_name, "modes": modes}]


def _attachment_vector(raw):
    if raw is None:
        return None
    try:
        values = [float(part) for part in str(raw).split(";")]
    except ValueError:
        return None
    return values if len(values) == 3 else None


def _attachment_modal_pairs(manifest):
    attachments = manifest.get("attachments") or {}
    pairs = []
    for name in sorted(attachments):
        if not name.endswith("_values.json"):
            continue
        case_id = name[:-len("_values.json")]
        shapes_name = f"{case_id}_shapes.npz"
        if shapes_name not in attachments:
            continue
        pairs.append((case_id, name, shapes_name))
    return pairs


def _project_full_dof_modes(shapes, node_keys, node_xyz, quad_keys, quad_conn, model, mode_meta):
    """Project full 7-DOF Quad eigenvectors onto the rendered node mesh."""
    expected = len(quad_keys) * 7
    shapes = np.asarray(shapes, dtype=float)
    if shapes.ndim != 2:
        return []
    if shapes.shape[1] != expected and shapes.shape[0] == expected:
        shapes = shapes.T
    if shapes.shape[1] != expected:
        return []
    node_index = {int(key): index for index, key in enumerate(node_keys)}
    block_keys = sorted(int(key) for key in quad_keys)
    block_position = {key: index for index, key in enumerate(block_keys)}
    conn_by_key = {int(key): quad_conn[index] for index, key in enumerate(quad_keys)}
    hrx_quads = {int(quad["key"]): quad for quad in model.get("quads", [])}
    geometries = []
    for quad_key in block_keys:
        corners = conn_by_key[quad_key]
        vertices = np.asarray(
            [node_xyz[node_index[int(key)]] for key in corners], dtype=float
        )
        hrx = hrx_quads.get(quad_key, {})
        attributes = hrx.get("attributes", {})
        center = _attachment_vector(attributes.get("G"))
        if center is None:
            center = vertices.mean(axis=0)
        reference = hrx.get("referenceSystem") or {}
        e1 = _attachment_vector(reference.get("E1"))
        if e1 is None:
            e1 = vertices[1] - vertices[0]
        e1 = np.asarray(e1, dtype=float)
        e1_norm = np.linalg.norm(e1)
        e1 = e1 / e1_norm if e1_norm > 1e-12 else np.asarray([1.0, 0.0, 0.0])
        e2 = _attachment_vector(reference.get("E2"))
        if e2 is None:
            normal = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
            normal_norm = np.linalg.norm(normal)
            e2 = np.cross(normal / normal_norm, e1) if normal_norm > 1e-12 else np.asarray([0.0, 1.0, 0.0])
        else:
            e2 = np.asarray(e2, dtype=float)
        lengths = []
        sins = []
        cosines = []
        for index in range(4):
            edge = vertices[(index + 1) % 4] - vertices[index]
            lengths.append(float(attributes.get(f"Length{index + 1}", np.linalg.norm(edge))))
            sins.append(float(attributes.get(f"Sin{index + 1}", 0.0)))
            cosines.append(float(attributes.get(f"Cos{index + 1}", 0.0)))
        geometries.append({
            "position": block_position[quad_key],
            "center": center,
            "e1": e1,
            "e2": e2,
            "lengths": lengths,
            "sins": sins,
            "cosines": cosines,
            "nodes": [node_index[int(key)] for key in corners],
        })

    modes = []
    for mode_index in range(min(len(mode_meta), shapes.shape[0])):
        blocks = shapes[mode_index].reshape(len(block_keys), 7)
        totals = np.zeros((len(node_keys), 3), dtype=float)
        counts = np.zeros(len(node_keys), dtype=int)
        for geometry in geometries:
            local = blocks[geometry["position"]]
            translation = np.asarray(local[:3], dtype=float)
            rotation = np.asarray(local[3:6], dtype=float)
            shear = float(local[6])
            for vertex_index, node_index_value in enumerate(geometry["nodes"]):
                base = np.asarray(node_xyz[node_index_value], dtype=float)
                displacement = translation + np.cross(rotation, base - geometry["center"])
                if vertex_index == 2 and abs(geometry["sins"][2]) > 1e-30:
                    coefficient = (
                        -geometry["lengths"][3] * geometry["sins"][3]
                        / geometry["sins"][2]
                    )
                    displacement = displacement + shear * coefficient * (
                        geometry["sins"][1] * geometry["e1"]
                        + geometry["cosines"][1] * geometry["e2"]
                    )
                elif vertex_index == 3:
                    displacement = displacement + shear * geometry["lengths"][3] * (
                        -geometry["sins"][0] * geometry["e1"]
                        + geometry["cosines"][0] * geometry["e2"]
                    )
                totals[node_index_value] += displacement
                counts[node_index_value] += 1
        valid = counts > 0
        if valid.any():
            totals[valid] /= counts[valid, None]
        maximum = float(np.max(np.linalg.norm(totals, axis=1))) if len(totals) else 0.0
        if maximum > 0:
            totals /= maximum
        meta = mode_meta[mode_index]
        modes.append({
            "number": int(meta.get("number", mode_index + 1)),
            "frequency": float(meta.get("frequency", 0.0)),
            "period": float(meta.get("period", 0.0)),
            "massPercent": [float(value) for value in meta.get("massPercent", [0.0, 0.0, 0.0])],
            "displacements": np.round(totals, 6).tolist(),
        })
    return modes


def _inline_modal_entries(case_id, arrays, model, summary):
    modal = summary.get("modal") or {}
    values = modal.get("modal_values") or []
    frequencies = np.asarray(arrays.get("modal_frequencies", []), dtype=float)
    periods = np.asarray(arrays.get("modal_periods", []), dtype=float)
    metadata = []
    for index, row in enumerate(values):
        frequency = float(row.get("Fn", frequencies[index] if index < len(frequencies) else 0.0))
        metadata.append({
            "number": int(row.get("Step", index + 1)),
            "frequency": frequency,
            "period": float(row.get("Tn", periods[index] if index < len(periods) else 0.0)),
            "massPercent": [
                float(row.get("Mx_pcent", 0.0)),
                float(row.get("My_pcent", 0.0)),
                float(row.get("Mz_pcent", 0.0)),
            ],
        })
    if not metadata:
        metadata = [
            {"number": index + 1, "frequency": float(frequencies[index]) if index < len(frequencies) else 0.0,
             "period": float(periods[index]) if index < len(periods) else 0.0,
             "massPercent": [0.0, 0.0, 0.0]}
            for index in range(len(frequencies))
        ]
    modes = _project_full_dof_modes(
        arrays.get("modal_mode_shapes", []),
        np.asarray(arrays["mesh/node_keys"]).astype(int),
        np.asarray(arrays["mesh/nodes_xyz"], dtype=float),
        np.asarray(arrays["mesh/quad_keys"]).astype(int),
        np.asarray(arrays["mesh/quad_conn"]).astype(int),
        model,
        metadata,
    )
    return [{"name": case_id, "modes": modes}] if modes else []


def _attachment_modal_descriptors(archive, manifest):
    """Return lightweight mode metadata without loading any mode shapes."""
    pairs = _attachment_modal_pairs(manifest)
    if not pairs:
        return []
    modal = []
    with zipfile.ZipFile(archive) as zf:
        for case_id, values_name, _shapes_name in pairs:
            try:
                values = json.loads(zf.read(manifest["attachments"][values_name]["member"]).decode("utf-8"))
            except (KeyError, ValueError, OSError, json.JSONDecodeError):
                continue
            modes = []
            for index, meta in enumerate(values.get("modes") or []):
                frequency = float(meta.get("frequency_hz", 0.0))
                modes.append({
                    "number": int(meta.get("mode", index + 1)),
                    "frequency": frequency,
                    "period": float(meta.get("period_s", 1.0 / frequency if frequency else 0.0)),
                    "massPercent": [
                        float(meta.get("mass_percent_x", 0.0)),
                        float(meta.get("mass_percent_y", 0.0)),
                        float(meta.get("mass_percent_z", 0.0)),
                    ],
                })
            if modes:
                modal.append({"name": case_id, "modes": modes, "lazy": True})
    return modal


def _attachment_modal_entries(archive, manifest, model, selected_arrays, selected_case,
                              case_filter=None):
    """Project modal attachment JSON/NPZ pairs into the viewer mode catalog.

    Newer ``.histra`` writers keep modes beside a static case as
    ``<case>_values.json`` + ``<case>_shapes.npz``.  The shape vector uses the
    solver's 7-DOF Quad order (three translations, three rotations and one
    shear/warping DOF), so project each Quad contribution to its four nodes
    and average shared nodes exactly as the static node output does.
    """
    pairs = _attachment_modal_pairs(manifest)
    if not pairs:
        return []
    modal = []
    with zipfile.ZipFile(archive) as zf:
        for case_id, values_name, shapes_name in pairs:
            if case_filter is not None and case_id != case_filter:
                continue
            try:
                values_entry = manifest["attachments"][values_name]
                shapes_entry = manifest["attachments"][shapes_name]
                values = json.loads(zf.read(values_entry["member"]).decode("utf-8"))
                with np.load(io.BytesIO(zf.read(shapes_entry["member"])), allow_pickle=False) as data:
                    shapes = np.asarray(data["shapes"], dtype=float)
                    frequencies = np.asarray(data.get("frequencies", []), dtype=float)
            except (KeyError, ValueError, OSError, json.JSONDecodeError):
                continue
            if case_id not in (manifest.get("cases") or {}):
                continue
            arrays = selected_arrays if case_id == selected_case else _read_case(
                archive, _stamp(archive), manifest, case_id
            )
            node_keys = np.asarray(arrays["mesh/node_keys"]).astype(int)
            node_xyz = np.asarray(arrays["mesh/nodes_xyz"], dtype=float)
            quad_keys = np.asarray(arrays["mesh/quad_keys"]).astype(int)
            quad_conn = np.asarray(arrays["mesh/quad_conn"]).astype(int)
            if shapes.ndim != 2 or len(quad_keys) == 0:
                continue
            expected_shapes = len(quad_keys) * 7
            if shapes.shape[1] != expected_shapes and shapes.shape[0] == expected_shapes:
                shapes = shapes.T
            if shapes.shape[1] != expected_shapes:
                continue
            node_index = {int(key): index for index, key in enumerate(node_keys)}
            block_keys = sorted(int(key) for key in quad_keys)
            block_position = {key: index for index, key in enumerate(block_keys)}
            conn_by_key = {int(key): quad_conn[index] for index, key in enumerate(quad_keys)}
            hrx_quads = {int(quad["key"]): quad for quad in model.get("quads", [])}
            quad_geometry = []
            for position, quad_key in enumerate(block_keys):
                corners = conn_by_key[quad_key]
                vertices = np.asarray(
                    [node_xyz[node_index[int(key)]] for key in corners],
                    dtype=float,
                )
                hrx = hrx_quads.get(quad_key, {})
                attributes = hrx.get("attributes", {})
                center = _attachment_vector(attributes.get("G"))
                if center is None:
                    center = vertices.mean(axis=0)
                reference = hrx.get("referenceSystem") or {}
                e1 = _attachment_vector(reference.get("E1"))
                if e1 is None:
                    e1 = vertices[1] - vertices[0]
                e1 = np.asarray(e1, dtype=float)
                e1_norm = np.linalg.norm(e1)
                if e1_norm <= 1e-12:
                    e1 = np.asarray([1.0, 0.0, 0.0])
                else:
                    e1 = e1 / e1_norm
                e2 = _attachment_vector(reference.get("E2"))
                if e2 is None:
                    normal = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
                    normal_norm = np.linalg.norm(normal)
                    e2 = np.cross(normal / normal_norm, e1) if normal_norm > 1e-12 else np.asarray([0.0, 1.0, 0.0])
                else:
                    e2 = np.asarray(e2, dtype=float)
                lengths = []
                sins = []
                cosines = []
                for index in range(4):
                    edge = vertices[(index + 1) % 4] - vertices[index]
                    lengths.append(float(attributes.get(f"Length{index + 1}", np.linalg.norm(edge))))
                    sins.append(float(attributes.get(f"Sin{index + 1}", 0.0)))
                    cosines.append(float(attributes.get(f"Cos{index + 1}", 0.0)))
                quad_geometry.append({
                    "position": block_position[quad_key],
                    "center": center,
                    "e1": e1,
                    "e2": e2,
                    "lengths": lengths,
                    "sins": sins,
                    "cosines": cosines,
                    "nodes": [node_index[int(key)] for key in corners],
                    "vertices": vertices,
                })

            mode_meta = values.get("modes") or []
            mode_count = min(len(mode_meta), shapes.shape[0])
            modes = []
            for mode_index in range(mode_count):
                blocks = shapes[mode_index].reshape(len(block_keys), 7)
                totals = np.zeros((len(node_keys), 3), dtype=float)
                counts = np.zeros(len(node_keys), dtype=int)
                for geometry in quad_geometry:
                    local = blocks[geometry["position"]]
                    translation = np.asarray(local[:3], dtype=float)
                    rotation = np.asarray(local[3:6], dtype=float)
                    shear = float(local[6])
                    for vertex_index, node_index_value in enumerate(geometry["nodes"]):
                        point = geometry["vertices"][vertex_index]
                        displacement = translation + np.cross(rotation, point - geometry["center"])
                        if geometry["sins"][2] and abs(geometry["sins"][2]) > 1e-30 and vertex_index == 2:
                            coefficient = (
                                -geometry["lengths"][3] * geometry["sins"][3]
                                / geometry["sins"][2]
                            )
                            displacement = displacement + shear * coefficient * (
                                geometry["sins"][1] * geometry["e1"]
                                + geometry["cosines"][1] * geometry["e2"]
                            )
                        elif vertex_index == 3:
                            displacement = displacement + shear * geometry["lengths"][3] * (
                                -geometry["sins"][0] * geometry["e1"]
                                + geometry["cosines"][0] * geometry["e2"]
                            )
                        totals[node_index_value] += displacement
                        counts[node_index_value] += 1
                valid = counts > 0
                if valid.any():
                    totals[valid] /= counts[valid, None]
                maximum = float(np.max(np.linalg.norm(totals, axis=1))) if len(totals) else 0.0
                if maximum > 0:
                    totals /= maximum
                meta = mode_meta[mode_index]
                frequency = float(meta.get("frequency_hz", frequencies[mode_index] if mode_index < len(frequencies) else 0.0))
                period = float(meta.get("period_s", 1.0 / frequency if frequency else 0.0))
                mass = [
                    float(meta.get("mass_percent_x", 0.0)),
                    float(meta.get("mass_percent_y", 0.0)),
                    float(meta.get("mass_percent_z", 0.0)),
                ]
                modes.append({
                    "number": int(meta.get("mode", mode_index + 1)),
                    "frequency": frequency,
                    "period": period,
                    "massPercent": mass,
                    "displacements": np.round(totals, 6).tolist(),
                })
            if modes:
                modal.append({"name": case_id, "modes": modes})
    return modal


def project_histra(archive_path: str | Path, analysis_name: str | None = None,
                   include_face_grids: bool | None = None,
                   include_stress_fields: bool = True,
                   include_modal_shapes: bool = True):
    archive, manifest, model, arrays, _case, summary, entry, case_id = _case_context(archive_path, analysis_name)
    meta = summary.get("metadata", {})
    preferred = manifest.get("default_case") or DEFAULT_CASE
    catalog = _catalog(manifest)
    default = preferred if preferred in (manifest.get("cases") or {}) else catalog[0]["name"]
    if _is_inline_modal_arrays(arrays):
        mesh = _mesh(str(archive), arrays, hrx_model=model)
        mesh["name"] = archive.name
        analysis = _analysis(
            entry, summary, mesh, arrays,
            include_face_grids=False,
            include_stress_fields=False,
        )
        analysis["name"] = case_id
        modal = _inline_modal_entries(case_id, arrays, model, summary)
        return {
            "schemaVersion": 3,
            "sourceSchema": "histra-results-1.0.0",
            "modelSha256": meta.get("model_sha256"),
            "title": archive.stem,
            "name": archive.name,
            "sourceUnits": meta.get("units", {
                "length": "cm", "displacement": "cm", "force": "kN",
                "moment": "kN*cm", "stress": "MPa", "rotation": "rad",
            }),
            "units": VIEWER_UNITS,
            "mesh": mesh,
            "analyses": [analysis],
            "analysisCatalog": catalog,
            "defaultAnalysis": default,
            "lazyFields": True,
            "modal": modal,
        }
    if _is_modal_arrays(arrays):
        mesh = _modal_mesh(archive, model, arrays)
        analysis, _selected_modal = _modal_analysis(case_id, mesh, arrays, summary)
        modal = []
        for modal_case in [item["name"] for item in catalog]:
            case_arrays = arrays if modal_case == case_id else _read_case(
                archive, _stamp(archive), manifest, modal_case
            )
            case_summary = (manifest["cases"][modal_case].get("summary") or {})
            _, case_modal = _modal_analysis(modal_case, mesh, case_arrays, case_summary)
            case_modal[0]["name"] = modal_case
            modal.append(case_modal[0])
        return {
            "schemaVersion": 3,
            "sourceSchema": "histra-results-1.0.0",
            "modelSha256": meta.get("model_sha256"),
            "title": archive.stem,
            "name": archive.name,
            "sourceUnits": meta.get("units", {
                "length": "cm", "displacement": "cm", "force": "kN",
                "moment": "kN*cm", "stress": "MPa", "rotation": "rad",
            }),
            "units": VIEWER_UNITS,
            "mesh": mesh,
            "analyses": [analysis],
            "analysisCatalog": catalog,
            "defaultAnalysis": default,
            "modal": modal,
        }
    mesh = _mesh(str(archive), arrays, hrx_model=model)
    mesh["name"] = archive.name
    if include_face_grids is None:
        include_face_grids = len(mesh["quads"]) <= 1000
    analysis = _analysis(
        entry, summary, mesh, arrays,
        include_face_grids=include_face_grids,
        include_stress_fields=include_stress_fields,
    )
    analysis["name"] = case_id
    modal = (_attachment_modal_entries(archive, manifest, model, arrays, case_id)
             if include_modal_shapes
             else _attachment_modal_descriptors(archive, manifest))
    return {
        "schemaVersion": 3,
        "sourceSchema": "histra-results-1.0.0",
        "modelSha256": meta.get("model_sha256"),
        "title": archive.stem,
        "name": archive.name,
        "sourceUnits": meta.get("units", {
            "length": "cm", "displacement": "cm", "force": "kN",
            "moment": "kN*cm", "stress": "MPa", "rotation": "rad",
        }),
        "units": VIEWER_UNITS,
        "mesh": mesh,
        "analyses": [analysis],
        "analysisCatalog": catalog,
        "defaultAnalysis": default,
        "lazyFields": not include_stress_fields,
        "modal": modal,
    }


def project_histra_modal(archive_path: str | Path, analysis_name: str):
    """Return one attachment-backed modal case with projected mode shapes."""
    archive, manifest, model, arrays, _case, _summary, _entry, case_id = _case_context(
        archive_path, analysis_name
    )
    entries = _attachment_modal_entries(
        archive, manifest, model, arrays, case_id, case_filter=case_id
    )
    if not entries:
        return {"name": case_id, "modes": []}
    return entries[0]


def project_histra_fields(archive_path: str | Path, analysis_name: str | None = None,
                          step: int | None = None):
    """Return lazy stress fields for a .histra case.

    The saved spring data exists only at the final stage end, so the requested
    ``step`` is accepted by the route but the returned fields are always the
    final snapshot.
    """
    archive, _manifest, model, arrays, _case, summary, entry, case_id = _case_context(
        archive_path, analysis_name
    )
    mesh = _mesh(str(archive), arrays, hrx_model=model)
    mesh["name"] = archive.name
    analysis = _analysis(entry, summary, mesh, arrays, include_face_grids=False)
    final_step = int(analysis["steps"][-1]["step"])
    return {
        "analysis": case_id,
        "step": final_step,
        "stressFields": analysis["stressFields"],
    }


def project_contours_histra(archive_path: str | Path, analysis_name: str | None = None):
    _archive, _manifest, _model, arrays, _case, summary, entry, _case_id = _case_context(archive_path, analysis_name)
    return _contours_payload(arrays, entry, summary)


def project_interface_histra(archive_path: str | Path, analysis_name: str | None, key: int):
    _archive, _manifest, _model, arrays, _case, summary, entry, _case_id = _case_context(archive_path, analysis_name)
    return _interface_payload(arrays, entry, summary, int(key))
