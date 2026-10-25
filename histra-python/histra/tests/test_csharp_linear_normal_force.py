"""NR=False normal-force calculations from original C# calls."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from histra.elements.interface import Interface
from histra.elements.quad import Quad
from histra.springs.hysteretic import SpringHysteretic
from histra.types.afference_entry import AfferenceEntry
from histra.types.point import Point


def doubles(bits):
    return np.array([int(v) for v in np.atleast_1d(bits)], dtype=np.int64).view(np.float64)


class NativeLinearNormalForceTests(unittest.TestCase):
    def test_original_global_projection_and_quad_edge_reductions(self):
        path = Path(__file__).parent / 'fixtures/csharp_linear_normal_force_2026_1_1.json'
        for case in json.loads(path.read_text(encoding='utf-8-sig'))['cases']:
            with self.subTest(parent=case['parent'],variant=case['variant']):
                ls = SimpleNamespace(x=doubles(case['x_bits']))
                interfaces = {}
                for row in case['interfaces']:
                    first = 'Restraint' if case['parent']=='first' else 'Quad'
                    second = 'Restraint' if case['parent']=='second' else 'Quad'
                    key1,key2 = (33,17) if case['parent']=='first' else (17,33)
                    if not row['belongs']: key1,key2 = 91,92
                    intf = Interface(key=row['key'],length=row['length'],nrow=2,ncol=3,parent_type_element1=first,parent_type_element2=second,parent_element_key1=key1,parent_element_key2=key2)
                    intf.aff = [[AfferenceEntry(int(g),float(a)) for g,a in entries] for entries in row['aff']]
                    intf.status.k = doubles(row['matrix_bits']).reshape(6,6).tolist()
                    intf.status.u[:] = [1e100]*12
                    intf._perf_area = row['area']
                    for force,committed in zip(doubles(row['force_bits']),doubles(row['committed_bits']),strict=True):
                        s=SpringHysteretic();s._tstress=float(force);s._cstress=float(committed);intf.trasv_1.append(s)
                    np.testing.assert_array_equal(intf.compute_flex_def(ls),doubles(row['flex_bits']))
                    self.assertEqual(intf.compute_dn(ls,nr=False),doubles(row['dn_bits'])[0])
                    self.assertEqual(intf.status.u,[1e100]*12)
                    interfaces[intf.key]=intf
                quad=Quad(key=17,interface_keys=case['edges']+[[],[]])
                actual=quad.compute_dn(SimpleNamespace(interfaces=interfaces),ls,nr=False)
                np.testing.assert_array_equal(actual,[doubles(case[k])[0] for k in ('quad_dn_bits','sigma_bits')])
                # Dense buffers own force state during production solves. Object
                # springs may be stale until explicit synchronization.
                from histra.solver.hysteretic_runtime import HystereticBatchRuntime
                runtime = HystereticBatchRuntime(SimpleNamespace(
                    gdl=8, collections=SimpleNamespace(interfaces=interfaces, quads={}, materials={})))
                for intf in interfaces.values():
                    self.assertTrue(runtime.manages(intf))
                    for spring in intf.trasv_1:
                        spring._tstress = -999.
                        spring._cstress = -888.
                dense = quad.compute_dn(SimpleNamespace(interfaces=interfaces),ls,nr=False)
                np.testing.assert_array_equal(dense,actual)


    def test_invalid_projection_inputs_fail_explicitly(self):
        intf=Interface()
        with self.assertRaisesRegex(ValueError,'current x'):
            intf.compute_dn(nr=False)
        intf.aff[0]=[AfferenceEntry(2,1.)]
        with self.assertRaises(IndexError):
            intf.compute_dn(SimpleNamespace(x=np.zeros(1)),nr=False)
        intf.status.k=[[0.]]
        with self.assertRaisesRegex(ValueError,'6-by-6'):
            intf.compute_dn(SimpleNamespace(x=np.zeros(2)),nr=False)
