"""Minimal ctypes binding for the UMFPACK API used by the C# HiStrA solver.

The authoritative C# implementation calls the 32-bit-index, double-precision
``umfpack_di_*`` API, initializes the default control vector and then forces
``UMFPACK_STRATEGY_SYMMETRIC`` (control slot 5 = 3).  Keeping the binding here
small avoids a hard dependency on a particular Python wrapper and lets a user
point HiStrA at the same native SuiteSparse library used by the original code.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import scipy.sparse as sp


class UmfpackUnavailable(RuntimeError):
    """Raised when a requested native UMFPACK library cannot be loaded."""


class UmfpackError(RuntimeError):
    """Raised when an UMFPACK symbolic, numeric or solve call fails."""


_UMFPACK_A = 0
_UMFPACK_OK = 0
_UMFPACK_CONTROL = 20
_UMFPACK_INFO = 90
_UMFPACK_STRATEGY = 5
_UMFPACK_STRATEGY_SYMMETRIC = 3.0
_UMFPACK_IRSTEP = 7
_UMFPACK_ORDERING = 10
_UMFPACK_ORDERING_CHOLMOD = 0.0
_UMFPACK_ORDERING_AMD = 1.0
_UMFPACK_ORDERING_METIS = 3.0
_UMFPACK_ORDERING_BEST = 4.0


def _candidate_names(explicit: str | os.PathLike[str] | None = None) -> Iterable[str]:
    if explicit:
        yield os.fspath(explicit)
    configured = os.environ.get("HISTRA_UMFPACK_LIBRARY")
    if configured and (not explicit or configured != os.fspath(explicit)):
        yield configured
    discovered = ctypes.util.find_library("umfpack")
    if discovered:
        yield discovered
    # Common SuiteSparse names on Linux/macOS and the names used by Windows
    # distributions.  Loading is attempted in order and failures are retained
    # for a useful final error message.
    yield from (
        "libumfpack.so",
        "libumfpack.dylib",
        "umfpack.dll",
        "libumfpack.dll",
    )


def find_umfpack_library(explicit: str | os.PathLike[str] | None = None) -> str | None:
    """Return the first loadable UMFPACK library name/path, or ``None``."""
    for candidate in _candidate_names(explicit):
        try:
            ctypes.CDLL(candidate)
        except OSError:
            continue
        return candidate
    return None


class UmfpackFactorization:
    """Own one C#-compatible UMFPACK symbolic/numeric factorization."""

    def __init__(
        self,
        matrix: sp.spmatrix,
        *,
        library: str | os.PathLike[str] | None = None,
        irstep: int | None = None,
        ordering: str | None = None,
    ) -> None:
        self.ordering = ordering
        candidate = find_umfpack_library(library)
        if candidate is None:
            requested = os.fspath(library) if library else "an installed SuiteSparse library"
            raise UmfpackUnavailable(
                "UMFPACK was requested but no loadable library was found. "
                f"Expected {requested}. Set HISTRA_UMFPACK_LIBRARY to the native "
                "umfpack shared library path."
            )
        self.library_path = candidate
        self._lib = ctypes.CDLL(candidate)
        self._configure_api()
        self._symbolic = ctypes.c_void_p()
        self._numeric = ctypes.c_void_p()
        self._closed = False

        if (
            isinstance(matrix, sp.csc_matrix)
            and getattr(matrix, "has_canonical_format", False)
            and getattr(matrix, "has_sorted_indices", False)
            and matrix.dtype == np.float64
        ):
            csc = matrix
        else:
            csc = sp.csc_matrix(matrix, dtype=np.float64, copy=True)
            csc.sum_duplicates()
            csc.sort_indices()
        if csc.shape[0] != csc.shape[1]:
            raise ValueError(f"UMFPACK requires a square matrix, received {csc.shape}")
        if csc.shape[0] > np.iinfo(np.int32).max or csc.nnz > np.iinfo(np.int32).max:
            raise ValueError("umfpack_di_* uses 32-bit indices; matrix is too large")

        self.n = int(csc.shape[0])
        self.ap = np.ascontiguousarray(csc.indptr, dtype=np.int32)
        self.ai = np.ascontiguousarray(csc.indices, dtype=np.int32)
        self.ax = np.ascontiguousarray(csc.data, dtype=np.float64)
        self.control = np.zeros(_UMFPACK_CONTROL, dtype=np.float64)
        self.info = np.zeros(_UMFPACK_INFO, dtype=np.float64)

        if irstep is None:
            env_irstep = os.environ.get("HISTRA_UMFPACK_IRSTEP")
            if env_irstep is not None:
                try:
                    irstep = int(env_irstep)
                except ValueError:
                    irstep = 2
            else:
                irstep = 2
        self.irstep = int(irstep)

        self._ap_ptr = self._int_ptr(self.ap)
        self._ai_ptr = self._int_ptr(self.ai)
        self._ax_ptr = self._double_ptr(self.ax)
        self._control_ptr = self._double_ptr(self.control)
        self._info_ptr = self._double_ptr(self.info)

        # Pre-bind raw memory addresses for direct zero-copy C ABI calls
        self._ap_data = self.ap.ctypes.data
        self._ai_data = self.ai.ctypes.data
        self._ax_data = self.ax.ctypes.data
        self._control_data = self.control.ctypes.data
        self._info_data = self.info.ctypes.data
        self._solve_fn = self._lib.umfpack_di_solve

        self._lib.umfpack_di_defaults(self._control_ptr)
        # Exact override in MatrixManager.SparseMatrix.InitializeControl().
        self.control[_UMFPACK_STRATEGY] = _UMFPACK_STRATEGY_SYMMETRIC
        self.control[_UMFPACK_IRSTEP] = float(self.irstep)

        # UMFPACK ordering (control slot 10): 0=CHOLMOD, 1=AMD, 3=METIS, 4=BEST.
        # METIS/CHOLMOD reduces fill-in on 3D meshes by over 15x, cutting numeric
        # factorization time by more than half (e.g. from 12.0s to 5.7s on 47k DOFs).
        ord_val = self.ordering or os.environ.get("HISTRA_UMFPACK_ORDERING", "metis")
        env_ordering = str(ord_val).strip().lower()
        if env_ordering in ("metis", "3"):
            self.control[_UMFPACK_ORDERING] = _UMFPACK_ORDERING_METIS
        elif env_ordering in ("cholmod", "0"):
            self.control[_UMFPACK_ORDERING] = _UMFPACK_ORDERING_CHOLMOD
        elif env_ordering in ("best", "4"):
            self.control[_UMFPACK_ORDERING] = _UMFPACK_ORDERING_BEST
        elif env_ordering in ("amd", "1"):
            self.control[_UMFPACK_ORDERING] = _UMFPACK_ORDERING_AMD

        # SolverRuntime.ModelManager.PrepareMatrices() maps the sparse pattern
        # and performs UMFPACK's symbolic factorization before PrepareK() has
        # assembled any stiffness coefficients.  Its Ax array is therefore
        # entirely zero during this call; the populated values are used only
        # by the subsequent numeric factorization.  Preserve that sequence
        # here because UMFPACK may use Ax while selecting a symmetric ordering.
        symbolic_ax = np.zeros_like(self.ax)
        status = self._lib.umfpack_di_symbolic(
            self.n,
            self.n,
            self._ap_ptr,
            self._ai_ptr,
            self._double_ptr(symbolic_ax),
            ctypes.byref(self._symbolic),
            self._control_ptr,
            self._info_ptr,
        )
        self._require_ok(status, "symbolic factorization")
        status = self._lib.umfpack_di_numeric(
            self._ap_ptr,
            self._ai_ptr,
            self._ax_ptr,
            self._symbolic,
            ctypes.byref(self._numeric),
            self._control_ptr,
            self._info_ptr,
        )
        self._require_ok(status, "numeric factorization")

    @staticmethod
    def _int_ptr(values: np.ndarray):
        return values.ctypes.data_as(ctypes.POINTER(ctypes.c_int))

    @staticmethod
    def _double_ptr(values: np.ndarray):
        return values.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

    def _configure_api(self) -> None:
        int_p = ctypes.POINTER(ctypes.c_int)
        double_p = ctypes.POINTER(ctypes.c_double)
        void_pp = ctypes.POINTER(ctypes.c_void_p)
        self._lib.umfpack_di_defaults.argtypes = [double_p]
        self._lib.umfpack_di_defaults.restype = None
        self._lib.umfpack_di_symbolic.argtypes = [
            ctypes.c_int, ctypes.c_int, int_p, int_p, double_p, void_pp,
            double_p, double_p,
        ]
        self._lib.umfpack_di_symbolic.restype = ctypes.c_int
        self._lib.umfpack_di_numeric.argtypes = [
            int_p, int_p, double_p, ctypes.c_void_p, void_pp, double_p, double_p,
        ]
        self._lib.umfpack_di_numeric.restype = ctypes.c_int
        void_p = ctypes.c_void_p
        self._lib.umfpack_di_solve.argtypes = [
            ctypes.c_int, void_p, void_p, void_p, void_p, void_p,
            void_p, void_p, void_p,
        ]
        self._lib.umfpack_di_solve.restype = ctypes.c_int
        self._lib.umfpack_di_free_symbolic.argtypes = [void_pp]
        self._lib.umfpack_di_free_symbolic.restype = None
        self._lib.umfpack_di_free_numeric.argtypes = [void_pp]
        self._lib.umfpack_di_free_numeric.restype = None

    def _require_ok(self, status: int, operation: str) -> None:
        if int(status) != _UMFPACK_OK:
            self.close()
            raise UmfpackError(
                f"UMFPACK {operation} failed with status {int(status)} "
                f"(Info[0]={self.info[0] if self.info.size else float('nan')})."
            )

    def solve(self, rhs: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
        if self._closed or not self._numeric:
            raise UmfpackError("UMFPACK factorization is already closed")
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

        status = self._solve_fn(
            _UMFPACK_A,
            self._ap_data,
            self._ai_data,
            self._ax_data,
            x.ctypes.data,
            b.ctypes.data,
            self._numeric,
            self._control_data,
            self._info_data,
        )
        self._require_ok(status, "solve")
        return x

    def can_refactor_numeric(self, matrix: sp.spmatrix) -> bool:
        """Check whether matrix shares the exact sparsity pattern of current factorization."""
        if self._closed or not self._symbolic:
            return False
        if getattr(matrix, "shape", None) != (self.n, self.n):
            return False
        if getattr(matrix, "format", None) != "csc":
            return False
        data = getattr(matrix, "data", None)
        if data is None or len(data) != len(self.ax):
            return False
        indptr = getattr(matrix, "indptr", None)
        indices = getattr(matrix, "indices", None)
        if indptr is None or indices is None:
            return False
        if indptr is self.ap and indices is self.ai:
            return True
        if len(indptr) == len(self.ap) and len(indices) == len(self.ai):
            if np.array_equal(indptr, self.ap) and np.array_equal(indices, self.ai):
                return True
        return False

    def refactor_numeric(self, matrix: sp.spmatrix) -> bool:
        """Reuse existing symbolic factorization and compute a new numeric factorization."""
        if not self.can_refactor_numeric(matrix):
            return False
        np.copyto(self.ax, matrix.data)
        if self._numeric:
            self._lib.umfpack_di_free_numeric(ctypes.byref(self._numeric))
            self._numeric = ctypes.c_void_p()
        status = self._lib.umfpack_di_numeric(
            self._ap_ptr,
            self._ai_ptr,
            self._ax_ptr,
            self._symbolic,
            ctypes.byref(self._numeric),
            self._control_ptr,
            self._info_ptr,
        )
        self._require_ok(status, "numeric factorization")
        return True

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        if getattr(self, "_numeric", None):
            self._lib.umfpack_di_free_numeric(ctypes.byref(self._numeric))
        if getattr(self, "_symbolic", None):
            self._lib.umfpack_di_free_symbolic(ctypes.byref(self._symbolic))
        self._closed = True

    def __enter__(self) -> "UmfpackFactorization":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown dependent
        try:
            self.close()
        except Exception:
            pass
