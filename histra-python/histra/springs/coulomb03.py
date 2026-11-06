from __future__ import annotations
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple
from histra.types.phase_enum import PhaseEnum
from histra.types.xml_utils import _attr
from histra.types.hysteretic_curve_types import (
    HystereticTensileCurveTypeEnum,
    HystereticCompressiveCurveTypeEnum,
)
from histra.springs.base import Spring
from histra.springs.registry import _register_spring
from histra.springs.coulomb03_envelope import Coulomb03EnvelopeMixin
from histra.springs.coulomb03_state import Coulomb03StateMixin


@_register_spring("HiStrA.Objects.SpringCoulomb03")
@dataclass(slots=True)
class SpringCoulomb03(
    Coulomb03StateMixin,
    Coulomb03EnvelopeMixin,
    Spring,
):
    """Coulomb friction spring type 03 — direct port of C# SpringCoulomb03.

    Full Takeda hysteretic state machine with Coulomb (or Cacovic) yielding.
    """
    # -------------------------------------------------------------------
    # Serialised scalar parameters  (XML attributes)
    # -------------------------------------------------------------------
    check_contact_area: bool = False
    sub_law: str = "Coulomb"
    hysteretic_type: str = "Takeda"
    cohesion: float = 0.0
    mu: float = 0.0

    @property
    def c(self) -> float:
        return self.cohesion

    @c.setter
    def c(self, val: float) -> None:
        self.cohesion = val

    @property
    def kt(self) -> float:
        return self.k_tang

    @kt.setter
    def kt(self, val: float) -> None:
        self.k_tang = val
    plastic_strain_ratio: float = 0.0
    plastic_stiffness_ratio: float = 0.0001
    max_tensile_ratio: float = 0.8
    reload_stiffness_ratio: float = 1.0
    bcacovic: float = 0.0

    # -------------------------------------------------------------------
    # Backbone envelope points
    # -------------------------------------------------------------------
    mom1p: float = 0.0
    rot1p: float = 0.0
    mom2p: float = 0.0
    rot2p: float = 0.0
    mom3p: float = 0.0
    rot3p: float = 0.0
    mom1n: float = 0.0
    rot1n: float = 0.0
    mom2n: float = 0.0
    rot2n: float = 0.0
    mom3n: float = 0.0
    rot3n: float = 0.0

    # -------------------------------------------------------------------
    # Envelope slopes  (set by _set_envelope)
    # -------------------------------------------------------------------
    e1p: float = 0.0
    e2p: float = 0.0
    e3p: float = 0.0
    e1n: float = 0.0
    e2n: float = 0.0
    e3n: float = 0.0
    eup: float = 0.0
    eun: float = 0.0

    # -------------------------------------------------------------------
    # Energy  (envelope area)
    # -------------------------------------------------------------------
    energy_a: float = 0.0

    # -------------------------------------------------------------------
    # Array-backed state
    # -------------------------------------------------------------------
    fy: list = field(default_factory=lambda: [0.0, 0.0])
    ur: list = field(default_factory=lambda: [0.0, 0.0])
    umax: list = field(default_factory=lambda: [0.0, 0.0])   # [0]=CrotMax, [1]=CrotMin

    # -------------------------------------------------------------------
    # Committed state  (C prefix in C#)
    # -------------------------------------------------------------------
    _cstress: float = 0.0
    _cstrain: float = 0.0
    _cstress_normal: float = 0.0
    _cstress_normal_prev: float = 0.0
    _ccontact_area: float = 0.0
    _crot_pu: float = 0.0
    _crot_nu: float = 0.0
    _crot_lim_pu: float = 0.0
    _crot_lim_nu: float = 0.0
    _crot_yp: float = 0.0
    _crot_yn: float = 0.0
    _cmom_max: float = 0.0
    _cmom_min: float = 0.0
    _cload_indicator: int = 0
    _cplastic_tension_indicator: bool = False
    _cplastic_compression_indicator: bool = False
    _c_phase_unload_t: int = 0      # PhaseEnum.Elastic
    _c_phase_unload_c: int = 0
    _cup: float = 0.0
    cenergy_d: float = 0.0

    # -------------------------------------------------------------------
    # Trial state  (T prefix in C#)
    # -------------------------------------------------------------------
    _tstress: float = 0.0
    _tstrain: float = 0.0
    _tstress_normal: float = 0.0
    _tcontact_area: float = 0.0
    _trot_max: float = 0.0
    _trot_min: float = 0.0
    _trot_pu: float = 0.0
    _trot_nu: float = 0.0
    _trot_lim_pu: float = 0.0
    _trot_lim_nu: float = 0.0
    _trot_yp: float = 0.0
    _trot_yn: float = 0.0
    _tmom_max: float = 0.0
    _tmom_min: float = 0.0
    _tload_indicator: int = 0
    _tplastic_tension_indicator: bool = False
    _tplastic_compression_indicator: bool = False
    _t_phase_unload_t: int = 0
    _t_phase_unload_c: int = 0
    _tenergy_d: float = 0.0
    _tup: float = 0.0

    # -------------------------------------------------------------------
    # Misc
    # -------------------------------------------------------------------
    dn: float = 0.0
    area_corrente: float = 0.0
    k_tang_committed: float = 0.0
    _tangent_reload_t: float = 0.0
    _tangent_reload_c: float = 0.0
    phase: int = 0     # PhaseEnum.Elastic  (committed)
    t_phase: int = 0   # PhaseEnum.Elastic  (trial)

    # C# SpringCoulomb03 does not expose the raw stored reload tangent.
    # Its TangentReload_t/c getters enforce a lower bound of 0.0001 * K.
    # Keeping that behaviour is essential because the Takeda state machine
    # divides by these values while resolving yielding displacements.
    @property
    def tangent_reload_t(self) -> float:
        return max(1.0e-4 * self.k, self._tangent_reload_t)

    @tangent_reload_t.setter
    def tangent_reload_t(self, value: float) -> None:
        self._tangent_reload_t = value

    @property
    def tangent_reload_c(self) -> float:
        return max(1.0e-4 * self.k, self._tangent_reload_c)

    @tangent_reload_c.setter
    def tangent_reload_c(self, value: float) -> None:
        self._tangent_reload_c = value

    def __copy__(self) -> SpringCoulomb03:
        cls = self.__class__
        out = cls.__new__(cls)
        out.type_of = self.type_of
        out.extra = self.extra.copy()
        out.key = self.key
        out.parent_key = self.parent_key
        out.parent_type = self.parent_type
        out.spring_purpose = self.spring_purpose
        out.type_name = self.type_name
        out.area = self.area
        out.length = self.length
        out.k = self.k
        out.k_tang = self.k_tang
        out.f = self.f
        out.u = self.u
        out.is_on = self.is_on
        out.phase = self.phase
        out.t_phase = self.t_phase
        out._histra_batch_managed = self._histra_batch_managed

        out.check_contact_area = self.check_contact_area
        out.sub_law = self.sub_law
        out.hysteretic_type = self.hysteretic_type
        out.cohesion = self.cohesion
        out.mu = self.mu
        out.plastic_strain_ratio = self.plastic_strain_ratio
        out.plastic_stiffness_ratio = self.plastic_stiffness_ratio
        out.max_tensile_ratio = self.max_tensile_ratio
        out.reload_stiffness_ratio = self.reload_stiffness_ratio
        out.bcacovic = self.bcacovic

        out.mom1p = self.mom1p
        out.rot1p = self.rot1p
        out.mom2p = self.mom2p
        out.rot2p = self.rot2p
        out.mom3p = self.mom3p
        out.rot3p = self.rot3p
        out.mom1n = self.mom1n
        out.rot1n = self.rot1n
        out.mom2n = self.mom2n
        out.rot2n = self.rot2n
        out.mom3n = self.mom3n
        out.rot3n = self.rot3n

        out.e1p = self.e1p
        out.e2p = self.e2p
        out.e3p = self.e3p
        out.e1n = self.e1n
        out.e2n = self.e2n
        out.e3n = self.e3n
        out.eup = self.eup
        out.eun = self.eun
        out.energy_a = self.energy_a

        out.fy = self.fy.copy()
        out.ur = self.ur.copy()
        out.umax = self.umax.copy()

        out._cstress = self._cstress
        out._cstrain = self._cstrain
        out._cstress_normal = self._cstress_normal
        out._cstress_normal_prev = self._cstress_normal_prev
        out._ccontact_area = self._ccontact_area
        out._crot_pu = self._crot_pu
        out._crot_nu = self._crot_nu
        out._crot_lim_pu = self._crot_lim_pu
        out._crot_lim_nu = self._crot_lim_nu
        out._crot_yp = self._crot_yp
        out._crot_yn = self._crot_yn
        out._cmom_max = self._cmom_max
        out._cmom_min = self._cmom_min
        out._cload_indicator = self._cload_indicator
        out._cplastic_tension_indicator = self._cplastic_tension_indicator
        out._cplastic_compression_indicator = self._cplastic_compression_indicator
        out._c_phase_unload_t = self._c_phase_unload_t
        out._c_phase_unload_c = self._c_phase_unload_c
        out._cup = self._cup
        out.cenergy_d = self.cenergy_d

        out._tstress = self._tstress
        out._tstrain = self._tstrain
        out._tstress_normal = self._tstress_normal
        out._tcontact_area = self._tcontact_area
        out._trot_max = self._trot_max
        out._trot_min = self._trot_min
        out._trot_pu = self._trot_pu
        out._trot_nu = self._trot_nu
        out._trot_lim_pu = self._trot_lim_pu
        out._trot_lim_nu = self._trot_lim_nu
        out._trot_yp = self._trot_yp
        out._trot_yn = self._trot_yn
        out._tmom_max = self._tmom_max
        out._tmom_min = self._tmom_min
        out._tload_indicator = self._tload_indicator
        out._tplastic_tension_indicator = self._tplastic_tension_indicator
        out._tplastic_compression_indicator = self._tplastic_compression_indicator
        out._t_phase_unload_t = self._t_phase_unload_t
        out._t_phase_unload_c = self._t_phase_unload_c
        out._tenergy_d = self._tenergy_d
        out._tup = self._tup

        out.dn = self.dn
        out.area_corrente = self.area_corrente
        out.k_tang_committed = self.k_tang_committed
        out._tangent_reload_t = self._tangent_reload_t
        out._tangent_reload_c = self._tangent_reload_c
        return out

    def __deepcopy__(self, memo: dict) -> SpringCoulomb03:
        existing = memo.get(id(self))
        if existing is not None:
            return existing
        out = self.__copy__()
        out._histra_batch_managed = False
        memo[id(self)] = out
        return out

    # ===================================================================
    # XML construction
    # ===================================================================

    @classmethod
    def _from_xml(cls, elem: ET.Element, type_of: str = "") -> SpringCoulomb03:
        inst = super(SpringCoulomb03, cls)._from_xml(elem, type_of)
        inst.check_contact_area = _attr(elem, "CheckContactArea", False, lambda v: str(v).lower() == "true")
        inst.sub_law = _attr(elem, "SubLaw", "Coulomb")
        inst.hysteretic_type = _attr(elem, "HystereticType", "Takeda")
        inst.cohesion = _attr(elem, "C", 0.0, float) or _attr(elem, "Fy_0", 0.0, float)
        inst.mu = _attr(elem, "Mu", 0.0, float)
        inst.plastic_strain_ratio = _attr(elem, "PlasticStrainRatio", 0.0, float)
        inst.plastic_stiffness_ratio = _attr(elem, "PlasticStiffnessRatio", 0.0001, float)
        inst.max_tensile_ratio = _attr(elem, "MaxTensileRatio", 0.8, float)
        inst.reload_stiffness_ratio = _attr(elem, "ReloadStiffnessRatio", 1.0, float)
        inst.bcacovic = _attr(elem, "Bcacovic", 0.0, float)
        inst.mom1p = _attr(elem, "Mom1p", 0.0, float)
        inst.rot1p = _attr(elem, "Rot1p", 0.0, float)
        inst.mom2p = _attr(elem, "Mom2p", 0.0, float)
        inst.rot2p = _attr(elem, "Rot2p", 0.0, float)
        inst.mom3p = _attr(elem, "Mom3p", 0.0, float)
        inst.rot3p = _attr(elem, "Rot3p", 0.0, float)
        inst.mom1n = _attr(elem, "Mom1n", 0.0, float)
        inst.rot1n = _attr(elem, "Rot1n", 0.0, float)
        inst.mom2n = _attr(elem, "Mom2n", 0.0, float)
        inst.rot2n = _attr(elem, "Rot2n", 0.0, float)
        inst.mom3n = _attr(elem, "Mom3n", 0.0, float)
        inst.rot3n = _attr(elem, "Rot3n", 0.0, float)
        inst.e1p = _attr(elem, "E1p", inst.k, float)
        inst.e2p = _attr(elem, "E2p", 0.0, float)
        inst.e3p = _attr(elem, "E3p", 0.0, float)
        inst.e1n = _attr(elem, "E1n", inst.k, float)
        inst.e2n = _attr(elem, "E2n", 0.0, float)
        inst.e3n = _attr(elem, "E3n", 0.0, float)
        inst.eup = _attr(elem, "Eup", 0.0, float)
        inst.eun = _attr(elem, "Eun", 0.0, float)
        inst.energy_a = _attr(elem, "EnergyA", 0.0, float)
        inst.fy = [_attr(elem, "Fy1", 0.0, float), _attr(elem, "Fy2", 0.0, float)]
        inst.ur = [_attr(elem, "Ur1", 0.0, float), _attr(elem, "Ur2", 0.0, float)]
        inst._set_envelope()
        inst.revert_to_start()
        inst.revert_to_last_commit()
        return inst

    # ===================================================================
    # Envelope helpers
    # ===================================================================
