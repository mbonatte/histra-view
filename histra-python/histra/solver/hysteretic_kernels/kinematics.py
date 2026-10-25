"""Compiled kinematics kernels for the nonlinear batch runtime.

Global-to-local displacement mapping (inverting immutable afferences) and the
interface/quad kinematics preparation kernels that build trial strain inputs
for the element-family evaluators.

No ``fastmath`` is used; phases and dense column constants are imported from
the kernel modules that own them.
"""
from __future__ import annotations

import numpy as np

from histra.solver.hysteretic_kernels.quad_takeda import (
    QPSUBLAW,
    QUAD_SUBLAW_ELASTIC,
    QUAD_SUBLAW_HYSTERETIC,
)

try:  # optional acceleration dependency
    from numba import njit, prange
except Exception:  # pragma: no cover - exercised when numba is unavailable
    njit = None
    prange = None


if njit is not None:
    @njit(cache=True, nogil=True)
    def _interface_flex_from_global(x, offsets, gdls, coefficients, length, restrained):
        du = np.zeros(6, dtype=np.float64)
        for i in range(6):
            for j in range(offsets[i], offsets[i+1]):
                gdl = gdls[j]
                if gdl < 0 or gdl >= x.size:
                    raise IndexError("Interface afference DOF outside the displacement vector")
                du[i] += x[gdl] * coefficients[j]
        if restrained:
            # ComputeFlexdef multiplies by Length before dividing by two.
            return (du[3] - du[0] + du[1] * length / 2.0,
                    du[2] - du[0] - du[1] * length / 2.0, du[5] - du[4])
        return du[3] - du[0], du[2] - du[1], du[5] - du[4]

    @njit(cache=True, nogil=True)
    def _interface_linear_normal_increment(x, offsets, gdls, coefficients, length, restrained, k):
        f0, f1, f2 = _interface_flex_from_global(x, offsets, gdls, coefficients, length, restrained)
        return -((k[2,2] + k[3,2]) * f0 + (k[2,3] + k[3,3]) * f1
                 + (k[2,5] + k[3,5]) * f2)

    @njit(cache=True, nogil=True)
    def _quad_linear_normal_force(edges, dns, spring_offsets, forces, increments, areas):
        normal = np.zeros(4, dtype=np.float64)
        stress = np.zeros(4, dtype=np.float64)
        for edge in range(4):
            force = 0.0
            for i in range(edges[edge], edges[edge+1]):
                normal[edge] += dns[i]
                interface_force = 0.0
                for j in range(spring_offsets[i], spring_offsets[i+1]):
                    interface_force += forces[j] - increments[j]
                force += interface_force
            if areas[edge] > 0.0:
                stress[edge] = force / areas[edge]
        return ((normal[0] + normal[2]) / 2.0 + (normal[1] + normal[3]) / 2.0,
                (stress[0] + stress[2]) / 2.0 + (stress[1] + stress[3]) / 2.0)

    @njit(cache=True, nogil=True)
    def _map_global_to_local(x, offsets, gdls, coefficients, out, local_u=None):
        flat = out.reshape(out.size)
        state = local_u.reshape(local_u.size) if local_u is not None else None
        for local_index in range(flat.size):
            total = 0.0
            for pair_index in range(offsets[local_index], offsets[local_index + 1]):
                gdl = gdls[pair_index]
                if 0 <= gdl < x.size:
                    increment = x[gdl] * coefficients[pair_index]
                    total += increment
                    if state is not None:
                        state[local_index] += increment
            flat[local_index] = total

    @njit(cache=True, nogil=True)
    def _prepare_interface_kinematics(
        local_du, local_u, lengths, constrained, d0s, d1s,
        nums, nums2, delta_flex, pending, accumulate_local_u=True,
    ):
        for i in range(local_du.shape[0]):
            if accumulate_local_u:
                for j in range(local_du.shape[1]):
                    local_u[i, j] += local_du[i, j]
            if not constrained[i]:
                nums[i] = local_du[i, 3] - local_du[i, 0]
                nums2[i] = local_du[i, 2] - local_du[i, 1]
            else:
                half_length = 0.5 * lengths[i]
                nums[i] = local_du[i, 3] - (local_du[i, 0] - local_du[i, 1] * half_length)
                nums2[i] = local_du[i, 2] - (local_du[i, 0] + local_du[i, 1] * half_length)
            delta_flex[i] = local_du[i, 5] - local_du[i, 4]
            d0 = d0s[i]
            d1 = d1s[i]
            pending[i, 0] = local_du[i, d0] - local_du[i, d0 + 1]
            pending[i, 1] = local_du[i, d0 + d1] - local_du[i, d0 + d1 + 2]
            pending[i, 2] = local_du[i, d0 + d1 + 1] - local_du[i, d0 + d1 + 3]

    @njit(cache=True, nogil=True, parallel=True)
    def _map_and_prepare_interface_kinematics(
        x, offsets, gdls, coefficients, local_du, local_u, lengths,
        constrained, d0s, d1s, nums, nums2, delta_flex, pending,
    ):
        """Fuse exact afference mapping with per-interface kinematics."""
        local_width = local_du.shape[1]
        for i in prange(local_du.shape[0]):
            flat_base = i * local_width
            for j in range(local_width):
                local_index = flat_base + j
                total = 0.0
                for pair_index in range(
                    offsets[local_index], offsets[local_index + 1]
                ):
                    gdl = gdls[pair_index]
                    if 0 <= gdl < x.size:
                        increment = x[gdl] * coefficients[pair_index]
                        total += increment
                        local_u[i, j] += increment
                local_du[i, j] = total

            if not constrained[i]:
                nums[i] = local_du[i, 3] - local_du[i, 0]
                nums2[i] = local_du[i, 2] - local_du[i, 1]
            else:
                half_length = 0.5 * lengths[i]
                nums[i] = local_du[i, 3] - (
                    local_du[i, 0] - local_du[i, 1] * half_length
                )
                nums2[i] = local_du[i, 2] - (
                    local_du[i, 0] + local_du[i, 1] * half_length
                )
            delta_flex[i] = local_du[i, 5] - local_du[i, 4]
            d0 = d0s[i]
            d1 = d1s[i]
            pending[i, 0] = local_du[i, d0] - local_du[i, d0 + 1]
            pending[i, 1] = (
                local_du[i, d0 + d1] - local_du[i, d0 + d1 + 2]
            )
            pending[i, 2] = (
                local_du[i, d0 + d1 + 1] - local_du[i, d0 + d1 + 3]
            )

    @njit(cache=True, nogil=True)
    def _prepare_quad_kinematics(
        local_du, local_u, edge_offsets, edge_records, edge_areas,
        interface_normal_increments, interface_committed_forces,
        d_alfa, step, sigma_initial, strains, dns, quad_params, accumulate_local_u=True,
    ):
        for q in range(local_du.shape[0]):
            if accumulate_local_u:
                for j in range(local_du.shape[1]):
                    local_u[q, j] += local_du[q, j]
            if int(quad_params[q, QPSUBLAW]) in (QUAD_SUBLAW_ELASTIC, QUAD_SUBLAW_HYSTERETIC):
                dns[q] = 0.0
                strains[q] = d_alfa[q] * local_u[q, 6]
                continue
            normal0 = 0.0
            normal1 = 0.0
            normal2 = 0.0
            normal3 = 0.0
            stress0 = 0.0
            stress1 = 0.0
            stress2 = 0.0
            stress3 = 0.0
            base = q * 4
            for edge in range(4):
                normal = 0.0
                force = 0.0
                edge_index = base + edge
                for k in range(edge_offsets[edge_index], edge_offsets[edge_index + 1]):
                    record_index = edge_records[k]
                    normal += interface_normal_increments[record_index]
                    force += interface_committed_forces[record_index]
                area = edge_areas[q, edge]
                stress = force / area if area > 0.0 else 0.0
                if edge == 0:
                    normal0 = normal
                    stress0 = stress
                elif edge == 1:
                    normal1 = normal
                    stress1 = stress
                elif edge == 2:
                    normal2 = normal
                    stress2 = stress
                else:
                    normal3 = normal
                    stress3 = stress
            sigma = 0.5 * (stress0 + stress2) + 0.5 * (stress1 + stress3)
            dn = 0.5 * (normal0 + normal2) + 0.5 * (normal1 + normal3)
            if step == 1:
                sigma_initial[q] = sigma
            dns[q] = dn
            strains[q] = d_alfa[q] * local_u[q, 6]



else:  # pragma: no cover - exercised when numba is unavailable
    _map_global_to_local = None
    _interface_flex_from_global = None
    _interface_linear_normal_increment = None
    _quad_linear_normal_force = None
    _prepare_interface_kinematics = None
    _map_and_prepare_interface_kinematics = None
    _prepare_quad_kinematics = None
