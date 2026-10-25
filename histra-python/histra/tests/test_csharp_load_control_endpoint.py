"""Final load increments measured by invoking original C# routines."""
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

from histra.solver.load_control import LoadControl


class NativeLoadControlEndpointTests(unittest.TestCase):
    def test_final_interval_binary_outputs(self):
        fixture = Path(__file__).with_name("fixtures") / "csharp_load_control_endpoint_2026_1_1.json"
        for case in json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]:
            with self.subTest(case=case):
                control = LoadControl()
                control._lf_items = [(0.0, 0.0), (1.0, 1.0)]
                control._t = case["time"]
                control.mult = case["mult"]
                control.state.analysis = SimpleNamespace(mult=case["analysis_mult"], load_function=SimpleNamespace(discr_val=0.1))
                dt, df = control._get_increment()
                for value, key in ((dt, "dt_bits"), (df, "df_bits")):
                    self.assertEqual(struct.unpack("<q", struct.pack("<d", value))[0], int(case[key]))
