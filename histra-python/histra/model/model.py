"""Top-level Model container and Collections holder."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional

from histra.model.node import Node, NodeC
from histra.model.quad import Quad
from histra.model.interface import Interface
from histra.model.restraint import Restraint
from histra.model.load import (
    Analysis, LoadCombination, LoadCondition, LoadFunction, LoadTemplate,
    LineLoadElement, ModelPoint,
)
from histra.model.masonry_material import MasonryMaterial


@dataclass
class Collections:
    """Named collections of all structural entities."""

    nodes: Dict[int, Node] = field(default_factory=dict)
    node_c: Dict[int, NodeC] = field(default_factory=dict)
    quads: Dict[int, Quad] = field(default_factory=dict)
    interfaces: Dict[int, Interface] = field(default_factory=dict)
    restraints: Dict[int, Restraint] = field(default_factory=dict)
    load_combinations: Dict[int, LoadCombination] = field(default_factory=dict)
    load_conditions: Dict[int, LoadCondition] = field(default_factory=dict)
    load_functions: Dict[int, LoadFunction] = field(default_factory=dict)
    load_templates: Dict[int, LoadTemplate] = field(default_factory=dict)
    line_loads: Dict[int, LineLoadElement] = field(default_factory=dict)
    model_points: Dict[int, ModelPoint] = field(default_factory=dict)
    analyses: Dict[int, Analysis] = field(default_factory=dict)
    materials: Dict[int, MasonryMaterial] = field(default_factory=dict)


@dataclass
class Model:
    """Top-level HiStrA model."""

    version: str = ""
    gdl: int = 0
    wizard_type: str = ""
    is_locked: bool = False
    # A locked HRX may serialize C#-prepared interfaces, afference and spring
    # definitions.  Those are reference data, never Python solver input: the
    # first Python preparation/solve must regenerate them from geometry and
    # material definitions.  The HRX loader sets this flag and Python
    # preprocessing clears it only after a successful fresh build.
    requires_python_preparation: bool = False
    source_path: Optional[str] = None
    geometry_tolerance_node: float = 1.0
    geometry_tolerance_plane: float = 1.0
    interface_nrow: int = 3
    interface_imax: float = 40.0
    mass_matrix_type: str = "Consistent"
    unsupported_v1_features: Dict[str, int] = field(default_factory=dict)
    unsupported_material_templates: Dict[int, str] = field(default_factory=dict)
    collections: Optional[Collections] = None
