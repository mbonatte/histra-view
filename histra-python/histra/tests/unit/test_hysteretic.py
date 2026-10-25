"""Tests for SpringHysteretic — interface transversal behavior."""
import unittest
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.registry import spring_from_xml


class TestSpringHystereticElastic(unittest.TestCase):
    def setUp(self):
        self.s = SpringHysteretic(k=3000.0, e1p=3000.0, e1n=-3000.0,
                                  tensile_curve_type="Elastic",
                                  compressive_curve_type="Elastic")

    def test_initial_state(self):
        self.assertEqual(self.s._tstress, 0.0)
        self.assertEqual(self.s._tstrain, 0.0)

    def test_set_trial_strain(self):
        self.s.set_trial_strain(0.0005)
        # f = k * u = 3000 * 0.0005 = 1.5
        self.assertAlmostEqual(self.s.get_force(), 1.5, places=4)

    def test_commit(self):
        self.s.set_trial_strain(0.0005)
        self.s.commit()
        self.assertAlmostEqual(self.s._cstrain, 0.0005)

    def test_stiffness(self):
        self.s.set_trial_strain(0.001)
        self.assertAlmostEqual(self.s.get_force(), 3.0, places=4)


class TestSpringHystereticLinearHardening(unittest.TestCase):
    def setUp(self):
        self.s = SpringHysteretic(k=3000.0,
                                  e1p=3000.0, e2p=100.0, e3p=0.0,
                                  e1n=-3000.0, e2n=-100.0, e3n=0.0,
                                  tensile_curve_type="LinearHardening",
                                  compressive_curve_type="LinearHardening",
                                  fy=[3000.0, -3000.0],
                                  rot1p=1.0, rot1n=-1.0,
                                  mom1p=3000.0, mom1n=-3000.0)

    def test_elastic(self):
        self.s.set_trial_strain(0.5)
        stress = self.s.get_force()
        self.assertAlmostEqual(stress, 1500.0, places=4)


if __name__ == "__main__":
    unittest.main()
