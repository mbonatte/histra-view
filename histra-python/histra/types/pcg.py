"""Preconditioned Conjugate Gradient (PCG) iterative linear solver.

Provides matrix-free, iterative solving for large symmetric positive-definite
structural systems. Supports Jacobi (diagonal scaling) and Symmetric Successive
Over-Relaxation (SSOR) preconditioners, with automatic fallback to high-performance
direct solvers (CHOLMOD or UMFPACK) if ill-conditioning or contact detachment
prevents convergence within the iteration limit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve_triangular

logger = logging.getLogger(__name__)


class PCGConvergenceError(RuntimeError):
    """Raised when the PCG solver fails to converge within the iteration limit."""


@dataclass(frozen=True)
class PCGResult:
    """Outcome of a Preconditioned Conjugate Gradient solve."""
    x: np.ndarray
    iterations: int
    residual_norm: float
    converged: bool


def _build_preconditioner(
    A: sp.spmatrix,
    preconditioner: str = "ssor",
    omega: float = 1.0,
) -> Callable[[np.ndarray], np.ndarray]:
    """Construct a fast symmetric preconditioning operator."""
    precon_type = preconditioner.strip().lower()
    n = A.shape[0]

    if precon_type in ("none", "identity"):
        return lambda v: v

    diag = A.diagonal().astype(np.float64)

    if precon_type == "jacobi":
        inv_diag = np.where(np.abs(diag) > 1e-14, 1.0 / diag, 1.0)
        return lambda v: inv_diag * v

    if precon_type == "ssor":
        # SSOR: M = 1/(2-w) * (D + w*L) * D^-1 * (D + w*L^T)
        scale = float(2.0 - omega)
        L_strict = sp.tril(A, -1, format="csr").astype(np.float64)
        D = sp.diags(diag, format="csr", dtype=np.float64)
        M_lower = (D + omega * L_strict).tocsr()
        M_upper = (D + omega * L_strict.T).tocsr()

        safe_diag = np.where(np.abs(diag) > 1e-14, diag, 1.0)

        def apply_ssor(v: np.ndarray) -> np.ndarray:
            try:
                y = spsolve_triangular(M_lower, v, lower=True)
                Dy = safe_diag * y
                z = spsolve_triangular(M_upper, Dy, lower=False)
                if scale != 1.0:
                    z *= scale
                return z
            except Exception:
                # Fallback to Jacobi if triangular solve fails
                inv_d = np.where(np.abs(diag) > 1e-14, 1.0 / diag, 1.0)
                return inv_d * v

        return apply_ssor

    if precon_type in ("amg", "pyamg", "algebraic_multigrid"):
        try:
            import pyamg
            csr = A if isinstance(A, sp.csr_matrix) else A.tocsr()
            ml = pyamg.smoothed_aggregation_solver(csr)
            M = ml.aspreconditioner(cycle="V")
            return lambda v: M.matvec(v)
        except Exception as exc:
            logger.debug("PyAMG preconditioner setup failed: %s; falling back to SSOR", exc)
            return _build_preconditioner(A, preconditioner="ssor", omega=omega)

    raise ValueError(f"Unknown preconditioner type: {preconditioner!r}; expected 'ssor', 'jacobi', 'amg', or 'none'")


def pcg_solve(
    A: sp.spmatrix,
    b: np.ndarray,
    x0: np.ndarray | None = None,
    *,
    tol: float = 1e-6,
    maxiter: int = 500,
    preconditioner: str = "ssor",
    omega: float = 1.0,
) -> PCGResult:
    """Solve A x = b using Preconditioned Conjugate Gradient.

    Parameters
    ----------
    A : sp.spmatrix
        Symmetric positive-definite sparse matrix.
    b : np.ndarray
        Right-hand side vector.
    x0 : np.ndarray | None
        Initial guess vector.
    tol : float
        Relative residual tolerance: ||b - A x|| / ||b|| <= tol.
    maxiter : int
        Maximum number of PCG iterations.
    preconditioner : str
        Preconditioner type ('ssor', 'jacobi', 'none').
    omega : float
        Relaxation parameter for SSOR (typically 1.0 <= omega < 2.0).
    """
    n = len(b)
    if A.shape != (n, n):
        raise ValueError(f"Matrix shape {A.shape} does not match vector size {n}")

    b_vec = np.asarray(b, dtype=np.float64)
    norm_b = float(np.linalg.norm(b_vec))
    if norm_b == 0.0:
        return PCGResult(x=np.zeros(n, dtype=np.float64), iterations=0, residual_norm=0.0, converged=True)

    x = np.zeros(n, dtype=np.float64) if x0 is None else np.asarray(x0, dtype=np.float64).copy()
    r = b_vec - (A @ x)
    norm_r = float(np.linalg.norm(r))
    rel_res = norm_r / norm_b
    if rel_res <= tol:
        return PCGResult(x=x, iterations=0, residual_norm=rel_res, converged=True)

    apply_M = _build_preconditioner(A, preconditioner=preconditioner, omega=omega)
    z = apply_M(r)
    p = z.copy()
    rz_old = float(np.dot(r, z))

    if rz_old <= 0.0 or not np.isfinite(rz_old):
        # Preconditioner is not positive definite
        return PCGResult(x=x, iterations=0, residual_norm=rel_res, converged=False)

    for it in range(1, maxiter + 1):
        Ap = A @ p
        pAp = float(np.dot(p, Ap))
        if pAp <= 0.0 or not np.isfinite(pAp):
            # Breakdown or indefinite direction
            break

        alpha = rz_old / pAp
        x += alpha * p
        r -= alpha * Ap

        norm_r = float(np.linalg.norm(r))
        rel_res = norm_r / norm_b
        if rel_res <= tol:
            return PCGResult(x=x, iterations=it, residual_norm=rel_res, converged=True)

        z = apply_M(r)
        rz_new = float(np.dot(r, z))
        if rz_new <= 0.0 or not np.isfinite(rz_new):
            break

        beta = rz_new / rz_old
        p = z + beta * p
        rz_old = rz_new

    return PCGResult(x=x, iterations=maxiter, residual_norm=rel_res, converged=False)


class PCGFactorization:
    """Iterative PCG solver wrapper matching the Factorization interface.

    Solves A x = b iteratively and falls back to a direct solver (CHOLMOD or
    UMFPACK) if PCG does not reach the specified tolerance within maxiter.
    """

    def __init__(
        self,
        matrix: sp.spmatrix,
        *,
        tol: float = 1e-6,
        maxiter: int = 500,
        preconditioner: str = "ssor",
        omega: float = 1.0,
        fallback_backend: str | None = "auto",
    ) -> None:
        self.n = int(matrix.shape[0])
        self.matrix = matrix if isinstance(matrix, sp.csc_matrix) else matrix.tocsc()
        self.tol = float(tol)
        self.maxiter = int(maxiter)
        self.preconditioner = str(preconditioner)
        self.omega = float(omega)
        self.fallback_backend = fallback_backend
        self._fallback_factorization: Any = None
        self._closed = False
        self.last_iterations = 0
        self.last_residual_norm = 0.0
        self.fallback_used = False

    def can_refactor_numeric(self, matrix: sp.spmatrix) -> bool:
        if self._closed or getattr(matrix, "shape", None) != (self.n, self.n):
            return False
        return True

    def refactor_numeric(self, matrix: sp.spmatrix) -> bool:
        if not self.can_refactor_numeric(matrix):
            return False
        self.matrix = matrix if isinstance(matrix, sp.csc_matrix) else matrix.tocsc()
        if self._fallback_factorization is not None:
            if hasattr(self._fallback_factorization, "refactor_numeric"):
                try:
                    self._fallback_factorization.refactor_numeric(self.matrix)
                except Exception:
                    self._fallback_factorization = None
            else:
                self._fallback_factorization = None
        return True

    def _get_fallback(self) -> Any:
        if self._fallback_factorization is not None:
            return self._fallback_factorization
        from histra.types.cholmod import CholmodFactorization, is_cholmod_available
        from histra.types.umfpack import UmfpackFactorization, find_umfpack_library

        if is_cholmod_available():
            self._fallback_factorization = CholmodFactorization(self.matrix)
        elif find_umfpack_library() is not None:
            self._fallback_factorization = UmfpackFactorization(self.matrix)
        else:
            from scipy.sparse.linalg import splu
            self._fallback_factorization = splu(self.matrix)
        return self._fallback_factorization

    def solve(self, rhs: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
        if self._closed:
            raise RuntimeError("PCGFactorization is already closed")

        b = np.ascontiguousarray(rhs, dtype=np.float64)
        if b.shape != (self.n,):
            raise ValueError(f"Expected right-hand side shape {(self.n,)}, got {b.shape}")

        # Symmetrize for PCG
        A_sym = (self.matrix + self.matrix.T) * 0.5

        result = pcg_solve(
            A_sym,
            b,
            x0=out if out is not None else None,
            tol=self.tol,
            maxiter=self.maxiter,
            preconditioner=self.preconditioner,
            omega=self.omega,
        )
        self.last_iterations = result.iterations
        self.last_residual_norm = result.residual_norm

        if result.converged and np.all(np.isfinite(result.x)):
            self.fallback_used = False
            if out is not None:
                np.copyto(out, result.x)
                return out
            return result.x

        # Fallback to direct solver
        self.fallback_used = True
        logger.debug(
            "PCG did not converge (iters=%d, rel_res=%.2e); falling back to direct solver",
            result.iterations,
            result.residual_norm,
        )
        direct = self._get_fallback()
        if hasattr(direct, "solve"):
            if out is not None:
                try:
                    return direct.solve(b, out=out)
                except TypeError:
                    sol = direct.solve(b)
                    np.copyto(out, sol)
                    return out
            return direct.solve(b)
        raise PCGConvergenceError(
            f"PCG failed to converge (res={result.residual_norm:.2e}) and direct fallback failed."
        )

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        if self._fallback_factorization is not None:
            if hasattr(self._fallback_factorization, "close"):
                self._fallback_factorization.close()
            self._fallback_factorization = None
        self._closed = True

    def __enter__(self) -> "PCGFactorization":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
