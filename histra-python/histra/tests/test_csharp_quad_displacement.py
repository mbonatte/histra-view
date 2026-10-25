import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import struct
import numpy as np

from histra.postprocessing import quad_node_displacement


class NativeQuadDisplacementTests(unittest.TestCase):
    def test_original_quad_projection_binary_outputs(self):
        fixture = Path(__file__).with_name("fixtures") / "csharp_quad_displacement_2026_1_1.json"
        q = SimpleNamespace(
            aff=[[SimpleNamespace(gdl=i+1, alfa=1.0)] for i in range(7)],
            g=SimpleNamespace(x=1.25, y=-2.5, z=1.1),
            length=[1.0,1.0,1.0,123.456789], sin=[0.9,0.7,0.6,0.8], cos=[0.4,0.3,0.2,0.1],
            reference_e1=[0.6,0.8,0.0], reference_e2=[-0.8,0.6,0.0],
        )
        point = SimpleNamespace(x=31.25, y=-12.5, z=7.3)
        data = json.loads(fixture.read_text(encoding="utf-8-sig"))
        def decode(value):
            return struct.unpack("<d", struct.pack("<q", int(value)))[0]
        q.sin = [decode(v) for v in data["sin_bits"]]
        q.cos = [decode(v) for v in data["cos_bits"]]
        q.length[3] = decode(data["length_bits"])
        q.reference_e1 = [data["e1"][a] for a in ("X", "Y", "Z")]
        q.reference_e2 = [data["e2"][a] for a in ("X", "Y", "Z")]
        for case in data["cases"]:
            with self.subTest(vertex=case["vertex"], u=case["u"]):
                result = quad_node_displacement(q, point, case["vertex"], np.array([decode(v) for v in case["u_bits"]]))
                np.testing.assert_array_equal(result.astype(np.float32).view(np.int32), np.array(case["bits"], dtype=np.int32))
