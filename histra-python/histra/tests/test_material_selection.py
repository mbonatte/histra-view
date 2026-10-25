"""Owner-level tests for preprocessing.material_selection (C# parity)."""

import numpy as np
import pytest

from histra.elements.interface import Interface
from histra.elements.quad import Quad
from histra.model.masonry_material import MasonryMaterial
from histra.model.model import Collections, Model
from histra.preprocessing import material_selection as ms
from histra.preprocessing.constitutive_laws import sliding_law


def _material(**overrides) -> MasonryMaterial:
    properties = {
        "Gd": "1000.0",
        "AlfaShearUser": "0.9",
        "CohesionSlidingHor": "0.30",
        "FrictionRatioSlidingHor": "0.70",
        "SlidingPlasticStiffnessRatioHor": "0.10",
        "CohesionSlidingVert": "0.50",
        "FrictionRatioSlidingVert": "0.40",
        "SlidingPlasticStiffnessRatioVert": "0.20",
        "CohesionSlidingDir3": "0.80",
        "FrictionRatioSlidingDir3": "0.90",
        "SlidingPlasticStiffnessRatioDir3": "0.30",
        "scorrhor": "true",
        "scorrvert": "true",
        "scorrDir3": "true",
    }
    properties.update(overrides)
    return MasonryMaterial(key=7, properties=properties)


def _model_with_quad(key: int, e1) -> Model:
    model = Model()
    model.collections = Collections()
    model.collections.quads[key] = Quad(
        key=key,
        node_keys=(1, 2, 3, 4),
        thickness=[1.0] * 4,
        normal=[None] * 4,
        length=[1.0] * 4,
        sin=[0.0] * 4,
        cos=[1.0] * 4,
        g=None,
        reference_e1=e1,
        reference_e2=(0.0, 0.0, 1.0),
        reference_e3=(0.0, -1.0, 0.0),
    )
    return model


def _interface(e1, *, parent_type1="Quad", parent_key1=1, face1=1) -> Interface:
    intf = Interface(length=2.0, nrow=1, ncol=1, nspring=3)
    intf.reference_e1 = np.asarray(e1, dtype=float)
    intf.reference_e2 = np.asarray((0.0, 0.0, 1.0), dtype=float)
    intf.reference_e3 = np.asarray((0.0, -1.0, 0.0), dtype=float)
    intf.parent_type_element1 = parent_type1
    intf.parent_element_key1 = parent_key1
    intf.face1 = face1
    intf.parent_type_element2 = "None"
    intf.parent_element_key2 = 0
    intf.face2 = 0
    return intf


def test_cached_sliding_law_parses_once_per_material_and_direction(monkeypatch):
    material = _material()
    calls = []
    original = ms._sliding_law

    def counted(*args, **kwargs):
        calls.append(kwargs.get("direction"))
        return original(*args, **kwargs)

    monkeypatch.setattr(ms, "_sliding_law", counted)
    cache: dict = {}
    first = ms._cached_sliding_law(
        material, out_of_plane=False, direction="hor", cache=cache
    )
    second = ms._cached_sliding_law(
        material, out_of_plane=False, direction="hor", cache=cache
    )
    third = ms._cached_sliding_law(
        material, out_of_plane=False, direction="vert", cache=cache
    )

    assert calls == ["hor", "vert"]
    assert second is first
    assert third is not first
    # The cache key carries the exact direction plus the material identity and
    # the out-of-plane flag, so one parse happens per (material, oop, direction).
    assert set(cache) == {(id(material), False, "hor"), (id(material), False, "vert")}


def test_cached_flex_law_caches_by_material_identity_and_orientation(monkeypatch):
    material = _material(
        Ehor=8.0,
        Ever=16.0,
        FtmHor=2.0,
        FtmVer=4.0,
        FmHor=6.0,
        FmVer=12.0,
        TensileCurveType="LinearSoftening",
        TensileCurveTypeVertical="Exponential",
        CompressiveCurveType="LinearHardening",
        CompressiveCurveTypeVertical="Parabolic",
    )
    calls = []
    original = ms._flex_law

    def counted(*args, **kwargs):
        calls.append(kwargs.get("vertical"))
        return original(*args, **kwargs)

    monkeypatch.setattr(ms, "_flex_law", counted)
    cache: dict = {}
    horizontal = ms._cached_flex_law(material, vertical=False, cache=cache)
    horizontal_again = ms._cached_flex_law(material, vertical=False, cache=cache)
    vertical = ms._cached_flex_law(material, vertical=True, cache=cache)

    assert calls == [False, True]
    assert horizontal_again is horizontal
    assert vertical is not horizontal
    assert vertical.E == 16.0
    assert set(cache) == {(id(material), False), (id(material), True)}


def test_broad_faces_4_and_5_select_the_direction3_law():
    model = _model_with_quad(1, (1.0, 0.0, 0.0))
    intf = _interface((1.0, 0.0, 0.0), face1=4)
    material = _material()
    cache: dict = {}

    law = ms._interface_sliding_law(
        model,
        intf,
        parent_type="Quad",
        parent_key=1,
        face=4,
        material=material,
        out_of_plane=False,
        vertical=False,
        cache=cache,
    )

    assert law == sliding_law(material, out_of_plane=False, direction="dir3")


def test_orthotropic_blending_follows_interface_quad_e1_alignment():
    material = _material()
    horizontal = sliding_law(material, out_of_plane=False, direction="hor")
    vertical = sliding_law(material, out_of_plane=False, direction="vert")
    # E is shared by both directions (it derives from Gd); cohesion differs.
    assert horizontal.cohesion != vertical.cohesion

    # Parallel e1 systems: c1 = 1, c2 = 0 -> the pure horizontal law.
    parallel_model = _model_with_quad(1, (1.0, 0.0, 0.0))
    parallel = ms._interface_sliding_law(
        parallel_model,
        _interface((1.0, 0.0, 0.0)),
        parent_type="Quad",
        parent_key=1,
        face=1,
        material=material,
        out_of_plane=False,
        vertical=False,
        cache={},
    )
    assert parallel == horizontal

    # Orthogonal e1 systems: c1 = 0, c2 = 1 -> E/cohesion/mu/ductility come
    # from the vertical law, but every other envelope setting stays with the
    # primary (horizontal) law, exactly as C# PropOrthotropyParameter does.
    orthogonal_model = _model_with_quad(1, (0.0, 1.0, 0.0))
    orthogonal = ms._interface_sliding_law(
        orthogonal_model,
        _interface((1.0, 0.0, 0.0)),
        parent_type="Quad",
        parent_key=1,
        face=1,
        material=material,
        out_of_plane=False,
        vertical=False,
        cache={},
    )
    assert orthogonal.E == vertical.E
    assert orthogonal.cohesion == vertical.cohesion
    assert orthogonal.mu == vertical.mu
    assert (
        orthogonal.plastic_stiffness_ratio == horizontal.plastic_stiffness_ratio
    )
    assert orthogonal.max_tensile_ratio == horizontal.max_tensile_ratio
    assert orthogonal.is_elastic == horizontal.is_elastic


def test_orthotropic_blend_weights_match_csharp_proporthotropy():
    material = _material()
    horizontal = sliding_law(material, out_of_plane=False, direction="hor")
    vertical = sliding_law(material, out_of_plane=False, direction="vert")

    # |e1_intf . e1_quad| = cos(45 degrees) -> w1 = 0.5, w2 = 0.5.
    model = _model_with_quad(1, (np.cos(np.pi / 4), np.sin(np.pi / 4), 0.0))
    blended = ms._interface_sliding_law(
        model,
        _interface((1.0, 0.0, 0.0)),
        parent_type="Quad",
        parent_key=1,
        face=1,
        material=material,
        out_of_plane=False,
        vertical=False,
        cache={},
    )

    assert blended.E == pytest.approx(0.5 * horizontal.E + 0.5 * vertical.E)
    assert blended.cohesion == pytest.approx(
        0.5 * horizontal.cohesion + 0.5 * vertical.cohesion
    )
    assert blended.mu == pytest.approx(0.5 * horizontal.mu + 0.5 * vertical.mu)


def test_orthotropic_blend_keeps_primary_runtime_law_type():
    primary = ms._CoulombLaw(
        E=10.0,
        cohesion=1.0,
        mu=0.5,
        plastic_stiffness_ratio=0.2,
        max_tensile_ratio=0.8,
        is_elastic=True,
    )
    secondary = ms._CoulombLaw(
        E=30.0,
        cohesion=3.0,
        mu=0.1,
        plastic_stiffness_ratio=0.4,
        max_tensile_ratio=0.9,
        is_elastic=False,
    )
    blended = ms._blend_coulomb_laws(primary, secondary, 0.6, 0.8)

    # PropOrthotropyParameter modifies E, cohesion, mu and ductility only; the
    # primary law's runtime type and envelope settings must survive.
    assert blended.is_elastic is True
    assert blended.hysteretic_type == primary.hysteretic_type
    assert blended.sub_law == primary.sub_law
    assert blended.plastic_stiffness_ratio == primary.plastic_stiffness_ratio
    assert blended.max_tensile_ratio == primary.max_tensile_ratio
    assert blended.E == pytest.approx(10.0 * 0.36 + 30.0 * 0.64)
    assert blended.ductility == pytest.approx(
        primary.ductility * 0.36 + secondary.ductility * 0.64
    )


def test_restraint_parent_uses_its_own_axis_for_law_selection():
    material = _material()
    model = _model_with_quad(3, (1.0, 0.0, 0.0))
    restraint_parent = _interface((1.0, 0.0, 0.0), parent_type1="Restraint")
    restraint_parent.parent_element_key1 = 0
    restraint_parent.parent_type_element1 = "Restraint"
    restraint_parent.parent_type_element2 = "Quad"
    restraint_parent.parent_element_key2 = 3
    restraint_parent.face2 = 2

    from histra.model.restraint import Restraint
    from histra.model.node import Node
    from histra.types.point import Point
    model.collections.nodes = {1: Node(point=Point()), 2: Node(point=Point(0.,1.,0.))}
    model.collections.restraints[99] = Restraint(key=99, node_keys=[1,2])
    via_restraint = ms._interface_sliding_law(
        model,
        restraint_parent,
        parent_type="Restraint",
        parent_key=99,
        face=0,
        material=material,
        out_of_plane=False,
        vertical=False,
        cache={},
    )
    via_quad = ms._interface_sliding_law(
        model,
        restraint_parent,
        parent_type="Quad",
        parent_key=3,
        face=2,
        material=material,
        out_of_plane=False,
        vertical=False,
        cache={},
    )

    assert via_restraint.cohesion == float(np.float32(.5))
    assert via_quad.cohesion == float(np.float32(.3))


def test_missing_material_key_fails_explicitly():
    model = Model()
    model.collections = Collections()
    with pytest.raises(ms.ModelPreparationError, match="Missing MasonryMaterial key 5"):
        ms._material(model, 5)
