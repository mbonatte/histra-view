"""Linear static solver and verification helpers."""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from histra.model.model import Model
from histra.types.linear_system import LinearSystem
from .assembler import assemble_global_k
from .load_assembly import assemble_load_vector, extract_displacements


def solve_linear(
    model: Model,
    *,
    stiffness_alfa: float = 0.0,
    analysis_key: int | None = None,
    combination: int = 1,
) -> np.ndarray:
    """Solve the active HRX generalized-DOF system ``K u = b``.

    Fixed physical DOFs are removed when the original C# model builds the
    afference/global-DOF map; they must not be inferred again from zero matrix
    diagonals.  The earlier Python signature also accidentally passed
    ``alfa`` as an analysis key when assembling loads.
    """
    n = int(model.gdl)
    ls = LinearSystem(n)
    ls.k = assemble_global_k(model, stiffness_alfa).tocsc()
    ls.b[:] = assemble_load_vector(model, analysis_key, combination)
    ls.solve()
    return ls.x.copy()


def verify_solution(model: Model, alfa: float = 0.0) -> dict:
    k = assemble_global_k(model, alfa)
    u_ref = extract_displacements(model)
    f_computed = k @ u_ref
    return {
        "K": k,
        "u_ref": u_ref,
        "f_computed": f_computed,
        "K_nnz": k.nnz,
        "K_norm": sp.linalg.norm(k),
    }


def compute_residual(K: sp.csc_matrix, u: np.ndarray, b: np.ndarray) -> float:
    residual = K @ u - b
    norm_b = np.linalg.norm(b)
    return float(np.linalg.norm(residual) if norm_b < 1e-30 else np.linalg.norm(residual) / norm_b)
