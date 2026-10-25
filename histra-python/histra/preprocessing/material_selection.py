"""Masonry material lookup and C# constitutive-law selection/blending.

Owns the immutable material-to-law mapping consumed by model preparation:
cached flexural, diagonal and sliding law construction, the
``ConstitutiveLawCoulomb.PropOrthotropyParameter`` orthotropic blend and the
``Interface.SetSpring`` sliding-law slot selection (broad faces 4/5 use the
direction-3 law; other faces blend horizontal/vertical by the interface/quad
e1 alignment).

C# authorities:

- ``ModelManagement.ComputationalElementsOperations/ConstitutiveLawOperations.cs``
- ``Objects.Material/MasonryMaterial.cs``
- ``Objects.ConstitutiveLaw/ConstitutiveLawCoulomb.cs``

This module must not depend on spring construction; it selects parameters only.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from histra.elements.interface import Interface
from histra.model.masonry_material import MasonryMaterial
from histra.model.model import Model
from histra.preprocessing.constitutive_laws import (
    CoulombLaw as _CoulombLaw,
    HystereticLaw as _HystereticLaw,
    diagonal_flex_law as _diagonal_flex_law,
    flex_law as _flex_law,
    shear_law as _shear_law,
    sliding_law as _sliding_law,
    material_bool,
)
from histra.preprocessing.errors import ModelPreparationError


def _material(model: Model, key: int) -> MasonryMaterial:
    assert model.collections is not None
    try:
        return model.collections.materials[key]
    except KeyError as exc:
        raise ModelPreparationError(f"Missing MasonryMaterial key {key}.") from exc


def _cached_flex_law(
    material: MasonryMaterial,
    *,
    vertical: bool,
    cache: dict[tuple[int, bool], _HystereticLaw] | None,
) -> _HystereticLaw:
    if cache is None:
        return _flex_law(material, vertical=vertical)
    key = (id(material), bool(vertical))
    law = cache.get(key)
    if law is None:
        law = _flex_law(material, vertical=vertical)
        cache[key] = law
    return law


def _flex_alignment(interface_e1, quad_e1) -> tuple[float, float]:
    """ConstitutiveLawBase: Vector3.Dot in Single, then Double sqrt."""
    f = np.float32
    a = np.asarray(interface_e1, dtype=np.float32)
    b = np.asarray(quad_e1, dtype=np.float32)
    dot = f(f(f(a[0] * b[0]) + f(a[1] * b[1])) + f(a[2] * b[2]))
    c1 = min(1.0, abs(float(dot)))
    return c1, math.sqrt(1.0 - c1 * c1)


def _blend_hysteretic_laws(primary: _HystereticLaw, secondary: _HystereticLaw,
                           c1: float, c2: float) -> _HystereticLaw:
    """Literal ConstitutiveLawHysteretic.PropOrthotropyParameter order.

    Keep each value*c*c product in source order. Even equal material values
    must go through the blend: rounding can determine the softening tail sign.
    The source retains the primary unloading/ductility coefficients.
    """
    def blend(name):
        return (getattr(primary, name) * c1 * c1
                + getattr(secondary, name) * c2 * c2)

    changes = {'E': blend('E')}
    primary_elastic = primary.tensile_curve == primary.compressive_curve == 'Elastic'
    secondary_elastic = secondary.tensile_curve == secondary.compressive_curve == 'Elastic'
    if not primary_elastic and not secondary_elastic:
        for name in ('ratio_et_c', 'ratio_et_t', 'fy_c', 'fy_t',
                     'eps_u_c', 'eps_u_t', 'G_t', 'G_c'):
            changes[name] = blend(name)
        if c2 != 0.0:
            changes['tensile_curve'] = secondary.tensile_curve
            changes['compressive_curve'] = secondary.compressive_curve
    return replace(primary, **changes)


def _restraint_reference_e1(model: Model, key: int) -> np.ndarray:
    """Original line-Restraint constructor: Normalize(p2 - p1) in Single."""
    from histra.preprocessing.contact_geometry import _unit_f32, _v
    try:
        restraint = model.collections.restraints[key]
        first, second = (model.collections.nodes[k].point for k in restraint.node_keys)
    except KeyError as exc:
        raise ModelPreparationError(f"Restraint {key} references missing geometry.") from exc
    delta = np.asarray(_v(second), dtype=np.float32) - np.asarray(_v(first), dtype=np.float32)
    axis = _unit_f32(delta, label=f"Restraint {key} reference axis")
    # The line constructor normalizes, then ReferenceSystem.Set normalizes again.
    return _unit_f32(axis, label=f"Restraint {key} reference system")


def _restraint_flex_law(model: Model, key: int, material: MasonryMaterial,
                         intf: Interface, *, cache=None) -> _HystereticLaw:
    horizontal = _cached_flex_law(material, vertical=False, cache=cache)
    vertical = _cached_flex_law(material, vertical=True, cache=cache)
    c1, c2 = _flex_alignment(intf.reference_e1, _restraint_reference_e1(model, key))
    return _blend_hysteretic_laws(horizontal, vertical, c1, c2)


def _interface_flex_law(material: MasonryMaterial, intf: Interface, quad,
                        face: int, *, cache=None) -> _HystereticLaw:
    horizontal = _cached_flex_law(material, vertical=False, cache=cache)
    vertical = _cached_flex_law(material, vertical=True, cache=cache)
    primary, secondary = horizontal, vertical
    if material_bool(material, 'FlexuralOrthotropyType', False):
        if face in (0, 2):
            primary, secondary = vertical, horizontal
        elif face not in (1, 3):
            # The source switch has no blending branch for broad faces 4/5.
            return horizontal
    c1, c2 = _flex_alignment(intf.reference_e1, quad.reference_e1)
    return _blend_hysteretic_laws(primary, secondary, c1, c2)


def _cached_diagonal_laws(
    material: MasonryMaterial,
    cache: dict[int, tuple[_HystereticLaw, _CoulombLaw | _HystereticLaw]] | None,
) -> tuple[_HystereticLaw, _CoulombLaw | _HystereticLaw]:
    if cache is None:
        return _diagonal_flex_law(material), _shear_law(material)
    key = id(material)
    laws = cache.get(key)
    if laws is None:
        laws = (_diagonal_flex_law(material), _shear_law(material))
        cache[key] = laws
    return laws


def _cached_sliding_law(
    material: MasonryMaterial,
    *,
    out_of_plane: bool,
    direction: str,
    cache: dict[tuple[int, bool, str], _CoulombLaw] | None,
) -> _CoulombLaw:
    if cache is None:
        return _sliding_law(
            material, out_of_plane=out_of_plane, direction=direction
        )
    key = (id(material), bool(out_of_plane), direction.casefold())
    law = cache.get(key)
    if law is None:
        law = _sliding_law(
            material, out_of_plane=out_of_plane, direction=direction
        )
        cache[key] = law
    return law


def _blend_coulomb_laws(
    primary: _CoulombLaw,
    secondary: _CoulombLaw,
    c1: float,
    c2: float,
) -> _CoulombLaw:
    """Port ``ConstitutiveLawCoulomb.PropOrthotropyParameter``.

    The C# method modifies only E, Fy_0, Mu and U_r.  Other envelope settings
    remain those of the primary (horizontal) law.
    """
    def blend(name):
        return (getattr(primary, name) * c1 * c1
                + getattr(secondary, name) * c2 * c2)

    changes = {'E': blend('E')}
    # Elastic primary laws interpolate E only. A Coulomb primary with an
    # elastic secondary also retains its own strength/friction/ductility.
    if not primary.is_elastic and not secondary.is_elastic:
        for name in ('cohesion', 'mu', 'ductility'):
            changes[name] = blend(name)
    return replace(primary, **changes)


def _interface_sliding_law(
    model: Model,
    intf: Interface,
    *,
    parent_type: str,
    parent_key: int,
    face: int,
    material: MasonryMaterial,
    out_of_plane: bool,
    vertical: bool,
    cache: dict[tuple[int, bool, str], _CoulombLaw] | None,
    side: int = 1,
) -> _CoulombLaw:
    """Select/blend the same constitutive-law slot used by C# Interface.SetSpring."""
    assert model.collections is not None
    effective_face = int(face)
    quad = None
    if parent_type == "Quad":
        quad = model.collections.quads[parent_key]
    elif parent_type == "Restraint":
        # Interface.SetSpring takes the non-Quad branch for a restraint.
        # Neither the adjacent Quad's axes nor its broad-face slot applies.
        horizontal = _cached_sliding_law(material, out_of_plane=out_of_plane, direction="hor", cache=cache)
        vertical_law = _cached_sliding_law(material, out_of_plane=out_of_plane, direction="vert", cache=cache)
        c1, c2 = _flex_alignment(intf.reference_e1, _restraint_reference_e1(model, parent_key))
        return _blend_coulomb_laws(horizontal, vertical_law, c1, c2)

    # C# ``MasonryMaterial.SlidingOrthotropyType`` is a read-only property
    # that always returns true. ``ortsc`` only controls whether SetIsotropic
    # copies the horizontal parameters into the vertical/dir3 fields; it does
    # not disable directional law selection in Interface.SetSpring.
    orthotropic = True
    if orthotropic and effective_face in (4, 5):
        return _cached_sliding_law(
            material,
            out_of_plane=out_of_plane,
            direction="dir3",
            cache=cache,
        )
    if orthotropic and quad is not None:
        if out_of_plane and side == 2 and parent_type == "Quad":
            # Node-based Interface.SetSpring assigns law2[5] = law2[6]
            # after blending slot 5 on side 2. The final slot is vertical.
            return _cached_sliding_law(
                material, out_of_plane=True, direction="vert", cache=cache)
        horizontal = _cached_sliding_law(
            material,
            out_of_plane=out_of_plane,
            direction="hor",
            cache=cache,
        )
        vertical_law = _cached_sliding_law(
            material,
            out_of_plane=out_of_plane,
            direction="vert",
            cache=cache,
        )
        c1, c2 = _flex_alignment(intf.reference_e1, quad.reference_e1)
        return _blend_coulomb_laws(horizontal, vertical_law, c1, c2)
    return _cached_sliding_law(
        material,
        out_of_plane=out_of_plane,
        direction="hor" if vertical else "vert",
        cache=cache,
    )
