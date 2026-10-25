"""Offline exact-output regressions for the production hysteretic spring.

Hardening and pinching cases were independently checked against the installed
original C# assembly on 2026-10-17. Elastic values are analytical regression
expectations. The separate masonry-backbone fixture provides a reproducible
native driver and compiled-history checks; this module does not run C#.
"""
import numpy as np
import pytest

from histra.springs.hysteretic import SpringHysteretic


def test_csharp_hysteretic_elastic_regime_bitwise():
    """Check exact analytical force values in the reversible elastic regime."""
    k = 2500.0
    strains = [0.0002, 0.0006, 0.001, -0.0004, -0.0008]
    expected_force_bits = [4602678819172646912, 4609434218613702655, 4612811918334230528, -4616189618054758400, -4611686018427387904]

    py_spring = SpringHysteretic(
        k=k,
        e1p=k,
        e1n=k,
        tensile_curve_type="Elastic",
        compressive_curve_type="Elastic",
    )

    for i, s in enumerate(strains):
        py_spring.set_trial_strain(s)
        py_f = py_spring.get_force()
        py_spring.commit()

        # Bitwise IEEE-754 representation matching against C# SpringHysteretic
        py_bits = int(np.asarray([py_f], dtype=np.float64).view(np.int64)[0])
        assert py_bits == expected_force_bits[i], f"Elastic hysteretic bit mismatch at strain {s}: py={py_bits}, cs={expected_force_bits[i]}"


def test_csharp_hysteretic_linear_hardening_and_unloading():
    """Verify post-yield linear hardening branch and unloading stiffness against C# outputs."""
    k = 1000.0
    kt_1 = 100.0
    kt_2 = 50.0
    fy_1 = 10.0
    fy_2 = -10.0
    ur_1 = 0.05
    ur_2 = -0.05

    strains = [0.005, 0.015, -0.005]
    expected_force_bits = [4617315517961601024, 4622100592565682176, -4606056518893174784]

    py_spring = SpringHysteretic(
        k=k,
        tensile_curve_type="LinearHardening",
        compressive_curve_type="LinearHardening",
        mom1p=fy_1, rot1p=fy_1 / k,
        mom2p=fy_1 + kt_1 * (ur_1 - fy_1 / k), rot2p=ur_1,
        mom3p=0.0, rot3p=ur_1 * 1.0001,
        mom1n=fy_2, rot1n=fy_2 / k,
        mom2n=fy_2 + kt_2 * (ur_2 - fy_2 / k), rot2n=ur_2,
        mom3n=0.0, rot3n=ur_2 * 1.0001,
    )
    py_spring._set_envelope()
    py_spring.revert_to_start()
    py_spring.revert_to_last_commit()

    py_bits = []
    for s in strains:
        py_spring.set_trial_strain(s)
        f = py_spring.get_force()
        py_spring.commit()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    assert py_bits == expected_force_bits


def test_csharp_hysteretic_pinching_parameters():
    """Verify execution of full 24-parameter pinching model against authoritative C# outputs."""
    m1p, r1p = 10.0, 0.01
    m2p, r2p = 15.0, 0.03
    m3p, r3p = 5.0, 0.05
    m1n, r1n = -10.0, -0.01
    m2n, r2n = -15.0, -0.03
    m3n, r3n = -5.0, -0.05
    pinchXp, pinchYp = 0.5, 0.25
    pinchXn, pinchYn = 0.5, 0.25
    d1p = d2p = d1n = d2n = betap = betan = 0.0

    strains = [0.005, 0.02, 0.01, -0.01, -0.02]
    expected_force_bits = [4617315517961601024, 4623226492472524800, 4612811918334230528, -4601552919265804288, -4600145544382251008]

    py_spring = SpringHysteretic(
        k=m1p / r1p,
        tensile_curve_type="LinearHardening",
        compressive_curve_type="LinearHardening",
        pinch_xp=pinchXp, pinch_yp=pinchYp,
        pinch_xn=pinchXn, pinch_yn=pinchYn,
        damfc1p=d1p, damfc2p=d2p, damfc1n=d1n, damfc2n=d2n,
        betap=betap, betan=betan,
        mom1p=m1p, rot1p=r1p, mom2p=m2p, rot2p=r2p, mom3p=m3p, rot3p=r3p,
        mom1n=m1n, rot1n=r1n, mom2n=m2n, rot2n=r2n, mom3n=m3n, rot3n=r3n,
    )
    py_spring._set_envelope()
    py_spring.revert_to_start()
    py_spring.revert_to_last_commit()

    py_bits = []
    for s in strains:
        py_spring.set_trial_strain(s)
        f = py_spring.get_force()
        py_spring.commit()
        py_bits.append(int(np.asarray([f], dtype=np.float64).view(np.int64)[0]))

    assert py_bits == expected_force_bits
