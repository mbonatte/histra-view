"""Architecture checks for the Quad split (§11.1 boundaries)."""

import importlib


def test_quad_facade_exposes_the_complete_public_surface():
    quad = importlib.import_module("histra.elements.quad")
    loads = importlib.import_module("histra.elements.quad_loads")
    geometry = importlib.import_module("histra.elements.quad_geometry")

    assert quad.Quad.__mro__[1] is geometry.QuadGeometryMixin
    assert quad.Quad.__mro__[2] is loads.QuadLoadsMixin

    for name in (
        "compute_static_load_internal",
        "_compute_static_load_internal_scalar",
        "compute_line_load_internal",
        "compute_self_weight_load",
    ):
        assert getattr(quad.Quad, name) is getattr(loads.QuadLoadsMixin, name)

    for name in (
        "d_alfa_2d_diag",
        "d_diag_2d_alfa",
        "cos_alfa",
        "compute_k",
        "get_diagonal_stiffness",
    ):
        assert getattr(quad.Quad, name) is getattr(geometry.QuadGeometryMixin, name)

    # The facade keeps the C# yield-search delegation and the XML adapter.
    for name in (
        "set_non_linear_properties",
        "from_xml",
        "compute_energy",
        "update_domain",
        "commit",
        "revert_to_last_commit",
        "compute_dn",
        "max_u",
    ):
        assert callable(getattr(quad.Quad, name))


def test_quad_owners_have_no_reverse_dependency_on_the_facade():
    for module in ("histra.elements.quad_loads", "histra.elements.quad_geometry"):
        source = importlib.util.find_spec(module).origin
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        assert "elements.quad import" not in text
