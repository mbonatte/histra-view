"""Original C# contact containment preserves input vertex coordinates."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.quad_faces import classify_contained_contact
from histra.preprocessing.contact_geometry import _coplanar_quad_intersection_prechecked, _face_normal


class CSharpContactContainmentTests(unittest.TestCase):
    def test_native_classification_and_polygon_coordinates(self):
        path=Path(__file__).parent/"fixtures/csharp_contact_containment_2026_1_1.json"
        fixture=json.loads(path.read_text(encoding="utf-8"))
        for case in fixture["cases"]:
            with self.subTest(interface=case["key"]):
                first=np.asarray(case["first"],dtype=np.float32)
                second=np.asarray(case["second"],dtype=np.float32)
                code=classify_contained_contact(first,second,np.float32(fixture["tolerance"]))
                self.assertEqual(code,case["expected"])
                polygon=_coplanar_quad_intersection_prechecked(first,second,_face_normal(first),fixture["tolerance"])
                np.testing.assert_array_equal(np.asarray(polygon),np.asarray(case["expected_vertices"],dtype=np.float32))
