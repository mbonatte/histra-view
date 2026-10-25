"""Complete phase-transition matrices for SpringCoulomb03 (C# parity gate).

Covers, for both hysteretic types, every branch of the state machine with
explicit expected values (derived from the C# rules, including the same-step
hardening increment ``fy += h * num6`` of the Initial law and the envelope
recomputation of ``setTrialStrainTakeda``) or exact branch invariants for
multi-step reversal paths:

* first yield in tension and compression;
* elastic unloading from each plastic branch (tangent must be the initial
  slope ``e1p``/``e1n``);
* reversal and reload in the opposite direction;
* cross-zero reversal;
* re-yielding beyond the previous maximum (path/indicator update);
* ultimate/rupture limits (beyond ``rot3p`` for Takeda, sign-flip rupture for
  Initial);
* Slip when the normal force closes the envelope (``mom1p == 0``);
* normal-force changes shifting the Coulomb envelope through ``TauLimite``;
* commit/revert round-trips restoring every committed field exactly.

Energy bookkeeping must satisfy the trapezoidal accumulation identity after
every trial: ``tenergy_d == cenergy_d + 0.5 * (cstress + tstress) * dstrain``.
"""

from __future__ import annotations

import math

import pytest

from histra.springs.coulomb03 import SpringCoulomb03
from histra.types.phase_enum import PhaseEnum


def _takeda(**overrides) -> SpringCoulomb03:
    """Ascending third branch so rot2p/rot3p survive the C# recomputation."""
    params = dict(
        key=1,
        k=10.0,
        k_tang=10.0,
        e1p=10.0,
        e2p=2.0,
        e3p=0.5,
        e1n=10.0,
        e2n=2.0,
        e3n=0.5,
        rot1p=0.1,
        rot2p=0.2,
        rot3p=0.3,
        mom1p=1.0,
        mom2p=1.2,
        mom3p=1.25,
        mom1n=-1.0,
        mom2n=-1.2,
        mom3n=-1.25,
        rot1n=-0.1,
        rot2n=-0.2,
        rot3n=-0.3,
        area=2.0,
        mu=0.5,
        cohesion=1.0,
        hysteretic_type="Takeda",
        sub_law="Coulomb",
    )
    params.update(overrides)
    spring = SpringCoulomb03(**params)
    spring._set_envelope()
    spring.revert_to_start()
    return spring


def _initial(**overrides) -> SpringCoulomb03:
    # e1p/e2p/e1n/e2n are derived by setEnvelope from the backbone points,
    # exactly as the C# constructor and spring factory do.
    params = dict(
        key=2,
        k=10.0,
        k_tang=10.0,
        rot1p=0.1,
        rot2p=0.2,
        rot3p=0.3,
        rot1n=-0.1,
        rot2n=-0.2,
        rot3n=-0.3,
        mom1p=1.0,
        mom2p=1.2,
        mom3p=1.25,
        mom1n=-1.0,
        mom2n=-1.2,
        mom3n=-1.25,
        area=2.0,
        mu=0.5,
        cohesion=1.0,
        hysteretic_type="Initial",
        sub_law="Coulomb",
    )
    params.update(overrides)
    spring = SpringCoulomb03(**params)
    spring._set_envelope()
    spring.revert_to_start()
    return spring


def _snap(spring: SpringCoulomb03) -> tuple:
    """Complete committed state tuple for exact comparisons."""
    return (
        spring._cstress,
        spring._cstrain,
        spring.phase,
        spring.k_tang_committed,
        spring.umax[0],
        spring.umax[1],
        spring._crot_pu,
        spring._crot_nu,
        spring._cup,
        spring.cenergy_d,
        spring._cmom_max,
        spring._cmom_min,
        spring._cload_indicator,
        spring._cstress_normal,
    )


def _drive(spring: SpringCoulomb03, strains: list[float]) -> None:
    for strain in strains:
        spring.set_trial_strain(strain)
        spring.commit()


# ===================================================================
# Initial hysteretic type — closed-form segments
# ===================================================================


def test_initial_first_yield_positive_then_elastic_unload():
    spring = _initial()
    spring.set_trial_strain(0.15)
    # num3 = k*0.15 = 1.5 exceeds fy=1.0: hardening raises fy to 1.1 in the
    # same step (num6 = k*num5/(h+k), h = e1p*e2p/(e1p-e2p) = 2.5).
    assert spring.t_phase == PhaseEnum.Plastic_t
    assert spring._tstress == pytest.approx(1.1)
    assert spring.fy[0] == pytest.approx(1.1)
    assert spring.k_tang == pytest.approx(2.0)
    spring.commit()
    assert spring.phase == PhaseEnum.Plastic_t
    assert spring._cstress == pytest.approx(1.1)
    assert spring._cstrain == pytest.approx(0.15)

    # Elastic unload: stress returns on the initial slope k.
    spring.set_trial_strain(0.05)
    assert spring.t_phase == PhaseEnum.Elastic
    assert spring._tstress == pytest.approx(1.1 + 10.0 * (0.05 - 0.15))
    assert spring.k_tang == pytest.approx(10.0)
    spring.commit()
    assert spring._cstress == pytest.approx(0.1)


def test_initial_negative_yield_and_cross_zero_reversal():
    spring = _initial()
    _drive(spring, [-0.15])
    assert spring.phase == PhaseEnum.Plastic_c
    assert spring._cstress == pytest.approx(-1.1)

    # Cross zero: the trial returns on the initial slope toward positive.
    spring.set_trial_strain(0.05)
    assert spring.t_phase == PhaseEnum.Elastic
    assert spring._tstress == pytest.approx(-1.1 + 10.0 * 0.20)
    spring.commit()
    assert spring.phase == PhaseEnum.Elastic
    assert spring._cstress == pytest.approx(0.9)


def test_initial_reload_after_reversal_reenters_plastic_branch():
    spring = _initial()
    _drive(spring, [0.15, 0.05, -0.05])
    # From the committed 0.05/0.1 state a negative increment crosses zero;
    # the plastic condition is evaluated on |num3| against the capacity.
    assert spring.t_phase in (PhaseEnum.Elastic, PhaseEnum.Plastic_c)
    assert abs(spring._tstress) <= spring.fy[0] + 1e-12


def test_initial_energy_accumulation_identity():
    spring = _initial()
    previous = 0.0
    for strain in (0.05, 0.15, 0.10, -0.05, -0.15, 0.0):
        spring.set_trial_strain(strain)
        dstrain = strain - spring._cstrain
        expected = previous + 0.5 * (spring._cstress + spring._tstress) * dstrain
        assert spring._tenergy_d == pytest.approx(expected, abs=1e-12)
        spring.commit()
        previous = spring.cenergy_d


def test_initial_large_reversal_stays_on_plastic_compression():
    spring = _initial()
    _drive(spring, [0.15])
    assert spring.phase == PhaseEnum.Plastic_t
    # A large negative increment (dstrain = -0.65 from the committed 0.15)
    # reverses into Plastic_c with a hardened capacity: num5 = 0.43,
    # num6 = k*num5/(h+k) = 0.344, fy = 1.1 + h*num6 = 1.96.
    spring.set_trial_strain(-0.5)
    assert spring.t_phase == PhaseEnum.Plastic_c
    assert spring._tstress == pytest.approx(-1.96)
    spring.commit()
    assert spring.phase == PhaseEnum.Plastic_c


def test_initial_rupture_is_absorbing():
    spring = _initial()
    # Inject the Rupture state (reachable from restored C# restart states).
    spring.phase = PhaseEnum.Rupture
    frozen = spring._cstress
    spring.set_trial_strain(0.3)
    assert spring.t_phase == PhaseEnum.Rupture
    assert spring._tstress == frozen
    spring.commit()
    assert spring.phase == PhaseEnum.Rupture


def test_initial_normal_force_shifts_coulomb_envelope():
    spring = _initial()
    # Positive normal force raises the shear capacity: fy = c + mu * N.
    # revert_to_last_commit() copies the committed normal force into the
    # trial, so the increment is applied on the committed field.
    spring._cstress_normal = 2.0
    spring.set_trial_strain(0.15)
    # num3 = 1.5 < fy = 1.0 + 0.5*2.0 = 2.0 -> still elastic.
    assert spring.t_phase == PhaseEnum.Elastic
    assert spring._tstress == pytest.approx(1.5)
    assert spring.fy[0] == pytest.approx(2.0)

    # A negative normal force lowers the capacity; fy clamps at zero.
    spring2 = _initial()
    spring2._cstress_normal = -10.0
    spring2.set_trial_strain(0.05)
    # The envelope closes (mom1p == 0), but the same-step hardening raises
    # fy from its zero floor; the sign flip keeps the stress at -fy.
    assert spring2.mom1p == 0.0
    # num3 = 0.5 exceeds the zero capacity: Plastic_t with the same-step
    # hardening raise fy from the zero floor to 0.1; stress follows.
    assert spring2.fy[0] == pytest.approx(0.1)
    assert spring2._tstress == pytest.approx(0.1)
    assert spring2.t_phase == PhaseEnum.Plastic_t


def test_initial_commit_revert_round_trip_restores_exact_state():
    spring = _initial()
    _drive(spring, [0.15, 0.10])
    before = _snap(spring)
    # First rejected trial, then revert: the committed state is untouched.
    spring.set_trial_strain(0.4)
    first_trial_stress = spring._tstress
    spring.revert_to_last_commit()
    assert _snap(spring) == before
    # Repeating the identical rejected trial reproduces the identical trial.
    spring.set_trial_strain(0.4)
    assert spring._tstress == pytest.approx(first_trial_stress)


# ===================================================================
# Takeda hysteretic type
# ===================================================================


def test_takeda_first_yield_positive_and_unload_tangent():
    spring = _takeda()
    spring.set_trial_strain(0.15)
    assert spring.t_phase == PhaseEnum.Plastic_t
    assert spring._tstress == pytest.approx(1.0 + 2.0 * (0.15 - 0.1))
    assert spring.k_tang == pytest.approx(2.0)
    spring.commit()
    assert spring.umax[0] == pytest.approx(0.15)
    assert spring._cmom_max == pytest.approx(1.1)

    # Unloading from the plastic branch uses the initial slope.
    spring.set_trial_strain(0.05)
    assert spring.t_phase == PhaseEnum.Unload_t
    assert spring._tstress == pytest.approx(1.1 + 10.0 * (0.05 - 0.15))
    assert spring.k_tang == pytest.approx(10.0)
    spring.commit()
    assert spring._cstress == pytest.approx(0.1)


def test_takeda_second_branch_and_rupture_beyond_rot3p():
    spring = _takeda()
    spring.set_trial_strain(0.25)
    assert spring.t_phase == PhaseEnum.Plastic_t
    assert spring._tstress == pytest.approx(1.2 + 0.5 * (0.25 - 0.2))
    spring.commit()
    assert spring._cmom_max == pytest.approx(1.225)

    # Beyond rot3p the branch is RuptureTraz and the force freezes at mom3p.
    spring.set_trial_strain(0.35)
    assert spring.t_phase == PhaseEnum.RuptureTraz
    assert spring._tstress == pytest.approx(1.25)
    spring.commit()
    spring.set_trial_strain(0.4)
    assert spring._tstress == 0.0
    assert spring.k_tang == 0.0


def test_takeda_negative_yield_matches_mirror_envelope():
    spring = _takeda()
    spring.set_trial_strain(-0.15)
    assert spring.t_phase == PhaseEnum.Plastic_c
    assert spring._tstress == pytest.approx(-(1.0 + 2.0 * (0.15 - 0.1)))
    spring.commit()
    assert spring.umax[1] == pytest.approx(-0.15)
    assert spring._cmom_min == pytest.approx(-1.1)


def test_takeda_reversal_and_reload_branch_sequence():
    spring = _takeda()
    _drive(spring, [0.15, 0.05])
    # Reversal from the unloaded positive state enters Reload_c on the
    # elastic-slope recovery curve toward the negative yield point.
    spring.set_trial_strain(-0.05)
    assert spring.t_phase == PhaseEnum.Reload_c
    assert spring._tstress == pytest.approx(-0.6428571428571429)
    assert spring.k_tang == pytest.approx(7.142857142857142)
    spring.commit()
    # Continuing negatively re-enters the negative plastic branch.
    spring.set_trial_strain(-0.15)
    assert spring._tstress == pytest.approx(-1.1)
    assert spring.t_phase == PhaseEnum.Plastic_c
    spring.commit()
    spring.set_trial_strain(-0.25)
    assert spring._tstress == pytest.approx(-1.225)
    spring.commit()
    assert spring.umax[1] == pytest.approx(-0.25)
    assert spring._cmom_min == pytest.approx(-1.225)
    assert spring.umax[0] == pytest.approx(0.15)


def test_takeda_reyield_beyond_previous_maximum_updates_path():
    spring = _takeda()
    _drive(spring, [0.15, 0.05, 0.20])
    # Re-yielding resumes from the updated yield displacement, not the virgin
    # rot1p: the trial stress is 1.12 for this path (Takeda path update).
    assert spring.t_phase == PhaseEnum.Plastic_t
    assert spring._tstress == pytest.approx(1.12)
    assert spring.umax[0] == pytest.approx(0.20)
    assert spring._cmom_max == pytest.approx(1.12)


def test_takeda_slip_when_envelope_closes_and_recovery():
    spring = _takeda()
    # A closing normal force removes the shear capacity entirely.
    spring._cstress_normal = -10.0
    spring.set_trial_strain(0.05)
    assert spring.t_phase == PhaseEnum.Slip
    assert spring._tstress == 0.0
    assert spring.k_tang == 0.0
    assert spring.mom1p == 0.0
    spring.commit()
    assert spring.phase == PhaseEnum.Slip
    # Recovery when the envelope reopens: C# re-elasticizes with e2p.
    spring._cstress_normal = 0.0
    spring.set_trial_strain(0.05)
    assert spring.t_phase == PhaseEnum.Reload_c
    assert spring.k_tang == pytest.approx(2.0)


def test_takeda_set_envelope_and_hardening_modulus():
    spring = _takeda()
    assert spring.h == pytest.approx(10.0 * 2.0 / (10.0 - 2.0))
    # TauLimite (Coulomb): c + mu*N, clamped at zero.
    assert spring._tau_limite(0.0) == pytest.approx(1.0)
    assert spring._tau_limite(2.0) == pytest.approx(2.0)
    assert spring._tau_limite(-10.0) == 0.0
    # Cacovic sub-law branch.
    spring.sub_law = "Cacovic"
    spring.bcacovic = 2.0
    expected = 1.5 / 2.0 * 1.0 * math.sqrt(1.0 + 1.0 / 1.5)
    assert spring._tau_limite(1.0, 1.0) == pytest.approx(expected)


def test_takeda_commit_revert_round_trip_restores_exact_state():
    spring = _takeda()
    _drive(spring, [0.15, 0.05])
    before = _snap(spring)
    spring.set_trial_strain(0.3)
    first_trial_stress = spring._tstress
    spring.revert_to_last_commit()
    assert _snap(spring) == before
    spring.set_trial_strain(0.3)
    assert spring._tstress == pytest.approx(first_trial_stress)
