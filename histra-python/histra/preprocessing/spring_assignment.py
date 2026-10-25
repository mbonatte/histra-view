"""Model-dependent spring assignment for Quads and Interfaces.

This module binds the generic spring arithmetic from
:mod:`histra.preprocessing.spring_factory` to concrete Quad/Interface objects:
diagonal Quad springs, per-side transverse cell springs, per-side sliding and
out-of-plane springs, and the C# ``Interface.SetSpring`` combination order.

C# quirks that are intentional and covered by tests:

* ``SpringCoulomb03.SetUltimateDisplacement`` runs only after both sides have
  been combined;
* broad Quad faces (4/5) use the direction-3 sliding modulus;
* the interface plane distance is computed once per Quad side;
* non-restrained transverse cells use the NumPy batch factory, while
  restraint paths keep the C# scalar validation/error order;
* for a restraint interface with a custom material, C# creates both
  out-of-plane entries from the same temporary, so both entries can be the
  same object.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from histra.elements.interface import Interface
from histra.elements.interface_state import InterfaceState
from histra.elements.quad import Quad
from histra.model.masonry_material import MasonryMaterial
from histra.model.model import Model
from histra.preprocessing.constitutive_laws import (
    CoulombLaw as _CoulombLaw,
    HystereticLaw as _HystereticLaw,
    flex_law as _flex_law,
    sliding_law as _sliding_law,
)
from histra.preprocessing.contact_geometry import (
    _cross3,
    _unit,
    _v,
)
from histra.preprocessing.errors import ModelPreparationError
from histra.preprocessing.csharp_fibre_geometry import _csharp_polygon_area, _csharp_polygon_areas
from histra.preprocessing.fibre_geometry import (
    _fiber_stiffness,
    _fiber_stiffness_batch,
    _interface_cells,
)
from histra.preprocessing.material_selection import (
    _cached_diagonal_laws,
    _cached_flex_law,
    _interface_sliding_law,
    _interface_flex_law,
    _restraint_flex_law,
    _material,
)
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.preprocessing.spring_factory import (
    _combine_hysteretic,
    _combine_sliding,
    _configure_combined_hysteretic_batch,
    _configure_coulomb,
    _configure_hysteretic,
    _copy_hysteretic_spring,
    _new_hysteretic_spring,
    _set_coulomb_ultimate,
)


def _distance_to_interface_plane(quad: Quad, intf: Interface) -> float:
    from histra.preprocessing.quad_faces import distance_to_contact_plane

    centre = np.asarray((quad.g.x, quad.g.y, quad.g.z), dtype=np.float32)
    vertices = np.asarray([(p.x, p.y, p.z) for p in intf.vint3d], dtype=np.float32)
    return distance_to_contact_plane(centre, vertices)



def _quad_spring(
    model: Model,
    quad: Quad,
    *,
    law_cache: dict[int, tuple[_HystereticLaw, _CoulombLaw | _HystereticLaw]] | None = None,
) -> SpringCoulomb03 | SpringHysteretic | SpringElastic:
    material = _material(model, quad.material_key)
    flex, shear = _cached_diagonal_laws(material, law_cache)
    length = quad.d_alfa_2d_diag()
    k = quad.get_diagonal_stiffness(flex.E, shear.E)
    if isinstance(shear, _HystereticLaw):
        fy = quad.set_non_linear_properties(k, flex.E, shear.E, shear.fy_t, shear.fy_c)
        if shear.law_type == "ElastoPlasticFractureEnergyFixed":
            from histra.preprocessing.constitutive_laws import material_float
            strength = min(abs(fy[0]), abs(fy[1]))
            ultimate = (strength / k + length * (2.0 / quad.length[3])
                        * (quad.sin[2] / (quad.sin[3] * quad.sin[1] + quad.sin[0] * quad.sin[2]))
                        * material_float(material, "FractureEnergyShear")
                        / material_float(material, "fvk0d"))
            ur = [ultimate, -ultimate]
        else:
            ur = [shear.eps_u_t * length, -shear.eps_u_c * length]
        spring = _new_hysteretic_spring()
        spring.k, spring.fy, spring.ur = k, fy, ur
        spring.length, spring.area = length, k * length / shear.E
        spring.tensile_curve_type = spring.compressive_curve_type = "LinearSoftening"
        spring.kt = [-fy[i] / (ur[i] - fy[i] / k) for i in range(2)]
        spring.alfar, spring.alfau = [0.0, 0.0], [0.0, 0.0]
        spring.initialize()
    elif shear.sub_law in {"Coulomb", "Cacovic"}:
        # Current masonry flexural laws are Hysteretic or LinearElastic,
        # not ConstitutiveLawElastoPlastic, regardless of the settings name.
        fy_compression = 10.0 * shear.cohesion
        fy = quad.set_non_linear_properties(
            k, flex.E, shear.E, shear.cohesion, fy_compression
        )
        cos_alpha = quad.cos_alfa
        if shear.fracture_energy:
            strength = min(abs(fy[0]), abs(fy[1]))
            yield_u = strength/k if k else 0.0
            ur = ((shear.G * quad.compute_volume() - 0.5*strength*yield_u)/strength + yield_u) if strength else length*shear.ductility
        else:
            ur = shear.ductility * length
        area = length * quad.diago[1] / quad.length[0] * float(np.float32(sum(quad.thickness)/4.0))
        spring = _configure_coulomb(
            k=k, area=area, length=length, law=shear,
            cohesion_force=min(abs(fy[0]), abs(fy[1])),
            mu=shear.mu/cos_alpha if cos_alpha else shear.mu,
            ur=ur, hysteretic_type="Takeda",
            plastic_strain=(ur if shear.fracture_energy else shear.plastic_strain * length),
            use_second_branch=shear.plastic_stiffness_ratio2 < 0.0,
            sub_law=shear.sub_law,
        )
    else:
        spring = SpringElastic(type_of="HiStrA.Objects.SpringElastic", k=k, area=k*length/shear.E, length=length)
    spring.key = 0
    spring.parent_key = quad.key
    spring.parent_type = "Quad"
    spring.spring_purpose = "Diagonal"
    return spring


def _side_transverse_spring(model: Model, parent_type: str, parent_key: int, face: int,
                            intf: Interface, cell: Sequence[np.ndarray],
                            material_override: MasonryMaterial | None = None) -> tuple[SpringHysteretic | SpringElastic, _HystereticLaw]:
    assert model.collections is not None
    if parent_type == "Restraint":
        sp = SpringElastic(type_of="HiStrA.Objects.SpringLinearElastic")
        sp.k = -1.0
        sp.area = float(_csharp_polygon_area(np.asarray(cell, dtype=np.float32)))
        if material_override is not None:
            return sp, _restraint_flex_law(model, parent_key, material_override, intf)
        quad_key = (
            intf.parent_element_key1
            if intf.parent_type_element1 == "Quad"
            else intf.parent_element_key2
        )
        material = _material(model, model.collections.quads[quad_key].material_key)
        return sp, _restraint_flex_law(model, parent_key, material, intf)
    quad = model.collections.quads[parent_key]
    material = material_override if material_override is not None else _material(model, quad.material_key)
    law = _interface_flex_law(material, intf, quad, face)
    k, area, length = _fiber_stiffness(model, quad, intf, cell, law.E, face)
    return _configure_hysteretic(k, area, length, law), law


def _interface_parent_material(
    model: Model,
    intf: Interface,
    parent_type: str,
    parent_key: int,
    material_override: MasonryMaterial | None,
) -> MasonryMaterial:
    """Return the material governing one interface side.

    Restraint-side ultimate-displacement rules use the material of the Quad on
    the opposite side in the C# implementation.  Resolving that material once
    also avoids repeating collection lookups for the three sliding springs.
    """
    assert model.collections is not None
    if material_override is not None:
        return material_override
    if parent_type == "Quad":
        return _material(model, model.collections.quads[parent_key].material_key)
    if parent_type != "Restraint":
        raise ModelPreparationError(
            f"Interface {intf.key} has unsupported parent type {parent_type!r}."
        )
    if intf.parent_type_element1 == "Quad":
        quad_key = intf.parent_element_key1
    elif intf.parent_type_element2 == "Quad":
        quad_key = intf.parent_element_key2
    else:
        raise ModelPreparationError(
            f"Interface {intf.key} has a restraint but no Quad parent."
        )
    return _material(model, model.collections.quads[quad_key].material_key)


def _side_sliding_spring(
    model: Model,
    parent_type: str,
    parent_key: int,
    intf: Interface,
    *,
    out_of_plane: bool,
    area: float,
    vertical: bool,
    material_override: MasonryMaterial | None = None,
    law: _CoulombLaw | None = None,
    distance: float | None = None,
    stiffness_area: float | None = None,
) -> SpringCoulomb03 | SpringElastic:
    assert model.collections is not None
    if parent_type == "Restraint":
        if law is not None and law.is_elastic:
            spring = SpringElastic(
                type_of="HiStrA.Objects.SpringLinearElastic", k_tang=-1.0
            )
        else:
            spring = SpringCoulomb03(type_of="HiStrA.Objects.SpringCoulomb03")
        spring.k = -1.0
        spring.area = area
        return spring
    quad = model.collections.quads[parent_key]
    if law is None:
        material = (
            material_override
            if material_override is not None
            else _material(model, quad.material_key)
        )
        law = _sliding_law(
            material, out_of_plane=out_of_plane, vertical=vertical
        )
    if distance is None:
        distance = _distance_to_interface_plane(quad, intf)
    if distance <= 1.0e-12:
        raise ModelPreparationError(
            f"Quad {quad.key}, Interface {intf.key}: zero sliding distance."
        )
    # C# sliding stiffness uses Interface.Area()/2 for both out-of-plane
    # springs, while capacity uses each side temporary's actual polygon area.
    # Those areas differ on tapered interfaces.
    effective_area = area if stiffness_area is None else stiffness_area
    k = law.E * effective_area / distance
    if law.is_elastic:
        return SpringElastic(
            type_of="HiStrA.Objects.SpringLinearElastic",
            k=k,
            k_tang=k,
            area=area,
            length=intf.length,
        )
    spring = _configure_coulomb(
        k=k,
        area=area,
        length=intf.length,
        law=law,
        cohesion_force=area * law.cohesion,
        ur=100000.0,
        hysteretic_type="Initial",
    )
    spring.plastic_strain_ratio = 1.0
    return spring


def _out_of_plane_spring_areas(intf: Interface) -> tuple[float, float]:
    """C# GetAreaSpring for the two bilinear out-of-plane half patches."""
    f = np.float32
    vertices = np.asarray([(p.x, p.y) for p in intf.vint2d], dtype=np.float32)
    areas = []
    for x0, x1 in [(-1., 0.), (0., 1.)]:
        xi = np.array([x0, x1, x1, x0], dtype=np.float32)[:, None]
        eta = np.array([-1., -1., 1., 1.], dtype=np.float32)[:, None]
        points = (vertices[0] * (f(1)-xi) * (f(1)-eta) / f(4)
                  + vertices[1] * (f(1)+xi) * (f(1)-eta) / f(4)
                  + vertices[2] * (f(1)+xi) * (f(1)+eta) / f(4)
                  + vertices[3] * (f(1)-xi) * (f(1)+eta) / f(4))
        # Operations.Area(Vector2[]) accumulates in single precision and order.
        total = f(0)
        for i in range(4):
            j = (i+1) % 4
            total += points[i, 0]*points[j, 1] - points[j, 0]*points[i, 1]
        areas.append(float(abs(total*f(.5))))
    return areas[0], areas[1]


def _transverse_side_properties_batch(
    model: Model, parent_type: str, parent_key: int, face: int,
    intf: Interface, cells: np.ndarray,
    material_override: MasonryMaterial | None = None,
    *,
    vertical: bool | None = None,
    law_cache: dict[tuple[int, bool], _HystereticLaw] | None = None,
) -> tuple[np.ndarray, _HystereticLaw]:
    assert model.collections is not None
    if parent_type == "Restraint":
        props = np.zeros((len(cells), 3), dtype=np.float64)
        props[:, 0] = -1.0
        props[:, 1] = _csharp_polygon_areas(np.asarray(cells, dtype=np.float32))
        if material_override is not None:
            law = _restraint_flex_law(model, parent_key, material_override, intf, cache=law_cache)
        else:
            quad_key = (
                intf.parent_element_key1
                if intf.parent_type_element1 == "Quad"
                else intf.parent_element_key2
            )
            material = _material(
                model, model.collections.quads[quad_key].material_key
            )
            law = _restraint_flex_law(model, parent_key, material, intf, cache=law_cache)
        return props, law
    quad = model.collections.quads[parent_key]
    material = (
        material_override
        if material_override is not None
        else _material(model, quad.material_key)
    )
    law = _interface_flex_law(material, intf, quad, face, cache=law_cache)
    return _fiber_stiffness_batch(
        model, quad, intf, cells, law.E, face
    ), law


def _create_interface_springs(
    model: Model,
    intf: Interface,
    *,
    flex_law_cache: dict[tuple[int, bool], _HystereticLaw] | None = None,
    sliding_law_cache: dict[tuple[int, bool, str], _CoulombLaw] | None = None,
) -> None:
    assert model.collections is not None
    restrained = (
        intf.parent_type_element1 == "Restraint"
        or intf.parent_type_element2 == "Restraint"
    )
    custom_material = None
    if int(intf.material_key) != 0:
        custom_material = _material(model, int(intf.material_key))

    vertical = abs(float(intf.reference_e2[2])) > math.cos(math.radians(45.0))
    cells = _interface_cells(intf)
    cell_count = len(cells)
    props1, law1 = _transverse_side_properties_batch(
        model,
        intf.parent_type_element1,
        intf.parent_element_key1,
        intf.face1,
        intf,
        cells,
        custom_material,
        vertical=vertical,
        law_cache=flex_law_cache,
    )
    props2, law2 = _transverse_side_properties_batch(
        model,
        intf.parent_type_element2,
        intf.parent_element_key2,
        intf.face2,
        intf,
        cells,
        custom_material,
        vertical=vertical,
        law_cache=flex_law_cache,
    )

    if not restrained:
        intf.trasv_1 = _configure_combined_hysteretic_batch(
            props1, law1, props2, law2, interface_key=intf.key, interface=intf
        )
    else:
        intf.trasv_1 = []
        append_transverse = intf.trasv_1.append
        for index in range(cell_count):
            k1, area1, length1 = map(float, props1[index])
            k2, area2, length2 = map(float, props2[index])

            if k1 == -1.0:
                sp1 = SpringElastic(type_of="HiStrA.Objects.SpringLinearElastic")
                sp1.k, sp1.area = -1.0, area1
            else:
                try:
                    sp1 = _configure_hysteretic(k1, area1, length1, law1)
                except ModelPreparationError as exc:
                    raise ModelPreparationError(
                        f"Interface {intf.key}, transverse cell {index}, parent 1 "
                        f"({intf.parent_type_element1} {intf.parent_element_key1}, "
                        f"face {intf.face1}): {exc}"
                    ) from exc
            if k2 == -1.0:
                sp2 = SpringElastic(type_of="HiStrA.Objects.SpringLinearElastic")
                sp2.k, sp2.area = -1.0, area2
            else:
                try:
                    sp2 = _configure_hysteretic(k2, area2, length2, law2)
                except ModelPreparationError as exc:
                    raise ModelPreparationError(
                        f"Interface {intf.key}, transverse cell {index}, parent 2 "
                        f"({intf.parent_type_element2} {intf.parent_element_key2}, "
                        f"face {intf.face2}): {exc}"
                    ) from exc
            if custom_material is not None and restrained:
                # C# Interface.SetSpring: for a custom material on a restraint/Quad
                # interface, clone the non-restraint spring rather than combining
                # it with the rigid restraint-side placeholder.
                spring = _copy_hysteretic_spring(
                    sp2 if intf.parent_type_element1 == "Restraint" else sp1
                )
            else:
                spring = _combine_hysteretic(
                    sp1, sp2, restrained, law1, law2
                )
            spring.key = index
            spring.parent_key = intf.key
            spring.parent_type = "Interface"
            spring.spring_purpose = "Transversal1"
            if not isinstance(spring, SpringElastic):
                spring.length = 0.0
            append_transverse(spring)
    area = intf.area()
    material1 = _interface_parent_material(
        model,
        intf,
        intf.parent_type_element1,
        intf.parent_element_key1,
        custom_material,
    )
    material2 = _interface_parent_material(
        model,
        intf,
        intf.parent_type_element2,
        intf.parent_element_key2,
        custom_material,
    )
    in_law1 = _interface_sliding_law(
        model,
        intf,
        parent_type=intf.parent_type_element1,
        parent_key=intf.parent_element_key1,
        face=intf.face1,
        material=material1,
        out_of_plane=False,
        vertical=vertical,
        cache=sliding_law_cache,
    )
    in_law2 = _interface_sliding_law(
        model,
        intf,
        parent_type=intf.parent_type_element2,
        parent_key=intf.parent_element_key2,
        face=intf.face2,
        material=material2,
        out_of_plane=False,
        vertical=vertical,
        cache=sliding_law_cache,
    )
    out_law1 = _interface_sliding_law(
        model,
        intf,
        parent_type=intf.parent_type_element1,
        parent_key=intf.parent_element_key1,
        face=intf.face1,
        material=material1,
        out_of_plane=True,
        vertical=vertical,
        cache=sliding_law_cache,
    )
    out_law2 = _interface_sliding_law(
        model,
        intf,
        parent_type=intf.parent_type_element2,
        parent_key=intf.parent_element_key2,
        face=intf.face2,
        material=material2,
        out_of_plane=True,
        vertical=vertical,
        cache=sliding_law_cache,
        side=2,
    )

    distance1 = None
    if intf.parent_type_element1 == "Quad":
        distance1 = _distance_to_interface_plane(
            model.collections.quads[intf.parent_element_key1], intf
        )
    distance2 = None
    if intf.parent_type_element2 == "Quad":
        distance2 = _distance_to_interface_plane(
            model.collections.quads[intf.parent_element_key2], intf
        )

    s1 = _side_sliding_spring(
        model,
        intf.parent_type_element1,
        intf.parent_element_key1,
        intf,
        out_of_plane=False,
        area=area,
        vertical=vertical,
        material_override=custom_material,
        law=in_law1,
        distance=distance1,
    )
    s2 = _side_sliding_spring(
        model,
        intf.parent_type_element2,
        intf.parent_element_key2,
        intf,
        out_of_plane=False,
        area=area,
        vertical=vertical,
        material_override=custom_material,
        law=in_law2,
        distance=distance2,
    )
    slid = _combine_sliding(s1, s2, restrained)
    # C# invokes SetUltimateDisplacement after combining both sides.
    if isinstance(slid, SpringCoulomb03):
        _set_coulomb_ultimate(slid, in_law1, in_law2)
    slid.key = 0
    slid.parent_key = intf.key
    slid.parent_type = "Interface"
    slid.spring_purpose = "Slid"
    slid.length = intf.length
    intf.slid = [slid]

    half_area = area / 2.0
    patch_areas = _out_of_plane_spring_areas(intf)
    intf.slid_out_plan = []

    # C# Interface.SetSpring creates the two *side* springs once, then invokes
    # CombinationSpring twice using those same temporaries.  Usually each call
    # returns a fresh combined spring.  For a restraint interface with a
    # custom material, however, the restraint-side placeholder has K == -1 and
    # CombinationSpring returns the active-side temporary itself.  Reusing the
    # temporaries therefore makes SlidOutPlan[0] and [1] the same object.
    # This is observable in the reference HRX (both entries serialize with
    # Key=1) and in the C# spring displacement, which accumulates both
    # interpolation contributions into the shared U field.
    o1 = _side_sliding_spring(
        model,
        intf.parent_type_element1,
        intf.parent_element_key1,
        intf,
        out_of_plane=True,
        area=patch_areas[0],
        stiffness_area=half_area,
        vertical=vertical,
        material_override=custom_material,
        law=out_law1,
        distance=distance1,
    )
    o2 = _side_sliding_spring(
        model,
        intf.parent_type_element2,
        intf.parent_element_key2,
        intf,
        out_of_plane=True,
        area=patch_areas[1],
        stiffness_area=half_area,
        vertical=vertical,
        material_override=custom_material,
        law=out_law2,
        distance=distance2,
    )
    for index in range(2):
        out = _combine_sliding(
            o1,
            o2,
            restrained,
            preserve_single_side_identity=(custom_material is not None and restrained),
        )
        if isinstance(out, SpringCoulomb03):
            _set_coulomb_ultimate(out, out_law1, out_law2)
        out.key = index
        out.parent_key = intf.key
        out.parent_type = "Interface"
        out.spring_purpose = "SlidOutOfPlan"
        out.area = patch_areas[index]
        out.length = intf.length / 2.0
        intf.slid_out_plan.append(out)

    intf.status = InterfaceState()
    intf.status.init_from_interface(intf)
    intf._perf_di = intf._perf_dj = intf._perf_ecc = None
    intf._perf_area = None


def rebuild_interface_springs(
    model: Model,
    interface: Interface | int,
    *,
    flex_law_cache: dict[tuple[int, bool], _HystereticLaw] | None = None,
    sliding_law_cache: dict[tuple[int, bool, str], _CoulombLaw] | None = None,
) -> Interface:
    """Recreate one interface's constitutive definitions from its material key.

    Geometry, topology, DOFs and afference matrices are preserved.  A nonzero
    ``Interface.material_key`` overrides both parent material laws, matching
    C# ``InterfaceOperations.ReSetInterfaces``.

    Optional law caches let callers rebuilding several interfaces reuse the
    same immutable material-law definitions.  Omitting them preserves the
    existing one-interface behaviour.
    """
    if model.collections is None:
        raise ModelPreparationError("Model.collections is not initialized.")
    intf = (
        model.collections.interfaces[int(interface)]
        if isinstance(interface, int)
        else interface
    )
    _create_interface_springs(
        model,
        intf,
        flex_law_cache=flex_law_cache,
        sliding_law_cache=sliding_law_cache,
    )
    dirty = getattr(model, "_perf_initial_stiffness_dirty_interfaces", None)
    if dirty is None:
        dirty = set()
        model._perf_initial_stiffness_dirty_interfaces = dirty
    dirty.add(int(intf.key))
    return intf
