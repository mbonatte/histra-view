"""Native C# out-of-plane interpolation distances."""
import json
from pathlib import Path
import unittest
from histra.elements.interface import Interface

class NativeSpringDistanceTests(unittest.TestCase):
    def test_public_and_protected_distance_factors(self):
        fixture=Path(__file__).parent/'fixtures/csharp_spring_distance_2026_1_1.json'
        for case in json.loads(fixture.read_text())['cases']:
            with self.subTest(length=case['length'],thickness=case['thickness']):
                intf=Interface(length=case['length'],thickness=[case['thickness']]*4)
                self.assertEqual(intf.compute_dist_spring(),tuple(case['expected']))
                self.assertEqual(intf.compute_dist_spring_for(intf),tuple(case['expected']))
