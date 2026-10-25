from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from histra.springs.base import Spring
from histra.springs.registry import _register_spring


@_register_spring("HiStrA.Objects.SpringLinearElastic")
@_register_spring("HiStrA.Objects.SpringElastic")
@dataclass(slots=True)
class SpringElastic(Spring):
    """C# ``SpringLinearElastic`` with distinct trial/committed state."""

    _tstress: float = 0.0
    _tstrain: float = 0.0
    _cstress: float = 0.0
    _cstrain: float = 0.0

    @classmethod
    def _from_xml(cls, elem: ET.Element, type_of: str = "") -> SpringElastic:
        spring = Spring._from_xml.__func__(cls, elem, type_of)
        spring._cstress = spring._tstress = float(spring.f)
        spring._cstrain = spring._tstrain = float(spring.u)
        if spring.k_tang == 0.0:
            spring.k_tang = spring.k
        return spring

    def get_force(self) -> float:
        return self._tstress

    def get_incr_force(self) -> float:
        return self._tstress - self._cstress

    def get_displacement(self) -> float:
        return self._tstrain

    def set_trial_strain(self, strain: float) -> None:
        if self.k_tang == 0.0:
            self.k_tang = self.k
        self._tstrain = float(strain)
        self._tstress = self._cstress + self.k_tang * (
            self._tstrain - self._cstrain
        )
        # C# keeps base U/F committed; trial response is exposed through
        # GetDisplacement/GetForce until Commit copies the dedicated fields.

    def revert_to_start(self) -> None:
        self._cstress = self._tstress = 0.0
        self._cstrain = self._tstrain = 0.0
        self.f = self.u = 0.0
        self.k_tang = self.k
        self.phase = self.t_phase = 0

    def revert_to_last_commit(self) -> None:
        self._tstress = self._cstress
        self._tstrain = self._cstrain
        self.f = self._cstress
        self.u = self._cstrain

    def commit(self) -> None:
        self._cstress = self._tstress
        self._cstrain = self._tstrain
        self.f = self._cstress
        self.u = self._cstrain
