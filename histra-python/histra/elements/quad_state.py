from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class QuadState:
    u: List[float] = field(default_factory=lambda: [0.0] * 7)
    k: float = 0.0  # Current elemental stiffness (scalar, through diagonal DOF)
    p: List[float] = field(default_factory=lambda: [0.0] * 7)  # Loads per DOF
    f: float = 0.0
