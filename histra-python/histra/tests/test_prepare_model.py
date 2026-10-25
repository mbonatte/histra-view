"""C# PrepareModel preprocessing regressions for the supported masonry topology."""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.preprocessing import prepare_model, inspect_solver_readiness
from histra.solver.assembler import assemble_global_k
from histra.solver.load_control import LoadControl
from histra.solver.model_manager import ModelManager
from histra.solver.solve import solve_static_nonlinear

pytestmark = pytest.mark.filterwarnings(
    "ignore::histra.solver.equilibrium.UnsafeEquilibriumWarning"
)

ROOT = Path(__file__).resolve().parents[1]
LOCKED_HRX = ROOT / "model-output" / "model.hrx"


def _interface_signature(model):
    return [
        (
            intf.parent_type_element1,
            intf.parent_element_key1,
            intf.parent_type_element2,
            intf.parent_element_key2,
            intf.face1,
            intf.face2,
            intf.nrow,
            intf.ncol,
        )
        for intf in model.collections.interfaces.values()
    ]


def _reset_to_initial(model) -> None:
    ModelManager.clear_hysteretic_batch()
    for quad in model.collections.quads.values():
        quad.spring.revert_to_start()
        quad.spring.revert_to_last_commit()
    for intf in model.collections.interfaces.values():
        for spring in (*intf.trasv_1, *intf.slid, *intf.slid_out_plan):
            spring.revert_to_start()
            spring.revert_to_last_commit()
        intf.status.init_from_interface(intf)
    ModelManager.compute_k(model, 0.0)


def test_force_regeneration_matches_csharp_locked_topology_and_counts():
    reference = load_model(LOCKED_HRX)
    generated = load_model(LOCKED_HRX)
    reference_signature = _interface_signature(reference)

    report = prepare_model(generated, force=True)

    assert report.prepared
    assert report.gdl == 126
    assert report.quads == 18
    assert report.quad_springs == 18
    assert report.interfaces == 29
    assert report.quad_quad_interfaces == 27
    assert report.restraint_interfaces == 2
    assert report.transverse_springs == 2349
    assert report.sliding_springs == 29
    assert report.out_of_plane_springs == 58
    assert _interface_signature(generated) == reference_signature
    assert inspect_solver_readiness(generated).is_ready

    # C# AfferenceMatrix.SetFromCoefficients uses a 1e-4 cutoff.  Therefore the
    # generated row structure and global DOF sequence must match exactly.
    reference_entries = [
        (entry.gdl, entry.alfa)
        for intf in reference.collections.interfaces.values()
        for row in intf.aff
        for entry in row
    ]
    generated_entries = [
        (entry.gdl, entry.alfa)
        for intf in generated.collections.interfaces.values()
        for row in intf.aff
        for entry in row
    ]
    assert len(generated_entries) == len(reference_entries) == 880
    assert [item[0] for item in generated_entries] == [item[0] for item in reference_entries]
    np.testing.assert_allclose(
        [item[1] for item in generated_entries],
        [item[1] for item in reference_entries],
        rtol=2.0e-6,
        atol=1.5e-5,
    )


def test_regenerated_initial_stiffness_matches_csharp_preprocessed_model():
    reference = load_model(LOCKED_HRX)
    generated = load_model(LOCKED_HRX)
    prepare_model(generated, force=True)

    _reset_to_initial(reference)
    k_reference = assemble_global_k(reference, alfa=0.0).toarray()
    _reset_to_initial(generated)
    k_generated = assemble_global_k(generated, alfa=0.0).toarray()

    relative_error = np.linalg.norm(k_generated - k_reference) / np.linalg.norm(k_reference)
    assert relative_error <= 5.0e-6
    assert np.isfinite(k_generated).all()
    ModelManager.clear_hysteretic_batch()


def test_prepare_model_is_idempotent_and_model_manager_exposes_csharp_entrypoint():
    model = load_model(LOCKED_HRX)
    first = ModelManager.prepare_model(model, force=True)
    interfaces_before = tuple(model.collections.interfaces)
    springs_before = tuple(id(q.spring) for q in model.collections.quads.values())

    second = ModelManager.prepare_model(model)

    assert first.prepared
    assert not second.prepared
    assert tuple(model.collections.interfaces) == interfaces_before
    assert tuple(id(q.spring) for q in model.collections.quads.values()) == springs_before


def test_loaded_locked_hrx_never_reuses_serialized_interface_springs():
    """Fresh Python preparation is mandatory even when HRX reports ready."""
    serialized = load_model(LOCKED_HRX)
    clean = load_model(LOCKED_HRX)
    assert serialized.requires_python_preparation
    assert clean.requires_python_preparation

    saved = serialized.collections.interfaces[1].trasv_1[0]
    saved_id = id(saved)
    saved.e1n = 9.87654321e99  # prove the serialized object cannot leak in

    report = ModelManager.prepare_model(serialized)
    clean_report = ModelManager.prepare_model(clean, force=True)

    assert report.prepared
    assert clean_report.prepared
    assert not serialized.requires_python_preparation
    regenerated = serialized.collections.interfaces[1].trasv_1[0]
    expected = clean.collections.interfaces[1].trasv_1[0]
    assert id(regenerated) != saved_id
    assert regenerated.e1n != pytest.approx(9.87654321e99)
    assert regenerated.e1n == pytest.approx(expected.e1n)


def test_solver_auto_prepares_unlocked_geometry_model(monkeypatch):
    model = load_model(LOCKED_HRX)
    # Recreate the state of an unlocked geometry HRX without depending on a
    # machine-specific fixture path.
    model.is_locked = False
    model.gdl = 0
    model.collections.interfaces.clear()
    for quad in model.collections.quads.values():
        quad.aff = []
        quad.spring = None
        quad.interface_keys = [[] for _ in range(6)]

    original_commit = LoadControl.commit

    def stop_after_first(self, model_, analysis, displacement, dof, changed):
        original_commit(self, model_, analysis, displacement, dof, changed)
        return True

    monkeypatch.setattr(LoadControl, "commit", stop_after_first)
    messages: list[str] = []
    code, rows = solve_static_nonlinear(
        model,
        copy.deepcopy(model.collections.analyses[1]),
        1,
        on_log=messages.append,
    )

    assert code == 0
    assert len(rows) == 1
    assert rows[0]["status"] == "OK"
    assert inspect_solver_readiness(model).is_ready
    assert any("PrepareModel completed" in message for message in messages)
    ModelManager.clear_hysteretic_batch()


def test_regenerated_quad_diagonal_envelopes_match_csharp_locked_model():
    """Catches the C# cosAlfa and SetNonLinearProperties sign conventions."""
    reference = load_model(LOCKED_HRX)
    generated = load_model(LOCKED_HRX)
    prepare_model(generated, force=True)

    np.testing.assert_allclose(
        [quad.spring.cohesion for quad in generated.collections.quads.values()],
        [quad.spring.cohesion for quad in reference.collections.quads.values()],
        rtol=5.0e-7,
        atol=1.0e-5,
    )
    np.testing.assert_allclose(
        [quad.spring.mu for quad in generated.collections.quads.values()],
        [quad.spring.mu for quad in reference.collections.quads.values()],
        rtol=5.0e-7,
        atol=5.0e-7,
    )


def test_distorted_quad_uses_csharp_diagonal_signs_and_yield_search():
    """Representative C# values from Quad key 21 in the 560-DOF benchmark."""
    from histra.elements.quad import Quad

    quad = Quad(
        length=[21.4999847412109, 87.0741653442383, 21.5000019073486, 76.2800369262695],
        sin=[0.951635564897295, 0.953827636154029, 0.979428628995489, 0.980859329226481],
        cos=[-0.307229151648418, 0.300354524701755, 0.201790883599871, -0.194717683504551],
        diago=[83.1839904785156, 85.3733978271484],
        thickness=[288.0, 288.0, 288.0, 288.0],
    )

    assert quad.cos_alfa == pytest.approx(-0.05593786469959976, abs=1.0e-14)
    fy_t, fy_c = quad.set_non_linear_properties(
        1024446.6401416943,
        1620.0,
        782.2222222222222,
        0.029,
        2.68,
    )
    assert fy_t == pytest.approx(212.998674604, rel=1.0e-7)
    assert fy_c == pytest.approx(-197.709832167, rel=1.0e-7)


def test_coulomb_combination_uses_actual_hardening_modulus_not_serialized_default():
    """C# CombinationSpring(SpringCoulomb03) combines ``sp.H`` values.

    ``SetQuadSlidSpring`` does not copy the material's plastic-stiffness ratio
    into the spring's serialized ``PlasticStiffnessRatio`` property, so that
    property remains at its class default 1e-4.  For a material ratio of zero,
    using the property invents a softening branch and changes the committed
    in-plane sliding phase under gravity.
    """
    from histra.preprocessing.prepare_model import (
        _CoulombLaw,
        _combine_coulomb,
        _configure_coulomb,
    )

    law = _CoulombLaw(
        E=1000.0,
        cohesion=0.1,
        mu=1.2,
        plastic_stiffness_ratio=0.0,
        max_tensile_ratio=0.8,
    )
    side1 = _configure_coulomb(k=9000.0, area=10.0, length=1.0, law=law)
    side2 = _configure_coulomb(k=12000.0, area=10.0, length=1.0, law=law)

    # This is the observable C# quirk: the property remains at its default,
    # while the actual envelope hardening modulus is zero.
    assert side1.plastic_stiffness_ratio == pytest.approx(1.0e-4)
    assert side1.h == pytest.approx(0.0)
    assert side2.h == pytest.approx(0.0)

    combined = _combine_coulomb(side1, side2, restrained=False)

    assert combined.h == pytest.approx(0.0)
    assert combined.e2p == pytest.approx(0.0)
    assert combined.mom2p == pytest.approx(combined.mom1p)


def test_disabled_masonry_sliding_builds_linear_elastic_springs():
    """C# uses the scorr* switches, not only SlidingYieldingDomain."""
    from histra.model.masonry_material import MasonryMaterial
    from histra.preprocessing.prepare_model import (
        _combine_sliding,
        _sliding_law,
    )
    from histra.springs.elastic import SpringElastic

    material = MasonryMaterial(
        key=146,
        properties={
            "Gd": "20.8",
            "AlfaShearUser": "0.9",
            "scorrhor": "false",
            "SlidingYieldingDomainHor": "Coulomb",
        },
    )
    law = _sliding_law(material, out_of_plane=False, direction="hor")
    assert law.is_elastic is True

    rigid = SpringElastic(k=-1.0, k_tang=-1.0, area=12.0)
    active = SpringElastic(k=345.0, k_tang=345.0, area=12.0)
    combined = _combine_sliding(rigid, active, restrained=True)
    assert isinstance(combined, SpringElastic)
    assert combined.type_of == "HiStrA.Objects.SpringLinearElastic"
    assert combined.k == 345.0


def test_elastic_to_coulomb_material_stage_transfers_common_committed_state():
    """C# restores a generic SpringStateDB row after changing spring law."""
    from histra.preprocessing.prepare_model import _CoulombLaw, _configure_coulomb
    from histra.solver.restart import transfer_committed_spring_state
    from histra.springs.elastic import SpringElastic

    source = SpringElastic(k=100.0, k_tang=100.0)
    source.set_trial_strain(0.025)
    source.commit()
    target = _configure_coulomb(
        k=80.0,
        area=2.0,
        length=3.0,
        law=_CoulombLaw(
            E=40.0,
            cohesion=0.01,
            mu=0.1,
            plastic_stiffness_ratio=0.001,
            max_tensile_ratio=0.8,
        ),
    )

    transfer_committed_spring_state(source, target)

    assert target._cstrain == source._cstrain
    assert target._cstress == source._cstress
    assert target.k == 80.0
    assert target.umax == [0.0, 0.0]


def test_partial_edge_quad_contacts_are_generated_and_afferenced():
    """C# GIQuadQuad creates two interfaces when one edge meets two half-edges."""
    from histra.model.node import Node
    from histra.elements.quad import Quad
    from histra.preprocessing.prepare_model import (
        _assign_interface_afference,
        _assign_quad_afference,
        _generate_interfaces,
    )
    from histra.types.point import Point

    model = load_model(LOCKED_HRX)
    c = model.collections
    c.nodes.clear()
    c.quads.clear()
    c.interfaces.clear()
    c.restraints.clear()

    coordinates = {
        1: (0.0, 0.0, 0.0),
        2: (2.0, 0.0, 0.0),
        3: (2.0, 0.0, 1.0),
        4: (0.0, 0.0, 1.0),
        5: (0.0, 0.0, -1.0),
        6: (1.0, 0.0, -1.0),
        7: (1.0, 0.0, 0.0),
        8: (2.0, 0.0, -1.0),
    }
    for key, xyz in coordinates.items():
        c.nodes[key] = Node(key=key, point=Point(*xyz), name=str(key))

    normal = [Point(0.0, 1.0, 0.0) for _ in range(4)]
    common = dict(
        thickness=[2.0] * 4,
        normal=normal,
        sin=[1.0] * 4,
        cos=[0.0] * 4,
        reference_e1=(1.0, 0.0, 0.0),
        reference_e2=(0.0, 0.0, 1.0),
        reference_e3=(0.0, -1.0, 0.0),
    )
    c.quads[1] = Quad(
        key=1,
        node_keys=[1, 2, 3, 4],
        length=[2.0, 1.0, 2.0, 1.0],
        g=Point(1.0, 0.0, 0.5),
        **common,
    )
    c.quads[2] = Quad(
        key=2,
        node_keys=[5, 6, 7, 1],
        length=[1.0] * 4,
        g=Point(0.5, 0.0, -0.5),
        **common,
    )
    c.quads[3] = Quad(
        key=3,
        node_keys=[6, 8, 2, 7],
        length=[1.0] * 4,
        g=Point(1.5, 0.0, -0.5),
        **common,
    )

    qq, qr = _generate_interfaces(model)
    assert (qq, qr) == (3, 0)  # two partial contacts plus q2--q3

    partial = [
        intf
        for intf in c.interfaces.values()
        if intf.parent_element_key1 == 1 and intf.face1 == 0
    ]
    assert [(i.parent_element_key2, i.node_keys, i.length) for i in partial] == [
        (2, [7, 1], pytest.approx(1.0)),
        (3, [2, 7], pytest.approx(1.0)),
    ]

    _assign_quad_afference(model)
    _assign_interface_afference(model)
    assert all(len(intf.aff) == 12 for intf in c.interfaces.values())
    assert all(any(row for row in intf.aff) for intf in partial)


def test_partial_edge_afference_interpolates_quad_warping_at_nonvertex_point():
    from histra.model.node import Node
    from histra.elements.quad import Quad
    from histra.preprocessing.prepare_model import (
        _warping_nodal_vectors,
        _warping_vector_at_point,
    )
    from histra.types.point import Point

    model = load_model(LOCKED_HRX)
    c = model.collections
    c.nodes.clear()
    for key, xyz in {
        1: (0.0, 0.0, 0.0),
        2: (2.0, 0.0, 0.0),
        3: (2.0, 0.0, 1.0),
        4: (0.0, 0.0, 1.0),
    }.items():
        c.nodes[key] = Node(key=key, point=Point(*xyz), name=str(key))
    quad = Quad(
        key=1,
        node_keys=[1, 2, 3, 4],
        length=[2.0, 1.2, 2.0, 1.5],
        sin=[0.8, 0.9, 0.7, 0.6],
        cos=[0.6, 0.435889894, 0.714142843, 0.8],
        reference_e1=(1.0, 0.0, 0.0),
        reference_e2=(0.0, 0.0, 1.0),
    )
    nodal = _warping_nodal_vectors(quad)
    midpoint = np.array([1.0, 0.0, 1.0])
    actual = _warping_vector_at_point(quad, midpoint, model)
    import json
    fixture = json.loads((Path(__file__).parent / "fixtures/csharp_midpoint_interpolation_2026_1_1.json").read_text(encoding="utf-8"))
    np.testing.assert_array_equal(nodal, fixture["input"]["nodal"])
    np.testing.assert_array_equal(actual, fixture["native"]["expected"])



def _surface_contact_model():
    """Return a fixture model stripped to geometry-only Quad data."""
    model = load_model(LOCKED_HRX)
    c = model.collections
    c.nodes.clear()
    c.quads.clear()
    c.interfaces.clear()
    c.restraints.clear()
    model.gdl = 0
    model.is_locked = False
    return model


def _add_planar_quad(model, *, key, node_start, y, z0, z1, x0, x1, thickness):
    from histra.elements.quad import Quad
    from histra.model.node import Node
    from histra.types.point import Point

    c = model.collections
    coordinates = (
        (x0, y, z0),
        (x1, y, z0),
        (x1, y, z1),
        (x0, y, z1),
    )
    node_keys = []
    for offset, xyz in enumerate(coordinates):
        node_key = node_start + offset
        c.nodes[node_key] = Node(key=node_key, point=Point(*xyz), name=str(node_key))
        node_keys.append(node_key)
    c.quads[key] = Quad(
        key=key,
        node_keys=node_keys,
        thickness=[thickness] * 4,
        normal=[Point(0.0, 1.0, 0.0) for _ in range(4)],
        length=[x1-x0, z1-z0, x1-x0, z1-z0],
        sin=[1.0] * 4,
        cos=[0.0] * 4,
        g=Point(0.5*(x0+x1), y, 0.5*(z0+z1)),
        reference_e1=(1.0, 0.0, 0.0),
        reference_e2=(0.0, 0.0, 1.0),
        reference_e3=(0.0, -1.0, 0.0),
    )


def test_quad_quad_generation_intersects_broad_faces_4_and_5():
    """C# GIQuadQuad connects adjacent transverse strips through faces 4/5."""
    from histra.preprocessing.prepare_model import (
        _assign_interface_afference,
        _assign_quad_afference,
        _generate_interfaces,
    )

    model = _surface_contact_model()
    # Do not inherit discretisation settings from the benchmark HRX fixture.
    # These values make the 40-unit polygon thickness use the minimum 3 rows,
    # while the 90-unit interface length requires 4 columns.
    model.interface_nrow = 3
    model.interface_imax = 30.0
    # Parent thickness is deliberately much larger than the 40-unit polygon
    # width. C# Interface.Set derives Nrow from the intersection edge, not from
    # the parent Quad thickness.
    _add_planar_quad(
        model, key=1, node_start=1, y=0.0,
        z0=0.0, z1=40.0, x0=0.0, x1=90.0, thickness=100.0,
    )
    _add_planar_quad(
        model, key=2, node_start=5, y=100.0,
        z0=0.0, z1=40.0, x0=0.0, x1=90.0, thickness=100.0,
    )

    qq, qr = _generate_interfaces(model)
    assert (qq, qr) == (1, 0)
    intf = next(iter(model.collections.interfaces.values()))
    assert (intf.face1, intf.face2) == (5, 4)
    assert intf.length == pytest.approx(90.0)
    assert max(intf.thickness) == pytest.approx(40.0)
    assert intf.nrow == 3
    assert intf.ncol == intf.nspring == 4

    _assign_quad_afference(model)
    _assign_interface_afference(model)
    shear_gdls = {
        model.collections.quads[1].aff[6][0].gdl,
        model.collections.quads[2].aff[6][0].gdl,
    }
    interface_gdls = {
        entry.gdl
        for row in intf.aff
        for entry in row
    }
    assert not (shear_gdls & interface_gdls)


def test_quad_quad_generation_detects_offset_lateral_surface_overlap():
    """The contact is an area although the two centre-line edges are offset."""
    from histra.preprocessing.prepare_model import _generate_interfaces

    model = _surface_contact_model()
    _add_planar_quad(
        model, key=1, node_start=1, y=0.0,
        z0=0.0, z1=1.0, x0=0.0, x1=2.0, thickness=2.0,
    )
    _add_planar_quad(
        model, key=2, node_start=5, y=1.5,
        z0=-1.0, z1=0.0, x0=0.0, x1=2.0, thickness=2.0,
    )

    qq, qr = _generate_interfaces(model)
    assert (qq, qr) == (1, 0)
    intf = next(iter(model.collections.interfaces.values()))
    assert (intf.face1, intf.face2) == (0, 2)
    assert intf.length == pytest.approx(2.0)
    assert intf.area() == pytest.approx(1.0)
    # The local interface plane must coincide with z=0.  The previous centroid-
    # based construction tilted e3 and reduced this area to 0.5547001958.
    assert abs(intf.reference_e2[2]) == pytest.approx(1.0)
    assert abs(intf.reference_e3[1]) == pytest.approx(1.0)



def test_broad_face_fibre_stiffness_reverses_opposite_face_like_csharp():
    """Faces 4/5 must map to the reversed opposite broad face."""
    from histra.preprocessing.fibre_geometry import (
        _cell_vertices,
        _fiber_stiffness,
        _fiber_stiffness_batch,
    )
    from histra.preprocessing.prepare_model import _generate_interfaces

    model = _surface_contact_model()
    model.interface_nrow = 2
    model.interface_imax = 1.0e9
    _add_planar_quad(
        model, key=1, node_start=1, y=0.0,
        z0=0.0, z1=2.0, x0=0.0, x1=4.0, thickness=2.0,
    )
    _add_planar_quad(
        model, key=2, node_start=5, y=2.0,
        z0=0.0, z1=2.0, x0=0.0, x1=4.0, thickness=2.0,
    )

    qq, qr = _generate_interfaces(model)
    assert (qq, qr) == (1, 0)
    intf = next(iter(model.collections.interfaces.values()))
    assert (intf.face1, intf.face2) == (5, 4)

    cell = _cell_vertices(intf, 0)
    k1, area1, length1 = _fiber_stiffness(
        model, model.collections.quads[1], intf, cell, 1000.0, intf.face1
    )
    k2, area2, length2 = _fiber_stiffness(
        model, model.collections.quads[2], intf, cell, 1000.0, intf.face2
    )

    assert k1 == pytest.approx(2000.0)
    assert k2 == pytest.approx(2000.0)
    assert area1 == pytest.approx(2.0)
    assert area2 == pytest.approx(2.0)
    assert length1 == pytest.approx(1.0)
    assert length2 == pytest.approx(1.0)

    cells = np.asarray([_cell_vertices(intf, index) for index in range(4)])
    batch1 = _fiber_stiffness_batch(
        model, model.collections.quads[1], intf, cells, 1000.0, intf.face1
    )
    batch2 = _fiber_stiffness_batch(
        model, model.collections.quads[2], intf, cells, 1000.0, intf.face2
    )
    assert batch1[:, 0] == pytest.approx([2000.0] * 4)
    assert batch2[:, 0] == pytest.approx([2000.0] * 4)
    assert batch1[:, 1] == pytest.approx([2.0] * 4)
    assert batch2[:, 1] == pytest.approx([2.0] * 4)
    assert batch1[:, 2] == pytest.approx([1.0] * 4)
    assert batch2[:, 2] == pytest.approx([1.0] * 4)

def test_warping_interpolation_accepts_projected_offset_face_point():
    """C# projects arbitrary lateral-face points to the Quad midsurface."""
    from histra.preprocessing.prepare_model import _warping_vector_at_point

    model = _surface_contact_model()
    _add_planar_quad(
        model, key=1, node_start=1, y=0.0,
        z0=0.0, z1=2.0, x0=0.0, x1=4.0, thickness=2.0,
    )
    quad = model.collections.quads[1]
    # This point lies on an extruded lateral surface but not on a centre-line
    # edge. Its orthogonal projection is the midsurface point (1, 0, 0).
    value = _warping_vector_at_point(
        quad, np.asarray((1.0, 0.75, 0.0)), model
    )
    assert np.isfinite(value).all()


def test_both_horizontal_interface_endpoints_use_parent_face_reference(monkeypatch):
    """Clipping order must not rotate a horizontal/horizontal interface by 90°.

    C#'s NodeListOut starts on the parent-1 reference edge for the Ersino pier
    contacts. Sutherland-Hodgman returns the same polygon with another cyclic
    start, so the parent face direction must be retained explicitly.
    """
    import importlib
    from types import SimpleNamespace

    prepare_model_module = importlib.import_module("histra.preprocessing.prepare_model")
    contact_geometry = importlib.import_module(
        "histra.preprocessing.contact_geometry"
    )

    # Polygon ordering returned by the Python clipper for Ersino Quad
    # 1332 face 5 against Quad 1336 face 4.
    polygon = [
        np.array([128.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 0.0]),
        np.array([0.0, 0.0, -160.0]),
        np.array([128.0, 0.0, -160.0]),
    ]
    created: list[np.ndarray] = []

    monkeypatch.setattr(
        contact_geometry,
        "_quad_face_reference_edge",
        lambda model, quad, face: (
            np.array([0.0, 0.0, -80.0]),
            np.array([128.0, 0.0, -80.0]),
        ),
    )

    def remember_node(model, point, *, tolerance=1.0e-4):
        created.append(np.asarray(point, dtype=float))
        return len(created)

    monkeypatch.setattr(
        contact_geometry, "_find_or_create_geometric_node", remember_node
    )
    q1 = SimpleNamespace(reference_e3=(0.0, 1.0, 0.0))
    q2 = SimpleNamespace(reference_e3=(0.0, 1.0, 0.0))

    _, length = prepare_model_module._prepare_interface_endpoints(
        object(), q1, 5, q2, 4, polygon
    )

    assert length == pytest.approx(128.0)
    np.testing.assert_allclose(np.abs(created[1] - created[0]), [128.0, 0.0, 0.0])


def test_contact_clipping_rejects_coordinate_tolerance_slivers():
    """A 3e-5-wide overlap is a tolerance artefact, not a finite interface."""
    import importlib

    prepare_model_module = importlib.import_module("histra.preprocessing.prepare_model")

    first = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    )
    second = np.array(
        [
            [0.99997, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 1.0, 0.0],
            [0.99997, 1.0, 0.0],
        ]
    )

    assert prepare_model_module._coplanar_quad_intersection(first, second) is None


def test_broad_face_sliding_uses_csharp_direction3_modulus_even_when_ortsc_false():
    """C# SlidingOrthotropyType is always true; ``ortsc`` is not a selector."""
    from histra.preprocessing.prepare_model import _sliding_law
    from histra.model.masonry_material import MasonryMaterial

    material = MasonryMaterial(
        key=18,
        properties={
            "Gd": "50.0",
            "AlfaShearUser": "0.9",
            "ortsc": "false",
            "CohesionSlidingHor": "1.0",
            "CohesionSlidingVert": "2.0",
            "CohesionSlidingDir3": "3.0",
            "FrictionRatioSlidingHor": "0.1",
            "FrictionRatioSlidingVert": "0.2",
            "FrictionRatioSlidingDir3": "0.3",
            "SlidingPlasticStiffnessRatioHor": "0.0",
            "SlidingPlasticStiffnessRatioVert": "0.0",
            "SlidingPlasticStiffnessRatioDir3": "0.0",
        },
    )

    horizontal = _sliding_law(material, out_of_plane=False, direction="hor")
    direction3 = _sliding_law(material, out_of_plane=False, direction="dir3")

    assert horizontal.E == pytest.approx(1000.0)
    assert direction3.E == pytest.approx(50.0)
    assert horizontal.E / direction3.E == pytest.approx(20.0)
    assert direction3.cohesion == pytest.approx(3.0)
    assert direction3.mu == pytest.approx(0.3)


def test_interface_subdivision_preserves_csharp_single_precision_boundary():
    """A nominal 160 mm face must produce six rows, not four."""
    from histra.preprocessing.prepare_model import _interface_division_count

    assert _interface_division_count(159.999959, minimum=4, imax=40.0) == 6
    assert _interface_division_count(128.0, minimum=4, imax=40.0) == 4


def test_force_preparation_always_starts_brand_new_structural_model():
    """Preparing with force mesh creation must purge non-structural nodes and C# artifacts."""
    from histra.model.node import Node
    from histra.types.point import Point
    from histra.elements.interface import Interface

    model = load_model(LOCKED_HRX)
    assert model.requires_python_preparation

    # Inject spurious non-structural node and fake interface
    dummy_key = 99999
    model.collections.nodes[dummy_key] = Node(key=dummy_key, point=Point(999, 999, 999), name="spurious")
    model.collections.interfaces[dummy_key] = Interface(key=dummy_key, name="spurious")
    first_quad = next(iter(model.collections.quads.values()))
    first_quad.spring.e1n = 1.2345e99  # spurious spring value

    report = ModelManager.prepare_model(model, force=True)

    assert report.prepared
    assert not model.requires_python_preparation
    # Verify spurious non-structural node was pruned
    assert dummy_key not in model.collections.nodes
    # Verify spurious interface was wiped
    assert dummy_key not in model.collections.interfaces
    # Verify quad spring was cleanly recreated
    assert first_quad.spring.e1n != pytest.approx(1.2345e99)
    # Verify HRX reference interfaces were preserved for testing/comparison
    assert hasattr(model, "hrx_reference_interfaces")
    assert 1 in model.hrx_reference_interfaces


def test_create_brand_new_model_leaves_hrx_untouched_for_comparison():
    """create_brand_new_model and prepare_brand_new_model leave source HRX intact."""
    source_hrx = load_model(LOCKED_HRX)
    orig_nodes = len(source_hrx.collections.nodes)
    orig_interfaces = len(source_hrx.collections.interfaces)
    assert source_hrx.requires_python_preparation

    new_model, report = ModelManager.prepare_brand_new_model(source_hrx)

    # Source model is 100% untouched for reference comparison
    assert len(source_hrx.collections.nodes) == orig_nodes
    assert len(source_hrx.collections.interfaces) == orig_interfaces
    assert source_hrx.requires_python_preparation

    # Prepared model is ready and independent
    assert report.prepared
    assert not new_model.requires_python_preparation
    assert inspect_solver_readiness(new_model).is_ready


def test_solver_rejects_solving_serialized_hrx_when_auto_prepare_is_false():
    """The solver must NEVER solve on serialized HRX mesh; it is reference-only."""
    from histra.preprocessing.errors import ModelPreparationError

    model = load_model(LOCKED_HRX)
    analysis = copy.deepcopy(model.collections.analyses[1])

    with pytest.raises(ModelPreparationError, match="Cannot solve model using serialized HRX mesh"):
        solve_static_nonlinear(model, analysis, 1, auto_prepare=False)
