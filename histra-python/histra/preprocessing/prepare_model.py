"""Port of the Quad/Restraint subset of C# ``ModelManager.PrepareModel``.

The original desktop preprocessor supports many computational element types.
This module implements the masonry-Quad solver path needed by the supplied
RailBridge models, including the C# six-face surface-intersection topology:

* four-node masonry ``Quad`` elements;
* coplanar polygonal intersections on all six Quad faces;
* fixed line ``Restraint`` contacts already associated with a Quad face;
* masonry diagonal, transverse, in-plane and out-of-plane springs;
* global DOF numbering and Quad/Interface afference matrices.

Unsupported topologies fail explicitly rather than producing a partial model.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - scalar fallback remains available
    njit = None

from histra.elements.interface import Interface
from histra.elements.quad import Quad
from histra.elements.interface_state import InterfaceState
from histra.elements.quad_state import QuadState
from histra.model.masonry_material import MasonryMaterial
from histra.model.model import Model
from histra.preprocessing.contact_geometry import (
    _CONTACT_ANGLE_TOLERANCE,
    _CONTACT_AREA_TOLERANCE,
    _CONTACT_BATCH_SIZE,
    _CONTACT_DISTANCE_TOLERANCE,
    _TOL,
    _build_geometric_node_index,
    _clean_clipped_polygon,
    _clip_convex_quad_2d,
    _convex_quad_overlap_prefilter_batch,
    _coplanar_quad_intersection,
    _coplanar_quad_intersection_prechecked,
    _cross3,
    _cross3_f32,
    _cross_2d,
    _dot3_f32,
    _f32,
    _face_normal,
    _face_normals_batch,
    _find_or_create_geometric_node,
    _generate_interfaces,
    _interface_division_count,
    _line_intersection_2d,
    _make_interface_geometry,
    _norm3,
    _norm3_f32,
    _node_bucket,
    _p,
    _passes_csharp_lateral_area_filter,
    _polygon_area_2d,
    _polygon_area_3d,
    _polygon_edge_at_point,
    _prepare_interface_endpoints,
    _quad_contact_pairs,
    _quad_face_reference_edge,
    _quad_face_vertices,
    _quad_lateral_face_vertices,
    _quad_vint,
    _unit,
    _unit_f32,
    _v,
)
from histra.preprocessing.afference import (
    _QuadAfferenceGeometry,
    _assign_interface_afference,
    _assign_quad_afference,
    _bilinear,
    _bilinear_component_f32_nb,
    _bilinear_f32,
    _inverse_bilinear,
    _inverse_bilinear_f32,
    _inverse_bilinear_f32_bisection_reference,
    _inverse_bilinear_f32_nb,
    _inverse_bilinear_f32_python,
    _point_afference,
    _quad_afference_geometry,
    _rotation_afference,
    _warping_nodal_vectors,
    _warping_vector_at_point,
    _warping_vector_from_geometry,
)
from histra.preprocessing.fibre_geometry import (
    _bilinear_nb,
    _cell_vertices,
    _cross3_nb,
    _dot3_nb,
    _fiber_stiffness,
    _fiber_stiffness_batch,
    _fiber_stiffness_batch_nb,
    _interface_cells,
    _interface_cells_nb,
    _inverse_bilinear_nb,
    _norm3_nb,
    _polygon_areas_3d,
    _polygon_areas_3d_nb,
)
from histra.preprocessing.constitutive_laws import (
    CoulombLaw as _CoulombLaw,
    HystereticLaw as _HystereticLaw,
    diagonal_flex_law as _diagonal_flex_law,
    flex_law as _flex_law,
    material_bool as _bool,
    material_float as _float,
    shear_law as _shear_law,
    sliding_law as _sliding_law,
)
from histra.preprocessing.errors import ModelPreparationError
from histra.preprocessing.spring_factory import (
    _combine_coulomb,
    _combine_hysteretic,
    _combine_sliding,
    _configure_combined_hysteretic,
    _configure_combined_hysteretic_batch,
    _configure_coulomb,
    _configure_hysteretic,
    _copy_coulomb_spring,
    _copy_hysteretic_spring,
    _hysteretic_side_definition,
    _new_hysteretic_spring,
    _series,
    _set_coulomb_ultimate,
    _set_ultimate_displacement,
)
from histra.preprocessing.material_selection import (
    _blend_coulomb_laws,
    _cached_diagonal_laws,
    _cached_flex_law,
    _cached_sliding_law,
    _interface_sliding_law,
    _material,
)
from histra.preprocessing.spring_assignment import (
    _create_interface_springs,
    _distance_to_interface_plane,
    _interface_parent_material,
    _quad_spring,
    _side_sliding_spring,
    _side_transverse_spring,
    _transverse_side_properties_batch,
    rebuild_interface_springs,
)
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic


@dataclass(frozen=True)
class PreparationReport:
    prepared: bool
    gdl: int
    quads: int
    quad_springs: int
    interfaces: int
    quad_quad_interfaces: int
    restraint_interfaces: int
    transverse_springs: int
    sliding_springs: int
    out_of_plane_springs: int


def reset_to_brand_new_structural_model(model: Model) -> None:
    """Reset model to a brand-new, unprepared structural model state.

    Removes all pre-baked C# interfaces, springs, afferences, and extra
    geometric nodes from a serialized HRX, retaining ONLY the raw structural
    definition: structural corner nodes, Quads, Restraints, Materials, Loads,
    and Analyses.
    """
    if model.collections is None:
        raise ModelPreparationError("Model.collections is not initialized.")
    c = model.collections

    # If the model had serialized HRX interfaces, save them as reference for testing/comparison
    if c.interfaces and getattr(model, "requires_python_preparation", False):
        if not hasattr(model, "hrx_reference_interfaces"):
            model.hrx_reference_interfaces = dict(c.interfaces)

    # Retain ONLY structural nodes referenced by Quads and Restraints
    structural_node_keys: set[int] = set()
    for quad in c.quads.values():
        structural_node_keys.update(quad.node_keys)
    for restraint in c.restraints.values():
        for k in getattr(restraint, "node_keys", ()):
            if k > 0:
                structural_node_keys.add(k)
        for k in getattr(restraint, "node_c_keys", ()):
            if k > 0 and k in c.nodes:
                structural_node_keys.add(k)

    # Prune non-structural nodes (e.g. C#-generated interface midpoints)
    c.nodes = {k: c.nodes[k] for k in structural_node_keys if k in c.nodes}

    # Clear all generated interfaces
    c.interfaces.clear()

    # Reset quads to fresh state
    for quad in c.quads.values():
        quad.spring = None
        quad.aff = []
        quad.status = QuadState()
        quad.interface_keys = [[] for _ in range(6)]
        quad._perf_aff_pairs = None
        quad._perf_dn_edges = None
        quad._perf_dn_areas = None

    model.gdl = 0
    model.is_locked = False

    # Clear spatial and stiffness caches
    for cache_name in (
        "_perf_element_stiffness_topology_signature",
        "_perf_element_stiffness_alfa",
        "_perf_initial_stiffness_dirty_interfaces",
        "_prep_geometric_node_index",
    ):
        if hasattr(model, cache_name):
            delattr(model, cache_name)


def create_brand_new_model(source: Model) -> Model:
    """Create an independent brand-new structural model from a source HRX model.

    The original source model remains completely untouched with its serialized
    C# reference data intact for testing and comparison.
    """
    import copy
    new_model = copy.deepcopy(source)
    reset_to_brand_new_structural_model(new_model)
    new_model.requires_python_preparation = True
    return new_model


def prepare_model(
    model: Model, *, force: bool = False, use_cache: bool | None = None
) -> PreparationReport:
    """Prepare an unlocked Quad/Restraint HRX for the nonlinear solver.

    The operation is idempotent for an already prepared model unless ``force``
    is true.  Existing generated interfaces/springs are replaced only when a
    fresh preparation is required.
    """
    if model.collections is None:
        raise ModelPreparationError("Model.collections is not initialized.")

    # AdvancedOptionsDefault stores both tolerances as Single. Normalize
    # programmatically supplied settings before contact and node comparisons.
    model.geometry_tolerance_node = float(np.float32(model.geometry_tolerance_node))
    model.geometry_tolerance_plane = float(np.float32(model.geometry_tolerance_plane))

    from .cache import is_cache_enabled, load_prepared_cache, save_prepared_cache

    cache_active = is_cache_enabled(use_cache)
    source_path = getattr(model, "source_path", None)

    if cache_active and source_path:
        cached = load_prepared_cache(source_path)
        if cached is not None:
            cached_model, report = cached
            model.collections = cached_model.collections
            model.gdl = cached_model.gdl
            model.is_locked = True
            model.requires_python_preparation = False
            return report

    # Serialized HRX interface/spring objects belong to the C# reference, not
    # to a Python computational model.  Do not let the usual idempotent-ready
    # shortcut preserve them.  This is intentionally enforced here (rather
    # than only in runners) so direct callers cannot accidentally bypass it.
    force = bool(force or getattr(model, "requires_python_preparation", False))
    from .validation import inspect_solver_readiness
    current = inspect_solver_readiness(model)
    if current.is_ready and not force:
        c = model.collections
        return PreparationReport(
            prepared=False, gdl=model.gdl, quads=len(c.quads),
            quad_springs=sum(q.spring is not None for q in c.quads.values()),
            interfaces=len(c.interfaces),
            quad_quad_interfaces=sum(i.parent_type_element1=="Quad" and i.parent_type_element2=="Quad" for i in c.interfaces.values()),
            restraint_interfaces=sum("Restraint" in (i.parent_type_element1,i.parent_type_element2) for i in c.interfaces.values()),
            transverse_springs=sum(len(i.trasv_1) for i in c.interfaces.values()),
            sliding_springs=sum(len(i.slid) for i in c.interfaces.values()),
            out_of_plane_springs=sum(len(i.slid_out_plan) for i in c.interfaces.values()),
        )
    # Mesh creation must ALWAYS start from a brand-new structural model.
    # Purge any pre-baked C# interfaces, springs, afferences, and extra nodes.
    reset_to_brand_new_structural_model(model)
    c = model.collections
    if not c.quads:
        raise ModelPreparationError("PrepareModel currently requires at least one Quad.")
    diagonal_law_cache: dict[
        int, tuple[_HystereticLaw, _CoulombLaw | _HystereticLaw]
    ] = {}
    flex_law_cache: dict[tuple[int, bool], _HystereticLaw] = {}
    sliding_law_cache: dict[
        tuple[int, bool, str], _CoulombLaw
    ] = {}

    from .quad_geometry import refresh_quad_geometry
    refresh_quad_geometry(model)
    _assign_quad_afference(model)
    for quad in c.quads.values():
        quad.status = QuadState()
        quad.spring = _quad_spring(
            model, quad, law_cache=diagonal_law_cache
        )
        quad._perf_aff_pairs = None
        quad._perf_dn_edges = None
        quad._perf_dn_areas = None
    qq, qr = _generate_interfaces(model)
    _assign_interface_afference(model)
    for intf in c.interfaces.values():
        _create_interface_springs(
            model,
            intf,
            flex_law_cache=flex_law_cache,
            sliding_law_cache=sliding_law_cache,
        )
    model.is_locked = True
    report = inspect_solver_readiness(model)
    if not report.is_ready:
        raise ModelPreparationError(
            "Python PrepareModel produced an incomplete model: " + "; ".join(report.missing)
        )
    model.requires_python_preparation = False
    report = PreparationReport(
        prepared=True, gdl=model.gdl, quads=len(c.quads),
        quad_springs=sum(q.spring is not None for q in c.quads.values()),
        interfaces=len(c.interfaces), quad_quad_interfaces=qq, restraint_interfaces=qr,
        transverse_springs=sum(len(i.trasv_1) for i in c.interfaces.values()),
        sliding_springs=sum(len(i.slid) for i in c.interfaces.values()),
        out_of_plane_springs=sum(len(i.slid_out_plan) for i in c.interfaces.values()),
    )
    if cache_active and source_path:
        save_prepared_cache(model, report, source_path)
    return report

