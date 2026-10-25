"""Energy increments from original C# Spring.ComputeEnergy."""
import numpy as np
try:
    from numba import njit
except ImportError:
    def njit(**kwargs):
        return lambda function: function

@njit(cache=True, nogil=True, error_model="numpy")
def spring_energy_increment(k, committed_stress, trial_stress, committed_strain, trial_strain):
    delta = trial_stress - committed_stress
    sign = 1.0 if delta > 0 else -1.0 if delta < 0 else 0.0
    elastic = sign * (trial_stress*trial_stress - committed_stress*committed_stress) / (2.0*k)
    total = 0.5 * (committed_stress + trial_stress) * (trial_strain - committed_strain)
    return elastic, total - elastic, total
