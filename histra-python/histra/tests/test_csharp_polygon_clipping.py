"""Selected saved-native contact cases and an analytical square intersection.

The two identified native fixture cases check rounded vertices and exact area
bits. The additional square-overlap case is analytical. These do not certify
every branch of the original FindIntersectionBetweenQuadrilaters algorithm.
"""
import json
from pathlib import Path
import numpy as np

from histra.preprocessing.csharp_fibre_geometry import _csharp_polygon_area
from histra.preprocessing.contact_geometry import _coplanar_quad_intersection_prechecked

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "csharp_quad_contact_intersection_2026_1_1.json"

# First two entries correspond to the identified native fixture cases.
# orthogonal_overlap is an analytical unit-square result, not a native capture.
CSHARP_CLIPPING_EXACT = {
    "partial_rectangle": {
        "code": 4,
        "count": 4,
        "vertices": [[0.0, -1.0, 0.0], [1.0, -1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        "area": 2.0,
        "area_single_bits": 1073741824,
    },
    "containing_diamond": {
        "code": 1,
        "count": 4,
        "vertices": [[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0]],
        "area": 4.0,
        "area_single_bits": 1082130432,
    },
    "orthogonal_overlap": {
        "code": 4,
        "count": 4,
        "vertices": [[1.0, 1.0, 0.0], [2.0, 1.0, 0.0], [2.0, 2.0, 0.0], [1.0, 2.0, 0.0]],
        "area": 1.0,
        "area_single_bits": 1065353216,
    },
}


def test_csharp_polygon_clipping_authoritative_fixtures():
    """Verify Quad contact clipping against authoritative C# outputs across reference cases."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8-sig"))

    for case in fixture["cases"]:
        if case["name"] not in CSHARP_CLIPPING_EXACT:
            continue
        poly1 = case["first"]
        poly2 = case["second"]
        expected = CSHARP_CLIPPING_EXACT[case["name"]]

        actual = _coplanar_quad_intersection_prechecked(
            np.asarray(poly1, dtype=float),
            np.asarray(poly2, dtype=float),
            np.array([0.0, 0.0, 1.0]),
            node_tolerance=fixture["node_tolerance"],
        )
        assert actual is not None

        # Check vertex coordinates (accounting for cyclic order / orientation)
        cs_verts = sorted(tuple(np.round(p, 5)) for p in expected["vertices"])
        py_verts = sorted(tuple(np.round(p, 5)) for p in actual)
        np.testing.assert_allclose(cs_verts, py_verts, atol=1e-5)

        # Check clipped polygon area bit representation
        py_area = _csharp_polygon_area(np.asarray(actual, dtype=np.float32))
        py_single_bits = int(np.asarray([py_area], dtype=np.float32).view(np.int32)[0])
        assert py_single_bits == expected["area_single_bits"]


def test_csharp_polygon_clipping_orthogonal_overlap():
    """Check the analytical area of overlapping squares in production code."""
    poly1 = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]]
    poly2 = [[1.0, 1.0, 0.0], [3.0, 1.0, 0.0], [3.0, 3.0, 0.0], [1.0, 3.0, 0.0]]
    expected = CSHARP_CLIPPING_EXACT["orthogonal_overlap"]

    actual = _coplanar_quad_intersection_prechecked(
        np.asarray(poly1, dtype=float),
        np.asarray(poly2, dtype=float),
        np.array([0.0, 0.0, 1.0]),
    )
    assert actual is not None
    py_area = _csharp_polygon_area(np.asarray(actual, dtype=np.float32))
    assert abs(py_area - 1.0) < 1e-7
    assert int(np.asarray([py_area], dtype=np.float32).view(np.int32)[0]) == expected["area_single_bits"]
