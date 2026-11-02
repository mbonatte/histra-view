import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hrx_cli
import mcp_server


class TestHrxCliAndMcp(unittest.TestCase):
    def test_catalog_sections(self):
        cat = hrx_cli.get_catalog()
        self.assertIn("geometry_defaults", cat)
        self.assertIn("masonry_material_templates", cat)
        self.assertIn("analysis_templates", cat)
        self.assertIn("masonry_advanced_schema", cat)
        self.assertIn("analysis_enums", cat)
        self.assertTrue(len(cat["masonry_material_templates"]) > 0)
        for mat in cat["masonry_material_templates"]:
            self.assertTrue(not mat.get("type") or mat["type"].endswith(".MasonryMaterial"))

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hrx_cli.main(["catalog", "--section", "masonry-schema"])
        self.assertEqual(rc, 0)
        parsed = json.loads(buf.getvalue())
        self.assertIn("rocking", parsed)
        self.assertIn("shear", parsed)
        self.assertIn("sliding", parsed)

    def test_cli_init_create_inspect_and_edit_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            spec_path = tmp / "spec.json"
            hrx_path = tmp / "bridge.hrx"

            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(hrx_cli.main(["init-spec", "-o", str(spec_path)]), 0)
            self.assertTrue(spec_path.exists())

            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(
                    hrx_cli.main([
                        "create",
                        "--spec",
                        str(spec_path),
                        "--set",
                        "nl=200",
                        "--set",
                        "spans.0.L=750",
                        "-o",
                        str(hrx_path),
                    ]),
                    0,
                )
            create_info = json.loads(buf.getvalue())
            self.assertTrue(hrx_path.exists())
            self.assertGreater(create_info["summary"]["quadCount"], 0)

            # Inspect materials
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(hrx_cli.main(["inspect", str(hrx_path), "--section", "materials"]), 0)
            mat_info = json.loads(buf.getvalue())
            self.assertGreater(len(mat_info["materials"]), 0)
            first_key = str(mat_info["materials"][0]["key"])

            # Edit material in Advanced mode (laws, sliding law, orthotropy, attributes)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(
                    hrx_cli.main([
                        "edit-material",
                        str(hrx_path),
                        "--key",
                        first_key,
                        "--sliding-law",
                        "LinearSoftening",
                        "--orthotropic-rocking",
                        "true",
                        "--set",
                        "Ehor=2100",
                        "--set",
                        "TensileCurveType=Exponential",
                        "--set",
                        "CompressiveCurveType=Parabolic",
                        "--set",
                        "Gs=0.025",
                    ]),
                    0,
                )
            edited_mat = json.loads(buf.getvalue())["material"]
            self.assertEqual(edited_mat["general"]["Ehor"], "2100")
            self.assertEqual(edited_mat["rocking"]["ortpf"], "true")
            self.assertEqual(edited_mat["rocking"]["TensileCurveType"], "Exponential")
            self.assertEqual(edited_mat["rocking"]["CompressiveCurveType"], "Parabolic")
            self.assertEqual(edited_mat["sliding"]["constitutiveLawDir1"], "LinearSoftening")
            self.assertEqual(edited_mat["sliding"]["scorrhor"], "true")
            self.assertEqual(edited_mat["sliding"]["SlidingFractureEnergy"], "true")
            self.assertEqual(edited_mat["sliding"]["Gs"], "0.025")

            # Edit analysis
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(
                    hrx_cli.main([
                        "edit-analysis",
                        str(hrx_path),
                        "--name",
                        "Vert",
                        "--set",
                        "MaxIterations=75",
                        "--set",
                        "ConvergenceTolerance=0.0005",
                    ]),
                    0,
                )
            edited_ana = json.loads(buf.getvalue())["analysis"]
            self.assertEqual(edited_ana["attributes"]["MaxIterations"], "75")
            self.assertEqual(edited_ana["attributes"]["ConvergenceTolerance"], "0.0005")

    def test_mcp_server_rpc_lifecycle_and_tools(self):
        init_res = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init_res["result"]["serverInfo"]["name"], "histra-hrx-builder")

        list_res = mcp_server.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in list_res["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {"hrx_catalog", "hrx_create_bridge", "hrx_inspect", "hrx_edit_material", "hrx_edit_analysis"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            hrx_path = Path(tmpdir) / "mcp_bridge.hrx"

            create_res = mcp_server.handle_rpc({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "hrx_create_bridge",
                    "arguments": {
                        "output_path": str(hrx_path),
                        "overrides": ["nl=200", "spans.0.L=700"],
                    },
                },
            })
            self.assertFalse(create_res["result"]["isError"])
            self.assertTrue(hrx_path.exists())

            edit_mat_res = mcp_server.handle_rpc({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "hrx_edit_material",
                    "arguments": {
                        "hrx_path": str(hrx_path),
                        "key": "18",
                        "sliding_law": "ElastoPlastic",
                        "orthotropic_rocking": False,
                        "attributes": {
                            "FmHor": 3.5,
                            "ConstitutiveLawMasonryShear": "ElastoPlasticDuctilityFixed",
                        },
                    },
                },
            })
            self.assertFalse(edit_mat_res["result"]["isError"])
            mat_payload = json.loads(edit_mat_res["result"]["content"][0]["text"])["material"]
            self.assertEqual(mat_payload["general"]["FmHor"], "3.5")
            self.assertEqual(mat_payload["shear"]["ConstitutiveLawMasonryShear"], "ElastoPlasticDuctilityFixed")
            self.assertEqual(mat_payload["sliding"]["constitutiveLawDir1"], "ElastoPlastic")

            edit_ana_res = mcp_server.handle_rpc({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "hrx_edit_analysis",
                    "arguments": {
                        "hrx_path": str(hrx_path),
                        "add_template": "Modal_0",
                        "attributes": {"Name": "Modal_Custom", "NumberOfEigenModes": 12},
                    },
                },
            })
            self.assertFalse(edit_ana_res["result"]["isError"])
            ana_payload = json.loads(edit_ana_res["result"]["content"][0]["text"])["analysis"]
            self.assertEqual(ana_payload["attributes"]["Name"], "Modal_Custom")
            self.assertEqual(ana_payload["attributes"]["NumberOfEigenModes"], "12")


if __name__ == "__main__":
    unittest.main()
