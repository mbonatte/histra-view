"""Boundary condition reduction and DOF restraint determination.

Extracted from assembler.py to separate boundary condition handling (fixed DOF
identification, row/column reduction) from global stiffness matrix assembly.
"""

from __future__ import annotations

from typing import Optional, Set, Tuple

import numpy as np
import scipy.sparse as sp

from histra.model.model import Model


def get_restrained_dofs(model: Model, K: Optional[sp.csc_matrix] = None) -> Set[int]:
    """Identify DOF indices (0-based) that are fixed.

    1. Explicit restraints from the model (NodeC-based).
    2. Any DOF with zero diagonal stiffness (passive DOFs that carry no
       load and must be removed to avoid a singular system).

    A Restraint with K[i] < 0 means that DOF i is fully fixed.
    """
    restrained: Set[int] = set()

    # ── 1. Explicit restraints ──
    for r in model.collections.restraints.values():
        # Restraint references NodeC objects via node_c_keys
        for nc_key in r.node_c_keys:
            if nc_key == 0 or nc_key not in model.collections.node_c:
                continue
            nc = model.collections.node_c[nc_key]
            node_key = nc.node_key
            if node_key == 0:
                continue
            # Find all quads that reference this node
            for quad in model.collections.quads.values():
                if node_key not in quad.node_keys:
                    continue
                pos = quad.node_keys.index(node_key)
                if pos > 1:
                    # Only diagonal nodes (pos 0 or 1) have direct DOFs
                    continue
                # Map restraint DOFs to quad DOFs based on node position
                # pos=0 → aff[0..2], pos=1 → aff[3..5]
                dof_offset = pos * 3
                for i in range(3):  # U1, U2, U3 only (ignore rotational K[3..5])
                    if i < len(r.k) and r.k[i] < 0:
                        for entry in quad.aff[dof_offset + i]:
                            restrained.add(entry.gdl - 1)

    # ── 2. Zero-diagonal DOFs (no stiffness contribution) ──
    if K is not None and K.nnz > 0:
        diag = K.diagonal()
        for dof in range(K.shape[0]):
            if abs(diag[dof]) < 1e-30:
                restrained.add(dof)

    return restrained


def apply_boundary_conditions(
    K: sp.csc_matrix,
    b: np.ndarray,
    fixed_dofs: Set[int],
) -> Tuple[sp.csc_matrix, np.ndarray]:
    """Eliminate fixed DOFs from the system (row/col deletion).

    Returns reduced K and b.
    """
    if not fixed_dofs:
        return K, b
    n = K.shape[0]
    free = sorted(set(range(n)) - fixed_dofs)
    K_free = K[np.ix_(free, free)]
    b_free = b[free]
    return K_free, b_free
