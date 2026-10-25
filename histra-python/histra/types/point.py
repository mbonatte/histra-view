from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Point:
    """Represents a 3D point / vector (port of C# ``Point``)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def from_str(cls, s: str) -> Point:
        parts = s.split(";")
        return cls(
            x=float(parts[0]) if len(parts) > 0 else 0.0,
            y=float(parts[1]) if len(parts) > 1 else 0.0,
            z=float(parts[2]) if len(parts) > 2 else 0.0,
        )

    def __iter__(self) -> Tuple[float, float, float]:
        yield self.x
        yield self.y
        yield self.z
