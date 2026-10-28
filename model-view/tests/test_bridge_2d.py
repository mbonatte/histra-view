import base64
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_v2 import project_bridge, project_contours, project_interface

FOLDER = Path(__file__).resolve().parents[2] / "results" / "2d_bridge"
HRX = FOLDER / "Bridge.hrx"
MANIFEST = FOLDER / "results" / "manifest.json"
FIELDS = FOLDER / "results" / "native" / "Bridge_Pushover_Span2_Quarter.fields.npz"


@unittest.skipUnless(HRX.is_file() and MANIFEST.is_file() and FIELDS.is_file(),
                     "2D bridge native result bundle not installed")
class Bridge2DProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_bridge(HRX, MANIFEST)
        cls.analysis = cls.result["analyses"][0]

    def test_manifest_and_mesh(self):
        self.assertEqual(self.result["sourceSchema"], "2.0.0")
        self.assertEqual(self.result["name"], "Bridge.hrx")
        self.assertEqual(len(self.result["mesh"]["nodes"]), 388)
        self.assertEqual(len(self.result["mesh"]["quads"]), 306)
        self.assertEqual(len(self.result["mesh"]["interfaces"]), 555)
        self.assertEqual(self.result["defaultAnalysis"], "Pushover_Span2_Quarter")
        self.assertEqual([item["name"] for item in self.result["analysisCatalog"]],
                         ["Pushover_Span2_Quarter", "Pushover_Span1_Half",
                          "Pushover_Span1_ThreeQuarter", "Pushover_Span2_Half"])

    def test_steps_and_fields(self):
        self.assertEqual(len(self.analysis["steps"]), 151)
        self.assertEqual(self.analysis["steps"][-1]["step"], 150)
        step = self.analysis["steps"][-1]
        self.assertEqual(len(step["displacements"]), 388)
        self.assertEqual(len(step["interfaceResultants"]), 555)
        quad = np.frombuffer(base64.b64decode(step["quadDisplacements"]), dtype="<f4")
        self.assertEqual(quad.size, 306 * 4 * 3)
        self.assertTrue(np.isfinite(quad).all())
        fields = {field["id"]: field for field in self.analysis["stressFields"]}
        self.assertEqual(len(fields), 19)
        self.assertTrue(fields["vonMises"]["available"])
        self.assertTrue(fields["globalStressX"]["available"])
        self.assertTrue(fields["localStressNormal"]["available"])
        values = np.asarray(fields["vonMises"]["quadCornerValues"], dtype=float)
        self.assertEqual(values.shape, (306, 4))
        self.assertTrue(np.isfinite(values).all())
        self.assertGreater(fields["vonMises"]["max"], 0.0)

    def test_contours_and_interface(self):
        contours = project_contours(MANIFEST, "Pushover_Span2_Quarter")
        self.assertEqual(contours["cellCount"], 44955)
        self.assertEqual(len(contours["groups"]), 555)
        stress = np.frombuffer(base64.b64decode(contours["stress"]), dtype="<f4")
        self.assertTrue(np.isfinite(stress).all())
        detail = project_interface(MANIFEST, "Pushover_Span2_Quarter", 1)
        self.assertEqual(detail["key"], 1)
        self.assertEqual(detail["geometry"]["nrow"] * detail["geometry"]["ncol"],
                         len(detail["normal"]))


if __name__ == "__main__":
    unittest.main()
