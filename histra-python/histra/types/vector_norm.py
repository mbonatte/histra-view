"""Ordered MatrixManager.LinearSystem vector-norm reduction."""
import math

from numba import njit


@njit(cache=True, nogil=True, error_model='numpy')
def csharp_vector_norm(values, norm_type):
    total = 0.0
    if norm_type > 0:
        for value in values:
            total += math.pow(abs(value), float(norm_type))
        return math.pow(total, 1.0 / norm_type)
    for value in values:
        # Retain Python's existing nonfinite guard for maximum norms, instead
        # of allowing NaN comparisons to hide a malformed residual.
        if math.isnan(value):
            return math.nan
        magnitude = abs(value)
        if magnitude > total:
            total = magnitude
    return total
