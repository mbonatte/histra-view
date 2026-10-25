"""Post-ultimate curve reassignment verified against native C# methods."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.constitutive_laws import HystereticLaw
from histra.preprocessing.spring_factory import _combine_hysteretic, _configure_combined_hysteretic_batch
from histra.springs.hysteretic import SpringHysteretic


class NativeInterfaceCurveSelectionTests(unittest.TestCase):
    def test_scalar_and_batch_post_ultimate_curve_selection(self):
        cases = json.loads((Path(__file__).parent / "fixtures/csharp_interface_curve_selection_2026_1_1.json").read_text(encoding="utf-8"))["cases"]
        tensile = ("Elastic", "LinearHardening", "LinearSoftening", "Exponential")
        compression = ("Elastic", "LinearHardening", "LinearSoftening", "Parabolic")
        for case in cases:
            with self.subTest(key=case["key"]):
                laws = [HystereticLaw(**side["law"]) for side in case["sides"]]
                sides = []
                props = []
                for side, law in zip(case["sides"], laws):
                    k, area, ft, fc, kt, kc = side["params"]
                    sides.append(SpringHysteretic(k=k, area=area, length=1., fy=[ft, fc], kt=[kt, kc], alfau=[law.alfa_u_t, law.alfa_u_c], alfar=[law.alfa_r_t, law.alfa_r_c], tensile_curve_type=law.tensile_curve, compressive_curve_type=law.compressive_curve))
                    props.append(np.asarray([[k, area, 1.]]))
                scalar = _combine_hysteretic(*sides, False, *laws)
                batch = _configure_combined_hysteretic_batch(props[0], laws[0], props[1], laws[1], interface_key=case["key"][1])[0]
                for spring in (scalar, batch):
                    self.assertEqual(spring.tensile_curve_type, tensile[int(case["expected"][0])])
                    self.assertEqual(spring.compressive_curve_type, compression[int(case["expected"][1])])
                    actual = [spring.k, *spring.fy, *spring.ur, spring.rot1n, spring.mom1n]
                    np.testing.assert_allclose(actual, case["expected"][2:9], rtol=1e-13, atol=1e-13)
