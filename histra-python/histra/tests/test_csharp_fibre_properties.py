"""Native C# oracle: every cell, both parents, geometry and stiffness."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.preprocessing.csharp_fibre_geometry import _csharp_properties, _csharp_stiffness
from histra.preprocessing.csharp_fibre_geometry import _csharp_fibre_stiffness_batch_nb

class TestOriginalCSharpFibreProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((Path(__file__).parent/'fixtures/csharp_fibre_properties_2026_1_1.json').read_text())['cases']

    def inputs(self,case):
        face=case['face'];vint=np.asarray(case['vint'],dtype=np.float32)
        far=vint[{0:2,1:3,2:0,3:1,4:5,5:4}[face]]
        if face>=4:far=far[::-1].copy()
        return vint[face],far,np.asarray(case['cells'],dtype=np.float32),np.asarray(case['e2'],dtype=np.float32)

    def test_every_fibre_property_against_native_csharp(self):
        for case in self.cases:
            near,far,cells,e2=self.inputs(case)
            for ref in case['expected']:
                with self.subTest(interface=case['interface'],quad=case['quad'],cell=ref['Cell']):
                    coeff,length,axis,area=_csharp_properties(near,far,cells[ref['Cell']])
                    np.testing.assert_array_equal(coeff,ref['Coefficients'])
                    self.assertEqual(length,ref['Length'])
                    self.assertEqual(area,ref['Area'])

    def test_compiled_factory_against_native_csharp(self):
        for case in self.cases:
            near,far,cells,e2=self.inputs(case)
            actual=np.empty((len(cells),3));errors=np.zeros(len(cells),dtype=np.int32)
            _csharp_fibre_stiffness_batch_nb(near,far,cells,1.,e2,actual,errors)
            np.testing.assert_array_equal(errors,0)
            for ref in case['expected']:
                with self.subTest(interface=case['interface'],quad=case['quad'],cell=ref['Cell']):
                    k,area,length=actual[ref['Cell']]
                    self.assertAlmostEqual(k,ref['KPerE'],delta=1e-10)
                    self.assertEqual(area,ref['SpringArea'])
                    self.assertEqual(length,ref['SpringLength'])

    def test_scalar_factory_against_native_csharp(self):
        scalar=getattr(_csharp_stiffness,'py_func',_csharp_stiffness)
        for case in self.cases:
            near,far,cells,e2=self.inputs(case)
            for ref in case['expected']:
                with self.subTest(interface=case['interface'],quad=case['quad'],cell=ref['Cell']):
                    k,area,length=scalar(near,far,cells[ref['Cell']],1.,e2)
                    self.assertAlmostEqual(k,ref['KPerE'],delta=1e-10)
                    self.assertEqual(area,ref['SpringArea'])
                    self.assertEqual(length,ref['SpringLength'])

if __name__=='__main__':unittest.main()
