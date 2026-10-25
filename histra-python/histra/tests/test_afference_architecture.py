"""Architecture checks for the extracted afference owner."""

import importlib.util

import histra.preprocessing.afference as afference


def test_prepare_model_compatibility_facade_reexports_afference():
    prepare_model = importlib.import_module("histra.preprocessing.prepare_model")
    names = (
        "_QuadAfferenceGeometry",
        "_assign_interface_afference",
        "_assign_quad_afference",
        "_bilinear",
        "_bilinear_component_f32_nb",
        "_bilinear_f32",
        "_inverse_bilinear",
        "_inverse_bilinear_f32",
        "_inverse_bilinear_f32_bisection_reference",
        "_inverse_bilinear_f32_nb",
        "_inverse_bilinear_f32_python",
        "_point_afference",
        "_quad_afference_geometry",
        "_rotation_afference",
        "_warping_nodal_vectors",
        "_warping_vector_at_point",
        "_warping_vector_from_geometry",
    )

    for name in names:
        assert getattr(prepare_model, name) is getattr(afference, name)


def test_afference_owner_has_no_reverse_dependency_on_prepare_model():
    source = importlib.util.find_spec(
        "histra.preprocessing.afference"
    ).origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "prepare_model" not in text
