"""Offline exact-output regressions for the production Coulomb spring.

The five normal-coupling cases were independently checked against the original
installed C# assembly on 2026-10-17. Other embedded expectations are regression
contracts pending a committed independent capture driver; see the source audit.
No original assembly is executed by this test module.
"""
import numpy as np
import pytest

from histra.springs.coulomb03 import SpringCoulomb03
from histra.types.phase_enum import PhaseEnum


def _init_coulomb_spring(
    k: float,
    cohesion: float,
    mu: float,
    ur: float = 0.05,
    normal_force: float = 0.0,
    ktang: float = 0.0,
    plastic_strain_ratio: float = 0.0,
) -> SpringCoulomb03:
    """Helper initializing SpringCoulomb03 with identical initial envelope to C#."""
    s = SpringCoulomb03(k=k, cohesion=cohesion, mu=mu, ur=ur, sub_law="Coulomb")
    mom1p = max(1e-9, cohesion + mu * 0.0)
    rot1p = mom1p / k
    s.mom1p = mom1p
    s.rot1p = rot1p
    s.mom2p = mom1p + ktang * (max(plastic_strain_ratio, rot1p * 1.0001) - rot1p)
    s.rot2p = max(plastic_strain_ratio, rot1p * 1.0001)
    s.mom3p = 0.0
    s.rot3p = max(ur, s.rot2p * 1.0001)
    s.mom1n = -mom1p
    s.rot1n = -rot1p
    s.mom2n = -s.mom2p
    s.rot2n = -s.rot2p
    s.mom3n = 0.0
    s.rot3n = -s.rot3p
    s._set_envelope()
    s.revert_to_start()
    s.revert_to_last_commit()
    if normal_force != 0.0:
        s._cstress_normal = normal_force
        s._tstress_normal = normal_force
    return s


@pytest.mark.parametrize(
    ("cohesion", "mu", "normal_force", "expected_force_bits"),
    [
        (10.0, 0.5, 0.0, [4617315517961601024, 4621819117588971520, 4621115553295575901]),
        (10.0, 0.5, 10.0, [4620130267728707584, 4624633867356078080, 4623578520915984651]),
        (25.0, 0.6, 20.0, [4625900504751276032, 4630404104378646528, 4625901025532061026]),
        (5.0, 0.35, 50.0, [4622522805030748160, 4627026404658118656, 4626674627397338283]),
        (15.0, 0.0, 100.0, [4620130267728707584, 4624633867356078080, 4622824669722295329]),
    ],
)
def test_csharp_coulomb_normal_coupling_and_yield_envelope(
    cohesion: float,
    mu: float,
    normal_force: float,
    expected_force_bits: list[int],
):
    """Verify Mohr-Coulomb normal coupling TauLimite = c + mu * N between C# and Python."""
    k = 1000.0
    ur = 0.05
    expected_yield = cohesion + mu * normal_force

    # 1. Python envelope limit matches analytical Mohr-Coulomb
    s_py = SpringCoulomb03(k=k, cohesion=cohesion, mu=mu, sub_law="Coulomb")
    tau_lim_py = s_py._tau_limite(normal_force)
    assert abs(tau_lim_py - expected_yield) < 1e-12

    # 2. Setup spring and test strains across yield
    strain_pre = (expected_yield * 0.5) / k
    strain_yield = expected_yield / k
    strain_post = (expected_yield * 1.5) / k
    strains = [strain_pre, strain_yield, strain_post]

    s = _init_coulomb_spring(k=k, cohesion=cohesion, mu=mu, ur=ur, normal_force=normal_force)

    py_bits = []
    for st in strains:
        s.set_trial_strain(st)
        f = s.get_force()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    # Exact bit-for-bit parity with C# HiStrA SpringCoulomb03
    assert py_bits == expected_force_bits


def test_csharp_coulomb_elastic_shear_bitwise():
    """Check the analytical elastic shear response at exact stored bits."""
    k = 2500.0
    strains = [0.0001, 0.0004, 0.0008, 0.0012]
    expected_force_bits = [4598175219545276416, 4607182418800017408, 4611686018427387904, 4613937818241073151]

    s = _init_coulomb_spring(k=k, cohesion=100.0, mu=0.5, ur=0.05)

    py_bits = []
    for strain in strains:
        s.set_trial_strain(strain)
        f = s.get_force()
        s.commit()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    assert py_bits == expected_force_bits


def test_csharp_coulomb_state_transitions():
    """Verify phase transitions: Elastic -> Plastic_t -> Reload_c."""
    k = 1000.0
    strains = [0.0005, 0.002, 0.001]
    expected_t_phases = [int(PhaseEnum.Elastic), int(PhaseEnum.Plastic_t), int(PhaseEnum.Reload_c)]
    expected_force_bits = [4602678819172646912, 4606998616413995895, -4646396143832211573]

    s = _init_coulomb_spring(k=k, cohesion=1.0, mu=0.5, ur=0.05)

    py_t_phases = []
    py_bits = []
    for strain in strains:
        s.set_trial_strain(strain)
        py_t_phases.append(int(s.t_phase))
        f = s.get_force()
        s.commit()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    assert py_t_phases == expected_t_phases
    assert py_bits == expected_force_bits
