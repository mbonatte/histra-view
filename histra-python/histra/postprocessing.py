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


def compute_node_displacements(model: Model, global_u: Iterable[float]) -> list[NodeDisplacement]:
    """Return global X/Y/Z translations for every node supported by Quads.

    If a node belongs to multiple Quads, the connected-element predictions are
    averaged exactly as in the C# response operation. Nodes with no supported
    Quad contribution raise an explicit ``NotImplementedError`` rather than
    being silently exported as zero displacement.
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

    unsupported = [
        int(node_key) for node_key, contributions in connected.items()
        if not contributions
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


def _interface_local_resultant(interface) -> np.ndarray:
    """Supported force part of C# ``Interface.CalcolaRisultanti``."""
    f32 = np.float32
    force_x = f32(0.0)
    force_y = f32(0.0)
    force_z = f32(0.0)
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
