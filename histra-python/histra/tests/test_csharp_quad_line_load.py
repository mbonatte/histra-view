"""Actual Dhir line loads evaluated by the original C# Quad routine."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.elements.quad import Quad
from histra.types.point import Point
from histra.preprocessing.quad_geometry import compute_quad_geometry_batch

class NativeQuadLineLoadTests(unittest.TestCase):
    def test_original_csharp_generalized_line_loads(self):
        cases=json.loads((Path(__file__).parent/'fixtures/csharp_quad_line_load_2026_1_1.json').read_text())['cases']
        for case in cases:
            with self.subTest(quad=case['quad'],load=case['key']):
                lengths,diagonals,cosines,sines,axes,centres,volumes=compute_quad_geometry_batch(np.asarray([case['nodes']],dtype=np.float32),np.asarray([case['thickness']],dtype=np.float32))
                nodes=[Point(*v) for v in case['nodes']]
                q=Quad(length=lengths[0].tolist(),sin=sines[0].tolist(),cos=cosines[0].tolist(),g=Point(*centres[0]),reference_origin=nodes[0],reference_e1=tuple(axes[0,0]),reference_e2=tuple(axes[0,1]),reference_e3=tuple(axes[0,2]))
                actual=q.compute_line_load_internal(nodes,case['points'],case['forces'],node_tolerance=case['tolerance'])
                np.testing.assert_array_equal(actual,case['expected'])
