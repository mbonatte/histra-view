import json
from pathlib import Path
import unittest
import numpy as np

from histra.postprocessing import _average_node_displacements


class NativeNodeDisplacementTests(unittest.TestCase):
    def test_original_node_average_binary_outputs(self):
        fixture = Path(__file__).with_name("fixtures") / "csharp_node_displacement_2026_1_1.json"
        for case in json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]:
            with self.subTest(inputs=case["inputs"]):
                result = _average_node_displacements(case["inputs"])
                np.testing.assert_array_equal(result.astype(np.float32).view(np.int32), np.array(case["bits"], dtype=np.int32))
