from __future__ import annotations

from typing import Any, Callable

import numpy as np

from histra.model.model import Model
from histra.solver.assembler import assemble_global_k, _get_stiffness_assembly_plan
from histra.solver.load_assembly import (
    _get_load_template_coefficient,
    assemble_load_vector,
)
from histra.solver.program import Program
from histra.types.integrator_state import IntegratorState
from histra.types.linear_system import LinearSystem


def pdelta_enabled(value: Any) -> bool:
    """Normalize the C# enum/string representation of P-Delta settings."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    text = str(value).strip().lower()
    return text not in {"", "0", "none", "no", "false", "disabled"}


class ModelManager:
    """Global assembly/state operations aligned with the C# ``ModelManager``."""

    _ptarget: np.ndarray | None = None
    _ptarget_signature: tuple[int, int | None, int] | None = None
    _fext: np.ndarray | None = None
    _pq: np.ndarray | None = None
    _pq_prev: np.ndarray | None = None
    _u_total: np.ndarray | None = None
    _hysteretic_batch: Any | None = None
    _hysteretic_batch_model_id: int | None = None
    _hysteretic_batch_error: str | None = None

    on_log: Callable[[str], None] | None = None
    on_progress: Callable[[float], None] | None = None

    @classmethod
    def prepare_model(cls, model: Model, *, force: bool = False, use_cache: bool | None = None):
        """Port the C# ``ModelManager.PrepareModel`` preprocessing stage.

        The translated implementation currently covers the Quad/Restraint
        computational topology used by the supplied masonry models.  It
        creates interfaces, constitutive springs, global DOFs, and afference
        mappings, then returns a :class:`PreparationReport`.
        """
        from histra.preprocessing.prepare_model import prepare_model

        cls.clear_hysteretic_batch()
        return prepare_model(model, force=force, use_cache=use_cache)

    @classmethod
    def create_brand_new_model(cls, source: Model) -> Model:
        """Create an independent brand-new structural model from a source HRX model.

        The source model is left untouched with its serialized C# reference data
        intact for testing and comparison.
        """
        from histra.preprocessing.prepare_model import create_brand_new_model

        return create_brand_new_model(source)

    @classmethod
    def prepare_brand_new_model(cls, source: Model):
        """Create and prepare a brand-new computational model from a source HRX model.

        Returns a tuple of ``(prepared_model, report)``.  The source model is untouched
        and preserved for reference and comparison.
        """
        new_model = cls.create_brand_new_model(source)
        report = cls.prepare_model(new_model, force=True)
        return new_model, report

    @classmethod
    def clear_hysteretic_batch(cls) -> None:
        """Detach any compiled spring runtime from its model objects."""
        runtime = cls._hysteretic_batch
        if runtime is not None:
            for record in runtime.records:
                interface = record.interface
                for name in ("_perf_hysteretic_batch", "_perf_hysteretic_slice"):
                    if hasattr(interface, name):
                        delattr(interface, name)
            for spring in getattr(runtime, "managed_springs", runtime.springs):
                if hasattr(spring, "_histra_batch_managed"):
                    spring._histra_batch_managed = False
                for name in (
                    "_histra_quad_batch",
                    "_histra_quad_batch_index",
                ):
                    if hasattr(spring, name):
                        delattr(spring, name)
        cls._hysteretic_batch = None
        cls._hysteretic_batch_model_id = None
        cls._hysteretic_batch_error = None

    @classmethod
    def prepare_hysteretic_batch(cls, model: Model, *, rebuild: bool = False) -> Any | None:
        """Build or reuse the optional compiled transverse-spring runtime."""
        if (
            not rebuild
            and cls._hysteretic_batch is not None
            and cls._hysteretic_batch_model_id == id(model)
        ):
            return cls._hysteretic_batch
        cls.clear_hysteretic_batch()
        plan = getattr(model, "_perf_stiffness_assembly_plan", None)
        if plan is not None:
            plan.batch_data = None
            plan.validated_runtime_id = 0
        try:
            from histra.solver.hysteretic_runtime import build_hysteretic_batch
            runtime = build_hysteretic_batch(model)
        except Exception as exc:
            # Acceleration is optional. The tested scalar implementation remains
            # the authoritative fallback on platforms without a working Numba.
            runtime = None
            cls._hysteretic_batch_error = f"{type(exc).__name__}: {exc}"
        cls._hysteretic_batch = runtime
        cls._hysteretic_batch_model_id = id(model) if runtime is not None else None
        return runtime

    @classmethod
    def hysteretic_batch_for(cls, model: Model) -> Any | None:
        if (
            cls._hysteretic_batch_model_id == id(model)
            and cls._hysteretic_batch is not None
            and getattr(cls._hysteretic_batch, "model", None) is model
        ):
            return cls._hysteretic_batch
        return None

    @classmethod
    def update_hysteretic_batch_material_interfaces(
        cls, model: Model, interfaces: list[Any] | tuple[Any, ...]
    ) -> bool:
        """Update a compatible compiled runtime after material-only changes.

        The dense runtime is an optional acceleration layer.  Any mismatch or
        unexpected update failure discards it and leaves the authoritative
        Python spring objects to seed the existing full rebuild on the next
        analysis.
        """
        runtime = cls.hysteretic_batch_for(model)
        if runtime is None:
            cls.clear_hysteretic_batch()
            return False
        try:
            if runtime.try_update_material_interfaces(interfaces):
                plan = getattr(model, "_perf_stiffness_assembly_plan", None)
                if plan is not None:
                    plan.batch_data = None
                    plan.validated_runtime_id = 0
                return True
        except Exception:
            # Never let an acceleration-only refresh compromise the mutation.
            # New spring objects are already authoritative; a fresh runtime
            # will be created from them before the next solve.
            pass
        cls.clear_hysteretic_batch()
        return False

    @classmethod
    def assemble_k(
        cls,
        model: Model,
        ls: LinearSystem,
        alfa: float = 1.0,
        *,
        set_zero: bool = True,
        recompute_elements: bool = True,
    ) -> None:
        """Assemble the element stiffness selected by ``alfa``.

        The C# code first calls each element's ``ComputeK(alfa)`` and then
        scatters those current coefficients.  The earlier Python port always
        reassembled with ``alfa=0``, silently turning Standard Newton into
        Modified Newton.
        """
        if set_zero:
            ls.set_zero()
        ls.k = assemble_global_k(
            model, alfa=alfa, recompute_elements=recompute_elements
        ).tocsc()

    @classmethod
    def assemble_load(
        cls,
        model: Model,
        ls: LinearSystem,
        analysis_key: int | None = None,
        combination: int = 1,
        *,
        reuse_current: bool = False,
    ) -> None:
        """Assemble or reuse the static target load for one analysis.

        The currently translated load generators are model self-weight and
        direct Quad line loads.  They are invariant during a static analysis;
        unsupported nonlinear P-Delta refreshes are rejected before this path.
        ``reuse_current`` is therefore used only by the incremental integrator
        after the solver has performed the mandatory fresh assembly at the
        beginning of the analysis.  A model/analysis/combination mismatch
        always forces a new vector.
        """
        signature = (id(model), analysis_key, int(combination))
        if not (
            reuse_current
            and cls._ptarget is not None
            and cls._ptarget_signature == signature
        ):
            cls._ptarget = assemble_load_vector(
                model, analysis_key, combination
            )
            cls._ptarget_signature = signature
        ls.set_zero_load()

    @classmethod
    def compute_ktang(cls, model: Model, ls: LinearSystem, alfa: float) -> int:
        runtime = cls.hysteretic_batch_for(model)
        if runtime is not None:
            plan = getattr(model, "_perf_stiffness_assembly_plan", None)
            dirty_interfaces = getattr(
                model, "_perf_initial_stiffness_dirty_interfaces", None
            )
            if dirty_interfaces:
                if plan is not None:
                    plan.batch_data = None
                    plan.validated_runtime_id = 0
                dirty_interfaces.clear()
            runtime_id = id(runtime)
            if (
                plan is None
                or (plan.batch_data is not None and not plan.batch_data.compatible(model))
                or (plan.validated_runtime_id != runtime_id and not plan.compatible(model))
            ):
                plan = _get_stiffness_assembly_plan(model)
                if plan is not None:
                    plan.validated_runtime_id = runtime_id
            else:
                plan.validated_runtime_id = runtime_id

            if plan is not None:
                plan.ensure_batch_data(model, runtime)
                if plan.batch_data is not None:
                    plan.evaluate_and_assemble(model, ls, alfa=alfa, runtime=runtime)
                    model._perf_element_stiffness_alfa = float(alfa)
                    return 0
        if runtime is not None and alfa != 0.0:
            # Updated-tangent methods need only the active tangent stiffnesses
            # to assemble K. Avoid expensive full-state object synchronizations.
            runtime.sync_tangents_to_objects()
        cls.compute_k(model, alfa)
        cls.assemble_k(
            model, ls, alfa=alfa, set_zero=True, recompute_elements=False
        )
        return 0

    @classmethod
    def compute_k(cls, model: Model, alfa: float = 1.0) -> None:
        topology_signature = (
            id(model.collections.quads),
            len(model.collections.quads),
            id(model.collections.interfaces),
            len(model.collections.interfaces),
        )
        cached_signature = getattr(
            model, "_perf_element_stiffness_topology_signature", None
        )
        cached_alfa = getattr(model, "_perf_element_stiffness_alfa", None)
        dirty_interfaces = getattr(
            model, "_perf_initial_stiffness_dirty_interfaces", None
        )

        # Every static analysis starts from alfa=0.  If no non-initial tangent
        # has overwritten the element blocks since the previous analysis, the
        # Quad blocks and all untouched interface blocks are already the exact
        # matrices that C# would recompute. Material replacement records the
        # handful of rebuilt interfaces explicitly, so only those blocks need
        # refreshing before the same ordered global scatter is performed.
        if (
            alfa == 0.0
            and cached_alfa == 0.0
            and cached_signature == topology_signature
        ):
            if dirty_interfaces:
                for key, intf in model.collections.interfaces.items():
                    if int(key) in dirty_interfaces:
                        intf.compute_k(alfa)
                dirty_interfaces.clear()
            return

        for quad in model.collections.quads.values():
            quad.compute_k(alfa)
        for intf in model.collections.interfaces.values():
            intf.compute_k(alfa)
        model._perf_element_stiffness_topology_signature = topology_signature
        model._perf_element_stiffness_alfa = float(alfa)
        if dirty_interfaces is not None:
            dirty_interfaces.clear()

    @classmethod
    def refresh_saved_interface_forces(cls, model: Model) -> None:
        """Mirror the force cache written by C# AddStateElements."""
        runtime = cls.hysteretic_batch_for(model)
        if runtime is not None:
            np.copyto(runtime._pdelta_saved_resultants, runtime.all_resultant_forces())
            for row, record in zip(runtime._pdelta_saved_resultants, runtime.records):
                record.interface.status.forces = tuple(float(value) for value in row)
            interfaces = runtime.unmanaged_interfaces
        else:
            interfaces = model.collections.interfaces.values()
        from histra.postprocessing import _interface_local_resultant
        for interface in interfaces:
            interface.status.forces = tuple(float(value) for value in _interface_local_resultant(interface))

    @classmethod
    def compute_and_assemble_pdelta_load(
        cls,
        model: Model,
        ls: LinearSystem | None = None,
        analysis: Any | None = None,
        combination: int = 1,
    ) -> np.ndarray:
        r"""Compute and assemble discrete macro-element P-Delta loads (Pq).

        Port of C# ModelLoadOperations.ComputePDeltaLoads and ModelManager.AssemblePdeltaLoad.
        Moments on each Quad Q are produced by applied line loads and interface forces:
            M_{P\Delta} = (\boldsymbol{\Phi}_G \times (G_{intf} - G_{quad})) \times \mathbf{F}_{intf, global}
        assembled into rotational DOFs (aff[3..5]).
        """
        collections = model.collections
        gdl = int(model.gdl)
        pq_global = np.zeros(gdl, dtype=np.float64)
        runtime = cls.hysteretic_batch_for(model)

        if runtime is not None:
            runtime.compute_pdelta_interface_moments(pq_global)
            if analysis is not None and collections.line_loads:
                runtime.compute_pdelta_line_load_moments(
                    pq_global, analysis, combination
                )
        else:
            line_loads_by_quad: dict[int, list[Any]] = {}
            if analysis is not None:
                for load in collections.line_loads.values():
                    if load.element_type == "Quad":
                        line_loads_by_quad.setdefault(int(load.element_key), []).append(load)

            for quad in collections.quads.values():
                local_u = np.asarray(quad.status.u, dtype=np.float64)
                if len(local_u) < 6:
                    continue
                # XNA Vector3 is Single precision in the C# path.
                phi_g = np.asarray(local_u[3:6], dtype=np.float32)
                translation = np.asarray(local_u[:3], dtype=np.float32)
                if phi_g[0] == 0.0 and phi_g[1] == 0.0 and phi_g[2] == 0.0:
                    continue
                g_quad = np.asarray([quad.g.x, quad.g.y, quad.g.z], dtype=np.float32)
                pq_quad = np.zeros(6, dtype=np.float64)

                for load in line_loads_by_quad.get(int(quad.key), ()):
                    template = collections.load_templates.get(load.load_template_key)
                    if template is None:
                        continue
                    point1 = np.asarray(load.point1, dtype=np.float32)
                    point2 = np.asarray(load.point2, dtype=np.float32)
                    midpoint = np.float32(0.5) * (point1 + point2)
                    length = np.float32(np.linalg.norm(point1 - point2))
                    delta_u = (translation + np.cross(phi_g, midpoint - g_quad)) - translation
                    for item in template.items:
                        coefficient = np.float32(
                            _get_load_template_coefficient(
                                model,
                                int(analysis.key),
                                combination,
                                int(item.load_condition_id),
                                item,
                            )
                        )
                        # ComputePDeltaLoads uses template.Dir(quad), including
                        # seismic analyses; its force-generation override is a
                        # different original routine.
                        direction = np.asarray(item.direction_for(quad), dtype=np.float32)
                        force = (
                            np.float32(item.load_value)
                            * length
                            * coefficient
                            * direction
                        ).astype(np.float32)
                        pq_quad[3:] += np.cross(delta_u, force).astype(np.float32)

                for face_intf_keys in quad.interface_keys[:4]:
                    for intf_key in face_intf_keys:
                        intf = collections.interfaces.get(intf_key)
                        if intf is None:
                            continue
                        sign = 1.0 if (intf.parent_element_key1 == quad.key and intf.parent_type_element1 == "Quad") else -1.0
                        f_local = np.asarray(intf.status.forces, dtype=np.float32)

                        # MatrixPerVector3 multiplies/adds Single components.
                        e1 = np.array(intf.reference_e1, dtype=np.float32)
                        e2 = np.array(intf.reference_e2, dtype=np.float32)
                        e3 = np.array(intf.reference_e3, dtype=np.float32)
                        f_global = np.asarray(
                            sign * (f_local[0] * e1 + f_local[1] * e2 + f_local[2] * e3),
                            dtype=np.float32,
                        )

                        intf_nodes = [collections.nodes[nk].point for nk in intf.node_keys if nk in collections.nodes]
                        if intf_nodes:
                            g_intf = np.mean([[p.x, p.y, p.z] for p in intf_nodes], axis=0)
                        elif getattr(intf, "vint3d", None):
                            g_intf = np.mean([[p.x, p.y, p.z] for p in intf.vint3d], axis=0)
                        else:
                            continue

                        r = np.asarray(g_intf, dtype=np.float32) - g_quad
                        delta_u = (translation + np.cross(phi_g, r)) - translation
                        moment = np.cross(delta_u, f_global)
                        pq_quad[3:] += moment

                for i in range(3, 6):
                    if i < len(quad.aff):
                        for entry in quad.aff[i]:
                            dof = entry.gdl - 1
                            if 0 <= dof < gdl:
                                pq_global[dof] += pq_quad[i] * entry.alfa

        relaxation = float(getattr(analysis, "pdelta_relaxation", 0.0) or 0.0)
        if relaxation > 0.0 and cls._pq_prev is not None and len(cls._pq_prev) == len(pq_global):
            pq_global = (1.0 - relaxation) * pq_global + relaxation * cls._pq_prev

        cls._pq = pq_global
        return pq_global

    @classmethod
    def form_unbalance(cls, model: Model, ls: LinearSystem, an: Any) -> None:
        cls.get_resisting_force(model, ls)
        fext = cls._fext if cls._fext is not None else np.zeros(ls.n)
        pq = cls._pq if cls._pq is not None else np.zeros(ls.n)
        residual_external = fext + pq if pdelta_enabled(getattr(an, "pdelta_effect", None)) else fext
        ls.b[: min(ls.n, len(residual_external))] += residual_external[:ls.n]

    @classmethod
    def get_resisting_force(cls, model: Model, ls: LinearSystem) -> None:
        ls.set_zero_load()
        runtime = cls.hysteretic_batch_for(model)
        if runtime is not None:
            runtime.copy_resisting_force_to(ls.b)
            for quad in runtime.unmanaged_quads:
                if quad.spring is None or len(quad.aff) <= 6:
                    continue
                quad.set_resisting_force()
                for entry in quad.aff[6]:
                    gdl = entry.gdl - 1
                    if 0 <= gdl < ls.n:
                        ls.sumb(gdl, -quad.status.f * entry.alfa)
            for intf in runtime.unmanaged_interfaces:
                intf.get_resisting_force(ls)
        else:
            # C# Model.GetComputationalElements(WithStiffness) yields
            # Interfaces before Quads.  The production C# run uses the
            # parallel per-DOF path, whose AffElements lists preserve that
            # insertion order.  Accumulate in the same order so round-off in
            # a nearly symmetric nonlinear state cannot select another branch.
            for intf in model.collections.interfaces.values():
                intf.get_resisting_force(ls)
            for quad in model.collections.quads.values():
                if quad.spring is None or len(quad.aff) <= 6:
                    continue
                quad.set_resisting_force()
                for entry in quad.aff[6]:
                    gdl = entry.gdl - 1
                    if 0 <= gdl < ls.n:
                        ls.sumb(gdl, -quad.status.f * entry.alfa)

    @classmethod
    def update_domain(cls, model: Model, ls: LinearSystem, state: IntegratorState) -> None:
        # C# updates interfaces before quads. Quad.ComputeDN depends on the
        # transverse interface spring increments produced in this same trial.
        runtime = cls.hysteretic_batch_for(model)
        if runtime is not None:
            runtime.update_domain(ls.x, state)
            for intf in runtime.unmanaged_interfaces:
                intf.update_domain(ls.x, state)
        else:
            for intf in model.collections.interfaces.values():
                intf.update_domain(ls.x, state)
        if runtime is not None:
            for quad in runtime.unmanaged_quads:
                quad.update_domain(ls, state, model.collections)
        else:
            for quad in model.collections.quads.values():
                quad.update_domain(ls, state, model.collections)

    @classmethod
    def compute_energy(cls, model: Model, initial_elastic=0.0, initial_plastic=0.0) -> tuple[float, float]:
        runtime = cls.hysteretic_batch_for(model)
        eel, ed = runtime.compute_energy(initial_elastic, initial_plastic) if runtime is not None else (initial_elastic, initial_plastic)
        elements = (
            [*runtime.unmanaged_quads, *runtime.unmanaged_interfaces]
            if runtime is not None
            else [
                *model.collections.quads.values(),
                *model.collections.interfaces.values(),
            ]
        )
        for element in elements:
            de_el, de_pl, _ = element.compute_energy()
            eel += float(de_el)
            ed += float(de_pl)
        return eel, ed

    @classmethod
    def find_max_u(cls, model: Model, p: Program) -> None:
        runtime = cls.hysteretic_batch_for(model)
        max_u = 0.0
        max_key = 0
        max_type = ""
        if runtime is not None:
            max_u, max_key = runtime.cached_quad_max_u()
            if max_key:
                max_type = "Quad"
            quads = runtime.unmanaged_quads
        else:
            quads = model.collections.quads.values()
        # C# FindMaxU scans NodeC and MacroElements. Interfaces are explicitly
        # excluded, so their often much larger spring displacement must not
        # terminate an ArcLength analysis at Analysis.MaxU.
        for quad in quads:
            value = abs(float(quad.max_u()))
            if value > max_u:
                max_u = value
                max_key = int(getattr(quad, "key", 0))
                max_type = "Quad"
        p.max_u = max_u
        p.elem_max_u_key = max_key
        p.elem_max_u_type = max_type

    @classmethod
    def get_dof_for_max_displacement(cls, p: Program, model: Model, an: Any) -> int:
        """Port of C# ``ModelManager.GetDofForMaxDisplacement``.

        C# only selects a DOF when ``MasterPoint == -10`` (auto-selection from
        the stiffness-solved shape).  With an explicit master point the graph
        displacement comes from ``GetValueGraphAnalysis``'s model-point branch,
        and the returned DOF id is -1/unused there.
        """
        del model
        master = int(getattr(an, "master_point", -10))
        if master != -10:
            return -1
        if p.u is not None and len(p.u):
            return int(np.argmax(np.abs(p.u)))
        return 0
