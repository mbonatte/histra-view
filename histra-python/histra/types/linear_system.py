from __future__ import annotations

import os
import warnings

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import MatrixRankWarning, splu

from histra.types.cholmod import (
    CholmodError,
    CholmodFactorization,
    CholmodUnavailable,
    find_cholmod_library,
)
from histra.types.pcg import (
    PCGConvergenceError,
    PCGFactorization,
)
from histra.types.vector_norm import csharp_vector_norm

from histra.types.umfpack import (
    UmfpackError,
    UmfpackFactorization,
    UmfpackUnavailable,
    find_umfpack_library,
)



class LinearSolveError(RuntimeError):
    """Raised when the sparse stiffness solve is singular or non-finite."""


class LinearSystem:
    """Sparse global system used by the translated static solver.

    The original C# ``LinearSystem.SetZero`` clears only the matrix values.
    Load and displacement vectors are cleared by separate methods.  Preserving
    that distinction is important because a standard Newton iteration rebuilds
    ``K`` *after* the residual has already been assembled in ``b``.
    """

    def __init__(
        self,
        n: int,
        *,
        backend: str | None = None,
        precision: str = "fast",
        irstep: int | None = None,
        ordering: str | None = None,
    ):
        self.n = int(n)
        self.ordering = ordering
        self.precision = str(
            os.environ.get("HISTRA_LINEAR_SOLVER_PRECISION", precision)
        ).strip().lower()
        if irstep is not None:
            self.irstep = int(irstep)
        elif self.precision == "fast":
            self.irstep = 0
        else:
            env_irstep = os.environ.get("HISTRA_UMFPACK_IRSTEP")
            self.irstep = int(env_irstep) if env_irstep is not None else 2
        requested = (
            backend or os.environ.get("HISTRA_LINEAR_SOLVER", "auto")
        ).strip().lower()
        aliases = {
            "suite_sparse": "umfpack",
            "suitesparse": "umfpack",
            "super_lu": "superlu",
            "suitesparse_cholmod": "cholmod",
            "conjugate_gradient": "pcg",
            "preconditioned_conjugate_gradient": "pcg",
        }
        requested = aliases.get(requested, requested)
        if requested not in {"auto", "umfpack", "superlu", "cholmod", "pcg"}:
            raise ValueError(
                "linear solver backend must be one of: auto, umfpack, superlu, cholmod, pcg; "
                f"received {requested!r}"
            )
        self.requested_backend = requested
        self.backend = (
            "umfpack" if requested == "auto" and find_umfpack_library() else
            "superlu" if requested == "auto" else requested
        )
        self.k = sp.csc_matrix((self.n, self.n), dtype=np.float64)
        self.m = sp.csc_matrix((self.n, self.n), dtype=np.float64)
        self.c = sp.csc_matrix((self.n, self.n), dtype=np.float64)
        self.x = np.zeros(self.n, dtype=np.float64)
        self.b = np.zeros(self.n, dtype=np.float64)
        self.b0 = np.zeros(self.n, dtype=np.float64)
        self._factorization = None
        self._factor_backend: str | None = None
        self._factor_matrix_id: int | None = None
        self._factor_matrix_version: int | None = None
        self._matrix_version = 0
        self.solve_count = 0
        self.factorization_count = 0

    def sumb(self, i: int, v: float) -> None:
        self.b[i] += v

    def get_b_norm(self, norm_type: int = 2) -> float:
        return float(csharp_vector_norm(self.b, norm_type))

    def get_x_norm(self, norm_type: int = 2) -> float:
        return float(csharp_vector_norm(self.x, norm_type))

    def get_x_per_b(self) -> float:
        # C# MatrixManager.Vector.operator ^ is a left-associated scalar loop.
        # Keep this reduction order for energy convergence compatibility:
        # np.add.accumulate is a strictly sequential left-associated C loop, so
        # the accumulated products reproduce the scalar loop's rounding exactly
        # (bit-identical over randomized adversarial-magnitude differentials);
        # np.dot / np.sum / builtin sum would change the rounding (pairwise or
        # Neumaier) and could flip marginal convergence decisions.
        products = np.multiply(self.x, self.b)
        if products.size == 0:
            return 0.0
        return float(np.add.accumulate(products)[-1])

    def set_x(self, i: int, v: float) -> None:
        self.x[i] = v

    def set_x_vector(self, values: np.ndarray) -> None:
        values = np.asarray(values, dtype=np.float64)
        if values.shape != (self.n,):
            raise ValueError(
                f"Expected displacement vector of shape {(self.n,)}, "
                f"received {values.shape}"
            )
        self.x[:] = values

    def get_x(self, i: int) -> float:
        return float(self.x[i])

    def set_b(self, i: int, v: float) -> None:
        self.b[i] = v

    def set_b_vector(self, values: np.ndarray) -> None:
        values = np.asarray(values, dtype=np.float64)
        if values.shape != (self.n,):
            raise ValueError(
                f"Expected load vector of shape {(self.n,)}, "
                f"received {values.shape}"
            )
        self.b[:] = values

    def get_b(self, i: int) -> float:
        return float(self.b[i])

    def _invalidate_factorization(self) -> None:
        factorization = self._factorization
        if factorization is not None and hasattr(factorization, "close"):
            factorization.close()
        self._factorization = None
        self._factor_backend = None
        self._factor_matrix_id = None
        self._factor_matrix_version = None
        self._matrix_version += 1

    @property
    def matrix_version(self) -> int:
        """Monotonic stiffness revision used by integrator solve caches."""
        return self._matrix_version

    def set_k(self, i: int, j: int, v: float) -> None:
        if not sp.isspmatrix_lil(self.k):
            self.k = self.k.tolil()
        self.k[i, j] = v
        self._invalidate_factorization()

    def get_k(self, i: int, j: int) -> float:
        return float(self.k[i, j])

    def zero_b(self) -> None:
        self.b[:] = 0.0

    def zero_x(self) -> None:
        self.x[:] = 0.0

    def copy_b_to_b0(self) -> None:
        self.b0[:] = self.b

    def set_zero_load(self) -> None:
        self.b[:] = 0.0

    def set_zero_displacement(self) -> None:
        self.x[:] = 0.0

    def set_zero(self) -> None:
        """Clear only stiffness coefficients, matching C# ``K.SetZero()``."""
        self.k = sp.csc_matrix((self.n, self.n), dtype=np.float64)
        self._matrix_version += 1

    def close(self) -> None:
        """Release native factorization resources."""
        self._invalidate_factorization()

    def __enter__(self) -> "LinearSystem":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _ensure_factorization(self, matrix: sp.csc_matrix) -> None:
        """Ensure a valid factorization exists for the given matrix, refactoring if possible."""
        same_matrix = (
            self._factorization is not None
            and self._factor_backend in (self.backend, "umfpack", "superlu", "cholmod")
            and self._factor_matrix_id == id(self.k)
            and self._factor_matrix_version == self._matrix_version
        )
        if same_matrix:
            return

        refactored = False
        if (
            self.backend == "pcg"
            and isinstance(self._factorization, PCGFactorization)
            and self._factor_backend == "pcg"
        ):
            try:
                refactored = self._factorization.refactor_numeric(matrix)
            except Exception:
                refactored = False
        elif (
            self.backend == "cholmod"
            and self._factor_backend == "cholmod"
            and isinstance(self._factorization, CholmodFactorization)
        ):
            try:
                refactored = self._factorization.refactor_numeric(matrix)
            except Exception:
                refactored = False
        elif (
            (self.backend == "umfpack" or self._factor_backend == "umfpack")
            and isinstance(self._factorization, UmfpackFactorization)
        ):
            # A numeric failure on the same verified pattern must
            # reach StaticIntegrator's native alfa=0 fallback. Repeating
            # the same failed matrix with a new symbolic factorization
            # does not occur in the original AssembleKtang sequence.
            refactored = self._factorization.refactor_numeric(matrix)

        if not refactored:
            self._create_factorization(matrix)

        self.factorization_count += 1
        self._factor_matrix_id = id(self.k)
        self._factor_matrix_version = self._matrix_version

    def _create_factorization(self, matrix: sp.csc_matrix) -> None:
        """Create a fresh factorization based on the active backend configuration."""
        if self.backend == "pcg":
            self._invalidate_factorization()
            self._factorization = PCGFactorization(matrix)
            self._factor_backend = "pcg"
        elif self.backend == "cholmod":
            chol_ok = False
            try:
                self._invalidate_factorization()
                self._factorization = CholmodFactorization(matrix)
                self._factor_backend = "cholmod"
                chol_ok = True
            except (CholmodError, CholmodUnavailable):
                chol_ok = False
            if not chol_ok:
                # Indefinite matrix (cracking / softening): fall back to UMFPACK or SuperLU
                if find_umfpack_library() is not None:
                    self._invalidate_factorization()
                    self._factorization = UmfpackFactorization(
                        matrix, irstep=self.irstep, ordering=self.ordering
                    )
                    self._factor_backend = "umfpack"
                else:
                    self._invalidate_factorization()
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", MatrixRankWarning)
                        self._factorization = splu(matrix)
                    self._factor_backend = "superlu"
        elif self.backend == "umfpack":
            self._invalidate_factorization()
            self._factorization = UmfpackFactorization(
                matrix, irstep=self.irstep, ordering=self.ordering
            )
            self._factor_backend = "umfpack"
        else:
            self._invalidate_factorization()
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                self._factorization = splu(matrix)
            self._factor_backend = "superlu"

    def solve(self, rhs: np.ndarray | None = None) -> int:
        """Solve ``K x = rhs`` and store the result in ``x``.

        HiStrA's saved afference matrices are expressed in active generalized
        DOFs: fixed DOFs are omitted while the C# model is prepared.  Therefore
        this method solves the assembled active system directly rather than
        trying to infer and eliminate restraints a second time.

        Returns ``0`` on success and raises :class:`LinearSolveError` on a
        singular or non-finite result.
        """
        if self.n == 0:
            self.x = np.zeros(0, dtype=np.float64)
            self.solve_count += 1
            return 0

        vector = self.b if rhs is None else np.asarray(rhs, dtype=np.float64)
        if vector.shape != (self.n,):
            raise ValueError(
                f"Expected right-hand side of shape {(self.n,)}, "
                f"received {vector.shape}"
            )

        matrix = self.k if isinstance(self.k, sp.csc_matrix) else self.k.tocsc()
        if matrix.shape != (self.n, self.n):
            raise LinearSolveError(
                f"Stiffness matrix has shape {matrix.shape}; "
                f"expected {(self.n, self.n)}"
            )

        try:
            self._ensure_factorization(matrix)
            effective_backend = self._factor_backend or self.backend
            if effective_backend in ("umfpack", "cholmod", "pcg"):
                solution = self._factorization.solve(vector, out=self.x)
            else:
                solution = self._factorization.solve(vector)
            self.solve_count += 1
        except (
            MatrixRankWarning, RuntimeError, ValueError,
            UmfpackUnavailable, UmfpackError,
            CholmodUnavailable, CholmodError,
            PCGConvergenceError,
        ) as exc:
            self._invalidate_factorization()
            raise LinearSolveError(
                f"Unable to solve stiffness system with {self.backend}: {exc}"
            ) from exc

        if solution is not self.x:
            solution = np.asarray(solution, dtype=np.float64).reshape(-1)
            if solution.shape != (self.n,) or not np.all(np.isfinite(solution)):
                raise LinearSolveError(
                    "Sparse solve returned a singular or non-finite displacement vector"
                )
            self.x[:] = solution
        elif not np.all(np.isfinite(self.x)):
            raise LinearSolveError(
                "Sparse solve returned a singular or non-finite displacement vector"
            )
        return 0
