"""Envelope mathematics for ``SpringCoulomb03`` (C# SpringCoulomb03).

Owns the backbone/secant-slope envelope family: ``setEnvelope`` slope
computation, the Coulomb/Cacovic ``TauLimite`` capacity, the hardening modulus
``H``, the positive/negative envelope stress and tangent branches of the
Takeda law, and the current yielding-displacement helpers used by the
transition machines in :mod:`histra.springs.coulomb03_state`.

The methods live on a mixin so ``SpringCoulomb03`` remains the single public
object; every body is verbatim from the original class.
"""
from __future__ import annotations

import math

from histra.types.phase_enum import PhaseEnum


class Coulomb03EnvelopeMixin:
    """Backbone envelope, capacity and yielding-displacement helpers."""

    __slots__ = ()

    def _set_envelope(self) -> None:
        """Compute envelope slopes from backbone points (C# setEnvelope)."""
        if self.rot1p != 0.0:
            self.e1p = self.mom1p / self.rot1p
        if self.rot2p - self.rot1p != 0.0:
            self.e2p = (self.mom2p - self.mom1p) / (self.rot2p - self.rot1p)
        if self.rot3p - self.rot2p != 0.0:
            self.e3p = (self.mom3p - self.mom2p) / (self.rot3p - self.rot2p)
        if self.rot1n != 0.0:
            self.e1n = self.mom1n / self.rot1n
        if self.rot2n - self.rot1n != 0.0:
            self.e2n = (self.mom2n - self.mom1n) / (self.rot2n - self.rot1n)
        if self.rot3n - self.rot2n != 0.0:
            self.e3n = (self.mom3n - self.mom2n) / (self.rot3n - self.rot2n)
        self.eup = max(self.e1p, self.e2p, self.e3p)
        # C# setEnvelope selects the numerically largest negative-side slope.
        # The slopes are generally positive secants/tangents despite belonging
        # to the negative envelope; using min() selected the soft descending
        # branch and corrupted Takeda unloading/reloading after a restart.
        self.eun = max(self.e1n, self.e2n, self.e3n)

    def _tau_limite(self, N: float, ratio_cohesion: float = 1.0) -> float:
        """Coulomb or Cacovic limiting shear stress (C# TauLimite)."""
        c = self.cohesion * ratio_cohesion
        if self.sub_law == "Coulomb":
            return max(0.0, c + self.mu * N)
        elif self.sub_law == "Cacovic":
            val = 1.0 + N / (1.5 * c)
            if val < 0.0:
                return 0.0
            return 1.5 / self.bcacovic * c * math.sqrt(val)
        return 0.0

    @property
    def h(self) -> float:
        """Hardening modulus (C# H = E1p*E2p/(E1p - E2p))."""
        if self.e1p == 0.0:
            self._set_envelope()
        denom = self.e1p - self.e2p
        if denom == 0.0:
            return 0.0
        return self.e1p * self.e2p / denom

    # ===================================================================
    # Envelope stress / tangent  (Takeda type)
    # ===================================================================

    def _pos_envlp_stress_takeda(self, strain: float) -> float:
        """Positive envelope stress (C# posEnvlpStressTakeda)."""
        if self.hysteretic_type == "Initial":
            return min(self.mom1p, self._cstress + self.e1p * (self._tstrain - self._cstrain))
        # Takeda
        yp = self._trot_yp if self._tplastic_tension_indicator else self.rot1p
        if strain < yp:
            return self.e1p * strain
        if strain <= self.rot2p:
            return self.mom1p + self.e2p * (strain - yp)
        if strain <= self.rot3p:
            return self.mom2p + self.e3p * (strain - self.rot2p)
        return self.mom3p

    def _neg_envlp_stress_takeda(self, strain: float) -> float:
        """Negative envelope stress (C# negEnvlpStressTakeda)."""
        if self.hysteretic_type == "Initial":
            return max(self.mom1n, self._cstress + self.e1n * (self._tstrain - self._cstrain))
        yn = self._trot_yn if self._tplastic_compression_indicator else self.rot1n
        if strain > yn:
            return self.e1n * strain
        if strain >= self.rot2n:
            return self.mom1n + self.e2n * (strain - yn)
        if strain >= self.rot3n:
            return self.mom2n + self.e3n * (strain - self.rot2n)
        return self.mom3n

    def _pos_envlp_tangent_takeda(self, strain: float) -> float:
        """Positive envelope tangent, sets t_phase based on branch (C# posEnvlpTangentTakeda)."""
        yp = self._trot_yp if self._tplastic_tension_indicator else self.rot1p
        if strain < yp:
            self.t_phase = PhaseEnum.Elastic
            return self.e1p
        if strain <= self.rot2p:
            self.t_phase = PhaseEnum.Plastic_t
            return self.e2p
        if strain <= self.rot3p:
            self.t_phase = PhaseEnum.Plastic_t
            return self.e3p
        self.t_phase = PhaseEnum.RuptureTraz
        return self.e1p * 1e-09

    def _neg_envlp_tangent_takeda(self, strain: float) -> float:
        """Negative envelope tangent, sets t_phase (C# negEnvlpTangentTakeda)."""
        pu = self._trot_pu
        yn = self._trot_yn if self._t_phase_unload_c != PhaseEnum.Elastic else self.rot1n
        if strain > pu:
            return self.e1n * 1e-09
        if strain > yn:
            self.t_phase = PhaseEnum.Elastic
            return self.e1n
        if strain >= self.rot2n:
            self.t_phase = PhaseEnum.Plastic_c
            return self.e2n
        if strain >= self.rot3n:
            self.t_phase = PhaseEnum.Plastic_c
            return self.e3n
        self.t_phase = PhaseEnum.RuptureComp
        return self.e1n * 1e-09

    # ===================================================================
    # Yielding displacement helpers
    # ===================================================================

    def _get_current_yielding_displacement_tension(self, phase_unload: int, dstrain: float) -> float:
        """C# GetCurrentYieldingDisplacementTension."""
        if not self._tplastic_tension_indicator:
            num2 = self.mom1p
            num3 = self.rot1p
        else:
            num2 = self._cmom_max
            num3 = self.umax[0]   # CrotMax

        if dstrain < 0.0:
            return num3

        if self.t_phase == PhaseEnum.Slip:
            return self._trot_max
        if self.t_phase in (PhaseEnum.Elastic, PhaseEnum.Plastic_t):
            return self.umax[0]
        if self.t_phase == PhaseEnum.Plastic_c:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload in (PhaseEnum.Plastic_t, PhaseEnum.Reload_t):
                num4 = self._cstrain - self._cstress / self.e1n
                num5 = self.tangent_reload_t if num2 <= 0.0 else num2 / (num3 - num4)
                return self.mom1p / num5 + num4
        if self.t_phase == PhaseEnum.Unload_t:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload == PhaseEnum.Plastic_t:
                return self._trot_pu + self.mom1p / self.e1p
            if phase_unload == PhaseEnum.Reload_t:
                if self._tstrain < self._trot_lim_pu:
                    return self._trot_pu + self.mom1p / self.e1p
                else:
                    return self._trot_nu + self.mom1p / self.tangent_reload_t
        if self.t_phase == PhaseEnum.Unload_c:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload in (PhaseEnum.Plastic_t, PhaseEnum.Reload_t):
                num5 = self.tangent_reload_t if num2 <= 0.0 else num2 / (num3 - self._trot_nu)
                return self._trot_nu + self.mom1p / num5
        if self.t_phase == PhaseEnum.Reload_t:
            if phase_unload in (PhaseEnum.Elastic, PhaseEnum.Reload_t):
                num5 = self.tangent_reload_t
                num = self._trot_nu + self.mom1p / num5
                if self.e3p < 0.0:
                    val = (self._trot_nu * num5 - self.rot3p * self.e3p) / (num5 - self.e3p)
                    num = min(num, val)
                return num
        if self.t_phase == PhaseEnum.Reload_c:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload == PhaseEnum.Plastic_t:
                num4 = self._cstrain - self._cstress / self.e1n
                num5 = self.tangent_reload_t if num2 <= 0.0 else num2 / (num3 - num4)
                return num4 + self.mom1p / num5
            if phase_unload == PhaseEnum.Reload_t:
                if self._t_phase_unload_c == PhaseEnum.Reload_c:
                    num4 = self._cstrain - self._cstress / self.e1n
                    num5 = self.tangent_reload_t if num2 <= 0.0 else num2 / (num3 - num4)
                    return self._trot_nu + self.mom1p / num5
                else:
                    return self._trot_nu + self.mom1p / self.tangent_reload_t
        return num3

    def _get_current_yielding_displacement_compression(self, phase_unload: int, dstrain: float) -> float:
        """C# GetCurrentYieldingDisplacementCompression."""
        if not self._tplastic_compression_indicator:
            num2 = self.mom1n
            num3 = self.rot1n
        else:
            num2 = self._cmom_min
            num3 = self.umax[1]   # CrotMin

        if dstrain > 0.0:
            return num3

        if self.t_phase == PhaseEnum.Slip:
            return self._trot_min
        if self.t_phase in (PhaseEnum.Elastic, PhaseEnum.Plastic_c):
            return self.umax[1]
        if self.t_phase == PhaseEnum.Plastic_t:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload in (PhaseEnum.Plastic_c, PhaseEnum.Reload_c):
                num4 = self._cstrain - self._cstress / self.e1p
                tc = self.tangent_reload_c if num2 == 0.0 else num2 / (num3 - num4)
                return self.mom1n / tc + num4
        if self.t_phase == PhaseEnum.Unload_t:
            if phase_unload in (PhaseEnum.Elastic,):
                return num3
            if phase_unload in (PhaseEnum.Plastic_c, PhaseEnum.Reload_c):
                tc = self.tangent_reload_c if num2 == 0.0 else num2 / (num3 - self._trot_pu)
                return self._trot_pu + self.mom1n / tc
        if self.t_phase == PhaseEnum.Unload_c:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload == PhaseEnum.Plastic_c:
                return self._trot_nu + self.mom1n / self.e1n
            if phase_unload == PhaseEnum.Reload_c:
                if self._tstrain > self._trot_lim_nu:
                    return self._trot_nu + self.mom1n / self.e1n
                else:
                    return self._trot_pu + self.mom1n / self.tangent_reload_c
        if self.t_phase == PhaseEnum.Reload_t:
            if phase_unload == PhaseEnum.Elastic:
                return num3
            if phase_unload == PhaseEnum.Plastic_c:
                num4 = self._cstrain - self._cstress / self.e1p
                tc = self.tangent_reload_c if num2 == 0.0 else num2 / (num3 - num4)
                return num4 + self.mom1n / tc
            if phase_unload == PhaseEnum.Reload_c:
                if self._t_phase_unload_t == PhaseEnum.Reload_t:
                    num4 = self._cstrain - self._cstress / self.e1p
                    tc = self.tangent_reload_c if num2 == 0.0 else num2 / (num3 - num4)
                    return num4 + self.mom1n / tc
                else:
                    return self._trot_pu + self.mom1n / self.tangent_reload_c
        if self.t_phase == PhaseEnum.Reload_c:
            if phase_unload in (PhaseEnum.Elastic, PhaseEnum.Reload_c):
                tc = self.tangent_reload_c
                num = self._trot_pu + self.mom1n / tc
                if self.e3n < 0.0:
                    val = (self._trot_pu * tc - self.rot3n * self.e3n) / (tc - self.e3n)
                    num = max(num, val)
                return num
        return num3

    # ===================================================================
    # Increment handlers
    # ===================================================================
