"""Original C# endpoint alignment and authored HRX geometry tolerance."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from histra.preprocessing.quad_faces import align_nodes
from histra.io.hr_loader import load_model


class CSharpNodeAlignmentTests(unittest.TestCase):
    def test_native_alignment_branches(self):
        path=Path(__file__).parent/"fixtures/csharp_node_alignment_2026_1_1.json"
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            with self.subTest(point=case["point"]):
                args=[np.asarray(case[name],dtype=np.float32) for name in ("point","first","second")]
                self.assertEqual(align_nodes(*args,case["tolerance"]),case["expected"])

    def test_hrx_loads_authored_tolerances(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"geometry.hrx"
            path.write_text('<HiStrA><AdvancedOptionsDefault ToleranceNode="0.01" TolerancePlane="0.02"/></HiStrA>',encoding="utf-8")
            model=load_model(path)
        self.assertEqual(model.geometry_tolerance_node,0.009999999776482582)
        self.assertEqual(model.geometry_tolerance_plane,0.019999999552965164)
