from __future__ import annotations
import xml.etree.ElementTree as ET
from histra.types.xml_utils import _attr
from dataclasses import dataclass
from histra.springs.base import Spring
from histra.springs.registry import _register_spring


@_register_spring("HiStrA.Objects.SpringCoulomb")
@dataclass
class SpringCoulomb(Spring):
    """Coulomb friction spring (original type)."""
    mu: float = 0.0
    kt: float = 0.0
    kn: float = 0.0

    @classmethod
    def _from_xml(cls, elem: ET.Element, type_of: str = "") -> SpringCoulomb:
        inst = super()._from_xml(elem, type_of)
        inst.mu = _attr(elem, "Mu", 0.0, float)
        inst.kt = _attr(elem, "Kt", 0.0, float)
        inst.kn = _attr(elem, "Kn", 0.0, float)
        return inst
