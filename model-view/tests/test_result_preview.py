from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from result_preview import project_results, spring_values, project_interface, project_contours, validate_metadata, NATIVE_UNITS

FOLDER = Path(__file__).resolve().parents[2] / "results" / "wall_model"
HRX = FOLDER / "overturning_wall_elastic_foundation.hrx"
OUTPUT = FOLDER / "overturning_wall_raw_output.json"


@unittest.skipUnless(OUTPUT.is_file(), "Wall result bundle not installed")
class WallResultProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Projection also verifies every final node against the independent export.
        cls.result = project_results(None, OUTPUT)
        cls.analyses = {a["name"]: a for a in cls.result["analyses"]}

    def test_all_steps_align_to_the_rendered_mesh(self):
        self.assertEqual(len(self.result["mesh"]["nodes"]), 516)
        self.assertEqual(len(self.result["mesh"]["quads"]), 336)
        self.assertEqual({name: len(a["steps"]) for name, a in self.analyses.items()},
                         {"Vert": 6, "scour_1": 6, "LiveLoad_1": 36})
        for analysis in self.analyses.values():
            for step in analysis["steps"]:
                self.assertEqual(len(step["displacements"]), 516)
                self.assertTrue(all(len(v) == 3 for v in step["displacements"]))
                self.assertIn("quadDisplacements", step)
                self.assertGreaterEqual(step["maxDisplacement"], 0)
                self.assertEqual(len(step["interfaceResultants"]), 884)
                self.assertTrue(all(len(v) == 6 for v in step["interfaceResultants"]))

    def test_stage_initial_states_preserve_accumulated_deformation(self):
        self.assertTrue(all(v == [0, 0, 0] for v in self.analyses["Vert"]["steps"][0]["displacements"]))
        self.assertEqual(self.analyses["scour_1"]["steps"][0]["displacements"],
                         self.analyses["Vert"]["steps"][-1]["displacements"])
        self.assertEqual(self.analyses["LiveLoad_1"]["steps"][0]["displacements"],
                         self.analyses["scour_1"]["steps"][-1]["displacements"])

    def test_modal_shapes_are_normalized_and_periods_reciprocal(self):
        import math
        self.assertEqual([len(a["modes"]) for a in self.result["modal"]], [10, 10])
        for analysis in self.result["modal"]:
            for mode in analysis["modes"]:
                self.assertAlmostEqual(mode["period"] * mode["frequency"], 1)
                self.assertAlmostEqual(max(math.sqrt(sum(u*u for u in v)) for v in mode["displacements"]), 1)
                self.assertEqual(len(mode["displacements"]), 516)
                self.assertIn("quadDisplacements", mode)

    def test_physical_force_matches_wall_reference_load_and_missing_energy_is_preserved(self):
        live = self.analyses["LiveLoad_1"]["steps"]
        self.assertIsNone(live[0]["elasticEnergy"])
        self.assertEqual(live[0]["appliedVerticalForce"], 0)
        self.assertAlmostEqual(live[-1]["appliedVerticalForce"], live[-1]["loadFactor"] * .44, delta=5e-5)
        self.assertEqual(len(live[-1]["reactions"]), 3)
        self.assertTrue(all(len(a["interfaces"]) == 884 for a in self.analyses.values()))

    def test_selected_interface_matches_summary_and_nominal_stress(self):
        detail = project_interface(OUTPUT, "LiveLoad_1", 813)
        summary = next(i for i in self.analyses["LiveLoad_1"]["interfaces"] if i["key"] == 813)
        self.assertEqual(detail["forces"], summary["forces"])
        slot = self.analyses["LiveLoad_1"]["interfaceOrder"].index(813)
        final = self.analyses["LiveLoad_1"]["steps"][-1]["interfaceResultants"][slot]
        self.assertEqual(final, detail["forces"] + detail["moments"])
        self.assertEqual(len(detail["localForces"]), 12)
        self.assertEqual(len(detail["normal"]), 81)
        for s in detail["normal"] + detail["sliding"]:
            self.assertAlmostEqual(s["stress"], 10 * s["force"] / s["area"])

    def test_contour_cells_match_saved_springs_and_actual_geometry(self):
        import base64
        import numpy as np
        data = project_contours(OUTPUT, "LiveLoad_1")
        decode = lambda key: np.frombuffer(base64.b64decode(data[key]), dtype="<f4")
        positions = decode("positions").reshape(-1, 4, 3)
        self.assertEqual(data["cellCount"], 71604)
        self.assertEqual(len(data["groups"]), 884)
        self.assertEqual(sum(g["count"] for g in data["groups"] if g["restrained"]), 5832)
        self.assertTrue(np.isfinite(positions).all())
        self.assertEqual(data["step"], 35)
        self.assertEqual(data["modelSha256"], self.result["modelSha256"])
        g = next(g for g in data["groups"] if g["key"] == 856)
        detail = project_interface(OUTPUT, "LiveLoad_1", 856)
        cells = positions[g["start"]:g["start"] + g["count"]]
        for i, spring in enumerate(detail["normal"]):
            slot = g["start"] + i
            self.assertAlmostEqual(float(decode("stress")[slot]), spring["stress"], delta=1e-5)
            self.assertAlmostEqual(float(decode("force")[slot]), spring["force"], delta=1e-5)
            phase = base64.b64decode(data["phase"])[slot]
            self.assertEqual(data["phaseNames"][phase], spring["phase"])
        # Geometric areas must agree with the spring areas; this also detects
        # flattened/wrongly oriented cells in the 3D projection.
        areas = (np.linalg.norm(np.cross(cells[:, 1]-cells[:, 0], cells[:, 2]-cells[:, 0]), axis=1)
                 + np.linalg.norm(np.cross(cells[:, 2]-cells[:, 0], cells[:, 3]-cells[:, 0]), axis=1)) / 2
        np.testing.assert_allclose(areas, decode("area")[g["start"]:g["start"]+g["count"]], rtol=2e-5)
        normal = np.cross(np.asarray(g["e1"]), np.asarray(g["e3"]))
        np.testing.assert_allclose((cells-np.asarray(g["origin"])) @ normal, 0, atol=1e-4)

    def test_thrust_pairs_and_interface_geometry_are_extracted(self):
        mesh = self.result["mesh"]
        self.assertIn("thrustPairs", mesh)
        self.assertIn("interfaces", mesh)
        self.assertEqual(len(mesh["thrustPairs"]), 336)
        self.assertEqual(len(mesh["interfaces"]), 884)
        sample = mesh["thrustPairs"][0]
        self.assertEqual(len(sample), 4)  # quadKey, i1, i2, materialKey
        iface = mesh["interfaces"][str(sample[1])]
        self.assertEqual(len(iface["nodeKeys"]), 2)
        self.assertGreater(iface["length"], 0)

    def test_metadata_is_explicit_and_matching_hrx_is_optional(self):
        self.assertEqual(self.result["sourceSchema"], "1.1.0")
        self.assertEqual(self.result["sourceUnits"], NATIVE_UNITS)
        raw = {"schema_version": "1.1.0", "units": NATIVE_UNITS, "model_sha256": self.result["modelSha256"]}
        validate_metadata(raw)
        if HRX.is_file():
            validate_metadata(raw, HRX)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_metadata({**raw, "model_sha256": "0" * 64}, HRX)


class SpringProjectionTests(unittest.TestCase):
    def test_unsupported_units_are_rejected_instead_of_silently_relabeled(self):
        raw = {"schema_version": "1.1.0", "model_sha256": "0" * 64, "units": {**NATIVE_UNITS, "length": "mm"}}
        with self.assertRaisesRegex(ValueError, "units"):
            validate_metadata(raw)

    def test_force_over_area_converts_native_stress_to_mpa(self):
        s = spring_values({"cstress_force": -100, "area": 20, "phase_name": "0", "type": "SpringElastic"})
        self.assertEqual(s["stress"], -50)
        self.assertEqual(s["phase"], "Elastic")
        self.assertIsNone(spring_values({"force": 1, "area": 0})["stress"])


if __name__ == "__main__":
    unittest.main()
