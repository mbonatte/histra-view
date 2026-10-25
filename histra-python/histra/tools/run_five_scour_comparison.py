#!/usr/bin/env python3
"""Run the five-model Vert -> scour_1 -> scour_2 Python parity exercise.

The C# baseline is the ``random_NNN_copy_1.Results`` file created by the
desktop workflow.  The upstream-scour selection intentionally reproduces the
geometry recorded in the supplied C# log for pier_1:

* x = 502.0 mm, foundation length = 139.8 mm;
* y = 0.0 mm, foundation width = 342.4 mm;
* delta = 0.2 before ``scour_1`` and 0.4 before ``scour_2``.

It writes a compact JSON report containing final displacement-vector and
reaction comparisons for every analysis.  It neither alters the source HRX
files nor the C# result databases.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sqlite3
import time

import numpy as np

from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession
from histra.solver.model_manager import ModelManager


PIER_X = 502.0
PIER_LENGTH = 139.8
PIER_Y = 0.0
PIER_WIDTH = 342.4
SOIL_REMOVED_MATERIAL_KEY = 147
SOIL_MATERIAL_KEY = 146
PIER_CENTRES_X = (502.0, 846.0)


def _centre(interface) -> tuple[float, float, float]:
    vertices = interface.vint3d
    return tuple(sum(getattr(vertex, axis) for vertex in vertices) / 4.0 for axis in ("x", "y", "z"))


def upstream_interface_keys(model, delta: float) -> list[int]:
    """Resolve the C# pier_1 upstream-scour region after preprocessing."""
    left = PIER_X - PIER_LENGTH / 2.0
    right = PIER_X + PIER_LENGTH / 2.0
    upstream = PIER_Y - PIER_WIDTH / 2.0
    limit = upstream + PIER_WIDTH * float(delta)
    selected: list[int] = []
    for interface in model.collections.interfaces.values():
        if "Restraint" not in (interface.parent_type_element1, interface.parent_type_element2):
            continue
        x, y, _ = _centre(interface)
        if left - 1e-4 <= x <= right + 1e-4 and upstream - 1e-4 <= y <= limit + 1e-4:
            selected.append(int(interface.key))
    return sorted(selected)


def pier_foundation_interface_keys(model) -> list[int]:
    """Resolve every foundation restraint interface belonging to either pier.

    This is the pre-Vert C# stage: all pier restraint interfaces are changed
    from their parent definition to ``Soil``.  The two pier footprints have
    the same 139.8 mm foundation length; abutment restraint interfaces lie
    outside both x ranges and are deliberately excluded.
    """
    half_length = PIER_LENGTH / 2.0
    selected: list[int] = []
    for interface in model.collections.interfaces.values():
        if "Restraint" not in (interface.parent_type_element1, interface.parent_type_element2):
            continue
        x, _, _ = _centre(interface)
        if any(abs(x - pier_x) <= half_length + 1e-4 for pier_x in PIER_CENTRES_X):
            selected.append(int(interface.key))
    return sorted(selected)


def _vector_difference(python_u: np.ndarray, db: sqlite3.Connection, analysis_key: int) -> dict:
    rows = db.execute(
        "SELECT Dof,U FROM DynamicVectorsState WHERE AnalysisKey=? AND Combination=1 "
        "ORDER BY Dof", (analysis_key,)
    ).fetchall()
    csharp_u = np.asarray([row[1] for row in rows], dtype=float)
    dofs = np.asarray([row[0] for row in rows], dtype=int)
    if len(csharp_u) != len(python_u) or not np.array_equal(dofs, np.arange(len(python_u))):
        return {
            "comparable": False,
            "python_dofs": int(len(python_u)),
            "csharp_dofs": int(len(csharp_u)),
        }
    diff = np.asarray(python_u, dtype=float) - csharp_u
    index = int(np.argmax(np.abs(diff)))
    max_reference = float(np.max(np.abs(csharp_u)))
    return {
        "comparable": True,
        "dofs": int(len(diff)),
        "max_abs": float(abs(diff[index])),
        "rms": float(math.sqrt(float(np.mean(diff * diff)))),
        "max_abs_dof": index,
        "csharp_value_at_max_abs": float(csharp_u[index]),
        "python_value_at_max_abs": float(python_u[index]),
        "max_relative_to_peak_csharp_displacement": float(abs(diff[index]) / max_reference) if max_reference else 0.0,
    }


def _reaction_difference(python_step, db: sqlite3.Connection, analysis_key: int) -> dict:
    row = db.execute(
        "SELECT R1,R2,R3 FROM ReactionSumStates WHERE AnalysisKey=? AND Combination=1 "
        "ORDER BY Step DESC LIMIT 1", (analysis_key,)
    ).fetchone()
    python_reaction = np.asarray(
        [python_step.reaction_x, python_step.reaction_y, python_step.reaction_z], dtype=float
    )
    csharp_reaction = np.asarray(row, dtype=float)
    diff = python_reaction - csharp_reaction
    return {
        "python": python_reaction.tolist(),
        "csharp": csharp_reaction.tolist(),
        "component_difference": diff.tolist(),
        "max_abs": float(np.max(np.abs(diff))),
    }


def run_case(model_path: Path) -> dict:
    baseline = model_path.with_name(f"{model_path.stem}_copy_1.Results")
    started = time.perf_counter()
    print(f"[{model_path.parent.name}] loading", flush=True)
    model = load_model(model_path)
    prep_started = time.perf_counter()
    prep = ModelManager.prepare_model(model)
    prep_seconds = time.perf_counter() - prep_started
    pier_soil_keys = pier_foundation_interface_keys(model)
    scour_1_keys = upstream_interface_keys(model, 0.2)
    scour_2_keys = upstream_interface_keys(model, 0.4)
    print(
        f"[{model_path.parent.name}] prepared: {prep.gdl} DOF, {prep.interfaces} interfaces; "
        f"pier Soil/scour selections {len(pier_soil_keys)}/{len(scour_1_keys)}/{len(scour_2_keys)}",
        flush=True,
    )
    session = AnalysisSession(model, on_log=lambda text: print(f"[{model_path.parent.name}] {text}", flush=True))
    executions = []
    session.change_interface_materials(
        pier_soil_keys, SOIL_MATERIAL_KEY, preserve_committed_state=False
    )
    executions.append(session.run("Vert"))
    session.change_interface_materials(scour_1_keys, SOIL_REMOVED_MATERIAL_KEY)
    executions.append(session.run("scour_1"))
    session.change_interface_materials(scour_2_keys, SOIL_REMOVED_MATERIAL_KEY)
    executions.append(session.run("scour_2"))
    with sqlite3.connect(baseline) as db:
        comparisons = {}
        for execution in executions:
            comparisons[execution.analysis_name] = {
                "analysis_key": execution.analysis_key,
                "outcome": execution.outcome.value,
                "code": execution.code,
                "committed_steps": len(execution.committed_steps),
                "runtime_seconds": execution.runtime_seconds,
                "displacement": _vector_difference(
                    execution.committed_steps[-1].u, db, execution.analysis_key
                ),
                "reaction": _reaction_difference(
                    execution.committed_steps[-1], db, execution.analysis_key
                ),
            }
    result = {
        "model": str(model_path),
        "csharp_baseline": str(baseline),
        "preprocessing": {**prep.__dict__, "seconds": prep_seconds},
        "scour_selection": {
            "soil_material_key": SOIL_MATERIAL_KEY,
            "pier_soil_interface_keys": pier_soil_keys,
            "material_key": SOIL_REMOVED_MATERIAL_KEY,
            "scour_1_delta": 0.2,
            "scour_1_interface_keys": scour_1_keys,
            "scour_2_delta": 0.4,
            "scour_2_interface_keys": scour_2_keys,
        },
        "analyses": comparisons,
        "total_seconds": time.perf_counter() - started,
    }
    print(f"[{model_path.parent.name}] complete in {result['total_seconds']:.1f}s", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("temp-five-jobs"))
    parser.add_argument("--output", type=Path, default=Path("temp-five-jobs/python-scour-comparison.json"))
    parser.add_argument("--models", nargs="*", help="Optional random_NNN directory names.")
    args = parser.parse_args()
    selected = set(args.models or [])
    paths = sorted(
        path for path in args.root.glob("random_*/*.hrx")
        if "_copy_" not in path.name and (not selected or path.parent.name in selected)
    )
    if not paths:
        raise SystemExit("No source random_NNN HRX files selected.")
    report = {"cases": [run_case(path) for path in paths]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report written to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
