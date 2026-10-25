"""Reference values obtained by calling installed MonoGame Vector3.Normalize."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.contact_geometry import _unit_f32
from histra.preprocessing.errors import ModelPreparationError


class CSharpVectorNormalizationTests(unittest.TestCase):
    def test_every_native_direction_matches_exactly(self):
        path = Path(__file__).parent / "fixtures/csharp_vector_normalization_2026_1_1.json"
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 48)
        for case in cases:
            with self.subTest(interface=case["interface"], face=case["face"], edge=case["edge"]):
                actual = _unit_f32(case["input"], label="native reference")
                np.testing.assert_array_equal(actual, np.asarray(case["expected"], dtype=np.float32))

    def test_degenerate_geometry_fails_before_solver(self):
        with self.assertRaises(ModelPreparationError):
            _unit_f32([0., 0., 0.], label="zero reference direction")
