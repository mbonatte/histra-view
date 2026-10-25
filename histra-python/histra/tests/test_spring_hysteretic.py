"""Smoke test for SpringHysteretic.

Per the task specification:
1. Load model-output/model.hrx
2. Find a SpringHysteretic instance
3. Call revert_to_start
4. Test an elastic trial strain (within elastic range)
"""

import os
import sys
import math
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import xml.etree.ElementTree as ET
from histra.model.spring import (
    Spring, SpringHysteretic, _SPRING_REGISTRY,
    PhaseEnum, HystereticTensileCurveTypeEnum, HystereticCompressiveCurveTypeEnum,
)


MODEL_PATH = str(Path(__file__).resolve().parents[1] / "model-output" / "model.hrx")


def parse_spring_hysteretic_from_hrx() -> SpringHysteretic:
    """Parse the first ``SpringHysteretic`` element from the HRX file."""
    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(f"Cannot find {MODEL_PATH}")

    context_iter = ET.iterparse(MODEL_PATH, events=("end",))
    for event, elem in context_iter:
        if elem.tag == "Spring" and elem.get("TypeOf") == "HiStrA.Objects.SpringHysteretic":
            spring = Spring.from_xml(elem)
            assert isinstance(spring, SpringHysteretic), (
                f"Expected SpringHysteretic, got {type(spring).__name__}"
            )
            # Clear element to free memory (large file)
            elem.clear()
            return spring
        elem.clear()
    raise RuntimeError("No SpringHysteretic element found in the HRX file.")


# ===================================================================
# Tests
# ===================================================================

def test_revert_to_start():
    """Call revert_to_start on a fresh XML-loaded spring — state must be zero."""
    s = parse_spring_hysteretic_from_hrx()
    assert s.is_on, "Spring should be on after XML load"
    s.revert_to_start()
    assert s._tstress == 0.0, f"_tstress should be 0, got {s._tstress}"
    assert s._tstrain == 0.0, f"_tstrain should be 0, got {s._tstrain}"
    assert s._cstress == 0.0, f"_cstress should be 0, got {s._cstress}"
    assert s._cstrain == 0.0, f"_cstrain should be 0, got {s._cstrain}"
    assert s.f == 0.0, f"f should be 0, got {s.f}"
    assert s.u == 0.0, f"u should be 0, got {s.u}"
    assert s.umax[0] == 0.0 and s.umax[1] == 0.0, "umax should be [0,0]"
    assert s.phase == PhaseEnum.Elastic, f"phase should be Elastic, got {s.phase}"
    assert s.t_phase == PhaseEnum.Elastic, f"t_phase should be Elastic, got {s.t_phase}"
    print("  [PASS] revert_to_start — all state zero")


def test_elastic_trial_strain():
    """Apply a very small strain (within elastic range) — stress should be K * strain."""
    s = parse_spring_hysteretic_from_hrx()
    s.revert_to_start()

    k = s.k
    assert k > 0.0, f"Spring stiffness K must be positive, got {k}"

    # Small strain well within the elastic limit
    test_strain = 0.00001

    s.set_trial_strain(test_strain)

    expected_stress = k * test_strain
    actual_stress = s._tstress
    err = abs(actual_stress - expected_stress)

    print(f"  K={k:.6f}, strain={test_strain:.8f}")
    print(f"  expected stress={expected_stress:.8f}, got={actual_stress:.8f}, err={err:.8e}")

    # Allow small tolerance for floating-point
    assert err < 1e-6 * max(1.0, abs(expected_stress)), (
        f"Trial stress mismatch: expected {expected_stress:.8f}, got {actual_stress:.8f}"
    )
    print("  [PASS] elastic trial strain — stress matches K * strain")


def test_commit_revert_cycle():
    """Commit trial state, then revert — state consistency."""
    s = parse_spring_hysteretic_from_hrx()
    s.revert_to_start()

    test_strain = 0.00001
    s.set_trial_strain(test_strain)
    assert s._tstress != 0.0, "Trial stress should be non-zero after loading"

    # Commit
    s.commit()
    assert s._cstress == s._tstress, "Committed stress should equal trial stress after commit"
    assert s._cstrain == s._tstrain, "Committed strain should equal trial strain after commit"
    assert s.f == s._cstress, "Spring force should equal committed stress"
    assert s.u == s._tstrain, "Spring displacement should equal trial strain"
    print("  [PASS] commit — state copied correctly")

    # Revert to last commit
    s.set_trial_strain(0.0)
    stress_before = s._tstress
    strain_before = s._tstrain
    s.revert_to_last_commit()
    assert s._tstress == s._cstress, (
        f"After revert, trial stress ({s._tstress}) should equal committed ({s._cstress})"
    )
    assert s._tstrain == s._cstrain, (
        f"After revert, trial strain ({s._tstrain}) should equal committed ({s._cstrain})"
    )
    assert s.t_phase == s.phase, "Trial phase should equal committed phase after revert"
    print("  [PASS] revert_to_last_commit — trial restored to committed")


def test_get_force_incr_displacement():
    """Getters return expected values."""
    s = parse_spring_hysteretic_from_hrx()
    s.revert_to_start()
    s.set_trial_strain(0.0005)
    force = s.get_force()
    incr = s.get_incr_force()
    disp = s.get_displacement()
    assert force == s._tstress, f"get_force()={force} != _tstress={s._tstress}"
    assert incr == s._tstress - s._cstress, "get_incr_force mismatch"
    assert disp == s._tstrain, f"get_displacement()={disp} != _tstrain={s._tstrain}"
    print(f"  [PASS] get_force={force:.6f}, get_incr_force={incr:.6f}, get_displacement={disp:.8f}")


def test_multiple_steps():
    """Two sequential trial steps — basic hysteretic path test."""
    s = parse_spring_hysteretic_from_hrx()
    s.revert_to_start()

    # Step 1: load in tension
    s.set_trial_strain(0.0005)
    f1 = s._tstress
    s.commit()
    print(f"  Step 1 (tension): strain=0.0005, stress={f1:.8f}")

    # Step 2: unload to zero strain
    s.set_trial_strain(0.0)
    f2 = s._tstress
    print(f"  Step 2 (unload):  strain=0.0000, stress={f2:.8f}")
    # After unloading from positive stress, stress may not be exactly 0
    # but should be between 0 and f1

    # Step 3: small compression
    s.set_trial_strain(-0.00001)
    f3 = s._tstress
    print(f"  Step 3 (comp):    strain=-0.00001, stress={f3:.8f}")

    # At least check no NaN/Inf
    for i, val in enumerate([f1, f2, f3]):
        assert math.isfinite(val), f"Step {i+1} stress is not finite: {val}"
    print("  [PASS] multiple steps — all stresses finite")


def test_envelope_stress_functions():
    """Direct call to envelope stress/tangent helpers."""
    s = parse_spring_hysteretic_from_hrx()
    s.revert_to_start()

    # Positive envelope at small strain
    eps = 0.00001
    stress = s._pos_envlp_stress(eps)
    tangent = s._pos_envlp_tangent(eps)
    print(f"  posEnvlp(strain={eps:.8f}) = {stress:.8f}, tangent = {tangent:.8f}")

    # Negative envelope at small strain
    stress_n = s._neg_envlp_stress(-eps)
    tangent_n = s._neg_envlp_tangent(-eps)
    print(f"  negEnvlp(strain={-eps:.8f}) = {stress_n:.8f}, tangent = {tangent_n:.8f}")

    assert math.isfinite(stress), "pos envelope stress not finite"
    assert math.isfinite(tangent), "pos envelope tangent not finite"
    assert math.isfinite(stress_n), "neg envelope stress not finite"
    assert math.isfinite(tangent_n), "neg envelope tangent not finite"
    print("  [PASS] envelope functions — all finite")


def test_initialize_from_xml_fields():
    """Verify XML-loaded fields are populated correctly."""
    s = parse_spring_hysteretic_from_hrx()
    # These should be populated from XML
    assert s.k > 0.0, f"K should be positive from XML, got {s.k}"
    assert s.rot1p > 0.0, f"rot1p should be > 0 from XML, got {s.rot1p}"
    assert s.rot1n < 0.0, f"rot1n should be < 0 from XML, got {s.rot1n}"
    assert s.mom1p != 0.0 or s.mom1n != 0.0, "At least one backbone point should be non-zero"
    assert s.tensile_curve_type in ("Elastic", "LinearHardening", "LinearSoftening", "Exponential")
    assert s.compressive_curve_type in ("Elastic", "LinearHardening", "LinearSoftening", "Parabolic")
    print(f"  K={s.k:.6f}, rot1p={s.rot1p:.8f}, rot1n={s.rot1n:.8f}")
    print(f"  tensile_curve_type={s.tensile_curve_type}, compressive_curve_type={s.compressive_curve_type}")
    print("  [PASS] XML fields — populated correctly")


def test_is_on_flag():
    """is_on=False should make set_trial_strain a no-op."""
    s = parse_spring_hysteretic_from_hrx()
    s.revert_to_start()
    s.is_on = False
    s.set_trial_strain(0.001)
    assert s._tstrain == 0.0, "Trial strain should not change when is_on=False"
    assert s._tstress == 0.0, "Trial stress should not change when is_on=False"
    s.is_on = True
    print("  [PASS] is_on flag — respected")


# ===================================================================
# Main
# ===================================================================

if __name__ == "__main__":
    tests = [
        ("XML fields", test_initialize_from_xml_fields),
        ("revert_to_start", test_revert_to_start),
        ("elastic trial strain", test_elastic_trial_strain),
        ("commit/revert cycle", test_commit_revert_cycle),
        ("getters", test_get_force_incr_displacement),
        ("envelope functions", test_envelope_stress_functions),
        ("multi-step path", test_multiple_steps),
        ("is_on flag", test_is_on_flag),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n--- Test: {name} ---")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)}")
    if failed:
        sys.exit(1)
    print("ALL TESTS PASSED")
