from __future__ import annotations
import xml.etree.ElementTree as ET
from histra.types.xml_utils import _attr
from dataclasses import dataclass
from typing import List
from histra.springs.base import Spring
from histra.springs.registry import _register_spring


@_register_spring("HiStrA.Objects.SpringMultiLinear")
@dataclass
class SpringMultiLinear(Spring):
    """Legacy HRX field container, without a numerical constitutive law.

    The original class is SpringMultiLinearPlastic, which has plastic history
    and reversal rules. Inheriting the base spring's linear response must not
    silently masquerade as that implementation. Supported masonry piecewise
    backbones are evaluated by SpringHysteretic instead.
    """
    # Deformation points (could be encoded as semicolon-separated values)
    deformations: str = ""
    forces: str = ""

    def set_trial_strain(self, strain: float) -> None:
        raise NotImplementedError("Generic multilinear plastic spring evaluation is not implemented")

    def get_force(self) -> float:
        raise NotImplementedError("Generic multilinear plastic spring evaluation is not implemented")

    def commit(self) -> None:
        raise NotImplementedError("Generic multilinear plastic spring evaluation is not implemented")

    @classmethod
    def _from_xml(cls, elem: ET.Element, type_of: str = "") -> SpringMultiLinear:
        inst = cls(type_of=type_of or elem.get("TypeOf", ""))
        inst.k = _attr(elem, "K", 0.0, float)
        inst.deformations = _attr(elem, "Deformations", "")
        inst.forces = _attr(elem, "Forces", "")
        known = {"TypeOf", "K", "Deformations", "Forces"}
        for key, val in elem.attrib.items():
            if key not in known:
                inst.extra[key] = val
        return inst
