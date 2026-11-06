import time
import unittest
from pathlib import Path

from builder_api import build, defaults
from histra_results import extract_histra_model, project_histra, project_histra_modal
from solver_api import RUNS_DIR, bundle_path_for_job, job_status, start_job


class SolverApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = defaults()
        payload["nl"] = 200
        cls.hrx_bytes = build({"mode": "create", "payload": payload})

    @classmethod
    def tearDownClass(cls):
        (RUNS_DIR / "solver_test_bridge.histra").unlink(missing_ok=True)
        (RUNS_DIR / "solver_test_bridge.hrx").unlink(missing_ok=True)

    def _wait_for_job(self, job_id: str, timeout: float = 60.0) -> dict:
        deadline = time.monotonic() + timeout
        status = job_status(job_id)
        while status["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.1)
            status = job_status(job_id)
        self.assertNotEqual(status["status"], "running", "Solver job timed out")
        return status

    def test_modal_analysis_runs_and_saves_histra_bundle(self):
        initial = start_job(
            self.hrx_bytes,
            "solver_test_bridge.hrx",
            "Modal_-1",
        )
        final = self._wait_for_job(initial["jobId"])
        self.assertEqual(final["status"], "completed")
        self.assertTrue(final["bundleReady"])
        self.assertGreater(final["logCount"], 0)
        self.assertEqual(len(final["stages"]), 1)
        self.assertEqual(final["stages"][0]["name"], "Modal_-1")
        self.assertIn("30", final["analysisStates"])
        self.assertEqual(final["analysisStates"]["30"]["State"], "ExecutedCompleted")

        bundle_path = bundle_path_for_job(initial["jobId"])
        self.assertTrue(Path(bundle_path).is_file())
        projected = project_histra(str(bundle_path), "Modal_-1", include_stress_fields=False, include_modal_shapes=False)
        self.assertTrue(any(m["name"] == "Modal_-1" for m in projected["modal"]))
        shapes = project_histra_modal(str(bundle_path), "Modal_-1")
        self.assertGreater(len(shapes["modes"]), 0)
        self.assertGreater(len(shapes["modes"][0]["displacements"]), 0)

    def test_static_analysis_runs_and_accumulates_in_histra_bundle(self):
        initial = start_job(
            self.hrx_bytes,
            "solver_test_bridge.hrx",
            "Vert",
        )
        final = self._wait_for_job(initial["jobId"])
        self.assertIn(final["status"], ("completed", "failed"))
        self.assertTrue(final["bundleReady"])
        self.assertIn("1", final["analysisStates"])

        bundle_path = bundle_path_for_job(initial["jobId"])
        self.assertTrue(Path(bundle_path).is_file())
        self.assertFalse(Path(bundle_path).with_suffix(".hrx").exists())
        projected = project_histra(str(bundle_path), "Vert", include_stress_fields=False, include_modal_shapes=False)
        catalog_names = [item["name"] for item in projected["analysisCatalog"]]
        self.assertIn("Vert", catalog_names)
        self.assertIn("Modal_-1", catalog_names)
        self.assertEqual(projected["defaultAnalysis"], "Vert")

        _embedded_bytes, embedded_name, embedded_model = extract_histra_model(bundle_path)
        self.assertEqual(embedded_name, "solver_test_bridge.hrx")
        by_key = {str(a["key"]): a for a in embedded_model["analyses"]}
        self.assertEqual(by_key["1"]["state"]["State"], "ExecutedCompleted")
        self.assertEqual(by_key["30"]["state"]["State"], "ExecutedCompleted")


if __name__ == "__main__":
    unittest.main()
