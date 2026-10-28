import base64
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from histra_results import project_contours_histra, project_histra, project_interface_histra

ARCHIVE = Path(__file__).resolve().parents[2] / "results" / "native_soil_15e3" / "native_soil_15e3.histra"


@unittest.skipUnless(ARCHIVE.is_file(), "native_soil_15e3.histra not installed")
class HistraResultProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_histra(ARCHIVE)
        cls.analysis = cls.result["analyses"][0]

    def test_archive_catalog_and_mesh(self):
        self.assertEqual(self.result["sourceSchema"], "histra-results-1.0.0")
        self.assertEqual(self.result["defaultAnalysis"], "Interface_Span2_Quarter")
        self.assertEqual(len(self.result["analysisCatalog"]), 104)
        self.assertEqual(self.result["analysisCatalog"][0]["name"], "Interface_Span1_Half")
        self.assertEqual(len(self.result["mesh"]["nodes"]), 388)
        self.assertEqual(len(self.result["mesh"]["quads"]), 306)
        self.assertEqual(len(self.result["mesh"]["interfaces"]), 555)
        self.assertEqual(len(self.result["mesh"]["thrustPairs"]), 460)

    def test_default_case(self):
        self.assertEqual(self.analysis["name"], "Interface_Span2_Quarter")
        self.assertEqual(len(self.analysis["steps"]), 151)
        step = self.analysis["steps"][-1]
        self.assertEqual(step["step"], 150)
        self.assertEqual(len(step["displacements"]), 388)
        self.assertEqual(len(step["interfaceResultants"]), 555)
        quad = np.frombuffer(base64.b64decode(step["quadDisplacements"]), dtype="<f4")
        self.assertEqual(quad.size, 306 * 4 * 3)
        self.assertTrue(np.isfinite(quad).all())
        fields = {field["id"]: field for field in self.analysis["stressFields"]}
        self.assertEqual(len(fields), 19)
        self.assertTrue(fields["vonMises"]["available"])
        self.assertGreater(fields["vonMises"]["max"], 0.0)

    def test_case_selection_and_auxiliary_endpoints(self):
        other = project_histra(ARCHIVE, "Interface_Span1_Half")
        self.assertEqual(len(other["analyses"][0]["steps"]), 521)
        self.assertEqual(other["analyses"][0]["name"], "Interface_Span1_Half")
        contours = project_contours_histra(ARCHIVE, "Interface_Span1_Half")
        self.assertEqual(contours["cellCount"], 44955)
        self.assertEqual(len(contours["groups"]), 555)
        stress = np.frombuffer(base64.b64decode(contours["stress"]), dtype="<f4")
        self.assertTrue(np.isfinite(stress).all())
        detail = project_interface_histra(ARCHIVE, "Interface_Span1_Half", 1)
        self.assertEqual(detail["key"], 1)
        self.assertEqual(len(detail["normal"]), 81)
        self.assertEqual(len(detail["sliding"]), 3)


if __name__ == "__main__":
    unittest.main()

SCOZZESE_ARCHIVE = Path(__file__).resolve().parents[2] / "results" / "Scozzese_Vert.histra"


@unittest.skipUnless(SCOZZESE_ARCHIVE.is_file(), "Scozzese_Vert.histra not installed")
class LargeHistraProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_histra(SCOZZESE_ARCHIVE)

    def test_large_static_case_projects_without_face_grids(self):
        self.assertEqual(self.result["defaultAnalysis"], "Vert")
        self.assertEqual(len(self.result["mesh"]["nodes"]), 4950)
        self.assertEqual(len(self.result["mesh"]["quads"]), 3800)
        self.assertEqual(len(self.result["mesh"]["interfaces"]), 10236)
        analysis = self.result["analyses"][0]
        self.assertEqual(len(analysis["steps"]), 21)
        fields = [field for field in analysis["stressFields"] if field["available"]]
        self.assertEqual(len(fields), 12)
        self.assertFalse(any(field.get("quadFaceGrids") for field in fields))
        self.assertGreater(next(field for field in fields if field["id"] == "vonMises")["max"], 0.0)

    def test_lazy_field_descriptors_avoid_eager_projection(self):
        lazy = project_histra(SCOZZESE_ARCHIVE, include_stress_fields=False)
        analysis = lazy["analyses"][0]
        self.assertTrue(lazy["lazyFields"])
        self.assertIsNone(analysis["finalStress"])
        fields = [field for field in analysis["stressFields"] if field["available"]]
        self.assertEqual(len(fields), 12)
        self.assertTrue(all(field.get("lazy") for field in fields))
        self.assertFalse(any(field.get("quadCornerValues") for field in fields))


ATTACHMENT_MODAL_ARCHIVE = Path(__file__).resolve().parents[2] / "results" / "Scozzese_Vert_Modal.histra"


@unittest.skipUnless(ATTACHMENT_MODAL_ARCHIVE.is_file(), "Scozzese_Vert_Modal.histra not installed")
class AttachmentModalHistraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_histra(ATTACHMENT_MODAL_ARCHIVE, include_stress_fields=False)

    def test_attachment_modes_are_projected_to_nodes(self):
        self.assertEqual(
            [(item["name"], len(item["modes"])) for item in self.result["modal"]],
            [("Modal_1", 12)],
        )
        mode = self.result["modal"][0]["modes"][0]
        self.assertEqual(mode["number"], 1)
        self.assertAlmostEqual(mode["frequency"], 11.489356605486705)
        self.assertEqual(len(mode["displacements"]), 6150)
        norms = [sum(value * value for value in point) ** 0.5 for point in mode["displacements"]]
        self.assertAlmostEqual(max(norms), 1.0, places=5)


MODAL_ARCHIVE = Path(__file__).resolve().parents[2] / "results" / "modal_scour_y_mode_baseline_abutments.histra"


@unittest.skipUnless(MODAL_ARCHIVE.is_file(), "modal scour .histra not installed")
class ModalHistraProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = project_histra(MODAL_ARCHIVE)

    def test_modal_catalog_and_shapes(self):
        self.assertEqual(self.result["sourceSchema"], "histra-results-1.0.0")
        self.assertEqual(self.result["defaultAnalysis"], "eta_0.00")
        self.assertEqual(len(self.result["analysisCatalog"]), 8)
        self.assertEqual(len(self.result["mesh"]["nodes"]), 5862)
        self.assertEqual(len(self.result["mesh"]["quads"]), 2520)
        self.assertEqual(len(self.result["modal"]), 8)
        self.assertEqual([item["name"] for item in self.result["modal"]], [item["name"] for item in self.result["analysisCatalog"]])
        self.assertEqual(len(self.result["modal"][0]["modes"]), 30)
        self.assertEqual(len(self.result["modal"][0]["modes"][0]["displacements"]), 5862)
        self.assertGreater(self.result["modal"][0]["modes"][0]["frequency"], 0.0)

    def test_modal_case_switch(self):
        other = project_histra(MODAL_ARCHIVE, "eta_0.10")
        self.assertEqual(other["analyses"][0]["name"], "eta_0.10")
        self.assertEqual(len(other["modal"]), 8)
