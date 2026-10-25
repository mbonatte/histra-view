"""Compare deterministic Python parity snapshots with a C# HiStrA .Results DB."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sqlite3
from typing import Any

import numpy as np


def _summary(diff: np.ndarray, identities: np.ndarray | None = None) -> dict[str, Any]:
    values = np.asarray(diff, dtype=np.float64)
    if values.size == 0:
        return {"count": 0, "max_abs": 0.0, "rms": 0.0, "nonzero_gt_1e_12": 0}
    flat = np.abs(values).reshape(-1)
    index = int(np.argmax(flat))
    result: dict[str, Any] = {
        "count": int(values.size),
        "max_abs": float(flat[index]),
        "rms": float(np.sqrt(np.mean(values * values))),
        "nonzero_gt_1e_12": int(np.count_nonzero(flat > 1.0e-12)),
        "flat_index": index,
    }
    if identities is not None and identities.size:
        row = index if values.ndim == 1 else np.unravel_index(index, values.shape)[0]
        result["identity"] = np.asarray(identities[row]).astype(int).tolist()
    return result


def compare_state(snapshot: Path, results: Path, analysis: int, combination: int, step: int) -> dict[str, Any]:
    with np.load(snapshot) as py, sqlite3.connect(results) as db:
        report: dict[str, Any] = {
            "snapshot": str(snapshot),
            "results": str(results),
            "analysis": analysis,
            "combination": combination,
            "step": step,
        }
        spring_identity_key = "spring_identities" if "spring_identities" in py else "identities"
        spring_strain_key = "spring_strain" if "spring_strain" in py else "spring_u"
        spring_stress_key = "spring_stress" if "spring_stress" in py else "spring_f"
        if spring_identity_key in py:
            rows = db.execute(
                """SELECT ParentType, ParentKey, SpringPurpose, IdLocal, U, F, Phase
                   FROM SpringStatesTmp
                   WHERE AnalysisKey=? AND Combination=? AND Step=?
                   ORDER BY ParentType, ParentKey, SpringPurpose, IdLocal""",
                (analysis, combination, step),
            ).fetchall()
            csharp_ids = np.asarray([row[:4] for row in rows], dtype=np.int64)
            python_ids = np.asarray(py[spring_identity_key], dtype=np.int64)
            report["spring_identities_equal"] = bool(np.array_equal(python_ids, csharp_ids))
            report["spring_count_python"] = int(len(python_ids))
            report["spring_count_csharp"] = int(len(csharp_ids))
            if np.array_equal(python_ids, csharp_ids):
                report["spring_strain"] = _summary(
                    np.asarray(py[spring_strain_key]) - np.asarray([row[4] for row in rows]), python_ids
                )
                report["spring_stress"] = _summary(
                    np.asarray(py[spring_stress_key]) - np.asarray([row[5] for row in rows]), python_ids
                )
                phase_diff = np.asarray(py["spring_phase"], dtype=np.int64) - np.asarray(
                    [int(row[6]) for row in rows], dtype=np.int64
                )
                report["spring_phase"] = {
                    **_summary(phase_diff, python_ids),
                    "mismatch_count": int(np.count_nonzero(phase_diff)),
                }
        if "interface_keys" in py:
            rows = db.execute(
                """SELECT ParentKey,U1,U2,U3,U4,U5,U6,U7,U8,U9,U10,U11,U12
                   FROM InterfaceStates
                   WHERE AnalysisKey=? AND Combination=? AND Step=? ORDER BY ParentKey""",
                (analysis, combination, step),
            ).fetchall()
            keys = np.asarray([row[0] for row in rows], dtype=np.int64)
            py_keys = np.asarray(py["interface_keys"], dtype=np.int64)
            report["interface_keys_equal"] = bool(np.array_equal(keys, py_keys))
            if np.array_equal(keys, py_keys):
                report["interface_displacement"] = _summary(
                    np.asarray(py["interface_u"]) - np.asarray([row[1:] for row in rows]), keys[:, None]
                )
        if "quad_keys" in py:
            rows = db.execute(
                """SELECT ParentKey,U1,U2,U3,U4,U5,U6,U7 FROM QuadStates
                   WHERE AnalysisKey=? AND Combination=? AND Step=? ORDER BY ParentKey""",
                (analysis, combination, step),
            ).fetchall()
            keys = np.asarray([row[0] for row in rows], dtype=np.int64)
            py_keys = np.asarray(py["quad_keys"], dtype=np.int64)
            report["quad_keys_equal"] = bool(np.array_equal(keys, py_keys))
            if np.array_equal(keys, py_keys):
                report["quad_displacement"] = _summary(
                    np.asarray(py["quad_u"]) - np.asarray([row[1:] for row in rows]), keys[:, None]
                )
        return report


def export_history(results: Path, analysis: int, combination: int, output: Path) -> None:
    with sqlite3.connect(results) as db:
        rows = db.execute(
            """SELECT r.Step,r.R1,r.R2,r.R3,r.Eel,r.Ed,
                      COALESCE(MAX(ABS(d.Ux)),0),COALESCE(MAX(ABS(d.Uy)),0),COALESCE(MAX(ABS(d.Uz)),0)
               FROM ReactionSumStates r
               LEFT JOIN DisplModelPoints d
                 ON d.AnalysisKey=r.AnalysisKey AND d.Combination=r.Combination AND d.Step=r.Step
               WHERE r.AnalysisKey=? AND r.Combination=?
               GROUP BY r.Step,r.R1,r.R2,r.R3,r.Eel,r.Ed ORDER BY r.Step""",
            (analysis, combination),
        ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "reaction_x", "reaction_y", "reaction_z", "elastic_energy", "dissipated_energy", "max_abs_ux", "max_abs_uy", "max_abs_uz"])
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    state = sub.add_parser("state", help="compare one Python NPZ state to C#")
    state.add_argument("snapshot", type=Path)
    state.add_argument("results", type=Path)
    state.add_argument("analysis", type=int)
    state.add_argument("step", type=int)
    state.add_argument("--combination", type=int, default=1)
    state.add_argument("--output", type=Path)
    history = sub.add_parser("history", help="export C# reaction/displacement history")
    history.add_argument("results", type=Path)
    history.add_argument("analysis", type=int)
    history.add_argument("output", type=Path)
    history.add_argument("--combination", type=int, default=1)
    args = parser.parse_args()
    if args.command == "state":
        report = compare_state(args.snapshot, args.results, args.analysis, args.combination, args.step)
        text = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    else:
        export_history(args.results, args.analysis, args.combination, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
