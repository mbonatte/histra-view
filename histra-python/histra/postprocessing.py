"""Post-processing for standalone HiStrA Python analyses.

The functions in this module intentionally mirror the supported C# output
conventions:

* node translations are reconstructed from each connected Quad and averaged,
  following ``NodeOperations.GetDisplacements``;
* total reactions use ``ModelManager.ComputeVb`` for the supported
  Quad/Interface model subset.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from histra.model.model import Model


@dataclass(frozen=True)
class NodeDisplacement:
    node_key: int
    node_name: str
    x: float
    y: float
    z: float
    ux: float
    uy: float
    uz: float
    contributing_quads: int

    @property
    def deformed_x(self) -> float:
        return self.x + self.ux

    @property
    def deformed_y(self) -> float:
        return self.y + self.uy

    @property
    def deformed_z(self) -> float:
        return self.z + self.uz


@dataclass(frozen=True)
class ReactionResult:
    """Total reaction vector in HiStrA and balancing-support conventions."""

    x: float
    y: float
    z: float

    @property
    def balancing_x(self) -> float:
        return -self.x

    @property
    def balancing_y(self) -> float:
        return -self.y

    @property
    def balancing_z(self) -> float:
        return -self.z


def _quad_local_displacement(quad, global_u: np.ndarray) -> np.ndarray:
    local = np.zeros(7, dtype=float)
    for local_dof, afference in enumerate(quad.aff[:7]):
        local[local_dof] = sum(
            float(global_u[entry.gdl - 1]) * float(entry.alfa)
            for entry in afference
            if 0 <= entry.gdl - 1 < global_u.size
        )
    return local


def quad_node_displacement(quad, node_point, node_index: int, global_u: np.ndarray) -> np.ndarray:
    """Reconstruct one Quad-node translation using C# float boundaries."""

    local = _quad_local_displacement(quad, global_u)
    u = np.asarray(local, dtype=np.float32)
    translation = u[:3]
    rotation = u[3:6]
    point = np.asarray((node_point.x, node_point.y, node_point.z), dtype=np.float32)
    centre = np.asarray((quad.g.x, quad.g.y, quad.g.z), dtype=np.float32)
    result = translation + np.cross(rotation, point - centre).astype(np.float32)

    if node_index == 2:
        denominator = float(quad.sin[2])
        if abs(denominator) > 1.0e-30:
            coefficient = (
                -float(quad.length[3])
                * float(quad.sin[3])
                / denominator
            )
            e1 = np.asarray(quad.reference_e1, dtype=np.float32)
            e2 = np.asarray(quad.reference_e2, dtype=np.float32)
            correction = np.array([
                np.float32(local[6] * (coefficient * (
                    float(quad.sin[1]) * float(e1[j])
                    + float(quad.cos[1]) * float(e2[j])
                ))) for j in range(3)
            ], dtype=np.float32)
            result = result + correction
    elif node_index == 3:
        e1 = np.asarray(quad.reference_e1, dtype=np.float32)
        e2 = np.asarray(quad.reference_e2, dtype=np.float32)
        correction = np.array([
            np.float32(local[6] * (float(quad.length[3]) * (
                -float(quad.sin[0]) * float(e1[j])
                + float(quad.cos[0]) * float(e2[j])
            ))) for j in range(3)
        ], dtype=np.float32)
        result = result + correction

    return np.asarray(result, dtype=float)


def _average_node_displacements(contributions) -> np.ndarray:
    """Original ordered Vector3 sum and scalar reciprocal multiplication."""
    total = np.zeros(3, dtype=np.float32)
    for contribution in contributions:
        total += np.asarray(contribution, dtype=np.float32)
    if len(contributions) > 1:
        total *= np.float32(1.0) / np.float32(len(contributions))
    return total.astype(float)


def compute_node_displacements(
    model: Model,
    global_u: Iterable[float],
    *,
    only_quad_nodes: bool | None = None,
) -> list[NodeDisplacement]:
    """Return global X/Y/Z translations for every node supported by Quads.

    If a node belongs to multiple Quads, the connected-element predictions are
    averaged exactly as in the C# response operation.

    When ``only_quad_nodes`` is ``None`` (default), nodes created purely as
    2-node interface edge endpoints during ``ModelManager.prepare_model`` are
    skipped automatically (matching C# ``NodeOperations.GetDisplacements``
    which iterates ``node.QuadConnected``), while standalone non-interface
    nodes with no supported Quad contribution still raise an explicit
    ``NotImplementedError``. Setting ``only_quad_nodes=True`` filters strictly
    to nodes connected to at least one Quad; ``only_quad_nodes=False`` enforces
    that every node in ``model.collections.nodes`` is connected to a Quad.
    """

    u = np.asarray(global_u, dtype=float)
    if u.ndim != 1 or u.size != int(model.gdl):
        raise ValueError(
            f"Expected a one-dimensional displacement vector of length {model.gdl}; "
            f"received shape {u.shape}."
        )

    connected: dict[int, list] = {key: [] for key in model.collections.nodes}
    for quad in model.collections.quads.values():
        for index, node_key in enumerate(quad.node_keys):
            if node_key in connected:
                connected[node_key].append((quad, index))

    if only_quad_nodes is True:
        unsupported = []
    elif only_quad_nodes is False:
        unsupported = [
            int(node_key) for node_key, contributions in connected.items()
            if not contributions
        ]
    else:
        interface_node_keys = {
            int(nk)
            for intf in model.collections.interfaces.values()
            for nk in getattr(intf, "node_keys", ())
        }
        unsupported = [
            int(node_key) for node_key, contributions in connected.items()
            if not contributions and int(node_key) not in interface_node_keys
        ]

    if unsupported:
        preview = ", ".join(str(key) for key in unsupported[:10])
        suffix = "..." if len(unsupported) > 10 else ""
        raise NotImplementedError(
            "Global X/Y/Z node displacement export currently requires every "
            "node to be connected to at least one Quad. Unsupported node keys: "
            f"{preview}{suffix}"
        )

    rows: list[NodeDisplacement] = []
    for node_key, node in sorted(model.collections.nodes.items()):
        if not connected[node_key]:
            continue
        contributions = [
            quad_node_displacement(quad, node.point, index, u)
            for quad, index in connected[node_key]
        ]
        displacement = _average_node_displacements(contributions)
        rows.append(
            NodeDisplacement(
                node_key=int(node_key),
                node_name=str(node.name),
                x=float(node.point.x),
                y=float(node.point.y),
                z=float(node.point.z),
                ux=float(displacement[0]),
                uy=float(displacement[1]),
                uz=float(displacement[2]),
                contributing_quads=len(contributions),
            )
        )
    return rows


def _spring_area_centroid_local_xy(interface, spring_index: int) -> tuple[np.float32, np.float32]:
    """Compute the C# ``CalcolaRisultanti`` 4-corner averaged local (X, Y) centroid for a transverse spring."""
    f32 = np.float32
    ncol = max(int(interface.ncol), 1)
    nrow = max(int(interface.nrow), 1)
    id_row = spring_index // ncol + 1
    id_spring = spring_index + 1 - (id_row - 1) * ncol

    f_ncol = f32(ncol)
    f_nrow = f32(nrow)
    x0 = f32(f32(f32(f32(id_spring) - f32(1.0)) * f32(2.0)) / f_ncol - f32(1.0))
    y0 = f32(f32(f32(id_row - 1) * f32(2.0)) / f_nrow - f32(1.0))
    x1 = f32(f32(f32(id_spring) * f32(2.0)) / f_ncol - f32(1.0))
    y1 = f32(f32(f32(f32(id_row) - f32(1.0)) * f32(2.0)) / f_nrow - f32(1.0))
    x2 = x1
    y2 = f32(f32(f32(id_row) * f32(2.0)) / f_nrow - f32(1.0))
    x3 = x0
    y3 = y2
    corners = ((x0, y0), (x1, y1), (x2, y2), (x3, y3))

    v = interface.vint2d
    v0x, v0y = f32(v[0].x), f32(v[0].y)
    v1x, v1y = f32(v[1].x), f32(v[1].y)
    v2x, v2y = f32(v[2].x), f32(v[2].y)
    v3x, v3y = f32(v[3].x), f32(v[3].y)
    origin_x = f32(f32(interface.length) / f32(2.0))

    vec_x = f32(0.0)
    vec_y = f32(0.0)
    for vx, vy in corners:
        one_m_x = f32(f32(1.0) - vx)
        one_p_x = f32(f32(1.0) + vx)
        one_m_y = f32(f32(1.0) - vy)
        one_p_y = f32(f32(1.0) + vy)
        c0x = f32(f32(f32(v0x * one_m_x) * one_m_y) / f32(4.0))
        c0y = f32(f32(f32(v0y * one_m_x) * one_m_y) / f32(4.0))
        c1x = f32(f32(f32(v1x * one_p_x) * one_m_y) / f32(4.0))
        c1y = f32(f32(f32(v1y * one_p_x) * one_m_y) / f32(4.0))
        c2x = f32(f32(f32(v2x * one_p_x) * one_p_y) / f32(4.0))
        c2y = f32(f32(f32(v2y * one_p_x) * one_p_y) / f32(4.0))
        c3x = f32(f32(f32(v3x * one_m_x) * one_p_y) / f32(4.0))
        c3y = f32(f32(f32(v3y * one_m_x) * one_p_y) / f32(4.0))
        coord_x = f32(f32(f32(c0x + c1x) + c2x) + c3x)
        coord_y = f32(f32(f32(c0y + c1y) + c2y) + c3y)
        vec_x = f32(vec_x + f32(coord_x - origin_x))
        vec_y = f32(vec_y + coord_y)

    return f32(vec_x / f32(4.0)), f32(vec_y / f32(4.0))


def _interface_local_resultants(interface) -> tuple[np.ndarray, np.ndarray]:
    """Port of C# ``Interface.CalcolaRisultanti(out Vector3 Forze, out Vector3 Momenti)``."""
    f32 = np.float32
    force_x = f32(0.0)
    force_y = f32(0.0)
    force_z = f32(0.0)
    moment_x = f32(0.0)
    moment_y = f32(0.0)
    moment_z = f32(0.0)

    if getattr(interface.trasv_1, "is_batch_backed", False) and not interface.trasv_1._cache:
        for i, raw_force in enumerate(interface.trasv_1._trial[:, 6]):
            vec_x, vec_y = _spring_area_centroid_local_xy(interface, i)
            num2 = f32(raw_force)
            force_y = f32(force_y + num2)
            moment_z = f32(moment_z + f32(num2 * vec_x))
            moment_x = f32(moment_x + f32(num2 * vec_y))
    else:
        for i, spring in enumerate(interface.trasv_1):
            vec_x, vec_y = _spring_area_centroid_local_xy(interface, i)
            num2 = f32(spring.get_force())
            force_y = f32(force_y + num2)
            moment_z = f32(moment_z + f32(num2 * vec_x))
            moment_x = f32(moment_x + f32(num2 * vec_y))

    for i, spring in enumerate(interface.trasv_2):
        vec_x, vec_y = _spring_area_centroid_local_xy(interface, i)
        num2 = f32(spring.get_force())
        force_y = f32(force_y + num2)
        moment_z = f32(moment_z + f32(num2 * vec_x))
        moment_x = f32(moment_x + f32(num2 * vec_y))

    for spring in interface.slid:
        num2 = f32(-f32(spring.get_force()))
        force_x = f32(force_x + num2)

    half_len_pos = f32(f32(interface.length) / f32(2.0))
    half_len_neg = f32(f32(interface.length) / f32(-2.0))
    vec_x_oop = f32(0.0)
    for i, spring in enumerate(interface.slid_out_plan):
        if i == 0:
            vec_x_oop = half_len_pos
        if i == 1:
            vec_x_oop = half_len_neg
        num2 = f32(-f32(spring.get_force()))
        force_z = f32(force_z + num2)
        moment_y = f32(moment_y + f32(num2 * vec_x_oop))

    forces = np.asarray((force_x, force_y, force_z), dtype=np.float32)
    moments = np.asarray((moment_x, moment_y, moment_z), dtype=np.float32)
    return forces, moments


def _interface_local_resultant(interface) -> np.ndarray:
    """Supported force part of C# ``Interface.CalcolaRisultanti``."""
    f32 = np.float32
    force_x = f32(0.0)
    force_y = f32(0.0)
    force_z = f32(0.0)
    if getattr(interface.trasv_1, "is_batch_backed", False) and not interface.trasv_1._cache:
        for raw_force in interface.trasv_1._trial[:, 6]:
            force_y = f32(force_y + f32(raw_force))
    else:
        for spring in interface.trasv_1:
            force_y = f32(force_y + f32(spring.get_force()))
    for spring in interface.trasv_2:
        force_y = f32(force_y + f32(spring.get_force()))
    for spring in interface.slid:
        force_x = f32(force_x - f32(spring.get_force()))
    for spring in interface.slid_out_plan:
        force_z = f32(force_z - f32(spring.get_force()))
    return np.asarray((force_x, force_y, force_z), dtype=np.float32)


def compute_total_reaction(model: Model) -> ReactionResult:
    """Compute C# ``ReactionSum.R`` for supported constrained interfaces.

    The returned ``x/y/z`` values use the same sign convention as the HiStrA
    software's ``ReactionSumStates.R1/R2/R3`` columns. The ``balancing_*``
    properties provide the opposite, conventional support-on-structure sign.
    """

    # Dense spring state is authoritative while the compiled nonlinear loop is
    # active. Only the few restrained interfaces are needed for ReactionSum;
    # avoid synchronizing every generated spring at every committed step.
    from histra.solver.model_manager import ModelManager

    runtime = ModelManager.hysteretic_batch_for(model)
    if runtime is not None and getattr(runtime, "active", False):
        total = runtime.compute_total_reaction_vector().astype(float)
        # In diagnostic mixed-runtime mode, include any restrained interfaces
        # that were not managed by the compiled batch runtime.
        managed_ids = getattr(runtime, "interface_ids", None)
        if managed_ids is None:
            managed_ids = {id(rec.interface) for rec in runtime.records}
        for interface in model.collections.interfaces.values():
            if id(interface) not in managed_ids and interface.interfaccia_vincolata_computed():
                local = _interface_local_resultant(interface)
                e1 = np.asarray(interface.reference_e1, dtype=np.float32)
                e2 = np.asarray(interface.reference_e2, dtype=np.float32)
                e3 = np.asarray(interface.reference_e3, dtype=np.float32)
                global_force = (
                    e1 * local[0] + e2 * local[1] + e3 * local[2]
                ).astype(np.float32)
                total += global_force.astype(float)
        return ReactionResult(float(total[0]), float(total[1]), float(total[2]))

    total = np.zeros(3, dtype=float)
    for interface in model.collections.interfaces.values():
        if not interface.interfaccia_vincolata_computed():
            continue
        local = _interface_local_resultant(interface)
        e1 = np.asarray(interface.reference_e1, dtype=np.float32)
        e2 = np.asarray(interface.reference_e2, dtype=np.float32)
        e3 = np.asarray(interface.reference_e3, dtype=np.float32)
        global_force = (
            e1 * local[0] + e2 * local[1] + e3 * local[2]
        ).astype(np.float32)
        total += global_force.astype(float)
    return ReactionResult(float(total[0]), float(total[1]), float(total[2]))
