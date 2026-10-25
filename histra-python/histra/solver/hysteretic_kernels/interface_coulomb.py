"""Compiled interface Coulomb/sliding kernels (C# SpringCoulomb03, ``Initial``).

Dense-state evaluators for interface SpringCoulomb03 objects: target
advancement, the full ``Initial`` law state update (normal and shear
components with contact-area and fracture-energy bookkeeping), the elastic
sliding shortcut, full interface-force assembly and the commit kernels.

The dense state-column constants below (``CFY0`` .. ``COULOMB_STATE_SIZE``)
are part of the compiled contract; the layout deliberately keeps committed and
trial values in one contiguous row so rejected Newton/ArcLength trials can be
reverted without touching Python attributes.

No ``fastmath`` is used; phases are the canonical C# codes imported from the
transverse kernel module.
"""
from __future__ import annotations

import numpy as np

from histra.solver.hysteretic_kernels.transverse import (
    ELASTIC,
    PLASTIC_C,
    PLASTIC_T,
    RELOAD_T,
    RELOAD_C,
    RUPTURE,
)

try:  # optional acceleration dependency
    from numba import njit, prange
except Exception:  # pragma: no cover - exercised when numba is unavailable
    njit = None
    prange = None


# Dense state columns for interface SpringCoulomb03 objects using the C#
# ``Initial`` law.  Keeping the state in one contiguous array avoids hundreds
# of thousands of Python attribute reads/writes per Newton correction.
CFY0 = 0
CFY1 = 1
CCUP = 2
CCSTRESS = 3
CCSTRAIN = 4
CCSTRESS_NORMAL = 5
CCSTRESS_NORMAL_PREV = 6
CCCONTACT_AREA = 7
CCENERGY = 8
CCPHASE = 9
CTUP = 10
CTSTRESS = 11
CTSTRAIN = 12
CTSTRESS_NORMAL = 13
CTCONTACT_AREA = 14
CTENERGY = 15
CTPHASE = 16
CKTANG = 17
CMOM1P = 18
CROT1P = 19
CMOM2P = 20
CROT2P = 21
CMOM1N = 22
CROT1N = 23
CMOM2N = 24
CROT2N = 25
CROT3N = 26
CROT3P = 27
CU = 28
CF = 29
CKTANG_COMMITTED = 30
CDN = 31
# Committed unloading memory is required even for the Initial force law.
CCUNLOAD_T = 32
CCUNLOAD_C = 33
CCPLASTIC_T = 34
CCPLASTIC_C = 35
CTANGENT_RELOAD_T = 36
CTANGENT_RELOAD_C = 37
COULOMB_STATE_SIZE = 38


if njit is not None:
    @njit(cache=True, nogil=True)
    def _advance_interface_coulomb_targets(
        pending, dist_for, normal_increments, slid_index, oop0_index, oop1_index,
        targets, dns,
    ):
        for i in range(pending.shape[0]):
            s = slid_index[i]
            if s >= 0:
                targets[s] += pending[i, 0]
                dns[s] = normal_increments[i]
            a = oop0_index[i]
            b = oop1_index[i]
            if a >= 0 and b >= 0:
                di = dist_for[i, 0]
                dj = dist_for[i, 1]
                dua = pending[i, 1]
                dub = pending[i, 2]
                targets[a] += dua + (dub - dua) * di
                targets[b] += dua + (dub - dua) * dj
                dn = 0.5 * normal_increments[i]
                dns[a] = dn
                dns[b] = dn

    @njit(cache=True, nogil=True, parallel=True)
    def _evaluate_initial_coulomb_batch(params, state, targets, dns, enabled):
        """Exact C# ``setTrialStrainInitial`` for interface Coulomb springs.

        The accelerated path is deliberately limited to the model's supported
        no-contact-area Coulomb law.  Other variants stay on the scalar path.
        """
        for i in prange(targets.size):
            if not enabled[i]:
                continue
            k = params[i, 0]
            h = params[i, 1]
            cohesion = params[i, 2]
            mu = params[i, 3]
            area = params[i, 4]
            e1p = params[i, 5]
            e2p = params[i, 6]

            # C# RevertToLastCommit subset used by the Initial law.
            fy0 = -state[i, CFY1]
            tup = state[i, CCUP]
            cstress = state[i, CCSTRESS]
            cstrain = state[i, CCSTRAIN]
            tstress_normal = state[i, CCSTRESS_NORMAL]
            tcontact_area = state[i, CCCONTACT_AREA]
            tenergy = state[i, CCENERGY]
            phase = int(state[i, CCPHASE])
            tphase = phase
            tstress = cstress
            tstrain = targets[i]
            ktang = state[i, CKTANG]
            dstrain = tstrain - cstrain

            if phase == RUPTURE:
                tstress = cstress
                tstress_normal += dns[i]
                state[i, CFY0] = fy0
                state[i, CTUP] = tup
                state[i, CTSTRESS] = tstress
                state[i, CTSTRAIN] = tstrain
                state[i, CTSTRESS_NORMAL] = tstress_normal
                state[i, CTCONTACT_AREA] = tcontact_area
                state[i, CTENERGY] = tenergy
                state[i, CTPHASE] = tphase
                state[i, CKTANG] = ktang
                state[i, CU] = tstrain
                state[i, CF] = tstress
                state[i, CDN] = dns[i]
                continue

            tcontact_area = area
            mom1p = cohesion + mu * tstress_normal
            if mom1p < 0.0:
                mom1p = 0.0
            c_hard = cohesion + h * abs(state[i, CCUP])
            if cohesion != 0.0:
                fy0 = c_hard + mu * tstress_normal
            else:
                fy0 = 0.0
            if fy0 < 0.0:
                fy0 = 0.0

            rot1p = mom1p / e1p if e1p != 0.0 else 0.0
            rot2p = state[i, CROT2P]
            rot3p = state[i, CROT3P]
            if e2p < 0.0:
                mom2p = 0.0
                rot2p = rot1p - mom1p / e2p
            else:
                if rot2p < rot1p:
                    rot2p = rot1p
                    rot3p = rot2p * 1.0001
                mom2p = mom1p + e2p * (rot2p - rot1p)
            mom1n = -mom1p
            rot1n = -rot1p
            mom2n = -mom2p
            rot2n = -rot2p
            rot3n = -rot3p

            num3 = cstress + k * dstrain
            if abs(num3) - fy0 > 0.0:
                if num3 > 0.0:
                    tphase = PLASTIC_T
                    sign = 1.0
                else:
                    tphase = PLASTIC_C
                    sign = -1.0
                num5 = (abs(num3) - fy0) / k
                num6 = k * num5 / (h + k)
                fy0 += h * num6
                tstress = fy0 * sign
                if tphase == PLASTIC_T and tstress < 0.0:
                    tphase = RUPTURE
                    tstress = 0.0
                    ktang = 0.0
                elif tphase == PLASTIC_C and tstress > 0.0:
                    tphase = RUPTURE
                    tstress = 0.0
                    ktang = 0.0
                else:
                    tup += num6
                    ktang = e2p
            else:
                tstress = num3
                ktang = k
                tphase = ELASTIC

            tenergy = state[i, CCENERGY] + 0.5 * (cstress + tstress) * dstrain
            tstress_normal += dns[i]
            state[i, CFY0] = fy0
            state[i, CTUP] = tup
            state[i, CTSTRESS] = tstress
            state[i, CTSTRAIN] = tstrain
            state[i, CTSTRESS_NORMAL] = tstress_normal
            state[i, CTCONTACT_AREA] = tcontact_area
            state[i, CTENERGY] = tenergy
            state[i, CTPHASE] = tphase
            state[i, CKTANG] = ktang
            state[i, CMOM1P] = mom1p
            state[i, CROT1P] = rot1p
            state[i, CMOM2P] = mom2p
            state[i, CROT2P] = rot2p
            state[i, CMOM1N] = mom1n
            state[i, CROT1N] = rot1n
            state[i, CMOM2N] = mom2n
            state[i, CROT2N] = rot2n
            state[i, CROT3N] = rot3n
            state[i, CROT3P] = rot3p
            state[i, CU] = tstrain
            state[i, CF] = tstress
            state[i, CDN] = dns[i]

    @njit(cache=True, nogil=True, parallel=True)
    def _evaluate_elastic_sliding_batch(state, targets, elastic_indices):
        """Exact ``SpringElastic.set_trial_strain`` for dense sliding rows."""
        for dense_position in prange(elastic_indices.size):
            i = elastic_indices[dense_position]
            row = state[i]
            tstrain = targets[i]
            ktang = row[CKTANG]
            tstress = row[CCSTRESS] + ktang * (tstrain - row[CCSTRAIN])
            row[CTSTRESS] = tstress
            row[CTSTRAIN] = tstrain
            row[CU] = tstrain
            row[CF] = tstress

    @njit(cache=True, nogil=True, parallel=True)
    def _assemble_full_interface_forces(
        transverse_forces, coulomb_state, slid_index, oop0_index, oop1_index,
        dist, local_full_forces, max_displacements, coulomb_targets,
    ):
        for i in prange(local_full_forces.shape[0]):
            for local_dof in range(6):
                local_full_forces[i, local_dof] = transverse_forces[i, local_dof]
            for local_dof in range(6, 12):
                local_full_forces[i, local_dof] = 0.0
            max_u = max_displacements[i]
            s = slid_index[i]
            if s >= 0:
                force = coulomb_state[s, CTSTRESS]
                local_full_forces[i, 6] += force
                local_full_forces[i, 7] -= force
                value = abs(coulomb_targets[s])
                if value > max_u:
                    max_u = value
            a = oop0_index[i]
            b = oop1_index[i]
            if a >= 0 and b >= 0:
                di = dist[i, 0]
                dj = dist[i, 1]
                force0 = coulomb_state[a, CTSTRESS]
                force1 = coulomb_state[b, CTSTRESS]
                first = dj * force0 + di * force1
                second = di * force0 + dj * force1
                local_full_forces[i, 8] += first
                local_full_forces[i, 9] += second
                local_full_forces[i, 10] -= first
                local_full_forces[i, 11] -= second
                value = abs(coulomb_targets[a])
                if value > max_u:
                    max_u = value
                value = abs(coulomb_targets[b])
                if value > max_u:
                    max_u = value
            max_displacements[i] = max_u

    @njit(cache=True, nogil=True)
    def _commit_initial_coulomb_batch(state, enabled):
        for i in range(state.shape[0]):
            if not enabled[i]:
                continue
            row = state[i]
            row[CFY1] = -row[CFY0]
            row[CCUP] = row[CTUP]
            row[CCSTRESS_NORMAL_PREV] = row[CCSTRESS_NORMAL]
            row[CCSTRESS] = row[CTSTRESS]
            row[CCSTRAIN] = row[CTSTRAIN]
            row[CCSTRESS_NORMAL] = row[CTSTRESS_NORMAL]
            row[CCCONTACT_AREA] = row[CTCONTACT_AREA]
            row[CCENERGY] = row[CTENERGY]
            row[CCPHASE] = row[CTPHASE]
            row[CKTANG_COMMITTED] = row[CKTANG]
            row[CU] = row[CTSTRAIN]
            row[CF] = row[CTSTRESS]
            row[CDN] = 0.0
            phase = int(row[CCPHASE])
            if phase == PLASTIC_T:
                row[CCUNLOAD_T] = phase
            elif phase == PLASTIC_C:
                row[CCUNLOAD_C] = phase
            elif phase == RELOAD_T:
                if row[CCPLASTIC_T] == 0.0 and row[CCPLASTIC_C] == 0.0:
                    row[CCUNLOAD_T] = ELASTIC
                else:
                    row[CCUNLOAD_T] = phase
                    row[CCPLASTIC_T] = 1.0
                row[CTANGENT_RELOAD_T] = row[CKTANG]
            elif phase == RELOAD_C:
                if row[CCPLASTIC_T] == 0.0 and row[CCPLASTIC_C] == 0.0:
                    row[CCUNLOAD_C] = ELASTIC
                else:
                    row[CCUNLOAD_C] = phase
                    row[CCPLASTIC_C] = 1.0
                row[CTANGENT_RELOAD_C] = row[CKTANG]


    @njit(cache=True, nogil=True)
    def _commit_elastic_sliding_batch(state, elastic_indices):
        """Exact ``SpringElastic.commit`` for dense sliding rows."""
        for dense_position in range(elastic_indices.size):
            i = elastic_indices[dense_position]
            row = state[i]
            row[CCSTRESS] = row[CTSTRESS]
            row[CCSTRAIN] = row[CTSTRAIN]
            row[CU] = row[CTSTRAIN]
            row[CF] = row[CTSTRESS]



else:  # pragma: no cover - exercised when numba is unavailable
    _advance_interface_coulomb_targets = None
    _evaluate_initial_coulomb_batch = None
    _evaluate_elastic_sliding_batch = None
    _assemble_full_interface_forces = None
    _commit_initial_coulomb_batch = None
    _commit_elastic_sliding_batch = None
