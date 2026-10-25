from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from histra.solver.modal import ModalAnalysisResult, ModalMode
from histra.tools.run_modal import discover_hrx_inputs
from histra.validation.modal_results import (
    ModalComparisonTolerances,
    compare_modal_result_to_csharp,
)


def _mode(number: int, frequency: float, shape: np.ndarray, gamma_x: float) -> ModalMode:
    omega = frequency * 2.0 * np.pi
    return ModalMode(
        mode_number=number,
        eigenvalue=omega * omega,
        angular_frequency=omega,
        frequency=frequency,
        period=1.0 / frequency,
        participation_x=gamma_x,
        participation_y=0.2 * number,
        participation_z=0.05 * number,
        effective_mass_x=gamma_x * gamma_x,
        effective_mass_y=(0.2 * number) ** 2,
        effective_mass_z=(0.05 * number) ** 2,
        total_mass_x=10.0,
        total_mass_y=10.0,
        total_mass_z=10.0,
        mass_percent_x=gamma_x * gamma_x * 10.0,
        mass_percent_y=(0.2 * number) ** 2 * 10.0,
        mass_percent_z=(0.05 * number) ** 2 * 10.0,
        max_displacement_x=float(np.max(np.abs(shape))),
        max_displacement_y=0.0,
        max_displacement_z=0.0,
        residual_norm=0.0,
        shape=shape,
    )


def _result() -> ModalAnalysisResult:
    modes = (
        _mode(1, 2.0, np.array([1.0, 0.0, 0.0]), 0.5),
        _mode(2, 3.0, np.array([0.0, 1.0, 0.0]), -0.75),
    )
    return ModalAnalysisResult(
        analysis_key=30,
        analysis_name="Modal_-1",
        combination=1,
        requested_modes=2,
        procedure="SubspaceIterations",
        convergence_criteria="EigenValue",
        requested_mass_matrix_type="Lumped",
        effective_mass_matrix_type="Consistent",
        dof_count=3,
        stiffness_nnz=3,
        mass_nnz=3,
        runtime_seconds=0.1,
        modes=modes,
    )


def _write_reference(path: Path, result: ModalAnalysisResult, *, frequency_scale: float = 1.0) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE ModalValues (
                Id INTEGER PRIMARY KEY, AnalysisKey INTEGER, Combination INTEGER, Step INTEGER,
                Wn REAL, Fn REAL, Tn REAL, GammaX REAL, GammaY REAL, GammaZ REAL,
                MassaX REAL, MassaY REAL, MassaZ REAL, MTotX REAL, MTotY REAL, MTotZ REAL,
                Mx_pcent REAL, My_pcent REAL, Mz_pcent REAL,
                UMaxX REAL, UMaxY REAL, UMaxZ REAL
            )"""
        )
        db.execute(
            """CREATE TABLE ModalShapeValues (
                Id INTEGER PRIMARY KEY, AnalysisKey INTEGER, Combination INTEGER,
                Step INTEGER, Dof REAL, Val REAL
            )"""
        )
        for mode in result.modes:
            # Deliberately reverse every C# mode sign. Gamma sign must not matter.
            db.execute(
                """INSERT INTO ModalValues VALUES (
                    NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )""",
                (
                    30, 1, mode.mode_number,
                    mode.angular_frequency * frequency_scale,
                    mode.frequency * frequency_scale,
                    mode.period / frequency_scale,
                    -mode.participation_x, -mode.participation_y, -mode.participation_z,
                    mode.effective_mass_x, mode.effective_mass_y, mode.effective_mass_z,
                    mode.total_mass_x, mode.total_mass_y, mode.total_mass_z,
                    mode.mass_percent_x, mode.mass_percent_y, mode.mass_percent_z,
                    mode.max_displacement_x, mode.max_displacement_y, mode.max_displacement_z,
                ),
            )
            for dof, value in enumerate(mode.shape):
                db.execute(
                    "INSERT INTO ModalShapeValues VALUES (NULL,?,?,?,?,?)",
                    (30, 1, mode.mode_number, dof, -float(value)),
                )


def test_discover_hrx_inputs_accepts_folder_and_wildcard(tmp_path: Path) -> None:
    (tmp_path / "b.hrx").write_text("x", encoding="utf-8")
    (tmp_path / "a.HRX").write_text("x", encoding="utf-8")
    (tmp_path / "a.Results").write_text("x", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.hrx").write_text("x", encoding="utf-8")

    from_folder = discover_hrx_inputs([str(tmp_path)])
    assert [item.name for item in from_folder] == ["a.HRX", "b.hrx"]

    from_wildcard = discover_hrx_inputs([str(tmp_path / "*")])
    assert [item.name for item in from_wildcard] == ["a.HRX", "b.hrx"]

    recursive = discover_hrx_inputs([str(tmp_path)], recursive=True)
    assert [item.name for item in recursive] == ["a.HRX", "b.hrx", "c.hrx"]


def test_modal_comparison_is_sign_invariant_and_compares_shapes(tmp_path: Path) -> None:
    result = _result()
    reference = tmp_path / "model.Results"
    _write_reference(reference, result)

    report = compare_modal_result_to_csharp(
        result,
        reference,
        tolerances=ModalComparisonTolerances(relative=1.0e-12, absolute=1.0e-12, minimum_mac=0.999999),
    )

    assert report["status"] == "PASS"
    assert report["minimum_diagonal_mac"] == pytest.approx(1.0)
    assert report["field_comparisons"]["GammaX"]["all_within_tolerance"]


def test_modal_comparison_fails_when_csharp_frequency_differs(tmp_path: Path) -> None:
    result = _result()
    reference = tmp_path / "model.Results"
    _write_reference(reference, result, frequency_scale=1.02)

    report = compare_modal_result_to_csharp(
        result,
        reference,
        tolerances=ModalComparisonTolerances(relative=1.0e-4, absolute=1.0e-8),
    )

    assert report["status"] == "FAIL"
    assert not report["field_comparisons"]["Fn"]["all_within_tolerance"]
    assert report["maximum_absolute_relative_frequency_error"] == pytest.approx(0.02 / 1.02)
