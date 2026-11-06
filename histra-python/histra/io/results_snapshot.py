"""Stage-boundary snapshots, independent of later material/runtime mutations."""
from __future__ import annotations

import numpy as np

from histra.solver.model_manager import ModelManager
from histra.solver.hysteretic_kernels.interface_coulomb import CCSTRESS, CCPHASE


def capture_export_snapshot(model):
    """Copy topology and committed spring state before a later analysis changes it."""
    if not hasattr(model.collections, "quads"):
        return {}
    arrays = _node_arrays(model)
    quads = [q for _, q in sorted(model.collections.quads.items())]
    interfaces = [i for _, i in sorted(model.collections.interfaces.items())]
    arrays.update(_quad_arrays(quads))
    arrays.update(_interface_arrays(model, interfaces))
    _add_spring_arrays(model, interfaces, arrays)
    return {key: np.array(value, copy=True) for key, value in arrays.items()}


def _xyz(point):
    return [point.x, point.y, getattr(point, "z", 0.0)]


def _node_arrays(model):
    connected = {key for q in model.collections.quads.values() for key in q.node_keys}
    nodes = [(key, node) for key, node in sorted(model.collections.nodes.items()) if key in connected]
    return {
        "mesh/node_keys": np.array([key for key, _ in nodes], np.uint32),
        "mesh/nodes_xyz": np.array([_xyz(n.point) for _, n in nodes], np.float32).reshape(-1, 3),
    }


def _quad_arrays(quads):
    arrays = {
        "mesh/quad_keys": np.array([q.key for q in quads], np.uint32),
        "mesh/quad_conn": np.array([q.node_keys for q in quads], np.uint32).reshape(-1, 4),
        "mesh/quad_g": np.array([_xyz(q.g) for q in quads], np.float32).reshape(-1, 3),
        "mesh/quad_material_keys": np.array([q.material_key for q in quads], np.uint32),
        "mesh/quad_thickness": np.array([q.thickness for q in quads], np.float32).reshape(-1, 4),
    }
    faces = [face for q in quads for face in q.interface_keys]
    # Partial-edge contacts can have several interfaces per face. Preserve all
    # keys in CSR, alongside the first-key convenience table requested by viewers.
    arrays["mesh/quad_interface_keys"] = np.array(
        [face[0] if face else -1 for face in faces], np.int32
    ).reshape(-1, 6)
    arrays["mesh/quad_face_interface_offsets"] = _offsets([len(face) for face in faces])
    arrays["mesh/quad_face_interface_keys"] = np.array([key for face in faces for key in face], np.uint32)
    return arrays


def _interface_arrays(model, interfaces):
    arrays = _interface_geometry(model, interfaces)
    for name, attr, dtype in (
        ("length", "length", np.float32), ("material_keys", "material_key", np.uint32),
        ("nrow", "nrow", np.uint16), ("ncol", "ncol", np.uint16),
        ("restrained", "interfaccia_vincolata", np.uint8),
    ):
        arrays[f"mesh/interface_{name}"] = np.array([getattr(i, attr) for i in interfaces], dtype)
    # The internal nspring is a legacy alias for ncol, not the fibre count.
    arrays["mesh/interface_nspring"] = np.array([len(i.trasv_1) for i in interfaces], np.uint16)
    for axis in ("e1", "e3"):
        arrays[f"mesh/interface_{axis}"] = np.array(
            [getattr(i, f"reference_{axis}") for i in interfaces], np.float32
        ).reshape(-1, 3)
    arrays["mesh/interface_origin"] = np.array(
        [_xyz(i.reference_origin) for i in interfaces], np.float32
    ).reshape(-1, 3)
    return arrays


def _interface_geometry(model, interfaces):
    vint = np.zeros((len(interfaces), 4, 3), np.float32)
    for index, interface in enumerate(interfaces):
        points = interface.vint3d or interface.vint2d
        for corner, point in enumerate(points[:4]):
            vint[index, corner] = _xyz(point)
    return {
        "mesh/interface_keys": np.array([i.key for i in interfaces], np.uint32),
        "mesh/interface_parents": np.array(
            [[i.parent_element_key1, i.parent_element_key2] for i in interfaces], np.uint32
        ).reshape(-1, 2),
        "mesh/interface_vint": vint,
        "mesh/interface_node_keys": np.array([i.node_keys for i in interfaces], np.uint32).reshape(-1, 2),
        "mesh/interface_node_xyz": np.array(
            [[_xyz(model.collections.nodes[key].point) for key in i.node_keys] for i in interfaces],
            np.float32,
        ).reshape(-1, 2, 3),
    }


def _offsets(counts):
    return np.concatenate(([0], np.cumsum(counts, dtype=np.uint32))).astype(np.uint32)


def _spring_indices(runtime, interfaces, arrays):
    records = {id(record.interface): (index, record) for index, record in enumerate(runtime.records)}
    transverse, areas, sliding, sliding_counts, record_order = [], [], [], [], []
    for interface in interfaces:
        if id(interface) not in records:
            raise ValueError("Cannot export incomplete compiled interface spring coverage")
        index, record = records[id(interface)]
        record_order.append(index)
        transverse.extend(range(record.start, record.stop))
        group = interface.trasv_1
        areas.extend(group._area if getattr(group, "is_batch_backed", False)
                     else [spring.area for spring in group])
        # Runtime rows deduplicate aliases; export the component slots, including
        # shared out-of-plane springs, so each interface has an explicit span.
        indices = [int(rows[index]) for rows in
                   (runtime._slid_index, runtime._oop0_index, runtime._oop1_index)
                   if int(rows[index]) >= 0]
        sliding.extend(indices)
        sliding_counts.append(len(indices))
    arrays["_export/interface_record_order"] = np.asarray(record_order, dtype=np.int32)
    arrays["springs/transverse_offsets"] = _offsets([len(i.trasv_1) for i in interfaces])
    arrays["springs/sliding_offsets"] = _offsets(sliding_counts)
    return np.asarray(transverse, dtype=np.int64), np.asarray(sliding, dtype=np.int64), areas


def _add_spring_arrays(model, interfaces, arrays):
    runtime = ModelManager.hysteretic_batch_for(model)
    if runtime is None or not runtime.active:
        return
    transverse, sliding, areas = _spring_indices(runtime, interfaces, arrays)
    arrays["springs/transverse_force"] = runtime.committed[transverse, 6].astype(np.float32)
    arrays["springs/transverse_phase"] = runtime.committed[transverse, 8].astype(np.int8)
    arrays["springs/sliding_force"] = runtime.coulomb_state[sliding, CCSTRESS].astype(np.float32)
    arrays["springs/sliding_phase"] = runtime.coulomb_state[sliding, CCPHASE].astype(np.int8)
    for kind, area in (("transverse", areas), ("sliding", runtime.coulomb_params[sliding, 4])):
        area = np.asarray(area, dtype=float)
        valid = np.isfinite(area) & (area > 0)
        arrays[f"springs/{kind}_area"] = area.astype(np.float32)
        arrays[f"springs/{kind}_stress_valid"] = valid.astype(np.uint8)
        # Zero-area elastic sliding slots are valid force-carrying objects, but
        # have no physical stress. Preserve force and expose that distinction.
        stress = np.zeros_like(area)
        np.divide(10.0 * arrays[f"springs/{kind}_force"], area, out=stress, where=valid)
        arrays[f"springs/{kind}_stress"] = stress.astype(np.float32)

    from histra.io.spring_snapshot import add_spring_responses

    add_spring_responses(runtime, interfaces, transverse, sliding, arrays)
    order = arrays["_export/interface_record_order"]
    arrays["springs/runtime_arrays/all_resultant_forces"] = runtime.all_resultant_forces()[order]
    arrays["springs/runtime_arrays/all_bending_moments"] = runtime.all_bending_moments()[order]
    for name in ("quad_state", "coulomb_state"):
        arrays[f"springs/runtime_arrays/{name}"] = np.asarray(getattr(runtime, name), np.float32)
