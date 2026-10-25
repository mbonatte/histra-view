#!/usr/bin/env python3
"""Run the C#-equivalent pier-Soil -> Vert phase for a batch of HRX models."""
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

SOIL_MATERIAL_KEY = 146
PIER_CENTRES_X = (502.0, 846.0)
PIER_FOUNDATION_LENGTH = 139.8


def _centre(interface) -> tuple[float, float, float]:
    return tuple(
        sum(getattr(vertex, axis) for vertex in interface.vint3d) / 4.0
        for axis in ("x", "y", "z")
    )


def pier_foundation_interface_keys(model) -> list[int]:
    half_length = PIER_FOUNDATION_LENGTH / 2.0
    return sorted(
        int(interface.key)
        for interface in model.collections.interfaces.values()
        if "Restraint" in (interface.parent_type_element1, interface.parent_type_element2)
        and any(abs(_centre(interface)[0] - pier_x) <= half_length + 1.0e-4 for pier_x in PIER_CENTRES_X)
    )


def _vector_comparison(python_u: np.ndarray, db: sqlite3.Connection) -> dict:
    rows = db.execute(
        "SELECT Dof,U FROM DynamicVectorsState WHERE AnalysisKey=1 AND Combination=1 ORDER BY Dof"
    ).fetchall()
    csharp_u = np.asarray([row[1] for row in rows], dtype=float)
    diff = np.asarray(python_u, dtype=float) - csharp_u
    index = int(np.argmax(np.abs(diff)))
    peak = float(np.max(np.abs(csharp_u)))
    return {
        "dofs": int(len(diff)), "max_abs": float(abs(diff[index])),
        "rms": float(np.sqrt(np.mean(diff * diff))), "max_abs_dof": index,
        "python_at_max_abs": float(python_u[index]), "csharp_at_max_abs": float(csharp_u[index]),
        "relative_to_csharp_peak": float(abs(diff[index]) / peak) if peak else 0.0,
    }


def _save_interface_snapshot(path: Path, model) -> None:
    interfaces = sorted(model.collections.interfaces.values(), key=lambda item: item.key)
    for item in interfaces:
        item.set_resisting_force()
    np.savez_compressed(
        path,
        keys=np.asarray([item.key for item in interfaces], dtype=np.int64),
        u=np.asarray([item.status.u for item in interfaces], dtype=np.float64),
        forces=np.asarray([item.status.forces for item in interfaces], dtype=np.float64),
        local_force=np.asarray([item.f for item in interfaces], dtype=np.float64),
        spring_u=np.asarray([
            [spring.u for spring in (item.trasv_1 + item.slid + item.slid_out_plan)]
            for item in interfaces
        ], dtype=np.float64),
        spring_f=np.asarray([
            [spring.get_force() for spring in (item.trasv_1 + item.slid + item.slid_out_plan)]
            for item in interfaces
        ], dtype=np.float64),
        centres=np.asarray([_centre(item) for item in interfaces], dtype=np.float64),
        material_keys=np.asarray([item.material_key for item in interfaces], dtype=np.int64),
        foundation=np.asarray([
            "Restraint" in (item.parent_type_element1, item.parent_type_element2) for item in interfaces
        ], dtype=bool),
    )


def run_case(path: Path, snapshot_dir: Path) -> dict:
    baseline = path.with_name(f"{path.stem}_copy_1.Results")
    started = time.perf_counter()
    model = load_model(path)
    prep_started = time.perf_counter()
    prep = ModelManager.prepare_model(model)
    soil_keys = pier_foundation_interface_keys(model)
    session = AnalysisSession(model)
    mutation = session.change_interface_materials(soil_keys, SOIL_MATERIAL_KEY, preserve_committed_state=False)
    execution = session.run("Vert")
    if not execution.completed:
        raise RuntimeError(f"{path}: Vert ended as {execution.outcome.value}")
    snapshot = snapshot_dir / f"{path.parent.name}_interfaces.npz"
    _save_interface_snapshot(snapshot, model)
    with sqlite3.connect(baseline) as db:
        csharp_reaction = np.asarray(db.execute(
            "SELECT R1,R2,R3 FROM ReactionSumStates WHERE AnalysisKey=1 AND Combination=1 ORDER BY Step DESC LIMIT 1"
        ).fetchone(), dtype=float)
        python_reaction = np.asarray([
            execution.committed_steps[-1].reaction_x,
            execution.committed_steps[-1].reaction_y,
            execution.committed_steps[-1].reaction_z,
        ])
        vector = _vector_comparison(execution.committed_steps[-1].u, db)
    return {
        "model": str(path), "csharp_baseline": str(baseline),
        "preprocessing_seconds": time.perf_counter() - prep_started - execution.runtime_seconds,
        "gdl": prep.gdl, "interfaces": prep.interfaces,
        "soil_interface_count": len(soil_keys), "soil_interface_keys": soil_keys,
        "soil_mutation_springs": mutation.spring_count,
        "vert": {"steps": len(execution.committed_steps), "runtime_seconds": execution.runtime_seconds,
                 "displacement": vector,
                 "reaction": {"python": python_reaction.tolist(), "csharp": csharp_reaction.tolist(),
                              "difference": (python_reaction - csharp_reaction).tolist()}},
        "interface_snapshot": str(snapshot), "total_seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("temp-six-jobs"))
    parser.add_argument("--output", type=Path, default=Path("temp-six-jobs/python-soil-vert-comparison.json"))
    parser.add_argument("--models", nargs="*", help="Optional random_NNN directories to run.")
    args = parser.parse_args()
    selected = set(args.models or [])
    paths = sorted(
        path for path in args.root.glob("random_*/*.hrx")
        if "_copy_" not in path.name and (not selected or path.parent.name in selected)
    )
    if not paths:
        raise SystemExit("No source HRX files selected.")
    snapshot_dir = args.output.parent / "python-soil-vert-snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for path in paths:
        print(f"[{path.parent.name}] Soil -> Vert", flush=True)
        result = run_case(path, snapshot_dir)
        print(f"[{path.parent.name}] complete: max |du|={result['vert']['displacement']['max_abs']:.6g}", flush=True)
        cases.append(result)
    args.output.write_text(json.dumps({"cases": cases}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
