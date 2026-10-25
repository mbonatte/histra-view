import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hrx_model import parse_hrx


def fixture(extra="", quad_attributes="", reference=""):
    return f'''<HiStrA>
    <Node Key="1" Point="0;0;0"/><Node Key="2" Point="10;0;0"/>
    <Node Key="3" Point="10;0;10"/><Node Key="4" Point="0;0;10"/>
    <Quad Key="1" NodeKey1="1" NodeKey2="2" NodeKey3="3" NodeKey4="4"
     MaterialKey="7" {quad_attributes}>{reference}</Quad>
    <Template Key="7" Name="Stone" Color="#FF123456" PurposeType="MasonryMaterial"/>
    {extra}</HiStrA>'''.encode()


def load(direction="0", value="2", extra=""):
    return f'''<Template Key="3" Name="Load" TypeOf="HiStrA.Objects.LoadTemplate">
      <LoadTemplateItem Key="9" IdLoadDirection="{direction}" LoadValue="{value}"
       IdTypeLoad="Force" IdLoadCondition="11" DirX="1" DirY="0" DirZ="0" {extra}/>
    </Template><LoadElement Key="2" ElementType="Quad" ElementKey="1" IdLoadTemplate="3"
    TypeOf="HiStrA.Objects.LineLoadElement" Point1="0;0;10" Point2="10;0;10"/>'''


class ProjectionTests(unittest.TestCase):
    def test_sample_inventory_and_load_mapping(self):
        data = (Path(__file__).resolve().parents[2] / "model_example.hrx").read_bytes()
        model = parse_hrx(data)
        self.assertEqual([len(model[k]) for k in ("nodes", "quads", "materials", "loads", "restraints")], [3216, 2520, 4, 8, 136])
        self.assertTrue(all(l["drawable"] and l["direction"] == [0, 0, -1] and l["value"] == 0.01 for l in model["loads"]))

    def test_gravity_ignores_custom_vector(self):
        model = parse_hrx(fixture(load(value="-2")))
        self.assertEqual(model["loads"][0]["direction"], [0, 0, -1])
        self.assertEqual(model["loads"][0]["value"], -2)
        self.assertEqual(model["materials"][0]["color"], "#123456")

    def test_material_library_includes_unassigned_materials(self):
        extra = '<Template Key="8" Name="Unused steel" PurposeType="SteelMaterial" Color="#FFAABBCC"/>'
        model = parse_hrx(fixture(extra))
        self.assertEqual(len(model["materials"]), 1)
        self.assertEqual(len(model["materialLibrary"]), 2)
        unused = next(m for m in model["materialLibrary"] if m["key"] == "8")
        self.assertEqual(unused["quadCount"], 0)
        self.assertEqual(unused["color"], "#AABBCC")

    def test_element_local_axis_and_normalization(self):
        reference = '<ReferenceSystem E1="0;3;4" E2="1;0;0" E3="0;0;1"/>'
        row = parse_hrx(fixture(load(direction="4"), reference=reference))["loads"][0]
        self.assertEqual(row["direction"], [0, .6, .8])
        self.assertTrue(row["drawable"])

    def test_missing_local_axis_is_reported(self):
        model = parse_hrx(fixture(load(direction="4")))
        self.assertFalse(model["loads"][0]["drawable"])
        self.assertTrue(model["warnings"])

    def test_restraint_parent_is_not_drawn_twice(self):
        extra = '''<Restraint Key="1" ParentKey="5" ParentTypeElement="GeometryLineRestraint"
          Point1="0;0;0" Point2="10;0;0" U1mechBehaviourType="Fixed"/>
          <GeometryLineRestraint Key="5" NodeKey1="1" NodeKey2="2"/>
          <GeometryLineRestraint Key="6" NodeKey1="3" NodeKey2="4"/>'''
        restraints = parse_hrx(fixture(extra))["restraints"]
        self.assertEqual(len(restraints), 2)
        self.assertEqual(restraints[0]["dofs"]["U1"], "Fixed")

    def test_explicit_and_quad_load_assignment_deduplicated(self):
        model = parse_hrx(fixture(load(), 'LoadTemplateLineKey="3"'))
        self.assertEqual(len(model["loads"]), 1)

    def test_missing_node_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid node"):
            parse_hrx(fixture().replace(b'NodeKey4="4"', b'NodeKey4="55"'))

    def test_doctype_rejected_in_utf16(self):
        data = '<!DOCTYPE HiStrA [<!ENTITY x "unsafe">]><HiStrA/>'.encode('utf-16')
        with self.assertRaisesRegex(ValueError, "DTD"):
            parse_hrx(data)

    def test_no_mesh_rejected(self):
        with self.assertRaisesRegex(ValueError, "No serialized Quad"):
            parse_hrx(b'<HiStrA/>')


if __name__ == '__main__':
    unittest.main()
