"""Native C# yield-coordinate initialization for scalar and lazy springs."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.transverse_fiber_group import TransverseFiberGroup
from histra.solver.hysteretic_kernels.transverse import TRANSVERSE_PARAM_SIZE


class NativeSpringYieldCoordinatesTests(unittest.TestCase):
    def test_scalar_and_proxy_yield_coordinates(self):
        cases = json.loads((Path(__file__).parent / "fixtures/csharp_spring_yield_coordinates_2026_1_1.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(k=case["k"], fy=case["fy"]):
                spring = SpringHysteretic(k=case["k"], fy=case["fy"].copy())
                spring.initialize()
                self.assertEqual(spring.uy_corr, case["expected"])
                spring.revert_to_start()
                self.assertEqual(spring.uy_corr, case["expected"])
                group = TransverseFiberGroup(np.zeros((1, TRANSVERSE_PARAM_SIZE)), np.array([case["k"]]), np.ones(1), fy=np.asarray([case["fy"]]))
                self.assertEqual(group[0].uy_corr, case["expected"])
