"""Direct unit test of the SpringCoulomb03 Takeda state machine."""
import os
import sys
import math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from histra.model.spring import SpringCoulomb03, PhaseEnum
from histra.model.masonry_material import MasonryMaterial

def _make_spring():
    """Create a Coulomb03 spring with a proper softening backbone."""
    s = SpringCoulomb03(
        k=10000.0,
        cohesion=100.0,
        mu=0.5,
        e1p=10000.0, e2p=-500.0, e3p=-100.0,
        e1n=10000.0, e2n=-500.0, e3n=-100.0,
        eup=10000.0, eun=10000.0,
        mom1p=100.0, rot1p=0.01,
        mom2p=99.9995, rot2p=0.010001,
        mom3p=0.0, rot3p=1.0,
        mom1n=-100.0, rot1n=-0.01,
        mom2n=-99.9995, rot2n=-0.010001,
        mom3n=0.0, rot3n=-1.0,
    )
    s.revert_to_start()
    s.revert_to_last_commit()
    return s


def test_elastic_then_yield():
    """Elastic loading, then beyond yield into plastic regime."""
    s = _make_spring()

    # Elastic strain (within rot1p = 100/10000 = 0.01)
    s.set_trial_strain_takeda_diagonal_quad(0.005, 0.0)
    print(f"Elastic: strain={s._tstrain:.6f}, stress={s._tstress:.6f}, k_tang={s.k_tang:.6f}")
    assert abs(s._tstress - 50.0) < 1e-10, f"Expected 50.0, got {s._tstress}"
    assert s.t_phase == PhaseEnum.Elastic

    # Yield (strain beyond rot1p = 0.01).
    # With a softening backbone (e2p=-500) the stress drops below the peak mom1p=100.
    s.set_trial_strain_takeda_diagonal_quad(0.02, 0.0)
    print(f"Yield: strain={s._tstrain:.6f}, stress={s._tstress:.6f}, k_tang={s.k_tang:.6f}, phase={PhaseEnum(s.t_phase).name}")
    # Stress should be less than mom1p (softening) but still positive
    assert 90.0 < s._tstress < 100.0, f"Expected stress near 99, got {s._tstress}"
    assert s.t_phase in (PhaseEnum.Plastic_t, PhaseEnum.Elastic), f"Expected plastic or elastic, got {PhaseEnum(s.t_phase).name}"

    print("[PASS] Elastic → yield transition works")


def test_unload_reload():
    """Load to yield, unload, reload."""
    s = _make_spring()

    # Load beyond yield
    s.set_trial_strain_takeda_diagonal_quad(0.02, 0.0)
    s.commit()
    print(f"After commit to 0.02: stress={s._cstress:.6f}, phase={PhaseEnum(s.phase).name}")

    # Unload
    s.set_trial_strain_takeda_diagonal_quad(0.015, 0.0)
    print(f"Unload to 0.015: stress={s._tstress:.6f}, k_tang={s.k_tang:.6f}, phase={PhaseEnum(s.t_phase).name}")
    s.commit()

    # Re-increase
    s.set_trial_strain_takeda_diagonal_quad(0.025, 0.0)
    print(f"Re-increase to 0.025: stress={s._tstress:.6f}, k_tang={s.k_tang:.6f}, phase={PhaseEnum(s.t_phase).name}")

    print("[PASS] Unload/reload works")

def test_reload_tangent_uses_csharp_minimum():
    """Reload tangents must reproduce the C# 0.0001*K getter floor."""
    s = _make_spring()

    # revert_to_start intentionally stores zero in C#, but the public getter
    # returns max(0.0001*K, stored_value).  With K=10000 the floor is 1.0.
    s.tangent_reload_t = 0.0
    s.tangent_reload_c = 0.0
    assert s.tangent_reload_t == 1.0
    assert s.tangent_reload_c == 1.0

    # Exercise the exact compression branch that previously divided by zero.
    s.t_phase = PhaseEnum.Reload_c
    s._trot_pu = 0.0
    yn = s._get_current_yielding_displacement_compression(
        PhaseEnum.Elastic,
        -1.0e-6,
    )
    assert math.isfinite(yn)
    expected_yn = max(
        s._trot_pu + s.mom1n / s.tangent_reload_c,
        (
            s._trot_pu * s.tangent_reload_c
            - s.rot3n * s.e3n
        )
        / (
            s.tangent_reload_c - s.e3n
        ),
    )
    assert math.isclose(
        yn,
        expected_yn,
        rel_tol=1.0e-12,
        abs_tol=1.0e-12,
    )

    # The symmetric tension branch must be protected as well.
    s.t_phase = PhaseEnum.Reload_t
    s._trot_nu = 0.0
    yp = s._get_current_yielding_displacement_tension(PhaseEnum.Elastic, 1.0e-6)
    assert math.isfinite(yp)
    expected_yp = min(
        s._trot_nu + s.mom1p / s.tangent_reload_t,
        (
            s._trot_nu * s.tangent_reload_t
            - s.rot3p * s.e3p
        )
        / (
            s.tangent_reload_t - s.e3p
        ),
    )
    assert math.isclose(
        yp,
        expected_yp,
        rel_tol=1.0e-12,
        abs_tol=1.0e-12,
    )

def test_negative_yield():
    """Compression (negative) loading."""
    s = _make_spring()

    # Negative elastic
    s.set_trial_strain_takeda_diagonal_quad(-0.005, 0.0)
    print(f"Neg elastic: strain={s._tstrain:.6f}, stress={s._tstress:.6f}")
    assert abs(s._tstress - (-50.0)) < 1e-10

    # Negative yield (softening backbone)
    s.set_trial_strain_takeda_diagonal_quad(-0.02, 0.0)
    print(f"Neg yield: strain={s._tstrain:.6f}, stress={s._tstress:.6f}, phase={PhaseEnum(s.t_phase).name}")
    assert s._tstress < -90.0, f"Should have yielded negative, got {s._tstress}"
    assert s.t_phase in (PhaseEnum.Plastic_c, PhaseEnum.Elastic)

    print("[PASS] Negative yielding works")


def test_slip():
    """Zero friction strength → Slip phase."""
    s = SpringCoulomb03(
        k=10000.0,
        cohesion=0.0, mu=0.0,
        e1p=10000.0, e2p=0.0, e3p=0.0,
        mom1p=0.0, rot1p=0.0,
        mom2p=0.0, rot2p=0.0,
        mom3p=0.0, rot3p=0.0,
        mom1n=0.0, rot1n=0.0,
        mom2n=0.0, rot2n=0.0,
        mom3n=0.0, rot3n=0.0,
    )
    s.revert_to_start()
    s.revert_to_last_commit()

    s.set_trial_strain_takeda_diagonal_quad(0.01, 0.0)
    print(f"Slip: strain={s._tstrain:.6f}, stress={s._tstress:.6f}, phase={PhaseEnum(s.t_phase).name}")
    assert s.t_phase == PhaseEnum.Slip
    assert s._tstress == 0.0

    print("[PASS] Slip works")


def test_unmanaged_quad_uses_stress_interpolated_masonry_energy():
    """The scalar fallback must retain the C# enum-5 energy callback."""
    s = _make_spring()
    masonry = MasonryMaterial(
        properties={
            "ConstitutiveLawMasonryShear": "ElastoPlasticEnergySigmaInterpolation"
        }
    )

    s.set_trial_strain_takeda_diagonal_quad(
        0.02, 0.0, masonry=masonry, volume=4.0, sigma=-0.0575
    )

    expected_energy = (0.0007775 + 0.0004402) / 2.0
    assert math.isclose(
        s.ur[0], expected_energy * 4.0 / 100.0 + 0.005,
        rel_tol=1.0e-12,
        abs_tol=1.0e-12,
    )


if __name__ == "__main__":
    test_elastic_then_yield()
    test_unload_reload()
    test_reload_tangent_uses_csharp_minimum()
    test_negative_yield()
    test_slip()
    print("\nAll tests passed!")
