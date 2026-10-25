from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Tuple, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from histra.elements.interface import Interface


def _list2d(rows: int, cols: int) -> List[List[float]]:
    """Create a rows×cols zero-initialised 2-D list."""
    return [[0.0] * cols for _ in range(rows)]


@dataclass
class InterfaceState:
    """Port of Objects.InterfaceState (.NET).

    Stores the element-local displacement vector *u*, the three stiffness
    blocks (k, kslid, kslid_out_plan), the resultant forces and bending
    moments, and scratch arrays *v* / *fd* and the scalar *evd*.
    """
    u: List[float] = field(default_factory=lambda: [0.0] * 12)
    v: List[float] = field(default_factory=lambda: [0.0] * 12)
    fd: List[float] = field(default_factory=lambda: [0.0] * 12)
    evd: float = 0.0
    forces: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bending_moments: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    k: List[List[float]] = field(default_factory=lambda: _list2d(6, 6))
    kslid: List[List[float]] = field(default_factory=lambda: _list2d(2, 2))
    kslid_out_plan: List[List[float]] = field(default_factory=lambda: _list2d(4, 4))

    # Cached trial values used by the nonlinear solver. They are part of the
    # reversible element state and are therefore captured by SolverStateSnapshot.
    normal_increment: float = 0.0
    committed_normal_force: float = 0.0
    max_spring_displacement: float = 0.0

    # ── port of InterfaceState.Init(I) ──────────────────────────────────────
    def init_from_interface(self, intf: Interface) -> None:
        """Create/reshape the stiffness matrices to match *intf.dim_aff*.

        Port of ``InterfaceState.Init(Interface I)``.
        """
        d0 = intf.dim_aff[0] if len(intf.dim_aff) > 0 else 6
        d1 = intf.dim_aff[1] if len(intf.dim_aff) > 1 else 2
        d2 = intf.dim_aff[2] if len(intf.dim_aff) > 2 else 4
        self.k = _list2d(d0, d0)
        self.kslid = _list2d(d1, d1)
        self.kslid_out_plan = _list2d(d2, d2)

    # ── port of InterfaceState.Compute_du ───────────────────────────────────
    def compute_du(self, intf: Interface, x: np.ndarray, i: int) -> float:
        """Return Σ x[gdl-1] · alfa over the afference entries of DOF *i*.

        Port of ``InterfaceState.Compute_du(ref Interface I,
        ref LinearSystem A, int i)``.
        """
        if i >= len(intf.aff):
            return 0.0
        total = 0.0
        for entry in intf.aff[i]:
            g = entry.gdl - 1
            if 0 <= g < len(x):
                total += x[g] * entry.alfa
        return total
