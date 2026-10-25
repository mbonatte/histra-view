"""Architecture checks for the extracted material-selection owner."""

import importlib.util

import histra.preprocessing.material_selection as material_selection


def test_prepare_model_compatibility_facade_reexports_material_selection():
    prepare_model = importlib.import_module("histra.preprocessing.prepare_model")
    names = (
        "_material",
        "_cached_flex_law",
        "_cached_diagonal_laws",
        "_cached_sliding_law",
        "_blend_coulomb_laws",
        "_interface_sliding_law",
    )

    for name in names:
        assert getattr(prepare_model, name) is getattr(material_selection, name)


def test_material_selection_owner_has_no_reverse_dependency_on_prepare_model():
    source = importlib.util.find_spec(
        "histra.preprocessing.material_selection"
    ).origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "prepare_model" not in text
