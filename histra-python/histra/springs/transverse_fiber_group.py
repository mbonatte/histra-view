"""Array-backed transverse fiber group and on-demand spring proxy.

This module provides ``TransverseFiberGroup``, an array-backed contiguous
container for the hundreds of thousands of transverse fiber springs generated
across masonry interfaces.  Instead of allocating individual Python dataclass
objects and nested lists for every fiber during preprocessing, all parameters,
initial stiffnesses, areas, and constitutive states are stored in contiguous
NumPy arrays.

For compatibility with tests and inspection tools, ``TransverseFiberGroup``
implements the standard Python ``MutableSequence`` interface and instantiates
transparent ``SpringHysteretic`` proxy objects strictly on demand.
"""

from __future__ import annotations

from collections.abc import MutableSequence
from typing import Any, Iterator, Sequence
import numpy as np

from histra.types.phase_enum import PhaseEnum
from histra.springs.base import Spring
from histra.springs.hysteretic import SpringHysteretic

_PHASE_BY_CODE = {code: PhaseEnum(code) for code in range(11)}
_CODE_BY_PHASE = {p: int(p) for p in PhaseEnum}



class TransverseFiberGroup(MutableSequence):
    """Contiguous array-backed storage for an interface's transverse fibers."""

    __slots__ = (
        "_params",
        "_k",
        "_area",
        "tensile_curve_type",
        "compressive_curve_type",
        "_tensile_curve_types",
        "_compressive_curve_types",
        "parent_key",
        "betap",
        "betan",
        "_committed",
        "_trial",
        "is_on",
        "_histra_batch_managed",
        "_batch_slice",
        "_cache",
        "_fy",
        "_uy_corr",
        "_f0",
        "_kt",
        "_ur",
        "alfar_p",
        "alfar_n",
    )

    def __init__(
        self,
        params: np.ndarray,
        k: np.ndarray,
        area: np.ndarray,
        tensile_curve_type: str = "LinearSoftening",
        compressive_curve_type: str = "LinearSoftening",
        parent_key: int = 0,
        betap: float = 0.0,
        betan: float = 0.0,
        tensile_curve_types: Sequence[str] | None = None,
        compressive_curve_types: Sequence[str] | None = None,
        fy: np.ndarray | None = None,
        kt: np.ndarray | None = None,
        ur: np.ndarray | None = None,
        alfar: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self._params = np.ascontiguousarray(params, dtype=np.float64)
        self._k = np.ascontiguousarray(k, dtype=np.float64)
        self._area = np.ascontiguousarray(area, dtype=np.float64)
        self.tensile_curve_type = str(tensile_curve_type)
        self.compressive_curve_type = str(compressive_curve_type)
        self._tensile_curve_types = (
            tuple(tensile_curve_types) if tensile_curve_types is not None else None
        )
        self._compressive_curve_types = (
            tuple(compressive_curve_types) if compressive_curve_types is not None else None
        )
        self.parent_key = int(parent_key)
        self.betap = float(betap)
        self.betan = float(betan)
        self._fy = np.ascontiguousarray(fy, dtype=np.float64) if fy is not None else None
        self._uy_corr: np.ndarray | None = None
        self._f0: np.ndarray | None = None
        self._kt = np.ascontiguousarray(kt, dtype=np.float64) if kt is not None else None
        self._ur = np.ascontiguousarray(ur, dtype=np.float64) if ur is not None else None
        self.alfar_p = float(alfar[0])
        self.alfar_n = float(alfar[1])

        n = len(self._k)
        self._committed = np.zeros((n, 9), dtype=np.float64)
        self._trial = np.zeros((n, 10), dtype=np.float64)
        e1p = self._params[:, 13] if self._params.shape[1] > 13 else None
        if e1p is not None:
            self._trial[:, 9] = np.where(e1p != 0.0, e1p, self._k)
        else:
            self._trial[:, 9] = self._k

        self.is_on = np.ones(n, dtype=bool)
        self._histra_batch_managed = False
        self._batch_slice: tuple[int, int] | None = None
        self._cache: dict[int, SpringHysteretic] = {}

    @property
    def is_batch_backed(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self._k)

    def __bool__(self) -> bool:
        return len(self._k) > 0

    def _materialize_proxy(self, index: int) -> SpringHysteretic:
        sp = SpringHysteretic.__new__(SpringHysteretic)
        sp.type_of = "HiStrA.Objects.SpringHysteretic"
        sp.extra = {}
        sp.key = index
        sp.parent_key = self.parent_key
        sp.parent_type = "Interface"
        sp.spring_purpose = "Transversal1"
        sp.type_name = ""
        sp.area = float(self._area[index])
        sp.length = 0.0
        sp.k = float(self._k[index])
        sp.k_tang = float(self._trial[index, 9])
        sp.f = float(self._trial[index, 6])
        sp.u = float(self._trial[index, 7])
        sp.is_on = bool(self.is_on[index])

        code_c = int(self._committed[index, 8])
        sp.phase = _PHASE_BY_CODE.get(code_c, PhaseEnum.Elastic)
        code_t = int(self._trial[index, 8])
        sp.t_phase = _PHASE_BY_CODE.get(code_t, PhaseEnum.Elastic)
        sp._histra_batch_managed = self._histra_batch_managed

        p = self._params[index]
        sp.rot1p = float(p[0])
        sp.mom1p = float(p[1])
        sp.rot2p = float(p[2])
        sp.mom2p = float(p[3])
        sp.rot3p = float(p[4])
        sp.mom3p = float(p[5])
        sp.mom1n = float(p[6])
        sp.rot1n = float(p[7])
        sp.rot2n = float(p[8])
        sp.mom2n = float(p[9])
        sp.rot3n = float(p[10])
        sp.mom3n = float(p[11])
        sp.e1n = float(p[12])
        sp.e1p = float(p[13])
        sp.e2n = float(p[14])
        sp.e2p = float(p[15])
        sp.e3n = float(p[16])
        sp.e3p = float(p[17])
        sp.eun = float(p[18])
        sp.eup = float(p[19])

        sp.pinch_xp = 0.0
        sp.pinch_yp = 0.0
        sp.pinch_xn = 0.0
        sp.pinch_yn = 0.0
        sp.damfc1p = 0.0
        sp.damfc2p = 0.0
        sp.damfc1n = 0.0
        sp.damfc2n = 0.0
        sp.betap = self.betap
        sp.betan = self.betan

        sp.energy_a = 0.5 * (
            p[0] * p[1]
            + (p[2] - p[0]) * (p[3] + p[1])
            + (p[4] - p[2]) * (p[5] + p[3])
            + p[7] * p[6]
            + (p[8] - p[7]) * (p[9] + p[6])
            + (p[10] - p[8]) * (p[11] + p[9])
        )

        sp.tensile_curve_type = (
            self._tensile_curve_types[index]
            if self._tensile_curve_types is not None
            else self.tensile_curve_type
        )
        sp.compressive_curve_type = (
            self._compressive_curve_types[index]
            if self._compressive_curve_types is not None
            else self.compressive_curve_type
        )

        if self._fy is not None:
            sp.fy = [float(self._fy[index, 0]), float(self._fy[index, 1])]
        else:
            sp.fy = [float(p[1]), float(p[6])]
        if self._kt is not None:
            sp.kt = [float(self._kt[index, 0]), float(self._kt[index, 1])]
        else:
            sp.kt = [float(p[15]), float(p[14])]
        if self._ur is not None:
            sp.ur = [float(self._ur[index, 0]), float(self._ur[index, 1])]
        else:
            sp.ur = [float(p[2]), float(p[8])]
        sp.alfau = [self.betap, self.betan]
        sp.alfar = [self.alfar_p, self.alfar_n]
        sp.umax = [float(self._committed[index, 0]), float(self._committed[index, 1])]
        sp.uy_corr = (
            self._uy_corr[index].tolist() if self._uy_corr is not None
            else [value / sp.k if sp.k else 0.0 for value in sp.fy]
        )
        sp.f0 = float(self._f0[index]) if self._f0 is not None else 0.0
        sp.f0_target = 0.0
        sp.kstrain = 0.0
        sp.cenergy_d = float(self._committed[index, 4])
        sp.k_tang = float(self._trial[index, 9])
        sp.k_tang_committed = float(self._trial[index, 9])
        sp._crot_pu = float(self._committed[index, 2])
        sp._crot_nu = float(self._committed[index, 3])
        sp._cload_indicator = int(self._committed[index, 5])
        sp._cstress = float(self._committed[index, 6])
        sp._cstrain = float(self._committed[index, 7])

        sp._trot_max = float(self._trial[index, 0])
        sp._trot_min = float(self._trial[index, 1])
        sp._trot_pu = float(self._trial[index, 2])
        sp._trot_nu = float(self._trial[index, 3])
        sp._tenergy_d = float(self._trial[index, 4])
        sp._tload_indicator = int(self._trial[index, 5])
        sp._tstress = float(self._trial[index, 6])
        sp._tstrain = float(self._trial[index, 7])

        self._cache[index] = sp
        return sp

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        idx = int(index)
        n = len(self._k)
        if idx < 0:
            idx += n
        if idx < 0 or idx >= n:
            raise IndexError(f"TransverseFiberGroup index out of range: {index}")
        cached = self._cache.get(idx)
        if cached is not None:
            return cached
        return self._materialize_proxy(idx)

    def __setitem__(self, index: Any, value: Any) -> None:
        idx = int(index)
        n = len(self._k)
        if idx < 0:
            idx += n
        if idx < 0 or idx >= n:
            raise IndexError(f"TransverseFiberGroup index out of range: {index}")
        self._cache[idx] = value
        if hasattr(value, "k"):
            self._k[idx] = float(value.k)
        if hasattr(value, "area"):
            self._area[idx] = float(value.area)
        if hasattr(value, "is_on"):
            self.is_on[idx] = bool(value.is_on)

    def __delitem__(self, index: Any) -> None:
        raise NotImplementedError("TransverseFiberGroup does not support deletion")

    def insert(self, index: int, value: Any) -> None:
        raise NotImplementedError("TransverseFiberGroup does not support insertion")

    def __iter__(self) -> Iterator[SpringHysteretic]:
        for i in range(len(self)):
            yield self[i]

    def __repr__(self) -> str:
        return f"<TransverseFiberGroup n={len(self)} parent={self.parent_key}>"

    def transverse_rejection_reason(self) -> str:
        if self._cache:
            for sp in self._cache.values():
                if getattr(sp, "tensile_curve_type", "") not in {
                    "LinearHardening", "LinearSoftening", "Exponential", "Elastic"
                }:
                    return "unsupported_tensile_curve_type"
                if getattr(sp, "compressive_curve_type", "") not in {
                    "LinearHardening", "LinearSoftening", "Elastic", "Parabolic"
                }:
                    return "unsupported_compressive_curve_type"

        if self._tensile_curve_types is not None:
            for t_curve in self._tensile_curve_types:
                if t_curve not in {
                    "LinearHardening", "LinearSoftening", "Exponential", "Elastic"
                }:
                    return "unsupported_tensile_curve_type"
        else:
            if self.tensile_curve_type not in {
                "LinearHardening", "LinearSoftening", "Exponential", "Elastic"
            }:
                return "unsupported_tensile_curve_type"

        if self._compressive_curve_types is not None:
            for c_curve in self._compressive_curve_types:
                if c_curve not in {
                    "LinearHardening", "LinearSoftening", "Elastic", "Parabolic"
                }:
                    return "unsupported_compressive_curve_type"
        else:
            if self.compressive_curve_type not in {
                "LinearHardening", "LinearSoftening", "Elastic", "Parabolic"
            }:
                return "unsupported_compressive_curve_type"
        return ""

    def get_k_array(self, alfa: float, count: int) -> np.ndarray:
        c = min(count, len(self._k))
        k = self._k[:c]
        kt = self._trial[:c, 9]
        if alfa == 0.0:
            return k.copy()
        return k + (kt - k) * alfa

    def compute_area_corr(self, excluded_phases: set[PhaseEnum] | None = None) -> float:
        if excluded_phases is None:
            excluded_phases = {
                PhaseEnum.Rupture,
                PhaseEnum.RuptureComp,
                PhaseEnum.RuptureTraz,
                PhaseEnum.Plastic_t,
            }
        excluded_codes = np.fromiter(
            (_CODE_BY_PHASE.get(p, -1) for p in excluded_phases),
            dtype=np.int32,
            count=len(excluded_phases),
        )
        mask = ~np.isin(self._committed[:, 8].astype(np.int32), excluded_codes)
        return float(np.sum(self._area[mask]))

    def sum_force_f32(self) -> np.float32:
        f32 = np.float32
        tot = f32(0.0)
        forces = self._committed[:, 6].astype(np.float32)
        for i in range(len(forces)):
            tot = f32(tot + forces[i])
        return tot

    def sync_from_dense(self, committed: np.ndarray, trial: np.ndarray) -> None:
        """Update committed and trial state arrays from the solver runtime."""
        self._committed[:] = committed
        self._trial[:] = trial

        # If any springs were materialized in the cache, update their attributes
        if self._cache:
            for idx, sp in self._cache.items():
                c = self._committed[idx]
                t = self._trial[idx]
                sp.umax[0] = float(c[0])
                sp.umax[1] = float(c[1])
                sp._crot_pu = float(c[2])
                sp._crot_nu = float(c[3])
                sp.cenergy_d = float(c[4])
                sp._cload_indicator = int(c[5])
                sp._cstress = float(c[6])
                sp._cstrain = float(c[7])
                sp.phase = _PHASE_BY_CODE.get(int(c[8]), PhaseEnum.Elastic)

                sp._trot_max = float(t[0])
                sp._trot_min = float(t[1])
                sp._trot_pu = float(t[2])
                sp._trot_nu = float(t[3])
                sp._tenergy_d = float(t[4])
                sp._tload_indicator = int(t[5])
                sp._tstress = float(t[6])
                sp._tstrain = float(t[7])
                sp.t_phase = _PHASE_BY_CODE.get(int(t[8]), PhaseEnum.Elastic)
                sp.k_tang = float(t[9])
                sp.k_tang_committed = float(t[9])
                sp.f = float(t[6])
                sp.u = float(t[7])

    def sync_tangents_from_dense(self, k_tang: np.ndarray) -> None:
        """Update tangent stiffness from the solver runtime."""
        self._trial[:, 9] = k_tang
        if self._cache:
            for idx, sp in self._cache.items():
                sp.k_tang = float(self._trial[idx, 9])
                sp.k_tang_committed = float(self._trial[idx, 9])

    def sync_trial_from_dense(self, trial: np.ndarray) -> None:
        """Update trial state from the solver runtime."""
        self._trial[:] = trial
        if self._cache:
            for idx, sp in self._cache.items():
                t = self._trial[idx]
                sp._trot_max = float(t[0])
                sp._trot_min = float(t[1])
                sp._trot_pu = float(t[2])
                sp._trot_nu = float(t[3])
                sp._tenergy_d = float(t[4])
                sp._tload_indicator = int(t[5])
                sp._tstress = float(t[6])
                sp._tstrain = float(t[7])
                sp.t_phase = _PHASE_BY_CODE.get(int(t[8]), PhaseEnum.Elastic)
                sp.k_tang = float(t[9])
                sp.k_tang_committed = float(t[9])
                sp.f = float(t[6])
                sp.u = float(t[7])

    def copy_committed_state_from(self, source: TransverseFiberGroup) -> None:
        """Match SetSpring(false) at a committed material-change boundary.

        New envelope parameters remain on the target. Native DB restoration
        retains the predecessor tangent, yield forces/coordinates and F0.
        Python additionally preserves cumulative energy, as in scalar transfer.
        """
        self._committed[:] = source._committed
        self._trial[:, :9] = source._committed[:, :9]
        self._trial[:, 9] = source._trial[:, 9]
        self._copy_committed_metadata(source)
        self.is_on[:] = source.is_on
        if self._cache:
            self._cache.clear()

    def _copy_committed_metadata(self, source: TransverseFiberGroup) -> None:
        self._fy = (source._fy if source._fy is not None else source._params[:, [1, 6]]).copy()
        self._uy_corr = (
            source._uy_corr.copy() if source._uy_corr is not None
            else np.divide(self._fy, source._k[:, None], out=np.zeros_like(self._fy),
                           where=source._k[:, None] != 0.0)
        )
        self._f0 = source._f0.copy() if source._f0 is not None else np.zeros(len(source))
        # Inspection/restart code can have populated a proxy's metadata.
        for index, spring in source._cache.items():
            self._fy[index] = spring.fy
            self._uy_corr[index] = spring.uy_corr
            self._f0[index] = spring.f0
            self._trial[index, 9] = spring.k_tang_committed
