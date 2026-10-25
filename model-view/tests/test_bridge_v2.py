import base64
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_v2 import project_bridge, project_contours, project_interface, cache_stamp

FOLDER = Path(__file__).resolve().parents[2] / "3D_bridge"
HRX = FOLDER / "Bridge.hrx"
OUTPUT = FOLDER / "pdelta_soft_subgrade_phase4_results.json"


@unittest.skipUnless(OUTPUT.is_file() and HRX.is_file(), "Bridge v2 result bundle not installed")
class BridgeV2ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_bridge(HRX, OUTPUT)
        cls.analysis = cls.result["analyses"][0]

    def test_manifest_and_mesh(self):
        self.assertEqual(self.result["sourceSchema"], "2.0.0")
        self.assertEqual(self.result["units"]["length"], "cm")
        self.assertEqual(self.result["modelSha256"], "44b3d26087722b7755f5a46f95498ec13e328f4d8347e8e0efb3c07752d68c14")
        self.assertEqual(len(self.result["mesh"]["nodes"]), 3216)
        self.assertEqual(len(self.result["mesh"]["quads"]), 2520)
        self.assertEqual(len(self.result["mesh"]["interfaces"]), 6762)
        self.assertEqual(len(self.result["mesh"]["thrustPairs"]), 3752)
        self.assertEqual(len(self.result["analysisCatalog"]), 5)
        self.assertEqual(self.result["defaultAnalysis"], "Pushover_Span2_Quarter")

    def test_analysis_steps_and_units(self):
        self.assertEqual(self.analysis["name"], "Pushover_Span2_Quarter")
        self.assertEqual(len(self.analysis["steps"]), 46)
        self.assertEqual(self.analysis["steps"][-1]["step"], 45)
        self.assertAlmostEqual(self.analysis["steps"][-1]["controlDisplacement"], 1.4306018352508545, places=6)
        self.assertAlmostEqual(self.analysis["steps"][-1]["appliedVerticalForce"], 256.9682435207069, places=3)
        self.assertEqual(len(self.analysis["interfaceOrder"]), 6762)
        self.assertEqual(len(self.analysis["interfaces"]), 6762)
        step = self.analysis["steps"][-1]
        self.assertEqual(len(step["displacements"]), 3216)
        self.assertEqual(len(step["interfaceResultants"]), 6762)
        quad = np.frombuffer(base64.b64decode(step["quadDisplacements"]), dtype="<f4")
        self.assertEqual(quad.size, 2520 * 4 * 3)
        self.assertTrue(np.isfinite(quad).all())

    def test_final_von_mises_field(self):
        stress = self.analysis["finalStress"]
        self.assertEqual(stress["unit"], "MPa")
        self.assertEqual(stress["step"], 45)
        self.assertEqual(len(stress["quadCornerValues"]), 2520)
        self.assertEqual(len(stress["quadCornerValues"][0]), 4)
        values = np.asarray(stress["quadCornerValues"], dtype=float)
        self.assertTrue(np.isfinite(values).all())
        self.assertGreater(stress["max"], stress["min"])
        self.assertGreaterEqual(stress["min"], 0.0)

    def test_lazy_analysis_selection(self):
        other = project_bridge(HRX, OUTPUT, "Pushover_Span1_Half")
        self.assertEqual(other["defaultAnalysis"], "Pushover_Span1_Half")
        self.assertEqual(other["analyses"][0]["name"], "Pushover_Span1_Half")
        self.assertEqual(len(other["analyses"][0]["steps"]), 56)
        self.assertEqual(len(other["analysisCatalog"]), 5)

    def test_contours_and_interface(self):
        contours = project_contours(OUTPUT, "Pushover_Span2_Quarter")
        self.assertEqual(contours["cellCount"], 547722)
        self.assertEqual(len(contours["groups"]), 6762)
        self.assertEqual(contours["groups"][0]["nrow"], 9)
        self.assertEqual(contours["groups"][0]["ncol"], 9)
        positions = np.frombuffer(base64.b64decode(contours["positions"]), dtype="<f4")
        stress = np.frombuffer(base64.b64decode(contours["stress"]), dtype="<f4")
        self.assertEqual(positions.size, 547722 * 12)
        self.assertEqual(stress.size, 547722)
        self.assertTrue(np.isfinite(positions).all() and np.isfinite(stress).all())
        self.assertFalse(contours["strainAvailable"])
        detail = project_interface(OUTPUT, "Pushover_Span2_Quarter", 6651)
        self.assertEqual(detail["key"], 6651)
        self.assertEqual(detail["geometry"]["nrow"], 9)
        self.assertEqual(detail["geometry"]["ncol"], 9)
        self.assertEqual(len(detail["normal"]), 81)
        self.assertEqual(len(detail["sliding"]), 3)
        self.assertEqual(len(detail["geometry"]["vint2d"]), 4)

    def test_cache_stamp_covers_case_files(self):
        stamp = cache_stamp(OUTPUT)
        names = {item[0] for item in stamp}
        self.assertTrue(any(name.endswith("pdelta_soft_subgrade_phase4_results.json") for name in names))
        self.assertTrue(any(name.endswith("pdelta_scour4_soft_Span2_Quarter.fields.npz") for name in names))
        self.assertTrue(any(name.endswith("pdelta_scour4_soft_Span2_Quarter.summary.json") for name in names))
