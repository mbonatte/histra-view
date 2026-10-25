"""Restraint material orientation from native geometry and law-builder calls."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.model.model import Model, Collections
from histra.model.masonry_material import MasonryMaterial
from histra.model.restraint import Restraint
from histra.model.node import Node
from histra.types.point import Point
from histra.elements.quad import Quad
from histra.elements.interface import Interface
from histra.preprocessing.material_selection import _restraint_reference_e1, _interface_sliding_law
from histra.preprocessing.spring_assignment import _side_transverse_spring, _transverse_side_properties_batch
from histra.preprocessing.constitutive_laws import sliding_law


def doubles(bits):
    return np.array([int(v) for v in np.atleast_1d(bits)], dtype=np.int64).view(np.float64)


class NativeRestraintOrientationTests(unittest.TestCase):
    def test_native_axes_and_all_three_material_law_blends(self):
        fixture = Path(__file__).parent / 'fixtures/csharp_restraint_orientation_2026_1_1.json'
        for case in json.loads(fixture.read_text(encoding='utf-8-sig'))['cases']:
            with self.subTest(p2=case['p2'], elastic=case['properties']['scorrhor']):
                material = MasonryMaterial(key=1, properties={k: str(v).lower() if isinstance(v,bool) else str(v) for k,v in case['properties'].items()})
                collection = Collections()
                collection.materials[1] = material
                collection.nodes = {1:Node(key=1,point=Point(*case['p1'])),2:Node(key=2,point=Point(*case['p2']))}
                collection.restraints[1] = Restraint(key=1,node_keys=[1,2])
                collection.quads[2] = Quad(key=2,material_key=1,reference_e1=(0.,0.,1.))
                model = Model(collections=collection)
                intf = Interface(key=1, parent_type_element1='Restraint', parent_element_key1=1, parent_type_element2='Quad', parent_element_key2=2, face2=4, reference_e1=case['interface_e1'])
                np.testing.assert_array_equal(_restraint_reference_e1(model,1), doubles(case['restraint_e1_bits']))
                cell = np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]])
                for override in (None,material):
                    _, scalar = _side_transverse_spring(model,'Restraint',1,0,intf,cell,material_override=override)
                    _, batched = _transverse_side_properties_batch(model,'Restraint',1,0,intf,np.array([cell]),material_override=override)
                    self.assertEqual(scalar,batched)
                    native = case['expected']['HorizontalFlexional']
                    self.assertEqual(scalar.E, doubles(native['E'])[0])
                    self.assertEqual(scalar.is_elastic, native['type']=='ConstitutiveLawElastic')
                    if not scalar.is_elastic:
                        for attr,name in [('fy_t','Fy_t'),('fy_c','Fy_c'),('eps_u_t','Eps_u_t'),('eps_u_c','Eps_u_c'),('ratio_et_t','RatioEttrac'),('ratio_et_c','RatioEtcomp')]:
                            self.assertEqual(getattr(scalar,attr),doubles(native[name])[0],attr)
                        self.assertEqual(scalar.tensile_curve,native['TensileCurveType'])
                        self.assertEqual(scalar.compressive_curve,native['CompressiveCurveType'])
                for oop,slot in [(False,'InplaneSlidingHorizontal'),(True,'OutOfPlaneSlidingHorizontal')]:
                    native = case['expected'][slot]
                    for side in (1,2):
                        law = _interface_sliding_law(model,intf,parent_type='Restraint',parent_key=1,face=4,material=material,out_of_plane=oop,vertical=False,cache={},side=side)
                        self.assertEqual(law.E,doubles(native['E'])[0])
                        self.assertEqual(law.is_elastic,native['type']=='ConstitutiveLawElastic')
                        if not law.is_elastic:
                            self.assertEqual(law.is_ductility_fixed,native['is_ductility_fixed'])
                            for attr,name in [('cohesion','Fy_0'),('mu','Mu'),('ductility','U_r'),('plastic_stiffness_ratio','PlasticStiffnessRatio')]:
                                self.assertEqual(getattr(law,attr),doubles(native[name])[0],attr)
                    if 'secondary_plastic_ratio' in native:
                        raw = sliding_law(material,out_of_plane=oop,direction='vert')
                        self.assertEqual(raw.plastic_stiffness_ratio,doubles(native['secondary_plastic_ratio'])[0])

    def test_vertical_plastic_stiffness_uses_original_ver_attribute(self):
        material = MasonryMaterial(properties={'SlidingPlasticStiffnessRatioVer':'.125','SlidingPlasticStiffnessRatioVert':'.875'})
        for oop in (False,True):
            self.assertEqual(sliding_law(material,out_of_plane=oop,direction='vert').plastic_stiffness_ratio,.125)
