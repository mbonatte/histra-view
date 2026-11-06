"""Opt-in, float64 CUDA sparse solves through NVIDIA nvmath/cuDSS.

Host operands keep the existing CPU assembly and constitutive kernels intact.
nvmath's blocking host interface includes transfers in measured solve times.
No CPU fallback is allowed when this experimental backend is requested.
"""
from __future__ import annotations

from functools import lru_cache
from importlib import metadata
import os

import numpy as np
import scipy.sparse as sp


class CudssUnavailable(RuntimeError):
    """The optional CUDA runtime, driver, or nvmath package is unavailable."""


class CudssError(RuntimeError):
    """cuDSS could not factorize or solve the requested system."""


def _direct_solver_type():
    try:
        from nvmath.sparse.advanced import DirectSolver
    except Exception as exc:
        raise CudssUnavailable(
            "cuDSS requires a working NVIDIA CUDA driver and nvmath-python; "
            "install histra-python[gpu-cu12] for CUDA 12 (see the GPU solver guide). "
            f"Import failed: {exc}"
        ) from exc
    return DirectSolver


def _canonical_matrix(matrix):
    if np.iscomplexobj(matrix.data):
        raise ValueError("cuDSS stiffness matrices must be real")
    result = sp.csr_matrix(matrix, dtype=np.float64, copy=True)
    if result.shape[0] != result.shape[1] or result.shape[0] == 0:
        raise ValueError("cuDSS requires a nonempty square stiffness matrix")
    result.sum_duplicates()
    result.sort_indices()
    if not np.all(np.isfinite(result.data)):
        raise ValueError("cuDSS stiffness matrix contains non-finite values")
    return result


@lru_cache(maxsize=1)
def _solver_options():
    """Enable cuDSS's packaged CPU planning layer without changing the GPU solve."""
    options = {"blocking": True}
    try:
        package = metadata.distribution("nvidia-cudss-cu12")
    except metadata.PackageNotFoundError:
        return options
    for file in package.files or ():
        if file.name == "libcudss_mtlayer_gomp.so.0":
            library = package.locate_file(file)
            if library.is_file():
                options["multithreading_lib"] = str(library)
                break
    return options


def _configure_solver(solver, mode):
    """Determinism and cuDSS 0.8 refinement are mutually exclusive profiles."""
    if mode == "refined":
        solver.solution_config.ir_num_steps = 3
        return
    if mode == "default":
        return
    from nvmath.bindings import cudss

    value = np.asarray([1], dtype=np.int32)
    cudss.config_set(solver.config_ptr, cudss.ConfigParam.DETERMINISTIC_MODE,
                     value.ctypes.data, value.nbytes)


class CudssFactorization:
    """Reuse factors for new RHS vectors and symbolic analysis for fixed topology."""

    def __init__(self, matrix):
        self._solver = None
        self.mode = os.environ.get("HISTRA_CUDSS_MODE", "deterministic").strip().lower()
        if self.mode not in {"deterministic", "refined", "default"}:
            raise ValueError("HISTRA_CUDSS_MODE must be deterministic, refined, or default")
        self.matrix = _canonical_matrix(matrix)
        self.n = self.matrix.shape[0]
        solver_type = _direct_solver_type()
        try:
            # GENERAL/FULL defaults preserve nonsymmetric and indefinite tangents.
            self._solver = solver_type(
                self.matrix, np.zeros(self.n, dtype=np.float64),
                execution="cuda", options=dict(_solver_options()),
            )
            _configure_solver(self._solver, self.mode)
            self._solver.plan()
            self._factorize()
        except Exception as exc:
            self.close()
            raise CudssError(f"cuDSS CUDA initialization/factorization failed: {exc}") from exc

    def _factorize(self):
        info = self._solver.factorize()
        if np.any(np.asarray(info.info) != 0):
            raise CudssError(f"cuDSS numerical factorization failed: info={info.info}")

    def refactor_numeric(self, matrix) -> bool:
        candidate = _canonical_matrix(matrix)
        same_pattern = (
            candidate.shape == self.matrix.shape
            and np.array_equal(candidate.indptr, self.matrix.indptr)
            and np.array_equal(candidate.indices, self.matrix.indices)
        )
        if not same_pattern:
            return False
        self._require_open()
        try:
            # CPU operands must be reset explicitly; in-place edits are not uploaded.
            self._solver.reset_operands(a=candidate)
            self._factorize()
            self.matrix = candidate
        except Exception as exc:
            raise CudssError(f"cuDSS numeric refactorization failed: {exc}") from exc
        return True

    def _require_open(self):
        if self._solver is None:
            raise CudssError("cuDSS factorization is closed")

    def solve(self, rhs, out=None):
        self._require_open()
        vector = np.array(rhs, dtype=np.float64, order="C", copy=True)
        if vector.shape != (self.n,) or not np.all(np.isfinite(vector)):
            raise ValueError(f"cuDSS requires a finite RHS of shape {(self.n,)}")
        if out is not None and (out.shape != (self.n,) or out.dtype != np.float64):
            raise ValueError("cuDSS output must be a float64 vector matching the RHS")
        try:
            self._solver.reset_operands(b=vector)
            solution = np.asarray(self._solver.solve(), dtype=np.float64)
        except Exception as exc:
            raise CudssError(f"cuDSS CUDA solve failed: {exc}") from exc
        if solution.shape != (self.n,) or not np.all(np.isfinite(solution)):
            raise CudssError("cuDSS returned a non-finite or invalid displacement vector")
        if out is not None:
            np.copyto(out, solution)
            return out
        return solution.copy()

    def close(self):
        solver, self._solver = self._solver, None
        if solver is not None:
            solver.free()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def probe_cudss() -> tuple[bool, str | None]:
    """Exercise CUDA, rather than mistaking an importable package for a usable GPU."""
    factor = None
    try:
        factor = CudssFactorization(sp.eye(1, format="csr", dtype=np.float64))
        result = factor.solve(np.ones(1))
        if not np.allclose(result, 1.0, atol=1e-12, rtol=0):
            raise CudssError("cuDSS CUDA probe returned an incorrect solution")
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        if factor is not None:
            factor.close()
