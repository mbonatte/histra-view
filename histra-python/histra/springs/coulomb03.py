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
