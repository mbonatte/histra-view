"""Exact structural singularity checks; no numerical rank tolerance."""
try:
    from numba import njit
except ImportError:  # optional optimization; native factorization remains valid
    njit = None

if njit is not None:
    @njit(cache=True, nogil=True)
    def first_exact_zero_column(indptr, data):
        for column in range(len(indptr)-1):
            nonzero = False
            for offset in range(indptr[column],indptr[column+1]):
                if data[offset] != 0.:
                    nonzero = True
                    break
            if not nonzero:
                return column
        return -1
else:  # pragma: no cover
    first_exact_zero_column = None
