"""Compiled local coordinate mapping checked against native C# routines."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.intrinsic_coordinates import native_projected_intrinsic


class NativeIntrinsicCoordinateTests(unittest.TestCase):
    def test_scalar_and_compiled_coordinates_match_original(self):
        cases = json.loads((Path(__file__).parent / "fixtures/csharp_intrinsic_coordinates_2026_1_1.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            for routine in (native_projected_intrinsic, native_projected_intrinsic.py_func):
                with self.subTest(interface=case["interface"], quad=case["quad"], compiled=routine is native_projected_intrinsic):
                    actual = routine(np.asarray(case["vertices"], dtype=np.float32), np.asarray(case["point"], dtype=np.float32), np.float32(.01))
                    np.testing.assert_array_equal(actual, [case["expected"]["u"], case["expected"]["v"]])
