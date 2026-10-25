from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
from ._types import Point


@dataclass
class Node:
    key: int = 0
    point: Point = field(default_factory=Point)
    name: str = ""

    @classmethod
    def from_xml(cls, elem) -> Node:
        n = cls()
        n.key = int(elem.get("Key", "0"))
        n.name = elem.get("Name", "") or elem.get("Label", "")
        pstr = elem.get("Point")
        if pstr:
            n.point = Point.from_str(pstr)
        return n


@dataclass
class SlaveElement:
    slave_key: int = 0
    slave_type: str = ""


@dataclass
class NodeC:
    key: int = 0
    node_key: int = 0
    name: str = ""
    master_element_key: int = 0
    master_element_type: str = ""
    slave_elements: List[SlaveElement] = field(default_factory=list)

    @property
    def master_elements(self) -> List[SlaveElement]:
        return self.slave_elements

    @master_elements.setter
    def master_elements(self, val: List[SlaveElement]) -> None:
        self.slave_elements = val

    u: List[float] = field(default_factory=lambda: [0.0] * 6)
    p: List[float] = field(default_factory=lambda: [0.0] * 6)
    aff: List[list] = field(default_factory=lambda: [[] for _ in range(6)])
    is_independent: bool = True

    @classmethod
    def from_xml(cls, elem) -> NodeC:
        nc = cls()
        nc.key = int(elem.get("Key", "0"))
        nc.name = elem.get("Name", "")
        nc.node_key = int(elem.get("NodeKey", "0"))
        nc.master_element_key = int(elem.get("MasterElementKey", "0"))
        nc.master_element_type = elem.get("MasterElementType", "")
        nc.is_independent = elem.get("IsIndipendent", "true").lower() == "true"

        # SlaveElements
        se_group = elem.find("MasterElements")
        if se_group is not None:
            for se in se_group.findall("MasterElement"):
                nc.slave_elements.append(SlaveElement(
                    slave_key=int(se.get("Key", se.get("SlaveKey", "0"))),
                    slave_type=se.get("Value", se.get("SlaveType", "")),
                ))

        # U1..U6
        for i in range(6):
            ustr = elem.get(f"U{i+1}", None)
            if ustr is not None:
                nc.u[i] = float(ustr)

        return nc
