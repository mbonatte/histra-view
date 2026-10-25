from __future__ import annotations
from enum import IntEnum


class PhaseEnum(IntEnum):
    """Spring phase / load state machine (C# ``PhaseEnum``)."""
    Elastic = 0
    Plastic_t = 1
    Plastic_c = 2
    Unload_t = 3
    Unload_c = 4
    Reload_t = 5
    Reload_c = 6
    Rupture = 7
    RuptureTraz = 8
    RuptureComp = 9
    Slip = 10
