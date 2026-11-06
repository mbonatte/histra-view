"""Batch export projections with the scalar C# Vector3 rounding boundaries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class _ProjectionPlan:
    offsets: np.ndarray
    correction: np.ndarray
    corrected_corner_two: np.ndarray
    local_indices: np.ndarray
    global_indices: np.ndarray
    coefficients: np.ndarray
    node_indices: np.ndarray
    corner_indices: np.ndarray
    node_counts: np.ndarray


def _local_afference(quads):
    local, global_dofs, coefficients = [], [], []
    for index, quad in enumerate(quads):
        for dof, entries in enumerate(quad.aff[:7]):
            for entry in entries:
                if entry.gdl > 0:
                    local.append(index * 7 + dof)
                    global_dofs.append(entry.gdl - 1)
                    coefficients.append(float(entry.alfa))
    return (
        np.asarray(local, dtype=np.intp),
        np.asarray(global_dofs, dtype=np.intp),
        np.asarray(coefficients, dtype=np.float64),
    )


def _distortion_directions(quads):
    sine = np.asarray([q.sin for q in quads], dtype=np.float64).reshape(-1, 4)
    cosine = np.asarray([q.cos for q in quads], dtype=np.float64).reshape(-1, 4)
    length = np.asarray([q.length[3] for q in quads], dtype=np.float64)
    first = (
        np.asarray([q.reference_e1 for q in quads], dtype=np.float32).reshape(-1, 3).astype(float)
    )
    second = (
        np.asarray([q.reference_e2 for q in quads], dtype=np.float32).reshape(-1, 3).astype(float)
    )
    correction = np.zeros((len(quads), 2, 3), dtype=np.float64)
    valid = np.abs(sine[:, 2]) > 1.0e-30
    coefficient = -length[valid] * sine[valid, 3] / sine[valid, 2]
    correction[valid, 0] = coefficient[:, None] * (
        sine[valid, 1, None] * first[valid] + cosine[valid, 1, None] * second[valid]
    )
    correction[:, 1] = length[:, None] * (-sine[:, 0, None] * first + cosine[:, 0, None] * second)
    return correction, valid


def _node_contributions(model, quad_keys):
    # C# averages in connected-Quad insertion order, not sorted export order.
    indices = {key: index for index, key in enumerate(sorted(model.collections.nodes))}
    quads = {key: index for index, key in enumerate(quad_keys)}
    nodes, corners = [], []
    for key, quad in model.collections.quads.items():
        for corner, node in enumerate(quad.node_keys):
            nodes.append(indices[node])
            corners.append(quads[key] * 4 + corner)
    nodes = np.asarray(nodes, dtype=np.intp)
    return nodes, np.asarray(corners, dtype=np.intp), np.bincount(nodes, minlength=len(indices))


def _projection_plan(model):
    keys = sorted(model.collections.quads)
    quads = [model.collections.quads[key] for key in keys]
    points = np.asarray(
        [
            [
                (
                    model.collections.nodes[key].point.x,
                    model.collections.nodes[key].point.y,
                    model.collections.nodes[key].point.z,
                )
                for key in q.node_keys
            ]
            for q in quads
        ],
        dtype=np.float32,
    ).reshape(-1, 4, 3)
    centres = np.asarray([(q.g.x, q.g.y, q.g.z) for q in quads], dtype=np.float32).reshape(-1, 3)
    correction, valid = _distortion_directions(quads)
    return _ProjectionPlan(
        points - centres[:, None],
        correction,
        valid,
        *_local_afference(quads),
        *_node_contributions(model, keys),
    )


def _project_corners(plan, global_u):
    local = np.zeros((len(plan.offsets), 7), dtype=np.float64)
    valid = plan.global_indices < global_u.size
    # add.at preserves the original ordered sum for multi-entry afferences.
    np.add.at(
        local.ravel(),
        plan.local_indices[valid],
        global_u[plan.global_indices[valid]] * plan.coefficients[valid],
    )
    vector = local.astype(np.float32)
    result = vector[:, None, :3] + np.cross(vector[:, None, 3:6], plan.offsets)
    mask = plan.corrected_corner_two
    result[mask, 2] += (local[mask, 6, None] * plan.correction[mask, 0]).astype(np.float32)
    result[:, 3] += (local[:, 6, None] * plan.correction[:, 1]).astype(np.float32)
    return result


def _project_connected_nodes(plan, corners):
    total = np.zeros((len(plan.node_counts), 3), dtype=np.float32)
    np.add.at(total, plan.node_indices, corners.reshape(-1, 3)[plan.corner_indices])
    multiple = plan.node_counts > 1
    total[multiple] *= (np.float32(1.0) / plan.node_counts[multiple].astype(np.float32))[:, None]
    # Preserve the existing export convention: connected nodes are packed first;
    # nodes generated only for interfaces retain the trailing zero rows.
    return total[plan.node_counts > 0]


def build_displacement_fields(model, steps, *, include_node_displacements=True, node_count=None):
    """Project each Quad corner once per step and reuse it for node averaging.

    Plans live only for this export, so changes to geometry, afferences and
    preparation cannot leave stale kinematics in a later analysis output.
    """
    plan = _projection_plan(model)
    quad_fields = np.zeros((len(steps), len(plan.offsets), 4, 3), dtype=np.float32)
    output_nodes = len(plan.node_counts) if node_count is None else node_count
    node_fields = (
        np.zeros((len(steps), output_nodes, 3), dtype=np.float32)
        if include_node_displacements
        else None
    )
    for index, step in enumerate(steps):
        if step.get("u") is None:
            continue
        displacement = np.asarray(step["u"], dtype=float)
        if node_fields is not None and (displacement.ndim != 1 or displacement.size != model.gdl):
            raise ValueError(
                f"Expected a one-dimensional displacement vector of length {model.gdl}; "
                f"received shape {displacement.shape}."
            )
        quad_fields[index] = _project_corners(plan, displacement)
        if node_fields is not None:
            connected = _project_connected_nodes(plan, quad_fields[index])
            count = min(len(connected), output_nodes)
            node_fields[index, :count] = connected[:count]
    return quad_fields, node_fields
