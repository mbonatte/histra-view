"""Ahead-of-time JIT kernel compilation and cache pre-warming utilities."""
from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)


def warmup_compiled_backends(verbose: bool = False) -> None:
    """Trigger ahead-of-time compilation of core Numba kernels.

    Executes minimal synthetic inputs through critical dispatchers
    (contact filters, assembly scatter, kinematics) so downstream
    model preprocessing and solves incur zero cold-start JIT latency.
    """
    # 1. Preprocessing Contact Geometry Broadphase & Face Filters
    try:
        from histra.preprocessing.contact_geometry import (
            _find_broad_pairs_nb,
            _find_face_candidates_nb,
        )
        if _find_broad_pairs_nb is not None:
            centres = np.zeros((2, 3), dtype=np.float64)
            radii = np.ones(2, dtype=np.float64)
            _find_broad_pairs_nb(centres, radii)

            f1 = np.array([0], dtype=np.int64)
            f2 = np.array([1], dtype=np.int64)
            fmin = np.zeros((2, 6, 3), dtype=np.float64)
            fmax = np.ones((2, 6, 3), dtype=np.float64)
            fcen = np.zeros((2, 6, 3), dtype=np.float64)
            fnor = np.zeros((2, 6, 3), dtype=np.float64)
            _find_face_candidates_nb(f1, f2, fmin, fmax, fcen, fnor, 0.1, 0.5)
    except Exception as exc:
        if verbose:
            logger.debug("Preprocessing contact warmup skipped: %s", exc)

    # 2. Global Stiffness Sparse Scatter Accumulator
    try:
        from histra.solver.assembler import _accumulate_csharp_order_impl
        if _accumulate_csharp_order_impl is not None:
            vals = np.zeros(1, dtype=np.float64)
            idx = np.zeros(1, dtype=np.int64)
            term_idx = np.zeros(1, dtype=np.int64)
            a_i = np.ones(1, dtype=np.float64)
            a_j = np.ones(1, dtype=np.float64)
            terms = np.ones(1, dtype=np.float64)
            _accumulate_csharp_order_impl(vals, idx, term_idx, a_i, a_j, terms)
    except Exception as exc:
        if verbose:
            logger.debug("Assembler scatter warmup skipped: %s", exc)

    # 3. Quad Yield Search Kernel
    try:
        from histra.elements.quad_kernels import quad_yield_search
        if quad_yield_search is not None:
            quad_yield_search(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    except Exception as exc:
        if verbose:
            logger.debug("Quad kernel warmup skipped: %s", exc)
