"""Native C# SetGeometry fixtures, using explicit geometry inputs only."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.quad_faces import compute_quad_faces_batch


class CSharpQuadFaceTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / "fixtures/csharp_quad_faces_2026_1_1.json"
        self.cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        self.points = np.asarray([c["points"] for c in self.cases], dtype=np.float32)
        self.normals = np.asarray([c["normals"] for c in self.cases], dtype=np.float32)
        self.thickness = np.asarray([c["thickness"] for c in self.cases], dtype=np.float32)
        self.expected = np.asarray([c["expected_vint"] for c in self.cases], dtype=np.float32)

    def test_compiled_faces_match_every_native_coordinate(self):
        actual = compute_quad_faces_batch(self.points, self.normals, self.thickness)
        np.testing.assert_array_equal(actual, self.expected)

    def test_scalar_faces_match_every_native_coordinate(self):
        actual = compute_quad_faces_batch.py_func(self.points, self.normals, self.thickness)
        np.testing.assert_array_equal(actual, self.expected)
