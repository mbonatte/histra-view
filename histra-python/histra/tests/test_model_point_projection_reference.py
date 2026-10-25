from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

import pytest

from histra import PythonAnalysisRequest, run_python_solver_job

@dataclass(frozen=True)
class StepOutput:
    enabled: bool = True
    all_steps: bool = True
    step: int | None = None
    model_point_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ModalOutput:
    enabled: bool = False
    top_n: int = 3


@dataclass(frozen=True)
class Outputs:
    reactions: StepOutput = field(default_factory=StepOutput)
    displacements: StepOutput = field(default_factory=StepOutput)
    modal_contributions: ModalOutput = field(default_factory=ModalOutput)


def test_vert_outputs_match_authoritative_csharp_results() -> None:
    root = Path(__file__).resolve().parents[1] / "model-output"
    result = run_python_solver_job(
        root / "model.hrx",
        [PythonAnalysisRequest("Vert", Outputs(), 300.0)],
        timeout_seconds=300.0,
        equilibrium_policy="off",
        strategy_policy="off",
    ).analyses["Vert"].outputs

    with sqlite3.connect(root / "model.Results") as connection:
        connection.row_factory = sqlite3.Row
        expected_displacements = [
            dict(row) for row in connection.execute(
                "SELECT IdElement, ParentKey, Step, Ux, Uy, Uz "
                "FROM DisplModelPoints WHERE AnalysisKey=1 ORDER BY IdElement, Step"
            )
        ]
        expected_reactions = [
            dict(row) for row in connection.execute(
                "SELECT Step, R1, R2, R3 FROM ReactionSumStates "
                "WHERE AnalysisKey=1 ORDER BY Step"
            )
        ]

    assert len(result["displacements"]) == len(expected_displacements)
    for actual, expected in zip(result["displacements"], expected_displacements, strict=True):
        assert actual["IdElement"] == expected["IdElement"]
        assert actual["ParentKey"] == expected["ParentKey"]
        assert actual["Step"] == expected["Step"]
        for column in ("Ux", "Uy", "Uz"):
            assert actual[column] == pytest.approx(expected[column], abs=1e-9, rel=1e-5)

    assert len(result["reactions"]) == len(expected_reactions)
    for actual, expected in zip(result["reactions"], expected_reactions, strict=True):
        assert actual["Step"] == expected["Step"]
        for column in ("R1", "R2", "R3"):
            assert actual[column] == pytest.approx(expected[column], abs=1e-10, rel=1e-6)


def test_node_and_quad_model_points_match_csharp_for_reference_state() -> None:
    from histra import compute_model_point_displacements, load_model
    from histra.io.results_reader import read_global_displacements

    root = Path(__file__).resolve().parents[1] / "model-chain"
    model = load_model(root / "model.hrx")
    displacement = read_global_displacements(
        root / "model.Results", 1, 1, 5, model_or_hrx=model, size=model.gdl
    )
    actual = [
        row.as_runner_dict()
        for row in compute_model_point_displacements(model, displacement, step=5)
    ]
    with sqlite3.connect(root / "model.Results") as connection:
        connection.row_factory = sqlite3.Row
        expected = [
            dict(row) for row in connection.execute(
                "SELECT IdElement, ParentKey, Step, Ux, Uy, Uz FROM DisplModelPoints "
                "WHERE AnalysisKey=1 AND Step=5 ORDER BY IdElement, ParentKey"
            )
        ]
    actual.sort(key=lambda row: (row["IdElement"], row["ParentKey"]))
    assert len(actual) == len(expected) == 3
    for row, reference in zip(actual, expected, strict=True):
        assert (row["IdElement"], row["ParentKey"], row["Step"]) == (
            reference["IdElement"], reference["ParentKey"], reference["Step"]
        )
        for column in ("Ux", "Uy", "Uz"):
            assert row[column] == pytest.approx(reference[column], abs=3e-10, rel=2e-6)
