"""Original DLL masonry modulus calculations, including clamp boundaries."""
import json
from pathlib import Path
import unittest
from histra.model.masonry_material import MasonryMaterial
from histra.preprocessing.constitutive_laws import shear_law, sliding_law


class NativeMasonryModulusTests(unittest.TestCase):
    def test_original_masonry_moduli(self):
        cases = json.loads((Path(__file__).parent / "fixtures/csharp_material_moduli_2026_1_1.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(gd=case["gd"], alpha=case["alpha"]):
                material = MasonryMaterial(properties={"Gd": str(case["gd"]), "AlfaShearUser": str(case["alpha"])})
                self.assertEqual(shear_law(material).E, case["shear"])
                self.assertEqual(sliding_law(material, out_of_plane=False, direction="hor").E, case["sliding"])
                self.assertEqual(sliding_law(material, out_of_plane=False, direction="vert").E, case["sliding"])
