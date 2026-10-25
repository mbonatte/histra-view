"""Architecture checks for the extracted fibre-geometry owner."""

import importlib.util

import histra.preprocessing.fibre_geometry as fibre_geometry


def test_prepare_model_compatibility_facade_reexports_fibre_geometry():
    prepare_model = importlib.import_module("histra.preprocessing.prepare_model")
    names = (
        "_bilinear_nb",
        "_cell_vertices",
        "_cross3_nb",
        "_dot3_nb",
        "_fiber_stiffness",
        "_fiber_stiffness_batch",
        "_fiber_stiffness_batch_nb",
        "_interface_cells",
        "_interface_cells_nb",
        "_inverse_bilinear_nb",
        "_norm3_nb",
        "_polygon_areas_3d",
        "_polygon_areas_3d_nb",
    )

    for name in names:
        assert getattr(prepare_model, name) is getattr(fibre_geometry, name)


def test_fibre_geometry_owner_has_no_reverse_dependency_on_prepare_model():
    source = importlib.util.find_spec(
        "histra.preprocessing.fibre_geometry"
    ).origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "prepare_model" not in text
