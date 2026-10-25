from __future__ import annotations
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple

from histra.types.xml_utils import _attr
from histra.types.phase_enum import PhaseEnum
from histra.types.hysteretic_curve_types import (
    HystereticTensileCurveTypeEnum,
    HystereticCompressiveCurveTypeEnum,
)
from histra.springs.base import Spring
from histra.springs.registry import _register_spring


@_register_spring("HiStrA.Objects.SpringHysteretic")
@dataclass(slots=True)
class SpringHysteretic(Spring):
    """Hysteretic spring with multi-linear/parabolic backbone and pinching rules.

    Port of ``Objects.SpringHysteretic`` from the C# reference.
    """

    # -- Serialised scalar parameters (XML attributes) ------------------------
    pinch_xp: float = 0.0
    pinch_yp: float = 0.0
    pinch_xn: float = 0.0
    pinch_yn: float = 0.0
    damfc1p: float = 0.0
    damfc2p: float = 0.0
    damfc1n: float = 0.0
    damfc2n: float = 0.0
    betap: float = 0.0
    betan: float = 0.0

    # -- Backbone control points (positive / negative) ------------------------
    rot1p: float = 0.0
    mom1p: float = 0.0
    rot2p: float = 0.0
    mom2p: float = 0.0
    rot3p: float = 0.0
    mom3p: float = 0.0
    mom1n: float = 0.0
    rot1n: float = 0.0
    rot2n: float = 0.0
    mom2n: float = 0.0
    rot3n: float = 0.0
    mom3n: float = 0.0

    # -- Envelope stiffness ---------------------------------------------------
    e1n: float = 0.0
    e1p: float = 0.0
    e2n: float = 0.0
    e2p: float = 0.0
    e3n: float = 0.0
    e3p: float = 0.0
    eun: float = 0.0
    eup: float = 0.0

    # -- Energy ---------------------------------------------------------------
    energy_a: float = 0.0

    # -- Curve-type names (as stored in XML) ----------------------------------
    tensile_curve_type: str = "LinearSoftening"
    compressive_curve_type: str = "LinearSoftening"

    # -- Array-backed parameters [0] = tension/positive, [1] = compression/negative
    fy: list = field(default_factory=lambda: [0.0, 0.0])
    kt: list = field(default_factory=lambda: [0.0, 0.0])
    ur: list = field(default_factory=lambda: [0.0, 0.0])
    alfau: list = field(default_factory=lambda: [0.0, 0.0])
    alfar: list = field(default_factory=lambda: [0.0, 0.0])

    # -- Extreme-strain trackers ----------------------------------------------
    umax: list = field(default_factory=lambda: [0.0, 0.0])   # [0] = CrotMax, [1] = CrotMin
    uy_corr: list = field(default_factory=lambda: [0.0, 0.0])

    # -- Miscellaneous --------------------------------------------------------
    f0: float = 0.0
    f0_target: float = 0.0
    kstrain: float = 0.0
    cenergy_d: float = 0.0
    k_tang_committed: float = 0.0
    is_on: bool = True

    # -- Committed state (C prefix = committed) -------------------------------
    _crot_pu: float = 0.0
    _crot_nu: float = 0.0
    _cload_indicator: int = 0
    _cstress: float = 0.0
    _cstrain: float = 0.0

    # -- Trial state (T prefix = trial) ---------------------------------------
    _trot_max: float = 0.0
    _trot_min: float = 0.0
    _trot_pu: float = 0.0
    _trot_nu: float = 0.0
    _tenergy_d: float = 0.0
    _tload_indicator: int = 0
    _tstress: float = 0.0
    _tstrain: float = 0.0

    # -- Phase tracking -------------------------------------------------------
    phase: int = 0      # committed PhaseEnum value
    t_phase: int = 0    # trial PhaseEnum value

    def __copy__(self) -> SpringHysteretic:
        cls = self.__class__
        out = cls.__new__(cls)
        # Copy base slots
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

        # Copy SpringHysteretic slots
        out.pinch_xp = self.pinch_xp
        out.pinch_yp = self.pinch_yp
        out.pinch_xn = self.pinch_xn
        out.pinch_yn = self.pinch_yn
        out.damfc1p = self.damfc1p
        out.damfc2p = self.damfc2p
        out.damfc1n = self.damfc1n
        out.damfc2n = self.damfc2n
        out.betap = self.betap
        out.betan = self.betan

        out.rot1p = self.rot1p
        out.mom1p = self.mom1p
        out.rot2p = self.rot2p
        out.mom2p = self.mom2p
        out.rot3p = self.rot3p
        out.mom3p = self.mom3p
        out.mom1n = self.mom1n
        out.rot1n = self.rot1n
        out.rot2n = self.rot2n
        out.mom2n = self.mom2n
        out.rot3n = self.rot3n
        out.mom3n = self.mom3n

        out.e1n = self.e1n
        out.e1p = self.e1p
        out.e2n = self.e2n
        out.e2p = self.e2p
        out.e3n = self.e3n
        out.e3p = self.e3p
        out.eun = self.eun
        out.eup = self.eup
        out.energy_a = self.energy_a

        out.tensile_curve_type = self.tensile_curve_type
        out.compressive_curve_type = self.compressive_curve_type

        out.fy = self.fy.copy()
        out.kt = self.kt.copy()
        out.ur = self.ur.copy()
        out.alfau = self.alfau.copy()
        out.alfar = self.alfar.copy()
        out.umax = self.umax.copy()
        out.uy_corr = self.uy_corr.copy()

        out.f0 = self.f0
        out.f0_target = self.f0_target
        out.kstrain = self.kstrain
        out.cenergy_d = self.cenergy_d
        out.k_tang_committed = self.k_tang_committed

        out._crot_pu = self._crot_pu
        out._crot_nu = self._crot_nu
        out._cload_indicator = self._cload_indicator
        out._cstress = self._cstress
        out._cstrain = self._cstrain

        out._trot_max = self._trot_max
        out._trot_min = self._trot_min
        out._trot_pu = self._trot_pu
        out._trot_nu = self._trot_nu
        out._tenergy_d = self._tenergy_d
        out._tload_indicator = self._tload_indicator
        out._tstress = self._tstress
        out._tstrain = self._tstrain
        return out


    # ===================================================================
    # XML construction
    # ===================================================================

    @classmethod
    def _from_xml(cls, elem: ET.Element, type_of: str = "") -> SpringHysteretic:
        inst = cls(type_of=type_of or elem.get("TypeOf", ""))

        # --- Base Spring attributes ---
        inst.key = _attr(elem, "Key", 0, int)
        inst.parent_key = _attr(elem, "ParentKey", 0, int)
        inst.parent_type = _attr(elem, "ParentType", "")
        inst.spring_purpose = _attr(elem, "SpringPurpose", "")
        inst.type_name = _attr(elem, "Type", "")
        inst.area = _attr(elem, "Area", 0.0, float)
        inst.length = _attr(elem, "Length", 0.0, float)
        inst.k = _attr(elem, "K", 0.0, float)

        # --- Scalar parameters ---
        inst.pinch_xp = _attr(elem, "PinchXp", 0.0, float)
        inst.pinch_yp = _attr(elem, "PinchYp", 0.0, float)
        inst.pinch_xn = _attr(elem, "PinchXn", 0.0, float)
        inst.pinch_yn = _attr(elem, "PinchYn", 0.0, float)
        inst.damfc1p = _attr(elem, "Damfc1p", 0.0, float)
        inst.damfc2p = _attr(elem, "Damfc2p", 0.0, float)
        inst.damfc1n = _attr(elem, "Damfc1n", 0.0, float)
        inst.damfc2n = _attr(elem, "Damfc2n", 0.0, float)
        inst.betap = _attr(elem, "Betap", 0.0, float)
        inst.betan = _attr(elem, "Betan", 0.0, float)

        # --- Backbone points ---
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

        # --- Envelope stiffness ---
        inst.e1n = _attr(elem, "E1n", 0.0, float)
        inst.e1p = _attr(elem, "E1p", 0.0, float)
        inst.e2n = _attr(elem, "E2n", 0.0, float)
        inst.e2p = _attr(elem, "E2p", 0.0, float)
        inst.e3n = _attr(elem, "E3n", 0.0, float)
        inst.e3p = _attr(elem, "E3p", 0.0, float)
        inst.eun = _attr(elem, "Eun", 0.0, float)
        inst.eup = _attr(elem, "Eup", 0.0, float)

        # --- Energy ---
        inst.energy_a = _attr(elem, "EnergyA", 0.0, float)

        # --- Curve types ---
        inst.tensile_curve_type = _attr(elem, "TensileCurveType", "LinearSoftening")
        inst.compressive_curve_type = _attr(elem, "CompressiveCurveType", "LinearSoftening")

        # --- Array-backed parameters (serialised as individual attrs) ---
        inst.fy[0] = _attr(elem, "Fy1", 0.0, float)
        inst.fy[1] = _attr(elem, "Fy2", 0.0, float)
        inst.kt[0] = _attr(elem, "Kt1", 0.0, float)
        inst.kt[1] = _attr(elem, "Kt2", 0.0, float)
        inst.ur[0] = _attr(elem, "Ur1", 0.0, float)
        inst.ur[1] = _attr(elem, "Ur2", 0.0, float)
        inst.alfau[0] = _attr(elem, "AlfaU1", 0.0, float)
        inst.alfau[1] = _attr(elem, "AlfaU2", 0.0, float)
        inst.alfar[0] = _attr(elem, "AlfaR1", 0.0, float)
        inst.alfar[1] = _attr(elem, "AlfaR2", 0.0, float)

        # Initialise state
        inst.is_on = True
        inst.revert_to_start()
        inst.revert_to_last_commit()
        return inst

    # ===================================================================
    # Lifecycle  (port of C# revertToStart / RevertToLastCommit / Commit)
    # ===================================================================

    def revert_to_start(self) -> None:
        """Reset to initial (virgin) state (C# ``SpringHysteretic.revertToStart()``)."""
        self.umax[0] = 0.0   # CrotMax
        self.umax[1] = 0.0   # CrotMin
        self._crot_pu = 0.0
        self._crot_nu = 0.0
        self.cenergy_d = 0.0
        self._cload_indicator = 0
        self._cstress = 0.0
        self._cstrain = 0.0
        self._tstrain = 0.0
        self._tstress = 0.0
        self.k_tang = self.e1p if self.e1p != 0.0 else self.k
        self.k_tang_committed = self.k_tang
        self.phase = PhaseEnum.Elastic
        self.t_phase = PhaseEnum.Elastic
        self.f = self._cstress
        self.u = self._tstrain

    def revert_to_last_commit(self) -> None:
        """Revert trial state to last committed state (C# ``RevertToLastCommit()``)."""
        self._trot_max = self.umax[0]
        self._trot_min = self.umax[1]
        self._trot_pu = self._crot_pu
        self._trot_nu = self._crot_nu
        self._tenergy_d = self.cenergy_d
        self._tload_indicator = self._cload_indicator
        self._tstress = self._cstress
        self._tstrain = self._cstrain
        self.t_phase = self.phase

    def commit(self) -> None:
        """Commit trial → committed (C# ``SpringHysteretic.Commit()``)."""
        if not self.is_on:
            return
        self.umax[0] = self._trot_max           # CrotMax
        self.umax[1] = self._trot_min           # CrotMin
        self._crot_pu = self._trot_pu
        self._crot_nu = self._trot_nu
        self.cenergy_d = self._tenergy_d
        self._cload_indicator = self._tload_indicator
        self._cstress = self._tstress
        self._cstrain = self._tstrain
        self.f = self._cstress
        self.u = self._tstrain
        # k_tang stays the same (no-op in C#: base.K_tang = base.K_tang)
        self.k_tang_committed = self.k_tang
        self.phase = self.t_phase

    # ===================================================================
    # Queries  (port of C# GetForce / GetIncrForce / GetDisplacement)
    # ===================================================================

    def get_force(self) -> float:
        """Return trial stress (C# ``SpringHysteretic.GetForce()``)."""
        return self._tstress

    def get_incr_force(self) -> float:
        """Force increment trial − committed (C# ``SpringHysteretic.GetIncrForce()``)."""
        return self._tstress - self._cstress

    def get_displacement(self) -> float:
        """Return trial strain (C# ``SpringHysteretic.GetDisplacement()``)."""
        return self._tstrain

    # ===================================================================
    # Trial-strain driver  (port of C# setTrialStrain)
    # ===================================================================

    def set_trial_strain(self, strain: float) -> None:
        """Set trial strain and compute trial stress/tangent.

        Port of ``SpringHysteretic.setTrialStrain(double strain)``.
        NOTE: The C# method also contains a ``Model.GetIstance()`` geo-link
        early-return (lines 1597–1601) that is omitted here because it
        requires the external ``Model`` singleton.  That check only applies
        to lateral-earth-pressure loading and is not needed for the standard
        XML-loaded spring workflow.
        """
        if not self.is_on:
            return
        if self._tload_indicator == 0 and strain == 0.0:
            return

        self.revert_to_last_commit()
        self._tstrain = strain
        d_strain = self._tstrain - self._cstrain

        if self._tload_indicator == 0:
            self._tload_indicator = 1 if d_strain >= 0.0 else 2

        # --- Rupture check ---------------------------------------------------
        if self.phase in (PhaseEnum.Rupture, PhaseEnum.RuptureComp, PhaseEnum.RuptureTraz):
            self._tstress = 0.0
            self.k_tang = 0.0
            if self._tstrain >= self.umax[0]:
                self._trot_max = self._tstrain
            elif self._tstrain <= self.umax[1]:
                self._trot_min = self._tstrain

        # --- Envelope loading (new max / min) --------------------------------
        if self._tstrain >= self.umax[0]:
            self._trot_max = self._tstrain
            self._tstress = self._pos_envlp_stress(self._tstrain)
            self.k_tang = self._pos_envlp_tangent(self._tstrain)
            self._tload_indicator = 1
        elif self._tstrain <= self.umax[1]:
            self._trot_min = self._tstrain
            self._tstress = self._neg_envlp_stress(self._tstrain)
            self.k_tang = self._neg_envlp_tangent(self._tstrain)
            self._tload_indicator = 2
        elif d_strain < 0.0:
            # Negative increment (loading into compression or unloading from tension)
            if self._tstress > 0.0:
                self.t_phase = PhaseEnum.Unload_t
            else:
                self.t_phase = PhaseEnum.Reload_c
            self._negative_increment(d_strain)
        elif d_strain > 0.0:
            # Positive increment (loading into tension or unloading from compression)
            if self._tstress > 0.0:
                self.t_phase = PhaseEnum.Reload_t
            else:
                self.t_phase = PhaseEnum.Unload_c
            self._positive_increment(d_strain)

        # --- Energy accumulator ----------------------------------------------
        self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * d_strain
        self.f = self._tstress

    # ===================================================================
    # Positive / negative increment helpers
    # ===================================================================

    def _positive_increment(self, d_strain: float) -> None:
        """Port of C# ``positiveIncrement(double dStrain)``."""

        # Damage factor from compressive history
        num = (self.umax[1] / self.rot1n) ** self.betan if self.rot1n != 0.0 else 0.0
        if num <= 1.0:
            num = 1.0
        else:
            env_stress = self._neg_envlp_stress(self.umax[1])
            num = env_stress / self.mom1n / num if num != 0.0 else 1.0

        # Damage factor from tensile history
        num2 = (self.umax[0] / self.rot1p) ** self.betap if self.rot1p != 0.0 else 0.0
        if num2 <= 1.0:
            num2 = 1.0
        else:
            env_stress = self._pos_envlp_stress(self.umax[0])
            num2 = env_stress / self.mom1p / num2 if num2 != 0.0 else 1.0

        # Reversal from compression → tension
        if self._tload_indicator == 2:
            self._tload_indicator = 1
            if self._cstress <= 0.0:
                self._trot_nu = self._cstrain - self._cstress / (self.eun * num) if (self.eun * num) != 0.0 else 0.0
                if self._neg_envlp_stress(self.umax[1]) == 0.0:
                    self._trot_nu = 0.0
                num3 = self.cenergy_d - 0.5 * self._cstress / (self.eun * num) * self._cstress if (self.eun * num) != 0.0 else self.cenergy_d
                if num == 0.0:
                    num3 = self.cenergy_d
                num4 = 0.0
                if self.umax[1] < self.rot1n:
                    num4 = self.damfc2p * num3 / self.energy_a if self.energy_a != 0.0 else 0.0
                    num4 += self.damfc1p * (self.umax[1] - self.rot1n) / self.rot1n if self.rot1n != 0.0 else 0.0
                self._trot_max = self.umax[0] * (1.0 + num4)

        self._tload_indicator = 1
        self._trot_max = max(self._trot_max, self.rot1p)
        num5 = self._pos_envlp_stress(self._trot_max)
        num6 = self._neg_envlp_rotlim(self.umax[1])
        num7 = max(num6, self._trot_nu)

        num8 = self._trot_max - (1.0 - self.pinch_yp) * num5 / (self.eup * num2) if (self.eup * num2) != 0.0 else self._trot_max
        if num2 == 0.0:
            num8 = self._trot_max
        num9 = num7 + (num8 - num7) * self.pinch_xp

        # Region 1: below TrotNu (unloading continuation)
        if self._tstrain <= self._trot_nu:
            self.k_tang = self.eun * num
            self._tstress = self._cstress + self.k_tang * d_strain
            if self._tstress >= 0.0:
                self._tstress = 0.0
            return

        # Region 2: between TrotNu and pinch point
        if self._trot_nu < self._tstrain < num9:
            if self._tstrain <= num7:
                self._tstress = 0.0
                return
            self.k_tang = num5 * self.pinch_yp / (num9 - num7) if (num9 - num7) != 0.0 else 0.0
            num10 = self._cstress + self.eup * num2 * d_strain
            num11 = (self._tstrain - num7) * self.k_tang
            if num10 < num11:
                self._tstress = num10
                self.k_tang = self.eup * num2
            else:
                self._tstress = num11
            return

        # Region 3: beyond pinch point, towards TrotMax
        self.k_tang = (1.0 - self.pinch_yp) * num5 / (self._trot_max - num9) if (self._trot_max - num9) != 0.0 else 0.0
        num10 = self._cstress + self.eup * num2 * d_strain
        num11 = self.pinch_yp * num5 + (self._tstrain - num9) * self.k_tang
        if num10 < num11:
            self._tstress = num10
            self.k_tang = self.eup * num2
        else:
            self._tstress = num11

        # Crossing the TrotNu boundary during this step — two-segment correction
        if self._cstrain < self._trot_nu and self._tstrain > self._trot_nu:
            self.k_tang = self.eun * num
            self._tstress = self._cstress + self.k_tang * (self._trot_nu - self._cstrain)
            self.k_tang = (1.0 - self.pinch_yp) * num5 / (self._trot_max - num9) if (self._trot_max - num9) != 0.0 else 0.0
            self._tstress += self.k_tang * (self._tstrain - self._trot_nu)

    def _negative_increment(self, d_strain: float) -> None:
        """Port of C# ``negativeIncrement(double dStrain)``."""

        # Damage factor from tensile history
        num = (self.umax[1] / self.rot1n) ** self.betan if self.rot1n != 0.0 else 0.0
        if num <= 1.0:
            num = 1.0
        else:
            env_stress = self._neg_envlp_stress(self.umax[1])
            num = env_stress / self.mom1n / num if num != 0.0 else 1.0

        # Damage factor from compressive history
        num2 = (self.umax[0] / self.rot1p) ** self.betap if self.rot1p != 0.0 else 0.0
        if num2 <= 1.0:
            num2 = 1.0
        else:
            env_stress = self._pos_envlp_stress(self.umax[0])
            num2 = env_stress / self.mom1p / num2 if num2 != 0.0 else 1.0

        # Reversal from tension → compression
        if self._tload_indicator == 1:
            self._tload_indicator = 2
            if self._cstress >= 0.0:
                self._trot_pu = self._cstrain - self._cstress / (self.eup * num2) if (self.eup * num2) != 0.0 else 0.0
                if self._pos_envlp_stress(self.umax[0]) == 0.0:
                    self._trot_pu = 0.0
                num3 = self.cenergy_d - 0.5 * self._cstress / (self.eup * num2) * self._cstress if (self.eup * num2) != 0.0 else self.cenergy_d
                if num2 == 0.0:
                    num3 = self.cenergy_d
                num4 = 0.0
                if self.umax[0] > self.rot1p:
                    num4 = self.damfc2n * num3 / self.energy_a if self.energy_a != 0.0 else 0.0
                    num4 += self.damfc1n * (self.umax[0] - self.rot1p) / self.rot1p if self.rot1p != 0.0 else 0.0
                self._trot_min = self.umax[1] * (1.0 + num4)

        self._tload_indicator = 2
        self._trot_min = min(self._trot_min, self.rot1n)
        num5 = self._neg_envlp_stress(self._trot_min)
        num6 = self._pos_envlp_rotlim(self.umax[0])
        num7 = min(num6, self._trot_pu)

        num8 = self._trot_min - (1.0 - self.pinch_yn) * num5 / (self.eun * num) if (self.eun * num) != 0.0 else self._trot_min
        if num == 0.0:
            num8 = self._trot_min
        num9 = num7 + (num8 - num7) * self.pinch_xn

        # Region 1: above TrotPu (unloading continuation)
        if self._tstrain >= self._trot_pu:
            self.k_tang = self.eup * num2
            self._tstress = self._cstress + self.k_tang * d_strain
            if self._tstress <= 0.0:
                self._tstress = 0.0
            return

        # Region 2: between TrotPu and pinch point
        if self._tstrain <= self._trot_pu and self._tstrain > num9:
            if self._tstrain >= num7:
                self._tstress = 0.0
                return
            self.k_tang = num5 * self.pinch_yn / (num9 - num7) if (num9 - num7) != 0.0 else 0.0
            num10 = self._cstress + self.eun * num * d_strain
            num11 = (self._tstrain - num7) * self.k_tang
            if num10 > num11:
                self._tstress = num10
                self.k_tang = self.eun * num
            else:
                self._tstress = num11
            return

        # Region 3: beyond pinch point, towards TrotMin
        self.k_tang = (1.0 - self.pinch_yn) * num5 / (self._trot_min - num9) if (self._trot_min - num9) != 0.0 else 0.0
        num10 = self._cstress + self.eun * num * d_strain
        num11 = self.pinch_yn * num5 + (self._tstrain - num9) * self.k_tang
        if num10 > num11:
            self._tstress = num10
            self.k_tang = self.eun * num
        else:
            self._tstress = num11

        # Crossing the TrotPu boundary during this step — two-segment correction
        if self._cstrain > self._trot_pu and self._tstrain < self._trot_pu:
            self.k_tang = self.eup * num2
            self._tstress = self._cstress + self.k_tang * (self._trot_pu - self._cstrain)
            self.k_tang = (1.0 - self.pinch_yn) * num5 / (self._trot_min - num9) if (self._trot_min - num9) != 0.0 else 0.0
            self._tstress += self.k_tang * (self._tstrain - self._trot_pu)

    # ===================================================================
    # Envelope stress  (port of C# posEnvlpStress / negEnvlpStress)
    # ===================================================================

    def _pos_envlp_stress(self, strain: float) -> float:
        """Positive envelope stress (C# ``posEnvlpStress``)."""
        ct = self.tensile_curve_type
        if ct == "Elastic":
            return strain * self.k
        elif ct in ("LinearHardening", "LinearSoftening"):
            return self._pos_envlp_stress_linear(strain)
        elif ct == "Exponential":
            return self._pos_envlp_stress_exponential(strain)
        else:
            return -1.0

    def _pos_envlp_stress_linear(self, strain: float) -> float:
        """Positive envelope — linear/linear-softening branch."""
        if strain <= 0.0:
            return 0.0
        if strain <= self.rot1p:
            return self.e1p * strain
        if strain <= self.rot2p:
            return self.mom1p + self.e2p * (strain - self.rot1p)
        if strain <= self.rot3p or self.e3p > 0.0:
            return self.mom2p + self.e3p * (strain - self.rot2p)
        return self.mom3p

    def _pos_envlp_stress_exponential(self, strain: float) -> float:
        """Positive envelope — exponential softening branch."""
        if strain <= 0.0:
            return 0.0
        if strain <= self.rot1p:
            return self.e1p * strain
        denom = self.rot2p - self.rot1p
        if denom != 0.0:
            return self.mom1p * math.exp(-(strain - self.rot1p) / denom)
        return 0.0

    def _neg_envlp_stress(self, strain: float) -> float:
        """Negative envelope stress (C# ``negEnvlpStress``)."""
        ct = self.compressive_curve_type
        if ct == "Elastic":
            return strain * self.k
        elif ct in ("LinearHardening", "LinearSoftening"):
            return self._neg_envlp_stress_linear(strain)
        elif ct == "Parabolic":
            return self._neg_envlp_stress_parabolic(strain)
        else:
            return -1.0

    def _neg_envlp_stress_linear(self, strain: float) -> float:
        """Negative envelope — linear/linear-softening branch."""
        if strain >= 0.0:
            return 0.0
        if strain >= self.rot1n:
            return self.e1n * strain
        if strain >= self.rot2n:
            return self.mom1n + self.e2n * (strain - self.rot1n)
        if strain >= self.rot3n or self.e3n > 0.0:
            return self.mom2n + self.e3n * (strain - self.rot2n)
        return self.mom3n

    def _neg_envlp_stress_parabolic(self, strain: float) -> float:
        """Negative envelope — parabolic branch."""
        if strain >= 0.0:
            return 0.0
        if strain >= self.rot1n:
            return self.mom1n * strain / self.rot1n if self.rot1n != 0.0 else 0.0
        if strain >= self.rot2n:
            # r = (strain - rot1n) / (rot2n - rot1n)
            r = (strain - self.rot1n) / (self.rot2n - self.rot1n) if (self.rot2n - self.rot1n) != 0.0 else 0.0
            return self.mom1n * (1.0 + 4.0 * r - 2.0 * r * r)
        if strain >= self.rot3n:
            r = (strain - self.rot2n) / (self.rot3n - self.rot2n) if (self.rot3n - self.rot2n) != 0.0 else 0.0
            return self.mom2n * (1.0 - r * r)
        return 0.0

    # ===================================================================
    # Envelope tangent  (port of C# posEnvlpTangent / negEnvlpTangent)
    # ===================================================================

    def _pos_envlp_tangent(self, strain: float) -> float:
        """Positive envelope tangent stiffness (C# ``posEnvlpTangent``)."""
        ct = self.tensile_curve_type
        if ct == "Elastic":
            self.t_phase = PhaseEnum.Elastic
            return self.e1p
        elif ct in ("LinearHardening", "LinearSoftening"):
            return self._pos_envlp_tangent_linear(strain)
        elif ct == "Exponential":
            return self._pos_envlp_tangent_exponential(strain)
        else:
            return -1.0

    def _pos_envlp_tangent_linear(self, strain: float) -> float:
        """Positive envelope tangent — linear branch."""
        if strain < 0.0:
            return self.e1p * 1e-09
        if strain <= self.rot1p:
            self.t_phase = PhaseEnum.Elastic
            return self.e1p
        if strain <= self.rot2p:
            self.t_phase = PhaseEnum.Plastic_t
            return self.e2p
        if strain <= self.rot3p or self.e3p > 0.0:
            self.t_phase = PhaseEnum.Plastic_t
            return self.e3p
        self.t_phase = PhaseEnum.RuptureTraz
        return self.e1p * 1e-09

    def _pos_envlp_tangent_exponential(self, strain: float) -> float:
        """Positive envelope tangent — exponential branch."""
        if strain < 0.0:
            return self.e1p * 1e-09
        if strain <= self.rot1p:
            self.t_phase = PhaseEnum.Elastic
            return self.e1p
        self.t_phase = PhaseEnum.Plastic_t
        d_strain = self._tstrain - self._cstrain
        if d_strain != 0.0:
            return (self._tstress - self._cstress) / d_strain
        return self.e1p

    def _neg_envlp_tangent(self, strain: float) -> float:
        """Negative envelope tangent stiffness (C# ``negEnvlpTangent``)."""
        ct = self.compressive_curve_type
        if ct == "Elastic":
            self.t_phase = PhaseEnum.Elastic
            return self.e1n
        elif ct in ("LinearHardening", "LinearSoftening"):
            return self._neg_envlp_tangent_linear(strain)
        elif ct == "Parabolic":
            return self._neg_envlp_tangent_parabolic(strain)
        else:
            return -1.0

    def _neg_envlp_tangent_linear(self, strain: float) -> float:
        """Negative envelope tangent — linear branch."""
        if strain > 0.0:
            return self.e1n * 1e-09
        if strain >= self.rot1n:
            self.t_phase = PhaseEnum.Elastic
            return self.e1n
        if strain >= self.rot2n:
            self.t_phase = PhaseEnum.Plastic_c
            return self.e2n
        if strain >= self.rot3n or self.e3n > 0.0:
            self.t_phase = PhaseEnum.Plastic_c
            return self.e3n
        self.t_phase = PhaseEnum.RuptureComp
        return self.e1n * 1e-09

    def _neg_envlp_tangent_parabolic(self, strain: float) -> float:
        """Negative envelope tangent — parabolic branch."""
        if strain > 0.0:
            return self.e1n * 1e-09
        if strain >= self.rot1n:
            self.t_phase = PhaseEnum.Elastic
            return self.e1n
        if strain >= self.rot2n:
            self.t_phase = PhaseEnum.Elastic
            d_strain = self._tstrain - self._cstrain
            if d_strain != 0.0:
                return (self._tstress - self._cstress) / d_strain
            return self.e1n
        if strain >= self.rot3n:
            self.t_phase = PhaseEnum.Plastic_c
            d_strain = self._tstrain - self._cstrain
            if d_strain != 0.0:
                return (self._tstress - self._cstress) / d_strain
            return self.e1n
        self.t_phase = PhaseEnum.RuptureComp
        return self.e1n * 1e-09

    # ===================================================================
    # Rotation limits for zero-stress crossing (port of C# rotlim)
    # ===================================================================

    def _pos_envlp_rotlim(self, strain: float) -> float:
        """Positive envelope rotation limit (C# ``posEnvlpRotlim``).

        Returns the strain at which the positive envelope reaches zero
        stress, or ``+inf`` if no such point exists.
        """
        result = float('inf')
        if strain <= self.rot1p:
            return float('inf')
        if strain > self.rot1p and strain <= self.rot2p and self.e2p < 0.0:
            if self.e2p != 0.0:
                result = self.rot1p - self.mom1p / self.e2p
        if strain > self.rot2p and self.e3p < 0.0:
            if self.e3p != 0.0:
                result = self.rot2p - self.mom2p / self.e3p
        if result == float('inf'):
            return float('inf')
        if self._pos_envlp_stress(result) > 0.0:
            return float('inf')
        return result

    def _neg_envlp_rotlim(self, strain: float) -> float:
        """Negative envelope rotation limit (C# ``negEnvlpRotlim``).

        Returns the strain at which the negative envelope reaches zero
        stress, or ``-inf`` if no such point exists.
        """
        result = float('-inf')
        if strain >= self.rot1n:
            return float('-inf')
        if strain < self.rot1n and strain >= self.rot2n and self.e2n < 0.0:
            if self.e2n != 0.0:
                result = self.rot1n - self.mom1n / self.e2n
        if strain < self.rot2n and self.e3n < 0.0:
            if self.e3n != 0.0:
                result = self.rot2n - self.mom2n / self.e3n
        if result == float('-inf'):
            return float('-inf')
        if self._neg_envlp_stress(result) < 0.0:
            return float('-inf')
        return result

    # ===================================================================
    # Initialisation  (port of C# initialize / setEnvelope)
    # ===================================================================

    def initialize(self) -> None:
        """Compute envelope stiffness from backbone points (C# ``initialize()``).

        XML-loaded springs already have pre-computed E values in the file,
        so this method is only needed when creating a spring programmatically.
        """
        # C# SetInitial retains yield-coordinate metadata across revertToStart.
        self.uy_corr[:] = [value / self.k if self.k else 0.0 for value in self.fy]
        # Positive envelope
        if self.tensile_curve_type == "Elastic":
            self.mom1p = 1e19 * self.fy[0]
            self.rot1p = self.mom1p / self.k if self.k != 0.0 else 0.0
            self.rot2p = self.rot1p
            self.rot3p = self.rot1p
            self.mom2p = self.mom1p
            self.mom3p = self.mom1p
        elif self.tensile_curve_type in ("LinearHardening", "LinearSoftening"):
            self.mom1p = self.fy[0]
            self.rot1p = self.fy[0] / self.k if self.k != 0.0 else 0.0
            self.mom2p = self.mom1p + (self.ur[0] - self.rot1p) * self.kt[0]
            self.rot2p = self.ur[0]
            self.mom3p = 0.0
            self.rot3p = self.ur[0] * 1.01
        elif self.tensile_curve_type == "Exponential":
            self.mom1p = self.fy[0]
            self.rot1p = self.fy[0] / self.k if self.k != 0.0 else 0.0
            self.rot2p = self.ur[0]

        # Negative envelope
        if self.compressive_curve_type == "Elastic":
            self.mom1n = 1e19 * self.fy[1]
            self.rot1n = self.mom1n / self.k if self.k != 0.0 else 0.0
        elif self.compressive_curve_type in ("LinearHardening", "LinearSoftening"):
            self.mom1n = self.fy[1]
            self.rot1n = self.fy[1] / self.k if self.k != 0.0 else 0.0
            self.mom2n = self.mom1n + (self.ur[1] - self.rot1n) * self.kt[1]
            self.rot2n = self.ur[1]
            self.mom3n = 0.0
            self.rot3n = self.ur[1] * 1.01
        elif self.compressive_curve_type == "Parabolic":
            self.mom1n = self.fy[1] / 3.0
            self.rot1n = self.fy[1] / (3.0 * self.k) if self.k != 0.0 else 0.0
            self.mom2n = self.fy[1]
            self.rot2n = 5.0 * self.fy[1] / (3.0 * self.k) if self.k != 0.0 else 0.0
            self.mom3n = 0.0
            self.rot3n = self.ur[1]

        # Energy
        self.energy_a = 0.5 * (
            self.rot1p * self.mom1p
            + (self.rot2p - self.rot1p) * (self.mom2p + self.mom1p)
            + (self.rot3p - self.rot2p) * (self.mom3p + self.mom2p)
            + self.rot1n * self.mom1n
            + (self.rot2n - self.rot1n) * (self.mom2n + self.mom1n)
            + (self.rot3n - self.rot2n) * (self.mom3n + self.mom2n)
        )

        self.betap = self.alfau[0]
        self.betan = self.alfau[1]
        self._set_envelope()
        self.revert_to_start()
        self.revert_to_last_commit()

    def _set_envelope(self) -> None:
        """Compute envelope stiffnesses E1/E2/E3/Eu (C# ``setEnvelope()``)."""
        # Positive
        if self.tensile_curve_type == "Elastic":
            self.e1p = self.mom1p / self.rot1p if self.rot1p != 0.0 else self.k
        elif self.tensile_curve_type in ("LinearHardening", "LinearSoftening"):
            self.e1p = self.mom1p / self.rot1p if self.rot1p != 0.0 else self.k
            self.e2p = (self.mom2p - self.mom1p) / (self.rot2p - self.rot1p) if (self.rot2p - self.rot1p) != 0.0 else 0.0
            self.e3p = (self.mom3p - self.mom2p) / (self.rot3p - self.rot2p) if (self.rot3p - self.rot2p) != 0.0 else 0.0
        elif self.tensile_curve_type == "Exponential":
            self.e1p = self.mom1p / self.rot1p if self.rot1p != 0.0 else self.k

        # Negative
        if self.compressive_curve_type == "Elastic":
            self.e1n = self.mom1n / self.rot1n if self.rot1n != 0.0 else self.k
        elif self.compressive_curve_type in ("LinearHardening", "LinearSoftening"):
            self.e1n = self.mom1n / self.rot1n if self.rot1n != 0.0 else self.k
            self.e2n = (self.mom2n - self.mom1n) / (self.rot2n - self.rot1n) if (self.rot2n - self.rot1n) != 0.0 else 0.0
            self.e3n = (self.mom3n - self.mom2n) / (self.rot3n - self.rot2n) if (self.rot3n - self.rot2n) != 0.0 else 0.0
        elif self.compressive_curve_type == "Parabolic":
            self.e1n = self.mom1n / self.rot1n if self.rot1n != 0.0 else self.k

        # Eu — maximum of E1/E2/E3
        self.eup = max(self.e1p, self.e2p, self.e3p)
        self.eun = max(self.e1n, self.e2n, self.e3n)
