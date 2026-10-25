"""Test programmatic creation of SpringHysteretic via initialize()."""
import os
import sys
import math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from histra.model.spring import SpringHysteretic, PhaseEnum

# Create a spring programmatically (as C# constructor does)
s = SpringHysteretic(
    k=10000.0,
    fy=[100.0, -150.0],       # Fy1, Fy2
    kt=[500.0, 600.0],         # Kt1, Kt2
    ur=[0.05, -0.08],          # Ur1, Ur2
    alfau=[0.5, 0.5],          # AlfaU1, AlfaU2
    alfar=[0.8, 0.8],          # AlfaR1, AlfaR2
    tensile_curve_type="LinearHardening",
    compressive_curve_type="LinearHardening",
)

print("Before initialize():")
print(f"  mom1p={s.mom1p}, rot1p={s.rot1p}")
print(f"  mom1n={s.mom1n}, rot1n={s.rot1n}")

s.initialize()

print("After initialize():")
print(f"  mom1p={s.mom1p}, rot1p={s.rot1p}")
print(f"  mom2p={s.mom2p}, rot2p={s.rot2p}")
print(f"  e1p={s.e1p}, e2p={s.e2p}")
print(f"  mom1n={s.mom1n}, rot1n={s.rot1n}")
print(f"  mom2n={s.mom2n}, rot2n={s.rot2n}")
print(f"  e1n={s.e1n}, e2n={s.e2n}")
print(f"  energy_a={s.energy_a}")

# Check elastic limit
k = s.k
assert s.rot1p == s.fy[0] / k, f"rot1p should be Fy1/K, got {s.rot1p}"
assert s.rot1n == s.fy[1] / k, f"rot1n should be Fy2/K, got {s.rot1n}"

# Check state after initialize
assert s._tstress == 0.0
assert s._tstrain == 0.0
assert s.phase == PhaseEnum.Elastic
assert s.k_tang == s.e1p

# Elastic trial
s.set_trial_strain(0.005)  # within elastic (0.005 < 0.01)
expected = k * 0.005
err = abs(s._tstress - expected)
print(f"\nElastic trial: strain=0.005, stress={s._tstress:.6f}, expected={expected:.6f}, err={err:.6e}")
assert err < 1e-10, f"Elastic stress mismatch: {err}"

# Beyond yield
s.set_trial_strain(0.02)  # > rot1p=0.01
print(f"Beyond yield: strain=0.02, stress={s._tstress:.6f}, k_tang={s.k_tang:.6f}")
assert s._tstress > s.mom1p, "Should have yielded"
print("\n[PASS] initialize() works correctly for programmatic creation")
