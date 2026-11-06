from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from ._types import Point


def _default_reference_e1() -> Tuple[float, float, float]:
    return (1.0, 0.0, 0.0)


def _default_reference_e2() -> Tuple[float, float, float]:
    return (0.0, 1.0, 0.0)


def _default_reference_e3() -> Tuple[float, float, float]:
    return (0.0, 0.0, 1.0)


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
    # Native ``Restraint.ReferenceSystem``.  The local stiffness array K is
    # expressed in these axes; interface afferences need their signs.
    reference_e1: Tuple[float, float, float] = field(default_factory=_default_reference_e1)
    reference_e2: Tuple[float, float, float] = field(default_factory=_default_reference_e2)
    reference_e3: Tuple[float, float, float] = field(default_factory=_default_reference_e3)
    reference_origin: Point = field(default_factory=Point)
    has_reference_system: bool = False
    # Native ``RestraintState.U``.  It holds the displacement of each local
    # restraint DOF, not global translations.  Fixed directions stay zero.
    u: List[float] = field(default_factory=lambda: [0.0] * 6)
    # Global DOF number (1-based) for each local K direction.  Zero means the
    # direction is a fixed (K=-1) or otherwise inactive restraint DOF.
    solver_gdls: List[int] = field(default_factory=lambda: [0] * 6)
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
        reference = elem.find("ReferenceSystem")
        if reference is not None:
            r.has_reference_system = True
            if reference.get("E1"):
                r.reference_e1 = Point.from_str(reference.get("E1"))
            if reference.get("E2"):
                r.reference_e2 = Point.from_str(reference.get("E2"))
            if reference.get("E3"):
                r.reference_e3 = Point.from_str(reference.get("E3"))
            if reference.get("Origin"):
                r.reference_origin = Point.from_str(reference.get("Origin"))
        r.reference_origin = Point(
            r.reference_origin.x, r.reference_origin.y, r.reference_origin.z
        )
        # The Point fields used for the local axes are vectors, not geometric
        # points.  Normalise them here to shield preparation from HRX files
        # written by tools that serialised non-unit axes.
        r.reference_e1, r.reference_e2, r.reference_e3 = (
            _unit_axis(r.reference_e1),
            _unit_axis(r.reference_e2),
            _unit_axis(r.reference_e3),
        )
        r.extra = dict(elem.attrib)
        return r


def _unit_axis(value: Point | Tuple[float, float, float]) -> Tuple[float, float, float]:
    if isinstance(value, Point):
        x, y, z = value.x, value.y, value.z
    else:
        x, y, z = (float(value[0]), float(value[1]), float(value[2]))
    length = (x * x + y * y + z * z) ** 0.5
    if length <= 1.0e-12:
        return (1.0, 0.0, 0.0)
    return (x / length, y / length, z / length)
