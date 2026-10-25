"""Hysteretic state transitions for ``SpringCoulomb03``.

Owns the C# state machines: the full Takeda trial update (generic and
diagonal-Quad variants) with its positive/negative increment branches, the
simpler ``Initial`` elastic-plastic update, and the commit/revert lifecycle
that makes rejected Newton/line-search trials exactly reversible.

The methods live on a mixin so ``SpringCoulomb03`` remains the single public
object; every body is verbatim from the original class. Branch coverage is
locked by ``test_coulomb03_phase_matrix.py`` and
``test_coulomb03_state_machine.py``.
"""
from __future__ import annotations

from histra.types.phase_enum import PhaseEnum


class Coulomb03StateMixin:
    """Takeda/Initial trial updates and the commit/revert lifecycle."""

    __slots__ = ()

    def _positive_increment_takeda(self, dstrain: float) -> None:
        """C# positiveIncrementTakeda."""
        if self._tload_indicator == 2:
            if (self._t_phase_unload_c == PhaseEnum.Reload_c
                    and self._tmom_min > self._cstress and self._cstress < 0.0):
                self._tmom_min = self._cstress
                self._trot_min = self._cstrain
                self._trot_nu = self._cstrain - self._cstress / (self.eun * 1.0)
            if self._t_phase_unload_c == PhaseEnum.Reload_c and self.t_phase == PhaseEnum.Reload_c:
                self._trot_lim_nu = self._cstrain
            self._tload_indicator = 1
            if self._cstress <= 0.0:
                self._trot_nu = self._cstrain - self._cstress / (self.eun * 1.0)
                self._trot_max = self.umax[0] * (1.0 + 0.0)

        self._tload_indicator = 1
        if not self._tplastic_tension_indicator:
            self._trot_max = self.rot1p
            self._tmom_max = self.mom1p

        tmom_max = self._tmom_max
        trot_nu = self._trot_nu

        if self._tstrain < self._trot_nu:
            self.k_tang = self.e1n
            self._tstress = self._cstress + self.k_tang * dstrain
            if self._tstress < self.mom1n:
                self._tstress = self.mom1n
            if self._tstress >= 0.0:
                self._tstress = 0.0
                self.k_tang = self.eun * 1e-09
            return

        p = self.t_phase
        if p == PhaseEnum.Plastic_c:
            self.k_tang = tmom_max / (self._trot_max - trot_nu)
            self._tstress = self.k_tang * (self._tstrain - trot_nu)
        elif p in (PhaseEnum.Elastic, PhaseEnum.Unload_c):
            if self._t_phase_unload_c == PhaseEnum.Elastic:
                self.k_tang = tmom_max / (self._trot_max - trot_nu)
                self._tstress = self._cstress + self.k_tang * dstrain
            elif self._t_phase_unload_c in (PhaseEnum.Plastic_c, PhaseEnum.Reload_c):
                self.k_tang = tmom_max / (self._trot_max - trot_nu)
                self._tstress = self.k_tang * (self._tstrain - trot_nu)
        elif p == PhaseEnum.Unload_t:
            if self._t_phase_unload_t in (PhaseEnum.Elastic, PhaseEnum.Plastic_t):
                self.k_tang = self.e1p
                self._tstress = self._cstress + self.k_tang * dstrain
            elif self._t_phase_unload_t == PhaseEnum.Reload_t:
                if self._tstrain < self._trot_lim_pu:
                    self.k_tang = self.e1p
                    self._tstress = self._cstress + self.k_tang * dstrain
                else:
                    self.k_tang = self.tangent_reload_t
                    self._tstress = self.k_tang * (self._tstrain - trot_nu)
        elif p == PhaseEnum.Reload_c:
            self.k_tang = tmom_max / (self._trot_max - trot_nu)
            self._tstress = self.k_tang * (self._tstrain - trot_nu)
        elif p == PhaseEnum.Reload_t:
            self.k_tang = self.tangent_reload_t
            self._tstress = self.k_tang * (self._tstrain - trot_nu)
        # Plastic_t: no-op

    def _negative_increment_takeda(self, dstrain: float) -> None:
        """C# negativeIncrementTakeda."""
        if self._tload_indicator == 1:
            if (self._t_phase_unload_t == PhaseEnum.Reload_t
                    and self._tmom_max < self._cstress and self._cstress > 0.0):
                self._tmom_max = self._cstress
                self._trot_max = self._cstrain
                self._trot_pu = self._cstrain - self._cstress / (self.eup * 1.0)
            if self._t_phase_unload_t == PhaseEnum.Reload_t and self.t_phase == PhaseEnum.Reload_t:
                self._trot_lim_pu = self._cstrain
            self._tload_indicator = 2
            if self._cstress >= 0.0:
                self._trot_pu = self._cstrain - self._cstress / (self.eup * 1.0)
                self._trot_min = self.umax[1] * (1.0 + 0.0)

        self._tload_indicator = 2
        if not self._tplastic_compression_indicator:
            self._trot_min = self.rot1n
            self._tmom_min = self.mom1n

        tmom_min = self._tmom_min
        trot_pu = self._trot_pu

        if self._tstrain > self._trot_pu:
            self.k_tang = self.e1p
            self._tstress = self._cstress + self.k_tang * dstrain
            if self._tstress > self.mom1p:
                self._tstress = self.mom1p
            if self._tstress <= 0.0:
                self._tstress = 0.0
                self.k_tang = self.eup * 1e-09
            return

        p = self.t_phase
        if p == PhaseEnum.Plastic_t:
            self.k_tang = tmom_min / (self._trot_min - trot_pu)
            self._tstress = self.k_tang * (self._tstrain - trot_pu)
        elif p in (PhaseEnum.Elastic, PhaseEnum.Unload_t):
            if self._t_phase_unload_t == PhaseEnum.Elastic:
                self.k_tang = tmom_min / (self._trot_min - trot_pu)
                self._tstress = self._cstress + self.k_tang * dstrain
            elif self._t_phase_unload_t in (PhaseEnum.Plastic_t, PhaseEnum.Reload_t):
                self.k_tang = tmom_min / (self._trot_min - trot_pu)
                self._tstress = self.k_tang * (self._tstrain - trot_pu)
        elif p == PhaseEnum.Unload_c:
            if self._t_phase_unload_c in (PhaseEnum.Elastic, PhaseEnum.Plastic_c):
                self.k_tang = self.e1n
                self._tstress = self._cstress + self.k_tang * dstrain
            elif self._t_phase_unload_c == PhaseEnum.Reload_c:
                if self._tstrain > self._trot_lim_nu:
                    self.k_tang = self.e1n
                    self._tstress = self._cstress + self.k_tang * dstrain
                else:
                    self.k_tang = self.tangent_reload_c
                    self._tstress = self.k_tang * (self._tstrain - trot_pu)
        elif p == PhaseEnum.Reload_t:
            self.k_tang = tmom_min / (self._trot_min - trot_pu)
            self._tstress = self.k_tang * (self._tstrain - trot_pu)
        elif p == PhaseEnum.Reload_c:
            self.k_tang = self.tangent_reload_c
            self._tstress = self.k_tang * (self._tstrain - trot_pu)
        # Plastic_c: no-op

    # ===================================================================
    # Main state machine — Takeda type (diagonal quad variant)
    # ===================================================================

    def set_trial_strain_takeda_diagonal_quad(
        self, strain: float, dN: float, masonry=None, volume: float = 0.0, sigma: float = 0.0
    ) -> int:
        """C# setTrialStrainTakedaDiagonalQuad."""
        self.dn = dN
        if self._tload_indicator == 0 and strain == 0.0:
            return 0
        self.revert_to_last_commit()
        self._tstrain = strain
        dstrain = self._tstrain - self._cstrain

        # Normal stress carried by the spring increment (flag=False means DN used _tstressNormal update at end)
        # _tstressNormal += DN is deferred to the end of this method

        tau = self._tau_limite(self._tstress_normal)
        num3 = tau / self.e1p if self.e1p != 0.0 else 0.0

        # Fracture energy path  (ConstitutiveLawMasonryShearEnum 4 or 5)
        if masonry is not None and hasattr(masonry, 'constitutive_law_masonry_shear') and masonry.constitutive_law_masonry_shear in (4, 5):
            shear_ult_strain = masonry.get_shear_ultimate_strain(tau, num3, volume, sigma)
            self.ur[0] = shear_ult_strain
            self.ur[1] = -shear_ult_strain
            self.mom2p = self.mom1p = tau
            self.mom2n = self.mom1n = -tau
            self.rot1p = num3
            self.rot2p = max(shear_ult_strain, self.rot1p * 1.0001)
            self.rot3p = max(shear_ult_strain, self.rot2p * 1.0001)
        else:
            self.mom1p = tau
            self.rot1p = num3
            if self.e3p < 0.0:
                self.rot2p = max(self.plastic_strain_ratio, self.rot1p * 1.0001)
                self.rot3p = self.rot2p - self.mom2p / self.e3p
            if self.rot2p < self.rot1p:
                self.rot2p = self.rot1p * 1.0001
            if self.rot3p < self.rot2p:
                self.rot3p = self.rot2p * 1.0001
            self.mom2p = self.mom1p + self.e2p * (self.rot2p - self.rot1p)

        self.mom1n = -self.mom1p
        self.rot1n = -self.rot1p
        self.mom2n = -self.mom2p
        self.rot2n = -self.rot2p
        self.rot3n = -self.rot3p
        self.fy[0] = self.mom1p
        self.fy[1] = self.mom1n

        # Slip check
        if self.mom1p == 0.0:
            self.t_phase = PhaseEnum.Slip
            self._tstress = 0.0
            self.k_tang = 0.0
            self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
            self._tstress_normal += self.dn
            return 0

        # Coming from Slip
        if self.phase == PhaseEnum.Slip:
            if self.mom1p > 0.0:
                self._tload_indicator = 0
                self.t_phase = PhaseEnum.Elastic
                self._tplastic_tension_indicator = True
                self._tplastic_compression_indicator = True
                self._trot_nu = self._cstrain
                self._trot_pu = self._cstrain
                self.k_tang = self.e2p
                self.tangent_reload_c = self.k_tang
                self.tangent_reload_t = self.k_tang
                self._tstress = self.k_tang * dstrain
                self._trot_max = self._cstrain + self.rot1p
                self._tmom_max = self.k_tang * self.rot1p
                self._trot_min = self._cstrain + self.rot1n
                self._tmom_min = self.k_tang * self.rot1n
                if dstrain > 0.0:
                    self._tload_indicator = 1
                    self.t_phase = PhaseEnum.Reload_t
                else:
                    self.t_phase = PhaseEnum.Reload_c
                    self._tload_indicator = 2
                if abs(self._tstress) - self.mom1p > 0.0:
                    sign = 1.0 if self._tstress > 0.0 else -1.0
                    self._tstress = self.mom1p * sign
                    if sign > 0.0:
                        self.t_phase = PhaseEnum.Plastic_t
                        self._tmom_max = self._tstress
                        self._trot_max = self._tstrain
                    else:
                        self.t_phase = PhaseEnum.Plastic_c
                        self._tmom_min = self._tstress
                        self._trot_min = self._tstrain
                self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
                self._tstress_normal += self.dn
                return 0
            self._tstress = 0.0
            self.k_tang = 0.0
            self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
            self._tstress_normal += self.dn
            return 0

        # Rupture
        if self.phase in (PhaseEnum.RuptureTraz, PhaseEnum.RuptureComp):
            self._tstress = 0.0
            self.k_tang = 0.0
            self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
            self._tstress_normal += self.dn
            return 0

        # Core state machine
        self._trot_yp = self._get_current_yielding_displacement_tension(self._c_phase_unload_t, dstrain)
        self._trot_yn = self._get_current_yielding_displacement_compression(self._c_phase_unload_c, dstrain)

        if self._tload_indicator == 0:
            self._tload_indicator = 1 if dstrain >= 0.0 else 2

        if self._tstrain >= self._trot_yp and dstrain > 0.0:
            self._trot_max = self._tstrain
            self.k_tang = self._pos_envlp_tangent_takeda(self._tstrain)
            self._tstress = self._pos_envlp_stress_takeda(self._tstrain)
            self._tload_indicator = 1
            num5 = (self._tstress - self._cstress) / self.e1p if self.e1p != 0.0 else 0.0
            self._tup += dstrain - num5
            if self.t_phase == PhaseEnum.Plastic_t:
                self._tplastic_tension_indicator = True
            self._tmom_max = self._tstress
        elif self._tstrain <= self._trot_yn and dstrain < 0.0:
            self._trot_min = self._tstrain
            self.k_tang = self._neg_envlp_tangent_takeda(self._tstrain)
            self._tstress = self._neg_envlp_stress_takeda(self._tstrain)
            self._tload_indicator = 2
            num6 = (self._tstress - self._cstress) / self.e1n if self.e1n != 0.0 else 0.0
            self._tup += dstrain - num6
            if self.t_phase == PhaseEnum.Plastic_c:
                self._tplastic_compression_indicator = True
            self._tmom_min = self._tstress
        elif dstrain < 0.0:
            self._negative_increment_takeda(dstrain)
            if self._tstress > 0.0:
                self.t_phase = PhaseEnum.Unload_t
            elif self.t_phase == PhaseEnum.Unload_c:
                self.t_phase = PhaseEnum.Unload_c
                if self._tstrain <= self._trot_lim_nu and self._c_phase_unload_c == PhaseEnum.Reload_c:
                    self.t_phase = PhaseEnum.Reload_c
            else:
                self.t_phase = PhaseEnum.Reload_c
        elif dstrain > 0.0:
            self._positive_increment_takeda(dstrain)
            if self._tstress < 0.0:
                self.t_phase = PhaseEnum.Unload_c
            elif self.t_phase == PhaseEnum.Unload_t:
                self.t_phase = PhaseEnum.Unload_t
                if self._tstrain >= self._trot_lim_pu and self._c_phase_unload_t == PhaseEnum.Reload_t:
                    self.t_phase = PhaseEnum.Reload_t
            else:
                self.t_phase = PhaseEnum.Reload_t

        self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
        self._tstress_normal += self.dn
        return 0

    # ===================================================================
    # Main state machine — Takeda type (generic)
    # ===================================================================

    def set_trial_strain_takeda(self, strain: float) -> int:
        """C# setTrialStrainTakeda (generic, no fracture-energy path)."""
        if self._tload_indicator == 0 and strain == 0.0:
            return 0
        self.revert_to_last_commit()
        self._tstrain = strain
        dstrain = self._tstrain - self._cstrain

        self.mom1p = self._tau_limite(self._tstress_normal)
        self.rot1p = self.mom1p / self.e1p if self.e1p != 0.0 else 0.0

        if self.e3p < 0.0:
            self.rot2p = max(self.plastic_strain_ratio, self.rot1p * 1.0001)
            self.rot3p = self.rot2p - self.mom2p / self.e3p
        if self.rot2p < self.rot1p:
            self.rot2p = self.rot1p * 1.0001
        if self.rot3p < self.rot2p:
            self.rot3p = self.rot2p * 1.0001
        self.mom2p = self.mom1p + self.e2p * (self.rot2p - self.rot1p)

        self.mom1n = -self.mom1p
        self.rot1n = -self.rot1p
        self.mom2n = -self.mom2p
        self.rot2n = -self.rot2p
        self.rot3n = -self.rot3p
        self.fy[0] = self.mom1p
        self.fy[1] = self.mom1n

        if self.mom1p == 0.0:
            self.t_phase = PhaseEnum.Slip
            self._tstress = 0.0
            self.k_tang = 0.0
            self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
            self._tstress_normal += self.dn
            return 0

        if self.phase == PhaseEnum.Slip:
            if self.mom1p > 0.0:
                self._tload_indicator = 0
                self.t_phase = PhaseEnum.Elastic
                self._tplastic_tension_indicator = True
                self._tplastic_compression_indicator = True
                self._trot_nu = self._cstrain
                self._trot_pu = self._cstrain
                self.k_tang = self.e2p
                self.tangent_reload_c = self.k_tang
                self.tangent_reload_t = self.k_tang
                self._tstress = self.k_tang * dstrain
                self._trot_max = self._cstrain + self.rot1p
                self._tmom_max = self.k_tang * self.rot1p
                self._trot_min = self._cstrain + self.rot1n
                self._tmom_min = self.k_tang * self.rot1n
                if dstrain > 0.0:
                    self._tload_indicator = 1
                    self.t_phase = PhaseEnum.Reload_t
                else:
                    self.t_phase = PhaseEnum.Reload_c
                    self._tload_indicator = 2
                if abs(self._tstress) - self.mom1p > 0.0:
                    sign = 1.0 if self._tstress > 0.0 else -1.0
                    self._tstress = self.mom1p * sign
                    if sign > 0.0:
                        self.t_phase = PhaseEnum.Plastic_t
                        self._tmom_max = self._tstress
                        self._trot_max = self._tstrain
                    else:
                        self.t_phase = PhaseEnum.Plastic_c
                        self._tmom_min = self._tstress
                        self._trot_min = self._tstrain
                self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
                self._tstress_normal += self.dn
                return 0
            self._tstress = 0.0
            self.k_tang = 0.0
            self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
            self._tstress_normal += self.dn
            return 0

        if self.phase in (PhaseEnum.RuptureTraz, PhaseEnum.RuptureComp):
            self._tstress = 0.0
            self.k_tang = 0.0
            self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
            self._tstress_normal += self.dn
            return 0

        self._trot_yp = self._get_current_yielding_displacement_tension(self._c_phase_unload_t, dstrain)
        self._trot_yn = self._get_current_yielding_displacement_compression(self._c_phase_unload_c, dstrain)

        if self._tload_indicator == 0:
            self._tload_indicator = 1 if dstrain >= 0.0 else 2

        if self._tstrain >= self._trot_yp and dstrain > 0.0:
            self._trot_max = self._tstrain
            self.k_tang = self._pos_envlp_tangent_takeda(self._tstrain)
            self._tstress = self._pos_envlp_stress_takeda(self._tstrain)
            self._tload_indicator = 1
            num5 = (self._tstress - self._cstress) / self.e1p if self.e1p != 0.0 else 0.0
            self._tup += dstrain - num5
            if self.t_phase == PhaseEnum.Plastic_t:
                self._tplastic_tension_indicator = True
            self._tmom_max = self._tstress
        elif self._tstrain <= self._trot_yn and dstrain < 0.0:
            self._trot_min = self._tstrain
            self.k_tang = self._neg_envlp_tangent_takeda(self._tstrain)
            self._tstress = self._neg_envlp_stress_takeda(self._tstrain)
            self._tload_indicator = 2
            num6 = (self._tstress - self._cstress) / self.e1n if self.e1n != 0.0 else 0.0
            self._tup += dstrain - num6
            if self.t_phase == PhaseEnum.Plastic_c:
                self._tplastic_compression_indicator = True
            self._tmom_min = self._tstress
        elif dstrain < 0.0:
            self._negative_increment_takeda(dstrain)
            if self._tstress > 0.0:
                self.t_phase = PhaseEnum.Unload_t
            elif self.t_phase == PhaseEnum.Unload_c:
                self.t_phase = PhaseEnum.Unload_c
                if self._tstrain <= self._trot_lim_nu and self._c_phase_unload_c == PhaseEnum.Reload_c:
                    self.t_phase = PhaseEnum.Reload_c
            else:
                self.t_phase = PhaseEnum.Reload_c
        elif dstrain > 0.0:
            self._positive_increment_takeda(dstrain)
            if self._tstress < 0.0:
                self.t_phase = PhaseEnum.Unload_c
            elif self.t_phase == PhaseEnum.Unload_t:
                self.t_phase = PhaseEnum.Unload_t
                if self._tstrain >= self._trot_lim_pu and self._c_phase_unload_t == PhaseEnum.Reload_t:
                    self.t_phase = PhaseEnum.Reload_t
            else:
                self.t_phase = PhaseEnum.Reload_t

        self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
        self._tstress_normal += self.dn
        return 0

    # ===================================================================
    # Main state machine — Initial type
    # ===================================================================

    def set_trial_strain_initial(self, strain: float) -> int:
        """C# setTrialStrainInitial (simpler elastic-plastic with hardening)."""
        self.revert_to_last_commit()
        self._tstrain = strain
        dstrain = self._tstrain - self._cstrain

        if self.phase == PhaseEnum.Rupture:
            self._tstress = self._cstress
            self._tstress_normal += self.dn
            return 0

        if self.check_contact_area:
            self._tcontact_area = self.area_corrente
            self.fy[0] += self.cohesion * (self._tcontact_area - self._ccontact_area) / self.area
            self.mom1p = self._tau_limite(self._tstress_normal, self._tcontact_area / self.area)
        else:
            self._tcontact_area = self.area
            self.mom1p = self._tau_limite(self._tstress_normal)

        c_hard = self.cohesion + self.h * abs(self._cup)
        self.fy[0] = self._tau_limite(self._tstress_normal, c_hard / self.cohesion) if self.cohesion != 0.0 else 0.0
        if self.fy[0] < 0.0:
            self.fy[0] = 0.0

        self.rot1p = self.mom1p / self.e1p if self.e1p != 0.0 else 0.0
        if self.e2p < 0.0:
            self.mom2p = 0.0
            self.rot2p = self.rot1p - self.mom1p / self.e2p
        else:
            if self.rot2p < self.rot1p:
                self.rot2p = self.rot1p
                self.rot3p = self.rot2p * 1.0001
            self.mom2p = self.mom1p + self.e2p * (self.rot2p - self.rot1p)

        self.mom1n = -self.mom1p
        self.rot1n = -self.rot1p
        self.mom2n = -self.mom2p
        self.rot2n = -self.rot2p
        self.rot3n = -self.rot3p

        if self.phase == PhaseEnum.Rupture and self.mom1p == 0.0:
            self._tstress = 0.0
            self.k_tang = 0.0
            return 0

        num3 = self._cstress + self.k * dstrain
        if abs(num3) - self.fy[0] > 0.0:
            if num3 > 0.0:
                self.t_phase = PhaseEnum.Plastic_t
                sign = 1.0
            else:
                self.t_phase = PhaseEnum.Plastic_c
                sign = -1.0
            num5 = (abs(num3) - self.fy[0]) / self.k
            num6 = self.k * num5 / (self.h + self.k)
            self.fy[0] += self.h * num6
            self._tstress = self.fy[0] * sign
            if self.t_phase == PhaseEnum.Plastic_t and self._tstress < 0.0:
                self.t_phase = PhaseEnum.Rupture
                self._tstress = 0.0
                self.k_tang = 0.0
            elif self.t_phase == PhaseEnum.Plastic_c and self._tstress > 0.0:
                self.t_phase = PhaseEnum.Rupture
                self._tstress = 0.0
                self.k_tang = 0.0
            else:
                self._tup += num6
                self.k_tang = self.e2p
        else:
            self._tstress = num3
            self.k_tang = self.k
            self.t_phase = PhaseEnum.Elastic

        self._tenergy_d = self.cenergy_d + 0.5 * (self._cstress + self._tstress) * dstrain
        self._tstress_normal += self.dn
        return 0

    # ===================================================================
    # Lifecycle
    # ===================================================================

    def revert_to_start(self) -> None:
        """C# revertToStart."""
        self.umax[0] = 0.0
        self.umax[1] = 0.0
        self._crot_pu = 0.0
        self._crot_nu = 0.0
        self.cenergy_d = 0.0
        self._cload_indicator = 0
        self._cstress = 0.0
        self._cstrain = 0.0
        self._tstrain = 0.0
        self._tstress = 0.0
        self.k_tang = self.e1p if self.e1p != 0.0 else self.k
        self._tstress_normal = 0.0
        self._cstress_normal = 0.0
        self.dn = 0.0
        self.f = self._cstress
        self.u = self._tstrain
        self.k_tang_committed = self.k_tang
        self._ccontact_area = self.area
        self._tcontact_area = self.area
        self.phase = PhaseEnum.Elastic
        self._cmom_max = 0.0
        self._cmom_min = 0.0
        self._crot_lim_pu = 0.0
        self._crot_lim_nu = 0.0
        self._crot_yp = 0.0
        self._crot_yn = 0.0
        self._cplastic_compression_indicator = False
        self._cplastic_tension_indicator = False
        self._c_phase_unload_t = PhaseEnum.Elastic
        self._c_phase_unload_c = PhaseEnum.Elastic
        self.tangent_reload_c = 0.0
        self.tangent_reload_t = 0.0

    def revert_to_last_commit(self) -> None:
        """C# RevertToLastCommit."""
        # C# restores the trial positive capacity from the committed negative
        # capacity here (``Fy[0] = -Fy[1]``).  Reversing that assignment lets
        # a rejected line-search trial leak its normal-force-updated ``Fy[0]``
        # into the next trial.
        self.fy[0] = -self.fy[1]
        self._trot_max = self.umax[0]
        self._trot_min = self.umax[1]
        self._trot_pu = self._crot_pu
        self._trot_nu = self._crot_nu
        self._tenergy_d = self.cenergy_d
        self._tload_indicator = self._cload_indicator
        self._tstress = self._cstress
        self._tstrain = self._cstrain
        self._tstress_normal = self._cstress_normal
        self._tcontact_area = self._ccontact_area
        self._tup = self._cup
        self.t_phase = self.phase
        self._tmom_max = self._cmom_max
        self._tmom_min = self._cmom_min
        self._trot_lim_pu = self._crot_lim_pu
        self._trot_lim_nu = self._crot_lim_nu
        self._trot_yp = self._crot_yp
        self._trot_yn = self._crot_yn
        self._tplastic_tension_indicator = self._cplastic_tension_indicator
        self._tplastic_compression_indicator = self._cplastic_compression_indicator
        self._t_phase_unload_t = self._c_phase_unload_t
        self._t_phase_unload_c = self._c_phase_unload_c

    def revert_to_last_commit_stress_normal(self) -> None:
        """C# ``revertToLastCommitStressNormal`` used by diagonal quads."""
        self._cstress_normal = self._cstress_normal_prev

    def commit(self) -> None:
        """C# Commit."""
        if not self.is_on:
            return
        self.fy[1] = -self.fy[0]
        self._cup = self._tup
        self.umax[0] = self._trot_max
        self.umax[1] = self._trot_min
        self._crot_pu = self._trot_pu
        self._crot_nu = self._trot_nu
        self.cenergy_d = self._tenergy_d
        self._cload_indicator = self._tload_indicator
        self._cstress_normal_prev = self._cstress_normal
        self._cstress = self._tstress
        self._cstrain = self._tstrain
        self._cstress_normal = self._tstress_normal
        self._ccontact_area = self._tcontact_area
        self.dn = 0.0
        self.f = self._cstress
        self.u = self._tstrain
        self.k_tang = self.k_tang
        self.k_tang_committed = self.k_tang
        self.phase = self.t_phase
        self._cmom_max = self._tmom_max
        self._cmom_min = self._tmom_min
        self._crot_lim_pu = self._trot_lim_pu
        self._crot_lim_nu = self._trot_lim_nu
        self._crot_yp = self._trot_yp
        self._crot_yn = self._trot_yn
        if self.phase == PhaseEnum.Plastic_t:
            self._t_phase_unload_t = self.phase
        elif self.phase == PhaseEnum.Plastic_c:
            self._t_phase_unload_c = self.phase
        elif self.phase == PhaseEnum.Reload_t:
            if not self._tplastic_tension_indicator and not self._tplastic_compression_indicator:
                self._t_phase_unload_t = PhaseEnum.Elastic
            else:
                self._t_phase_unload_t = self.phase
                self._tplastic_tension_indicator = True
            self.tangent_reload_t = self.k_tang
        elif self.phase == PhaseEnum.Reload_c:
            if not self._tplastic_tension_indicator and not self._tplastic_compression_indicator:
                self._t_phase_unload_c = PhaseEnum.Elastic
            else:
                self._t_phase_unload_c = self.phase
                self._tplastic_compression_indicator = True
            self.tangent_reload_c = self.k_tang
        self._cplastic_compression_indicator = self._tplastic_compression_indicator
        self._cplastic_tension_indicator = self._tplastic_tension_indicator
        self._c_phase_unload_t = self._t_phase_unload_t
        self._c_phase_unload_c = self._t_phase_unload_c

    # ===================================================================
    # Dispatch
    # ===================================================================

    def set_trial_strain(self, strain: float) -> None:
        """Dispatch to Takeda or Initial hysteretic type (C# setTrialStrain)."""
        if not self.is_on:
            return
        if self.hysteretic_type == "Takeda" or self.hysteretic_type == "TakedaTensileCompressive":
            self.set_trial_strain_takeda(strain)
        else:
            self.set_trial_strain_initial(strain)

    def get_force(self) -> float:
        return self._tstress

    def get_incr_force(self) -> float:
        return self._tstress - self._cstress

    def get_displacement(self) -> float:
        return self._tstrain
