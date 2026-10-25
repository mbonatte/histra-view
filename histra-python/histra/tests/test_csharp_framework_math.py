"""Native Framework arithmetic, including corner-sine cancellation cases."""
import json
from pathlib import Path
import unittest
from histra.preprocessing.csharp_math import POWER_BACKEND, csharp_pow, csharp_atan


@unittest.skipUnless(POWER_BACKEND == 'dotnet-framework-crt', 'Windows Framework arithmetic required')
class NativeFrameworkMathTests(unittest.TestCase):
    def test_original_framework_functions(self):
        data=json.loads((Path(__file__).parent/'fixtures/csharp_framework_math_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in data['powers']:
            with self.subTest(function='pow',x=case['x'],y=case['y']):
                self.assertEqual(csharp_pow(case['x'],case['y']),case['result'])
        for case in data['angles']:
            with self.subTest(function='atan',x=case['x']):
                self.assertEqual(csharp_atan(case['x']),case['result'])
