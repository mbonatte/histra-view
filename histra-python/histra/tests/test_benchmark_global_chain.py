"""Global C# parity regression for the benchmark Vert -> Soil -> scour -> Live chain.

Runs the complete user workflow (``Vert``, soil mutation on the four foundation
interfaces, ``scour_1``, ``LiveLoad_1``) in one ``AnalysisSession`` and compares
the *full response* against the C# ``model.Results`` database: step counts,
per-step reaction sums, and final global/interface/spring/quad states.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.solver.model_manager import ModelManager
from histra.solver.session import AnalysisSession

ROOT = Path(__file__).resolve().parents[1]
HRX = ROOT / "model-benchmark" / "model.hrx"
RESULTS = ROOT / "model-benchmark" / "model.Results"
SOIL_MATERIAL_KEY = 146
SOIL_INTERFACE_KEYS = (102, 104, 106, 108)
ANALYSES = (("Vert", 1, 20), ("scour_1", 23, 20), ("LiveLoad_1", 22, 45))

pytestmark = pytest.mark.skipif(
    not HRX.exists() or not RESULTS.exists(),
    reason="model-benchmark assets are not installed",
)


@pytest.fixture(scope="module")
def chain():
    """Execute the full benchmark workflow once and keep per-analysis states."""
    from histra.solver.restart import _spring_targets

    model = load_model(HRX)
    prep = ModelManager.prepare_model(model)
    # This fixture deliberately reproduces the authored C# Work path.  Its
    # known unsafe commits are verified by the release harness, not by these
    # output-projection tests.
    session = AnalysisSession(model, equilibrium_policy="off", strategy_policy="off")

    def capture() -> dict:
        runtime = ModelManager.hysteretic_batch_for(model)
        if runtime is not None:
            runtime.sync_all_to_objects()
        return {
            "interfaces": {
                int(key): np.asarray(item.status.u[:12], dtype=float)
                for key, item in model.collections.interfaces.items()
            },
            "quads": {
                int(key): np.asarray(item.status.u[:7], dtype=float)
                for key, item in model.collections.quads.items()
            },
            "springs": {
                identity: (float(spring.u), float(spring.f))
                for identity, spring in _spring_targets(model)
                if spring is not None
            },
        }

    executions = {"Vert": session.run("Vert")}
    snapshots = {"Vert": capture()}
    session.change_interface_materials(SOIL_INTERFACE_KEYS, SOIL_MATERIAL_KEY)
    executions["scour_1"] = session.run("scour_1")
    snapshots["scour_1"] = capture()
    executions["LiveLoad_1"] = session.run("LiveLoad_1")
    snapshots["LiveLoad_1"] = capture()
    return {
        "model": model, "prep": prep, "session": session,
        "executions": executions, "snapshots": snapshots,
    }


def _final_step(db: sqlite3.Connection, table: str, analysis_key: int) -> int:
    return int(
        db.execute(
            f"SELECT MAX(Step) FROM {table} WHERE AnalysisKey=?", (analysis_key,)
        ).fetchone()[0]
    )


@pytest.mark.parametrize("name,analysis_key,steps", ANALYSES)
def test_chain_completes_csharp_step_counts(chain, name, analysis_key, steps):
    execution = chain["executions"][name]
    assert execution.completed
    assert [step.step for step in execution.committed_steps] == list(range(1, steps + 1))


@pytest.mark.parametrize("name,analysis_key,steps", ANALYSES)
def test_chain_per_step_reactions_match_csharp(chain, name, analysis_key, steps):
    with sqlite3.connect(RESULTS) as db:
        rows = db.execute(
            "SELECT Step,R1,R2,R3 FROM ReactionSumStates "
            "WHERE AnalysisKey=? AND Combination=1 ORDER BY Step",
            (analysis_key,),
        ).fetchall()
    assert len(rows) == steps + 1
    committed = chain["executions"][name].committed_steps
    for row, step in zip(rows[1:], committed):
        assert row[0] == step.step
        assert step.reaction_x == pytest.approx(row[1], abs=2.0e-3)
        assert step.reaction_y == pytest.approx(row[2], abs=2.0e-3)
        assert step.reaction_z == pytest.approx(row[3], abs=2.0e-3)


@pytest.mark.parametrize("name,analysis_key,steps", ANALYSES)
def test_chain_final_global_displacement_matches_csharp(
    chain, name, analysis_key, steps
):
    with sqlite3.connect(RESULTS) as db:
        csharp_u = np.asarray(
            [
                row[0]
                for row in db.execute(
                    "SELECT U FROM DynamicVectorsState "
                    "WHERE AnalysisKey=? AND Combination=1 AND Step=? ORDER BY Dof",
                    (analysis_key, steps),
                )
            ],
            dtype=float,
        )
    python_u = chain["executions"][name].committed_steps[-1].u
    assert python_u.shape == csharp_u.shape
    difference = python_u - csharp_u
    # C# stores the response vector in single precision.
    assert np.max(np.abs(difference)) <= 1.0e-6
    assert np.linalg.norm(difference) <= 1.0e-5


@pytest.mark.parametrize("name,analysis_key,steps", ANALYSES)
def test_chain_final_interface_and_quad_states_match_csharp(
    chain, name, analysis_key, steps
):
    snapshot = chain["snapshots"][name]
    with sqlite3.connect(RESULTS) as db:
        interfaces = {
            int(row[0]): np.asarray(row[1:], dtype=float)
            for row in db.execute(
                "SELECT ParentKey,U1,U2,U3,U4,U5,U6,U7,U8,U9,U10,U11,U12 "
                "FROM InterfaceStates WHERE AnalysisKey=? AND Combination=1 AND Step=?",
                (analysis_key, steps),
            )
        }
        quads = {
            int(row[0]): np.asarray(row[1:8], dtype=float)
            for row in db.execute(
                "SELECT ParentKey,U1,U2,U3,U4,U5,U6,U7 "
                "FROM QuadStates WHERE AnalysisKey=? AND Combination=1 AND Step=?",
                (analysis_key, steps),
            )
        }
    assert set(interfaces) == set(snapshot["interfaces"])
    assert set(quads) == set(snapshot["quads"])
    for key, csharp_u in interfaces.items():
        python_u = snapshot["interfaces"][key]
        assert np.max(np.abs(python_u - csharp_u)) <= 1.0e-6, f"interface {key}"
    for key, csharp_u in quads.items():
        python_u = snapshot["quads"][key]
        assert np.max(np.abs(python_u - csharp_u)) <= 1.0e-6, f"quad {key}"


@pytest.mark.parametrize("name,analysis_key,steps", ANALYSES)
def test_chain_final_spring_states_match_csharp(chain, name, analysis_key, steps):
    python_springs = chain["snapshots"][name]["springs"]
    with sqlite3.connect(RESULTS) as db:
        csharp = {
            (int(parent_type), int(parent), int(purpose), int(local)): (
                float(u), float(f)
            )
            for parent, parent_type, purpose, local, u, f in db.execute(
                "SELECT ParentKey,ParentType,SpringPurpose,IdLocal,U,F "
                "FROM SpringStates WHERE AnalysisKey=? AND Combination=1 AND Step=?",
                (analysis_key, steps),
            )
        }
    assert set(python_springs) == set(csharp)
    worst_u = worst_f = 0.0
    for identity, (pu, pf) in python_springs.items():
        cu, cf = csharp[identity]
        worst_u = max(worst_u, abs(pu - cu))
        worst_f = max(worst_f, abs(pf - cf))
    # C# persists spring forces in single precision.
    assert worst_u <= 1.0e-6
    assert worst_f <= 1.0e-3
