#!/usr/bin/env python3
"""Run the benchmark Vert -> Soil -> scour_1 -> LiveLoad_1 workflow and compare
every per-step value against the C# ``benchmark.Results`` SQLite database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

import numpy as np

from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession
from histra.solver.model_manager import ModelManager

SOIL_MATERIAL_KEY = 146
SOIL_INTERFACE_KEYS = [102, 104, 106, 108]
CSHARP_ANALYSES = {"Vert": 1, "scour_1": 23, "LiveLoad_1": 22}


def _inject_diagnostics(session: AnalysisSession, out_root: Path) -> None:
    """Patch the session's solve entry point to enable per-step diagnostics."""
    from histra.solver import session as session_module
    from histra.solver.diagnostics import DiagnosticOptions

    original = session_module.solve_static_nonlinear

    def wrapper(model, analysis, combination=1, **kwargs):
        name = str(getattr(analysis, "name", "analysis"))
        options = DiagnosticOptions(
            output_dir=out_root / name,
            capture_vectors=True,
            capture_element_states=True,
            spring_details=False,
            flush_each_event=True,
        )
        return original(model, analysis, combination, diagnostics=options, **kwargs)

    session_module.solve_static_nonlinear = wrapper


def _load_python_steps(diag_dir: Path) -> list[dict]:
    events = []
    path = diag_dir / "events.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        if payload.get("event") == "commit":
            events.append(payload)
    steps = []
    for event in events:
        snap = event.get("vector_snapshot")
        data = dict(np.load(diag_dir / snap)) if snap else {}
        steps.append({"event": event, "data": data})
    return steps


def _csharp_rows(db: sqlite3.Connection, analysis_key: int) -> dict[str, dict[int, dict]]:
    out: dict[str, dict[int, dict]] = {}
    reactions = {
        int(step): {"R1": r1, "R2": r2, "R3": r3}
        for step, r1, r2, r3 in db.execute(
            "SELECT Step,R1,R2,R3 FROM ReactionSumStates WHERE AnalysisKey=? AND Combination=1",
            (analysis_key,),
        )
    }
    out["reactions"] = reactions
    interfaces: dict[int, dict[int, np.ndarray]] = {}
    for parent, step, *u in db.execute(
        "SELECT ParentKey,Step,U1,U2,U3,U4,U5,U6,U7,U8,U9,U10,U11,U12 "
        "FROM InterfaceStates WHERE AnalysisKey=? AND Combination=1", (analysis_key,)
    ):
        interfaces.setdefault(int(step), {})[int(parent)] = np.asarray(u, dtype=float)
    out["interfaces"] = interfaces
    quads: dict[int, dict[int, np.ndarray]] = {}
    for parent, step, *rest in db.execute(
        "SELECT ParentKey,Step,U1,U2,U3,U4,U5,U6,U7,K "
        "FROM QuadStates WHERE AnalysisKey=? AND Combination=1", (analysis_key,)
    ):
        quads.setdefault(int(step), {})[int(parent)] = np.asarray(rest, dtype=float)
    out["quads"] = quads
    springs: dict[int, dict[tuple, tuple[float, float]]] = {}
    for parent, ptype, purpose, local, step, u, f in db.execute(
        "SELECT ParentKey,ParentType,SpringPurpose,IdLocal,Step,U,F "
        "FROM SpringStatesTmp WHERE AnalysisKey=? AND Combination=1", (analysis_key,)
    ):
        springs.setdefault(int(step), {})[
            (int(ptype), int(parent), int(purpose), int(local))
        ] = (float(u), float(f))
    out["springs"] = springs
    vectors = db.execute(
        "SELECT Dof,U FROM DynamicVectorsState WHERE AnalysisKey=? AND Combination=1 ORDER BY Dof",
        (analysis_key,),
    ).fetchall()
    out["final_u"] = np.asarray([row[1] for row in vectors], dtype=float)
    return out


def _spring_index(data: dict) -> dict[tuple, tuple[float, float]]:
    identities = data["spring_identities"]
    stress = data["spring_stress"]
    strain = data["spring_strain"]
    return {
        tuple(int(v) for v in ident): (float(strain[i]), float(stress[i]))
        for i, ident in enumerate(identities)
    }


def _compare_analysis(
    name: str, python_steps: list[dict], csharp: dict, report: dict
) -> None:
    entry: dict = {"analysis": name, "steps_python": len(python_steps)}
    # Reactions per committed step
    reaction_rows = []
    for record in python_steps:
        event = record["event"]
        step = int(event["step"])
        py = [event["reaction_x"], event["reaction_y"], event["reaction_z"]]
        cs_row = csharp["reactions"].get(step)
        cs = [cs_row["R1"], cs_row["R2"], cs_row["R3"]] if cs_row else None
        reaction_rows.append({
            "step": step,
            "python": list(py),
            "csharp": list(cs) if cs else None,
            "diff": [py[i] - cs[i] for i in range(3)] if cs else None,
        })
    entry["reactions"] = reaction_rows

    # Interface U per step
    iface_stats = []
    for record in python_steps:
        event = record["event"]
        step = int(event["step"])
        data = record["data"]
        if "interface_keys" not in data:
            continue
        cs_step = csharp["interfaces"].get(step, {})
        keys = data["interface_keys"]
        us = data["interface_u"]
        diffs = []
        for i, key in enumerate(keys):
            cs_u = cs_step.get(int(key))
            if cs_u is None:
                continue
            diffs.append((float(np.max(np.abs(us[i] - cs_u))), int(key)))
        if diffs:
            worst = max(diffs)
            iface_stats.append({
                "step": step, "max_abs_diff": worst[0], "worst_interface": worst[1],
                "rms": float(np.sqrt(np.mean([d[0] ** 2 for d in diffs]))),
            })
    entry["interface_u"] = iface_stats

    # Spring U/F per step
    spring_stats = []
    for record in python_steps:
        event = record["event"]
        step = int(event["step"])
        data = record["data"]
        if "spring_identities" not in data:
            continue
        py_springs = _spring_index(data)
        cs_springs = csharp["springs"].get(step, {})
        u_diffs, f_diffs = [], []
        for ident, (pu, pf) in py_springs.items():
            cs = cs_springs.get(ident)
            if cs is None:
                continue
            u_diffs.append((abs(pu - cs[0]), ident))
            f_diffs.append((abs(pf - cs[1]), ident))
        if u_diffs:
            wu = max(u_diffs)
            wf = max(f_diffs)
            spring_stats.append({
                "step": step,
                "max_u_diff": wu[0], "max_u_diff_spring": list(wu[1]),
                "max_f_diff": wf[0], "max_f_diff_spring": list(wf[1]),
                "rms_u": float(np.sqrt(np.mean([d[0] ** 2 for d in u_diffs]))),
                "rms_f": float(np.sqrt(np.mean([d[0] ** 2 for d in f_diffs]))),
            })
    entry["springs"] = spring_stats

    # Quad U per step
    quad_stats = []
    for record in python_steps:
        event = record["event"]
        step = int(event["step"])
        data = record["data"]
        if "quad_keys" not in data:
            continue
        cs_step = csharp["quads"].get(step, {})
        diffs = [
            (float(np.max(np.abs(data["quad_u"][i] - cs_step[int(key)][:7]))), int(key))
            for i, key in enumerate(data["quad_keys"]) if int(key) in cs_step
        ]
        if diffs:
            worst = max(diffs)
            quad_stats.append({
                "step": step, "max_abs_diff": worst[0], "worst_quad": worst[1],
            })
    entry["quad_u"] = quad_stats

    # Final global displacement
    if python_steps:
        py_u = np.asarray(python_steps[-1]["data"]["u"], dtype=float)
        cs_u = csharp["final_u"]
        if py_u.shape == cs_u.shape:
            diff = py_u - cs_u
            idx = int(np.argmax(np.abs(diff)))
            entry["final_displacement"] = {
                "max_abs": float(abs(diff[idx])), "max_abs_dof": idx,
                "rms": float(np.sqrt(np.mean(diff * diff))),
                "python_at_max": float(py_u[idx]), "csharp_at_max": float(cs_u[idx]),
                "relative_to_csharp_peak": float(abs(diff[idx]) / max(abs(cs_u))) if cs_u.size else 0.0,
            }
    report[name] = entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("my_model/benchmark_virgin.hrx"))
    parser.add_argument("--results", type=Path, default=Path("my_model/benchmark.Results"))
    parser.add_argument("--output", type=Path, default=Path("my_model/python-benchmark-comparison.json"))
    args = parser.parse_args()

    diag_root = args.output.parent / "benchmark-diagnostics"
    diag_root.mkdir(parents=True, exist_ok=True)

    model = load_model(args.model)
    prep = ModelManager.prepare_model(model)
    print(f"prepared: {prep.gdl} DOF, {prep.interfaces} interfaces", flush=True)

    session = AnalysisSession(model, on_log=lambda text: print(f"[session] {text}", flush=True))
    _inject_diagnostics(session, diag_root)

    executions = []
    for name in ("Vert", "scour_1", "LiveLoad_1"):
        if name == "scour_1":
            mutation = session.change_interface_materials(SOIL_INTERFACE_KEYS, SOIL_MATERIAL_KEY)
            print(f"[session] mutation: {mutation.interface_count} interfaces, "
                  f"{mutation.spring_count} springs rebuilt", flush=True)
        execution = session.run(name)
        print(f"[session] {name}: {execution.outcome.value}, "
              f"{len(execution.committed_steps)} steps, {execution.runtime_seconds:.1f}s", flush=True)
        executions.append(execution)

    report: dict = {"model": str(args.model), "csharp_results": str(args.results)}
    with sqlite3.connect(args.results) as db:
        for name, key in CSHARP_ANALYSES.items():
            diag_dir = diag_root / name
            python_steps = _load_python_steps(diag_dir)
            csharp = _load_python_rows(db, key)
            _compare_analysis(name, python_steps, csharp, report)

    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report: {args.output}", flush=True)
    return 0


def _load_python_rows(db, key):
    return _csharp_rows(db, key)


if __name__ == "__main__":
    raise SystemExit(main())
