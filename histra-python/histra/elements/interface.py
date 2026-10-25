from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, List, Tuple
import numpy as np
from histra.types.point import Point
from histra.types.afference_entry import AfferenceEntry
from histra.elements.interface_state import InterfaceState, _list2d
from histra.types.phase_enum import PhaseEnum


_STIFFNESS_GRID_FACTOR_CACHE: dict[
    tuple[int, int, int], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
] = {}


def _stiffness_grid_factors(
    nrow: int, ncol: int, count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return immutable interpolation factors in scalar C# operation order."""
    nrow = max(int(nrow), 1)
    ncol = max(int(ncol), 1)
    key = (nrow, ncol, int(count))
    cached = _STIFFNESS_GRID_FACTOR_CACHE.get(key)
    if cached is not None:
        return cached

    one_minus_xi = np.empty(count, dtype=np.float64)
    one_plus_xi = np.empty(count, dtype=np.float64)
    one_minus_eta = np.empty(count, dtype=np.float64)
    one_plus_eta = np.empty(count, dtype=np.float64)
    for index in range(count):
        row, col = divmod(index, ncol)
        xi = -1.0 + 2.0 / ncol * col + 1.0 / ncol
        eta = -1.0 + 2.0 / nrow * row + 1.0 / nrow
        one_minus_xi[index] = 1.0 - xi
        one_plus_xi[index] = 1.0 + xi
        one_minus_eta[index] = 1.0 - eta
        one_plus_eta[index] = 1.0 + eta
    cached = (one_minus_xi, one_plus_xi, one_minus_eta, one_plus_eta)
    _STIFFNESS_GRID_FACTOR_CACHE[key] = cached
    return cached


@dataclass
class Interface:
    key: int = 0
    node_keys: List[int] = field(default_factory=lambda: [0, 0])
    parent_element_key1: int = 0
    parent_element_key2: int = 0
    parent_type_element1: str = ""
    parent_type_element2: str = ""
    face1: int = 0
    face2: int = 0
    length: float = 0.0
    thickness: List[float] = field(default_factory=lambda: [0.0, 0.0])
    nrow: int = 3
    ncol: int = 3
    nspring: int = 9
    dim_aff: List[int] = field(default_factory=lambda: [6, 2, 4])
    dim_aff_tot: int = 12
    trasv_1: list = field(default_factory=list)  # Springs
    trasv_2: list = field(default_factory=list)
    slid: list = field(default_factory=list)
    slid_out_plan: list = field(default_factory=list)
    aff: List[List[AfferenceEntry]] = field(default_factory=lambda: [[] for _ in range(12)])
    reference_e1: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    reference_e2: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    reference_e3: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    reference_origin: Point = field(default_factory=Point)
    status: InterfaceState = field(default_factory=InterfaceState)
    name: str = ""
    material_key: int = 0
    layer_key: int = 0
    interfaccia_vincolata: bool = False
    frot: int = 0
    imax: int = 400
    csi: float = 0.0
    vint2d: List[Point] = field(default_factory=lambda: [Point(), Point(), Point(), Point()])
    vint3d: List[Point] = field(default_factory=lambda: [Point(), Point(), Point(), Point()])
    # Local 12-DOF resisting-force vector (port of ComputationalElement.F)
    f: List[float] = field(default_factory=lambda: [0.0] * 12)

    # Geometry/afference and scalar-update caches. These are built lazily after
    # XML loading and deliberately excluded from serialized/rollback state.
    _perf_di: tuple[float, ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_dj: tuple[float, ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_ecc: tuple[float, ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_aff_pairs: tuple[tuple[tuple[int, float], ...], ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_area: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_dist: tuple[float, float] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_dist_for: tuple[float, float] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_local_du: list[float] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_inv_length: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_half_length: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_constrained: bool | None = field(default=None, init=False, repr=False, compare=False)
    _perf_d0: int | None = field(default=None, init=False, repr=False, compare=False)
    _perf_d1: int | None = field(default=None, init=False, repr=False, compare=False)
    _perf_custom_force_access: tuple[bool, ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_has_custom_force_access: bool | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_di2: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_dj2: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_didj: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_ecc2: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_djecc: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_diecc: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_dm: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_sum_dm2: float | None = field(default=None, init=False, repr=False, compare=False)

    def area(self) -> float:
        """Return the cached C# ``Operations.Area(VInt2D)`` polygon area."""
        if self._perf_area is not None:
            return self._perf_area
        pts = self.vint2d
        if len(pts) < 3:
            return 0.0
        # XNA ``Vector2`` and ``Operations.Area`` accumulate in ``float``.
        # Preserve those single-precision boundaries because normal-stress
        # dependent friction is path-sensitive after the first elastic step.
        twice = np.float32(0.0)
        for index, point in enumerate(pts):
            nxt = pts[(index + 1) % len(pts)]
            cross = np.float32(
                np.float32(point.x) * np.float32(nxt.y)
                - np.float32(nxt.x) * np.float32(point.y)
            )
            twice = np.float32(twice + cross)
        self._perf_area = float(abs(np.float32(twice * np.float32(0.5))))
        return self._perf_area

    def _linear_normal_projection(self, ls):
        if ls is None or not hasattr(ls, "x"):
            raise ValueError("NR=False requires a linear system with its current x correction")
        if len(self.aff) < 6:
            raise ValueError("NR=False requires six flexural afference rows")
        rows = self.aff[:6]
        offsets = np.r_[0, np.cumsum([len(row) for row in rows])].astype(np.int64)
        gdls = np.fromiter((entry.gdl - 1 for row in rows for entry in row), dtype=np.int64)
        coefficients = np.fromiter((entry.alfa for row in rows for entry in row), dtype=np.float64)
        return (np.asarray(ls.x, dtype=np.float64), offsets, gdls, coefficients,
                float(self.length), self.interfaccia_vincolata_computed())

    def compute_flex_def(self, ls) -> tuple[float, float, float]:
        """Original ComputeFlexdef, using the current global correction only."""
        from histra.solver.hysteretic_kernels.kinematics import _interface_flex_from_global
        if _interface_flex_from_global is None:
            raise RuntimeError("ComputeFlexdef requires the compiled Numba backend")
        return _interface_flex_from_global(*self._linear_normal_projection(ls))

    def compute_dn(self, ls: Any = None, nr: bool = False) -> float:
        """Port of C# ``Interface.ComputeDN``.

        The nonlinear Newton path passes ``NR=True``;
        in that path the normal-force increment is the negative sum of the
        transverse springs' incremental forces.
        With ``NR=False``, project the current global correction and apply
        the current local flexural stiffness, as in C# ComputeFlexdef.
        """
        if nr:
            result = 0.0
            for spring in self.trasv_1:
                result -= float(spring.get_incr_force())
            return result
        from histra.solver.hysteretic_kernels.kinematics import _interface_linear_normal_increment
        if _interface_linear_normal_increment is None:
            raise RuntimeError("NR=False requires the compiled Numba backend")
        k = np.asarray(self.status.k, dtype=np.float64)
        if k.shape != (6, 6):
            raise ValueError("NR=False requires the current 6-by-6 flexural stiffness block")
        return float(_interface_linear_normal_increment(*self._linear_normal_projection(ls), k))

    def compute_area_corr(self) -> float:
        """Port of the contact-area sum used by Coulomb sliding springs."""
        if hasattr(self.trasv_1, "compute_area_corr"):
            return self.trasv_1.compute_area_corr()
        excluded = {
            PhaseEnum.Rupture,
            PhaseEnum.RuptureComp,
            PhaseEnum.RuptureTraz,
            PhaseEnum.Plastic_t,
        }
        return sum(float(s.area) for s in self.trasv_1 if s.phase not in excluded)

    def interfaccia_vincolata_computed(self) -> bool:
        """Port of .NET InterfacciaVincolata(): True if either parent is a Restraint."""
        return self.parent_type_element1 == "Restraint" or self.parent_type_element2 == "Restraint"

    # ═════════════════════════════════════════════════════════════════════════
    # Geometry helpers  (port of Interface geometry methods)
    # ═════════════════════════════════════════════════════════════════════════

    def idx(self, row: int, col: int) -> int:
        """Port of Interface.idx(riga, colonna) = riga * Ncol + colonna."""
        return row * self.ncol + col

    def get_di(self, row: int, index: int) -> float:
        """Port of Interface.Getdi(row, index).

        Bilinear interpolation of VInt2D.X over the master-element face.
        """
        nrow = max(self.nrow, 1)
        ncol = max(self.ncol, 1)
        xi = -1.0 + 2.0 / ncol * index + 1.0 / ncol
        eta = -1.0 + 2.0 / nrow * row + 1.0 / nrow
        v = self.vint2d
        return (
            v[0].x * (1.0 - xi) * (1.0 - eta) / 4.0
            + v[1].x * (1.0 + xi) * (1.0 - eta) / 4.0
            + v[2].x * (1.0 + xi) * (1.0 + eta) / 4.0
            + v[3].x * (1.0 - xi) * (1.0 + eta) / 4.0
        )

    def get_dj(self, row: int, index: int) -> float:
        """Port of Interface.Getdj(row, index) = Length - Getdi(row, index)."""
        return self.length - self.get_di(row, index)

    def get_dm(self, row: int, index: int) -> float:
        """Port of Interface.Getdm(row, index) = 0.5*Length - Getdi(row, index)."""
        return 0.5 * self.length - self.get_di(row, index)

    def geometry_spring(self, row: int, index: int) -> Tuple[float, float, float]:
        """Port of Interface.GeometrySpring(row, index, di, dj, dm)."""
        di = self.get_di(row, index)
        dj = self.get_dj(row, index)
        dm = self.get_dm(row, index)
        return di, dj, dm

    def ecc_spring(self, row: int, index: int) -> float:
        """Port of Interface.EccSpring(row, index).

        Bilinear interpolation of VInt2D.Y over the master-element face.
        """
        nrow = max(self.nrow, 1)
        ncol = max(self.ncol, 1)
        xi = -1.0 + 2.0 / ncol * index + 1.0 / ncol
        eta = -1.0 + 2.0 / nrow * row + 1.0 / nrow
        v = self.vint2d
        return (
            v[0].y * (1.0 - xi) * (1.0 - eta) / 4.0
            + v[1].y * (1.0 + xi) * (1.0 - eta) / 4.0
            + v[2].y * (1.0 + xi) * (1.0 + eta) / 4.0
            + v[3].y * (1.0 - xi) * (1.0 + eta) / 4.0
        )

    def _ensure_stiffness_geometry_cache(self) -> None:
        """Cache spring-point geometry used repeatedly by stiffness assembly.

        The values depend only on interface geometry/topology, not on spring
        constitutive state.  Keeping this cache separate from the broader
        update-domain cache lets ``compute_k`` reuse geometry without forcing
        unrelated afference/work-buffer initialization.
        """
        count = min(max(0, self.nrow * self.ncol), len(self.trasv_1))
        if (
            self._perf_di is not None
            and self._perf_dj is not None
            and self._perf_ecc is not None
            and self._perf_sum_di2 is not None
            and len(self._perf_di) == count
            and len(self._perf_dj) == count
            and len(self._perf_ecc) == count
        ):
            return

        one_minus_xi, one_plus_xi, one_minus_eta, one_plus_eta = (
            _stiffness_grid_factors(self.nrow, self.ncol, count)
        )
        v0, v1, v2, v3 = self.vint2d
        # Preserve scalar multiply/divide/add ordering exactly; precomputing a
        # single bilinear weight changes the final bits for some geometries.
        di_values = (
            ((v0.x * one_minus_xi) * one_minus_eta) / 4.0
            + ((v1.x * one_plus_xi) * one_minus_eta) / 4.0
            + ((v2.x * one_plus_xi) * one_plus_eta) / 4.0
            + ((v3.x * one_minus_xi) * one_plus_eta) / 4.0
        )
        ecc_values = (
            ((v0.y * one_minus_xi) * one_minus_eta) / 4.0
            + ((v1.y * one_plus_xi) * one_minus_eta) / 4.0
            + ((v2.y * one_plus_xi) * one_plus_eta) / 4.0
            + ((v3.y * one_minus_xi) * one_plus_eta) / 4.0
        )
        dj_values = self.length - di_values
        self._perf_di = tuple(di_values.tolist())
        self._perf_dj = tuple(dj_values.tolist())
        self._perf_ecc = tuple(ecc_values.tolist())

        self._perf_sum_di2 = float(np.sum(di_values * di_values))
        self._perf_sum_dj2 = float(np.sum(dj_values * dj_values))
        self._perf_sum_didj = float(np.sum(di_values * dj_values))
        self._perf_sum_ecc2 = float(np.sum(ecc_values * ecc_values))
        self._perf_sum_djecc = float(np.sum(dj_values * ecc_values))
        self._perf_sum_diecc = float(np.sum(di_values * ecc_values))

        dm_values = 0.5 * self.length - di_values
        self._perf_sum_dm = float(np.sum(dm_values))
        self._perf_sum_dm2 = float(np.sum(dm_values * dm_values))

    def _ensure_performance_cache(self) -> None:
        """Build immutable geometry and afference tuples once per interface."""
        self._ensure_stiffness_geometry_cache()
        if self._perf_aff_pairs is not None:
            return

        count = len(self._perf_di or ())
        self._perf_aff_pairs = tuple(
            tuple((entry.gdl - 1, float(entry.alfa)) for entry in (
                self.aff[local_dof] if local_dof < len(self.aff) else ()
            ))
            for local_dof in range(self.dim_aff_tot)
        )
        self._perf_dist = self.compute_dist_spring()
        self._perf_dist_for = self.compute_dist_spring_for(self)
        self._perf_local_du = [0.0] * self.dim_aff_tot
        self._perf_inv_length = 1.0 / self.length
        self._perf_half_length = 0.5 * self.length
        self._perf_constrained = self.interfaccia_vincolata_computed()
        self._perf_d0 = self.dim_aff[0] if self.dim_aff else 6
        self._perf_d1 = self.dim_aff[1] if len(self.dim_aff) > 1 else 2
        self._perf_custom_force_access = tuple(
            False
            if getattr(spring, "_histra_batch_managed", False)
            else not hasattr(spring, "_tstress")
            for spring in self.trasv_1[:count]
        )
        self._perf_has_custom_force_access = any(self._perf_custom_force_access)

    def _local_increment(self, x: np.ndarray) -> list[float]:
        self._ensure_performance_cache()
        assert self._perf_aff_pairs is not None
        assert self._perf_local_du is not None
        size = len(x)
        out = self._perf_local_du
        for i, pairs in enumerate(self._perf_aff_pairs):
            total = 0.0
            for gdl, coefficient in pairs:
                if 0 <= gdl < size:
                    total += x[gdl] * coefficient
            out[i] = total
        return out

    # ── ComputeDistSpring (two overloads) ───────────────────────────────────

    def compute_dist_spring(self) -> Tuple[float, float]:
        """Compute distance distribution factors *di*, *dj*.

        Port of ``ComputeDistSpring(out double di, out double dj)``
        (the parameterless overload that uses *this*).
        """
        di = self._compute_di_from_geometry(self)
        dj = 1.0 - di
        return di, dj

    def compute_dist_spring_for(self, intf: Interface) -> Tuple[float, float]:
        """Port of ``ComputeDistSpring(Interface I, ref double di, ref double dj)``.

        The protected virtual overload that takes an explicit Interface argument.
        If either parent is Fiber and the other is not, *di* = 0.5.
        """
        is_fiber1 = self.parent_type_element1 == "Fiber"
        is_fiber2 = self.parent_type_element2 == "Fiber"
        if (is_fiber1 and not is_fiber2) or (is_fiber2 and not is_fiber1):
            di = 0.5
        else:
            di = self._compute_di_from_geometry(intf)
        dj = 1.0 - di
        return di, dj

    def _compute_di_from_geometry(self, intf: Interface) -> float:
        """Helper: compute *di* from plate theory (port of the else-branch).

        Uses ``intf.thickness[0]`` and ``intf.length``.
        """
        t = intf.thickness[0]
        L = intf.length
        num = min(t, L)
        num2 = max(t, L)
        if num <= 0.0:
            return 0.5
        # C# stores this intermediate in a System.Single before taking the
        # square root.  Preserve that precision loss: it changes the
        # out-of-plane sliding interpolation and therefore its stiffness.
        x_val = float(np.float32(3.0 * num2 / (num * (num2 / num - 0.63))))
        # Operations.sqrt returns Single, so round the result as well as
        # its input before the following double-precision division.
        x_val = float(np.float32(math.sqrt(x_val)))
        num3 = 2.0 * num / x_val
        return 0.5 - 0.5 * num3 / L

    # ═════════════════════════════════════════════════════════════════════════
    # ComputeK storage  (port of Interface.ComputeK / ComputeKfless / etc.)
    # ═════════════════════════════════════════════════════════════════════════

    def compute_k(self, alfa: float = 0.0) -> None:
        """Port of Interface.ComputeK(double alfa).

        Computes and stores the three stiffness blocks into *status*.
        """
        self._compute_kfless(alfa)
        self._compute_kslid(alfa)
        self._compute_kslid_out_plan(alfa)

    # ── ComputeKflessNoInteract ─────────────────────────────────────────────

    def _compute_kfless(self, alfa: float) -> None:
        """Port of ComputeKflessNoInteract (ComputeKfless for Ngroup == 1).

        Builds the 6×6 (or 4×4 + coupling) flexural stiffness matrix.
        """
        I = self  # alias for readability, matching C# convention
        d0 = I.dim_aff[0] if len(I.dim_aff) > 0 else 6
        K = _list2d(d0, d0) if d0 > 4 else _list2d(6, 6)

        nrow = max(I.nrow, 1)
        ncol = max(I.ncol, 1)
        I._ensure_stiffness_geometry_cache()
        assert I._perf_di is not None
        assert I._perf_dj is not None
        assert I._perf_ecc is not None
        di_cache = I._perf_di
        dj_cache = I._perf_dj
        ecc_cache = I._perf_ecc

        spring_count = min(nrow * ncol, len(I.trasv_1))
        if spring_count == 0:
            self.status.k = K
            return

        if hasattr(I.trasv_1, "get_k_array"):
            k_arr = I.trasv_1.get_k_array(alfa, spring_count)
            spring_k = k_arr.tolist()
        else:
            spring_k = [I.trasv_1[index].get_k(alfa) for index in range(spring_count)]

        L = I.length
        L2 = L * L
        constrained = I.interfaccia_vincolata_computed()
        d2 = I.dim_aff[2] if len(I.dim_aff) > 2 else 4

        out_of_plane_diag = 0.0
        num7 = 0.0
        num8 = 0.0

        num = num2 = num3 = 0.0
        for i in range(nrow):
            row_offset = i * ncol
            for j in range(ncol):
                idx_ = row_offset + j
                if idx_ >= spring_count:
                    continue
                di = di_cache[idx_]
                dj = dj_cache[idx_]
                k = spring_k[idx_]
                num += k * di * di
                num3 += k * di * dj
                num2 += k * dj * dj

        if constrained:
            num4 = num5 = num6 = 0.0
            for i_ in range(ncol):
                for j_ in range(nrow):
                    idx_ = j_ * ncol + i_
                    if idx_ >= spring_count:
                        continue
                    di = di_cache[idx_]
                    dm = 0.5 * I.length - di
                    k = spring_k[idx_]
                    num4 += k
                    num5 -= k * dm
                    num6 += k * dm * dm

        if d2 > 0:
            for i_ in range(ncol):
                for j_ in range(nrow):
                    idx_ = j_ * ncol + i_
                    if idx_ >= spring_count:
                        continue
                    k = spring_k[idx_]
                    di = di_cache[idx_]
                    dj = dj_cache[idx_]
                    ecc = ecc_cache[idx_]
                    out_of_plane_diag += k * ecc * ecc
                    num7 += k * dj * ecc
                    num8 += k * di * ecc

        if L2 > 1e-30:
            num /= L2
            num3 /= L2
            num2 /= L2

        if constrained:
            K[0][0] = num4
            K[0][1] = num5
            K[1][1] = num6
            K[0][2] = -num - num3
            K[0][3] = -num3 - num2
            K[1][2] = num3 * L / 2.0 - num * L / 2.0
            K[1][3] = num2 * L / 2.0 - num3 * L / 2.0
            K[2][2] = num
            K[2][3] = num3
            K[3][3] = num2
        else:
            K[0][0] = num2
            K[0][1] = num3
            K[0][2] = -num3
            K[0][3] = -num2
            K[1][1] = num
            K[1][2] = -num
            K[1][3] = -num3
            K[2][2] = num
            K[2][3] = num3
            K[3][3] = num2

        # Symmetrise upper-left 4×4
        for i_ in range(4):
            for j_ in range(i_ + 1, 4):
                K[j_][i_] = K[i_][j_]

        if d2 <= 0:
            # Store and return
            self.status.k = K
            return

        # ── Out-of-plane coupling (DOFs 4,5) ────────────────────────────────

        K[4][4] = out_of_plane_diag
        K[5][5] = out_of_plane_diag
        K[4][5] = -out_of_plane_diag
        K[5][4] = -out_of_plane_diag

        if L > 1e-30:
            num7 /= L
            num8 /= L

        if not constrained:
            K[0][4] = -num7
            K[1][4] = -num8
            K[2][4] = num8
            K[3][4] = num7
            K[0][5] = num7
            K[1][5] = num8
            K[2][5] = -num8
            K[3][5] = -num7
        else:
            K[0][4] = -num7 - num8
            K[1][4] = (-num8 + num7) * L / 2.0
            K[2][4] = num8
            K[3][4] = num7
            K[0][5] = num7 + num8
            K[1][5] = (num8 - num7) * L / 2.0
            K[2][5] = -num8
            K[3][5] = -num7

        # Symmetrise coupling rows
        for i_ in range(4):
            K[4][i_] = K[i_][4]
            K[5][i_] = K[i_][5]

        self.status.k = K

    # ── ComputeKslid ────────────────────────────────────────────────────────

    def _compute_kslid(self, alfa: float) -> None:
        """Port of ComputeKslid — 2×2 in-plane sliding stiffness."""
        d1 = self.dim_aff[1] if len(self.dim_aff) > 1 else 2
        K = _list2d(d1, d1)
        if self.slid:
            k_val = self.slid[0].get_k(alfa)
            K[0][0] = k_val
            K[0][1] = -k_val
            K[1][0] = -k_val
            K[1][1] = k_val
        self.status.kslid = K

    # ── ComputeKslidOutPlan ─────────────────────────────────────────────────

    def _compute_kslid_out_plan(self, alfa: float) -> None:
        """Port the active C# ``TwoSprings`` out-of-plane branch.

        ``ModelOperations.CheckTorsionalModel`` is hard-coded to
        ``TypeModelTorsionEnum.TwoSprings`` in the supplied C# source.  The
        previous Python translation incorrectly used the alternative
        rotational-spring matrix, coupling otherwise unloaded out-of-plane
        generalized DOFs into the in-plane gravity response.
        """
        d2 = self.dim_aff[2] if len(self.dim_aff) > 2 else 4
        K = _list2d(d2, d2)
        if len(self.slid_out_plan) < 2:
            self.status.kslid_out_plan = K
            return

        if d2 == 4:
            di, dj = self.compute_dist_spring_for(self)
            k1 = self.slid_out_plan[0].get_k(alfa)
            k2 = self.slid_out_plan[1].get_k(alfa)
            K[0][0] = k1 * dj * dj + k2 * di * di
            K[0][1] = (k1 + k2) * di * dj
            K[0][2] = -k1 * dj * dj - k2 * di * di
            K[0][3] = -(k1 + k2) * di * dj
            K[1][0] = K[0][1]
            K[1][1] = k1 * di * di + k2 * dj * dj
            K[1][2] = -(k1 + k2) * di * dj
            K[1][3] = -k1 * di * di - k2 * dj * dj
            K[2][0] = K[0][2]
            K[2][1] = K[1][2]
            K[2][2] = K[0][0]
            K[2][3] = K[0][1]
            K[3][0] = K[0][3]
            K[3][1] = K[1][3]
            K[3][2] = K[2][3]
            K[3][3] = K[1][1]
        elif d2 == 6 and len(self.slid_out_plan) >= 4:
            values = [spring.get_k(alfa) for spring in self.slid_out_plan[:4]]
            K[0][0] = values[0] / self.length
            K[1][1] = values[1]
            K[2][2] = values[2] / self.length
            K[3][3] = values[3]
            K[0][4] = K[4][0] = -values[0]
            K[1][4] = K[4][1] = -values[1]
            K[4][4] = values[0] + values[1]
            K[2][5] = K[5][2] = -values[2]
            K[3][5] = K[5][3] = -values[3]
            K[5][5] = values[2] + values[3]
        else:
            raise NotImplementedError(
                f"Unsupported Interface out-of-plane afference size {d2}"
            )

        self.status.kslid_out_plan = K

    # ═════════════════════════════════════════════════════════════════════════
    # UpdateDomain  (port of Interface.UpdateDomain)
    # ═════════════════════════════════════════════════════════════════════════

    def update_domain(self, x: np.ndarray, state: Any) -> None:
        """Update local/interface spring trial state using cached geometry."""
        del state
        self._ensure_performance_cache()
        assert self._perf_di is not None
        assert self._perf_dj is not None
        assert self._perf_ecc is not None
        assert self._perf_inv_length is not None
        assert self._perf_half_length is not None
        assert self._perf_constrained is not None
        assert self._perf_d0 is not None
        assert self._perf_d1 is not None
        assert self._perf_custom_force_access is not None
        assert self._perf_has_custom_force_access is not None

        local_du = self._local_increment(x)
        status_u = self.status.u
        for i, pairs in enumerate(self._perf_aff_pairs or ()):
            for gdl, coefficient in pairs:
                if 0 <= gdl < len(x):
                    status_u[i] += float(x[gdl] * coefficient)

        if not self._perf_constrained:
            num = local_du[3] - local_du[0]
            num2 = local_du[2] - local_du[1]
        else:
            half_length = self._perf_half_length
            num = local_du[3] - (local_du[0] - local_du[1] * half_length)
            num2 = local_du[2] - (local_du[0] + local_du[1] * half_length)
        num3 = local_du[4]
        num4 = local_du[5]

        normal_increment = 0.0
        committed_normal_force = 0.0
        max_displacement = 0.0
        delta_flex = num4 - num3
        length = self.length
        if not self._perf_has_custom_force_access:
            # Standard translated springs expose their trial/committed values
            # directly. Avoid two instance-dictionary probes per fibre while
            # preserving the original spring and accumulation order exactly.
            for spring, di, dj, ecc in zip(
                self.trasv_1, self._perf_di, self._perf_dj, self._perf_ecc
            ):
                increment = (num * dj + num2 * di) / length - delta_flex * ecc
                new_u = spring.u + increment
                spring.u = new_u
                spring.set_trial_strain(new_u)
                trial = float(spring._tstress) if hasattr(spring, "_tstress") else float(spring.get_force())
                committed = float(spring._cstress) if hasattr(spring, "_cstress") else float(spring.get_committed_force())
                normal_increment -= float(spring.get_incr_force()) if hasattr(spring, "get_incr_force") else (trial - committed)
                committed_normal_force += trial - (trial - committed)
                abs_u = abs(new_u)
                if abs_u > max_displacement:
                    max_displacement = abs_u
        else:
            for spring, di, dj, ecc, custom_force_access in zip(
                self.trasv_1, self._perf_di, self._perf_dj, self._perf_ecc,
                self._perf_custom_force_access,
            ):
                increment = (num * dj + num2 * di) / length - delta_flex * ecc
                new_u = spring.u + increment
                spring.u = new_u
                spring.set_trial_strain(new_u)
                if custom_force_access:
                    trial = float(spring.get_force())
                    committed = trial - float(spring.get_incr_force())
                else:
                    trial = float(spring._tstress)
                    committed = float(spring._cstress)
                normal_increment -= trial - committed
                committed_normal_force += trial - (trial - committed)
                abs_u = abs(new_u)
                if abs_u > max_displacement:
                    max_displacement = abs_u

        self.status.normal_increment = normal_increment
        self.status.committed_normal_force = committed_normal_force

        d0 = self.dim_aff[0] if self.dim_aff else 6
        du_slid = local_du[d0] - local_du[d0 + 1]
        if self.slid:
            spring = self.slid[0]
            spring.u += float(du_slid)
            from histra.springs.coulomb03 import SpringCoulomb03
            if isinstance(spring, SpringCoulomb03):
                spring.dn = normal_increment
                if spring.check_contact_area:
                    spring.area_corrente = self.compute_area_corr()
            spring.set_trial_strain(spring.u)
            max_displacement = max(max_displacement, abs(float(spring.u)))

        d1 = self._perf_d1
        du_op_a = local_du[d0 + d1] - local_du[d0 + d1 + 2]
        du_op_b = local_du[d0 + d1 + 1] - local_du[d0 + d1 + 3]
        assert self._perf_dist_for is not None
        di_sop, dj_sop = self._perf_dist_for
        if len(self.slid_out_plan) >= 2:
            spring0, spring1 = self.slid_out_plan[0], self.slid_out_plan[1]
            spring0.u += float(du_op_a + (du_op_b - du_op_a) * di_sop)
            spring1.u += float(du_op_a + (du_op_b - du_op_a) * dj_sop)
            from histra.springs.coulomb03 import SpringCoulomb03
            if isinstance(spring0, SpringCoulomb03):
                dn = 0.5 * normal_increment
                spring0.dn = dn
                spring1.dn = dn
                if spring0.check_contact_area:
                    area = 0.5 * self.compute_area_corr()
                    spring0.area_corrente = area
                    spring1.area_corrente = area
            spring0.set_trial_strain(spring0.u)
            spring1.set_trial_strain(spring1.u)
            max_displacement = max(
                max_displacement, abs(float(spring0.u)), abs(float(spring1.u))
            )

        self.status.max_spring_displacement = max_displacement

    # ═════════════════════════════════════════════════════════════════════════
    # SetResistingForce  (port of Interface.SetResistingForce)
    # ═════════════════════════════════════════════════════════════════════════

    def set_resisting_force(self) -> None:
        """Compute the local 12-DOF force vector using cached geometry."""
        self._ensure_performance_cache()
        assert self._perf_di is not None
        assert self._perf_dj is not None
        assert self._perf_ecc is not None

        arr = self.f
        for i in range(12):
            arr[i] = 0.0

        batch = getattr(self, "_perf_hysteretic_batch", None)
        if batch is not None and batch.manages(self):
            local_force = batch.local_force_for(self)
            for i in range(12):
                arr[i] = float(local_force[i])
            return
        else:
            constrained = self.interfaccia_vincolata_computed()
            length = self.length
            for spring, di, dj, ecc in zip(
                self.trasv_1, self._perf_di, self._perf_dj, self._perf_ecc
            ):
                force = float(spring._tstress) if hasattr(spring, "_tstress") else float(spring.get_force())
                if not constrained:
                    arr[3] += force * dj / length
                    arr[2] += force * di / length
                    arr[0] += (0.0 - force) * dj / length
                    arr[1] += (0.0 - force) * di / length
                else:
                    arr[3] += force * dj / length
                    arr[2] += force * di / length
                    arr[0] += (0.0 - force) * di / length - force * dj / length
                    arr[1] += 0.5 * length * (
                        force * dj / length - force * di / length
                    )
                arr[4] += force * ecc
                arr[5] += (0.0 - force) * ecc

        if self.slid:
            spring = self.slid[0]
            force = float(spring._tstress) if hasattr(spring, "_tstress") else float(spring.get_force())
            arr[6] += force
            arr[7] -= force

        if len(self.slid_out_plan) >= 2:
            assert self._perf_dist is not None
            di, dj = self._perf_dist
            spring0, spring1 = self.slid_out_plan[0], self.slid_out_plan[1]
            force0 = float(spring0._tstress) if hasattr(spring0, "_tstress") else float(spring0.get_force())
            force1 = float(spring1._tstress) if hasattr(spring1, "_tstress") else float(spring1.get_force())
            first = dj * force0 + di * force1
            second = di * force0 + dj * force1
            arr[8] += first
            arr[9] += second
            arr[10] -= first
            arr[11] -= second

    def get_resisting_force(self, ls: Any) -> None:
        """Compute and scatter the cached local resisting-force projection."""
        self.set_resisting_force()
        for i, local_force in enumerate(self.f[: self.dim_aff_tot]):
            if local_force == 0.0 or i >= len(self.aff):
                continue
            for entry in self.aff[i]:
                g = entry.gdl - 1
                if 0 <= g < ls.n:
                    ls.b[g] -= local_force * entry.alfa

    # ═════════════════════════════════════════════════════════════════════════
    # Commit  (port of Interface.Commit)
    # ═════════════════════════════════════════════════════════════════════════

    def commit(self, ls: Any = None) -> None:
        """Port of Interface.Commit().

        Commits all spring states (trial → committed).
        The *ls* argument is accepted for interface compatibility with the
        solver but is not used (C# Commit has no LS parameter).
        """
        batch = getattr(self, "_perf_hysteretic_batch", None)
        if batch is None or not batch.manages(self):
            for s in self.trasv_1:
                if hasattr(s, 'commit'):
                    s.commit()
        for s in self.slid:
            if not getattr(s, "_histra_batch_managed", False) and hasattr(s, 'commit'):
                s.commit()
        for s in self.slid_out_plan:
            if not getattr(s, "_histra_batch_managed", False) and hasattr(s, 'commit'):
                s.commit()

    # ═════════════════════════════════════════════════════════════════════════
    # revertToLastCommit  (port of Interface.revertToLastCommit)
    # ═════════════════════════════════════════════════════════════════════════

    def revert_to_last_commit(self, ls: Any) -> None:
        """Port of Interface.revertToLastCommit(LinearSystem LS).

        Reverts *Status.U* using the displacement increment stored in
        *ls.x* (which at this point contains *u_committed - u*, i.e. the
        negative of the current increment), then calls
        ``RevertToLastCommit`` on each spring.
        """
        I = self
        x = ls.x if hasattr(ls, 'x') else ls  # accept both LS and raw array

        # Revert Status.U using the negative increment
        for i in range(I.dim_aff_tot):
            if i >= len(I.aff):
                continue
            total = 0.0
            for entry in I.aff[i]:
                g = entry.gdl - 1
                if 0 <= g < len(x):
                    total += x[g] * entry.alfa
            I.status.u[i] += total

        # Revert springs. Batched transverse histories are restored in dense
        # arrays and synchronized to their compatibility objects once per interface.
        batch = getattr(I, "_perf_hysteretic_batch", None)
        if batch is not None and batch.manages(I):
            batch.revert_interface(I)
        else:
            for s in I.trasv_1:
                if hasattr(s, 'revert_to_last_commit'):
                    s.revert_to_last_commit()
        for s in I.slid:
            if hasattr(s, 'revert_to_last_commit'):
                s.revert_to_last_commit()
        for s in I.slid_out_plan:
            if hasattr(s, 'revert_to_last_commit'):
                s.revert_to_last_commit()

    # ═════════════════════════════════════════════════════════════════════════
    # max_u / compute_energy  (convenience stubs matching solver expectations)
    # ═════════════════════════════════════════════════════════════════════════

    def max_u(self) -> float:
        """Maximum trial spring displacement cached during ``update_domain``."""
        return float(self.status.max_spring_displacement)

    def compute_energy(self) -> Tuple[float, float, float]:
        """Port of Interface.ComputeEnergy.

        Returns (elastic, plastic, total) energy summed over all springs.
        """
        e_el = e_pl = e_tot = 0.0
        for s in self.trasv_1:
            if hasattr(s, 'compute_energy'):
                de_el, de_pl, de_tot = s.compute_energy()
                e_el += de_el
                e_pl += de_pl
                e_tot += de_tot
            else:
                e_tot += 0.5 * getattr(s, 'k', 0.0) * getattr(s, 'u', 0.0) ** 2
                e_el = e_tot
        for s in self.slid:
            if hasattr(s, 'compute_energy'):
                de_el, de_pl, de_tot = s.compute_energy()
                e_el += de_el
                e_pl += de_pl
                e_tot += de_tot
            else:
                e_tot += 0.5 * getattr(s, 'k', 0.0) * getattr(s, 'u', 0.0) ** 2
        for s in self.slid_out_plan:
            if hasattr(s, 'compute_energy'):
                de_el, de_pl, de_tot = s.compute_energy()
                e_el += de_el
                e_pl += de_pl
                e_tot += de_tot
            else:
                e_tot += 0.5 * getattr(s, 'k', 0.0) * getattr(s, 'u', 0.0) ** 2
        return e_el, e_pl, e_tot

    @classmethod
    def from_xml(cls, elem) -> Interface:
        intf = cls()
        intf.key = int(elem.get("Key", "0"))
        intf.name = elem.get("Name", "")
        intf.parent_element_key1 = int(elem.get("ParentElementKey1", "0"))
        intf.parent_element_key2 = int(elem.get("ParentElementKey2", "0"))
        intf.parent_type_element1 = elem.get("ParentTypeElement1", "")
        intf.parent_type_element2 = elem.get("ParentTypeElement2", "")
        intf.face1 = int(elem.get("Face1", "0"))
        intf.face2 = int(elem.get("Face2", "0"))
        intf.length = float(elem.get("Length", "0"))
        intf.material_key = int(elem.get("MaterialKey", "0"))
        intf.layer_key = int(elem.get("LayerKey", "0"))
        intf.nrow = int(elem.get("Nrow", "3"))
        # In the .NET reference, Nspring and Ncol share the same backing field (`_ncol`).
        # The XML serializes the field once (typ= "Nspring"), so we read Nspring first
        # and only fall back to a "Ncol" attribute if explicitly present.
        ns = elem.get("Nspring")
        nc = elem.get("Ncol")
        if nc is not None:
            intf.ncol = int(nc)
        elif ns is not None:
            intf.ncol = int(ns)
        else:
            intf.ncol = 3
        intf.nspring = intf.ncol  # kept for parity with .NET (alias)
        intf.dim_aff = [
            int(elem.get("DimAff1", "6")),
            int(elem.get("DimAff2", "2")),
            int(elem.get("DimAff3", "4")),
        ]
        intf.dim_aff_tot = int(elem.get("DimAffTot", "12"))
        intf.frot = int(elem.get("Frot", "0"))
        intf.imax = int(elem.get("Imax", "400"))
        intf.csi = float(elem.get("Csi", "0"))
        intf.interfaccia_vincolata = elem.get("InterfacciaVincolata", "false") == "true"

        for i in range(2):
            intf.node_keys[i] = int(elem.get(f"NodeKey{i+1}", "0"))

        tstr = elem.get("Thickness1", None)
        if tstr is not None:
            intf.thickness[0] = float(tstr)
        tstr = elem.get("Thickness2", None)
        if tstr is not None:
            intf.thickness[1] = float(tstr)

        # VInt2D and VInt3D
        for i in range(4):
            v2d = elem.get(f"VInt2D{i+1}", None)
            if v2d:
                intf.vint2d[i] = Point.from_str(v2d)
            v3d = elem.get(f"VInt3D{i+1}", None)
            if v3d:
                intf.vint3d[i] = Point.from_str(v3d)

        # Springs
        from histra.springs.registry import spring_from_xml
        trasv1 = elem.find("Trasv1")
        if trasv1 is not None:
            for sp in trasv1.findall("Spring"):
                intf.trasv_1.append(spring_from_xml(sp))
        trasv2 = elem.find("Trasv2")
        if trasv2 is not None:
            for sp in trasv2.findall("Spring"):
                intf.trasv_2.append(spring_from_xml(sp))
        slid = elem.find("Slid")
        if slid is not None:
            for sp in slid.findall("Spring"):
                intf.slid.append(spring_from_xml(sp))
        sop = elem.find("SlidOutPlan")
        if sop is not None:
            # C# can serialize the same Spring instance twice in SlidOutPlan.
            # SetSpringProperty visits both list positions and mutates the
            # shared object's Key; consequently both XML entries carry the same
            # final Key.  Preserve that identity on import instead of creating
            # two independent Python objects.
            by_key: dict[int, Any] = {}
            for sp in sop.findall("Spring"):
                spring_key = int(sp.get("Key", "0"))
                spring = by_key.get(spring_key)
                if spring is None:
                    spring = spring_from_xml(sp)
                    by_key[spring_key] = spring
                intf.slid_out_plan.append(spring)

        # AfferenceMatrices
        aff_elem = elem.find("AfferenceMatrices")
        if aff_elem is not None:
            mats = aff_elem.findall("AfferenceMatrix")
            for idx, m in enumerate(mats):
                if idx >= 12:
                    break
                alfa_items = m.find("Alfa")
                gdl_items = m.find("Gdl")
                if alfa_items is not None and gdl_items is not None:
                    alfas = [float(a.get("Value", "0")) for a in alfa_items.findall("item")]
                    gdls = [int(g.get("Value", "0")) for g in gdl_items.findall("item")]
                    intf.aff[idx] = [AfferenceEntry(gdl=g, alfa=a) for a, g in zip(alfas, gdls)]

        # ReferenceSystem
        rs = elem.find("ReferenceSystem")
        if rs is not None:
            e1 = rs.get("E1", "1;0;0")
            e2 = rs.get("E2", "0;1;0")
            e3 = rs.get("E3", "0;0;1")
            intf.reference_e1 = tuple(float(x) for x in e1.split(";"))
            intf.reference_e2 = tuple(float(x) for x in e2.split(";"))
            intf.reference_e3 = tuple(float(x) for x in e3.split(";"))
            orig = rs.get("Origin", None)
            if orig:
                intf.reference_origin = Point.from_str(orig)

        return intf
