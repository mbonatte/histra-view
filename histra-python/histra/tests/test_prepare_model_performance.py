from __future__ import annotations

from types import SimpleNamespace
import copy
from dataclasses import fields
import itertools

import importlib
from pathlib import Path

import numpy as np
import pytest

from histra.preprocessing.prepare_model import (
    _HystereticLaw,
    _combine_hysteretic,
    _configure_combined_hysteretic,
    _configure_hysteretic,
    _new_hysteretic_spring,
    _set_ultimate_displacement,
    _find_or_create_geometric_node,
)
from histra.types.point import Point

from histra.io.hr_loader import load_model

pm = importlib.import_module("histra.preprocessing.prepare_model")
aff = importlib.import_module("histra.preprocessing.afference")
fg = importlib.import_module("histra.preprocessing.fibre_geometry")
ms = importlib.import_module("histra.preprocessing.material_selection")
sa = importlib.import_module("histra.preprocessing.spring_assignment")
ROOT = Path(__file__).resolve().parents[1]
LOCKED_HRX = ROOT / "model-output" / "model.hrx"


def _law(tensile: str, compressive: str, *, scale: float) -> _HystereticLaw:
    return _HystereticLaw(
        E=12000.0 * scale,
        fy_t=0.25 * scale,
        fy_c=4.5 * scale,
        tensile_curve=tensile,
        compressive_curve=compressive,
        ratio_et_t=0.015,
        ratio_et_c=0.02,
        alfa_r_t=0.1,
        alfa_r_c=0.2,
        alfa_u_t=0.3,
        alfa_u_c=0.4,
        G_t=0.08 * scale,
        G_c=2.5 * scale,
        eps_u_t=0.004,
        eps_u_c=0.012,
        law_type="Flexural",
    )

def _afference_values(model):
    return [
        (entry.gdl, entry.alfa)
        for intf in model.collections.interfaces.values()
        for row in intf.aff
        for entry in row
    ]

@pytest.mark.parametrize(
    ("tensile1", "compressive1", "tensile2", "compressive2"),
    [
        ("LinearSoftening", "LinearSoftening", "LinearSoftening", "LinearSoftening"),
        ("Exponential", "Parabolic", "Exponential", "Parabolic"),
        ("LinearHardening", "LinearHardening", "LinearHardening", "LinearHardening"),
        ("Elastic", "Elastic", "Elastic", "Elastic"),
        ("LinearSoftening", "Parabolic", "Exponential", "LinearSoftening"),
        ("Elastic", "LinearHardening", "LinearHardening", "Elastic"),
        ("Exponential", "Elastic", "LinearSoftening", "Parabolic"),
        ("LinearHardening", "LinearSoftening", "Elastic", "LinearHardening"),
    ],
)
def test_direct_combined_hysteretic_matches_legacy_path(
    tensile1, compressive1, tensile2, compressive2,
):
    law1 = _law(tensile1, compressive1, scale=1.0)
    law2 = _law(tensile2, compressive2, scale=1.3)
    legacy = _combine_hysteretic(
        _configure_hysteretic(1800.0, 2.5, 0.75, law1),
        _configure_hysteretic(2600.0, 3.0, 1.10, law2),
        False,
        law1,
        law2,
    )
    direct = _configure_combined_hysteretic(
        1800.0, 2.5, 0.75, law1,
        2600.0, 3.0, 1.10, law2,
    )

    scalar_fields = (
        "k", "area", "length", "energy_a", "betap", "betan",
        "rot1p", "mom1p", "rot2p", "mom2p", "rot3p", "mom3p",
        "rot1n", "mom1n", "rot2n", "mom2n", "rot3n", "mom3n",
        "e1p", "e2p", "e3p", "eup", "e1n", "e2n", "e3n", "eun",
        "k_tang", "k_tang_committed", "f", "u",
    )
    for name in scalar_fields:
        assert getattr(direct, name) == getattr(legacy, name)
    for name in ("fy", "kt", "ur", "alfar", "alfau", "umax", "uy_corr"):
        np.testing.assert_array_equal(getattr(direct, name), getattr(legacy, name))
    assert direct.tensile_curve_type == legacy.tensile_curve_type
    assert direct.compressive_curve_type == legacy.compressive_curve_type
    assert direct.phase == legacy.phase
    assert direct.t_phase == legacy.t_phase



def test_fast_hysteretic_factory_matches_constructor_and_owns_mutables():
    from histra.springs.hysteretic import SpringHysteretic

    expected = SpringHysteretic(type_of="HiStrA.Objects.SpringHysteretic")
    first = _new_hysteretic_spring()
    second = _new_hysteretic_spring()
    field_names = tuple(field.name for field in fields(SpringHysteretic))

    def state(spring):
        return {name: copy.deepcopy(getattr(spring, name)) for name in field_names}

    assert state(first) == state(expected)
    assert state(second) == state(expected)

    # Every mutable dataclass default must be independent.  This also makes the
    # performance factory fail loudly if a future spring field adds another
    # mutable default that the factory does not recreate.
    for name in field_names:
        value = getattr(expected, name)
        if isinstance(value, (dict, list, set)):
            assert getattr(first, name) is not getattr(second, name)
            assert getattr(first, name) is not getattr(expected, name)

    first.extra["probe"] = "1"
    first.fy[0] = 123.0
    first.kt[1] = 456.0
    first.ur[0] = 789.0
    first.alfau[0] = 0.9
    first.alfar[1] = 0.8
    first.umax[0] = 0.7
    first.uy_corr[1] = 0.6

    assert state(second) == state(expected)


def test_hysteretic_fixed_schema_is_slotted_but_dynamic_overrides_remain_supported():
    from histra.springs.hysteretic import SpringHysteretic

    spring = _new_hysteretic_spring()

    # Fixed numerical/constitutive fields are descriptors rather than entries
    # in a large per-instance dictionary.  A lazy dictionary remains available
    # solely for compatibility with deliberate instance-level overrides.
    assert "k" not in spring.__dict__
    assert "fy" not in spring.__dict__
    spring.get_force = lambda: 12.5
    assert spring.get_force() == 12.5
    assert "get_force" in spring.__dict__
    assert hasattr(SpringHysteretic, "__slots__")



def test_hysteretic_initialization_has_no_redundant_post_reset(monkeypatch):
    from histra.springs.hysteretic import SpringHysteretic

    calls = {"start": 0, "commit": 0}
    original_start = SpringHysteretic.revert_to_start
    original_commit = SpringHysteretic.revert_to_last_commit

    def counted_start(self):
        calls["start"] += 1
        return original_start(self)

    def counted_commit(self):
        calls["commit"] += 1
        return original_commit(self)

    monkeypatch.setattr(SpringHysteretic, "revert_to_start", counted_start)
    monkeypatch.setattr(SpringHysteretic, "revert_to_last_commit", counted_commit)

    spring = _configure_combined_hysteretic(
        1800.0, 2.5, 0.75, _law("LinearSoftening", "Parabolic", scale=1.0),
        2600.0, 3.0, 1.10, _law("Exponential", "LinearSoftening", scale=1.3),
    )

    # SpringHysteretic.initialize() performs exactly one reset of trial state
    # and one reset of committed state.  Preparation must not repeat either.
    assert calls == {"start": 1, "commit": 1}

    before = {
        field_info.name: copy.deepcopy(getattr(spring, field_info.name))
        for field_info in fields(SpringHysteretic)
    }
    before_dynamic = copy.deepcopy(spring.__dict__)
    spring.revert_to_start()
    spring.revert_to_last_commit()
    assert {
        field_info.name: getattr(spring, field_info.name)
        for field_info in fields(SpringHysteretic)
    } == before
    assert spring.__dict__ == before_dynamic


def _set_ultimate_displacement_reference(spring, law1, law2):
    """Pre-optimization scalar oracle; keep its operation order verbatim."""
    gt = [
        law.G_t
        for law in (law1, law2)
        if law.tensile_curve in {"LinearSoftening", "Exponential"}
    ]
    if gt and spring.area and spring.fy[0]:
        g = sum(gt) / len(gt)
        if spring.tensile_curve_type == "LinearSoftening":
            spring.ur[0] = (
                2.0 * g / (spring.fy[0] / spring.area)
                + spring.fy[0] / spring.k
            )
            spring.kt[0] = -spring.fy[0] / (
                spring.ur[0] - spring.fy[0] / spring.k
            )
        elif spring.tensile_curve_type == "Exponential":
            spring.ur[0] = (
                g / (spring.fy[0] / spring.area) + spring.fy[0] / spring.k
            )
        spring.ur[0] = max(spring.ur[0], spring.fy[0] / spring.k)
    else:
        candidates = []
        for law in (law1, law2):
            if law.tensile_curve != "Elastic" and law.fy_t and law.E:
                candidates.append(
                    spring.fy[0]
                    / spring.k
                    * law.eps_u_t
                    / (law.fy_t / law.E)
                )
        if candidates:
            spring.ur[0] = min(candidates)

    gc = [
        law.G_c
        for law in (law1, law2)
        if law.compressive_curve in {"LinearSoftening", "Parabolic"}
    ]
    if gc and spring.area and spring.fy[1]:
        g = sum(gc) / len(gc)
        if spring.compressive_curve_type == "LinearSoftening":
            spring.ur[1] = (
                2.0 * g / (spring.fy[1] / spring.area)
                + spring.fy[1] / spring.k
            )
            spring.kt[1] = -spring.fy[1] / (
                spring.ur[1] - spring.fy[1] / spring.k
            )
        elif spring.compressive_curve_type == "Parabolic":
            spring.ur[1] = (
                3.0 * g / (2.0 * spring.fy[1] / spring.area)
                + 5.0 * spring.fy[1] / (3.0 * spring.k)
            )
        spring.ur[1] = min(spring.ur[1], spring.fy[1] / spring.k)
    else:
        candidates = []
        for law in (law1, law2):
            if law.compressive_curve != "Elastic" and law.fy_c and law.E:
                candidates.append(
                    spring.fy[1]
                    / spring.k
                    * law.eps_u_c
                    / (law.fy_c / law.E)
                )
        if candidates:
            spring.ur[1] = max(candidates)


def test_fracture_ultimate_displacement_fast_path_preserves_operation_order():
    tensile = ("LinearSoftening", "Exponential", "LinearHardening", "Elastic")
    compressive = ("LinearSoftening", "Parabolic", "LinearHardening", "Elastic")

    for t1, c1, t2, c2 in itertools.product(
        tensile, compressive, tensile, compressive
    ):
        # Only the fracture branches retain this pre-optimization reference.
        # Its minimum-candidate ductility selection was not the C# rule;
        # native mixed-law/cyclic fixtures now cover those branches instead.
        if not ({t1, t2} & {'LinearSoftening', 'Exponential'}
                and {c1, c2} & {'LinearSoftening', 'Parabolic'}):
            continue
        law1 = _law(t1, c1, scale=1.0)
        law2 = _law(t2, c2, scale=1.3)
        for output_t, output_c in ((t1, c2), (t2, c1)):
            reference = pm.SpringHysteretic(
                type_of="HiStrA.Objects.SpringHysteretic"
            )
            reference.k = 1800.0
            reference.area = 2.5
            reference.fy = [0.625, -11.25]
            reference.kt = [0.0, 0.0]
            reference.ur = [0.001, -0.001]
            reference.tensile_curve_type = output_t
            reference.compressive_curve_type = output_c
            actual = copy.deepcopy(reference)

            _set_ultimate_displacement_reference(reference, law1, law2)
            _set_ultimate_displacement(actual, law1, law2)

            np.testing.assert_array_equal(actual.ur, reference.ur)
            np.testing.assert_array_equal(actual.kt, reference.kt)


def test_ultimate_displacement_scalar_fast_path_preserves_zero_capacity_branches():
    law1 = _law("LinearHardening", "LinearHardening", scale=1.0)
    law2 = _law("Elastic", "Elastic", scale=1.3)
    reference = pm.SpringHysteretic(type_of="HiStrA.Objects.SpringHysteretic")
    reference.k = 1800.0
    reference.area = 0.0
    reference.fy = [0.0, 0.0]
    reference.kt = [12.5, -3.25]
    reference.ur = [0.125, -0.25]
    reference.tensile_curve_type = "LinearHardening"
    reference.compressive_curve_type = "LinearHardening"
    actual = copy.deepcopy(reference)

    _set_ultimate_displacement_reference(reference, law1, law2)
    _set_ultimate_displacement(actual, law1, law2)

    np.testing.assert_array_equal(actual.ur, reference.ur)
    np.testing.assert_array_equal(actual.kt, reference.kt)


def _assert_fast_spring_copy_matches_deepcopy(source, actual):
    reference = copy.deepcopy(source)
    assert actual is not source
    assert actual.__dict__ == reference.__dict__
    for field_info in fields(type(source)):
        name = field_info.name
        value = getattr(source, name)
        assert getattr(actual, name) == getattr(reference, name), name
        if isinstance(value, (list, dict, set)):
            assert getattr(actual, name) is not value, name


def test_hysteretic_preparation_copy_matches_deepcopy_with_independent_mutables():
    spring = _configure_hysteretic(
        1800.0, 2.5, 0.75,
        _law("LinearSoftening", "LinearSoftening", scale=1.0),
    )
    spring.extra["marker"] = "source"

    actual = pm._copy_hysteretic_spring(spring)

    _assert_fast_spring_copy_matches_deepcopy(spring, actual)


def test_coulomb_preparation_copy_matches_deepcopy_with_independent_mutables():
    law = pm._CoulombLaw(
        E=1000.0, cohesion=2.0, mu=0.45,
        plastic_stiffness_ratio=0.01, max_tensile_ratio=0.8,
    )
    spring = pm._configure_coulomb(
        k=1200.0, area=2.0, length=0.5, law=law
    )
    spring.extra["marker"] = "source"

    actual = pm._copy_coulomb_spring(spring)

    _assert_fast_spring_copy_matches_deepcopy(spring, actual)

def test_geometric_node_spatial_index_preserves_tolerance_reuse():
    nodes = {
        1: SimpleNamespace(point=Point(0.0, 0.0, 0.0)),
        2: SimpleNamespace(point=Point(1.0, 2.0, 3.0)),
    }
    model = SimpleNamespace(collections=SimpleNamespace(nodes=nodes))

    assert _find_or_create_geometric_node(
        model, np.asarray((1.0 + 5.0e-5, 2.0, 3.0))
    ) == 2
    new_key = _find_or_create_geometric_node(
        model, np.asarray((4.0, 5.0, 6.0))
    )
    assert new_key == 3
    # The newly inserted node must be visible through the same spatial index.
    assert _find_or_create_geometric_node(
        model, np.asarray((4.0, 5.0 + 5.0e-5, 6.0))
    ) == new_key

def test_compiled_bilinear_preserves_scalar_evaluation_order():
    if pm.njit is None:
        return

    vertices = np.asarray(
        [
            [10.878649652149079, 632.2133485321168, 2287.9252612892487],
            [1193.974419132613, 1920.230899639857, 1577.1037912572513],
            [363.53635362901946, 1541.9522204102932, 683.404548834184],
            [677.6108838410398, 1097.1673186704572, -525.9304065189515],
        ],
        dtype=np.float64,
    )
    u = 0.6484831921948226
    v = -0.572474073249809
    expected = aff._bilinear(vertices, u, v)
    actual = np.empty(3, dtype=np.float64)

    fg._bilinear_nb(vertices, u, v, actual)

    np.testing.assert_array_equal(actual, expected)


def test_batched_interface_cells_match_scalar_reference_geometry():
    model = load_model(LOCKED_HRX)
    for intf in model.collections.interfaces.values():
        expected = np.asarray(
            [
                fg._cell_vertices(intf, index)
                for index in range(int(intf.nrow) * int(intf.ncol))
            ],
            dtype=np.float64,
        )
        actual = fg._interface_cells(intf)
        np.testing.assert_allclose(actual, expected, rtol=2.0e-14, atol=2.0e-14)
        np.testing.assert_allclose(
            fg._polygon_areas_3d(actual),
            [pm._polygon_area_3d(cell) for cell in expected],
            rtol=2.0e-14,
            atol=2.0e-14,
        )


def test_batched_quad_face_normals_match_scalar_reference_geometry():
    model = load_model(LOCKED_HRX)
    quads = list(model.collections.quads.values())
    faces = np.asarray(
        [np.asarray(pm._quad_vint(model, quad), dtype=float) for quad in quads],
        dtype=np.float64,
    )
    expected = np.asarray(
        [
            [pm._face_normal(faces[qindex, face]) for face in range(6)]
            for qindex in range(len(quads))
        ]
    )
    actual = pm._face_normals_batch(faces)
    np.testing.assert_allclose(actual, expected, rtol=2.0e-14, atol=2.0e-14)


def test_afference_reuses_each_quad_endpoint_warping_once(monkeypatch):
    model = load_model(LOCKED_HRX)
    reference = _afference_values(model)
    pm._assign_quad_afference(model)

    expected_warping_pairs: set[tuple[int, int]] = set()
    for intf in model.collections.interfaces.values():
        for parent_type, parent_key, face in (
            (
                intf.parent_type_element1,
                intf.parent_element_key1,
                intf.face1,
            ),
            (
                intf.parent_type_element2,
                intf.parent_element_key2,
                intf.face2,
            ),
        ):
            if parent_type == "Quad" and face <= 3:
                expected_warping_pairs.update(
                    (int(parent_key), int(node_key))
                    for node_key in intf.node_keys
                )

    # The warping vector is resolved inside the owning afference module, so
    # the interception must patch the owner, not the facade alias.
    calls: list[tuple[int, tuple[float, float, float]]] = []
    original = aff._warping_vector_from_geometry

    def counted(geometry, point):
        calls.append((id(geometry), tuple(float(value) for value in point)))
        return original(geometry, point)

    monkeypatch.setattr(aff, "_warping_vector_from_geometry", counted)
    pm._assign_interface_afference(model)

    assert len(calls) == len(expected_warping_pairs)
    generated = _afference_values(model)
    assert [item[0] for item in generated] == [item[0] for item in reference]
    np.testing.assert_allclose(
        [item[1] for item in generated],
        [item[1] for item in reference],
        rtol=2.0e-6,
        atol=1.5e-5,
    )


def test_interface_sliding_plane_distance_is_computed_once_per_quad_side(
    monkeypatch,
):
    model = load_model(LOCKED_HRX)
    intf = next(
        item
        for item in model.collections.interfaces.values()
        if item.parent_type_element1 == "Quad"
        and item.parent_type_element2 == "Quad"
    )
    expected_quad_sides = sum(
        parent_type == "Quad"
        for parent_type in (
            intf.parent_type_element1,
            intf.parent_type_element2,
        )
    )

    # _create_interface_springs resolves the distance helper inside the
    # spring_assignment owner, so the interception must patch the owner.
    calls: list[int] = []
    original = sa._distance_to_interface_plane

    def counted(quad, interface):
        calls.append(int(quad.key))
        return original(quad, interface)

    monkeypatch.setattr(sa, "_distance_to_interface_plane", counted)
    sa._create_interface_springs(
        model,
        intf,
        flex_law_cache={},
        sliding_law_cache={},
    )

    assert len(calls) == expected_quad_sides
    assert len(intf.slid) == 1
    assert len(intf.slid_out_plan) == 2
    assert len(intf.trasv_1) == int(intf.nrow) * int(intf.ncol)


def test_interface_cell_batch_has_scalar_fallback(monkeypatch):
    model = load_model(LOCKED_HRX)
    intf = next(iter(model.collections.interfaces.values()))
    expected = fg._interface_cells(intf)
    monkeypatch.setattr(fg, "njit", None)
    if hasattr(intf, "_prep_vertices"):
        delattr(intf, "_prep_vertices")
    actual = fg._interface_cells(intf)
    np.testing.assert_allclose(actual, expected, rtol=2.0e-14, atol=2.0e-14)


def test_prepare_model_parses_each_material_law_once_per_orientation(
    monkeypatch,
):
    model = load_model(LOCKED_HRX)
    calls = {"flex": 0, "sliding": 0, "diagonal": 0, "shear": 0}

    # The cached-law helpers resolve the law functions inside the
    # material_selection owner; patching the facade would not intercept.
    original_flex = ms._flex_law
    original_sliding = ms._sliding_law
    original_diagonal = ms._diagonal_flex_law
    original_shear = ms._shear_law

    def counted_flex(*args, **kwargs):
        calls["flex"] = 1
        return original_flex(*args, **kwargs)

    def counted_sliding(*args, **kwargs):
        calls["sliding"] = 1
        return original_sliding(*args, **kwargs)

    def counted_diagonal(*args, **kwargs):
        calls["diagonal"] = 1
        return original_diagonal(*args, **kwargs)

    def counted_shear(*args, **kwargs):
        calls["shear"] = 1
        return original_shear(*args, **kwargs)

    monkeypatch.setattr(ms, "_flex_law", counted_flex)
    monkeypatch.setattr(ms, "_sliding_law", counted_sliding)
    monkeypatch.setattr(ms, "_diagonal_flex_law", counted_diagonal)
    monkeypatch.setattr(ms, "_shear_law", counted_shear)

    pm.prepare_model(model, force=True)

    quad_material_keys = {
        int(quad.material_key) for quad in model.collections.quads.values()
    }
    interface_material_keys = {
        int(intf.material_key)
        for intf in model.collections.interfaces.values()
        if int(intf.material_key) != 0
    }
    interface_material_keys.update(quad_material_keys)

    assert calls["diagonal"] <= len(quad_material_keys)
    assert calls["shear"] <= len(quad_material_keys)
    assert calls["flex"] <= 2 * len(interface_material_keys)
    assert calls["sliding"] <= 4 * len(interface_material_keys)
