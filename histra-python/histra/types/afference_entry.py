from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class AfferenceEntry:
    """Afference coefficient linking a local DOF to a global DOF.

    Attributes:
        gdl: 1-based global DOF index.
        alfa: Participation factor (C# field).
    """
    gdl: int
    alfa: float
