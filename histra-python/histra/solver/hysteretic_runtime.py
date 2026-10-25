"""Dense-state batch runtime for the compiled hysteretic kernels.

Owns ``HystereticBatchRuntime`` (dense committed/trial arrays, material
mutation, snapshots, object synchronization and cached result APIs), the
fused ``_update_domain_batch`` orchestrator kernel, the thread-count policy
helpers and the compact parameter view. The kernels themselves live in
:mod:`histra.solver.hysteretic_kernels` and the immutable topology in
:mod:`histra.solver.hysteretic_topology`.

Key invariants that must survive any refactor:

* no extra Python call boundary inside the fused correction hot path;
* no forced object synchronization during normal Newton corrections;
* snapshots restore every dense state array exactly;
* interface material mutation refreshes only affected slices;
* force and max-u caches have explicit invalidation rules;
* unmanaged spring fallback remains correct and visible in performance counts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from typing import Any, Iterator, Sequence

import numpy as np

from histra.model.shear_law import (
    ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION,
    ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED,
    fracture_energy_shear,
    masonry_shear_law_code,
)
from histra.springs.energy import spring_energy_increment
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.types.phase_enum import PhaseEnum

try:  # optional acceleration dependency
    from numba import config as numba_config
    from numba import get_num_threads, njit, prange, set_num_threads
except Exception:  # pragma: no cover - exercised when numba is unavailable
    numba_config = None
    get_num_threads = None
    njit = None
    set_num_threads = None


from histra.solver.hysteretic_kernels.transverse import (
    COMPRESSIVE_LINEAR,
    COMPRESSIVE_PARABOLIC,
    COMPRESSIVE_CURVE_TYPE_PARAM,
    ELASTIC,
    LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE,
    PLASTIC_C,
    PLASTIC_T,
    RELOAD_C,
    RELOAD_T,
    RUPTURE,
    RUPTURE_C,
    RUPTURE_T,
    SIMPLE_PARAM_NAMES,
    SIMPLE_TENSILE_CURVE_TYPE_PARAM,
    SIMPLE_TRANSVERSE_PARAM_SIZE,
    TENSILE_CURVE_TYPE_PARAM,
    TENSILE_EXPONENTIAL,
    TENSILE_LINEAR,
    TRANSVERSE_PARAM_SIZE,
    UNLOAD_C,
    UNLOAD_T,
    _PARAM_NAMES,
    _advance_and_evaluate_simple_linear_batch,
    _advance_evaluate_and_finish_simple_linear_batch,
    _advance_transverse_targets,
    _evaluate_linear_batch,
    _evaluate_simple_linear_batch,
    _finish_transverse_batch,
    _pos_rotlim_typed,
    _pos_stress_typed,
    _pos_tangent_typed,
)

from histra.solver.hysteretic_kernels.interface_coulomb import (
    CCUNLOAD_T,
    CCUNLOAD_C,
    CCPLASTIC_T,
    CCPLASTIC_C,
    CTANGENT_RELOAD_T,
    CTANGENT_RELOAD_C,
    CCCONTACT_AREA,
    CCENERGY,
    CCPHASE,
    CCSTRAIN,
    CCSTRESS,
    CCSTRESS_NORMAL,
    CCSTRESS_NORMAL_PREV,
    CCUP,
    CDN,
    CF,
    CFY0,
    CFY1,
    CKTANG,
    CKTANG_COMMITTED,
    CMOM1N,
    CMOM1P,
    CMOM2N,
    CMOM2P,
    CROT1N,
    CROT1P,
    CROT2N,
    CROT2P,
    CROT3N,
    CROT3P,
    COULOMB_STATE_SIZE,
    CTCONTACT_AREA,
    CTENERGY,
    CTPHASE,
    CTSTRAIN,
    CTSTRESS,
    CTSTRESS_NORMAL,
    CTUP,
    CU,
    _advance_interface_coulomb_targets,
    _assemble_full_interface_forces,
    _commit_elastic_sliding_batch,
    _commit_initial_coulomb_batch,
    _evaluate_elastic_sliding_batch,
    _evaluate_initial_coulomb_batch,
)

from histra.solver.hysteretic_kernels.quad_takeda import (
    QCCONTACT,
    QCENERGY,
    QCLOAD,
    QCMOM_MAX,
    QCMOM_MIN,
    QCPLAST_C,
    QCPLAST_T,
    QCROT_LIM_NU,
    QCROT_LIM_PU,
    QCROT_NU,
    QCROT_PU,
    QCROT_YP,
    QCROT_YN,
    QCSTRAIN,
    QCSTRESS,
    QCSTRESS_NORMAL,
    QCSTRESS_NORMAL_PREV,
    QCUNLOAD_C,
    QCUNLOAD_T,
    QCUP,
    QDN,
    QFY0,
    QFY1,
    QKTANG,
    QKTANG_COMMITTED,
    QMOM1N,
    QMOM1P,
    QMOM2N,
    QMOM2P,
    QMOM3N,
    QMOM3P,
    QPBCACOVIC,
    QPCOHESION,
    QPENABLED,
    QPE1N,
    QPE1P,
    QPE2N,
    QPE2P,
    QPE3N,
    QPE3P,
    QPEUP,
    QPEUN,
    QPFRACTURE_ENERGY,
    QPFRACTURE_MODE,
    QPH,
    QPHASE,
    QPHYSTERETIC_TYPE,
    QPK,
    QPPLASTIC_STRAIN,
    QPMU,
    QPSUBLAW,
    QROT1N,
    QROT1P,
    QROT2N,
    QROT2P,
    QROT3N,
    QROT3P,
    QTANG_RELOAD_C,
    QTANG_RELOAD_T,
    QTCONTACT,
    QTENERGY,
    QTLOAD,
    QTMOM_MAX,
    QTMOM_MIN,
    QTPHASE,
    QTPLAST_C,
    QTPLAST_T,
    QTROT_LIM_NU,
    QTROT_LIM_PU,
    QTROT_MAX,
    QTROT_MIN,
    QTROT_NU,
    QTROT_PU,
    QTROT_YP,
    QTROT_YN,
    QTSTRAIN,
    QTSTRESS,
    QTSTRESS_NORMAL,
    QTUNLOAD_C,
    QTUNLOAD_T,
    QTUP,
    QUAD_FRACTURE_FIXED,
    QUAD_FRACTURE_INTERPOLATED,
    QUAD_FRACTURE_NONE,
    QUAD_HYSTERETIC_INITIAL,
    QUAD_HYSTERETIC_TAKEDA,
    QUAD_PARAM_SIZE,
    QUAD_SUBLAW_CACOVIC,
    QUAD_SUBLAW_COULOMB,
    QUAD_SUBLAW_ELASTIC,
    QUAD_SUBLAW_HYSTERETIC,
    QHPARAMS, QHCOMMITTED, QHTRIAL,
    _mirror_hysteretic_quad, _revert_hysteretic_quad,
    QUAD_STATE_SIZE,
    QUMAX0,
    QUMAX1,
    QUR0,
    QUR1,
    _commit_quad_takeda_batch,
    _evaluate_quad_takeda_batch,
    _quad_interpolated_shear_energy,
    _quad_shear_ultimate_strain,
    _quad_tau_limit,
    _quad_tangent_reload_c,
    _quad_tangent_reload_t,
    _quad_yield_compression,
    _quad_yield_tension,
    _quad_revert_trial,
)
from histra.solver.hysteretic_topology import (
    _InterfaceSlice,
    _SIMPLE_PARAM_GETTER,
    _PARAM_GETTER,
    _build_force_by_dof_topology,
    _extract_spring_committed,
    _extract_spring_compressive_curve_type,
    _extract_spring_curve_type,
    _extract_spring_params,
    _extract_spring_target,
    _extract_spring_trial,
)
from histra.solver.hysteretic_kernels.kinematics import (
    _map_and_prepare_interface_kinematics,
    _map_global_to_local,
    _prepare_interface_kinematics,
    _prepare_quad_kinematics,
)
from histra.solver.hysteretic_kernels.scatter import (
    _batch_interface_resultants,
    _eval_pdelta_interfaces_kernel,
    _eval_pdelta_line_loads_kernel,
    _refresh_global_resisting_force,
    _refresh_global_resisting_force_by_dof,
    _refresh_max_u_cache,
    _scatter_local_forces,
)


@dataclass(frozen=True)
class PDeltaPlan:
    """Precomputed static topology and geometry for compiled P-Delta load assembly."""

    quad_indices: np.ndarray
    intf_indices: np.ndarray
    r_arr: np.ndarray
    R_arr: np.ndarray
    scatter_quad_idx: np.ndarray
    scatter_comp: np.ndarray
    scatter_dof: np.ndarray
    scatter_alfa: np.ndarray
    scatter_offsets: np.ndarray


@dataclass(frozen=True)
class PDeltaLineLoadPlan:
    """Analysis-specific, object-free inputs for line-load P-Delta assembly."""

    load_quad_indices: np.ndarray
    load_r_arr: np.ndarray
    item_offsets: np.ndarray
    item_forces: np.ndarray


# ``PhaseEnum(code)`` goes through EnumMeta on every call.  Dense batch rows
# contain only the canonical C# phase codes 0..10, so reuse the singleton
# IntEnum objects.  The fallback retains the former ValueError semantics if a
# corrupted/out-of-range state ever reaches the object synchronization path.
_PHASE_BY_CODE = tuple(PhaseEnum(code) for code in range(11))


def _phase_from_code(value: float | int) -> PhaseEnum:
    code = int(value)
    if 0 <= code < len(_PHASE_BY_CODE):
        return _PHASE_BY_CODE[code]
    return PhaseEnum(code)




if njit is not None:

    @njit(cache=True, nogil=True, error_model="numpy")
    def _managed_elastic_energy(transverse_k, committed, trial, quad_k, quad_state,
                                starts, stops, coulomb_params, coulomb_state,
                                slid_index, oop0_index, oop1_index,
                                initial_elastic=0.0, initial_plastic=0.0):
        # Original ModelManager.ComputeEnergy: Quads first, then each
        # Interface's transverse, sliding and two out-of-plane springs.
        elastic = initial_elastic
        plastic = initial_plastic
        for i in range(quad_k.size):
            e, p, total = spring_energy_increment(quad_k[i], quad_state[i,QCSTRESS], quad_state[i,QTSTRESS],
                                                  quad_state[i,QCSTRAIN], quad_state[i,QTSTRAIN])
            elastic += e
            plastic += p
        for record in range(starts.size):
            interface_elastic = interface_plastic = 0.0
            for i in range(starts[record], stops[record]):
                e, p, total = spring_energy_increment(transverse_k[i], committed[i,6], trial[i,6], committed[i,7], trial[i,7])
                interface_elastic += e
                interface_plastic += p
            for index in (slid_index[record], oop0_index[record], oop1_index[record]):
                if index >= 0:
                    e, p, total = spring_energy_increment(coulomb_params[index,0], coulomb_state[index,CCSTRESS],
                                                          coulomb_state[index,CTSTRESS], coulomb_state[index,CCSTRAIN],
                                                          coulomb_state[index,CTSTRAIN])
                    interface_elastic += e
                    interface_plastic += p
            elastic += interface_elastic
            plastic += interface_plastic
        return elastic, plastic

    @njit(cache=True, nogil=True)
    def _update_domain_batch(
        x,
        aff_offsets, aff_gdls, aff_coefficients, local_du,
        local_u, lengths, constrained, d0s, d1s, num, num2, delta_flex,
        pending_values, record_index, di, dj, ecc, inv_length, targets,
        params, committed, trial, enabled, simple_hysteretic,
        starts, stops, local_forces,
        normal_increments, committed_forces, max_displacements,
        dist_for, slid_index, oop0_index, oop1_index, coulomb_targets,
        coulomb_dns, coulomb_params, coulomb_state, coulomb_enabled,
        dist, local_full_forces,
        quad_aff_offsets, quad_aff_gdls, quad_aff_coefficients, quad_local_du,
        quad_local_u, quad_edge_offsets, quad_edge_records, quad_edge_areas,
        quad_d_alfa, quad_volumes, step, quad_sigma_initial, quad_strains, quad_dns,
        quad_params, quad_state, quad_forces, quad_force_offsets,
        quad_force_gdls, quad_force_coefficients, global_resisting_force,
        max_u_cache,
    ):
        # One compiled boundary per Newton correction. Calling the individual
        # kernels from Numba avoids four Python↔native transitions and keeps
        # their shared dense arrays hot in cache.
        _map_global_to_local(
            x, aff_offsets, aff_gdls, aff_coefficients, local_du, local_u,
        )
        _prepare_interface_kinematics(
            local_du, local_u, lengths, constrained, d0s, d1s,
            num, num2, delta_flex, pending_values, False,
        )
        for i in range(targets.size):
            ri = record_index[i]
            targets[i] = trial[i, 7] + (
                (num[ri] * dj[i] + num2[ri] * di[i]) / lengths[ri]
                - delta_flex[ri] * ecc[i]
            )
        if simple_hysteretic:
            _evaluate_simple_linear_batch(
                params, committed, trial, targets, enabled,
            )
        else:
            _evaluate_linear_batch(
                params, committed, trial, targets, enabled,
            )
        _finish_transverse_batch(
            trial, committed, di, dj, ecc, lengths, starts, stops,
            constrained, local_forces, normal_increments,
            committed_forces, max_displacements,
        )
        if coulomb_targets.size:
            _advance_interface_coulomb_targets(
                pending_values, dist_for, normal_increments,
                slid_index, oop0_index, oop1_index,
                coulomb_targets, coulomb_dns,
            )
            _evaluate_initial_coulomb_batch(
                coulomb_params, coulomb_state, coulomb_targets,
                coulomb_dns, coulomb_enabled,
            )
        _assemble_full_interface_forces(
            local_forces, coulomb_state, slid_index, oop0_index, oop1_index,
            dist, local_full_forces, max_displacements, coulomb_targets,
        )

        if quad_local_du.shape[0]:
            _map_global_to_local(
                x, quad_aff_offsets, quad_aff_gdls,
                quad_aff_coefficients, quad_local_du, quad_local_u,
            )
            _prepare_quad_kinematics(
                quad_local_du, quad_local_u, quad_edge_offsets,
                quad_edge_records, quad_edge_areas, normal_increments,
                committed_forces, quad_d_alfa, step, quad_sigma_initial,
                quad_strains, quad_dns, quad_params, False,
            )
            _evaluate_quad_takeda_batch(
                quad_params, quad_state, quad_strains, quad_dns,
                quad_volumes, quad_sigma_initial,
            )
        _refresh_global_resisting_force(
            quad_d_alfa, quad_state, quad_forces, quad_force_offsets,
            quad_force_gdls, quad_force_coefficients, local_full_forces,
            aff_offsets, aff_gdls, aff_coefficients, global_resisting_force,
        )
        _refresh_max_u_cache(quad_local_u, max_displacements, max_u_cache)

else:
    _managed_elastic_energy = None
    _update_domain_batch = None


if len(_PARAM_NAMES) != TENSILE_CURVE_TYPE_PARAM:
    raise RuntimeError(
        "Transverse hysteretic parameter layout changed without updating "
        "TENSILE_CURVE_TYPE_PARAM"
    )


def recommended_numba_threads(
    interface_count: int,
    spring_count: int,
    available_threads: int,
    *,
    environ: dict[str, str] | os._Environ[str] | None = None,
) -> int:
    """Choose a useful worker count for the compiled nonlinear kernels.

    Each domain update enters several independent Numba parallel regions.  A
    machine-wide default (20 workers in the benchmark environment) is much
    slower for ordinary wall/bridge models than a small worker team because
    synchronization dominates the few hundred interface records.  Scale the
    team conservatively with model size while retaining explicit user control.
    """
    available = max(1, int(available_threads))
    environment = os.environ if environ is None else environ

    override = str(environment.get("HISTRA_NUMBA_THREADS", "")).strip().lower()
    if override and override != "auto":
        try:
            return max(1, min(int(override), available))
        except ValueError:
            pass

    # NUMBA_NUM_THREADS is Numba's standard explicit process-level setting.
    # Respect it instead of silently applying HiStrA's automatic policy.
    if str(environment.get("NUMBA_NUM_THREADS", "")).strip():
        return available

    # Most generated interfaces contain roughly 80 transverse fibres.  Use
    # both counts so unusual discretizations still select a sensible tier.
    work_records = max(
        max(0, int(interface_count)),
        (max(0, int(spring_count)) + 95) // 96,
    )
    if work_records < 256:
        requested = 1
    elif work_records < 2048:
        requested = 2
    elif work_records < 8192:
        requested = 4
    else:
        requested = 8
    return min(requested, available)


def current_numba_threads() -> int | None:
    """Return the active Numba worker count when acceleration is available."""
    if get_num_threads is None:
        return None
    return int(get_num_threads())


def restore_numba_threads(count: int | None) -> None:
    """Restore a caller's Numba worker setting after a nonlinear solve."""
    if count is not None and set_num_threads is not None:
        set_num_threads(int(count))


def _force_general_hysteretic_batch() -> bool:
    return os.environ.get(
        "HISTRA_FORCE_GENERAL_HYSTERETIC_BATCH", ""
    ).strip().lower() in {"1", "true", "yes", "on"}


def _uses_simple_hysteretic_parameters(spring: Any) -> bool:
    """Return the exact predicate used by the specialized dense kernel."""
    if not isinstance(spring, SpringHysteretic):
        return False  # LinearElastic uses its native incremental update.
    return (
        spring.pinch_xp == 0.0
        and spring.pinch_yp == 0.0
        and spring.pinch_xn == 0.0
        and spring.pinch_yn == 0.0
        and spring.damfc1p == 0.0
        and spring.damfc2p == 0.0
        and spring.damfc1n == 0.0
        and spring.damfc2n == 0.0
        and (spring.betap == 1.0 or spring.betap == 0.0)
        and spring.betan == 0.0
    )


class _VirtualSpringSequence(Sequence):
    """Virtual sequence wrapper providing lazy Spring access over interface slices."""

    __slots__ = ("_records", "_total", "_stops")

    def __init__(self, records: list[_InterfaceSlice], total: int) -> None:
        self._records = records
        self._total = total
        self._stops = np.asarray([r.stop for r in records], dtype=np.int32)

    def __len__(self) -> int:
        return self._total

    def __bool__(self) -> bool:
        return self._total > 0

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self._total))]
        idx = int(index)
        if idx < 0:
            idx += self._total
        if idx < 0 or idx >= self._total:
            raise IndexError(f"Virtual spring index {index} out of range [0, {self._total})")
        rec_idx = int(np.searchsorted(self._stops, idx, side="right"))
        rec = self._records[rec_idx]
        return rec.interface.trasv_1[idx - rec.start]

    def __setitem__(self, index: int, value: Any) -> None:
        idx = int(index)
        if idx < 0:
            idx += self._total
        rec_idx = int(np.searchsorted(self._stops, idx, side="right"))
        rec = self._records[rec_idx]
        rec.interface.trasv_1[idx - rec.start] = value

    def __iter__(self) -> Iterator[Any]:
        for rec in self._records:
            yield from rec.interface.trasv_1


class _VirtualManagedSequence(Sequence):
    """Virtual sequence combining virtual transverse springs, Coulomb, and Quads."""

    __slots__ = ("_springs", "_coulomb", "_quad_records")

    def __init__(
        self,
        springs: Any,
        coulomb_springs: list[Any],
        quad_records: list[Any],
    ) -> None:
        self._springs = springs
        self._coulomb = coulomb_springs
        self._quad_records = quad_records

    def __len__(self) -> int:
        return len(self._springs) + len(self._coulomb) + len(self._quad_records)

    def __bool__(self) -> bool:
        return len(self) > 0

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        idx = int(index)
        n_sp = len(self._springs)
        n_co = len(self._coulomb)
        total = n_sp + n_co + len(self._quad_records)
        if idx < 0:
            idx += total
        if idx < 0 or idx >= total:
            raise IndexError(f"Managed spring index out of range: {index}")
        if idx < n_sp:
            return self._springs[idx]
        elif idx < n_sp + n_co:
            return self._coulomb[idx - n_sp]
        else:
            return self._quad_records[idx - n_sp - n_co].spring

    def __setitem__(self, index: int, value: Any) -> None:
        idx = int(index)
        n_sp = len(self._springs)
        n_co = len(self._coulomb)
        total = n_sp + n_co + len(self._quad_records)
        if idx < 0:
            idx += total
        if idx < n_sp:
            self._springs[idx] = value
        elif idx < n_sp + n_co:
            self._coulomb[idx - n_sp] = value
        else:
            self._quad_records[idx - n_sp - n_co].spring = value

    def extend(self, items: Any) -> None:
        pass

    def __iter__(self) -> Iterator[Any]:
        yield from self._springs
        yield from self._coulomb
        for qr in self._quad_records:
            if qr.spring is not None:
                yield qr.spring


class _TransverseParameterView:
    """Logical 34-column view over transverse hysteretic parameters.

    ``HystereticBatchRuntime.params`` historically exposed the complete dense
    parameter layout.  The compact simple-law runtime stores only the 21 values
    consumed by the specialized Numba kernel, but diagnostics and regression
    tooling still rely on the legacy column numbers (notably columns 32/33 for
    the tensile/compressive-envelope discriminators).  This view preserves those read/write
    semantics without allocating a second full matrix during normal solves.

    Accessing a broad slice or coercing the view to an ndarray materializes only
    the requested logical values.  Writing through the view promotes the runtime
    to the full 34-column storage first; this is intentionally rare and preserves
    the historical mutability of ``params`` without compromising the compact
    production path.
    """

    def __init__(self, runtime: "HystereticBatchRuntime") -> None:
        self._runtime = runtime

    @property
    def shape(self) -> tuple[int, int]:
        return (self._runtime._params.shape[0], TRANSVERSE_PARAM_SIZE)

    @property
    def ndim(self) -> int:
        return 2

    @property
    def dtype(self) -> np.dtype:
        return np.dtype(np.float64)

    @property
    def size(self) -> int:
        rows, columns = self.shape
        return rows * columns

    def __len__(self) -> int:
        return self.shape[0]

    @staticmethod
    def _normalise_column(column: int) -> int:
        if column < 0:
            column += TRANSVERSE_PARAM_SIZE
        if not 0 <= column < TRANSVERSE_PARAM_SIZE:
            raise IndexError(
                f"index {column} is out of bounds for axis 1 with size "
                f"{TRANSVERSE_PARAM_SIZE}"
            )
        return column

    def _selected_energy_a(self, rows: Any) -> Any:
        indices = np.arange(len(self), dtype=np.intp)[rows]
        if np.ndim(indices) == 0:
            return float(self._runtime.springs[int(indices)].energy_a)
        flat = np.asarray(indices, dtype=np.intp).ravel()
        values = np.fromiter(
            (float(self._runtime.springs[int(index)].energy_a) for index in flat),
            dtype=np.float64,
            count=flat.size,
        )
        return values.reshape(np.asarray(indices).shape)

    def _materialize_rows(self, rows: Any) -> np.ndarray:
        runtime = self._runtime
        if not runtime._compact_simple_params:
            return np.asarray(runtime._params[rows], dtype=np.float64).copy()

        compact = runtime._params[rows]
        output_shape = compact.shape[:-1] + (TRANSVERSE_PARAM_SIZE,)
        result = np.empty(output_shape, dtype=np.float64)
        result[..., :8] = 0.0
        result[..., 8] = 1.0
        result[..., 9] = 0.0
        result[..., 10:30] = compact[..., :len(SIMPLE_PARAM_NAMES)]
        result[..., 30] = self._selected_energy_a(rows)
        result[..., 31] = runtime._transverse_k[rows]
        if runtime._compact_linear_params:
            result[..., TENSILE_CURVE_TYPE_PARAM] = TENSILE_LINEAR
        else:
            result[..., TENSILE_CURVE_TYPE_PARAM] = (
                compact[..., SIMPLE_TENSILE_CURVE_TYPE_PARAM]
            )
        result[..., COMPRESSIVE_CURVE_TYPE_PARAM] = 0.0
        return result

    def __getitem__(self, key: Any) -> Any:
        runtime = self._runtime
        if not runtime._compact_simple_params:
            return runtime._params[key]

        if isinstance(key, tuple) and len(key) == 2:
            rows, columns = key
            if isinstance(columns, (int, np.integer)):
                column = self._normalise_column(int(columns))
                if column < 8 or column == 9:
                    selected = runtime._transverse_k[rows]
                    if np.ndim(selected) == 0:
                        return 0.0
                    return np.zeros_like(selected, dtype=np.float64)
                if column == 8:
                    selected = runtime._transverse_k[rows]
                    if np.ndim(selected) == 0:
                        return 1.0
                    return np.ones_like(selected, dtype=np.float64)
                if 10 <= column < 30:
                    return runtime._params[rows, column - 10]
                if column == 30:
                    return self._selected_energy_a(rows)
                if column == 31:
                    return runtime._transverse_k[rows]
                if column == COMPRESSIVE_CURVE_TYPE_PARAM:
                    selected = runtime._transverse_k[rows]
                    if np.ndim(selected) == 0:
                        return 0.0
                    return np.zeros_like(selected, dtype=np.float64)
                if column != TENSILE_CURVE_TYPE_PARAM:
                    raise IndexError(f"unsupported compact parameter column {column}")
                if runtime._compact_linear_params:
                    selected = runtime._transverse_k[rows]
                    if np.ndim(selected) == 0:
                        return float(TENSILE_LINEAR)
                    return np.full_like(
                        selected, TENSILE_LINEAR, dtype=np.float64
                    )
                return runtime._params[rows, SIMPLE_TENSILE_CURVE_TYPE_PARAM]
            return self._materialize_rows(rows)[..., columns]

        return self._materialize_rows(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        runtime = self._runtime
        if runtime._compact_simple_params:
            runtime._promote_transverse_parameter_storage()
        runtime._params[key] = value
        # Column 31 historically represented ``k`` in the full parameter array;
        # keep the dedicated stiffness cache coherent after any compatibility
        # write.
        runtime._transverse_k[:] = runtime._params[:, 31]
        runtime._refresh_simple_hysteretic_flag()

    def copy(self, order: str = "C") -> np.ndarray:
        return np.array(self._materialize_rows(slice(None)), copy=True, order=order)

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> np.ndarray:
        array = self._materialize_rows(slice(None))
        if dtype is not None:
            array = array.astype(dtype, copy=False)
        if copy is True:
            array = array.copy()
        return array

    def __repr__(self) -> str:
        return repr(self._materialize_rows(slice(None)))


class HystereticBatchRuntime:
    """Dense committed/trial state for compatible transverse springs."""

    def __init__(self, model: Any) -> None:
        if _evaluate_linear_batch is None:
            raise RuntimeError("Numba is unavailable")
        self.model = model
        self.numba_threads: int | None = None
        self.records: list[_InterfaceSlice] = []
        self.interface_rejection_reasons: Counter[str] = Counter()
        springs: list[Any] = []
        total_springs = 0
        all_simple_params = True
        all_non_parabolic = True
        all_non_exponential = True
        has_batch_backed = False
        for interface in model.collections.interfaces.values():
            intf_trasv = interface.trasv_1
            if not intf_trasv:
                self.interface_rejection_reasons["no_transverse_springs"] += 1
                continue
            if getattr(intf_trasv, "is_batch_backed", False):
                has_batch_backed = True
                rejection_reason = intf_trasv.transverse_rejection_reason()
                if rejection_reason:
                    self.interface_rejection_reasons[rejection_reason] += 1
                    continue
                start = total_springs
                group_len = len(intf_trasv)
                stop = start + group_len
                total_springs = stop
                self.records.append(_InterfaceSlice(interface, start, stop))
                interface._perf_hysteretic_batch = self
                interface._perf_hysteretic_slice = (start, stop)
                intf_trasv._histra_batch_managed = True
                intf_trasv._batch_slice = (start, stop)
                if intf_trasv.betap != 0.0 or intf_trasv.betan != 0.0:
                    all_simple_params = False
                if intf_trasv.compressive_curve_type == "Parabolic":
                    all_non_parabolic = False
                if intf_trasv.tensile_curve_type == "Exponential":
                    all_non_exponential = False
                if getattr(intf_trasv, "_cache", None):
                    for sp in intf_trasv._cache.values():
                        if getattr(sp, "compressive_curve_type", "") == "Parabolic":
                            all_non_parabolic = False
                        if getattr(sp, "tensile_curve_type", "") == "Exponential":
                            all_non_exponential = False
            else:
                group = list(intf_trasv)
                rejection_reason = ""
                for spring in group:
                    rejection_reason = self._transverse_rejection_reason(spring)
                    if rejection_reason:
                        break
                if rejection_reason:
                    self.interface_rejection_reasons[rejection_reason] += 1
                    continue
                start = total_springs
                group_len = len(group)
                stop = start + group_len
                total_springs = stop
                springs.extend(group)
                self.records.append(_InterfaceSlice(interface, start, stop))
                interface._perf_hysteretic_batch = self
                interface._perf_hysteretic_slice = (start, stop)
                for spring in group:
                    spring._histra_batch_managed = True

                if all_simple_params:
                    for spring in group:
                        if not _uses_simple_hysteretic_parameters(spring):
                            all_simple_params = False
                            break
                if all_non_parabolic:
                    for spring in group:
                        if isinstance(spring, SpringHysteretic) and spring.compressive_curve_type == "Parabolic":
                            all_non_parabolic = False
                            break
                if all_non_exponential:
                    for spring in group:
                        if getattr(spring, "tensile_curve_type", "") == "Exponential":
                            all_non_exponential = False
                            break

        self.is_batch_backed = bool(has_batch_backed)
        if has_batch_backed:
            self.springs = _VirtualSpringSequence(self.records, total_springs)
        else:
            self.springs = springs
        self.interface_ids = frozenset(id(record.interface) for record in self.records)
        n = total_springs
        self._compact_simple_params = bool(
            n
            and not _force_general_hysteretic_batch()
            and all_simple_params
            and all_non_parabolic
        )
        self._compact_linear_params = bool(
            self._compact_simple_params
            and all_non_exponential
        )
        parameter_count = (
            LINEAR_SIMPLE_TRANSVERSE_PARAM_SIZE
            if self._compact_linear_params
            else SIMPLE_TRANSVERSE_PARAM_SIZE
            if self._compact_simple_params else TRANSVERSE_PARAM_SIZE
        )
        self._params = np.empty((n, parameter_count), dtype=np.float64)
        # Keep the historical full logical parameter interface while the
        # solver consumes the compact physical storage directly.
        self.params = _TransverseParameterView(self)
        self.committed = np.empty((n, 9), dtype=np.float64)
        self.trial = np.empty((n, 10), dtype=np.float64)
        self.targets = np.empty(n, dtype=np.float64)
        self.enabled = np.empty(n, dtype=np.bool_)
        self._transverse_k = np.empty(n, dtype=np.float64)
        self._read_transverse_objects_bulk(springs)
        self._refresh_simple_hysteretic_flag()
        self._record_index = np.empty(n, dtype=np.int32)
        self._di = np.empty(n, dtype=np.float64)
        self._dj = np.empty(n, dtype=np.float64)
        self._ecc = np.empty(n, dtype=np.float64)
        self._inv_length = np.empty(n, dtype=np.float64)
        for record_index, record in enumerate(self.records):
            interface = record.interface
            interface._ensure_performance_cache()
            assert interface._perf_di is not None
            assert interface._perf_dj is not None
            assert interface._perf_ecc is not None
            sl = slice(record.start, record.stop)
            self._record_index[sl] = record_index
            self._di[sl] = interface._perf_di
            self._dj[sl] = interface._perf_dj
            self._ecc[sl] = interface._perf_ecc
            self._inv_length[sl] = 1.0 / interface.length
        self._num = np.empty(len(self.records), dtype=np.float64)
        self._num2 = np.empty(len(self.records), dtype=np.float64)
        self._delta_flex = np.empty(len(self.records), dtype=np.float64)
        self._starts = np.asarray([record.start for record in self.records], dtype=np.int32)
        self._stops = np.asarray([record.stop for record in self.records], dtype=np.int32)
        self._constrained = np.asarray(
            [record.interface.interfaccia_vincolata_computed() for record in self.records],
            dtype=np.bool_,
        )
        self._lengths = np.asarray(
            [record.interface.length for record in self.records], dtype=np.float64
        )
        self._d0s = np.asarray(
            [
                record.interface.dim_aff[0] if record.interface.dim_aff else 6
                for record in self.records
            ],
            dtype=np.int32,
        )
        self._d1s = np.asarray(
            [
                record.interface.dim_aff[1]
                if len(record.interface.dim_aff) > 1 else 2
                for record in self.records
            ],
            dtype=np.int32,
        )
        self._pending_values = np.zeros((len(self.records), 3), dtype=np.float64)
        self._local_forces = np.zeros((len(self.records), 6), dtype=np.float64)
        self._normal_increments = np.zeros(len(self.records), dtype=np.float64)
        self._committed_forces = np.zeros(len(self.records), dtype=np.float64)
        self._max_displacements = np.zeros(len(self.records), dtype=np.float64)
        self._record_by_id = {
            id(record.interface): index for index, record in enumerate(self.records)
        }

        # Batch the three interface Coulomb springs (one in-plane and two
        # out-of-plane) when they use the simple C# Initial law.  Unsupported
        # variants remain on the scalar object path.
        from histra.springs.coulomb03 import SpringCoulomb03
        self.interface_coulomb_rejection_reasons: Counter[str] = Counter()
        coulomb_springs: list[SpringCoulomb03] = []
        # C# can hold the same SpringCoulomb03 object in both out-of-plane
        # positions of a restraint/custom-material interface.  Preserve that
        # identity in dense state so both kinematic increments accumulate into
        # one row just as the two C# list accesses update one object.
        coulomb_index_by_id: dict[int, int] = {}
        self._slid_index = np.full(len(self.records), -1, dtype=np.int32)
        self._oop0_index = np.full(len(self.records), -1, dtype=np.int32)
        self._oop1_index = np.full(len(self.records), -1, dtype=np.int32)
        self._dist = np.zeros((len(self.records), 2), dtype=np.float64)
        self._dist_for = np.zeros((len(self.records), 2), dtype=np.float64)
        for record_index, record in enumerate(self.records):
            interface = record.interface
            interface._ensure_performance_cache()
            if interface._perf_dist is not None:
                self._dist[record_index, :] = interface._perf_dist
            if interface._perf_dist_for is not None:
                self._dist_for[record_index, :] = interface._perf_dist_for

            candidates: list[tuple[str, Any]] = []
            if interface.slid:
                candidates.append(("slid", interface.slid[0]))
            if len(interface.slid_out_plan) >= 2:
                candidates.extend(
                    (("oop0", interface.slid_out_plan[0]),
                     ("oop1", interface.slid_out_plan[1]))
                )
            for kind, spring in candidates:
                rejection_reason = self._coulomb_rejection_reason(spring)
                if rejection_reason:
                    self.interface_coulomb_rejection_reasons[
                        f"{kind}:{rejection_reason}"
                    ] += 1
                    continue
                spring_id = id(spring)
                index = coulomb_index_by_id.get(spring_id, -1)
                if index < 0:
                    index = len(coulomb_springs)
                    coulomb_index_by_id[spring_id] = index
                    coulomb_springs.append(spring)
                    spring._histra_batch_managed = True
                if kind == "slid":
                    self._slid_index[record_index] = index
                elif kind == "oop0":
                    self._oop0_index[record_index] = index
                else:
                    self._oop1_index[record_index] = index

        self.coulomb_springs = coulomb_springs
        nc = len(coulomb_springs)
        self.coulomb_params = np.empty((nc, 7), dtype=np.float64)
        self.coulomb_state = np.empty((nc, COULOMB_STATE_SIZE), dtype=np.float64)
        self.coulomb_targets = np.empty(nc, dtype=np.float64)
        self.coulomb_dns = np.zeros(nc, dtype=np.float64)
        self.coulomb_enabled = np.empty(nc, dtype=np.bool_)
        for i, spring in enumerate(coulomb_springs):
            self._import_interface_sliding_object(i, spring)
        self._refresh_elastic_sliding_indices()
        self._refresh_unmanaged_sliding_record_indices()
        self.quad_records: list[Any] = []
        if has_batch_backed:
            self.managed_springs = _VirtualManagedSequence(self.springs, self.coulomb_springs, self.quad_records)
        else:
            self.managed_springs = [*self.springs, *self.coulomb_springs]
        offsets = [0]
        gdls: list[int] = []
        coefficients: list[float] = []
        for record in self.records:
            interface = record.interface
            assert interface._perf_aff_pairs is not None
            for local_dof in range(12):
                pairs = (
                    interface._perf_aff_pairs[local_dof]
                    if local_dof < len(interface._perf_aff_pairs)
                    else ()
                )
                for gdl, coefficient in pairs:
                    gdls.append(int(gdl))
                    coefficients.append(float(coefficient))
                offsets.append(len(gdls))
        self._aff_offsets = np.asarray(offsets, dtype=np.int32)
        self._aff_gdls = np.asarray(gdls, dtype=np.int32)
        self._aff_coefficients = np.asarray(coefficients, dtype=np.float64)
        self._local_du = np.zeros((len(self.records), 12), dtype=np.float64)
        self._local_u = np.asarray(
            [record.interface.status.u[:12] for record in self.records],
            dtype=np.float64,
        )
        self._local_full_forces = np.zeros((len(self.records), 12), dtype=np.float64)

        # Dense Quad kinematics / ComputeDN preparation. Compatible diagonal
        # SpringCoulomb03 laws are evaluated in the fused Numba kernel.  Every
        # rejected Quad is classified so production profiles can explain the
        # residual scalar path instead of only reporting its aggregate cost.
        self.quad_rejection_reasons: Counter[str] = Counter()
        quad_offsets = [0]
        quad_gdls: list[int] = []
        quad_coefficients: list[float] = []
        edge_offsets = [0]
        edge_records: list[int] = []
        edge_areas: list[list[float]] = []
        quad_d_alfa: list[float] = []
        quad_volumes: list[float] = []
        quad_materials: list[Any] = []
        quad_sublaws: list[int] = []
        quad_fracture_modes: list[int] = []
        quad_fracture_energies: list[float] = []
        disable_quad_batch = os.environ.get(
            "HISTRA_DISABLE_COMPILED_QUADS", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        for quad in model.collections.quads.values():
            if disable_quad_batch:
                self.quad_rejection_reasons["disabled_by_environment"] += 1
                continue
            spring = getattr(quad, "spring", None)
            is_elastic = isinstance(spring, SpringElastic)
            is_hysteretic = isinstance(spring, SpringHysteretic)
            needs_normal_force = isinstance(spring, SpringCoulomb03)
            if not (is_elastic or is_hysteretic or needs_normal_force):
                self.quad_rejection_reasons["unsupported_spring_type"] += 1
                continue
            htype = str(getattr(spring, "hysteretic_type", "Takeda")).casefold()
            if needs_normal_force and htype not in ("takeda", "initial", "0"):
                self.quad_rejection_reasons["unsupported_hysteretic_type"] += 1
                continue
            if is_elastic:
                sub_law = QUAD_SUBLAW_ELASTIC
            elif is_hysteretic:
                reason = self._transverse_rejection_reason(spring)
                if reason:
                    self.quad_rejection_reasons[reason] += 1
                    continue
                sub_law = QUAD_SUBLAW_HYSTERETIC
            else:
                sub_law_name = str(spring.sub_law).strip().lower()
                if sub_law_name == "coulomb":
                    sub_law = QUAD_SUBLAW_COULOMB
                elif sub_law_name == "cacovic":
                    if float(spring.cohesion) == 0.0 or float(spring.bcacovic) == 0.0:
                        self.quad_rejection_reasons["invalid_cacovic_parameters"] += 1
                        continue
                    sub_law = QUAD_SUBLAW_CACOVIC
                else:
                    self.quad_rejection_reasons["unsupported_shear_sublaw"] += 1
                    continue
            if needs_normal_force and spring.check_contact_area:
                self.quad_rejection_reasons["contact_area_check"] += 1
                continue
            if _evaluate_quad_takeda_batch is None:
                self.quad_rejection_reasons["numba_kernel_unavailable"] += 1
                continue

            material = model.collections.materials.get(quad.material_key)
            fracture_mode = (
                masonry_shear_law_code(material) if needs_normal_force
                else QUAD_FRACTURE_NONE
            )
            if fracture_mode not in (
                ELASTO_PLASTIC_FRACTURE_ENERGY_FIXED,
                ELASTO_PLASTIC_ENERGY_SIGMA_INTERPOLATION,
            ):
                fracture_mode = QUAD_FRACTURE_NONE

            quad._ensure_dn_cache(model.collections)
            assert quad._perf_dn_edges is not None
            assert quad._perf_dn_areas is not None
            local_edge_records: list[int] = []
            local_edge_counts: list[int] = [0, 0, 0, 0]
            if needs_normal_force:
                compatible = True
                rejection_reason = ""
                local_edge_counts.clear()
                for refs in quad._perf_dn_edges:
                    count = 0
                    for interface, custom_springs in refs:
                        if custom_springs:
                            compatible = False
                            rejection_reason = "custom_edge_springs"
                            break
                        if "compute_dn" in interface.__dict__:
                            compatible = False
                            rejection_reason = "custom_interface_compute_dn"
                            break
                        record_index = self._record_by_id.get(id(interface))
                        if record_index is None:
                            compatible = False
                            rejection_reason = "edge_interface_not_batched"
                            break
                        local_edge_records.append(record_index)
                        count += 1
                    if not compatible:
                        break
                    local_edge_counts.append(count)
                if not compatible:
                    self.quad_rejection_reasons[rejection_reason] += 1
                    continue

            self.quad_records.append(quad)
            if quad._perf_aff_pairs is None:
                quad._perf_aff_pairs = tuple(
                    tuple((entry.gdl - 1, float(entry.alfa)) for entry in entries)
                    for entries in quad.aff[:7]
                )
            for local_dof in range(7):
                pairs = quad._perf_aff_pairs[local_dof] if quad._perf_aff_pairs else ()
                for gdl, coefficient in pairs:
                    quad_gdls.append(int(gdl))
                    quad_coefficients.append(float(coefficient))
                quad_offsets.append(len(quad_gdls))
            cursor = 0
            for count in local_edge_counts:
                edge_records.extend(local_edge_records[cursor:cursor + count])
                cursor += count
                edge_offsets.append(len(edge_records))
            edge_areas.append([float(value) for value in quad._perf_dn_areas])
            quad_d_alfa.append(float(quad.d_alfa_2d_diag()))
            quad_volumes.append(float(quad.compute_volume()))
            quad_materials.append(material)
            quad_sublaws.append(sub_law)
            quad_fracture_modes.append(fracture_mode)
            quad_fracture_energies.append(fracture_energy_shear(material))

        self.quad_ids = frozenset(id(quad) for quad in self.quad_records)
        self.unmanaged_interfaces = tuple(
            interface for interface in model.collections.interfaces.values()
            if id(interface) not in self.interface_ids
        )
        self.unmanaged_quads = tuple(
            quad for quad in model.collections.quads.values()
            if id(quad) not in self.quad_ids
        )
        self._quad_aff_offsets = np.asarray(quad_offsets, dtype=np.int32)
        self._quad_aff_gdls = np.asarray(quad_gdls, dtype=np.int32)
        self._quad_aff_coefficients = np.asarray(quad_coefficients, dtype=np.float64)
        self._quad_edge_offsets = np.asarray(edge_offsets, dtype=np.int32)
        self._quad_edge_records = np.asarray(edge_records, dtype=np.int32)
        self._quad_edge_areas = np.asarray(
            edge_areas, dtype=np.float64
        ).reshape((len(self.quad_records), 4))
        self._quad_d_alfa = np.asarray(quad_d_alfa, dtype=np.float64)
        self._quad_volumes = np.asarray(quad_volumes, dtype=np.float64)
        self._quad_materials = quad_materials
        self._quad_local_du = np.zeros((len(self.quad_records), 7), dtype=np.float64)
        # ``np.asarray([])`` has shape ``(0,)``.  Keep the Quad displacement
        # storage rank-stable when the diagnostic interface-only runtime
        # deliberately contains no managed Quads; Numba kernels consume this
        # array as a two-dimensional ``(n_quads, 7)`` matrix.
        self._quad_local_u = np.asarray(
            [quad.status.u[:7] for quad in self.quad_records], dtype=np.float64
        ).reshape((len(self.quad_records), 7))
        self._quad_sigma_initial = np.asarray(
            [float(quad.sigma_initial) for quad in self.quad_records], dtype=np.float64
        )
        self._quad_strains = np.zeros(len(self.quad_records), dtype=np.float64)
        self._quad_dns = np.zeros(len(self.quad_records), dtype=np.float64)
        self.quad_params = np.zeros(
            (len(self.quad_records), QUAD_PARAM_SIZE), dtype=np.float64
        )
        self.quad_state = np.zeros(
            (len(self.quad_records), QUAD_STATE_SIZE), dtype=np.float64
        )
        self._quad_k = np.empty(len(self.quad_records), dtype=np.float64)
        for index, quad in enumerate(self.quad_records):
            spring = quad.spring
            spring._histra_batch_managed = True
            spring._histra_quad_batch = self
            spring._histra_quad_batch_index = index
            if isinstance(spring, SpringElastic):
                self.quad_params[index, QPENABLED] = float(bool(spring.is_on))
                self.quad_params[index, QPK] = float(spring.k)
                self.quad_params[index, QPSUBLAW] = QUAD_SUBLAW_ELASTIC
                self.quad_params[index, QPHYSTERETIC_TYPE] = QUAD_HYSTERETIC_TAKEDA
                self.quad_params[index, QPH] = 0.0
                self._read_elastic_quad_object(index, spring)
            elif isinstance(spring, SpringHysteretic):
                self.quad_params[index, QPENABLED] = float(bool(spring.is_on))
                self.quad_params[index, QPK] = float(spring.k)
                self.quad_params[index, QPSUBLAW] = QUAD_SUBLAW_HYSTERETIC
                self.quad_params[index, QHPARAMS:QHPARAMS+32] = _extract_spring_params(spring, False)
                self.quad_params[index, QHPARAMS+32] = _extract_spring_curve_type(spring)
                self.quad_params[index, QHPARAMS+33] = _extract_spring_compressive_curve_type(spring)
                row = self.quad_state[index]
                row[QHCOMMITTED:QHTRIAL] = _extract_spring_committed(spring)
                row[QHTRIAL:] = _extract_spring_trial(spring)
                row[QFY0:QFY1+1] = spring.fy
                row[QUR0:QUR1+1] = spring.ur
                row[QKTANG_COMMITTED] = float(spring.k_tang_committed)
                _mirror_hysteretic_quad(row)
            else:
                htype = str(getattr(spring, "hysteretic_type", "Takeda")).casefold()
                quad_htype = (
                    QUAD_HYSTERETIC_INITIAL
                    if htype in ("initial", "0")
                    else QUAD_HYSTERETIC_TAKEDA
                )
                self.quad_params[index, :17] = (
                    float(spring.cohesion), float(spring.mu),
                    float(spring.e1p), float(spring.e2p), float(spring.e3p),
                    float(spring.e1n), float(spring.e2n), float(spring.e3n),
                    float(spring.eup), float(spring.eun),
                    float(spring.plastic_strain_ratio), float(bool(spring.is_on)),
                    float(spring.k), float(quad_sublaws[index]),
                    float(spring.bcacovic), float(quad_fracture_modes[index]),
                    float(quad_fracture_energies[index]),
                )
                self.quad_params[index, QPHYSTERETIC_TYPE] = quad_htype
                self.quad_params[index, QPH] = float(getattr(spring, "h", 0.0))
                self._read_quad_object(index, spring)
            self._quad_k[index] = float(spring.k)
        self.managed_springs.extend(quad.spring for quad in self.quad_records)
        self._quad_forces = np.zeros((len(self.quad_records), 1), dtype=np.float64)
        quad_force_offsets = [0]
        quad_force_gdls: list[int] = []
        quad_force_coefficients: list[float] = []
        for quad in self.quad_records:
            pairs = quad._perf_aff_pairs[6] if quad._perf_aff_pairs else ()
            for gdl, coefficient in pairs:
                quad_force_gdls.append(int(gdl))
                quad_force_coefficients.append(float(coefficient))
            quad_force_offsets.append(len(quad_force_gdls))
        self._quad_force_offsets = np.asarray(quad_force_offsets, dtype=np.int32)
        self._quad_force_gdls = np.asarray(quad_force_gdls, dtype=np.int32)
        self._quad_force_coefficients = np.asarray(
            quad_force_coefficients, dtype=np.float64
        )
        self._global_resisting_force = np.zeros(int(model.gdl), dtype=np.float64)
        (
            self._global_force_offsets,
            self._global_force_indices,
            self._global_force_coefficients,
            self._interface_force_size,
        ) = _build_force_by_dof_topology(
            int(model.gdl),
            self._aff_offsets,
            self._aff_gdls,
            self._aff_coefficients,
            self._quad_force_offsets,
            self._quad_force_gdls,
            self._quad_force_coefficients,
        )
        # [overall value, record, kind, quad-only value, quad-only record].
        # C# convergence limits exclude interface spring displacements.
        self._max_u_cache = np.zeros(5, dtype=np.float64)
        self._interface_resultants = np.zeros((len(self.records), 3), dtype=np.float32)
        self._interface_resultants_valid = False
        self._pdelta_saved_resultants = np.asarray(
            [record.interface.status.forces for record in self.records], dtype=np.float32,
        ).reshape((-1, 3))
        self._e1 = (
            np.asarray([record.interface.reference_e1 for record in self.records], dtype=np.float32)
            if self.records else np.empty((0, 3), dtype=np.float32)
        )
        self._e2 = (
            np.asarray([record.interface.reference_e2 for record in self.records], dtype=np.float32)
            if self.records else np.empty((0, 3), dtype=np.float32)
        )
        self._e3 = (
            np.asarray([record.interface.reference_e3 for record in self.records], dtype=np.float32)
            if self.records else np.empty((0, 3), dtype=np.float32)
        )
        self._refresh_transverse_cache()
        self._refresh_full_force_cache()
        self._refresh_global_resisting_force_cache()
        self._refresh_max_u_cache()
        self._objects_trial_synced = True
        self._pdelta_plan: PDeltaPlan | None = None
        self._pdelta_line_load_plans: dict[tuple[int, int], PDeltaLineLoadPlan] = {}
        self.interface_ids = frozenset(id(record.interface) for record in self.records)
        self._initial_state_snapshot = self.snapshot()

    @staticmethod
    def _transverse_rejection_reason(spring: Any) -> str:
        from histra.springs.base import Spring
        if isinstance(spring, Spring) and not isinstance(spring, SpringHysteretic):
            return ""
        if not isinstance(spring, SpringHysteretic):
            return "unsupported_transverse_spring_type"
        if spring.tensile_curve_type not in {
            "LinearHardening", "LinearSoftening", "Exponential", "Elastic"
        }:
            return "unsupported_tensile_curve_type"
        if spring.compressive_curve_type not in {
            "LinearHardening", "LinearSoftening", "Elastic", "Parabolic"
        }:
            return "unsupported_compressive_curve_type"
        return ""

    @staticmethod
    def _coulomb_rejection_reason(spring: Any) -> str:
        from histra.springs.coulomb03 import SpringCoulomb03

        if isinstance(spring, SpringElastic):
            return ""
        if not isinstance(spring, SpringCoulomb03):
            return "unsupported_spring_type"
        if spring.hysteretic_type != "Initial":
            return "unsupported_hysteretic_type"
        if spring.sub_law != "Coulomb":
            return "unsupported_shear_sublaw"
        if spring.check_contact_area:
            return "contact_area_check"
        return ""

    def _refresh_elastic_sliding_indices(self) -> None:
        self._elastic_sliding_indices = np.fromiter(
            (
                index
                for index, spring in enumerate(self.coulomb_springs)
                if isinstance(spring, SpringElastic)
            ),
            dtype=np.int32,
        )

    def _refresh_unmanaged_sliding_record_indices(self) -> None:
        """Cache the rare scalar fallbacks outside the Newton hot loop."""
        self._unmanaged_sliding_record_indices = np.fromiter(
            (
                record_index
                for record_index, record in enumerate(self.records)
                if (
                    record.interface.slid
                    and int(self._slid_index[record_index]) < 0
                )
                or (
                    len(record.interface.slid_out_plan) >= 2
                    and int(self._oop0_index[record_index]) < 0
                    and int(self._oop1_index[record_index]) < 0
                )
            ),
            dtype=np.int32,
        )

    def _import_interface_sliding_object(self, index: int, spring: Any) -> None:
        """Import one supported interface sliding spring into dense storage."""
        if isinstance(spring, SpringElastic):
            self.coulomb_params[index, :] = 0.0
            self.coulomb_params[index, 0] = float(spring.k)
            self._read_coulomb_object(index, spring)
            self.coulomb_targets[index] = float(spring.u)
            # The nonlinear Coulomb kernel must skip elastic rows; their exact
            # state transition runs in _evaluate_elastic_sliding_batch.
            self.coulomb_enabled[index] = False
            return
        self.coulomb_params[index, :] = (
            float(spring.k), float(spring.h), float(spring.cohesion),
            float(spring.mu), float(spring.area), float(spring.e1p),
            float(spring.e2p),
        )
        self._read_coulomb_object(index, spring)
        self.coulomb_targets[index] = float(spring.u)
        self.coulomb_enabled[index] = bool(spring.is_on)

    def _rebuild_interface_coulomb_storage(
        self, *, changed_record_indices: frozenset[int] | None = None
    ) -> None:
        """Rebuild only interface-Coulomb dense rows after topology changes.

        Foundation material replacement can split an aliased fixed-restraint
        out-of-plane spring into two independent soil springs (or the reverse).
        That changes only the tiny interface-Coulomb identity/index topology;
        rebuilding the complete runtime also re-imported ~550k transverse
        hysteretic objects and all Quad metadata.

        Recreate the same Coulomb coverage/order used by ``__init__`` while
        retaining transverse, geometry and Quad dense arrays unchanged.  When
        the caller identifies the records that changed, rows whose spring
        identity occurs only in untouched records are copied from the previous
        synchronized dense storage instead of re-reading dozens of Python
        attributes from every Coulomb object. ``coulomb_dns`` deliberately is
        *not* copied: a topology rebuild historically resets that array to zero.
        """
        old_springs = self.coulomb_springs
        old_params = self.coulomb_params
        old_state = self.coulomb_state
        old_targets = self.coulomb_targets
        old_enabled = self.coulomb_enabled
        old_slid_index = self._slid_index
        old_oop0_index = self._oop0_index
        old_oop1_index = self._oop1_index
        known_changes = changed_record_indices is not None
        changed_records = changed_record_indices or frozenset()

        for spring in old_springs:
            if hasattr(spring, "_histra_batch_managed"):
                spring._histra_batch_managed = False

        rejection_reasons: Counter[str] = Counter()
        springs: list[Any] = []
        index_by_id: dict[int, int] = {}
        # At most three interface Coulomb rows can occur per record. Keep the
        # reuse metadata compact instead of allocating Python int/bool lists.
        max_coulomb_rows = 3 * len(self.records)
        old_row_for_new = np.full(max_coulomb_rows, -1, dtype=np.int32)
        row_touched = np.empty(max_coulomb_rows, dtype=np.bool_)
        slid_index = np.full(len(self.records), -1, dtype=np.int32)
        oop0_index = np.full(len(self.records), -1, dtype=np.int32)
        oop1_index = np.full(len(self.records), -1, dtype=np.int32)

        for record_index, record in enumerate(self.records):
            interface = record.interface
            candidates: list[tuple[str, Any]] = []
            if interface.slid:
                candidates.append(("slid", interface.slid[0]))
            if len(interface.slid_out_plan) >= 2:
                candidates.extend(
                    (
                        ("oop0", interface.slid_out_plan[0]),
                        ("oop1", interface.slid_out_plan[1]),
                    )
                )

            for kind, spring in candidates:
                rejection_reason = self._coulomb_rejection_reason(spring)
                if rejection_reason:
                    rejection_reasons[f"{kind}:{rejection_reason}"] += 1
                    continue

                spring_id = id(spring)
                dense_index = index_by_id.get(spring_id, -1)
                if dense_index < 0:
                    dense_index = len(springs)
                    index_by_id[spring_id] = dense_index
                    springs.append(spring)
                    if kind == "slid":
                        previous_index = int(old_slid_index[record_index])
                    elif kind == "oop0":
                        previous_index = int(old_oop0_index[record_index])
                    else:
                        previous_index = int(old_oop1_index[record_index])
                    if (
                        0 <= previous_index < len(old_springs)
                        and old_springs[previous_index] is spring
                    ):
                        old_row_for_new[dense_index] = previous_index
                    row_touched[dense_index] = (
                        (not known_changes) or record_index in changed_records
                    )
                    spring._histra_batch_managed = True
                elif record_index in changed_records:
                    # An object may be shared by multiple interfaces. If even
                    # one occurrence belongs to a changed record, re-import it
                    # rather than assuming an in-place material mutation did
                    # not alter the shared object.
                    row_touched[dense_index] = True

                if kind == "slid":
                    slid_index[record_index] = dense_index
                elif kind == "oop0":
                    oop0_index[record_index] = dense_index
                else:
                    oop1_index[record_index] = dense_index

        count = len(springs)
        old_row_for_new = old_row_for_new[:count]
        row_touched = row_touched[:count]
        params = np.empty((count, 7), dtype=np.float64)
        state = np.empty((count, COULOMB_STATE_SIZE), dtype=np.float64)
        targets = np.empty(count, dtype=np.float64)
        dns = np.zeros(count, dtype=np.float64)
        enabled = np.empty(count, dtype=np.bool_)

        # Publish storage before importing rows because _read_coulomb_object()
        # writes through self.coulomb_state.
        self.coulomb_springs = springs
        self.coulomb_params = params
        self.coulomb_state = state
        self.coulomb_targets = targets
        self.coulomb_dns = dns
        self.coulomb_enabled = enabled
        self._slid_index = slid_index
        self._oop0_index = oop0_index
        self._oop1_index = oop1_index
        self.interface_coulomb_rejection_reasons = rejection_reasons

        # Unchanged identities retain scan order, so material topology edits
        # normally leave a handful of contiguous old->new index runs. Copy
        # those runs as slices. This avoids the full-sized temporary arrays
        # created by NumPy advanced indexing while still doing each bulk copy
        # in C. The scalar fallback is only the number of topology boundaries,
        # not the number of unchanged Coulomb rows.
        run_new = -1
        run_old = -1
        previous_old = -2

        def copy_run(start_new: int, start_old: int, stop_new: int) -> None:
            if start_new < 0:
                return
            length = stop_new - start_new
            old_stop = start_old + length
            params[start_new:stop_new, :] = old_params[start_old:old_stop, :]
            state[start_new:stop_new, :] = old_state[start_old:old_stop, :]
            targets[start_new:stop_new] = old_targets[start_old:old_stop]
            enabled[start_new:stop_new] = old_enabled[start_old:old_stop]

        for index, (old_index, touched) in enumerate(
            zip(old_row_for_new, row_touched, strict=True)
        ):
            reusable = old_index >= 0 and not touched
            if reusable and run_new >= 0 and old_index == previous_old + 1:
                previous_old = old_index
                continue
            if run_new >= 0:
                copy_run(run_new, run_old, index)
                run_new = -1
            if reusable:
                run_new = index
                run_old = old_index
                previous_old = old_index
        if run_new >= 0:
            copy_run(run_new, run_old, count)

        for index, spring in enumerate(springs):
            if old_row_for_new[index] >= 0 and not row_touched[index]:
                continue
            self._import_interface_sliding_object(index, spring)

        self._refresh_elastic_sliding_indices()
        self._refresh_unmanaged_sliding_record_indices()

        # Preserve the constructor's managed-spring ordering exactly:
        # transverse -> interface Coulomb -> Quad diagonal.
        self.managed_springs = [
            *self.springs,
            *self.coulomb_springs,
            *(quad.spring for quad in self.quad_records),
        ]

    def _read_transverse_objects_bulk(
        self, springs: list[Any], *, chunk_size: int = 16384
    ) -> None:
        """Import all records, including groups with no materialized springs."""
        # ``springs`` contains only scalar objects. A fully numeric topology
        # still owns dense rows that must be initialized before any solve.
        if self.committed.shape[0] == 0:
            return
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")

        fixed_parameter_count = (
            len(SIMPLE_PARAM_NAMES) if self._compact_simple_params else len(_PARAM_NAMES)
        )
        curve_column = (
            SIMPLE_TENSILE_CURVE_TYPE_PARAM
            if self._compact_simple_params
            else TENSILE_CURVE_TYPE_PARAM
        )

        for record in self.records:
            intf = record.interface
            start, stop = record.start, record.stop
            group_count = stop - start
            group = intf.trasv_1
            if getattr(group, "is_batch_backed", False):
                if self._compact_simple_params:
                    param_cols = min(fixed_parameter_count, group._params.shape[1])
                    self._params[start:stop, :param_cols] = group._params[:, :param_cols]
                    if not self._compact_linear_params:
                        if group._tensile_curve_types is not None:
                            self._params[start:stop, curve_column] = [
                                TENSILE_EXPONENTIAL if t == "Exponential" else TENSILE_LINEAR
                                for t in group._tensile_curve_types
                            ]
                        else:
                            self._params[start:stop, curve_column] = (
                                TENSILE_EXPONENTIAL if group.tensile_curve_type == "Exponential" else TENSILE_LINEAR
                            )
                else:
                    p = group._params
                    self._params[start:stop, :8] = 0.0
                    self._params[start:stop, 8] = group.betap
                    self._params[start:stop, 9] = group.betan
                    self._params[start:stop, 10:30] = p
                    self._params[start:stop, 30] = 0.5 * (
                        p[:, 0] * p[:, 1]
                        + (p[:, 2] - p[:, 0]) * (p[:, 3] + p[:, 1])
                        + (p[:, 4] - p[:, 2]) * (p[:, 5] + p[:, 3])
                        + p[:, 7] * p[:, 6]
                        + (p[:, 8] - p[:, 7]) * (p[:, 9] + p[:, 6])
                        + (p[:, 10] - p[:, 8]) * (p[:, 11] + p[:, 9])
                    )
                    self._params[start:stop, 31] = group._k
                    if group._tensile_curve_types is not None:
                        self._params[start:stop, TENSILE_CURVE_TYPE_PARAM] = [
                            TENSILE_EXPONENTIAL if t == "Exponential" else TENSILE_LINEAR
                            for t in group._tensile_curve_types
                        ]
                    else:
                        self._params[start:stop, TENSILE_CURVE_TYPE_PARAM] = (
                            TENSILE_EXPONENTIAL if group.tensile_curve_type == "Exponential" else TENSILE_LINEAR
                        )
                    if group._compressive_curve_types is not None:
                        self._params[start:stop, COMPRESSIVE_CURVE_TYPE_PARAM] = [
                            COMPRESSIVE_PARABOLIC if c == "Parabolic" else COMPRESSIVE_LINEAR
                            for c in group._compressive_curve_types
                        ]
                    else:
                        self._params[start:stop, COMPRESSIVE_CURVE_TYPE_PARAM] = (
                            COMPRESSIVE_PARABOLIC if group.compressive_curve_type == "Parabolic" else COMPRESSIVE_LINEAR
                        )
                self._transverse_k[start:stop] = group._k
                is_dirty = (
                    np.any(group._committed[:, 7] != 0.0)
                    or np.any(group._trial[:, 7] != 0.0)
                    or np.any(group._committed[:, 8] != 0.0)
                )
                if not is_dirty:
                    self.committed[start:stop, :].fill(0.0)
                    self.trial[start:stop, :].fill(0.0)
                    # Native revertToStart uses the envelope E1p tangent;
                    # Fy / (Fy / K) can differ from nominal K in the last bits.
                    self.trial[start:stop, 9] = group._trial[:, 9]
                    self.targets[start:stop].fill(0.0)
                    self.enabled[start:stop].fill(True)
                else:
                    self.committed[start:stop, :] = group._committed
                    self.trial[start:stop, :] = group._trial
                    self.targets[start:stop].fill(0.0)
                    self.enabled[start:stop] = group.is_on
                continue

            if (
                self._compact_simple_params
                and getattr(intf, "_transverse_batch_params", None) is not None
                and intf._transverse_batch_params.shape == (group_count, fixed_parameter_count)
            ):
                self._params[start:stop, :fixed_parameter_count] = intf._transverse_batch_params
                self._transverse_k[start:stop] = intf._transverse_k
            else:
                self._params[start:stop, :fixed_parameter_count] = np.asarray(
                    [_extract_spring_params(spring, self._compact_simple_params) for spring in group],
                    dtype=np.float64,
                )
                if not self._compact_linear_params:
                    self._params[start:stop, curve_column] = np.fromiter(
                        (_extract_spring_curve_type(spring) for spring in group),
                        dtype=np.float64,
                        count=group_count,
                    )
                if not self._compact_simple_params:
                    self._params[start:stop, COMPRESSIVE_CURVE_TYPE_PARAM] = np.fromiter(
                        (_extract_spring_compressive_curve_type(spring) for spring in group),
                        dtype=np.float64,
                        count=group_count,
                    )
                self._transverse_k[start:stop] = np.fromiter(
                    (spring.k for spring in group),
                    dtype=np.float64,
                    count=group_count,
                )

            is_dirty = any(
                getattr(s, "_cstrain", 0.0) != 0.0
                or getattr(s, "_tstrain", 0.0) != 0.0
                or getattr(s, "phase", 0) != 0
                for s in group
            )
            if not is_dirty:
                self.committed[start:stop, :].fill(0.0)
                self.trial[start:stop, :].fill(0.0)
                self.trial[start:stop, 9] = np.fromiter(
                    (spring.k_tang for spring in group), dtype=np.float64,
                    count=group_count,
                )
                self.targets[start:stop].fill(0.0)
                self.enabled[start:stop].fill(True)
            else:
                self.committed[start:stop, :] = np.asarray(
                    [_extract_spring_committed(spring) for spring in group],
                    dtype=np.float64,
                )
                self.trial[start:stop, :] = np.asarray(
                    [_extract_spring_trial(spring) for spring in group],
                    dtype=np.float64,
                )
                self.targets[start:stop] = np.fromiter(
                    (_extract_spring_target(spring) for spring in group),
                    dtype=np.float64,
                    count=group_count,
                )
                self.enabled[start:stop] = np.fromiter(
                    (spring.is_on for spring in group),
                    dtype=np.bool_,
                    count=group_count,
                )


    def _read_transverse_object(self, index: int, spring: Any) -> None:
        fixed_count = len(SIMPLE_PARAM_NAMES) if self._compact_simple_params else len(_PARAM_NAMES)
        curve_col = (
            SIMPLE_TENSILE_CURVE_TYPE_PARAM
            if self._compact_simple_params
            else TENSILE_CURVE_TYPE_PARAM
        )
        self._params[index, :fixed_count] = _extract_spring_params(
            spring, self._compact_simple_params
        )
        if not self._compact_linear_params:
            self._params[index, curve_col] = _extract_spring_curve_type(spring)
        if not self._compact_simple_params:
            self._params[index, COMPRESSIVE_CURVE_TYPE_PARAM] = (
                _extract_spring_compressive_curve_type(spring)
            )
        self._transverse_k[index] = float(spring.k)
        self.committed[index, :] = _extract_spring_committed(spring)
        self.trial[index, :] = _extract_spring_trial(spring)
        self.targets[index] = _extract_spring_target(spring)
        self.enabled[index] = bool(spring.is_on)

    def _promote_transverse_parameter_storage(self) -> None:
        """Materialize the historical full layout after an explicit write."""
        if not self._compact_simple_params:
            return
        full = self.params._materialize_rows(slice(None))
        self._params = full
        self._compact_simple_params = False
        self._compact_linear_params = False

    def _refresh_simple_hysteretic_flag(self) -> None:
        n = len(self.springs)
        if self._compact_simple_params:
            # Compact storage is created only after every spring satisfies the
            # exact simple-law predicate, and incremental material updates are
            # rejected before import if a replacement violates it.
            self._simple_hysteretic = bool(n)
        else:
            self._simple_hysteretic = bool(
                n
                and np.all(self._params[:, :8] == 0.0)
                and np.all(self._params[:, 8] == 1.0)
                and np.all(self._params[:, 9] == 0.0)
                # The specialized zero-pinching kernel intentionally stores
                # no compressive-envelope discriminator.  Parabolic
                # compression therefore always uses the generic compiled
                # state machine, even when its other parameters are simple.
                and np.all(
                    self._params[:, COMPRESSIVE_CURVE_TYPE_PARAM] == 0.0
                )
            )
        # Diagnostic/correctness switch.  The specialized zero-pinching kernel
        # must remain bit-for-bit equivalent to the authoritative scalar state
        # machine through unloading/reloading histories.  Force the general
        # compiled kernel while investigating any full-analysis divergence.
        if _force_general_hysteretic_batch() and not self._compact_simple_params:
            self._simple_hysteretic = False
        if self._compact_linear_params:
            self._simple_linear_hysteretic = bool(self._simple_hysteretic and n)
        else:
            tensile_curve_column = (
                SIMPLE_TENSILE_CURVE_TYPE_PARAM
                if self._compact_simple_params else TENSILE_CURVE_TYPE_PARAM
            )
            self._simple_linear_hysteretic = bool(
                self._simple_hysteretic
                and n
                and np.all(
                    self._params[:, tensile_curve_column] == TENSILE_LINEAR
                )
            )

    @property
    def active(self) -> bool:
        return bool(self.springs or self.coulomb_springs or self.quad_records)

    def try_update_material_interfaces(self, interfaces: list[Any] | tuple[Any, ...]) -> bool:
        """Refresh changed interface constitutive rows without rebuilding the runtime.

        Material-only mutations preserve geometry, DOFs and afference topology.
        Transverse rows are refreshed in place; compact parameter storage is
        promoted to the full constitutive layout when required. Compatible
        interface-Coulomb identity/index changes (notably fixed-restraint to
        soil out-of-plane alias splitting) rebuild only that small dense
        subsystem. Any unsupported constitutive or structural change returns
        ``False`` before runtime arrays are modified, preserving the existing
        conservative full-runtime fallback.

        The spring objects must already contain the authoritative committed and
        trial state.  ``solve_static_nonlinear`` guarantees that condition at
        analysis boundaries by synchronizing the dense runtime in ``finally``.
        """
        changed = tuple(interfaces)
        if not changed:
            return True
        if not self._objects_trial_synced:
            # Do not import potentially stale object state into the dense
            # runtime.  A full rebuild is the conservative fallback.
            return False

        validated: list[tuple[int, _InterfaceSlice, tuple[Any, ...], tuple[tuple[int, Any], ...]]] = []
        requires_full_parameter_storage = False
        requires_coulomb_rebuild = False
        for interface in changed:
            record_index = self._record_by_id.get(id(interface))
            if record_index is None:
                return False
            record = self.records[record_index]
            group = interface.trasv_1
            if len(group) != record.stop - record.start:
                return False
            if hasattr(group, "transverse_rejection_reason"):
                rej = group.transverse_rejection_reason()
                if rej:
                    return False
            else:
                if any(self._transverse_rejection_reason(spring) for spring in group):
                    return False
            if self._compact_simple_params:
                if getattr(group, "is_batch_backed", False):
                    if (
                        (self._compact_linear_params and group.tensile_curve_type == "Exponential")
                        or group.compressive_curve_type == "Parabolic"
                    ):
                        requires_full_parameter_storage = True
                elif any(
                    not _uses_simple_hysteretic_parameters(spring)
                    or (
                        self._compact_linear_params
                        and spring.tensile_curve_type == "Exponential"
                    )
                    or spring.compressive_curve_type == "Parabolic"
                    for spring in group
                ):
                    requires_full_parameter_storage = True

            candidates: list[tuple[int, Any]] = []
            if len(interface.slid) > 1 or len(interface.slid_out_plan) > 2:
                return False

            old_oop0 = int(self._oop0_index[record_index])
            old_oop1 = int(self._oop1_index[record_index])
            old_oop_alias = old_oop0 >= 0 and old_oop0 == old_oop1
            new_oop_alias = (
                len(interface.slid_out_plan) >= 2
                and interface.slid_out_plan[0] is interface.slid_out_plan[1]
            )
            # A material mutation can change object-identity topology (fixed
            # restraint -> Soil is the relevant case).  Only the interface
            # Coulomb mapping needs rebuilding; the ~550k transverse rows and
            # all Quad/geometry arrays remain valid.
            if old_oop_alias != new_oop_alias:
                # Identity topology can change without invalidating any of the
                # large transverse/Quad arrays, but only if every replacement
                # spring still belongs to the compiled interface-Coulomb law.
                # Otherwise this interface must return to the conservative
                # scalar/full-runtime fallback.
                current_coulomb = []
                if interface.slid:
                    current_coulomb.append(interface.slid[0])
                current_coulomb.extend(interface.slid_out_plan[:2])
                if any(
                    self._coulomb_rejection_reason(spring)
                    for spring in current_coulomb
                ):
                    return False
                requires_coulomb_rebuild = True
                validated.append((record_index, record, group, ()))
                continue
            layouts = (
                (int(self._slid_index[record_index]), interface.slid[0] if interface.slid else None),
                (old_oop0, interface.slid_out_plan[0] if len(interface.slid_out_plan) >= 1 else None),
                (old_oop1, interface.slid_out_plan[1] if len(interface.slid_out_plan) >= 2 else None),
            )
            for dense_index, spring in layouts:
                if dense_index < 0:
                    if spring is not None:
                        # Runtime coverage may grow after a material-only
                        # mutation, but only for laws the compiled interface
                        # Coulomb path already supports. Unsupported laws must
                        # keep the conservative full-runtime fallback.
                        if self._coulomb_rejection_reason(spring):
                            return False
                        requires_coulomb_rebuild = True
                    continue
                if spring is None:
                    requires_coulomb_rebuild = True
                    continue
                if self._coulomb_rejection_reason(spring):
                    return False
                candidates.append((dense_index, spring))
            validated.append((record_index, record, group, tuple(candidates)))

        # Validation above is intentionally complete before touching any dense
        # state.  A compact runtime can be promoted in place because the
        # mutation is constitutive-only: geometry, dense indices, afference and
        # every state array keep the same topology.  Promotion reconstructs the
        # historical 33-column values exactly from the current synchronized
        # spring objects, avoiding a full 500k+ spring runtime rebuild after
        # scour-material changes.
        if requires_full_parameter_storage:
            self._promote_transverse_parameter_storage()

        # The remaining operations are fixed-shape assignments from production
        # spring types and cannot change runtime topology.
        for record_index, record, group, candidates in validated:
            start = record.start
            stop = record.stop
            if getattr(group, "is_batch_backed", False):
                group._histra_batch_managed = True
                self._transverse_k[start:stop] = group._k
                if self._compact_simple_params:
                    self._params[start:stop, :len(SIMPLE_PARAM_NAMES)] = group._params
                    if not self._compact_linear_params:
                        curve_col = SIMPLE_TENSILE_CURVE_TYPE_PARAM
                        if group._tensile_curve_types is not None:
                            self._params[start:stop, curve_col] = [
                                TENSILE_EXPONENTIAL if t == "Exponential" else TENSILE_LINEAR
                                for t in group._tensile_curve_types
                            ]
                        else:
                            self._params[start:stop, curve_col] = (
                                TENSILE_EXPONENTIAL if group.tensile_curve_type == "Exponential" else TENSILE_LINEAR
                            )
                else:
                    p = group._params
                    self._params[start:stop, :8] = 0.0
                    self._params[start:stop, 8] = group.betap
                    self._params[start:stop, 9] = group.betan
                    self._params[start:stop, 10:30] = p
                    self._params[start:stop, 30] = 0.5 * (
                        p[:, 0] * p[:, 1]
                        + (p[:, 2] - p[:, 0]) * (p[:, 3] + p[:, 1])
                        + (p[:, 4] - p[:, 2]) * (p[:, 5] + p[:, 3])
                        + p[:, 7] * p[:, 6]
                        + (p[:, 8] - p[:, 7]) * (p[:, 9] + p[:, 6])
                        + (p[:, 10] - p[:, 8]) * (p[:, 11] + p[:, 9])
                    )
                    self._params[start:stop, 31] = group._k
                    if group._tensile_curve_types is not None:
                        self._params[start:stop, TENSILE_CURVE_TYPE_PARAM] = [
                            TENSILE_EXPONENTIAL if t == "Exponential" else TENSILE_LINEAR
                            for t in group._tensile_curve_types
                        ]
                    else:
                        self._params[start:stop, TENSILE_CURVE_TYPE_PARAM] = (
                            TENSILE_EXPONENTIAL if group.tensile_curve_type == "Exponential" else TENSILE_LINEAR
                        )
                    if group._compressive_curve_types is not None:
                        self._params[start:stop, COMPRESSIVE_CURVE_TYPE_PARAM] = [
                            COMPRESSIVE_PARABOLIC if c == "Parabolic" else COMPRESSIVE_LINEAR
                            for c in group._compressive_curve_types
                        ]
                    else:
                        self._params[start:stop, COMPRESSIVE_CURVE_TYPE_PARAM] = (
                            COMPRESSIVE_PARABOLIC if group.compressive_curve_type == "Parabolic" else COMPRESSIVE_LINEAR
                        )
                self.committed[start:stop, :] = group._committed
                self.trial[start:stop, :] = group._trial
                self.enabled[start:stop] = group.is_on
            else:
                for offset, spring in enumerate(group):
                    dense_index = start + offset
                    predecessor = self.springs[dense_index]
                    if predecessor is not spring and hasattr(predecessor, "_histra_batch_managed"):
                        predecessor._histra_batch_managed = False
                    self.springs[dense_index] = spring
                    self.managed_springs[dense_index] = spring
                    spring._histra_batch_managed = True
                    self._read_transverse_object(dense_index, spring)
                    self._transverse_k[dense_index] = float(spring.k)

            if not requires_coulomb_rebuild:
                coulomb_offset = len(self.springs)
                for dense_index, spring in candidates:
                    predecessor = self.coulomb_springs[dense_index]
                    if predecessor is not spring and hasattr(predecessor, "_histra_batch_managed"):
                        predecessor._histra_batch_managed = False
                    self.coulomb_springs[dense_index] = spring
                    self.managed_springs[coulomb_offset + dense_index] = spring
                    spring._histra_batch_managed = True
                    self._import_interface_sliding_object(dense_index, spring)
                    self.coulomb_dns[dense_index] = 0.0

            # The interface object itself is retained by material mutation, so
            # the existing dense slice and record mapping remain valid.
            interface = record.interface
            interface._perf_hysteretic_batch = self
            interface._perf_hysteretic_slice = (record.start, record.stop)
            self._local_u[record_index, :] = interface.status.u[:12]

        if requires_coulomb_rebuild:
            self._rebuild_interface_coulomb_storage(
                changed_record_indices=frozenset(
                    record_index for record_index, _, _, _ in validated
                )
            )
        else:
            self._refresh_elastic_sliding_indices()
            self._refresh_unmanaged_sliding_record_indices()

        self._refresh_simple_hysteretic_flag()
        self._pending_values.fill(0.0)
        self._refresh_transverse_cache()
        self._refresh_full_force_cache()
        self._refresh_global_resisting_force_cache()
        self._refresh_max_u_cache()
        self._objects_trial_synced = True
        return True

    def performance_counts(self) -> dict[str, Any]:
        """Return stable production-backend coverage and rejection counters."""
        managed_interface_elastic = int(self._elastic_sliding_indices.size)
        managed_interface_coulomb = (
            len(self.coulomb_springs) - managed_interface_elastic
        )
        managed_quad_coulomb = sum(
            1 for row in self.quad_params
            if int(row[QPSUBLAW]) == QUAD_SUBLAW_COULOMB
        )
        managed_quad_cacovic = sum(
            1 for row in self.quad_params
            if int(row[QPSUBLAW]) == QUAD_SUBLAW_CACOVIC
        )
        managed_quad_elastic = sum(
            1 for row in self.quad_params
            if int(row[QPSUBLAW]) == QUAD_SUBLAW_ELASTIC
        )
        return {
            "managed_transverse_springs": len(self.springs),
            "transverse_parameter_columns": TRANSVERSE_PARAM_SIZE,
            "transverse_parameter_storage_columns": int(self._params.shape[1]),
            "compact_simple_hysteretic_params": bool(self._compact_simple_params),
            "managed_interface_coulomb_springs": managed_interface_coulomb,
            "managed_interface_elastic_springs": managed_interface_elastic,
            "managed_quad_coulomb_springs": managed_quad_coulomb,
            "managed_quad_cacovic_springs": managed_quad_cacovic,
            "managed_quad_elastic_springs": managed_quad_elastic,
            "managed_quad_hysteretic_springs": sum(
                int(row[QPSUBLAW]) == QUAD_SUBLAW_HYSTERETIC for row in self.quad_params
            ),
            "managed_coulomb_springs": (
                managed_interface_coulomb + managed_quad_coulomb
            ),
            "managed_quad_records": len(self.quad_records),
            "unmanaged_interfaces": len(self.unmanaged_interfaces),
            "unmanaged_quads": len(self.unmanaged_quads),
            "interface_rejection_reasons": dict(
                sorted(self.interface_rejection_reasons.items())
            ),
            "interface_coulomb_rejection_reasons": dict(
                sorted(self.interface_coulomb_rejection_reasons.items())
            ),
            "quad_rejection_reasons": dict(sorted(self.quad_rejection_reasons.items())),
        }

    def _read_elastic_quad_object(self, index: int, spring: SpringElastic) -> None:
        row = self.quad_state[index]
        row[QCSTRESS] = float(spring._cstress)
        row[QCSTRAIN] = float(spring._cstrain)
        row[QPHASE] = int(spring.phase)
        row[QTSTRESS] = float(spring._tstress)
        row[QTSTRAIN] = float(spring._tstrain)
        row[QTPHASE] = int(spring.t_phase)
        row[QKTANG] = float(spring.k_tang)
        row[QKTANG_COMMITTED] = float(spring.k_tang)

    def _write_elastic_quad_object(self, index: int, spring: SpringElastic) -> None:
        row = self.quad_state[index]
        spring._cstrain = float(row[QCSTRAIN])
        spring.u = float(row[QTSTRAIN])
        spring._cstress = spring.f = float(row[QCSTRESS])
        spring._tstrain = float(row[QTSTRAIN])
        spring._tstress = float(row[QTSTRESS])
        spring.k_tang = float(row[QKTANG])
        spring.phase = _PHASE_BY_CODE[int(row[QPHASE])]
        spring.t_phase = _PHASE_BY_CODE[int(row[QTPHASE])]

    def _read_quad_object(self, index: int, spring: Any) -> None:
        row = self.quad_state[index]
        row[QFY0], row[QFY1] = map(float, spring.fy[:2])
        row[QUMAX0], row[QUMAX1] = map(float, spring.umax[:2])
        row[QCROT_PU] = float(spring._crot_pu)
        row[QCROT_NU] = float(spring._crot_nu)
        row[QCROT_LIM_PU] = float(spring._crot_lim_pu)
        row[QCROT_LIM_NU] = float(spring._crot_lim_nu)
        row[QCROT_YP] = float(spring._crot_yp)
        row[QCROT_YN] = float(spring._crot_yn)
        row[QCMOM_MAX] = float(spring._cmom_max)
        row[QCMOM_MIN] = float(spring._cmom_min)
        row[QCLOAD] = int(spring._cload_indicator)
        row[QCPLAST_T] = float(bool(spring._cplastic_tension_indicator))
        row[QCPLAST_C] = float(bool(spring._cplastic_compression_indicator))
        row[QCUNLOAD_T] = int(spring._c_phase_unload_t)
        row[QCUNLOAD_C] = int(spring._c_phase_unload_c)
        row[QCUP] = float(spring._cup)
        row[QCENERGY] = float(spring.cenergy_d)
        row[QCSTRESS] = float(spring._cstress)
        row[QCSTRAIN] = float(spring._cstrain)
        row[QCSTRESS_NORMAL] = float(spring._cstress_normal)
        row[QCSTRESS_NORMAL_PREV] = float(spring._cstress_normal_prev)
        row[QCCONTACT] = float(spring._ccontact_area)
        row[QPHASE] = int(spring.phase)
        row[QTANG_RELOAD_T] = float(spring.tangent_reload_t)
        row[QTANG_RELOAD_C] = float(spring.tangent_reload_c)
        row[QKTANG_COMMITTED] = float(spring.k_tang_committed)
        row[QTROT_MAX] = float(spring._trot_max)
        row[QTROT_MIN] = float(spring._trot_min)
        row[QTROT_PU] = float(spring._trot_pu)
        row[QTROT_NU] = float(spring._trot_nu)
        row[QTROT_LIM_PU] = float(spring._trot_lim_pu)
        row[QTROT_LIM_NU] = float(spring._trot_lim_nu)
        row[QTROT_YP] = float(spring._trot_yp)
        row[QTROT_YN] = float(spring._trot_yn)
        row[QTMOM_MAX] = float(spring._tmom_max)
        row[QTMOM_MIN] = float(spring._tmom_min)
        row[QTLOAD] = int(spring._tload_indicator)
        row[QTPLAST_T] = float(bool(spring._tplastic_tension_indicator))
        row[QTPLAST_C] = float(bool(spring._tplastic_compression_indicator))
        row[QTUNLOAD_T] = int(spring._t_phase_unload_t)
        row[QTUNLOAD_C] = int(spring._t_phase_unload_c)
        row[QTENERGY] = float(spring._tenergy_d)
        row[QTUP] = float(spring._tup)
        row[QTSTRESS] = float(spring._tstress)
        row[QTSTRAIN] = float(spring._tstrain)
        row[QTSTRESS_NORMAL] = float(spring._tstress_normal)
        row[QTCONTACT] = float(spring._tcontact_area)
        row[QTPHASE] = int(spring.t_phase)
        row[QKTANG] = float(spring.k_tang)
        row[QMOM1P] = float(spring.mom1p)
        row[QROT1P] = float(spring.rot1p)
        row[QMOM2P] = float(spring.mom2p)
        row[QROT2P] = float(spring.rot2p)
        row[QMOM3P] = float(spring.mom3p)
        row[QROT3P] = float(spring.rot3p)
        row[QMOM1N] = float(spring.mom1n)
        row[QROT1N] = float(spring.rot1n)
        row[QMOM2N] = float(spring.mom2n)
        row[QROT2N] = float(spring.rot2n)
        row[QMOM3N] = float(spring.mom3n)
        row[QROT3N] = float(spring.rot3n)
        row[QUR0], row[QUR1] = map(float, spring.ur[:2])
        row[QDN] = float(spring.dn)

    def _write_hysteretic_quad_object(self, index: int, spring: SpringHysteretic) -> None:
        row = self.quad_state[index]
        c, t = row[QHCOMMITTED:QHTRIAL], row[QHTRIAL:]
        spring.umax[:] = c[:2].tolist()
        spring._crot_pu, spring._crot_nu = float(c[2]), float(c[3])
        spring.cenergy_d, spring._cload_indicator = float(c[4]), int(c[5])
        spring._cstress, spring._cstrain = float(c[6]), float(c[7])
        spring.phase = _PHASE_BY_CODE[int(c[8])]
        spring._trot_max, spring._trot_min = float(t[0]), float(t[1])
        spring._trot_pu, spring._trot_nu = float(t[2]), float(t[3])
        spring._tenergy_d, spring._tload_indicator = float(t[4]), int(t[5])
        spring._tstress, spring._tstrain = float(t[6]), float(t[7])
        spring.t_phase, spring.k_tang = _PHASE_BY_CODE[int(t[8])], float(t[9])
        spring.k_tang_committed = float(row[QKTANG_COMMITTED])
        spring.u, spring.f = spring._tstrain, spring._tstress

    def _write_quad_object(self, index: int, spring: Any) -> None:
        if isinstance(spring, SpringElastic):
            self._write_elastic_quad_object(index, spring)
            return
        if isinstance(spring, SpringHysteretic):
            self._write_hysteretic_quad_object(index, spring)
            return
        row = self.quad_state[index]
        spring.fy[:] = [float(row[QFY0]), float(row[QFY1])]
        spring.umax[:] = [float(row[QUMAX0]), float(row[QUMAX1])]
        spring._crot_pu = float(row[QCROT_PU])
        spring._crot_nu = float(row[QCROT_NU])
        spring._crot_lim_pu = float(row[QCROT_LIM_PU])
        spring._crot_lim_nu = float(row[QCROT_LIM_NU])
        spring._crot_yp = float(row[QCROT_YP])
        spring._crot_yn = float(row[QCROT_YN])
        spring._cmom_max = float(row[QCMOM_MAX])
        spring._cmom_min = float(row[QCMOM_MIN])
        spring._cload_indicator = int(row[QCLOAD])
        spring._cplastic_tension_indicator = bool(row[QCPLAST_T])
        spring._cplastic_compression_indicator = bool(row[QCPLAST_C])
        spring._c_phase_unload_t = _PHASE_BY_CODE[int(row[QCUNLOAD_T])]
        spring._c_phase_unload_c = _PHASE_BY_CODE[int(row[QCUNLOAD_C])]
        spring._cup = float(row[QCUP])
        spring.cenergy_d = float(row[QCENERGY])
        spring._cstress = float(row[QCSTRESS])
        spring._cstrain = float(row[QCSTRAIN])
        spring._cstress_normal = float(row[QCSTRESS_NORMAL])
        spring._cstress_normal_prev = float(row[QCSTRESS_NORMAL_PREV])
        spring._ccontact_area = float(row[QCCONTACT])
        spring.phase = _PHASE_BY_CODE[int(row[QPHASE])]
        spring.tangent_reload_t = float(row[QTANG_RELOAD_T])
        spring.tangent_reload_c = float(row[QTANG_RELOAD_C])
        spring.k_tang_committed = float(row[QKTANG_COMMITTED])
        spring._trot_max = float(row[QTROT_MAX])
        spring._trot_min = float(row[QTROT_MIN])
        spring._trot_pu = float(row[QTROT_PU])
        spring._trot_nu = float(row[QTROT_NU])
        spring._trot_lim_pu = float(row[QTROT_LIM_PU])
        spring._trot_lim_nu = float(row[QTROT_LIM_NU])
        spring._trot_yp = float(row[QTROT_YP])
        spring._trot_yn = float(row[QTROT_YN])
        spring._tmom_max = float(row[QTMOM_MAX])
        spring._tmom_min = float(row[QTMOM_MIN])
        spring._tload_indicator = int(row[QTLOAD])
        spring._tplastic_tension_indicator = bool(row[QTPLAST_T])
        spring._tplastic_compression_indicator = bool(row[QTPLAST_C])
        spring._t_phase_unload_t = _PHASE_BY_CODE[int(row[QTUNLOAD_T])]
        spring._t_phase_unload_c = _PHASE_BY_CODE[int(row[QTUNLOAD_C])]
        spring._tenergy_d = float(row[QTENERGY])
        spring._tup = float(row[QTUP])
        spring._tstress = float(row[QTSTRESS])
        spring._tstrain = float(row[QTSTRAIN])
        spring._tstress_normal = float(row[QTSTRESS_NORMAL])
        spring._tcontact_area = float(row[QTCONTACT])
        spring.t_phase = _PHASE_BY_CODE[int(row[QTPHASE])]
        spring.k_tang = float(row[QKTANG])
        spring.mom1p = float(row[QMOM1P])
        spring.rot1p = float(row[QROT1P])
        spring.mom2p = float(row[QMOM2P])
        spring.rot2p = float(row[QROT2P])
        spring.mom3p = float(row[QMOM3P])
        spring.rot3p = float(row[QROT3P])
        spring.mom1n = float(row[QMOM1N])
        spring.rot1n = float(row[QROT1N])
        spring.mom2n = float(row[QMOM2N])
        spring.rot2n = float(row[QROT2N])
        spring.mom3n = float(row[QMOM3N])
        spring.rot3n = float(row[QROT3N])
        spring.ur[:] = [float(row[QUR0]), float(row[QUR1])]
        spring.dn = float(row[QDN])
        spring.f = float(row[QCSTRESS])
        spring.u = float(row[QTSTRAIN])

    def _read_coulomb_object(self, index: int, spring: Any) -> None:
        row = self.coulomb_state[index]
        if isinstance(spring, SpringElastic):
            row.fill(0.0)
            ktang = float(spring.k_tang)
            if ktang == 0.0:
                ktang = float(spring.k)
            row[CCSTRESS] = float(spring._cstress)
            row[CCSTRAIN] = float(spring._cstrain)
            row[CTSTRESS] = float(spring._tstress)
            row[CTSTRAIN] = float(spring._tstrain)
            row[CKTANG] = ktang
            row[CKTANG_COMMITTED] = ktang
            row[CU] = float(spring.u)
            row[CF] = float(spring.f)
            return
        row[CFY0] = float(spring.fy[0])
        row[CFY1] = float(spring.fy[1])
        row[CCUP] = float(spring._cup)
        row[CCSTRESS] = float(spring._cstress)
        row[CCSTRAIN] = float(spring._cstrain)
        row[CCSTRESS_NORMAL] = float(spring._cstress_normal)
        row[CCSTRESS_NORMAL_PREV] = float(spring._cstress_normal_prev)
        row[CCCONTACT_AREA] = float(spring._ccontact_area)
        row[CCENERGY] = float(spring.cenergy_d)
        row[CCPHASE] = int(spring.phase)
        row[CTUP] = float(spring._tup)
        row[CTSTRESS] = float(spring._tstress)
        row[CTSTRAIN] = float(spring._tstrain)
        row[CTSTRESS_NORMAL] = float(spring._tstress_normal)
        row[CTCONTACT_AREA] = float(spring._tcontact_area)
        row[CTENERGY] = float(spring._tenergy_d)
        row[CTPHASE] = int(spring.t_phase)
        row[CKTANG] = float(spring.k_tang)
        row[CMOM1P] = float(spring.mom1p)
        row[CROT1P] = float(spring.rot1p)
        row[CMOM2P] = float(spring.mom2p)
        row[CROT2P] = float(spring.rot2p)
        row[CMOM1N] = float(spring.mom1n)
        row[CROT1N] = float(spring.rot1n)
        row[CMOM2N] = float(spring.mom2n)
        row[CROT2N] = float(spring.rot2n)
        row[CROT3N] = float(spring.rot3n)
        row[CROT3P] = float(spring.rot3p)
        row[CU] = float(spring.u)
        row[CF] = float(spring.f)
        row[CKTANG_COMMITTED] = float(spring.k_tang_committed)
        row[CDN] = float(spring.dn)
        row[CCUNLOAD_T] = int(spring._c_phase_unload_t)
        row[CCUNLOAD_C] = int(spring._c_phase_unload_c)
        row[CCPLASTIC_T] = float(spring._cplastic_tension_indicator)
        row[CCPLASTIC_C] = float(spring._cplastic_compression_indicator)
        row[CTANGENT_RELOAD_T] = float(spring.tangent_reload_t)
        row[CTANGENT_RELOAD_C] = float(spring.tangent_reload_c)


    def _write_coulomb_object(self, index: int, spring: Any) -> None:
        row = self.coulomb_state[index]
        if isinstance(spring, SpringElastic):
            spring._cstress = float(row[CCSTRESS])
            spring._cstrain = float(row[CCSTRAIN])
            spring._tstress = float(row[CTSTRESS])
            spring._tstrain = float(row[CTSTRAIN])
            spring.k_tang = float(row[CKTANG])
            spring.u = float(row[CU])
            spring.f = spring._cstress
            return
        spring.fy[0] = float(row[CFY0])
        spring.fy[1] = float(row[CFY1])
        spring._cup = float(row[CCUP])
        spring._cstress = float(row[CCSTRESS])
        spring._cstrain = float(row[CCSTRAIN])
        spring._cstress_normal = float(row[CCSTRESS_NORMAL])
        spring._cstress_normal_prev = float(row[CCSTRESS_NORMAL_PREV])
        spring._ccontact_area = float(row[CCCONTACT_AREA])
        spring.cenergy_d = float(row[CCENERGY])
        spring.phase = _PHASE_BY_CODE[int(row[CCPHASE])]
        spring._c_phase_unload_t = _PHASE_BY_CODE[int(row[CCUNLOAD_T])]
        spring._c_phase_unload_c = _PHASE_BY_CODE[int(row[CCUNLOAD_C])]
        spring._t_phase_unload_t = spring._c_phase_unload_t
        spring._t_phase_unload_c = spring._c_phase_unload_c
        spring._cplastic_tension_indicator = bool(row[CCPLASTIC_T])
        spring._cplastic_compression_indicator = bool(row[CCPLASTIC_C])
        spring._tplastic_tension_indicator = spring._cplastic_tension_indicator
        spring._tplastic_compression_indicator = spring._cplastic_compression_indicator
        spring.tangent_reload_t = float(row[CTANGENT_RELOAD_T])
        spring.tangent_reload_c = float(row[CTANGENT_RELOAD_C])

        spring._tup = float(row[CTUP])
        spring._tstress = float(row[CTSTRESS])
        spring._tstrain = float(row[CTSTRAIN])
        spring._tstress_normal = float(row[CTSTRESS_NORMAL])
        spring._tcontact_area = float(row[CTCONTACT_AREA])
        spring._tenergy_d = float(row[CTENERGY])
        spring.t_phase = _PHASE_BY_CODE[int(row[CTPHASE])]
        spring.k_tang = float(row[CKTANG])
        spring.mom1p = float(row[CMOM1P])
        spring.rot1p = float(row[CROT1P])
        spring.mom2p = float(row[CMOM2P])
        spring.rot2p = float(row[CROT2P])
        spring.mom1n = float(row[CMOM1N])
        spring.rot1n = float(row[CROT1N])
        spring.mom2n = float(row[CMOM2N])
        spring.rot2n = float(row[CROT2N])
        spring.rot3n = float(row[CROT3N])
        spring.rot3p = float(row[CROT3P])
        spring.u = float(row[CU])
        spring.f = float(row[CF])
        spring.k_tang_committed = float(row[CKTANG_COMMITTED])
        spring.dn = float(row[CDN])

    def _sync_interface_status_to_objects(self) -> None:
        for index, record in enumerate(self.records):
            record.interface.status.u[:12] = self._local_u[index].tolist()
            record.interface.status.normal_increment = float(self._normal_increments[index])
            record.interface.status.committed_normal_force = float(self._committed_forces[index])
            record.interface.status.max_spring_displacement = float(self._max_displacements[index])

    def prepare(self, x: np.ndarray) -> None:
        """Map one global Newton increment to all batched spring strains."""
        _map_and_prepare_interface_kinematics(
            x, self._aff_offsets, self._aff_gdls, self._aff_coefficients,
            self._local_du, self._local_u, self._lengths,
            self._constrained, self._d0s, self._d1s, self._num,
            self._num2, self._delta_flex, self._pending_values,
        )

        indices = self._record_index
        self.targets[:] = self.trial[:, 7] + (
            (self._num[indices] * self._dj + self._num2[indices] * self._di)
            / self._lengths[indices]
            - self._delta_flex[indices] * self._ecc
        )

    def evaluate(self) -> None:
        evaluator = (
            _evaluate_simple_linear_batch
            if self._simple_hysteretic
            else _evaluate_linear_batch
        )
        evaluator(
            self._params, self.committed, self.trial, self.targets, self.enabled
        )
        self._objects_trial_synced = False

    def configure_numba_threads(self) -> int | None:
        """Activate the workload-sized worker team for this runtime."""
        if set_num_threads is None or numba_config is None:
            self.numba_threads = None
            return None
        available = max(1, int(numba_config.NUMBA_NUM_THREADS))
        selected = recommended_numba_threads(
            len(self.records), len(self.springs), available
        )
        if get_num_threads is None or int(get_num_threads()) != selected:
            set_num_threads(selected)
        self.numba_threads = selected
        return selected

    def _refresh_transverse_cache(self) -> None:
        _finish_transverse_batch(
            self.trial, self.committed, self._di, self._dj, self._ecc,
            self._lengths, self._starts, self._stops, self._constrained,
            self._local_forces, self._normal_increments,
            self._committed_forces, self._max_displacements,
        )

    def finish(self) -> None:
        self._refresh_transverse_cache()
        if self.coulomb_springs:
            _advance_interface_coulomb_targets(
                self._pending_values, self._dist_for, self._normal_increments,
                self._slid_index, self._oop0_index, self._oop1_index,
                self.coulomb_targets, self.coulomb_dns,
            )
            _evaluate_initial_coulomb_batch(
                self.coulomb_params, self.coulomb_state,
                self.coulomb_targets, self.coulomb_dns, self.coulomb_enabled,
            )
            _evaluate_elastic_sliding_batch(
                self.coulomb_state,
                self.coulomb_targets,
                self._elastic_sliding_indices,
            )
        self._advance_unmanaged_sliding_springs()
        self._refresh_full_force_cache()
        # Keep the compact status values visible to Quad.ComputeDN and the
        # convergence/max-displacement checks.  Full local U and spring object
        # states are synchronized only at committed steps or snapshots.
        for record_index, record in enumerate(self.records):
            interface = record.interface
            interface.status.normal_increment = float(self._normal_increments[record_index])
            interface.status.committed_normal_force = float(self._committed_forces[record_index])
            interface.status.max_spring_displacement = float(self._max_displacements[record_index])

    def update_domain(self, x: np.ndarray, state: Any) -> None:
        """Evaluate all managed interfaces and Quads.

        The common simple-hysteretic path evaluates transverse springs and
        performs each interface's ordered force reduction in one compiled
        pass.  The general hysteretic path remains split into its existing
        kernels.  Every within-spring and within-interface arithmetic order is
        retained for nonlinear-path compatibility.
        """
        _map_and_prepare_interface_kinematics(
            x, self._aff_offsets, self._aff_gdls, self._aff_coefficients,
            self._local_du, self._local_u, self._lengths,
            self._constrained, self._d0s, self._d1s, self._num,
            self._num2, self._delta_flex, self._pending_values,
        )
        if self._simple_linear_hysteretic:
            _advance_evaluate_and_finish_simple_linear_batch(
                self._params, self.committed, self.trial, self.targets, self.enabled,
                self._record_index, self._num, self._num2, self._di, self._dj,
                self._lengths, self._delta_flex, self._ecc,
                self._starts, self._stops, self._constrained,
                self._local_forces, self._normal_increments,
                self._committed_forces, self._max_displacements,
            )
        else:
            if self._simple_hysteretic:
                _advance_and_evaluate_simple_linear_batch(
                    self._params, self.committed, self.trial, self.targets,
                    self.enabled, self._record_index, self._num, self._num2,
                    self._di, self._dj, self._lengths, self._delta_flex,
                    self._ecc,
                )
            else:
                _advance_transverse_targets(
                    self.trial, self._record_index, self._num, self._num2,
                    self._di, self._dj, self._lengths, self._delta_flex,
                    self._ecc, self.targets,
                )
                _evaluate_linear_batch(
                    self._params, self.committed, self.trial, self.targets,
                    self.enabled,
                )
            _finish_transverse_batch(
                self.trial, self.committed, self._di, self._dj, self._ecc,
                self._lengths, self._starts, self._stops, self._constrained,
                self._local_forces, self._normal_increments,
                self._committed_forces, self._max_displacements,
            )
        if self.coulomb_targets.size:
            _advance_interface_coulomb_targets(
                self._pending_values, self._dist_for, self._normal_increments,
                self._slid_index, self._oop0_index, self._oop1_index,
                self.coulomb_targets, self.coulomb_dns,
            )
            _evaluate_initial_coulomb_batch(
                self.coulomb_params, self.coulomb_state, self.coulomb_targets,
                self.coulomb_dns, self.coulomb_enabled,
            )
            _evaluate_elastic_sliding_batch(
                self.coulomb_state,
                self.coulomb_targets,
                self._elastic_sliding_indices,
            )
        self._advance_unmanaged_sliding_springs()
        self._refresh_full_force_cache()

        if self._quad_local_du.shape[0]:
            _map_global_to_local(
                x, self._quad_aff_offsets, self._quad_aff_gdls,
                self._quad_aff_coefficients, self._quad_local_du, self._quad_local_u,
            )
            _prepare_quad_kinematics(
                self._quad_local_du, self._quad_local_u,
                self._quad_edge_offsets, self._quad_edge_records,
                self._quad_edge_areas, self._normal_increments,
                self._committed_forces, self._quad_d_alfa,
                int(getattr(state, "step", 0)), self._quad_sigma_initial,
                self._quad_strains, self._quad_dns, self.quad_params, False,
            )
            _evaluate_quad_takeda_batch(
                self.quad_params, self.quad_state, self._quad_strains,
                self._quad_dns, self._quad_volumes, self._quad_sigma_initial,
            )
        _refresh_global_resisting_force_by_dof(
            self._quad_d_alfa, self.quad_state, self._quad_forces,
            self._local_full_forces, self._global_force_offsets,
            self._global_force_indices, self._global_force_coefficients,
            self._interface_force_size, self._global_resisting_force,
        )
        _refresh_max_u_cache(
            self._quad_local_u, self._max_displacements, self._max_u_cache
        )
        self._objects_trial_synced = False

    def update_quads(self, x: np.ndarray, state: Any) -> None:
        if not self.quad_records:
            return
        _map_global_to_local(
            x, self._quad_aff_offsets, self._quad_aff_gdls,
            self._quad_aff_coefficients, self._quad_local_du, self._quad_local_u,
        )
        _prepare_quad_kinematics(
            self._quad_local_du, self._quad_local_u,
            self._quad_edge_offsets, self._quad_edge_records,
            self._quad_edge_areas, self._normal_increments,
            self._committed_forces, self._quad_d_alfa,
            int(getattr(state, "step", 0)), self._quad_sigma_initial,
            self._quad_strains, self._quad_dns, self.quad_params, False,
        )
        _evaluate_quad_takeda_batch(
            self.quad_params, self.quad_state,
            self._quad_strains, self._quad_dns,
            self._quad_volumes, self._quad_sigma_initial,
        )
        for index, quad in enumerate(self.quad_records):
            quad.status.u[:7] = self._quad_local_u[index].tolist()
            quad.sigma_initial = float(self._quad_sigma_initial[index])
            # Keep the tangent visible to any analysis method that explicitly
            # asks Quad.compute_k for an updated stiffness.  The complete
            # constitutive object is synchronized only at commits/restores.
            quad.spring.k_tang = float(self.quad_state[index, QKTANG])

    def manages_quad(self, quad: Any) -> bool:
        return id(quad) in self.quad_ids

    def _refresh_full_force_cache(self) -> None:
        self._interface_resultants_valid = False
        _assemble_full_interface_forces(
            self._local_forces, self.coulomb_state,
            self._slid_index, self._oop0_index, self._oop1_index,
            self._dist, self._local_full_forces, self._max_displacements,
            self.coulomb_targets,
        )
        self._add_unmanaged_sliding_forces()

    def _advance_unmanaged_sliding_springs(self) -> None:
        """Advance scalar sliding springs on otherwise managed interfaces."""
        if self._unmanaged_sliding_record_indices.size == 0:
            return
        for record_index in self._unmanaged_sliding_record_indices:
            record = self.records[int(record_index)]
            interface = record.interface
            if interface.slid and int(self._slid_index[record_index]) < 0:
                spring = interface.slid[0]
                spring.u += float(self._pending_values[record_index, 0])
                spring.set_trial_strain(spring.u)

            oop0 = int(self._oop0_index[record_index])
            oop1 = int(self._oop1_index[record_index])
            if len(interface.slid_out_plan) >= 2 and oop0 < 0 and oop1 < 0:
                spring0, spring1 = interface.slid_out_plan[:2]
                di, dj = self._dist_for[record_index]
                du_a = float(self._pending_values[record_index, 1])
                du_b = float(self._pending_values[record_index, 2])
                spring0.u += du_a + (du_b - du_a) * di
                spring0.set_trial_strain(spring0.u)
                spring1.u += du_a + (du_b - du_a) * dj
                spring1.set_trial_strain(spring1.u)

    def _add_unmanaged_sliding_forces(self) -> None:
        """Add linear/unsupported sliding forces omitted by the dense kernel."""
        if self._unmanaged_sliding_record_indices.size == 0:
            return
        for record_index in self._unmanaged_sliding_record_indices:
            record_index = int(record_index)
            record = self.records[record_index]
            interface = record.interface
            max_u = float(self._max_displacements[record_index])
            if interface.slid and int(self._slid_index[record_index]) < 0:
                spring = interface.slid[0]
                force = float(spring.get_force())
                self._local_full_forces[record_index, 6] += force
                self._local_full_forces[record_index, 7] -= force
                max_u = max(max_u, abs(float(spring.get_displacement())))

            oop0 = int(self._oop0_index[record_index])
            oop1 = int(self._oop1_index[record_index])
            if len(interface.slid_out_plan) >= 2 and oop0 < 0 and oop1 < 0:
                spring0, spring1 = interface.slid_out_plan[:2]
                force0 = float(spring0.get_force())
                force1 = float(spring1.get_force())
                di, dj = self._dist[record_index]
                first = dj * force0 + di * force1
                second = di * force0 + dj * force1
                self._local_full_forces[record_index, 8] += first
                self._local_full_forces[record_index, 9] += second
                self._local_full_forces[record_index, 10] -= first
                self._local_full_forces[record_index, 11] -= second
                max_u = max(
                    max_u,
                    abs(float(spring0.get_displacement())),
                    abs(float(spring1.get_displacement())),
                )
            self._max_displacements[record_index] = max_u

    def _refresh_global_resisting_force_cache(self) -> None:
        _refresh_global_resisting_force_by_dof(
            self._quad_d_alfa, self.quad_state, self._quad_forces,
            self._local_full_forces, self._global_force_offsets,
            self._global_force_indices, self._global_force_coefficients,
            self._interface_force_size, self._global_resisting_force,
        )

    def _refresh_max_u_cache(self) -> None:
        _refresh_max_u_cache(
            self._quad_local_u, self._max_displacements, self._max_u_cache
        )

    def copy_resisting_force_to(self, destination: np.ndarray) -> None:
        destination[:] = self._global_resisting_force

    def scatter_quad_resisting_force(self, global_force: np.ndarray) -> None:
        for index, quad in enumerate(self.quad_records):
            force = float(self._quad_d_alfa[index] * self.quad_state[index, QTSTRESS])
            quad.status.f = force
            self._quad_forces[index, 0] = force
        _scatter_local_forces(
            self._quad_forces, self._quad_force_offsets,
            self._quad_force_gdls, self._quad_force_coefficients,
            global_force,
        )

    def scatter_resisting_force(self, global_force: np.ndarray) -> None:
        _scatter_local_forces(
            self._local_full_forces, self._aff_offsets, self._aff_gdls,
            self._aff_coefficients, global_force,
        )

    def cached_max_u(self) -> tuple[float, int, str]:
        value = float(self._max_u_cache[0])
        index = int(self._max_u_cache[1])
        kind = int(self._max_u_cache[2])
        if kind == 1 and 0 <= index < len(self.quad_records):
            return value, int(self.quad_records[index].key), "Quad"
        if kind == 2 and 0 <= index < len(self.records):
            return value, int(self.records[index].interface.key), "Interface"
        return value, 0, ""

    def cached_quad_max_u(self) -> tuple[float, int]:
        value = float(self._max_u_cache[3])
        index = int(self._max_u_cache[4])
        if 0 <= index < len(self.quad_records):
            return value, int(self.quad_records[index].key)
        return value, 0

    def manages(self, interface: Any) -> bool:
        return id(interface) in self.interface_ids

    def sync_interface_trial_to_objects(self, interface: Any) -> None:
        start, stop = interface._perf_hysteretic_slice
        group = interface.trasv_1
        if getattr(group, "is_batch_backed", False):
            group.sync_trial_from_dense(self.trial[start:stop])
        else:
            for local_i, spring in enumerate(self.springs[start:stop], start):
                row = self.trial[local_i]
                if isinstance(spring, SpringHysteretic):
                    spring._trot_max = float(row[0])
                    spring._trot_min = float(row[1])
                    spring._trot_pu = float(row[2])
                    spring._trot_nu = float(row[3])
                    spring._tenergy_d = float(row[4])
                    spring._tload_indicator = int(row[5])
                    spring._tstress = float(row[6])
                    spring._tstrain = float(row[7])
                    spring.t_phase = _PHASE_BY_CODE[int(row[8])]
                    spring.k_tang = float(row[9])
                    spring.f = spring._tstress
                    spring.u = spring._tstrain
                else:
                    stress = float(row[6])
                    strain = float(row[7])
                    spring._tstress = stress
                    spring._tstrain = strain
                    spring.u = strain
                    spring.k_tang = float(row[9])

        record_index = self._record_by_id[id(interface)]
        for spring_index in (
            int(self._slid_index[record_index]),
            int(self._oop0_index[record_index]),
            int(self._oop1_index[record_index]),
        ):
            if spring_index >= 0:
                self._write_coulomb_object(
                    spring_index, self.coulomb_springs[spring_index]
                )
        interface.status.u[:12] = self._local_u[record_index].tolist()

    def local_force_for(self, interface: Any) -> np.ndarray:
        return self._local_full_forces[self._record_by_id[id(interface)]]

    def transverse_force_for(self, interface: Any) -> np.ndarray:
        return self._local_forces[self._record_by_id[id(interface)]]

    def all_resultant_forces(self) -> np.ndarray:
        """Return (N_interfaces, 3) float32 physical local resultant forces."""
        if not self._interface_resultants_valid:
            _batch_interface_resultants(
                self._starts,
                self._stops,
                self.trial,
                self._slid_index,
                self._oop0_index,
                self._oop1_index,
                self.coulomb_state,
                self._interface_resultants,
            )
            self._interface_resultants_valid = True
        return self._interface_resultants

    def compute_total_reaction_vector(self) -> np.ndarray:
        """Compute the global sum of reaction forces on all constrained interfaces."""
        if not np.any(self._constrained):
            return np.zeros(3, dtype=np.float64)
        res = self.all_resultant_forces()[self._constrained]
        e1 = self._e1[self._constrained]
        e2 = self._e2[self._constrained]
        e3 = self._e3[self._constrained]
        global_forces = (
            e1 * res[:, 0:1] + e2 * res[:, 1:2] + e3 * res[:, 2:3]
        )
        return np.sum(global_forces, axis=0, dtype=np.float64)

    def get_pdelta_plan(self) -> PDeltaPlan:
        """Return cached PDeltaPlan precomputing static geometry and topology."""
        if self._pdelta_plan is None:
            self._pdelta_plan = self._build_pdelta_plan()
        return self._pdelta_plan

    def _build_pdelta_plan(self) -> PDeltaPlan:
        quad_indices: list[int] = []
        intf_indices: list[int] = []
        r_list: list[np.ndarray] = []
        R_list: list[np.ndarray] = []
        collections = self.model.collections
        managed_quad_indices = {id(q): i for i, q in enumerate(self.quad_records)}

        for quad in collections.quads.values():
            q_idx = managed_quad_indices.get(id(quad))
            if q_idx is None:
                continue
            g_quad = np.asarray([quad.g.x, quad.g.y, quad.g.z], dtype=np.float32)
            for face_intf_keys in quad.interface_keys[:4]:
                for intf_key in face_intf_keys:
                    intf = collections.interfaces.get(intf_key)
                    if intf is None:
                        continue
                    intf_idx = self._record_by_id.get(id(intf))
                    if intf_idx is None:
                        continue
                    sign = 1.0 if (intf.parent_element_key1 == quad.key and intf.parent_type_element1 == "Quad") else -1.0
                    e1 = np.array(intf.reference_e1, dtype=np.float32)
                    e2 = np.array(intf.reference_e2, dtype=np.float32)
                    e3 = np.array(intf.reference_e3, dtype=np.float32)
                    R = sign * np.column_stack([e1, e2, e3])

                    intf_nodes = [collections.nodes[nk].point for nk in intf.node_keys if nk in collections.nodes]
                    if intf_nodes:
                        g_intf = np.mean([[p.x, p.y, p.z] for p in intf_nodes], axis=0)
                    elif getattr(intf, "vint3d", None):
                        g_intf = np.mean([[p.x, p.y, p.z] for p in intf.vint3d], axis=0)
                    else:
                        continue

                    r = np.asarray(g_intf, dtype=np.float32) - g_quad
                    quad_indices.append(q_idx)
                    intf_indices.append(intf_idx)
                    r_list.append(r)
                    R_list.append(R)

        scatter_quad_idx: list[int] = []
        scatter_comp: list[int] = []
        scatter_dof: list[int] = []
        scatter_alfa: list[float] = []
        gdl = int(self.model.gdl)

        scatter_offsets = [0]
        for q_idx, quad in enumerate(self.quad_records):
            for comp in range(3):
                aff_idx = 3 + comp
                if aff_idx < len(quad.aff):
                    for entry in quad.aff[aff_idx]:
                        dof = entry.gdl - 1
                        if 0 <= dof < gdl:
                            scatter_quad_idx.append(q_idx)
                            scatter_comp.append(comp)
                            scatter_dof.append(dof)
                            scatter_alfa.append(float(entry.alfa))
            scatter_offsets.append(len(scatter_dof))

        return PDeltaPlan(
            quad_indices=np.asarray(quad_indices, dtype=np.int32),
            intf_indices=np.asarray(intf_indices, dtype=np.int32),
            r_arr=(
                np.asarray(r_list, dtype=np.float32)
                if r_list
                else np.empty((0, 3), dtype=np.float32)
            ),
            R_arr=(
                np.asarray(R_list, dtype=np.float32)
                if R_list
                else np.empty((0, 3, 3), dtype=np.float32)
            ),
            scatter_quad_idx=np.asarray(scatter_quad_idx, dtype=np.int32),
            scatter_comp=np.asarray(scatter_comp, dtype=np.int32),
            scatter_dof=np.asarray(scatter_dof, dtype=np.int32),
            scatter_alfa=np.asarray(scatter_alfa, dtype=np.float64),
            scatter_offsets=np.asarray(scatter_offsets, dtype=np.int32),
        )

    def compute_pdelta_interface_moments(self, pq_global: np.ndarray) -> None:
        """Accumulate macro-element P-Delta interface moments directly into ``pq_global``."""
        plan = self.get_pdelta_plan()
        if len(plan.quad_indices) == 0:
            return
        # ComputePDeltaLoads reads Interface.Status.Forces, refreshed by
        # CommonOperations.AddStateElements at save boundaries, not each trial.
        all_res = self._pdelta_saved_resultants
        _eval_pdelta_interfaces_kernel(
            self._quad_local_u,
            all_res,
            plan.quad_indices,
            plan.intf_indices,
            plan.r_arr,
            plan.R_arr,
            plan.scatter_quad_idx,
            plan.scatter_comp,
            plan.scatter_dof,
            plan.scatter_alfa,
            pq_global,
        )

    def _build_pdelta_line_load_plan(
        self, analysis: Any, combination: int
    ) -> PDeltaLineLoadPlan:
        """Resolve static line-load vectors once for an analysis configuration."""
        from histra.solver.load_assembly import _get_load_template_coefficient

        collections = self.model.collections
        managed_quad_indices = {id(quad): index for index, quad in enumerate(self.quad_records)}
        load_quad_indices: list[int] = []
        load_r: list[np.ndarray] = []
        item_offsets = [0]
        item_forces: list[np.ndarray] = []

        for load in collections.line_loads.values():
            if load.element_type != "Quad":
                continue
            quad = collections.quads.get(int(load.element_key))
            if quad is None:
                continue
            quad_index = managed_quad_indices.get(id(quad))
            if quad_index is None:
                continue
            template = collections.load_templates.get(load.load_template_key)
            if template is None:
                continue

            point1 = np.asarray(load.point1, dtype=np.float32)
            point2 = np.asarray(load.point2, dtype=np.float32)
            length = np.float32(np.linalg.norm(point1 - point2))
            midpoint = np.float32(0.5) * (point1 + point2)
            g_quad = np.asarray((quad.g.x, quad.g.y, quad.g.z), dtype=np.float32)
            load_quad_indices.append(quad_index)
            load_r.append(midpoint - g_quad)
            for item in template.items:
                coefficient = np.float32(
                    _get_load_template_coefficient(
                        self.model,
                        int(analysis.key),
                        combination,
                        int(item.load_condition_id),
                        item,
                    )
                )
                direction = np.asarray(item.direction_for(quad), dtype=np.float32)
                item_forces.append(
                    (
                        np.float32(item.load_value)
                        * length
                        * coefficient
                        * direction
                    ).astype(np.float32)
                )
            item_offsets.append(len(item_forces))

        return PDeltaLineLoadPlan(
            load_quad_indices=np.asarray(load_quad_indices, dtype=np.int32),
            load_r_arr=(
                np.asarray(load_r, dtype=np.float32)
                if load_r else np.empty((0, 3), dtype=np.float32)
            ),
            item_offsets=np.asarray(item_offsets, dtype=np.int32),
            item_forces=(
                np.asarray(item_forces, dtype=np.float32)
                if item_forces else np.empty((0, 3), dtype=np.float32)
            ),
        )

    def compute_pdelta_line_load_moments(
        self, pq_global: np.ndarray, analysis: Any, combination: int
    ) -> None:
        """Accumulate cached, compiled Quad line-load P-Delta moments."""
        key = (int(analysis.key), int(combination))
        plan = self._pdelta_line_load_plans.get(key)
        if plan is None:
            plan = self._build_pdelta_line_load_plan(analysis, combination)
            self._pdelta_line_load_plans[key] = plan
        if plan.load_quad_indices.size == 0:
            return
        scatter = self.get_pdelta_plan()
        _eval_pdelta_line_loads_kernel(
            self._quad_local_u,
            plan.load_quad_indices,
            plan.load_r_arr,
            plan.item_offsets,
            plan.item_forces,
            scatter.scatter_offsets,
            scatter.scatter_comp,
            scatter.scatter_dof,
            scatter.scatter_alfa,
            pq_global,
        )

    def resultant_force_for(self, interface: Any) -> np.ndarray:
        """Return C# ``Interface.Status.Forces`` from authoritative dense state.

        This is the physical local X/Y/Z resultant used by
        ``ComputePDeltaLoads``. It is not the six-component generalized
        resisting-force vector stored in ``_local_forces``.
        """
        record_index = self._record_by_id[id(interface)]
        base = self.all_resultant_forces()[record_index]
        if getattr(interface, "trasv_2", None) or (int(self._slid_index[record_index]) < 0 and interface.slid):
            f32 = np.float32
            fx = base[0]
            fy = base[1]
            fz = base[2]
            for spring in interface.trasv_2:
                fy = f32(fy + f32(spring.get_force()))
            if int(self._slid_index[record_index]) < 0:
                for spring in interface.slid:
                    fx = f32(fx - f32(spring.get_force()))
            return np.asarray((fx, fy, fz), dtype=np.float32)
        return base

    def trial_stresses_for(self, interface: Any) -> np.ndarray:
        start, stop = interface._perf_hysteretic_slice
        return self.trial[start:stop, 6]

    def sync_trial_to_objects(self) -> None:
        if self._objects_trial_synced:
            return
        for record in self.records:
            self.sync_interface_trial_to_objects(record.interface)
        self._objects_trial_synced = True

    def sync_tangents_to_objects(self) -> None:
        """Publish only the tangent stiffness needed for element stiffness assembly."""
        k_tang = self.trial[:, 9]
        if self.is_batch_backed:
            for record in self.records:
                group = record.interface.trasv_1
                start, stop = record.start, record.stop
                if getattr(group, "is_batch_backed", False):
                    group.sync_tangents_from_dense(k_tang[start:stop])
                else:
                    for i, spring in enumerate(group, start):
                        spring.k_tang = float(k_tang[i])
        else:
            for i, spring in enumerate(self.springs):
                spring.k_tang = float(k_tang[i])
        for i, spring in enumerate(self.coulomb_springs):
            spring.k_tang = float(self.coulomb_state[i, CKTANG])
        for i, quad in enumerate(self.quad_records):
            if quad.spring is not None:
                if isinstance(quad.spring, SpringElastic):
                    quad.spring.k_tang = float(quad.spring.k)
                else:
                    quad.spring.k_tang = float(self.quad_state[i, QKTANG])

    def sync_all_to_objects(self) -> None:
        """Publish the authoritative dense state to the compatibility objects."""
        if self.is_batch_backed:
            for record in self.records:
                group = record.interface.trasv_1
                start, stop = record.start, record.stop
                if getattr(group, "is_batch_backed", False):
                    group.sync_from_dense(self.committed[start:stop], self.trial[start:stop])
                else:
                    for local_i, spring in enumerate(group, start):
                        committed = self.committed[local_i]
                        trial = self.trial[local_i]
                        if isinstance(spring, SpringHysteretic):
                            spring.umax[0] = float(committed[0])
                            spring.umax[1] = float(committed[1])
                            spring._crot_pu = float(committed[2])
                            spring._crot_nu = float(committed[3])
                            spring.cenergy_d = float(committed[4])
                            spring._cload_indicator = int(committed[5])
                            spring._cstress = float(committed[6])
                            spring._cstrain = float(committed[7])
                            spring.phase = _PHASE_BY_CODE[int(committed[8])]
                            spring._trot_max = float(trial[0])
                            spring._trot_min = float(trial[1])
                            spring._trot_pu = float(trial[2])
                            spring._trot_nu = float(trial[3])
                            spring._tenergy_d = float(trial[4])
                            spring._tload_indicator = int(trial[5])
                            spring._tstress = float(trial[6])
                            spring._tstrain = float(trial[7])
                            spring.t_phase = _PHASE_BY_CODE[int(trial[8])]
                            spring.k_tang = float(trial[9])
                            spring.k_tang_committed = float(trial[9])
                            spring.f = float(trial[6])
                            spring.u = float(trial[7])
                        else:
                            spring._cstress, spring._cstrain = float(committed[6]), float(committed[7])
                            spring._tstress, spring._tstrain = float(trial[6]), float(trial[7])
                            spring.f = spring._cstress
                            spring.u = float(trial[7])
                            spring.k_tang = float(trial[9])
                            spring.k_tang_committed = float(trial[9])
        else:
            for i, spring in enumerate(self.springs):
                committed = self.committed[i]
                trial = self.trial[i]
                if isinstance(spring, SpringHysteretic):
                    spring.umax[0] = float(committed[0])
                    spring.umax[1] = float(committed[1])
                    spring._crot_pu = float(committed[2])
                    spring._crot_nu = float(committed[3])
                    spring.cenergy_d = float(committed[4])
                    spring._cload_indicator = int(committed[5])
                    spring._cstress = float(committed[6])
                    spring._cstrain = float(committed[7])
                    spring.phase = _PHASE_BY_CODE[int(committed[8])]
                    spring._trot_max = float(trial[0])
                    spring._trot_min = float(trial[1])
                    spring._trot_pu = float(trial[2])
                    spring._trot_nu = float(trial[3])
                    spring._tenergy_d = float(trial[4])
                    spring._tload_indicator = int(trial[5])
                    spring._tstress = float(trial[6])
                    spring._tstrain = float(trial[7])
                    spring.t_phase = _PHASE_BY_CODE[int(trial[8])]
                    spring.k_tang = float(trial[9])
                    spring.k_tang_committed = float(trial[9])
                    spring.f = float(trial[6])
                    spring.u = float(trial[7])
                else:
                    spring._cstress, spring._cstrain = float(committed[6]), float(committed[7])
                    spring._tstress, spring._tstrain = float(trial[6]), float(trial[7])
                    spring.f = spring._cstress
                    spring.u = float(trial[7])
                    spring.k_tang = float(trial[9])
                    spring.k_tang_committed = float(trial[9])
        for i, spring in enumerate(self.coulomb_springs):
            self._write_coulomb_object(i, spring)
        for i, quad in enumerate(self.quad_records):
            self._write_quad_object(i, quad.spring)
            quad.status.u[:7] = self._quad_local_u[i].tolist()
            quad.status.f = float(self._quad_forces[i, 0])
            quad.sigma_initial = float(self._quad_sigma_initial[i])
        self._sync_interface_status_to_objects()
        self._objects_trial_synced = True

    def compute_energy(self, initial_elastic=0.0, initial_plastic=0.0) -> tuple[float, float]:
        """Add original signed increments directly to the running totals."""
        elastic, plastic = _managed_elastic_energy(
            self._transverse_k, self.committed, self.trial, self._quad_k, self.quad_state,
            self._starts, self._stops, self.coulomb_params, self.coulomb_state,
            self._slid_index, self._oop0_index, self._oop1_index,
            initial_elastic, initial_plastic,
        )
        return float(elastic), float(plastic)

    def commit(self, *, sync_objects: bool = False) -> None:
        if self.quad_records:
            _commit_quad_takeda_batch(self.quad_params, self.quad_state)
        self.committed[:, 0] = self.trial[:, 0]
        self.committed[:, 1] = self.trial[:, 1]
        self.committed[:, 2] = self.trial[:, 2]
        self.committed[:, 3] = self.trial[:, 3]
        self.committed[:, 4] = self.trial[:, 4]
        self.committed[:, 5] = self.trial[:, 5]
        self.committed[:, 6] = self.trial[:, 6]
        self.committed[:, 7] = self.trial[:, 7]
        self.committed[:, 8] = self.trial[:, 8]
        if self.coulomb_springs:
            _commit_initial_coulomb_batch(
                self.coulomb_state, self.coulomb_enabled
            )
            _commit_elastic_sliding_batch(
                self.coulomb_state, self._elastic_sliding_indices
            )
            self.coulomb_targets[:] = self.coulomb_state[:, CU]
        self._sync_interface_status_to_objects()
        self._objects_trial_synced = False
        if sync_objects:
            self.sync_all_to_objects()

    def snapshot(
        self, *, reuse: tuple[np.ndarray, ...] | None = None
    ) -> tuple[np.ndarray, ...]:
        """Copy reversible state, optionally consuming a previous snapshot's buffers.

        Reuse overwrites that snapshot; independent step/line-search snapshots
        must keep their own buffers. All fields are still copied losslessly.
        """
        sources = (
            self.committed, self.trial, self.targets,
            self.coulomb_state, self.coulomb_targets,
            self.coulomb_dns, self._local_u,
            self._quad_local_u, self._quad_sigma_initial, self.quad_state,
            self._pdelta_saved_resultants,
        )
        if reuse is None:
            return tuple(source.copy() for source in sources)
        if len(reuse) != len(sources):
            raise ValueError("Snapshot buffer count does not match runtime state")
        # Validate the complete buffer set before overwriting any saved state.
        for target, source in zip(reuse, sources):
            if (target.shape != source.shape or target.dtype != source.dtype
                    or not target.flags.writeable):
                raise ValueError("Snapshot buffer shape, dtype or writability differs")
        for index, target in enumerate(reuse):
            if any(np.shares_memory(target, source) for source in sources):
                raise ValueError("Snapshot buffers must not alias live runtime state")
            if any(np.shares_memory(target, other) for other in reuse[:index]):
                raise ValueError("Snapshot buffers must not alias each other")
        for target, source in zip(reuse, sources):
            np.copyto(target, source)
        return reuse

    def restore(self, state: tuple[np.ndarray, ...]) -> None:
        (
            committed, trial, targets, coulomb_state, coulomb_targets,
            coulomb_dns, local_u, quad_local_u, quad_sigma_initial,
            quad_state, saved_resultants,
        ) = state
        self.committed[...] = committed
        self.trial[...] = trial
        self.targets[...] = targets
        self.coulomb_state[...] = coulomb_state
        self.coulomb_targets[...] = coulomb_targets
        self.coulomb_dns[...] = coulomb_dns
        self._local_u[...] = local_u
        self._quad_local_u[...] = quad_local_u
        self._quad_sigma_initial[...] = quad_sigma_initial
        self.quad_state[...] = quad_state
        self._pdelta_saved_resultants[...] = saved_resultants
        for row, record in zip(self._pdelta_saved_resultants, self.records):
            record.interface.status.forces = tuple(float(value) for value in row)
        self._pending_values.fill(0.0)
        self._refresh_transverse_cache()
        self._objects_trial_synced = False
        self.sync_trial_to_objects()
        for index, quad in enumerate(self.quad_records):
            quad.status.u[:7] = self._quad_local_u[index].tolist()
            quad.sigma_initial = float(self._quad_sigma_initial[index])
            self._write_quad_object(index, quad.spring)
        self._refresh_full_force_cache()
        self._refresh_global_resisting_force_cache()
        self._refresh_max_u_cache()

    def reset_to_initial_state(self) -> None:
        """Reset runtime state arrays to the initial virgin state."""
        self.restore(self._initial_state_snapshot)

    def revert_quad(self, quad: Any) -> None:
        index = int(quad.spring._histra_quad_batch_index)
        row = self.quad_state[index]
        if isinstance(quad.spring, SpringHysteretic):
            _revert_hysteretic_quad(row)
            self._write_quad_object(index, quad.spring)
            return
        _quad_revert_trial(row)
        # Preserve the C# ordering in Quad.revertToLastCommit: trial normal
        # stress is restored first, then committed normal stress rolls back to
        # its previous committed value.
        row[QCSTRESS_NORMAL] = row[QCSTRESS_NORMAL_PREV]
        self._write_quad_object(index, quad.spring)

    def revert_interface(self, interface: Any) -> None:
        start, stop = interface._perf_hysteretic_slice
        self.trial[start:stop, 0] = self.committed[start:stop, 0]
        self.trial[start:stop, 1] = self.committed[start:stop, 1]
        self.trial[start:stop, 2] = self.committed[start:stop, 2]
        self.trial[start:stop, 3] = self.committed[start:stop, 3]
        self.trial[start:stop, 4] = self.committed[start:stop, 4]
        self.trial[start:stop, 5] = self.committed[start:stop, 5]
        self.trial[start:stop, 6] = self.committed[start:stop, 6]
        self.trial[start:stop, 7] = self.committed[start:stop, 7]
        self.trial[start:stop, 8] = self.committed[start:stop, 8]
        self.targets[start:stop] = self.committed[start:stop, 7]
        record_index = self._record_by_id[id(interface)]
        for spring_index in (
            int(self._slid_index[record_index]),
            int(self._oop0_index[record_index]),
            int(self._oop1_index[record_index]),
        ):
            if spring_index < 0:
                continue
            spring = self.coulomb_springs[spring_index]
            # Use the object's exact C# lifecycle implementation for this rare
            # rollback path, then refresh the dense representation.
            self._write_coulomb_object(spring_index, spring)
            spring.revert_to_last_commit()
            self._read_coulomb_object(spring_index, spring)
            self.coulomb_targets[spring_index] = float(spring._cstrain)
        self.sync_interface_trial_to_objects(interface)
        self._objects_trial_synced = False


def build_hysteretic_batch(model: Any) -> HystereticBatchRuntime | None:
    """Return an active batch runtime, or ``None`` for a safe Python fallback."""
    disabled = os.environ.get("HISTRA_DISABLE_COMPILED_SPRINGS", "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return None
    if _evaluate_linear_batch is None:
        return None
    runtime = HystereticBatchRuntime(model)
    return runtime if runtime.active else None
