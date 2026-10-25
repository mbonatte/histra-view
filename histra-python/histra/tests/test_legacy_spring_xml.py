"""Legacy serialized springs remain readable before fresh preprocessing."""
import unittest
import xml.etree.ElementTree as ET
from histra.model.spring import SpringCoulomb, SpringMultiLinear, spring_from_xml

class TestLegacySpringXml(unittest.TestCase):
    def test_coulomb_snapshot_parses_common_and_friction_fields(self):
        spring = spring_from_xml(ET.fromstring(
            '<Spring TypeOf="HiStrA.Objects.SpringCoulomb" Key="7" K="12" Mu="0.4" Kt="3" Kn="5"/>'))
        self.assertIsInstance(spring, SpringCoulomb)
        self.assertEqual((spring.key, spring.k, spring.mu, spring.kt, spring.kn), (7, 12, 0.4, 3, 5))

    def test_multilinear_snapshot_retains_serialized_curve(self):
        spring = spring_from_xml(ET.fromstring(
            '<Spring TypeOf="HiStrA.Objects.SpringMultiLinear" K="12" Deformations="0;1;2" Forces="0;12;15"/>'))
        self.assertIsInstance(spring, SpringMultiLinear)
        self.assertEqual((spring.k, spring.deformations, spring.forces), (12, "0;1;2", "0;12;15"))

    def test_legacy_snapshots_accept_absent_optional_attributes(self):
        for name in ("SpringCoulomb", "SpringMultiLinear"):
            with self.subTest(type=name):
                spring = spring_from_xml(ET.fromstring(f'<Spring TypeOf="HiStrA.Objects.{name}"/>'))
                self.assertEqual(spring.k, 0)
