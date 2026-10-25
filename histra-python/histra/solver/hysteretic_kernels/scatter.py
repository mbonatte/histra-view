"""Compiled force-scatter kernels for the nonlinear batch runtime.

Fixed-topology local/global force scatter, force-by-DOF refresh and the
max-displacement cache update. The scatter topology is built once per
preparation (see :mod:`histra.solver.hysteretic_topology`) and reused verbatim
in every Newton correction, so these kernels never touch Python objects.

No ``fastmath`` is used; the dense state column constants are imported from
the kernel modules that own them.
"""
from __future__ import annotations

import numpy as np

from histra.solver.hysteretic_kernels.quad_takeda import QTSTRESS

try:  # optional acceleration dependency
    from numba import njit, prange
except Exception:  # pragma: no cover - exercised when numba is unavailable
    njit = None
    prange = None


def _pdelta_displacement_component(translation, rotation):
    """Keep C# DisplacementsCurrent(point) - DisplacementsCurrent(G) rounding."""
    translation = np.float32(translation)
    return np.float32(np.float32(translation + rotation) - translation)


if njit is not None:
    _pdelta_displacement_component = njit(cache=True, inline="always")(_pdelta_displacement_component)


if njit is not None:
    @njit(cache=True, nogil=True)
    def _scatter_local_forces(local_forces, offsets, gdls, coefficients, global_force):
        flat = local_forces.reshape(local_forces.size)
        for local_index in range(flat.size):
            force = flat[local_index]
            if force == 0.0:
                continue
            for pair_index in range(offsets[local_index], offsets[local_index + 1]):
                gdl = gdls[pair_index]
                if 0 <= gdl < global_force.size:
                    global_force[gdl] -= force * coefficients[pair_index]

    @njit(cache=True, nogil=True)
    def _refresh_global_resisting_force(
        quad_d_alfa, quad_state, quad_forces,
        quad_offsets, quad_gdls, quad_coefficients,
        interface_forces, interface_offsets, interface_gdls,
        interface_coefficients, global_force,
    ):
        global_force[:] = 0.0
        for i in range(quad_forces.shape[0]):
            quad_forces[i, 0] = quad_d_alfa[i] * quad_state[i, QTSTRESS]
        _scatter_local_forces(
            interface_forces, interface_offsets, interface_gdls,
            interface_coefficients, global_force,
        )
        _scatter_local_forces(
            quad_forces, quad_offsets, quad_gdls, quad_coefficients,
            global_force,
        )

    @njit(cache=True, nogil=True, parallel=True)
    def _refresh_global_resisting_force_by_dof(
        quad_d_alfa, quad_state, quad_forces, interface_forces,
        global_offsets, force_indices, force_coefficients,
        interface_force_size, global_force,
    ):
        """Assemble independent global DOFs with C#-ordered afferences.

        ``force_indices`` is prepared once in the same Interface-then-Quad,
        local-DOF, afference order used by ``_scatter_local_forces``.  Each
        global DOF can therefore be reduced independently without changing
        the order of any floating-point additions.
        """
        for i in range(quad_forces.shape[0]):
            quad_forces[i, 0] = quad_d_alfa[i] * quad_state[i, QTSTRESS]

        interface_flat = interface_forces.reshape(interface_forces.size)
        quad_flat = quad_forces.reshape(quad_forces.size)
        for gdl in prange(global_force.size):
            total = 0.0
            for position in range(global_offsets[gdl], global_offsets[gdl + 1]):
                force_index = force_indices[position]
                if force_index < interface_force_size:
                    force = interface_flat[force_index]
                else:
                    force = quad_flat[force_index - interface_force_size]
                if force != 0.0:
                    total -= force * force_coefficients[position]
            global_force[gdl] = total

    @njit(cache=True, nogil=True)
    def _refresh_max_u_cache(quad_local_u, interface_max_u, cache):
        quad_value = 0.0
        quad_index = -1
        kind = 0
        for i in range(quad_local_u.shape[0]):
            for j in range(quad_local_u.shape[1]):
                candidate = abs(quad_local_u[i, j])
                if candidate > quad_value:
                    quad_value = candidate
                    quad_index = i
                    kind = 1
        value = quad_value
        index = quad_index
        for i in range(interface_max_u.size):
            candidate = abs(interface_max_u[i])
            if candidate > value:
                value = candidate
                index = i
                kind = 2
        cache[0] = value
        cache[1] = index
        cache[2] = kind
        cache[3] = quad_value
        cache[4] = quad_index

    @njit(cache=True, nogil=True)
    def _batch_interface_resultants(
        starts, stops, trial_stresses, slid_indices, oop0_indices, oop1_indices, coulomb_state, resultants
    ):
        n = starts.shape[0]
        for r in range(n):
            fy = np.float32(0.0)
            st = starts[r]
            sp = stops[r]
            for s in range(st, sp):
                fy = np.float32(fy + np.float32(trial_stresses[s, 6]))
            resultants[r, 1] = fy

            fx = np.float32(0.0)
            idx_slid = slid_indices[r]
            if idx_slid >= 0:
                fx = np.float32(fx - np.float32(coulomb_state[idx_slid, 29]))
            resultants[r, 0] = fx

            fz = np.float32(0.0)
            idx_oop0 = oop0_indices[r]
            if idx_oop0 >= 0:
                fz = np.float32(fz - np.float32(coulomb_state[idx_oop0, 29]))
            idx_oop1 = oop1_indices[r]
            if idx_oop1 >= 0:
                fz = np.float32(fz - np.float32(coulomb_state[idx_oop1, 29]))
            resultants[r, 2] = fz

    @njit(cache=True, nogil=True)
    def _eval_pdelta_interfaces_kernel(
        quad_local_u,
        all_res_forces,
        quad_indices,
        intf_indices,
        r_arr,
        R_arr,
        scatter_quad_idx,
        scatter_comp,
        scatter_dof,
        scatter_alfa,
        pq_global,
    ):
        n_quads = quad_local_u.shape[0]
        quad_moments = np.zeros((n_quads, 3), dtype=np.float64)
        m_count = len(quad_indices)
        for m in range(m_count):
            q = quad_indices[m]
            phi_x = np.float32(quad_local_u[q, 3])
            phi_y = np.float32(quad_local_u[q, 4])
            phi_z = np.float32(quad_local_u[q, 5])
            if phi_x == 0.0 and phi_y == 0.0 and phi_z == 0.0:
                continue
            rx = r_arr[m, 0]
            ry = r_arr[m, 1]
            rz = r_arr[m, 2]

            du_x = phi_y * rz - phi_z * ry
            du_y = phi_z * rx - phi_x * rz
            du_z = phi_x * ry - phi_y * rx

            du_x = _pdelta_displacement_component(quad_local_u[q, 0], du_x)
            du_y = _pdelta_displacement_component(quad_local_u[q, 1], du_y)
            du_z = _pdelta_displacement_component(quad_local_u[q, 2], du_z)

            intf_idx = intf_indices[m]
            fl_x = all_res_forces[intf_idx, 0]
            fl_y = all_res_forces[intf_idx, 1]
            fl_z = all_res_forces[intf_idx, 2]

            fg_x = np.float32(R_arr[m, 0, 0] * fl_x + R_arr[m, 0, 1] * fl_y + R_arr[m, 0, 2] * fl_z)
            fg_y = np.float32(R_arr[m, 1, 0] * fl_x + R_arr[m, 1, 1] * fl_y + R_arr[m, 1, 2] * fl_z)
            fg_z = np.float32(R_arr[m, 2, 0] * fl_x + R_arr[m, 2, 1] * fl_y + R_arr[m, 2, 2] * fl_z)

            mx = np.float64(du_y * fg_z - du_z * fg_y)
            my = np.float64(du_z * fg_x - du_x * fg_z)
            mz = np.float64(du_x * fg_y - du_y * fg_x)

            quad_moments[q, 0] += mx
            quad_moments[q, 1] += my
            quad_moments[q, 2] += mz

        s_count = len(scatter_dof)
        for s in range(s_count):
            q = scatter_quad_idx[s]
            c = scatter_comp[s]
            dof = scatter_dof[s]
            alfa = scatter_alfa[s]
            pq_global[dof] += quad_moments[q, c] * alfa

    @njit(cache=True, nogil=True)
    def _eval_pdelta_line_loads_kernel(
        quad_local_u,
        load_quad_indices,
        load_r_arr,
        item_offsets,
        item_forces,
        scatter_offsets,
        scatter_comp,
        scatter_dof,
        scatter_alfa,
        pq_global,
    ):
        """Accumulate cached Quad line-load P-Delta moments.

        One row represents one ``LineLoadElement`` and its item range.  The
        order deliberately mirrors the scalar C#-compatible path: sum all
        template items for a line load, then scatter that line load through
        the Quad rotational afferences before advancing to the next load.
        """
        for load_index in range(load_quad_indices.size):
            q = load_quad_indices[load_index]
            phi_x = np.float32(quad_local_u[q, 3])
            phi_y = np.float32(quad_local_u[q, 4])
            phi_z = np.float32(quad_local_u[q, 5])
            if phi_x == 0.0 and phi_y == 0.0 and phi_z == 0.0:
                continue

            rx = load_r_arr[load_index, 0]
            ry = load_r_arr[load_index, 1]
            rz = load_r_arr[load_index, 2]
            du_x = phi_y * rz - phi_z * ry
            du_y = phi_z * rx - phi_x * rz
            du_z = phi_x * ry - phi_y * rx

            du_x = _pdelta_displacement_component(quad_local_u[q, 0], du_x)
            du_y = _pdelta_displacement_component(quad_local_u[q, 1], du_y)
            du_z = _pdelta_displacement_component(quad_local_u[q, 2], du_z)

            mx = np.float64(0.0)
            my = np.float64(0.0)
            mz = np.float64(0.0)
            for item_index in range(item_offsets[load_index], item_offsets[load_index + 1]):
                fx = item_forces[item_index, 0]
                fy = item_forces[item_index, 1]
                fz = item_forces[item_index, 2]
                mx += np.float64(du_y * fz - du_z * fy)
                my += np.float64(du_z * fx - du_x * fz)
                mz += np.float64(du_x * fy - du_y * fx)

            for scatter_index in range(scatter_offsets[q], scatter_offsets[q + 1]):
                comp = scatter_comp[scatter_index]
                if comp == 0:
                    moment = mx
                elif comp == 1:
                    moment = my
                else:
                    moment = mz
                pq_global[scatter_dof[scatter_index]] += moment * scatter_alfa[scatter_index]


else:  # pragma: no cover - exercised when numba is unavailable
    _scatter_local_forces = None
    _refresh_global_resisting_force = None
    _refresh_global_resisting_force_by_dof = None
    _refresh_max_u_cache = None

    def _batch_interface_resultants(
        starts, stops, trial_stresses, slid_indices, oop0_indices, oop1_indices, coulomb_state, resultants
    ):
        n = starts.shape[0]
        for r in range(n):
            fy = np.float32(0.0)
            st = starts[r]
            sp = stops[r]
            for s in range(st, sp):
                fy = np.float32(fy + np.float32(trial_stresses[s, 6]))
            resultants[r, 1] = fy

            fx = np.float32(0.0)
            idx_slid = slid_indices[r]
            if idx_slid >= 0:
                fx = np.float32(fx - np.float32(coulomb_state[idx_slid, 29]))
            resultants[r, 0] = fx

            fz = np.float32(0.0)
            idx_oop0 = oop0_indices[r]
            if idx_oop0 >= 0:
                fz = np.float32(fz - np.float32(coulomb_state[idx_oop0, 29]))
            idx_oop1 = oop1_indices[r]
            if idx_oop1 >= 0:
                fz = np.float32(fz - np.float32(coulomb_state[idx_oop1, 29]))
            resultants[r, 2] = fz

    def _eval_pdelta_interfaces_kernel(
        quad_local_u,
        all_res_forces,
        quad_indices,
        intf_indices,
        r_arr,
        R_arr,
        scatter_quad_idx,
        scatter_comp,
        scatter_dof,
        scatter_alfa,
        pq_global,
    ):
        n_quads = quad_local_u.shape[0]
        quad_moments = np.zeros((n_quads, 3), dtype=np.float64)
        m_count = len(quad_indices)
        for m in range(m_count):
            q = quad_indices[m]
            phi_x = np.float32(quad_local_u[q, 3])
            phi_y = np.float32(quad_local_u[q, 4])
            phi_z = np.float32(quad_local_u[q, 5])
            if phi_x == 0.0 and phi_y == 0.0 and phi_z == 0.0:
                continue
            rx = r_arr[m, 0]
            ry = r_arr[m, 1]
            rz = r_arr[m, 2]

            du_x = phi_y * rz - phi_z * ry
            du_y = phi_z * rx - phi_x * rz
            du_z = phi_x * ry - phi_y * rx

            du_x = _pdelta_displacement_component(quad_local_u[q, 0], du_x)
            du_y = _pdelta_displacement_component(quad_local_u[q, 1], du_y)
            du_z = _pdelta_displacement_component(quad_local_u[q, 2], du_z)

            intf_idx = intf_indices[m]
            fl_x = all_res_forces[intf_idx, 0]
            fl_y = all_res_forces[intf_idx, 1]
            fl_z = all_res_forces[intf_idx, 2]

            fg_x = np.float32(R_arr[m, 0, 0] * fl_x + R_arr[m, 0, 1] * fl_y + R_arr[m, 0, 2] * fl_z)
            fg_y = np.float32(R_arr[m, 1, 0] * fl_x + R_arr[m, 1, 1] * fl_y + R_arr[m, 1, 2] * fl_z)
            fg_z = np.float32(R_arr[m, 2, 0] * fl_x + R_arr[m, 2, 1] * fl_y + R_arr[m, 2, 2] * fl_z)

            mx = np.float64(du_y * fg_z - du_z * fg_y)
            my = np.float64(du_z * fg_x - du_x * fg_z)
            mz = np.float64(du_x * fg_y - du_y * fg_x)

            quad_moments[q, 0] += mx
            quad_moments[q, 1] += my
            quad_moments[q, 2] += mz

        s_count = len(scatter_dof)
        for s in range(s_count):
            q = scatter_quad_idx[s]
            c = scatter_comp[s]
            dof = scatter_dof[s]
            alfa = scatter_alfa[s]
            pq_global[dof] += quad_moments[q, c] * alfa

    def _eval_pdelta_line_loads_kernel(
        quad_local_u, load_quad_indices, load_r_arr, item_offsets,
        item_forces, scatter_offsets, scatter_comp, scatter_dof,
        scatter_alfa, pq_global,
    ):
        for load_index, q in enumerate(load_quad_indices):
            phi = np.asarray(quad_local_u[q, 3:6], dtype=np.float32)
            if not np.any(phi):
                continue
            translation = np.asarray(quad_local_u[q, :3], dtype=np.float32)
            delta_u = (translation + np.cross(phi, load_r_arr[load_index])) - translation
            moment = np.zeros(3, dtype=np.float64)
            for item_index in range(item_offsets[load_index], item_offsets[load_index + 1]):
                moment += np.cross(delta_u, item_forces[item_index]).astype(np.float32)
            for scatter_index in range(scatter_offsets[q], scatter_offsets[q + 1]):
                pq_global[scatter_dof[scatter_index]] += (
                    moment[scatter_comp[scatter_index]] * scatter_alfa[scatter_index]
                )
