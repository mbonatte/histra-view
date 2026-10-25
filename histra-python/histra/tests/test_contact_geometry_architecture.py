"""Architecture checks for the extracted contact-geometry owner."""

import importlib

import histra.preprocessing.contact_geometry as contact_geometry


def test_prepare_model_compatibility_facade_reexports_contact_geometry():
    prepare_model = importlib.import_module("histra.preprocessing.prepare_model")
    names = (
        "_CONTACT_ANGLE_TOLERANCE",
        "_CONTACT_AREA_TOLERANCE",
        "_CONTACT_BATCH_SIZE",
        "_CONTACT_DISTANCE_TOLERANCE",
        "_TOL",
        "_build_geometric_node_index",
        "_clean_clipped_polygon",
        "_clip_convex_quad_2d",
        "_convex_quad_overlap_prefilter_batch",
        "_coplanar_quad_intersection",
        "_coplanar_quad_intersection_prechecked",
        "_cross3",
        "_cross3_f32",
        "_cross_2d",
        "_dot3_f32",
        "_f32",
        "_face_normal",
        "_face_normals_batch",
        "_find_or_create_geometric_node",
        "_generate_interfaces",
        "_interface_division_count",
        "_line_intersection_2d",
        "_make_interface_geometry",
        "_norm3",
        "_norm3_f32",
        "_node_bucket",
        "_p",
        "_passes_csharp_lateral_area_filter",
        "_polygon_area_2d",
        "_polygon_area_3d",
        "_polygon_edge_at_point",
        "_prepare_interface_endpoints",
        "_quad_contact_pairs",
        "_quad_face_reference_edge",
        "_quad_face_vertices",
        "_quad_lateral_face_vertices",
        "_quad_vint",
        "_unit",
        "_unit_f32",
        "_v",
    )

    for name in names:
        assert getattr(prepare_model, name) is getattr(contact_geometry, name)
