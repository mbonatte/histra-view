"""HiStrA model package — dataclass-based structural model."""
from ._types import Point, AfferenceEntry
from .node import Node, NodeC, SlaveElement
from .quad import Quad, QuadState
from .interface import Interface, InterfaceState
from .restraint import Restraint
from .masonry_material import MasonryMaterial
from .spring import (
    Spring,
    SpringCoulomb03,
    SpringElastic,
    SpringCoulomb,
    SpringMultiLinear,
    spring_from_xml,
)
from .load import (
    Analysis,
    LoadCombination,
    LoadCombinationItem,
    LoadCondition,
    LoadFunction,
    LoadFunctionItem,
)
from .model import Model, Collections

__all__ = [
    "Point", "AfferenceEntry", "Node", "NodeC", "SlaveElement",
    "Quad", "QuadState", "Interface", "InterfaceState", "Restraint",
    "MasonryMaterial",
    "Spring", "SpringCoulomb03", "SpringElastic", "SpringCoulomb",
    "SpringMultiLinear", "spring_from_xml", "Analysis", "LoadCombination",
    "LoadCombinationItem", "LoadCondition", "LoadFunction", "LoadFunctionItem",
    "Model", "Collections",
]
