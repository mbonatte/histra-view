from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from ._types import Point


@dataclass
class Restraint:
    key: int = 0
    name: str = ""
    node_c_keys: List[int] = field(default_factory=lambda: [0, 0])
    k: List[float] = field(default_factory=lambda: [-1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
    node_keys: List[int] = field(default_factory=lambda: [0, 0])
    material_key: int = 0
    computational_element_key: int = 0
    computational_element_type: str = ""
    computational_element_edge: int = 0
    points: List[Point] = field(default_factory=lambda: [Point(), Point(), Point(), Point()])
    g: Point = field(default_factory=Point)
    zg: float = 0.0
    parent_key: int = 0
    parent_type: str = ""
    layer_key: int = 0
    extra: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_xml(cls, elem) -> Restraint:
        r = cls()
        r.key = int(elem.get("Key", "0"))
        r.name = elem.get("Name", "")
        r.parent_key = int(elem.get("ParentKey", "0"))
        r.parent_type = elem.get("ParentTypeElement", "")
        nck1 = int(elem.get("NodeCKey1", "0"))
        nck2 = int(elem.get("NodeCKey2", "0"))
        r.node_c_keys = [nck1, nck2]
        r.node_keys = [int(elem.get("NodeKey1", "0")), int(elem.get("NodeKey2", "0"))]
        r.material_key = int(elem.get("MaterialKey", "0"))
        r.computational_element_key = int(elem.get("ComputationalElementKey", "0"))
        r.computational_element_type = elem.get("ComputationalElementType", "")
        r.computational_element_edge = int(elem.get("ComputationalElementEdge", "0"))
        r.zg = float(elem.get("Zg", "0"))
        r.layer_key = int(elem.get("LayerKey", "0"))
        if elem.get("G"):
            r.g = Point.from_str(elem.get("G"))
        for i in range(4):
            value = elem.get(f"Point{i+1}")
            if value:
                r.points[i] = Point.from_str(value)
        for i in range(6):
            # Translational fields are K1..K3, rotational fields are Kr1..Kr3.
            attr = f"K{i+1}" if i < 3 else f"Kr{i-2}"
            kval = elem.get(attr, None)
            if kval is not None:
                r.k[i] = float(kval)
        r.extra = dict(elem.attrib)
        return r
