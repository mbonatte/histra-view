import base64
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from csharp_results import (
    _cached_models,
    project_contours_csharp,
    project_csharp,
    project_csharp_fields,
    project_interface_csharp,
)

FOLDER = Path(__file__).resolve().parents[2] / "results" / "benchmark"
HRX = FOLDER / "benchmark.hrx"
RESULTS = FOLDER / "benchmark.Results"


@unittest.skipUnless(HRX.is_file() and RESULTS.is_file(), "C# benchmark Results database not installed")
class CSharpResultsProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_csharp(HRX, RESULTS, "LiveLoad_1")
        cls.analysis = cls.result["analyses"][0]

    def test_catalog_and_mesh(self):
        self.assertEqual(self.result["sourceSchema"], "csharp-results")
        self.assertEqual([item["name"] for item in self.result["analysisCatalog"]],
                         ["Vert", "LiveLoad_1", "scour_1"])
        self.assertEqual(self.result["defaultAnalysis"], "LiveLoad_1")
        self.assertEqual(len(self.result["mesh"]["nodes"]), 400)
        self.assertEqual(len(self.result["mesh"]["quads"]), 260)
        self.assertEqual(len(self.result["mesh"]["interfaces"]), 682)
        self.assertEqual(len(self.result["mesh"]["thrustPairs"]), 260)

    def test_steps_and_quantities(self):
        self.assertEqual(len(self.analysis["steps"]), 132)
        self.assertEqual(self.analysis["steps"][-1]["step"], 131)
        step = self.analysis["steps"][-1]
        self.assertEqual(len(step["displacements"]), 400)
        self.assertEqual(len(step["interfaceResultants"]), 682)
        self.assertEqual(len(step["reactions"]), 3)
        quad = np.frombuffer(base64.b64decode(step["quadDisplacements"]), dtype="<f4")
        self.assertEqual(quad.size, 260 * 4 * 3)
        self.assertTrue(np.isfinite(quad).all())
        self.assertIsNone(step["loadFactor"])
        self.assertAlmostEqual(step["controlDisplacement"], 39.30486940326355, places=6)

    def test_interface_and_modal(self):
        self.assertEqual(len(self.analysis["interfaces"]), 682)
        self.assertEqual(len(self.analysis["finalStress"]["quadCornerValues"]), 260)
        self.assertGreater(self.analysis["finalStress"]["max"], 0.0)
        fields = {field["id"]: field for field in self.analysis["stressFields"]}
        self.assertEqual(len(fields), 19)
        self.assertTrue(fields["globalStressX"]["available"])
        self.assertTrue(fields["localStressNormal"]["available"])
        self.assertTrue(fields["localStrainNormal"]["available"])
        self.assertTrue(fields["localStrainNormal"]["partial"])
        self.assertTrue(fields["plasticStrainRatioNormal"]["available"])
        self.assertTrue(fields["plasticStrainRatioNormal"]["partial"])
        self.assertTrue(fields["quadDiagonalSigma"]["available"])
        self.assertTrue(fields["quadDiagonalPhase"]["available"])
        self.assertEqual(fields["vonMises"]["min"], self.analysis["finalStress"]["min"])
        for field_id in ("globalStressX", "principalTensile", "localStressNormal",
                         "localStrainInPlane", "plasticStrainNormal"):
            values = np.asarray(fields[field_id]["quadCornerValues"], dtype=float)
            self.assertEqual(values.shape, (260, 4), field_id)
            self.assertTrue(np.isfinite(values).all(), field_id)
            face_values = np.asarray(fields[field_id]["quadFaceValues"], dtype=float)
            self.assertEqual(face_values.shape, (260, 6, 4), field_id)
            self.assertTrue(np.isfinite(face_values).all(), field_id)
        y_values = np.asarray(fields["globalStressY"]["quadFaceValues"], dtype=float)
        self.assertLess(y_values.min(), 0.0)
        self.assertGreater(y_values.max(), 0.0)
        self.assertEqual(len(step_modes := self.result["modal"][0]["modes"]), 10)
        self.assertEqual(step_modes[0]["number"], 1)
        self.assertAlmostEqual(step_modes[0]["frequency"], 62.41630734183502, places=9)
        self.assertEqual(len(step_modes[0]["displacements"]), 400)
        mode_quad = np.frombuffer(base64.b64decode(step_modes[0]["quadDisplacements"]), dtype="<f4")
        self.assertEqual(mode_quad.size, 260 * 4 * 3)
        self.assertTrue(np.isfinite(mode_quad).all())

    def test_per_step_stress_fields(self):
        early = project_csharp_fields(HRX, RESULTS, "LiveLoad_1", 1)
        self.assertEqual(early["step"], 1)
        self.assertEqual(early["analysis"], "LiveLoad_1")
        fields = {field["id"]: field for field in early["stressFields"]}
        self.assertEqual(fields["vonMises"]["step"], 1)
        values = np.asarray(fields["vonMises"]["quadFaceValues"], dtype=float)
        self.assertEqual(values.shape, (260, 6, 4))
        self.assertTrue(np.isfinite(values).all())
        final_field = next(field for field in self.analysis["stressFields"] if field["id"] == "vonMises")
        final_values = np.asarray(final_field["quadFaceValues"], dtype=float)
        self.assertFalse(np.allclose(values, final_values))
        early_contours = project_contours_csharp(HRX, RESULTS, "LiveLoad_1", 1)
        self.assertEqual(early_contours["step"], 1)
        early_interface = project_interface_csharp(HRX, RESULTS, "LiveLoad_1", 1, 1)
        self.assertEqual(early_interface["step"], 1)

    def test_lazy_stress_field_descriptors(self):
        lazy = project_csharp(HRX, RESULTS, "LiveLoad_1", include_stress_fields=False)
        analysis = lazy["analyses"][0]
        self.assertIsNone(analysis["finalStress"])
        self.assertEqual(len(analysis["stressFields"]), 19)
        self.assertTrue(all("quadCornerValues" not in field for field in analysis["stressFields"]))
        self.assertTrue(all(field["available"] for field in analysis["stressFields"]))

    def test_contours(self):
        contours = project_contours_csharp(HRX, RESULTS, "LiveLoad_1")
        self.assertEqual(contours["cellCount"], 55242)
        self.assertEqual(len(contours["groups"]), 682)
        positions = np.frombuffer(base64.b64decode(contours["positions"]), dtype="<f4")
        stress = np.frombuffer(base64.b64decode(contours["stress"]), dtype="<f4")
        for key in ("slidingStress", "slidingOutOfPlaneStress"):
            self.assertEqual(np.frombuffer(base64.b64decode(contours[key]), dtype="<f4").size,
                             contours["cellCount"], key)
        self.assertEqual(np.frombuffer(base64.b64decode(contours["slidingPhase"]), dtype="u1").size,
                         contours["cellCount"])
        self.assertEqual(np.frombuffer(base64.b64decode(contours["slidingOutOfPlanePhase"]), dtype="u1").size,
                         contours["cellCount"])
        self.assertEqual(positions.size, 55242 * 12)
        self.assertEqual(stress.size, 55242)
        self.assertTrue(np.isfinite(positions).all() and np.isfinite(stress).all())
        self.assertTrue(contours["strainAvailable"])
        detail = project_interface_csharp(HRX, RESULTS, "LiveLoad_1", 1)
        self.assertEqual(detail["key"], 1)
        self.assertEqual(len(detail["normal"]), 81)
        self.assertEqual(len(detail["sliding"]), 3)
        self.assertEqual(detail["geometry"]["nrow"], 9)
        self.assertEqual(detail["geometry"]["ncol"], 9)
        final = self.analysis["steps"][-1]["interfaceResultants"][self.analysis["interfaceOrder"].index(1)]
        self.assertEqual(detail["forces"] + detail["moments"], final)

    def test_load_control_and_global_parity(self):
        from histra.io.results_reader import read_global_displacements
        from histra.postprocessing import _average_node_displacements, quad_node_displacement

        result = project_csharp(HRX, RESULTS, "Vert")
        analysis = result["analyses"][0]
        self.assertEqual([step["loadFactor"] for step in analysis["steps"]],
                         [0.0, 0.2, 0.4, 0.6000000000000001, 0.8, 1.0])
        model, _viewer, _digest = _cached_models(HRX)
        global_u = read_global_displacements(RESULTS, 1, 1, size=model.gdl)
        connected = {int(node["key"]): [] for node in result["mesh"]["nodes"]}
        for quad in model.collections.quads.values():
            for index, node_key in enumerate(quad.node_keys):
                if int(node_key) in connected:
                    connected[int(node_key)].append((quad, index))
        expected = np.asarray([
            _average_node_displacements([
                quad_node_displacement(quad, model.collections.nodes[int(node_key)].point, index, global_u)
                for quad, index in connected[int(node_key)]
            ])
            for node_key in connected
        ])
        actual = np.asarray(analysis["steps"][-1]["displacements"])
        self.assertTrue(np.allclose(actual, expected, rtol=0, atol=2e-6))


if __name__ == "__main__":
    unittest.main()
