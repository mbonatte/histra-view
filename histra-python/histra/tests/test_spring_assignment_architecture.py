"""Architecture checks for the extracted spring-assignment owner."""

import importlib.util

import histra.preprocessing.spring_assignment as spring_assignment


def test_prepare_model_compatibility_facade_reexports_spring_assignment():
    prepare_model = importlib.import_module("histra.preprocessing.prepare_model")
    names = (
        "_create_interface_springs",
        "_distance_to_interface_plane",
        "_interface_parent_material",
        "_quad_spring",
        "_side_sliding_spring",
        "_side_transverse_spring",
        "_transverse_side_properties_batch",
        "rebuild_interface_springs",
    )

    for name in names:
        assert getattr(prepare_model, name) is getattr(spring_assignment, name)


def test_spring_assignment_owner_has_no_reverse_dependency_on_prepare_model():
    source = importlib.util.find_spec(
        "histra.preprocessing.spring_assignment"
    ).origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "prepare_model" not in text
