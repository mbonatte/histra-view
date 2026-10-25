"""
Global stiffness matrix and load vector assembly.

Maps .NET HiStrA element assembly into COO / CSC format for scipy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple

import numpy as np
import scipy.sparse as sp

try:
    from numba import njit
except Exception:  # pragma: no cover - optional acceleration
    njit = None

from histra.model.model import Model
from histra.model.quad import Quad
from histra.model.interface import Interface
from histra.model.spring import SpringElastic
from histra.model._types import AfferenceEntry
from histra.preprocessing.csharp_math import csharp_pow
from histra.solver.hysteretic_kernels.interface_coulomb import CKTANG
from histra.solver.hysteretic_kernels.quad_takeda import QKTANG
from histra.solver.load_assembly import (
    _get_comb_coeff_gravity,
    _get_load_template_coefficient,
    _resolve_coefficient,
    assemble_load_vector,
    extract_displacements,
    generate_line_loads,
    generate_self_weight_loads,
)


# ── Assembly helpers ────────────────────────────────────────────────────────

def _assemble_afference(
    rows: list, cols: list, vals: list,
    n: int,
    aff_i: List[AfferenceEntry],
    aff_j: List[AfferenceEntry],
    k_ij: float,
):
    """Scatter local stiffness k_ij through afference matrices into global COO."""
    if abs(k_ij) < 1e-30:
        return
    for ei in aff_i:
        gi = ei.gdl - 1
        if gi < 0 or gi >= n:
            continue
        for ej in aff_j:
            gj = ej.gdl - 1
            if gj < 0 or gj >= n:
                continue
            v = k_ij * ei.alfa * ej.alfa
            if abs(v) < 1e-30:
                continue
            rows.append(gi)
            cols.append(gj)
            vals.append(v)


# ── Public API ──────────────────────────────────────────────────────────────

def _assemble_global_k_legacy(
    model: Model,
    alfa: float = 0.0,
    *,
    recompute_elements: bool = True,
) -> sp.csc_matrix:
    """
    Assemble the global stiffness matrix K (CSC format).

    Includes contributions from:
      - Quad diagonal (Aff[6]) — scalar stiffness * alfa_i * alfa_j
      - Interface flexural (DimAff[0]×DimAff[0] block) via Trasv_1 springs
      - Interface sliding (DimAff[1]×DimAff[1] block) via Slid springs
      - Interface out-of-plane (DimAff[2]×DimAff[2] block) via SlidOutPlan springs

    When ``recompute_elements`` is false, assemble the stiffness blocks already
    stored on each element by ``ModelManager.compute_k``. This avoids executing
    every constitutive/geometry stiffness calculation twice in the normal
    ``compute_ktang -> compute_k -> assemble_k`` path while keeping standalone
    assembler behaviour unchanged by default.
    """
    n = model.gdl
    rows, cols, vals = [], [], []

    # ── Quad contributions ──
    for quad in model.collections.quads.values():
        if recompute_elements:
            quad.compute_k(alfa)
        k_scalar = quad.status.k
        if not quad.aff or len(quad.aff) <= 6:
            continue
        aff6 = quad.aff[6]
        if not aff6:
            continue
        for ei in aff6:
            gi = ei.gdl - 1
            for ej in aff6:
                gj = ej.gdl - 1
                v = k_scalar * ei.alfa * ej.alfa
                if abs(v) > 1e-30:
                    rows.append(gi)
                    cols.append(gj)
                    vals.append(v)

    # ── Interface contributions ──
    dim0 = 6  # typical flexural DOF count
    dim1 = 2  # typical sliding DOF count
    dim2 = 4  # typical out-of-plane DOF count

    for intf in model.collections.interfaces.values():
        d0 = intf.dim_aff[0] if len(intf.dim_aff) > 0 else dim0
        d1 = intf.dim_aff[1] if len(intf.dim_aff) > 1 else dim1
        d2 = intf.dim_aff[2] if len(intf.dim_aff) > 2 else dim2
        if recompute_elements:
            intf.compute_k(alfa)

        # Flexural block
        k_flex = intf.status.k
        for i in range(d0):
            for j in range(d0):
                k_ij = k_flex[i][j]
                if i < len(intf.aff) and j < len(intf.aff):
                    _assemble_afference(rows, cols, vals, n,
                                        intf.aff[i], intf.aff[j], k_ij)

        # Sliding block
        if intf.slid:
            k_slid = intf.status.kslid
            for i in range(d1):
                for j in range(d1):
                    ai = d0 + i
                    aj = d0 + j
                    k_ij = k_slid[i][j]
                    if ai < len(intf.aff) and aj < len(intf.aff):
                        _assemble_afference(rows, cols, vals, n,
                                            intf.aff[ai], intf.aff[aj], k_ij)

        # Out-of-plane sliding block
        if len(intf.slid_out_plan) >= 2:
            k_sop = intf.status.kslid_out_plan
            for i in range(d2):
                for j in range(d2):
                    ai = d0 + d1 + i
                    aj = d0 + d1 + j
                    k_ij = k_sop[i][j]
                    if ai < len(intf.aff) and aj < len(intf.aff):
                        _assemble_afference(rows, cols, vals, n,
                                            intf.aff[ai], intf.aff[aj], k_ij)

    K = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsc()
    return K


class _AssemblyPlanIncompatible(RuntimeError):
    """Internal signal requesting the exact legacy scatter fallback."""


@dataclass(slots=True)
class _InterfaceAssemblyLayout:
    interface: Interface
    aff_lists: tuple[Any, ...]
    d0: int
    d1: int
    d2: int
    has_slid: bool
    has_out_of_plane: bool


@dataclass(slots=True)
class _StiffnessBatchData:
    """Dense precomputed geometry and metadata for compiled batch stiffness evaluation."""

    quad_dalfa_sq: np.ndarray
    quad_k0: np.ndarray
    quad_is_elastic: np.ndarray
    term_offsets: np.ndarray
    lengths: np.ndarray
    constrained_flags: np.ndarray
    d2_flags: np.ndarray
    has_slid_flags: np.ndarray
    has_sop_flags: np.ndarray
    sop_di: np.ndarray
    sop_dj: np.ndarray
    nrows: np.ndarray
    ncols: np.ndarray
    spring_counts: np.ndarray
    spring_offsets: np.ndarray
    sum_di2: np.ndarray
    sum_dj2: np.ndarray
    sum_didj: np.ndarray
    sum_dm: np.ndarray
    sum_dm2: np.ndarray
    sum_ecc2: np.ndarray
    sum_djecc: np.ndarray
    sum_diecc: np.ndarray
    flat_di: np.ndarray
    flat_dj: np.ndarray
    flat_ecc: np.ndarray
    flat_dm: np.ndarray
    slid_managed_idx: np.ndarray
    slid_k0: np.ndarray
    sop0_managed_idx: np.ndarray
    sop0_k0: np.ndarray
    sop1_managed_idx: np.ndarray
    sop1_k0: np.ndarray
    spring_k0: np.ndarray

    def compatible(self, model: Model) -> bool:
        if model.collections is None:
            return False
        if len(self.lengths) != len(model.collections.interfaces):
            return False
        if len(self.quad_k0) != len(model.collections.quads):
            return False
        return True


@dataclass(slots=True)
class _StiffnessAssemblyPlan:
    """C#-ordered fixed CSC scatter topology for a prepared model.

    HiStrA C# first maps a fixed symmetric sparse mask, then every AssembleK
    call performs ``Ax[idx] += value`` immediately in element/local-loop order.
    Rebuilding COO triplets and consolidating duplicates changes that floating-
    point accumulation order.  This plan stores the exact contribution stream
    and the target CSC slot for every contribution so nonlinear iterations can
    replay C# assembly without Python object traversal.
    """

    n: int
    all_quads: tuple[Quad, ...]
    quad_terms: tuple[tuple[Quad, Any], ...]
    interfaces: tuple[_InterfaceAssemblyLayout, ...]
    indptr: np.ndarray
    indices: np.ndarray
    output_indices: np.ndarray
    term_indices: np.ndarray
    alpha_i: np.ndarray
    alpha_j: np.ndarray
    term_count: int
    batch_data: Optional[_StiffnessBatchData] = None
    validated_runtime_id: int = 0

    def compatible(self, model: Model) -> bool:
        if int(model.gdl) != self.n or model.collections is None:
            return False
        quads = model.collections.quads
        interfaces = model.collections.interfaces
        if len(quads) != len(self.all_quads) or len(interfaces) != len(self.interfaces):
            return False
        if self.batch_data is not None and not self.batch_data.compatible(model):
            return False
        for current, expected in zip(quads.values(), self.all_quads):
            if current is not expected:
                return False
        for current, layout in zip(interfaces.values(), self.interfaces):
            if current is not layout.interface:
                return False
            d0 = current.dim_aff[0] if len(current.dim_aff) > 0 else 6
            d1 = current.dim_aff[1] if len(current.dim_aff) > 1 else 2
            d2 = current.dim_aff[2] if len(current.dim_aff) > 2 else 4
            if (d0, d1, d2) != (layout.d0, layout.d1, layout.d2):
                return False
            if bool(current.slid) != layout.has_slid:
                return False
            if (len(current.slid_out_plan) >= 2) != layout.has_out_of_plane:
                return False
            if len(current.aff) != len(layout.aff_lists):
                return False
            for current_aff, expected_aff in zip(current.aff, layout.aff_lists):
                if current_aff is not expected_aff:
                    return False
        for quad, aff6 in self.quad_terms:
            if len(quad.aff) <= 6 or quad.aff[6] is not aff6:
                return False
        return True

    def ensure_batch_data(self, model: Model, runtime: Any) -> None:
        if self.batch_data is not None:
            return
        try:
            self.batch_data = _build_stiffness_batch_data(self, model, runtime)
        except Exception:
            self.batch_data = None

    def evaluate_and_assemble(
        self,
        model: Model,
        ls: Any,
        alfa: float,
        runtime: Any,
    ) -> None:
        if self.batch_data is None:
            self.ensure_batch_data(model, runtime)
        b = self.batch_data
        if b is None:
            terms = _fill_stiffness_terms(self)
        else:
            terms = np.empty(self.term_count, dtype=np.float64)
            quad_state = getattr(runtime, "quad_state", None)
            if quad_state is None:
                quad_state = np.empty((0, 66), dtype=np.float64)
            coulomb_state = getattr(runtime, "coulomb_state", None)
            if coulomb_state is None:
                coulomb_state = np.empty((0, 21), dtype=np.float64)
            trial = getattr(runtime, "trial", None)
            if trial is None:
                trial = np.empty((0, 10), dtype=np.float64)

            _evaluate_stiffness_terms_batch(
                terms,
                float(alfa),
                b.quad_dalfa_sq,
                b.quad_k0,
                b.quad_is_elastic,
                quad_state,
                b.term_offsets,
                b.lengths,
                b.constrained_flags,
                b.d2_flags,
                b.has_slid_flags,
                b.has_sop_flags,
                b.sop_di,
                b.sop_dj,
                b.nrows,
                b.ncols,
                b.spring_counts,
                b.spring_offsets,
                b.sum_di2,
                b.sum_dj2,
                b.sum_didj,
                b.sum_dm,
                b.sum_dm2,
                b.sum_ecc2,
                b.sum_djecc,
                b.sum_diecc,
                b.flat_di,
                b.flat_dj,
                b.flat_ecc,
                b.flat_dm,
                b.spring_k0,
                trial,
                b.slid_managed_idx,
                b.slid_k0,
                b.sop0_managed_idx,
                b.sop0_k0,
                b.sop1_managed_idx,
                b.sop1_k0,
                coulomb_state,
            )
            for q_idx, quad in enumerate(self.all_quads):
                quad.status.k = terms[q_idx]

        values = np.zeros(self.indices.size, dtype=np.float64)
        _accumulate_csharp_order(
            values,
            self.output_indices,
            self.term_indices,
            self.alpha_i,
            self.alpha_j,
            terms,
        )
        mat = sp.csc_matrix(
            (values, self.indices, self.indptr), shape=(self.n, self.n), copy=False
        )
        mat._has_sorted_indices = True
        mat._has_canonical_format = True
        ls.set_zero()
        ls.k = mat



def _expand_scatter_terms_numeric(
    *,
    aff_starts: np.ndarray,
    aff_lengths: np.ndarray,
    aff_gdls: np.ndarray,
    aff_coefficients: np.ndarray,
    term_aff_i: np.ndarray,
    term_aff_j: np.ndarray,
    term_values: np.ndarray,
    term_mirror: np.ndarray,
    chunk_terms: int = 8192,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Expand local afference Cartesian products with NumPy, in C# order.

    The old plan builder executed one Python function call per stiffness term
    and five ``array.array.append`` calls per emitted contribution.  Large
    bridges therefore spent several seconds creating ~2.8 million scalar
    records in Python before the numerical solve started.

    Here Python records only one compact metadata row per *local stiffness
    term*.  NumPy expands the variable-size Cartesian products in chunks.
    Ordering is unchanged:

    * terms remain in C# element/local-loop order;
    * ``ei`` is the outer loop and ``ej`` the inner loop;
    * mirrored interface contributions are emitted immediately after their
      corresponding forward contribution;
    * mirrored entries intentionally retain ``alpha_i, alpha_j`` in the same
      order as C# ``LinearSystem.SumK(..., d:false)``.
    """
    if term_values.size == 0:
        empty_i = np.empty(0, dtype=np.int32)
        empty_f = np.empty(0, dtype=np.float64)
        return empty_i, empty_i.copy(), empty_i.copy(), empty_f, empty_f.copy()

    len_i = aff_lengths[term_aff_i].astype(np.int64, copy=False)
    len_j = aff_lengths[term_aff_j].astype(np.int64, copy=False)
    factors = 1 + term_mirror.astype(np.int64, copy=False)
    counts = len_i * len_j * factors
    total = int(np.sum(counts, dtype=np.int64))

    rows = np.empty(total, dtype=np.int32)
    cols = np.empty(total, dtype=np.int32)
    out_terms = np.empty(total, dtype=np.int32)
    alpha_i = np.empty(total, dtype=np.float64)
    alpha_j = np.empty(total, dtype=np.float64)

    cursor = 0
    term_count = int(term_values.size)
    for begin in range(0, term_count, chunk_terms):
        stop = min(begin + chunk_terms, term_count)
        chunk_counts = counts[begin:stop]
        chunk_total = int(np.sum(chunk_counts, dtype=np.int64))
        if chunk_total == 0:
            continue

        # Metadata-row index for every emitted contribution in this chunk.
        meta = np.repeat(
            np.arange(begin, stop, dtype=np.int32),
            chunk_counts,
        )
        local_counts = chunk_counts.astype(np.int64, copy=False)
        starts = np.cumsum(local_counts, dtype=np.int64) - local_counts
        within = (
            np.arange(chunk_total, dtype=np.int64)
            - np.repeat(starts, local_counts)
        )

        factor = factors[meta]
        pair = within // factor
        nj = len_j[meta]
        ai_pos = aff_starts[term_aff_i[meta]] + pair // nj
        aj_pos = aff_starts[term_aff_j[meta]] + pair % nj

        forward_rows = aff_gdls[ai_pos]
        forward_cols = aff_gdls[aj_pos]
        mirrored = (factor == 2) & ((within & 1) == 1)

        target = slice(cursor, cursor + chunk_total)
        rows[target] = np.where(mirrored, forward_cols, forward_rows)
        cols[target] = np.where(mirrored, forward_rows, forward_cols)
        out_terms[target] = term_values[meta]
        alpha_i[target] = aff_coefficients[ai_pos]
        alpha_j[target] = aff_coefficients[aj_pos]
        cursor += chunk_total

    if cursor != total:
        raise _AssemblyPlanIncompatible(
            f"numeric stiffness scatter expansion wrote {cursor} of {total} entries"
        )
    return rows, cols, out_terms, alpha_i, alpha_j

def _map_contributions_to_csc_python(
    rows: np.ndarray,
    cols: np.ndarray,
    indptr: np.ndarray,
    indices: np.ndarray,
) -> np.ndarray:
    out = np.empty(rows.size, dtype=np.int32)
    for k in range(rows.size):
        row = int(rows[k])
        col = int(cols[k])
        lo = int(indptr[col])
        hi = int(indptr[col + 1])
        pos = int(np.searchsorted(indices[lo:hi], row)) + lo
        if pos >= hi or int(indices[pos]) != row:
            out[k] = -1
        else:
            out[k] = pos
    return out


if njit is not None:
    _map_contributions_to_csc_impl = njit(cache=True, nogil=True)(
        _map_contributions_to_csc_python
    )
else:  # pragma: no cover
    _map_contributions_to_csc_impl = _map_contributions_to_csc_python


def _map_contributions_to_csc(
    rows: np.ndarray,
    cols: np.ndarray,
    indptr: np.ndarray,
    indices: np.ndarray,
) -> np.ndarray:
    """Map contribution coordinates to sorted CSC slots without a huge dict."""
    out = _map_contributions_to_csc_impl(rows, cols, indptr, indices)
    if np.any(out < 0):
        bad = int(np.flatnonzero(out < 0)[0])
        raise _AssemblyPlanIncompatible(
            f"CSC mask is missing stiffness entry ({int(rows[bad])}, {int(cols[bad])})"
        )
    return out



def _build_stiffness_assembly_plan(model: Model) -> _StiffnessAssemblyPlan:
    """Build immutable global scatter topology in exact C# assembly order.

    Only local-term metadata is accumulated in Python.  The millions of
    individual afference contributions are expanded numerically afterwards.
    """
    if model.collections is None:
        raise _AssemblyPlanIncompatible("Model.collections is not initialized")

    n = int(model.gdl)
    all_quads = tuple(model.collections.quads.values())
    quad_terms: list[tuple[Quad, Any]] = []

    # Flatten every distinct afference list once.  Each interface aff[i] list
    # is reused by many local stiffness terms, so repeatedly traversing those
    # Python objects was pure overhead in the former builder.
    aff_cache: dict[int, int] = {}
    aff_starts_list: list[int] = []
    aff_lengths_list: list[int] = []
    aff_gdls_list: list[int] = []
    aff_coefficients_list: list[float] = []

    def register_aff(entries: List[AfferenceEntry]) -> int:
        cache_key = id(entries)
        cached = aff_cache.get(cache_key)
        if cached is not None:
            return cached

        slot = len(aff_starts_list)
        aff_cache[cache_key] = slot
        start = len(aff_gdls_list)
        for entry in entries:
            gdl = int(entry.gdl) - 1
            if 0 <= gdl < n:
                aff_gdls_list.append(gdl)
                aff_coefficients_list.append(float(entry.alfa))
        aff_starts_list.append(start)
        aff_lengths_list.append(len(aff_gdls_list) - start)
        return slot

    # One metadata row per local stiffness term that can emit contributions.
    term_aff_i_list: list[int] = []
    term_aff_j_list: list[int] = []
    term_values_list: list[int] = []
    term_mirror_list: list[bool] = []

    append_term_i = term_aff_i_list.append
    append_term_j = term_aff_j_list.append
    append_term_value = term_values_list.append
    append_term_mirror = term_mirror_list.append

    term_index = 0

    # C# ModelManager.AssembleK: all Quads first, each Aff[6] i,j pair.
    for quad in all_quads:
        if not quad.aff or len(quad.aff) <= 6 or not quad.aff[6]:
            continue
        aff6 = quad.aff[6]
        quad_terms.append((quad, aff6))
        slot = register_aff(aff6)
        if aff_lengths_list[slot]:
            append_term_i(slot)
            append_term_j(slot)
            append_term_value(term_index)
            append_term_mirror(False)
        term_index += 1

    # Then Interfaces. C# reads only the local upper triangle and immediately
    # mirrors every off-diagonal local term via LinearSystem.SumK(..., d:false).
    interface_layouts: list[_InterfaceAssemblyLayout] = []
    for intf in model.collections.interfaces.values():
        aff = intf.aff
        aff_len = len(aff)
        d0 = intf.dim_aff[0] if len(intf.dim_aff) > 0 else 6
        d1 = intf.dim_aff[1] if len(intf.dim_aff) > 1 else 2
        d2 = intf.dim_aff[2] if len(intf.dim_aff) > 2 else 4

        has_slid = bool(intf.slid)
        has_out_of_plane = len(intf.slid_out_plan) >= 2
        # Register each local afference list exactly once. The previous
        # record_term path performed two cached function/dict lookups for every
        # one of the ~34 local stiffness terms per interface.
        aff_slots = [register_aff(entries) for entries in aff]
        interface_layouts.append(
            _InterfaceAssemblyLayout(
                interface=intf,
                aff_lists=tuple(aff),
                d0=d0,
                d1=d1,
                d2=d2,
                has_slid=has_slid,
                has_out_of_plane=has_out_of_plane,
            )
        )

        for i in range(d0):
            for j in range(i, d0):
                if i < aff_len and j < aff_len:
                    slot_i = aff_slots[i]
                    slot_j = aff_slots[j]
                    if aff_lengths_list[slot_i] and aff_lengths_list[slot_j]:
                        append_term_i(slot_i)
                        append_term_j(slot_j)
                        append_term_value(term_index)
                        append_term_mirror(i != j)
                term_index += 1

        if has_slid:
            for i in range(d1):
                for j in range(i, d1):
                    ai_idx = d0 + i
                    aj_idx = d0 + j
                    if ai_idx < aff_len and aj_idx < aff_len:
                        slot_i = aff_slots[ai_idx]
                        slot_j = aff_slots[aj_idx]
                        if aff_lengths_list[slot_i] and aff_lengths_list[slot_j]:
                            append_term_i(slot_i)
                            append_term_j(slot_j)
                            append_term_value(term_index)
                            append_term_mirror(ai_idx != aj_idx)
                    term_index += 1

        if has_out_of_plane:
            for i in range(d2):
                for j in range(i, d2):
                    ai_idx = d0 + d1 + i
                    aj_idx = d0 + d1 + j
                    if ai_idx < aff_len and aj_idx < aff_len:
                        slot_i = aff_slots[ai_idx]
                        slot_j = aff_slots[aj_idx]
                        if aff_lengths_list[slot_i] and aff_lengths_list[slot_j]:
                            append_term_i(slot_i)
                            append_term_j(slot_j)
                            append_term_value(term_index)
                            append_term_mirror(ai_idx != aj_idx)
                    term_index += 1

    aff_starts = np.asarray(aff_starts_list, dtype=np.int64)
    aff_lengths = np.asarray(aff_lengths_list, dtype=np.int32)
    aff_gdls = np.asarray(aff_gdls_list, dtype=np.int32)
    aff_coefficients = np.asarray(aff_coefficients_list, dtype=np.float64)
    term_aff_i = np.asarray(term_aff_i_list, dtype=np.int32)
    term_aff_j = np.asarray(term_aff_j_list, dtype=np.int32)
    term_values = np.asarray(term_values_list, dtype=np.int32)
    term_mirror = np.asarray(term_mirror_list, dtype=np.bool_)

    row_arr, col_arr, contribution_terms, alpha_i, alpha_j = (
        _expand_scatter_terms_numeric(
            aff_starts=aff_starts,
            aff_lengths=aff_lengths,
            aff_gdls=aff_gdls,
            aff_coefficients=aff_coefficients,
            term_aff_i=term_aff_i,
            term_aff_j=term_aff_j,
            term_values=term_values,
            term_mirror=term_mirror,
        )
    )

    # C# ComputeMaskK begins by inserting every diagonal.
    # MapSparseMatrix then sorts row indices within each CSC column.
    pattern = sp.coo_matrix(
        (
            np.ones(row_arr.size, dtype=np.int8),
            (row_arr, col_arr),
        ),
        shape=(n, n),
    ).tocsc()
    pattern.setdiag(1)
    pattern.sum_duplicates()
    pattern.sort_indices()

    indptr = np.asarray(pattern.indptr, dtype=np.int32).copy()
    indices = np.asarray(pattern.indices, dtype=np.int32).copy()
    output_indices = _map_contributions_to_csc(
        row_arr, col_arr, indptr, indices,
    )

    return _StiffnessAssemblyPlan(
        n=n,
        all_quads=all_quads,
        quad_terms=tuple(quad_terms),
        interfaces=tuple(interface_layouts),
        indptr=indptr,
        indices=indices,
        output_indices=output_indices,
        term_indices=contribution_terms,
        alpha_i=alpha_i,
        alpha_j=alpha_j,
        term_count=term_index,
    )

def _fill_stiffness_terms(plan: _StiffnessAssemblyPlan) -> np.ndarray:
    terms = np.empty(plan.term_count, dtype=np.float64)
    index = 0
    for quad, _aff6 in plan.quad_terms:
        terms[index] = float(quad.status.k)
        index += 1

    for layout in plan.interfaces:
        st = layout.interface.status
        k = st.k
        d0 = layout.d0
        if d0 == 6:
            r0 = k[0]; r1 = k[1]; r2 = k[2]; r3 = k[3]; r4 = k[4]; r5 = k[5]
            terms[index:index+21] = (
                r0[0], r0[1], r0[2], r0[3], r0[4], r0[5],
                r1[1], r1[2], r1[3], r1[4], r1[5],
                r2[2], r2[3], r2[4], r2[5],
                r3[3], r3[4], r3[5],
                r4[4], r4[5],
                r5[5]
            )
            index += 21
        else:
            for i in range(d0):
                row = k[i]
                for j in range(i, d0):
                    terms[index] = float(row[j])
                    index += 1
        if layout.has_slid:
            ks = st.kslid
            d1 = layout.d1
            if d1 == 2:
                r0 = ks[0]; r1 = ks[1]
                terms[index:index+3] = (r0[0], r0[1], r1[1])
                index += 3
            else:
                for i in range(d1):
                    row = ks[i]
                    for j in range(i, d1):
                        terms[index] = float(row[j])
                        index += 1
        if layout.has_out_of_plane:
            ko = st.kslid_out_plan
            d2 = layout.d2
            if d2 == 4:
                r0 = ko[0]; r1 = ko[1]; r2 = ko[2]; r3 = ko[3]
                terms[index:index+10] = (
                    r0[0], r0[1], r0[2], r0[3],
                    r1[1], r1[2], r1[3],
                    r2[2], r2[3],
                    r3[3]
                )
                index += 10
            else:
                for i in range(d2):
                    row = ko[i]
                    for j in range(i, d2):
                        terms[index] = float(row[j])
                        index += 1
    if index != plan.term_count:
        raise _AssemblyPlanIncompatible(
            f"stiffness term layout changed ({index} != {plan.term_count})"
        )
    return terms


def _accumulate_csharp_order_python(
    values: np.ndarray,
    output_indices: np.ndarray,
    term_indices: np.ndarray,
    alpha_i: np.ndarray,
    alpha_j: np.ndarray,
    terms: np.ndarray,
) -> None:
    # Deliberately scalar and left-associated, matching:
    #   a = k * alfa_i * alfa_j; Ax[idx] += a
    for k in range(output_indices.size):
        a = terms[term_indices[k]] * alpha_i[k]
        a = a * alpha_j[k]
        values[output_indices[k]] += a


if njit is not None:
    _accumulate_csharp_order_impl = njit(cache=True, nogil=True)(
        _accumulate_csharp_order_python
    )
else:  # pragma: no cover
    _accumulate_csharp_order_impl = _accumulate_csharp_order_python


def _accumulate_csharp_order(
    values: np.ndarray,
    output_indices: np.ndarray,
    term_indices: np.ndarray,
    alpha_i: np.ndarray,
    alpha_j: np.ndarray,
    terms: np.ndarray,
) -> None:
    _accumulate_csharp_order_impl(
        values, output_indices, term_indices, alpha_i, alpha_j, terms
    )


def _evaluate_stiffness_terms_batch_python(
    terms: np.ndarray,
    alfa: float,
    quad_dalfa_sq: np.ndarray,
    quad_k0: np.ndarray,
    quad_is_elastic: np.ndarray,
    quad_state: np.ndarray,
    term_offsets: np.ndarray,
    lengths: np.ndarray,
    constrained_flags: np.ndarray,
    d2_flags: np.ndarray,
    has_slid_flags: np.ndarray,
    has_sop_flags: np.ndarray,
    sop_di: np.ndarray,
    sop_dj: np.ndarray,
    nrows: np.ndarray,
    ncols: np.ndarray,
    spring_counts: np.ndarray,
    spring_offsets: np.ndarray,
    sum_di2: np.ndarray,
    sum_dj2: np.ndarray,
    sum_didj: np.ndarray,
    sum_dm: np.ndarray,
    sum_dm2: np.ndarray,
    sum_ecc2: np.ndarray,
    sum_djecc: np.ndarray,
    sum_diecc: np.ndarray,
    flat_di: np.ndarray,
    flat_dj: np.ndarray,
    flat_ecc: np.ndarray,
    flat_dm: np.ndarray,
    spring_k0: np.ndarray,
    transverse_trial: np.ndarray,
    slid_managed_idx: np.ndarray,
    slid_k0: np.ndarray,
    sop0_managed_idx: np.ndarray,
    sop0_k0: np.ndarray,
    sop1_managed_idx: np.ndarray,
    sop1_k0: np.ndarray,
    coulomb_state: np.ndarray,
) -> None:
    # ── Quads ──
    nq = len(quad_k0)
    for q in range(nq):
        if quad_is_elastic[q] or alfa == 0.0:
            kq = quad_k0[q]
        else:
            kt = quad_state[q, QKTANG]
            kq = quad_k0[q] + (kt - quad_k0[q]) * alfa
        terms[q] = kq * quad_dalfa_sq[q]

    # ── Interfaces ──
    ni = len(term_offsets)
    for i in range(ni):
        t_idx = term_offsets[i]
        L = lengths[i]
        L2 = L * L
        c = constrained_flags[i]
        d2 = d2_flags[i]
        nr = nrows[i]
        nc = ncols[i]
        sc = spring_counts[i]
        sp_base = spring_offsets[i]

        num = 0.0
        num2 = 0.0
        num3 = 0.0
        for r in range(nr):
            row_offset = r * nc
            for col in range(nc):
                idx = row_offset + col
                if idx >= sc:
                    continue
                if alfa == 0.0:
                    k = spring_k0[sp_base + idx]
                else:
                    k0_val = spring_k0[sp_base + idx]
                    k = k0_val + (transverse_trial[sp_base + idx, 9] - k0_val) * alfa
                di = flat_di[sp_base + idx]
                dj = flat_dj[sp_base + idx]
                num += k * di * di
                num3 += k * di * dj
                num2 += k * dj * dj

        num4 = 0.0
        num5 = 0.0
        num6 = 0.0
        if c:
            for col in range(nc):
                for r in range(nr):
                    idx = r * nc + col
                    if idx >= sc:
                        continue
                    if alfa == 0.0:
                        k = spring_k0[sp_base + idx]
                    else:
                        k0_val = spring_k0[sp_base + idx]
                        k = k0_val + (transverse_trial[sp_base + idx, 9] - k0_val) * alfa
                    dm = flat_dm[sp_base + idx]
                    num4 += k
                    num5 -= k * dm
                    num6 += k * dm * dm

        out_of_plane_diag = 0.0
        num7 = 0.0
        num8 = 0.0
        if d2:
            for col in range(nc):
                for r in range(nr):
                    idx = r * nc + col
                    if idx >= sc:
                        continue
                    if alfa == 0.0:
                        k = spring_k0[sp_base + idx]
                    else:
                        k0_val = spring_k0[sp_base + idx]
                        k = k0_val + (transverse_trial[sp_base + idx, 9] - k0_val) * alfa
                    di = flat_di[sp_base + idx]
                    dj = flat_dj[sp_base + idx]
                    ecc = flat_ecc[sp_base + idx]
                    out_of_plane_diag += k * ecc * ecc
                    num7 += k * dj * ecc
                    num8 += k * di * ecc

        if L2 > 1e-30:
            num /= L2
            num3 /= L2
            num2 /= L2
        if L > 1e-30:
            num7 /= L
            num8 /= L

        if c:
            terms[t_idx + 0] = num4
            terms[t_idx + 1] = num5
            terms[t_idx + 2] = -num - num3
            terms[t_idx + 3] = -num3 - num2
            terms[t_idx + 4] = -num7 - num8
            terms[t_idx + 5] = num7 + num8
            terms[t_idx + 6] = num6
            terms[t_idx + 7] = num3 * L / 2.0 - num * L / 2.0
            terms[t_idx + 8] = num2 * L / 2.0 - num3 * L / 2.0
            terms[t_idx + 9] = (-num8 + num7) * L * 0.5
            terms[t_idx + 10] = (num8 - num7) * L * 0.5
            terms[t_idx + 11] = num
            terms[t_idx + 12] = num3
            terms[t_idx + 13] = num8
            terms[t_idx + 14] = -num8
            terms[t_idx + 15] = num2
            terms[t_idx + 16] = num7
            terms[t_idx + 17] = -num7
            terms[t_idx + 18] = out_of_plane_diag
            terms[t_idx + 19] = -out_of_plane_diag
            terms[t_idx + 20] = out_of_plane_diag
        else:
            terms[t_idx + 0] = num2
            terms[t_idx + 1] = num3
            terms[t_idx + 2] = -num3
            terms[t_idx + 3] = -num2
            terms[t_idx + 4] = -num7
            terms[t_idx + 5] = num7
            terms[t_idx + 6] = num
            terms[t_idx + 7] = -num
            terms[t_idx + 8] = -num3
            terms[t_idx + 9] = -num8
            terms[t_idx + 10] = num8
            terms[t_idx + 11] = num
            terms[t_idx + 12] = num3
            terms[t_idx + 13] = num8
            terms[t_idx + 14] = -num8
            terms[t_idx + 15] = num2
            terms[t_idx + 16] = num7
            terms[t_idx + 17] = -num7
            terms[t_idx + 18] = out_of_plane_diag
            terms[t_idx + 19] = -out_of_plane_diag
            terms[t_idx + 20] = out_of_plane_diag
        t_idx += 21

        if has_slid_flags[i]:
            sm_idx = slid_managed_idx[i]
            if sm_idx < 0 or alfa == 0.0:
                ks = slid_k0[i]
            else:
                kt = coulomb_state[sm_idx, CKTANG]
                ks = slid_k0[i] + (kt - slid_k0[i]) * alfa
            terms[t_idx + 0] = ks
            terms[t_idx + 1] = -ks
            terms[t_idx + 2] = ks
            t_idx += 3

        if has_sop_flags[i]:
            s0_idx = sop0_managed_idx[i]
            if s0_idx < 0 or alfa == 0.0:
                k1 = sop0_k0[i]
            else:
                kt0 = coulomb_state[s0_idx, CKTANG]
                k1 = sop0_k0[i] + (kt0 - sop0_k0[i]) * alfa

            s1_idx = sop1_managed_idx[i]
            if s1_idx < 0 or alfa == 0.0:
                k2 = sop1_k0[i]
            else:
                kt1 = coulomb_state[s1_idx, CKTANG]
                k2 = sop1_k0[i] + (kt1 - sop1_k0[i]) * alfa

            di_s = sop_di[i]
            dj_s = sop_dj[i]
            k00 = k1 * dj_s * dj_s + k2 * di_s * di_s
            k01 = (k1 + k2) * di_s * dj_s
            k11 = k1 * di_s * di_s + k2 * dj_s * dj_s
            terms[t_idx + 0] = k00
            terms[t_idx + 1] = k01
            terms[t_idx + 2] = -k00
            terms[t_idx + 3] = -k01
            terms[t_idx + 4] = k11
            terms[t_idx + 5] = -k01
            terms[t_idx + 6] = -k11
            terms[t_idx + 7] = k00
            terms[t_idx + 8] = k01
            terms[t_idx + 9] = k11


if njit is not None:
    _evaluate_stiffness_terms_batch = njit(cache=True, nogil=True)(
        _evaluate_stiffness_terms_batch_python
    )
else:  # pragma: no cover
    _evaluate_stiffness_terms_batch = _evaluate_stiffness_terms_batch_python


def _build_stiffness_batch_data(
    plan: _StiffnessAssemblyPlan,
    model: Model,
    runtime: Any,
) -> Optional[_StiffnessBatchData]:
    if getattr(runtime, "records", None) is None:
        return None
    if len(runtime.records) != len(plan.interfaces):
        return None
    if len(getattr(runtime, "quad_records", ())) != len(plan.all_quads):
        return None

    for layout in plan.interfaces:
        if layout.d0 != 6:
            return None
        if layout.has_slid and layout.d1 != 2:
            return None
        if layout.has_out_of_plane and layout.d2 != 4:
            return None

    quad_dalfa_sq = np.array(
        [float(csharp_pow(q.d_alfa_2d_diag(), 2.0)) for q, _ in plan.quad_terms],
        dtype=np.float64,
    )
    quad_k0 = np.array(
        [float(getattr(q.spring, "k", 0.0)) for q, _ in plan.quad_terms],
        dtype=np.float64,
    )
    quad_is_elastic = np.array(
        [int(isinstance(q.spring, SpringElastic)) for q, _ in plan.quad_terms],
        dtype=np.int8,
    )

    n_intf = len(plan.interfaces)
    term_offsets = np.empty(n_intf, dtype=np.int32)
    lengths = np.empty(n_intf, dtype=np.float64)
    constrained_flags = np.empty(n_intf, dtype=np.int8)
    d2_flags = np.empty(n_intf, dtype=np.int8)
    has_slid_flags = np.empty(n_intf, dtype=np.int8)
    has_sop_flags = np.empty(n_intf, dtype=np.int8)
    sop_di = np.empty(n_intf, dtype=np.float64)
    sop_dj = np.empty(n_intf, dtype=np.float64)
    nrows = np.empty(n_intf, dtype=np.int32)
    ncols = np.empty(n_intf, dtype=np.int32)
    spring_counts = np.empty(n_intf, dtype=np.int32)
    spring_offsets = np.empty(n_intf, dtype=np.int32)

    sum_di2 = np.empty(n_intf, dtype=np.float64)
    sum_dj2 = np.empty(n_intf, dtype=np.float64)
    sum_didj = np.empty(n_intf, dtype=np.float64)
    sum_dm = np.empty(n_intf, dtype=np.float64)
    sum_dm2 = np.empty(n_intf, dtype=np.float64)
    sum_ecc2 = np.empty(n_intf, dtype=np.float64)
    sum_djecc = np.empty(n_intf, dtype=np.float64)
    sum_diecc = np.empty(n_intf, dtype=np.float64)

    all_di: list[float] = []
    all_dj: list[float] = []
    all_ecc: list[float] = []
    all_dm: list[float] = []
    all_k0: list[float] = []

    term_idx = len(plan.quad_terms)
    sp_offset = 0

    for i, layout in enumerate(plan.interfaces):
        intf = layout.interface
        term_offsets[i] = term_idx
        lengths[i] = float(intf.length)
        constrained_flags[i] = int(intf.interfaccia_vincolata_computed())
        d2_flags[i] = int(layout.d2 > 0)
        has_slid_flags[i] = int(layout.has_slid)
        has_sop_flags[i] = int(layout.has_out_of_plane)

        if layout.has_out_of_plane and len(intf.slid_out_plan) >= 2:
            di_v, dj_v = intf.compute_dist_spring_for(intf)
            sop_di[i] = float(di_v)
            sop_dj[i] = float(dj_v)
        else:
            sop_di[i] = 0.0
            sop_dj[i] = 0.0

        nr = max(intf.nrow, 1)
        nc = max(intf.ncol, 1)
        sc = min(nr * nc, len(intf.trasv_1))
        nrows[i] = nr
        ncols[i] = nc
        spring_counts[i] = sc
        spring_offsets[i] = sp_offset

        intf._ensure_stiffness_geometry_cache()
        sum_di2[i] = float(intf._perf_sum_di2 or 0.0)
        sum_dj2[i] = float(intf._perf_sum_dj2 or 0.0)
        sum_didj[i] = float(intf._perf_sum_didj or 0.0)
        sum_dm[i] = float(intf._perf_sum_dm or 0.0)
        sum_dm2[i] = float(intf._perf_sum_dm2 or 0.0)
        sum_ecc2[i] = float(intf._perf_sum_ecc2 or 0.0)
        sum_djecc[i] = float(intf._perf_sum_djecc or 0.0)
        sum_diecc[i] = float(intf._perf_sum_diecc or 0.0)

        di_c = intf._perf_di[:sc]
        dj_c = intf._perf_dj[:sc]
        ecc_c = intf._perf_ecc[:sc]
        L = float(intf.length)
        for s_idx in range(sc):
            all_di.append(float(di_c[s_idx]))
            all_dj.append(float(dj_c[s_idx]))
            all_ecc.append(float(ecc_c[s_idx]))
            all_dm.append(0.5 * L - float(di_c[s_idx]))
            all_k0.append(float(intf.trasv_1[s_idx].k))

        sp_offset += sc
        term_idx += 21 + (3 if layout.has_slid else 0) + (10 if layout.has_out_of_plane else 0)

    flat_di = np.asarray(all_di, dtype=np.float64)
    flat_dj = np.asarray(all_dj, dtype=np.float64)
    flat_ecc = np.asarray(all_ecc, dtype=np.float64)
    flat_dm = np.asarray(all_dm, dtype=np.float64)
    spring_k0 = np.asarray(all_k0, dtype=np.float64)

    slid_managed_idx = np.asarray(getattr(runtime, "_slid_index", ()), dtype=np.int32).copy()
    slid_k0 = np.array(
        [float(layout.interface.slid[0].k) if layout.has_slid and layout.interface.slid else 0.0
         for layout in plan.interfaces],
        dtype=np.float64,
    )
    sop0_managed_idx = np.asarray(getattr(runtime, "_oop0_index", ()), dtype=np.int32).copy()
    sop0_k0 = np.array(
        [float(layout.interface.slid_out_plan[0].k) if layout.has_out_of_plane and len(layout.interface.slid_out_plan) >= 1 else 0.0
         for layout in plan.interfaces],
        dtype=np.float64,
    )
    sop1_managed_idx = np.asarray(getattr(runtime, "_oop1_index", ()), dtype=np.int32).copy()
    sop1_k0 = np.array(
        [float(layout.interface.slid_out_plan[1].k) if layout.has_out_of_plane and len(layout.interface.slid_out_plan) >= 2 else 0.0
         for layout in plan.interfaces],
        dtype=np.float64,
    )

    return _StiffnessBatchData(
        quad_dalfa_sq=quad_dalfa_sq,
        quad_k0=quad_k0,
        quad_is_elastic=quad_is_elastic,
        term_offsets=term_offsets,
        lengths=lengths,
        constrained_flags=constrained_flags,
        d2_flags=d2_flags,
        has_slid_flags=has_slid_flags,
        has_sop_flags=has_sop_flags,
        sop_di=sop_di,
        sop_dj=sop_dj,
        nrows=nrows,
        ncols=ncols,
        spring_counts=spring_counts,
        spring_offsets=spring_offsets,
        sum_di2=sum_di2,
        sum_dj2=sum_dj2,
        sum_didj=sum_didj,
        sum_dm=sum_dm,
        sum_dm2=sum_dm2,
        sum_ecc2=sum_ecc2,
        sum_djecc=sum_djecc,
        sum_diecc=sum_diecc,
        flat_di=flat_di,
        flat_dj=flat_dj,
        flat_ecc=flat_ecc,
        flat_dm=flat_dm,
        slid_managed_idx=slid_managed_idx,
        slid_k0=slid_k0,
        sop0_managed_idx=sop0_managed_idx,
        sop0_k0=sop0_k0,
        sop1_managed_idx=sop1_managed_idx,
        sop1_k0=sop1_k0,
        spring_k0=spring_k0,
    )


def _assemble_global_k_cached(model: Model, plan: _StiffnessAssemblyPlan) -> sp.csc_matrix:
    terms = _fill_stiffness_terms(plan)
    values = np.zeros(plan.indices.size, dtype=np.float64)
    _accumulate_csharp_order(
        values,
        plan.output_indices,
        plan.term_indices,
        plan.alpha_i,
        plan.alpha_j,
        terms,
    )
    mat = sp.csc_matrix(
        (values, plan.indices, plan.indptr), shape=(plan.n, plan.n), copy=False
    )
    mat._has_sorted_indices = True
    mat._has_canonical_format = True
    return mat


def _get_stiffness_assembly_plan(model: Model) -> _StiffnessAssemblyPlan:
    plan = getattr(model, "_perf_stiffness_assembly_plan", None)
    if isinstance(plan, _StiffnessAssemblyPlan) and plan.compatible(model):
        return plan
    plan = _build_stiffness_assembly_plan(model)
    setattr(model, "_perf_stiffness_assembly_plan", plan)
    return plan


def assemble_global_k(
    model: Model,
    alfa: float = 0.0,
    *,
    recompute_elements: bool = True,
) -> sp.csc_matrix:
    """Assemble global stiffness, reusing static scatter topology when safe.

    ``recompute_elements=True`` intentionally retains the original standalone
    implementation. The nonlinear solver first computes every element block
    and calls this function with ``recompute_elements=False``; only that path
    uses the topology cache. If the prepared topology has changed, the cache is
    rebuilt. If a cached layout cannot be consumed safely, the authoritative
    legacy scatter remains the fallback.
    """
    if recompute_elements:
        return _assemble_global_k_legacy(
            model, alfa=alfa, recompute_elements=True
        )
    try:
        plan = _get_stiffness_assembly_plan(model)
        return _assemble_global_k_cached(model, plan)
    except _AssemblyPlanIncompatible:
        if hasattr(model, "_perf_stiffness_assembly_plan"):
            delattr(model, "_perf_stiffness_assembly_plan")
        return _assemble_global_k_legacy(
            model, alfa=alfa, recompute_elements=False
        )


from histra.solver.boundary_conditions import (
    apply_boundary_conditions,
    get_restrained_dofs,
)

__all__ = [
    "assemble_global_k",
    "apply_boundary_conditions",
    "get_restrained_dofs",
]
