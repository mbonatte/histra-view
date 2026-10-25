"""Minimal ctypes binding for the SuiteSparse CHOLMOD API.

CHOLMOD performs high-performance supernodal Cholesky factorization for
symmetric positive-definite linear systems, substantially outperforming
general unsymmetric LU factorizations (like UMFPACK or SuperLU) on 3D
structural macro-element meshes.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import scipy.sparse as sp


class CholmodUnavailable(RuntimeError):
    """Raised when a requested native CHOLMOD library cannot be loaded."""


class CholmodError(RuntimeError):
    """Raised when a CHOLMOD symbolic, numeric or solve call fails."""


def _candidate_names(explicit: str | os.PathLike[str] | None = None) -> Iterable[str]:
    if explicit:
        yield os.fspath(explicit)
    configured = os.environ.get("HISTRA_CHOLMOD_LIBRARY")
    if configured and (not explicit or configured != os.fspath(explicit)):
        yield configured
    discovered = ctypes.util.find_library("cholmod")
    if discovered:
        yield discovered
    yield from (
        "libcholmod.so.5",
        "libcholmod.so",
        "libcholmod.dylib",
        "cholmod.dll",
        "libcholmod.dll",
    )


def find_cholmod_library(explicit: str | os.PathLike[str] | None = None) -> str | None:
    """Return the first loadable CHOLMOD library name/path, or ``None``."""
    for candidate in _candidate_names(explicit):
        try:
            ctypes.CDLL(candidate)
        except OSError:
            continue
        return candidate
    return None


def is_cholmod_available() -> bool:
    """Check whether a native CHOLMOD shared library is available."""
    return find_cholmod_library() is not None


class _CholmodCommon(ctypes.Structure):
    _fields_ = [
        ("dbound", ctypes.c_double),
        ("grow0", ctypes.c_double),
        ("grow1", ctypes.c_double),
        ("grow2", ctypes.c_size_t),
        ("maxrank", ctypes.c_size_t),
        ("supernodal_switch", ctypes.c_double),
        ("supernodal", ctypes.c_int),
        ("final_asis", ctypes.c_int),
        ("final_super", ctypes.c_int),
        ("final_ll", ctypes.c_int),
        ("final_pack", ctypes.c_int),
        ("final_monotonic", ctypes.c_int),
        ("final_resymbol", ctypes.c_int),
        ("zrelax", ctypes.c_double * 3),
        ("nrelax", ctypes.c_size_t * 3),
        ("prefer_zomplex", ctypes.c_int),
        ("prefer_upper", ctypes.c_int),
        ("quick_return_if_not_posdef", ctypes.c_int),
        ("prefer_binary", ctypes.c_int),
        ("print", ctypes.c_int),
        ("precise", ctypes.c_int),
        ("try_catch", ctypes.c_int),
        ("_pad", ctypes.c_byte * 2520),
    ]


class _CholmodSparse(ctypes.Structure):
    _fields_ = [
        ("nrow", ctypes.c_size_t),
        ("ncol", ctypes.c_size_t),
        ("nzmax", ctypes.c_size_t),
        ("p", ctypes.c_void_p),
        ("i", ctypes.c_void_p),
        ("nz", ctypes.c_void_p),
        ("x", ctypes.c_void_p),
        ("z", ctypes.c_void_p),
        ("stype", ctypes.c_int),
        ("itype", ctypes.c_int),
        ("xtype", ctypes.c_int),
        ("dtype", ctypes.c_int),
        ("sorted", ctypes.c_int),
        ("packed", ctypes.c_int),
    ]


class _CholmodDense(ctypes.Structure):
    _fields_ = [
        ("nrow", ctypes.c_size_t),
        ("ncol", ctypes.c_size_t),
        ("nzmax", ctypes.c_size_t),
        ("d", ctypes.c_size_t),
        ("x", ctypes.c_void_p),
        ("z", ctypes.c_void_p),
        ("xtype", ctypes.c_int),
        ("dtype", ctypes.c_int),
    ]


class _CholmodFactor(ctypes.Structure):
    _fields_ = [
        ("n", ctypes.c_size_t),
        ("minor", ctypes.c_size_t),
    ]


class CholmodFactorization:
    """Own one native CHOLMOD symbolic/numeric Cholesky factorization."""

    def __init__(
        self,
        matrix: sp.spmatrix,
        *,
        library: str | os.PathLike[str] | None = None,
        supernodal: int | None = None,
    ) -> None:
        candidate = find_cholmod_library(library)
        if candidate is None:
            requested = os.fspath(library) if library else "an installed SuiteSparse CHOLMOD library"
            raise CholmodUnavailable(
                "CHOLMOD was requested but no loadable library was found. "
                f"Expected {requested}. Set HISTRA_CHOLMOD_LIBRARY to the native "
                "cholmod shared library path."
            )
        self.library_path = candidate
        self._lib = ctypes.CDLL(candidate)
        self._configure_api()

        if matrix.shape[0] != matrix.shape[1]:
            raise ValueError(f"CHOLMOD requires a square matrix, received {matrix.shape}")
        if matrix.shape[0] > np.iinfo(np.int32).max or matrix.nnz > np.iinfo(np.int32).max:
            raise ValueError("cholmod uses 32-bit indices; matrix is too large")

        self.n = int(matrix.shape[0])
        self._common = _CholmodCommon()
        self._common_initialized = False
        self._L: ctypes.c_void_p | None = None
        self._closed = False

        status = self._lib.cholmod_start(ctypes.byref(self._common))
        if status == 0:
            raise CholmodError("cholmod_start failed to initialize common workspace")
        self._common_initialized = True

        # Silence stdout prints and catch warnings gracefully
        self._common.print = -1
        self._common.try_catch = 1
        self._common.final_asis = 0
        self._common.final_ll = 1
        if supernodal is not None:
            self._common.supernodal = int(supernodal)

        # HiStrA structural stiffness matrices are symmetric. We symmetrize and
        # extract the sorted lower triangle for CHOLMOD (stype = -1).
        k_sym = (matrix + matrix.T) * 0.5
        k_lower = sp.tril(k_sym).tocsc()
        k_lower.sort_indices()

        self.ap = np.ascontiguousarray(k_lower.indptr, dtype=np.int32)
        self.ai = np.ascontiguousarray(k_lower.indices, dtype=np.int32)
        self.ax = np.ascontiguousarray(k_lower.data, dtype=np.float64)

        self._sparse = _CholmodSparse()
        self._sparse.nrow = self.n
        self._sparse.ncol = self.n
        self._sparse.nzmax = len(self.ax)
        self._sparse.p = self.ap.ctypes.data
        self._sparse.i = self.ai.ctypes.data
        self._sparse.nz = None
        self._sparse.x = self.ax.ctypes.data
        self._sparse.z = None
        self._sparse.stype = -1  # Lower triangular symmetric
        self._sparse.itype = 0   # CHOLMOD_INT
        self._sparse.xtype = 1   # CHOLMOD_REAL
        self._sparse.dtype = 0   # CHOLMOD_DOUBLE
        self._sparse.sorted = 1
        self._sparse.packed = 1

        self._L = self._lib.cholmod_analyze(
            ctypes.byref(self._sparse), ctypes.byref(self._common)
        )
        if not self._L:
            self.close()
            raise CholmodError("CHOLMOD symbolic analysis failed")

        status = self._lib.cholmod_factorize(
            ctypes.byref(self._sparse), self._L, ctypes.byref(self._common)
        )
        factor = _CholmodFactor.from_address(self._L)
        if factor.minor < factor.n:
            minor = factor.minor
            self.close()
            raise CholmodError(
                f"Matrix is singular or not positive definite (failed at minor {minor} of {self.n})"
            )

    def _configure_api(self) -> None:
        void_p = ctypes.c_void_p
        void_pp = ctypes.POINTER(ctypes.c_void_p)
        self._lib.cholmod_start.argtypes = [void_p]
        self._lib.cholmod_start.restype = ctypes.c_int
        self._lib.cholmod_finish.argtypes = [void_p]
        self._lib.cholmod_finish.restype = ctypes.c_int
        self._lib.cholmod_analyze.argtypes = [void_p, void_p]
        self._lib.cholmod_analyze.restype = void_p
        self._lib.cholmod_factorize.argtypes = [void_p, void_p, void_p]
        self._lib.cholmod_factorize.restype = ctypes.c_int
        self._lib.cholmod_solve.argtypes = [ctypes.c_int, void_p, void_p, void_p]
        self._lib.cholmod_solve.restype = void_p
        self._lib.cholmod_free_factor.argtypes = [void_pp, void_p]
        self._lib.cholmod_free_factor.restype = ctypes.c_int
        self._lib.cholmod_free_dense.argtypes = [void_pp, void_p]
        self._lib.cholmod_free_dense.restype = ctypes.c_int

    def can_refactor_numeric(self, matrix: sp.spmatrix) -> bool:
        """Check whether matrix matches dimensions and can be refactored."""
        if self._closed or not self._L or not self._common_initialized:
            return False
        if getattr(matrix, "shape", None) != (self.n, self.n):
            return False
        return True

    def refactor_numeric(self, matrix: sp.spmatrix) -> bool:
        """Reuse existing symbolic factorization and compute a new numeric factorization."""
        if not self.can_refactor_numeric(matrix):
            return False
        k_sym = (matrix + matrix.T) * 0.5
        k_lower = sp.tril(k_sym).tocsc()
        k_lower.sort_indices()
        if len(k_lower.data) != len(self.ax):
            return False
        if not np.array_equal(k_lower.indptr, self.ap) or not np.array_equal(k_lower.indices, self.ai):
            return False

        np.copyto(self.ax, k_lower.data)
        status = self._lib.cholmod_factorize(
            ctypes.byref(self._sparse), self._L, ctypes.byref(self._common)
        )
        factor = _CholmodFactor.from_address(self._L)
        if factor.minor < factor.n:
            raise CholmodError(
                f"Matrix is singular or not positive definite (failed at minor {factor.minor} of {factor.n})"
            )
        return True

    def solve(self, rhs: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
        if self._closed or not self._L:
            raise CholmodError("CHOLMOD factorization is already closed")
        b = np.ascontiguousarray(rhs, dtype=np.float64)
        if b.shape != (self.n,):
            raise ValueError(f"Expected right-hand side shape {(self.n,)}, got {b.shape}")

        if out is None:
            x = np.zeros(self.n, dtype=np.float64)
        else:
            if out.shape != (self.n,) or out.dtype != np.float64:
                raise ValueError(
                    f"Expected out shape {(self.n,)} float64, got {out.shape} {out.dtype}"
                )
            if not out.flags.c_contiguous:
                raise ValueError("Expected out to be C-contiguous")
            x = out

        dense_b = _CholmodDense()
        dense_b.nrow = self.n
        dense_b.ncol = 1
        dense_b.nzmax = self.n
        dense_b.d = self.n
        dense_b.x = b.ctypes.data
        dense_b.z = None
        dense_b.xtype = 1  # CHOLMOD_REAL
        dense_b.dtype = 0  # CHOLMOD_DOUBLE

        x_ptr = self._lib.cholmod_solve(
            0, self._L, ctypes.byref(dense_b), ctypes.byref(self._common)
        )
        if not x_ptr:
            raise CholmodError("CHOLMOD solve returned NULL")

        try:
            x_dense = _CholmodDense.from_address(x_ptr)
            arr = np.ctypeslib.as_array(
                ctypes.cast(x_dense.x, ctypes.POINTER(ctypes.c_double)),
                shape=(self.n,),
            )
            np.copyto(x, arr)
        finally:
            x_handle = ctypes.c_void_p(x_ptr)
            self._lib.cholmod_free_dense(
                ctypes.byref(x_handle), ctypes.byref(self._common)
            )
        return x

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        if getattr(self, "_L", None):
            l_handle = ctypes.c_void_p(self._L)
            self._lib.cholmod_free_factor(
                ctypes.byref(l_handle), ctypes.byref(self._common)
            )
            self._L = None
        if getattr(self, "_common_initialized", False):
            self._lib.cholmod_finish(ctypes.byref(self._common))
            self._common_initialized = False
        self._closed = True

    def __enter__(self) -> "CholmodFactorization":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
