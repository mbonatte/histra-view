from __future__ import annotations

from typing import Any

from histra.types.linear_system import LinearSystem


class ConvergenceTest:
    """C#-aligned nonlinear convergence test.

    The original solver selects one of three absolute criteria. With HiStrA's
    native kN/cm unit convention, their scalar values are:

    * ``ForceMoment``: norm of ``b``, mixing force (kN) and moment (kN*cm)
      generalized components in one unscaled vector;
    * ``DispRotation``: norm of ``x``, mixing translations (cm), rotations
      (radians), and DMEM internal generalized displacements;
    * ``Work``: ``0.5 * abs(x dot b)``, in kN*cm (10 joules per unit).

    The Python translation previously used a relative residual by default and
    failed to initialize its reference norm in the line-search path.  That was
    not how the C# implementation behaves.
    """

    def __init__(
        self,
        tolerance: float = 1e-6,
        max_iter: int = 100,
        max_u: float = 1e30,
        print_level: int = 0,
        norm_type: int = 2,
        criterion: str = "ForceMoment",
        absolute: bool = True,
    ) -> None:
        self.tolerance = float(tolerance)
        self.max_iter = int(max_iter)
        self.max_u = float(max_u)
        self.print_level = int(print_level)
        self.norm_type = int(norm_type)
        self.criterion = self._normalize_criterion(criterion)
        self.absolute = bool(absolute)
        self.current_iter = 0
        self.flag = 0
        self._error = 0.0
        self._previous_raw_norm = 1.0

    @staticmethod
    def _normalize_criterion(value: Any) -> str:
        text = str(value or "ForceMoment").replace("_", "").replace(" ", "").lower()
        if text in {"disprotation", "displacement", "displacementincrement", "normdispincr"}:
            return "DispRotation"
        if text in {"work", "energy", "energyincrement"}:
            return "Work"
        if text == "forcemoment":
            return "ForceMoment"
        if text == "relativework":
            raise ValueError(
                "RelativeWork is present in the C# enum but has no convergence-test "
                "implementation in EquiSolnAlgo and is not a usable HiStrA criterion."
            )
        raise ValueError(
            "Unsupported convergence criterion. Expected ForceMoment, "
            f"DispRotation, or Work; received {value!r}."
        )

    def set_tolerance(self, tol: float) -> None:
        self.tolerance = float(tol)

    def set_max_num_iter(self, n: int) -> None:
        self.max_iter = int(n)

    def set_print_level(self, n: int) -> None:
        self.print_level = int(n)

    def start(self, ls: LinearSystem | None = None, reference_norm: float = 0.0) -> int:
        del ls, reference_norm
        self.current_iter = 1
        self._error = 0.0
        self._previous_raw_norm = 1.0
        return 0

    def _raw_error(self, ls: LinearSystem) -> float:
        if self.criterion == "DispRotation":
            return ls.get_x_norm(self.norm_type)
        if self.criterion == "Work":
            return 0.5 * abs(ls.get_x_per_b())
        return ls.get_b_norm(self.norm_type)

    def test(self, p: Any, model: Any, ls: LinearSystem) -> int:
        """Return C#-compatible result codes.

        ``>=0`` converged, ``-1`` continue, ``-2`` iteration limit and ``-3``
        maximum displacement reached.
        """
        from histra.solver.model_manager import ModelManager

        ModelManager.find_max_u(model, p)
        raw = self._raw_error(ls)

        if self.absolute:
            self._error = raw
        elif self.criterion == "ForceMoment":
            # CTestNormUnbalance divides before capturing the first norm.
            # Preserve IEEE division (including 0/0) rather than clamping it.
            import numpy as np

            with np.errstate(divide="ignore", invalid="ignore"):
                self._error = float(np.divide(raw, self._previous_raw_norm))
            if self.current_iter == 1:
                self._previous_raw_norm = raw
        else:
            # CTestNormDispIncr and CTestEnergyIncr are always absolute.
            self._error = raw

        if self._error <= self.tolerance:
            return self.current_iter
        if self.current_iter >= self.max_iter:
            self.current_iter += 1
            return -2
        if p.max_u >= self.max_u:
            return -3

        self.current_iter += 1
        return -1

    def get_error(self) -> float:
        return abs(float(self._error))

    def get_tol(self) -> float:
        return self.tolerance

    def get_copy(self, iterations: int) -> "ConvergenceTest":
        """Match the 2026.1.1 C# convergence-test copy constructors.

        CTestNormUnbalance returns a displacement test and passes its norm
        type as MaxU. This observable C# quirk is retained for output parity.
        Copies are fresh tests; no iteration/history state is inherited.
        """
        force = self.criterion == "ForceMoment"
        return ConvergenceTest(
            tolerance=self.tolerance,
            max_iter=iterations,
            max_u=float(self.norm_type) if force else self.max_u,
            norm_type=2 if force or self.criterion == "Work" else self.norm_type,
            criterion="DispRotation" if force else self.criterion,
            absolute=True,
        )
