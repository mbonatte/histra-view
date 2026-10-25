"""C# GetAreaSpring/SetInterfaceSlidSpring geometry regressions."""
import unittest
from types import SimpleNamespace
from histra.types.point import Point
from histra.preprocessing.spring_assignment import _out_of_plane_spring_areas, _side_sliding_spring
from histra.preprocessing.constitutive_laws import CoulombLaw

class TestSlidingPatchAreas(unittest.TestCase):
    def test_tapered_patches_have_distinct_areas(self):
        # Same section widths as Dhir interface 5737: 30 and 145 over 100.
        i=SimpleNamespace(vint2d=[Point(0,30),Point(100,145),Point(100,0),Point(0,0)])
        self.assertEqual(_out_of_plane_spring_areas(i),(2937.5,5812.5))

    def test_rectangle_and_reversed_winding_remain_positive(self):
        points=[Point(0,10),Point(100,10),Point(100,0),Point(0,0)]
        for vertices in [points,list(reversed(points))]:
            with self.subTest(vertices=vertices):
                self.assertEqual(_out_of_plane_spring_areas(SimpleNamespace(vint2d=vertices)),(500.,500.))

    def test_capacity_uses_patch_area_and_stiffness_uses_common_half_area(self):
        quad=SimpleNamespace(key=1)
        model=SimpleNamespace(collections=SimpleNamespace(quads={1:quad}))
        law=CoulombLaw(E=100.,cohesion=.01,mu=.4,plastic_stiffness_ratio=0.,max_tensile_ratio=0.)
        spring=_side_sliding_spring(model,"Quad",1,SimpleNamespace(length=100.),
            out_of_plane=True,area=2937.5,vertical=False,law=law,distance=5.,
            stiffness_area=4375.)
        self.assertEqual(spring.k,87500.)
        self.assertEqual(spring.area,2937.5)
        self.assertEqual(spring.cohesion,29.375)
