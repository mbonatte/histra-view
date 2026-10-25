"""Sliding geometry verified against original C# calls."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.quad_faces import distance_to_contact_plane


class NativeSlidingDistanceTests(unittest.TestCase):
    def test_every_native_distance_and_stiffness(self):
        cases = json.loads((Path(__file__).parent / "fixtures/csharp_sliding_distance_2026_1_1.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            for routine in (distance_to_contact_plane, distance_to_contact_plane.py_func):
                with self.subTest(interface=case["interface"], quad=case["quad"], compiled=routine is distance_to_contact_plane):
                    distance = routine(np.asarray(case["g"], dtype=np.float32), np.asarray(case["vint3d"], dtype=np.float32))
                    expected = case["expected"]
                    self.assertAlmostEqual(distance, expected["distance"], delta=1e-12)
                    self.assertEqual(case["python_area"] / distance, expected["inplane"])
                    self.assertEqual(case["python_area"] / 2. / distance, expected["outplane"])
