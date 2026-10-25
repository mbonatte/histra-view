"""Tests for SpringCoulomb03 — the critical interface spring type."""
import unittest
import numpy as np
from xml.etree import ElementTree as ET
from histra.types.phase_enum import PhaseEnum
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.registry import spring_from_xml


def make_coulomb_xml(**kw):
    """Build a SpringCoulomb03 XML element with given attributes."""
    attrs = {
        "TypeOf": "HiStrA.Objects.SpringCoulomb03",
        "Tag": str(kw.get("Tag", 1)),
        "K0": str(kw.get("K0", 2000.0)),
        "Fy": str(kw.get("Fy", 100.0)),
        "HystereticType": str(kw.get("HystereticType", "Takeda")),
        "TensileCurveType": str(kw.get("TensileCurveType", "Elastic")),
        "CompressiveCurveType": str(kw.get("CompressiveCurveType", "Elastic")),
    }
    elem = ET.Element("SpringCoulomb03", attrs)
    return elem


class TestSpringCoulomb03Representation(unittest.TestCase):
    def test_fixed_schema_is_slotted_with_dynamic_override_compatibility(self):
        s = SpringCoulomb03(k=123.0, cohesion=4.0)
        self.assertNotIn("k", s.__dict__)
        self.assertNotIn("cohesion", s.__dict__)
        s.get_force = lambda: 7.25
        self.assertEqual(s.get_force(), 7.25)
        self.assertIn("get_force", s.__dict__)
        self.assertTrue(hasattr(SpringCoulomb03, "__slots__"))


class TestSpringCoulomb03FromXml(unittest.TestCase):
    def test_create_takeda(self):
        s = spring_from_xml(make_coulomb_xml())
        self.assertIsInstance(s, SpringCoulomb03)
        self.assertEqual(s.hysteretic_type, "Takeda")

    def test_create_initial(self):
        xml = make_coulomb_xml(HystereticType="Initial",
                               TensileCurveType="LinearHardening")
        s = spring_from_xml(xml)
        self.assertIsInstance(s, SpringCoulomb03)
        self.assertEqual(s.hysteretic_type, "Initial")


class TestSpringCoulomb03CohesionYield(unittest.TestCase):
    """
    SpringCoulomb03 with cohesion-based yield (sub_law='Coulomb').
    - Initial stiffness e1p = 2000
    - Yield at cohesion = 100
    - Perfect plastic after yield (e2p = 0)
    """

    def setUp(self):
        self.s = SpringCoulomb03(e1p=2000.0, e1n=-2000.0,
                                 rot2p=1.0, rot3p=2.0,
                                 rot2n=-1.0, rot3n=-2.0,
                                 e2p=0.0, e3p=0.0,
                                 cohesion=100.0, mu=0.0, sub_law="Coulomb",
                                 hysteretic_type="Takeda")

    def test_initial_state(self):
        self.assertEqual(self.s._tstress, 0.0)
        self.assertEqual(self.s._tstrain, 0.0)
        self.assertEqual(self.s.t_phase, PhaseEnum.Elastic)

    def test_before_yield(self):
        self.s.set_trial_strain(0.04)
        self.assertAlmostEqual(self.s._tstress, 80.0, places=4)
        self.assertEqual(self.s.t_phase, PhaseEnum.Elastic)

    def test_post_yield_tension(self):
        self.s.set_trial_strain(0.06)
        self.assertAlmostEqual(self.s._tstress, 100.0, places=4)

    def test_post_yield_compression(self):
        self.s.set_trial_strain(-0.06)
        self.assertAlmostEqual(self.s._tstress, -100.0, places=4)

    def test_get_force(self):
        self.s.set_trial_strain(0.04)
        self.assertAlmostEqual(self.s.get_force(), 80.0)

    def test_get_displacement(self):
        self.s.set_trial_strain(0.04)
        self.assertAlmostEqual(self.s.get_displacement(), 0.04)


class TestSpringCoulomb03TakedaLinearHardening(unittest.TestCase):
    """Takeda with linear hardening."""

    def setUp(self):
        self.s = SpringCoulomb03(e1p=2000.0, e1n=-2000.0,
                                 rot2p=1.0, rot3p=2.0,
                                 rot2n=-1.0, rot3n=-2.0,
                                 e2p=400.0, e2n=-400.0,
                                 eup=2000.0, eun=-2000.0,
                                 cohesion=100.0, mu=0.0,
                                 sub_law="Coulomb",
                                 hysteretic_type="Takeda")

    def test_yield_and_harden(self):
        self.s.set_trial_strain(0.06)
        # mom1p = 100, rot1p = 100/2000 = 0.05
        # yield at 0.05 with stress 100, then hardening at e2p = 400
        # stress = 100 + 400 * (0.06 - 0.05) = 104
        self.assertAlmostEqual(self.s._tstress, 104.0, places=4)

    def test_commit_and_unload(self):
        self.s.set_trial_strain(0.06)
        self.s.commit()
        self.s.set_trial_strain(0.0)
        stress = self.s._tstress
        self.assertLess(stress, 100.0)

    def test_reversal_to_compression(self):
        self.s.set_trial_strain(0.06)
        self.s.commit()
        self.s.set_trial_strain(-0.06)
        stress = self.s._tstress
        self.assertLess(stress, 0.0)


class TestSpringCoulomb03InitialLinearHardening(unittest.TestCase):
    """Initial loading curve with linear hardening."""

    def setUp(self):
        self.s = SpringCoulomb03(e1p=2000.0, e1n=-2000.0,
                                 k=2000.0,   # used by set_trial_strain_initial
                                 e2p=200.0, e2n=-200.0,
                                 rot2p=1.0, rot3p=2.0,
                                 rot2n=-1.0, rot3n=-2.0,
                                 eup=2000.0, eun=-2000.0,
                                 cohesion=100.0, mu=0.0,
                                 sub_law="Coulomb",
                                 hysteretic_type="Initial")

    def test_pre_yield(self):
        self.s.set_trial_strain(0.04)
        self.assertAlmostEqual(self.s._tstress, 80.0, places=4)

    def test_yield_harden(self):
        self.s.set_trial_strain(0.06)
        # num3 = 0 + 2000 * 0.06 = 120
        # abs(120) - fy[0] = 120 - 100 = 20 > 0 → plastic_t
        # num5 = (120 - 100) / 2000 = 0.01
        # h = e1p * e2p / (e1p - e2p) = 2000 * 200 / (2000 - 200) = 222.22...
        # num6 = 2000 * 0.01 / (222.22 + 2000) = 20 / 2222.22 = 0.009
        # fy[0] += 222.22 * 0.009 ≈ 102
        self.assertAlmostEqual(self.s._tstress, 102.0, places=0)

    def test_reload_follows_initial(self):
        self.s.set_trial_strain(0.06)
        self.s.commit()
        self.s.set_trial_strain(0.04)
        # After commit to strain 0.06: _cstress ≈ 102, _cstrain = 0.06
        # On reload to 0.04: dstrain = 0.04 - 0.06 = -0.02 (compression direction)
        # num3 = 102 + 2000 * (-0.02) = 102 - 40 = 62
        # abs(62) - fy[0] > 0? No, fy[0] is still ~102, so abs(62) - 102 = -40 < 0
        # So stays elastic: _tstress = 62
        self.assertAlmostEqual(self.s._tstress, 62.0, places=0)


class TestSpringCoulomb03SetTrialStrainRegression(unittest.TestCase):
    """Regression: bug was _tstress = 0 in set_trial_strain."""

    def test_stress_not_zero_after_set_trial_strain(self):
        s = SpringCoulomb03(e1p=2000.0, e1n=-2000.0,
                            cohesion=100.0, mu=0.0,
                            sub_law="Coulomb")
        s.set_trial_strain(0.01)
        self.assertNotAlmostEqual(s._tstress, 0.0)
        self.assertAlmostEqual(s._tstress, 20.0, places=4)


if __name__ == "__main__":
    unittest.main()
