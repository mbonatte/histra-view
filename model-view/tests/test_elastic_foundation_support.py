"""Native Kz foundation support generation and viewer projection."""

from __future__ import annotations

import math
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from builder_api import build, defaults
from hrx_model import parse_hrx


def _node_points(root):
    return {
        element.get("Key"): [float(value) for value in element.get("Point", "").split(";")]
        for element in root.findall("Node")
    }


def _distance(first, second):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


class ElasticFoundationSupportTests(unittest.TestCase):
    def _payload(self, *, elastic: bool):
        payload = defaults()
        # One native mesh column per 10 cm forces multiple Quad columns under
        # each GeometryLineRestraint, exercising the subdivision path.
        payload["nl"] = 10.0
        pier = payload["piers"][0]
        pier["is_fix_dir_z"] = not elastic
        pier["Kz"] = 0.25
        return payload

    def _generated_root(self, *, elastic: bool):
        raw = build({"mode": "create", "payload": self._payload(elastic=elastic)})
        return ET.fromstring(raw), raw

    def test_fixed_generation_keeps_all_native_restraints_fixed(self):
        root, _ = self._generated_root(elastic=False)
        glrs = root.findall("GeometryLineRestraint")
        self.assertTrue(glrs)
        for glr in glrs:
            self.assertEqual(glr.get("K2"), "-1")
            self.assertEqual(glr.get("U2mechBehaviourType"), "Fixed")
        for restraint in root.findall("Restraint"):
            self.assertEqual(restraint.get("K2"), "-1")

    def test_elastic_vertical_k2_is_subdivided_by_tributary_area(self):
        root, raw = self._generated_root(elastic=True)
        nodes = _node_points(root)
        kz = 0.25
        elastic_glrs = [
            glr for glr in root.findall("GeometryLineRestraint")
            if float(glr.get("K2", "-1")) > 0.0
        ]
        self.assertTrue(elastic_glrs)
        self.assertTrue(any(len([
            child for child in root.findall("Restraint")
            if child.get("ParentKey") == glr.get("Key")
        ]) > 1 for glr in elastic_glrs))

        total_child_stiffness = 0.0
        for glr in elastic_glrs:
            parent_stiffness = float(glr.get("K2"))
            self.assertIn("U2mechBehaviourType", glr.attrib)
            self.assertEqual(glr.get("U2mechBehaviourType"), "Fixed")
            self.assertGreater(parent_stiffness, 0.0)
            children = [
                child for child in root.findall("Restraint")
                if child.get("ParentKey") == glr.get("Key")
            ]
            self.assertTrue(children)
            child_sum = sum(float(child.get("K2")) for child in children)
            self.assertAlmostEqual(child_sum, parent_stiffness, places=9)
            for child in children:
                self.assertEqual(child.get("U2mechBehaviourType"), "Fixed")
                p0 = nodes[child.get("NodeKey1")]
                p1 = nodes[child.get("NodeKey2")]
                tributary_length = _distance(p0, p1)
                self.assertAlmostEqual(
                    float(child.get("K2")),
                    kz * float(glr.get("B")) * tributary_length,
                    places=9,
                )
                total_child_stiffness += float(child.get("K2"))

        # The serialized support total is Kz * B * total foundation length.
        self.assertGreater(total_child_stiffness, 0.0)
        self.assertIn('K2="', raw.decode("utf-8"))

    def test_viewer_marks_positive_k2_as_elastic(self):
        root, raw = self._generated_root(elastic=True)
        model = parse_hrx(raw, "elastic.hrx")
        elastic = [
            restraint for restraint in model["restraints"]
            if restraint["type"] == "Restraint"
            and restraint["stiffness"][1] is not None
            and restraint["stiffness"][1] > 0.0
        ]
        self.assertTrue(elastic)
        self.assertEqual(elastic[0]["dofs"]["U2"], "Elastic")
        self.assertGreater(elastic[0]["stiffness"][1], 0.0)
        self.assertEqual(elastic[0]["dofs"]["U1"], "Fixed")

    def test_viewer_keeps_fixed_k2_fixed(self):
        _, raw = self._generated_root(elastic=False)
        model = parse_hrx(raw, "fixed.hrx")
        restraint = next(
            item for item in model["restraints"] if item["type"] == "Restraint"
        )
        self.assertEqual(restraint["dofs"]["U2"], "Fixed")
        self.assertEqual(restraint["stiffness"][1], -1.0)


if __name__ == "__main__":
    unittest.main()
