from __future__ import annotations
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from histra.types.xml_utils import _attr
from histra.types.point import Point
from histra.types.afference_entry import AfferenceEntry


class _DynamicAttributes:
    """Provide a lazy instance dictionary for compatibility-only overrides.

    Production spring fields live in slots; ``__dict__`` is allocated only if
    callers attach a truly dynamic attribute (for example a test override).
    """
    __slots__ = ("__dict__",)


@dataclass(slots=True)
class Spring(_DynamicAttributes):
    """Base spring — used as fallback when *TypeOf* is unknown."""
    type_of: str = ""

    # -- stored as plain key-value dict for unknown attributes ---------------
    extra: Dict[str, str] = field(default_factory=dict)

    # -- known common attributes ---------------------------------------------
    key: int = 0
    parent_key: int = 0
    parent_type: str = ""
    spring_purpose: str = ""
    type_name: str = ""
    area: float = 0.0
    length: float = 0.0
    k: float = 0.0
    k_tang: float = 0.0
    f: float = 0.0
    u: float = 0.0

    # -- lifecycle flags -----------------------------------------------------
    is_on: bool = True
    phase: int = 0       # PhaseEnum value (committed)
    t_phase: int = 0     # PhaseEnum value (trial)

    # Runtime metadata used by the compiled solver.  Keeping this fixed field
    # in a slot avoids allocating a per-spring dynamic ``__dict__`` for the
    # hundreds of thousands of generated interface fibres.
    _histra_batch_managed: bool = False

    def compute_energy(self) -> Tuple[float, float, float]:
        """Original C# signed trial-to-commit energy increments."""
        from histra.springs.energy import spring_energy_increment
        return spring_energy_increment(
            self.k, getattr(self, "_cstress", 0.0), getattr(self, "_tstress", self.f),
            getattr(self, "_cstrain", 0.0), getattr(self, "_tstrain", self.u),
        )

    def get_k(self, alfa: float = 0.0) -> float:
        return self.k + (self.k_tang - self.k) * alfa

    def get_force(self) -> float:
        """Current spring force (C# ``Spring.GetForce()``).

        For a linear spring: ``F = k * u``.
        For nonlinear subclasses, override to return the committed force.
        """
        return self.k * self.u

    def get_incr_force(self) -> float:
        """Force increment since last commit (C# ``Spring.GetIncrForce()``)."""
        return 0.0

    def get_displacement(self) -> float:
        """Current spring displacement (C# ``Spring.GetDisplacement()``)."""
        return self.u

    def set_trial_strain(self, strain: float) -> None:
        """Set the current trial strain ``u`` and update state.

        C# ``Spring.setTrialStrain(strain)``.
        Base implementation just stores the strain and computes force.
        Nonlinear subclasses should override with their own integration.
        """
        self.u = strain
        self.f = self.k * self.u

    def revert_to_start(self) -> None:
        """Reset to initial (virgin) state (C# ``Spring.revertToStart()``)."""
        self.u = 0.0
        self.f = 0.0
        self.k_tang = self.k
        self.phase = 0
        self.t_phase = 0

    def revert_to_last_commit(self) -> None:
        """Revert trial state to last committed state (C# ``RevertToLastCommit()``)."""
        pass

    def commit(self) -> None:
        """Commit trial → committed (C# ``Spring.Commit()``)."""
        self.f = self.k * self.u

    def set_quad_diagonal(self, k: float, fy: Tuple[float, float] | None = None,
                           mu: float = 0.0, eps_u: Tuple[float, float] | None = None,
                           plastic_stiffness_ratio: float = 0.0,
                           reload_stiffness_ratio: float = 1.0,
                           max_tensile_ratio: float = 0.0,
                           plastic_stiffness_ratio2: float = 1.0,
                           plastic_strain_ratio: float = 1.0,
                           sub_law: str = "Linear",
                           is_ductility_fixed: bool = False,
                           bcacovic: float = 0.0) -> None:
        """Set diagonal spring properties (C# ``Spring.SetQuadDiagonal``).

        Maps the many arguments from ``SetDiagonalQuad`` into the spring.
        The base implementation stores ``k``; subclasses may store more.
        """
        self.k = k
        # Store remaining parameters as extra attributes for nonlinear laws
        if fy is not None:
            self.fy_t, self.fy_c = fy
        self.mu = mu
        if eps_u is not None:
            self.eps_u_t, self.eps_u_c = eps_u
        self.plastic_stiffness_ratio = plastic_stiffness_ratio
        self.reload_stiffness_ratio = reload_stiffness_ratio
        self.max_tensile_ratio = max_tensile_ratio
        self.plastic_stiffness_ratio2 = plastic_stiffness_ratio2
        self.plastic_strain_ratio = plastic_strain_ratio
        self.sub_law = sub_law
        self.is_ductility_fixed = is_ductility_fixed
        self.bcacovic = bcacovic

    @classmethod
    def from_xml(cls, elem: ET.Element) -> Spring:
        """Dispatch to the correct subclass based on *TypeOf*."""
        from histra.springs.registry import _SPRING_REGISTRY
        type_of = elem.get("TypeOf", "")
        subclass = _SPRING_REGISTRY.get(type_of, cls)
        return subclass._from_xml(elem, type_of)

    @classmethod
    def _from_xml(cls, elem: ET.Element, type_of: str = "") -> Spring:
        """Construct instance (default implementation for base spring).

        Subclasses may override for custom attribute parsing.
        """
        inst = cls(type_of=type_of or elem.get("TypeOf", ""))
        inst.key = _attr(elem, "Key", 0, int)
        inst.parent_key = _attr(elem, "ParentKey", 0, int)
        inst.parent_type = _attr(elem, "ParentType", "")
        inst.spring_purpose = _attr(elem, "SpringPurpose", "")
        inst.type_name = _attr(elem, "Type", "")
        inst.area = _attr(elem, "Area", 0.0, float)
        inst.length = _attr(elem, "Length", 0.0, float)
        inst.k = _attr(elem, "K", 0.0, float)
        inst.k_tang = _attr(elem, "Kt", 0.0, float) or _attr(elem, "K_tang", 0.0, float)
        inst.f = _attr(elem, "F", 0.0, float)
        inst.u = _attr(elem, "U", 0.0, float)
        known = {"TypeOf", "K", "Key", "ParentKey", "ParentType", "SpringPurpose",
                 "Type", "Area", "Length", "K_tang", "Kt", "F", "U"}
        for key, val in elem.attrib.items():
            if key not in known:
                inst.extra[key] = val
        return inst
