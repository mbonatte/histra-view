"""Modal-result parity checks against original HiStrA C# ``.Results`` files.

The original application stores modal summaries in ``ModalValues`` and complete
mode vectors in ``ModalShapeValues``.  This module compares those database rows
with :class:`histra.solver.modal.ModalAnalysisResult` without assuming that an
eigenvector has the same global sign in both solvers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sqlite3
from typing import Any

import numpy as np

from histra.solver.modal import ModalAnalysisResult


class ModalReferenceError(RuntimeError):
    """Raised when a C# modal reference database is missing or malformed."""


@dataclass(frozen=True)
class ModalComparisonTolerances:
    """Numerical tolerances used by the C#/Python modal parity check."""

    # Participation/effective-mass quantities can be very small, so their
    # end-to-end preprocessing comparison needs a mixed relative/absolute test.
    relative: float = 5.0e-3
    absolute: float = 1.0e-4
    # Eigenvalues/frequencies/periods and total directional masses are stricter
    # primary parity quantities.
    frequency_relative: float = 1.0e-4
    frequency_absolute: float = 1.0e-6
    mass_relative: float = 1.0e-4
    mass_absolute: float = 1.0e-6
    minimum_mac: float = 0.999

    def __post_init__(self) -> None:
        for name in (
            "relative",
            "absolute",
            "frequency_relative",
            "frequency_absolute",
            "mass_relative",
            "mass_absolute",
        ):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} tolerance must be non-negative")
        if not 0.0 <= self.minimum_mac <= 1.0:
            raise ValueError("minimum_mac must be between 0 and 1")


@dataclass(frozen=True)
class CSharpModalReference:
    analysis_key: int
    combination: int
    rows: tuple[dict[str, float | int], ...]
    shapes: np.ndarray | None
    shape_row_count: int


# C# database field, Python attribute, sign-invariant flag.
_MODAL_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("Wn", "angular_frequency", False),
    ("Fn", "frequency", False),
    ("Tn", "period", False),
    ("GammaX", "participation_x", True),
    ("GammaY", "participation_y", True),
    ("GammaZ", "participation_z", True),
    ("MassaX", "effective_mass_x", False),
    ("MassaY", "effective_mass_y", False),
    ("MassaZ", "effective_mass_z", False),
    ("MTotX", "total_mass_x", False),
    ("MTotY", "total_mass_y", False),
    ("MTotZ", "total_mass_z", False),
    ("Mx_pcent", "mass_percent_x", False),
    ("My_pcent", "mass_percent_y", False),
    ("Mz_pcent", "mass_percent_z", False),
    ("UMaxX", "max_displacement_x", False),
    ("UMaxY", "max_displacement_y", False),
    ("UMaxZ", "max_displacement_z", False),
)


def _connect_read_only(results_path: Path) -> sqlite3.Connection:
    if not results_path.exists():
        raise FileNotFoundError(f"C# Results database not found: {results_path}")
    connection = sqlite3.connect(f"file:{results_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def read_csharp_modal_reference(
    results_path: str | Path,
    analysis_key: int,
    *,
    combination: int = 1,
    dof_count: int | None = None,
    include_shapes: bool = True,
) -> CSharpModalReference:
    """Read one modal analysis from an original HiStrA ``.Results`` database."""

    path = Path(results_path)
    with _connect_read_only(path) as connection:
        if not _table_exists(connection, "ModalValues"):
            raise ModalReferenceError(f"{path} has no ModalValues table")

        columns = ", ".join(["Step"] + [item[0] for item in _MODAL_FIELDS])
        db_rows = connection.execute(
            f"SELECT {columns} FROM ModalValues "
            "WHERE AnalysisKey=? AND Combination=? ORDER BY Step",
            (int(analysis_key), int(combination)),
        ).fetchall()
        if not db_rows:
            raise ModalReferenceError(
                f"No ModalValues rows in {path} for analysis {analysis_key}, "
                f"combination {combination}."
            )
        rows = tuple({key: row[key] for key in row.keys()} for row in db_rows)

        shapes: np.ndarray | None = None
        shape_row_count = 0
        if include_shapes:
            if not _table_exists(connection, "ModalShapeValues"):
                raise ModalReferenceError(f"{path} has no ModalShapeValues table")
            shape_rows = connection.execute(
                "SELECT Step, Dof, Val FROM ModalShapeValues "
                "WHERE AnalysisKey=? AND Combination=? ORDER BY Step, Dof",
                (int(analysis_key), int(combination)),
            ).fetchall()
            shape_row_count = len(shape_rows)
            if not shape_rows:
                raise ModalReferenceError(
                    f"No ModalShapeValues rows in {path} for analysis {analysis_key}, "
                    f"combination {combination}."
                )
            inferred_dofs = max(int(row["Dof"]) for row in shape_rows) + 1
            n_dofs = inferred_dofs if dof_count is None else int(dof_count)
            if inferred_dofs > n_dofs:
                raise ModalReferenceError(
                    f"C# ModalShapeValues require {inferred_dofs} DOFs, but Python model "
                    f"has only {n_dofs}."
                )
            shapes = np.zeros((n_dofs, len(rows)), dtype=float)
            steps = {int(row["Step"]): index for index, row in enumerate(rows)}
            for row in shape_rows:
                step = int(row["Step"])
                if step not in steps:
                    raise ModalReferenceError(
                        f"ModalShapeValues contains Step={step} with no ModalValues row."
                    )
                dof = int(row["Dof"])
                if dof < 0 or dof >= n_dofs:
                    raise ModalReferenceError(
                        f"Invalid modal-shape DOF {dof}; expected 0 <= Dof < {n_dofs}."
                    )
                shapes[dof, steps[step]] = float(row["Val"])

    return CSharpModalReference(
        analysis_key=int(analysis_key),
        combination=int(combination),
        rows=rows,
        shapes=shapes,
        shape_row_count=shape_row_count,
    )


def _relative_errors(python: np.ndarray, reference: np.ndarray) -> np.ndarray:
    denominator = np.abs(reference)
    result = np.full_like(python, np.nan, dtype=float)
    nonzero = denominator > np.finfo(float).tiny
    result[nonzero] = np.abs(python[nonzero] - reference[nonzero]) / denominator[nonzero]
    return result


def _field_report(
    python: np.ndarray,
    csharp: np.ndarray,
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> dict[str, Any]:
    differences = np.abs(python - csharp)
    relative = _relative_errors(python, csharp)
    within = np.isclose(
        python,
        csharp,
        rtol=relative_tolerance,
        atol=absolute_tolerance,
        equal_nan=False,
    )
    finite_relative = relative[np.isfinite(relative)]
    return {
        "python": python.tolist(),
        "csharp": csharp.tolist(),
        "absolute_error": differences.tolist(),
        "relative_error": [None if not np.isfinite(value) else float(value) for value in relative],
        "maximum_absolute_error": float(np.max(differences)) if differences.size else 0.0,
        "maximum_absolute_relative_error": (
            float(np.max(finite_relative)) if finite_relative.size else None
        ),
        "relative_tolerance": float(relative_tolerance),
        "absolute_tolerance": float(absolute_tolerance),
        "all_within_tolerance": bool(np.all(within)),
    }


def _modal_assurance_criterion(
    python_shapes: np.ndarray, csharp_shapes: np.ndarray
) -> np.ndarray:
    """Return the sign- and scale-invariant MAC matrix between two mode sets."""

    python = np.asarray(python_shapes, dtype=float)
    csharp = np.asarray(csharp_shapes, dtype=float)
    cross = python.T @ csharp
    python_norm = np.sum(python * python, axis=0)
    csharp_norm = np.sum(csharp * csharp, axis=0)
    denominator = python_norm[:, None] * csharp_norm[None, :]
    mac = np.zeros_like(cross, dtype=float)
    valid = denominator > np.finfo(float).tiny
    mac[valid] = (np.abs(cross[valid]) ** 2) / denominator[valid]
    return np.clip(mac, 0.0, 1.0)


def compare_modal_result_to_csharp(
    result: ModalAnalysisResult,
    results_path: str | Path,
    *,
    tolerances: ModalComparisonTolerances | None = None,
    compare_shapes: bool = True,
) -> dict[str, Any]:
    """Compare one Python modal result with its original C# database output.

    ``GammaX/Y/Z`` are compared by magnitude because a global eigenvector sign
    reversal is physically immaterial.  Mode shapes are compared using the
    Modal Assurance Criterion (MAC), which is also sign and scale invariant.
    """

    limits = tolerances or ModalComparisonTolerances()
    reference = read_csharp_modal_reference(
        results_path,
        result.analysis_key,
        combination=result.combination,
        dof_count=result.dof_count,
        include_shapes=compare_shapes,
    )

    python_count = result.converged_modes
    csharp_count = len(reference.rows)
    count_equal = python_count == csharp_count
    compare_count = min(python_count, csharp_count)

    field_reports: dict[str, dict[str, Any]] = {}
    for csharp_name, python_attribute, sign_invariant in _MODAL_FIELDS:
        python_values = np.asarray(
            [getattr(mode, python_attribute) for mode in result.modes[:compare_count]],
            dtype=float,
        )
        csharp_values = np.asarray(
            [float(row[csharp_name]) for row in reference.rows[:compare_count]],
            dtype=float,
        )
        if sign_invariant:
            python_values = np.abs(python_values)
            csharp_values = np.abs(csharp_values)
        if csharp_name in {"Wn", "Fn", "Tn"}:
            rtol = limits.frequency_relative
            atol = limits.frequency_absolute
        elif csharp_name in {"MTotX", "MTotY", "MTotZ"}:
            rtol = limits.mass_relative
            atol = limits.mass_absolute
        else:
            rtol = limits.relative
            atol = limits.absolute
        field_reports[csharp_name] = _field_report(
            python_values,
            csharp_values,
            relative_tolerance=rtol,
            absolute_tolerance=atol,
        )

    shape_report: dict[str, Any] = {"compared": False}
    diagonal_mac: np.ndarray | None = None
    if compare_shapes:
        if reference.shapes is None:
            raise ModalReferenceError("Shape comparison requested but no C# shapes were loaded.")
        python_shapes = result.mode_shapes[:, :compare_count]
        csharp_shapes = reference.shapes[:, :compare_count]
        mac = _modal_assurance_criterion(python_shapes, csharp_shapes)
        diagonal_mac = np.diag(mac)
        shape_report = {
            "compared": True,
            "csharp_shape_row_count": reference.shape_row_count,
            "expected_shape_row_count": int(result.dof_count * csharp_count),
            "row_count_equal": reference.shape_row_count == result.dof_count * csharp_count,
            "diagonal_mac": diagonal_mac.tolist(),
            "minimum_diagonal_mac": float(np.min(diagonal_mac)) if diagonal_mac.size else None,
            "maximum_off_diagonal_mac": (
                float(np.max(mac - np.diag(np.diag(mac)))) if mac.size > 1 else 0.0
            ),
            "all_within_tolerance": bool(
                diagonal_mac.size == compare_count
                and np.all(diagonal_mac >= limits.minimum_mac)
                and reference.shape_row_count == result.dof_count * csharp_count
            ),
        }

    fields_pass = bool(field_reports) and all(
        field["all_within_tolerance"] for field in field_reports.values()
    )
    shapes_pass = (not compare_shapes) or bool(shape_report["all_within_tolerance"])
    passed = bool(count_equal and fields_pass and shapes_pass)

    modes: list[dict[str, Any]] = []
    for index in range(compare_count):
        fn = field_reports["Fn"]
        mode_data: dict[str, Any] = {
            "mode": index + 1,
            "python_frequency_hz": fn["python"][index],
            "csharp_frequency_hz": fn["csharp"][index],
            "absolute_frequency_error_hz": fn["absolute_error"][index],
            "relative_frequency_error": fn["relative_error"][index],
        }
        if diagonal_mac is not None:
            mode_data["mac"] = float(diagonal_mac[index])
        modes.append(mode_data)

    frequency = field_reports.get("Fn", {})
    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "results_path": str(Path(results_path)),
        "analysis_key": result.analysis_key,
        "analysis_name": result.analysis_name,
        "combination": result.combination,
        "dof_count": result.dof_count,
        "python_mode_count": python_count,
        "csharp_mode_count": csharp_count,
        "mode_count_equal": count_equal,
        "tolerances": asdict(limits),
        "maximum_absolute_frequency_error_hz": frequency.get("maximum_absolute_error"),
        "maximum_absolute_relative_frequency_error": frequency.get(
            "maximum_absolute_relative_error"
        ),
        "minimum_diagonal_mac": shape_report.get("minimum_diagonal_mac"),
        "field_comparisons": field_reports,
        "shape_comparison": shape_report,
        "modes": modes,
    }
