from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt

import numpy as np
from typing import Dict, List, Tuple, Optional

try:
    from numba import njit
except Exception:  # pragma: no cover
    njit = None
from histra.types.point import Point
from histra.types.afference_entry import AfferenceEntry
from histra.springs.base import Spring
from histra.elements.quad_state import QuadState
from histra.elements.quad_static_load import compute_static_load_area


from histra.elements.quad_geometry import QuadGeometryMixin
from histra.elements.quad_loads import QuadLoadsMixin
from histra.elements.quad_kernels import (  # noqa: E402
    _quad_yield_search_kernel,
    quad_yield_search,
    quad_yield_search_scalar,
)


@dataclass
class Quad(
    QuadGeometryMixin,
    QuadLoadsMixin,
):
    key: int = 0
    node_keys: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    length: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    sin: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    cos: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    diago: List[float] = field(default_factory=lambda: [0.0, 0.0])
    thickness: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    normal: List[Point] = field(default_factory=lambda: [Point(), Point(), Point(), Point()])
    g: Point = field(default_factory=Point)
    material_key: int = 0
    spring: Spring | None = None

    @property
    def springs(self) -> List[Spring]:
        return [self.spring] if self.spring else []

    @springs.setter
    def springs(self, val: List[Spring]) -> None:
        self.spring = val[0] if val else None
    # 7 Afference matrices (each is a list of (gdl, alfa) entries)
    aff: List[List[AfferenceEntry]] = field(default_factory=lambda: [[] for _ in range(7)])
    interface_keys: List[List[int]] = field(default_factory=lambda: [[] for _ in range(6)])
    # Reference system
    reference_e1: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    reference_e2: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    reference_e3: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    reference_origin: Point = field(default_factory=Point)
    status: QuadState = field(default_factory=QuadState)
    name: str = ""
    extra: Dict[str, str] = field(default_factory=dict)
    parent_key: int = 0
    parent_type: str = ""
    material_key: int = 0
    layer_key: int = 0
    master_element_key: int = 0
    master_element_type: str = ""
    sigma_initial: float = 0.0
    _perf_volume: float | None = field(default=None, init=False, repr=False, compare=False)
    _perf_aff_pairs: tuple[tuple[tuple[int, float], ...], ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_dn_edges: tuple[tuple[tuple[object, bool], ...], ...] | None = field(default=None, init=False, repr=False, compare=False)
    _perf_dn_areas: tuple[float, ...] | None = field(default=None, init=False, repr=False, compare=False)

    def set_non_linear_properties(self, k: float, E: float, G: float,
                                   Fyt: float, Fyc: float) -> Tuple[float, float]:
        """Literal port of C# ``Quad.SetNonLinearProperties``.

        The C# routine evaluates both principal stresses for each of two
        opposite unit diagonal deformations.  Its extrema are intentionally
        cumulative across the two passes; the first and second returned yield
        forces can therefore have different magnitudes.  A previous Python
        simplification used one symmetric extrema pair and overestimated the
        Quad cohesion by up to two orders of magnitude.
        """
        return quad_yield_search(
            float(k), float(E), float(G), float(Fyt), float(Fyc),
            float(self.d_alfa_2d_diag()),
            float(self.length[0]), float(self.length[1]), float(self.length[3]),
            float(self.cos[0]), float(self.cos[1]),
            float(self.sin[0]), float(self.sin[1]), float(self.sin[2]), float(self.sin[3]),
        )

    # ── SetResistingForce / GetResistingForce ────────────────────────────────

    def set_resisting_force(self) -> None:
        """Compute internal force F[0] from the diagonal spring.

        C# ``SetResistingForce``:

            base.F[0] = DAlfa2DDiag() * Spring.GetForce()
        """
        if self.spring is None:
            return
        self.status.f = self.d_alfa_2d_diag() * self.spring.get_force()

    def get_resisting_force(self, gdl_map: List[int],
                             alfa_map: List[float],
                             b: List[float]) -> None:
        """Distribute the diagonal spring resisting force into global vector b.

        C# ``GetResistingForce(LS, gdl=None)``.

        Parameters
        ----------
        gdl_map : list of global DOF indices (0-based) from Aff[6]
        alfa_map : corresponding alfa coefficients
        b : global load vector (mutated in-place)
        """
        if self.spring is None or not gdl_map:
            return
        # Ensure F[0] is up-to-date
        self.set_resisting_force()
        f0 = self.status.f

        for g, a in zip(gdl_map, alfa_map):
            if 0 <= g < len(b):
                b[g] -= f0 * a

    def compute_volume(self) -> float:
        """Return the cached C# ``Quad.GetVolume`` value."""
        if self._perf_volume is not None:
            return self._perf_volume
        l0, l1, l3 = self.length[0], self.length[1], self.length[3]
        xcoord = [-l0 / 2.0, l0 / 2.0, l0 / 2.0 - l1 * self.cos[1], -l0 / 2.0 + l3 * self.cos[0]]
        ycoord = [0.0, 0.0, l1 * self.sin[1], l3 * self.sin[0]]
        volume = ((-self.thickness[0]) * xcoord[1] * ycoord[0] / 6.0
                  - self.thickness[1] * xcoord[1] * ycoord[0] / 6.0
                  - self.thickness[2] * xcoord[1] * ycoord[0] / 12.0
                  - self.thickness[3] * xcoord[1] * ycoord[0] / 12.0
                  + self.thickness[1] * xcoord[2] * ycoord[0] / 12.0
                  - self.thickness[3] * xcoord[2] * ycoord[0] / 12.0
                  + self.thickness[0] * xcoord[3] * ycoord[0] / 6.0
                  + self.thickness[1] * xcoord[3] * ycoord[0] / 12.0
                  + self.thickness[2] * xcoord[3] * ycoord[0] / 12.0
                  + self.thickness[3] * xcoord[3] * ycoord[0] / 6.0
                  + self.thickness[0] * xcoord[0] * ycoord[1] / 6.0
                  + self.thickness[1] * xcoord[0] * ycoord[1] / 6.0
                  + self.thickness[2] * xcoord[0] * ycoord[1] / 12.0
                  + self.thickness[3] * xcoord[0] * ycoord[1] / 12.0
                  - self.thickness[0] * xcoord[2] * ycoord[1] / 12.0
                  - self.thickness[1] * xcoord[2] * ycoord[1] / 6.0
                  - self.thickness[2] * xcoord[2] * ycoord[1] / 6.0
                  - self.thickness[3] * xcoord[2] * ycoord[1] / 12.0
                  - self.thickness[0] * xcoord[3] * ycoord[1] / 12.0
                  + self.thickness[2] * xcoord[3] * ycoord[1] / 12.0
                  - self.thickness[1] * xcoord[0] * ycoord[2] / 12.0
                  + self.thickness[3] * xcoord[0] * ycoord[2] / 12.0
                  + self.thickness[0] * xcoord[1] * ycoord[2] / 12.0
                  + self.thickness[1] * xcoord[1] * ycoord[2] / 6.0
                  + self.thickness[2] * xcoord[1] * ycoord[2] / 6.0
                  + self.thickness[3] * xcoord[1] * ycoord[2] / 12.0
                  - self.thickness[0] * xcoord[3] * ycoord[2] / 12.0
                  - self.thickness[1] * xcoord[3] * ycoord[2] / 12.0
                  - self.thickness[2] * xcoord[3] * ycoord[2] / 6.0
                  - self.thickness[3] * xcoord[3] * ycoord[2] / 6.0
                  - self.thickness[0] * xcoord[0] * ycoord[3] / 6.0
                  - self.thickness[1] * xcoord[0] * ycoord[3] / 12.0
                  - self.thickness[2] * xcoord[0] * ycoord[3] / 12.0
                  - self.thickness[3] * xcoord[0] * ycoord[3] / 6.0
                  + self.thickness[0] * xcoord[1] * ycoord[3] / 12.0
                  - self.thickness[2] * xcoord[1] * ycoord[3] / 12.0
                  + self.thickness[0] * xcoord[2] * ycoord[3] / 12.0
                  + self.thickness[1] * xcoord[2] * ycoord[3] / 12.0
                  + self.thickness[2] * xcoord[2] * ycoord[3] / 6.0
                  + self.thickness[3] * xcoord[2] * ycoord[3] / 6.0)
        self._perf_volume = volume
        return volume

    def _ensure_dn_cache(self, collections) -> None:
        if self._perf_dn_edges is not None:
            return
        edges: list[tuple[tuple[object, bool], ...]] = []
        areas: list[float] = []
        for edge in range(4):
            refs: list[tuple[object, bool]] = []
            area = 0.0
            for interface_key in self.interface_keys[edge]:
                intf = collections.interfaces.get(interface_key)
                if intf is None:
                    continue
                area += intf.area()
                belongs = (
                    (intf.parent_type_element1 == "Quad" and intf.parent_element_key1 == self.key)
                    or (intf.parent_type_element2 == "Quad" and intf.parent_element_key2 == self.key)
                )
                if not belongs:
                    continue
                custom_springs = any(
                    not getattr(spring, "_histra_batch_managed", False)
                    and (
                        "get_force" in spring.__dict__
                        or "get_incr_force" in spring.__dict__
                    )
                    for spring in intf.trasv_1
                )
                refs.append((intf, custom_springs))
            edges.append(tuple(refs))
            areas.append(area)
        self._perf_dn_edges = tuple(edges)
        self._perf_dn_areas = tuple(areas)

    def compute_dn(self, collections, ls=None, nr: bool = False) -> tuple[float, float]:
        """Port of C# ``Quad.ComputeDN`` using cached interface relationships."""
        if not nr:
            return self._compute_linear_normal_force(collections, ls)
        self._ensure_dn_cache(collections)
        assert self._perf_dn_edges is not None
        assert self._perf_dn_areas is not None
        normal_increment = [0.0] * 4
        committed_stress = [0.0] * 4
        for edge, refs in enumerate(self._perf_dn_edges):
            force = 0.0
            for intf, custom_springs in refs:
                custom_interface = "compute_dn" in intf.__dict__
                if custom_interface or custom_springs:
                    normal_increment[edge] += intf.compute_dn(nr=True)
                    force += sum(
                        float(spring.get_force() - spring.get_incr_force())
                        for spring in intf.trasv_1
                    )
                else:
                    normal_increment[edge] += float(intf.status.normal_increment)
                    force += float(intf.status.committed_normal_force)
            area = self._perf_dn_areas[edge]
            if area > 0.0:
                committed_stress[edge] = force / area
        sigma = 0.5 * (committed_stress[0] + committed_stress[2]) + 0.5 * (committed_stress[1] + committed_stress[3])
        dn = 0.5 * (normal_increment[0] + normal_increment[2]) + 0.5 * (normal_increment[1] + normal_increment[3])
        return dn, sigma

    def _compute_linear_normal_force(self, collections, ls) -> tuple[float, float]:
        from histra.solver.hysteretic_kernels.kinematics import _quad_linear_normal_force
        if _quad_linear_normal_force is None:
            raise RuntimeError("NR=False requires the compiled Numba backend")
        self._ensure_dn_cache(collections)
        interfaces, edges = [], [0]
        for refs in self._perf_dn_edges:
            interfaces.extend(intf for intf, _ in refs)
            edges.append(len(interfaces))
        dns = np.fromiter((intf.compute_dn(ls, nr=False) for intf in interfaces), dtype=np.float64)
        offsets, forces, increments = [0], [], []
        for intf in interfaces:
            runtime = getattr(intf, "_perf_hysteretic_batch", None)
            if runtime is not None and runtime.manages(intf):
                start, stop = intf._perf_hysteretic_slice
                trial = runtime.trial[start:stop, 6]
                delta = trial - runtime.committed[start:stop, 6]
            else:
                trial = np.fromiter((s.get_force() for s in intf.trasv_1), dtype=np.float64)
                delta = np.fromiter((s.get_incr_force() for s in intf.trasv_1), dtype=np.float64)
            forces.append(trial)
            increments.append(delta)
            offsets.append(offsets[-1] + len(trial))
        return _quad_linear_normal_force(
            np.asarray(edges, dtype=np.int64), dns, np.asarray(offsets, dtype=np.int64),
            np.concatenate(forces) if forces else np.empty(0),
            np.concatenate(increments) if increments else np.empty(0),
            np.asarray(self._perf_dn_areas, dtype=np.float64),
        )

    def _local_increment(self, x: np.ndarray) -> list[float]:
        if self._perf_aff_pairs is None:
            self._perf_aff_pairs = tuple(
                tuple((entry.gdl - 1, float(entry.alfa)) for entry in entries)
                for entries in self.aff[:7]
            )
        size = len(x)
        out = [0.0] * 7
        for i, pairs in enumerate(self._perf_aff_pairs):
            total = 0.0
            for gdl, coefficient in pairs:
                if 0 <= gdl < size:
                    total += x[gdl] * coefficient
            out[i] = total
        return out

    def update_domain(self, ls_or_x, state, collections=None) -> None:
        """Port of ``Quad.UpdateDomain``.

        Calls ``set_trial_strain_takeda_diagonal_quad`` when the diagonal
        spring is a ``SpringCoulomb03`` (passing normal-force increment and
        material params), otherwise falls back to ``Spring.set_trial_strain``.
        """
        if self.spring is None:
            return
        x = ls_or_x.x if hasattr(ls_or_x, "x") else ls_or_x
        self._local_increment(x)  # Initialize immutable afference cache.
        for i, pairs in enumerate(self._perf_aff_pairs or ()):
            for gdl, coefficient in pairs:
                if 0 <= gdl < len(x):
                    self.status.u[i] += float(x[gdl] * coefficient)
        from histra.springs.coulomb03 import SpringCoulomb03
        if isinstance(self.spring, SpringCoulomb03):
            if collections is None:
                raise RuntimeError("Quad Coulomb update requires model collections for ComputeDN")
            dN, sigma = self.compute_dn(collections, ls_or_x, nr=True)
            if int(getattr(state, "step", 0)) == 1:
                self.sigma_initial = sigma
            strain = self.d_alfa_2d_diag() * self.status.u[6]
            htype = str(getattr(self.spring, "hysteretic_type", "Takeda")).casefold()
            if htype in ("initial", "0"):
                self.spring.dn = dN
                self.spring.set_trial_strain_initial(strain)
            else:
                self.spring.set_trial_strain_takeda_diagonal_quad(
                    strain,
                    dN,
                    masonry=collections.materials.get(self.material_key),
                    volume=self.compute_volume(),
                    sigma=self.sigma_initial,
                )
        else:
            self.spring.set_trial_strain(self.d_alfa_2d_diag() * self.status.u[6])

    def commit(self, _ls=None) -> None:
        """Port of ``Quad.Commit``."""
        if self.spring is not None and not getattr(
            self.spring, "_histra_batch_managed", False
        ):
            self.spring.commit()

    def revert_to_last_commit(self, ls) -> None:
        """Port of ``Quad.revertToLastCommit``."""
        x = ls.x if hasattr(ls, "x") else ls
        for i, value in enumerate(self._local_increment(x)):
            self.status.u[i] += float(value)
        if self.spring is not None:
            batch = getattr(self.spring, "_histra_quad_batch", None)
            if batch is not None and getattr(self.spring, "_histra_batch_managed", False):
                batch.revert_quad(self)
            else:
                self.spring.revert_to_last_commit()
                if hasattr(self.spring, "revert_to_last_commit_stress_normal"):
                    self.spring.revert_to_last_commit_stress_normal()

    def max_u(self) -> float:
        """Port of ``Quad.MaxU``."""
        return max((abs(value) for value in self.status.u), default=0.0)

    # ── Set diagonal quad ────────────────────────────────────────────────────

    @classmethod
    def _warping_coeffs(cls, quad: Quad) -> List[float]:
        """Compute the warping displacement vector a[0..3] (C# array2)."""
        L3 = quad.length[3]
        Sin0, Sin1 = quad.sin[0], quad.sin[1]
        Sin2, Sin3 = quad.sin[2], quad.sin[3]
        Cos0, Cos1 = quad.cos[0], quad.cos[1]
        a = [0.0] * 4
        if abs(Sin2) > 1e-30:
            a[0] = -L3 * Sin3 * Sin1 / Sin2
            a[1] = -L3 * Sin3 * Cos1 / Sin2
        a[2] = -L3 * Sin0
        a[3] =  L3 * Cos0
        return a

    def compute_energy(self) -> Tuple[float, float, float]:
        """Port of Quad.ComputeEnergy — delegates to the spring."""
        if self.spring is not None and hasattr(self.spring, 'compute_energy'):
            return self.spring.compute_energy()
        k = getattr(self.spring, 'k', 0.0) if self.spring else 0.0
        u = getattr(self.spring, 'u', 0.0) if self.spring else 0.0
        e = 0.5 * k * u * u
        return e, 0.0, e

    @classmethod
    def from_xml(cls, elem) -> Quad:
        q = cls()
        q.key = int(elem.get("Key", "0"))
        q.name = elem.get("Name", "")
        for k, v in elem.attrib.items():
            if k not in {"Key", "Name"}:
                q.extra[k] = v
        q.parent_key = int(elem.get("ParentKey", "0"))
        q.parent_type = elem.get("ParentTypeElement", "")
        q.material_key = int(elem.get("MaterialKey", "0"))
        q.layer_key = int(elem.get("LayerKey", "0"))
        q.master_element_key = int(elem.get("MasterElementKey", "0"))
        q.master_element_type = elem.get("MasterElementType", "None")

        for i in range(4):
            q.node_keys[i] = int(elem.get(f"NodeKey{i+1}", "0"))
            q.length[i] = float(elem.get(f"Length{i+1}", "0"))
            q.sin[i] = float(elem.get(f"Sin{i+1}", "0"))
            q.cos[i] = float(elem.get(f"Cos{i+1}", "0"))
            q.thickness[i] = float(elem.get(f"Thickness{i+1}", "0"))
            nstr = elem.get(f"Normal{i+1}", None)
            if nstr:
                q.normal[i] = Point.from_str(nstr)
        for i in range(2):
            q.diago[i] = float(elem.get(f"Diago{i+1}", "0"))

        gstr = elem.get("G", None)
        if gstr:
            q.g = Point.from_str(gstr)

        # U1..U7 (post-solve state)
        for i in range(7):
            ustr = elem.get(f"U{i+1}", None)
            if ustr is not None:
                q.status.u[i] = float(ustr)

        # Spring
        sp = elem.find("Spring")
        if sp is not None:
            from histra.springs.registry import spring_from_xml
            q.spring = spring_from_xml(sp)

        # AfferenceMatrices
        aff_elem = elem.find("AfferenceMatrices")
        if aff_elem is not None:
            mats = aff_elem.findall("AfferenceMatrix")
            for idx, m in enumerate(mats):
                if idx >= 7:
                    break
                alfa_items = m.find("Alfa")
                gdl_items = m.find("Gdl")
                if alfa_items is not None and gdl_items is not None:
                    alfas = [float(a.get("Value", "0")) for a in alfa_items.findall("item")]
                    gdls = [int(g.get("Value", "0")) for g in gdl_items.findall("item")]
                    q.aff[idx] = [AfferenceEntry(gdl=g, alfa=a) for a, g in zip(alfas, gdls)]

        # Interface references
        for f in range(6):
            grp = elem.find(f"Interfaces{f+1}")
            if grp is not None:
                q.interface_keys[f] = [int(iface.get("Value", "0")) for iface in grp.findall("Interface")]

        # ReferenceSystem
        rs = elem.find("ReferenceSystem")
        if rs is not None:
            e1 = rs.get("E1", "1;0;0")
            e2 = rs.get("E2", "0;1;0")
            e3 = rs.get("E3", "0;0;1")
            q.reference_e1 = tuple(float(x) for x in e1.split(";"))
            q.reference_e2 = tuple(float(x) for x in e2.split(";"))
            q.reference_e3 = tuple(float(x) for x in e3.split(";"))
            orig = rs.get("Origin", None)
            if orig:
                q.reference_origin = Point.from_str(orig)

        return q
