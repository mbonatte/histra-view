#!/usr/bin/env python3
"""Run Vert and a chained Live Load analysis from an unrun HRX model.

No C# ``.Results`` database is required. The solver runs Vert first, retains
its full committed constitutive state in memory, and then starts Live Load from
that state. Results are exported as human-readable CSV plus a JSON summary.

Example::

    python -m histra.tools.run_vert_live model.HRX \
        --live-analysis LiveLoad_1 --output-dir python-results
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from histra.io.hr_loader import load_model
from histra.postprocessing import compute_node_displacements
from histra.solver.solve import solve_static_nonlinear
from histra.solver.model_manager import ModelManager


def _resolve_analysis(model, selector: str | None, kind: str):
    analyses = model.collections.analyses
    if selector is not None:
        try:
            key = int(selector)
        except ValueError:
            matches = [a for a in analyses.values() if a.name.casefold() == selector.casefold()]
            if len(matches) != 1:
                raise ValueError(
                    f"Analysis name {selector!r} matched {len(matches)} analyses. "
                    "Use an exact name or numeric key."
                )
            return matches[0]
        if key not in analyses:
            raise ValueError(
                f"Analysis key {key} is absent. Available keys: {sorted(analyses)}"
            )
        return analyses[key]

    if kind == "vert":
        exact = [a for a in analyses.values() if a.name.casefold() == "vert"]
        if len(exact) == 1:
            return exact[0]
        candidates = [
            a for a in analyses.values()
            if "vert" in a.name.casefold() and int(a.initial_analysis_key) < 0
        ]
    else:
        preferred = [a for a in analyses.values() if a.name.casefold() == "liveload_1"]
        if len(preferred) == 1:
            return preferred[0]
        candidates = [a for a in analyses.values() if "live" in a.name.casefold()]

    if len(candidates) != 1:
        choices = ", ".join(f"{a.key}:{a.name}" for a in sorted(candidates, key=lambda x: x.key))
        raise ValueError(
            f"Could not select one {kind} analysis automatically. Candidates: "
            f"{choices or '<none>'}. Pass --{kind}-analysis."
        )
    return candidates[0]


def _finite(value: Any) -> Any:
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return value if math.isfinite(value) else None
    return value


def _initial_record(u: np.ndarray, reaction: tuple[float, float, float]) -> dict[str, Any]:
    rx, ry, rz = reaction
    return {
        "step": 0,
        "status": "INITIAL",
        "exit_code": 0,
        "u": np.asarray(u, dtype=float).copy(),
        "load_factor": 0.0,
        "displacement": 0.0,
        "iterations": 0,
        "convergence_error": 0.0,
        "residual_norm": 0.0,
        "increment_norm": 0.0,
        "reaction_x": rx,
        "reaction_y": ry,
        "reaction_z": rz,
        "balancing_reaction_x": -rx,
        "balancing_reaction_y": -ry,
        "balancing_reaction_z": -rz,
    }


def _write_step_csv(path: Path, analysis, records: Iterable[dict[str, Any]]) -> None:
    """Write step results with explicit reaction sign conventions.

    ``histra_reaction_sum_*`` maps directly to the software's ReactionSum
    R1/R2/R3 values. ``total_support_reaction_*`` is its negative and is the
    conventional support-on-structure reaction. ``incremental_support_*`` is
    measured from step 0 of the current analysis; for Live Load this removes
    the already-present Vert reaction.
    """
    rows = list(records)
    if not rows:
        return
    initial_support = np.asarray(
        [
            float(rows[0].get("balancing_reaction_x", -rows[0].get("reaction_x", 0.0))),
            float(rows[0].get("balancing_reaction_y", -rows[0].get("reaction_y", 0.0))),
            float(rows[0].get("balancing_reaction_z", -rows[0].get("reaction_z", 0.0))),
        ],
        dtype=float,
    )
    fields = [
        "analysis_key", "analysis_name", "step", "status",
        "convergence_result_code", "load_factor", "iterations",
        "monitored_displacement", "max_element_displacement",
        "max_element_type", "max_element_key",
        "convergence_criterion", "convergence_tolerance", "convergence_error",
        "residual_norm", "increment_norm",
        "equilibrium_checked", "equilibrium_ok", "equilibrium_force_ok",
        "equilibrium_residual_ok", "equilibrium_expected_reaction_x",
        "equilibrium_expected_reaction_y", "equilibrium_expected_reaction_z",
        "equilibrium_force_error_x", "equilibrium_force_error_y",
        "equilibrium_force_error_z", "equilibrium_force_error_norm",
        "equilibrium_force_error_max", "equilibrium_force_limit",
        "equilibrium_force_relative_error", "equilibrium_residual_norm",
        "equilibrium_residual_max", "equilibrium_residual_limit",
        "histra_reaction_sum_x", "histra_reaction_sum_y", "histra_reaction_sum_z",
        "histra_reaction_sum_magnitude",
        "total_support_reaction_x", "total_support_reaction_y",
        "total_support_reaction_z", "total_support_reaction_magnitude",
        "incremental_support_reaction_x", "incremental_support_reaction_y",
        "incremental_support_reaction_z", "incremental_support_reaction_magnitude",
    ]
    reaction_fields = [name for name in fields if "reaction" in name]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            has_committed_reaction = all(
                key in row for key in ("reaction_x", "reaction_y", "reaction_z")
            )
            if has_committed_reaction:
                reaction_sum = np.asarray(
                    [float(row["reaction_x"]), float(row["reaction_y"]), float(row["reaction_z"])],
                    dtype=float,
                )
                support = np.asarray(
                    [
                        float(row.get("balancing_reaction_x", -reaction_sum[0])),
                        float(row.get("balancing_reaction_y", -reaction_sum[1])),
                        float(row.get("balancing_reaction_z", -reaction_sum[2])),
                    ],
                    dtype=float,
                )
                incremental = support - initial_support
                reaction_values = {
                    "histra_reaction_sum_x": reaction_sum[0],
                    "histra_reaction_sum_y": reaction_sum[1],
                    "histra_reaction_sum_z": reaction_sum[2],
                    "histra_reaction_sum_magnitude": float(np.linalg.norm(reaction_sum)),
                    "total_support_reaction_x": support[0],
                    "total_support_reaction_y": support[1],
                    "total_support_reaction_z": support[2],
                    "total_support_reaction_magnitude": float(np.linalg.norm(support)),
                    "incremental_support_reaction_x": incremental[0],
                    "incremental_support_reaction_y": incremental[1],
                    "incremental_support_reaction_z": incremental[2],
                    "incremental_support_reaction_magnitude": float(np.linalg.norm(incremental)),
                }
            else:
                # Failed trial steps are rolled back and have no committed
                # reaction state. Blank cells prevent a false zero reaction.
                reaction_values = {name: "" for name in reaction_fields}

            writer.writerow(
                {
                    "analysis_key": analysis.key,
                    "analysis_name": analysis.name,
                    "step": row["step"],
                    "status": row["status"],
                    "convergence_result_code": row.get("exit_code", 0),
                    "load_factor": row.get("load_factor", 0.0),
                    "iterations": row.get("iterations", 0),
                    "monitored_displacement": row.get("displacement", 0.0),
                    "max_element_displacement": row.get("max_element_displacement", 0.0),
                    "max_element_type": row.get("max_element_type", ""),
                    "max_element_key": row.get("max_element_key", 0),
                    "convergence_criterion": row.get("convergence_criterion", ""),
                    "convergence_tolerance": row.get("convergence_tolerance", ""),
                    "convergence_error": row.get("convergence_error", 0.0),
                    "residual_norm": row.get("residual_norm", 0.0),
                    "increment_norm": row.get("increment_norm", 0.0),
                    "equilibrium_checked": row.get("equilibrium_checked", ""),
                    "equilibrium_ok": row.get("equilibrium_ok", ""),
                    "equilibrium_force_ok": row.get("equilibrium_force_ok", ""),
                    "equilibrium_residual_ok": row.get("equilibrium_residual_ok", ""),
                    "equilibrium_expected_reaction_x": row.get(
                        "equilibrium_expected_reaction_x", ""
                    ),
                    "equilibrium_expected_reaction_y": row.get(
                        "equilibrium_expected_reaction_y", ""
                    ),
                    "equilibrium_expected_reaction_z": row.get(
                        "equilibrium_expected_reaction_z", ""
                    ),
                    "equilibrium_force_error_x": row.get("equilibrium_force_error_x", ""),
                    "equilibrium_force_error_y": row.get("equilibrium_force_error_y", ""),
                    "equilibrium_force_error_z": row.get("equilibrium_force_error_z", ""),
                    "equilibrium_force_error_norm": row.get(
                        "equilibrium_force_error_norm", ""
                    ),
                    "equilibrium_force_error_max": row.get(
                        "equilibrium_force_error_max", ""
                    ),
                    "equilibrium_force_limit": row.get("equilibrium_force_limit", ""),
                    "equilibrium_force_relative_error": row.get(
                        "equilibrium_force_relative_error", ""
                    ),
                    "equilibrium_residual_norm": row.get(
                        "equilibrium_residual_norm", ""
                    ),
                    "equilibrium_residual_max": row.get(
                        "equilibrium_residual_max", ""
                    ),
                    "equilibrium_residual_limit": row.get(
                        "equilibrium_residual_limit", ""
                    ),
                    **reaction_values,
                }
            )

def _write_node_csv(path: Path, model, analysis, records: Iterable[dict[str, Any]]) -> None:
    fields = [
        "analysis_key", "analysis_name", "step", "node_key", "node_name",
        "x", "y", "z", "ux", "uy", "uz", "displacement_magnitude",
        "deformed_x", "deformed_y", "deformed_z", "contributing_quads",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            for node in compute_node_displacements(model, record["u"]):
                magnitude = math.sqrt(node.ux ** 2 + node.uy ** 2 + node.uz ** 2)
                writer.writerow(
                    {
                        "analysis_key": analysis.key,
                        "analysis_name": analysis.name,
                        "step": record["step"],
                        "node_key": node.node_key,
                        "node_name": node.node_name,
                        "x": node.x,
                        "y": node.y,
                        "z": node.z,
                        "ux": node.ux,
                        "uy": node.uy,
                        "uz": node.uz,
                        "displacement_magnitude": magnitude,
                        "deformed_x": node.deformed_x,
                        "deformed_y": node.deformed_y,
                        "deformed_z": node.deformed_z,
                        "contributing_quads": node.contributing_quads,
                    }
                )


def _write_final_node_csv(path: Path, model, analysis, record: dict[str, Any]) -> None:
    _write_node_csv(path, model, analysis, [record])


def _analysis_status(code: int, rows: list[dict[str, Any]], analysis) -> str:
    if code == 0:
        return "completed"
    if code == -3:
        failed = [row for row in rows if row["status"] == "FAILED"]
        if failed:
            measured = abs(float(failed[-1].get("max_element_displacement", 0.0)))
            limit = abs(float(getattr(analysis, "max_u", math.inf)))
            if measured >= limit:
                return "completed_at_configured_displacement_limit"
    return "failed"



def _write_output_readme(path: Path) -> None:
    path.write_text(
        """HiStrA Python standalone output

QUICK COMPARISON FILES
- vert_final_node_displacements.csv: final global X/Y/Z node translations after Vert.
- live_load_final_node_displacements.csv: final global X/Y/Z node translations after Live Load.
- vert_steps.csv and live_load_steps.csv: load factor, convergence values, maximum element displacement, and total reactions for every step.

NODE DISPLACEMENTS
- ux, uy, uz are global translations in the model X, Y, and Z directions.
- x, y, z are original node coordinates.
- deformed_x/y/z = original coordinate + displacement.
- displacement_magnitude = sqrt(ux^2 + uy^2 + uz^2).
- Coordinates and displacements use the HRX model length unit.
- Nodes connected to multiple Quads are averaged like the C# response output.

REACTIONS
- histra_reaction_sum_x/y/z are the software ReactionSum R1/R2/R3 values.
  Use these columns for a direct row-for-row comparison with HiStrA.
- total_support_reaction_x/y/z are the negatives of ReactionSum. They are the
  conventional support forces acting on the structure.
- incremental_support_reaction_x/y/z subtract the current analysis step-0
  reaction. In Live Load, this removes the inherited Vert/gravity reaction and
  shows only the additional reaction generated by Live Load.
- Reaction values use the HRX model force unit.

STEPS
- convergence_result_code is positive for a converged step and negative for a stopped/failed trial step; it is not the overall process exit code.
- monitored_displacement is the analysis graph/control output.
- max_element_displacement is the largest element displacement used by the model-wide maxU stop test.
- equilibrium_ok requires both global X/Y/Z force balance and the independent
  full active-DOF residual test. Force errors and limits are in kN.
- Exit code -12 means the selected HRX criterion passed but strict equilibrium
  safety rejected and rolled back the candidate before commit.
- Step 0 is the initial state.
- Vert step 0 is the virgin zero state.
- Live Load step 0 is the final committed Vert state.
- A Live Load convergence code -3 is classified as a configured displacement
  limit only when the failed trial's max_element_displacement reaches analysis.maxU.
- Failed/uncommitted attempts appear in *_steps.csv, but never in node displacement CSVs. Their reaction cells are blank because no trial reaction is committed.

PERFORMANCE
- run_summary.json records the active backend and the number of batched springs.
- numba_compiled_batch is the accelerated path installed by requirements.txt.
- The first process may spend a few seconds compiling kernels; later processes
  load them from Numba's cache.
- Set HISTRA_DISABLE_COMPILED_SPRINGS=1 only for scalar-path diagnostics.

The command does not read a .Results database. Vert and Live Load are solved
sequentially in one Python process, with the full committed constitutive state
passed in memory.
""",
        encoding="utf-8",
    )

def run_vert_live(
    hrx: Path,
    output_dir: Path,
    *,
    vert_selector: str | None = None,
    live_selector: str | None = None,
    combination: int = 1,
    echo_log: bool = True,
    equilibrium_policy: str = "error",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model = load_model(hrx)
    vert = copy.deepcopy(_resolve_analysis(model, vert_selector, "vert"))
    live = copy.deepcopy(_resolve_analysis(model, live_selector, "live"))
    if int(live.initial_analysis_key) != int(vert.key):
        raise ValueError(
            f"Live analysis {live.key}:{live.name} starts from analysis "
            f"{live.initial_analysis_key}, not selected Vert {vert.key}:{vert.name}."
        )

    log_path = output_dir / "solver.log"
    log_path.write_text("", encoding="utf-8")

    def log(message: str) -> None:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")
        if echo_log:
            print(message, flush=True)

    _write_output_readme(output_dir / "OUTPUT_README.txt")
    from histra.solver.warmup import warmup_compiled_backends
    warmup_compiled_backends()
    started = time.perf_counter()
    log(f"Model: {hrx.resolve()}")
    log(f"Running Vert {vert.key}:{vert.name} from virgin HRX state")
    vert_code, vert_rows = solve_static_nonlinear(
        model,
        vert,
        combination,
        on_log=lambda message: log(f"[Vert] {message}"),
        equilibrium_policy=equilibrium_policy,
    )
    vert_committed = [row for row in vert_rows if row["status"] == "OK"]
    runtime = ModelManager.hysteretic_batch_for(model)
    if runtime is not None:
        log(
            f"Performance backend: Numba compiled hysteretic batch "
            f"({len(runtime.springs)} springs)"
        )
    elif ModelManager._hysteretic_batch_error:
        log(
            "Performance backend: scalar Python fallback; compiled backend failed: "
            f"{ModelManager._hysteretic_batch_error}"
        )
    else:
        log("Performance backend: scalar Python fallback")
    if vert_code != 0 or not vert_committed:
        raise RuntimeError(
            f"Vert did not complete (code {vert_code}, committed steps "
            f"{len(vert_committed)}). Live Load was not started."
        )

    vert_initial = _initial_record(np.zeros(model.gdl), (0.0, 0.0, 0.0))
    vert_export_rows = [vert_initial, *vert_committed]
    vert_final = vert_committed[-1]

    # Persist the complete gravity result before starting the potentially long
    # ArcLength analysis. A user can inspect Vert output even if Live Load is
    # interrupted externally.
    _write_step_csv(output_dir / "vert_steps.csv", vert, vert_export_rows)
    _write_node_csv(
        output_dir / "vert_node_displacements.csv", model, vert, vert_export_rows
    )
    _write_final_node_csv(
        output_dir / "vert_final_node_displacements.csv", model, vert, vert_final
    )

    log(
        f"Running Live Load {live.key}:{live.name} from the in-memory committed "
        f"Vert step {vert_final['step']}"
    )
    live_code, live_rows = solve_static_nonlinear(
        model,
        live,
        combination,
        on_log=lambda message: log(f"[Live] {message}"),
        initial_displacement=np.asarray(vert_final["u"], dtype=float),
        restart_from_current_state=True,
        equilibrium_policy=equilibrium_policy,
    )
    live_committed = [row for row in live_rows if row["status"] == "OK"]
    baseline_reaction = (
        float(vert_final["reaction_x"]),
        float(vert_final["reaction_y"]),
        float(vert_final["reaction_z"]),
    )
    live_initial = _initial_record(np.asarray(vert_final["u"]), baseline_reaction)
    # The step table includes the uncommitted terminal attempt so its stop code
    # and max-element displacement remain visible. Node tables contain only
    # committed states because a failed trial is rolled back by design.
    live_step_rows = [live_initial, *live_rows]
    live_node_rows = [live_initial, *live_committed]

    _write_step_csv(output_dir / "live_load_steps.csv", live, live_step_rows)
    _write_node_csv(
        output_dir / "live_load_node_displacements.csv", model, live, live_node_rows
    )
    if live_committed:
        _write_final_node_csv(
            output_dir / "live_load_final_node_displacements.csv",
            model,
            live,
            live_committed[-1],
        )

    elapsed = time.perf_counter() - started
    live_status = _analysis_status(live_code, live_rows, live)
    summary = {
        "schema_version": 1,
        "model": str(hrx.resolve()),
        "units": {
            "displacements_and_coordinates": "HRX model length unit",
            "reactions": "HRX model force unit",
        },
        "reaction_sign_convention": {
            "histra_reaction_sum_x_y_z": (
                "HiStrA ReactionSum R1/R2/R3 convention for direct software comparison"
            ),
            "total_support_reaction_x_y_z": (
                "negative of ReactionSum; conventional support force acting on the structure"
            ),
            "incremental_support_reaction_x_y_z": (
                "total support reaction minus the current analysis step-0 support reaction"
            ),
        },
        "performance": {
            "backend": "numba_compiled_batch" if runtime is not None else "scalar_python",
            "batched_hysteretic_springs": len(runtime.springs) if runtime is not None else 0,
            "fallback_error": ModelManager._hysteretic_batch_error,
            "disable_environment_variable": "HISTRA_DISABLE_COMPILED_SPRINGS=1",
        },
        "equilibrium_policy": equilibrium_policy,
        "analyses": {
            "vert": {
                "key": int(vert.key),
                "name": vert.name,
                "completion_code": int(vert_code),
                "status": _analysis_status(vert_code, vert_rows, vert),
                "committed_steps": [int(row["step"]) for row in vert_committed],
                "final_histra_reaction_sum": {
                    axis: float(vert_final[f"reaction_{axis}"])
                    for axis in ("x", "y", "z")
                },
                "final_total_support_reaction": {
                    axis: float(vert_final[f"balancing_reaction_{axis}"])
                    for axis in ("x", "y", "z")
                },
            },
            "live_load": {
                "key": int(live.key),
                "name": live.name,
                "initial_analysis_key": int(live.initial_analysis_key),
                "completion_code": int(live_code),
                "status": live_status,
                "committed_steps": [int(row["step"]) for row in live_committed],
                "final_histra_reaction_sum": (
                    {
                        axis: float(live_committed[-1][f"reaction_{axis}"])
                        for axis in ("x", "y", "z")
                    }
                    if live_committed
                    else None
                ),
                "final_total_support_reaction": (
                    {
                        axis: float(live_committed[-1][f"balancing_reaction_{axis}"])
                        for axis in ("x", "y", "z")
                    }
                    if live_committed
                    else None
                ),
            },
        },
        "elapsed_seconds": elapsed,
        "files": {
            "vert_steps": "vert_steps.csv",
            "vert_nodes_all_steps": "vert_node_displacements.csv",
            "vert_nodes_final": "vert_final_node_displacements.csv",
            "live_steps": "live_load_steps.csv",
            "live_nodes_all_steps": "live_load_node_displacements.csv",
            "live_nodes_final": (
                "live_load_final_node_displacements.csv" if live_committed else None
            ),
            "solver_log": "solver.log",
        },
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hrx", type=Path, help="unrun HRX model")
    parser.add_argument("--output-dir", type=Path, default=Path("python-results"))
    parser.add_argument("--vert-analysis", help="Vert analysis key or exact name")
    parser.add_argument("--live-analysis", help="Live Load analysis key or exact name")
    parser.add_argument("--combination", type=int, default=1)
    parser.add_argument(
        "--equilibrium-policy",
        choices=("error", "warn", "off"),
        default="error",
        help=(
            "error rejects unbalanced candidate steps (default); warn preserves "
            "the C# path for diagnostics; off disables the safety audit"
        ),
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = run_vert_live(
            args.hrx,
            args.output_dir,
            vert_selector=args.vert_analysis,
            live_selector=args.live_analysis,
            combination=args.combination,
            echo_log=not args.quiet,
            equilibrium_policy=args.equilibrium_policy,
        )
    except (KeyError, ValueError, RuntimeError, NotImplementedError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    vert = summary["analyses"]["vert"]
    live = summary["analyses"]["live_load"]
    print(f"Vert: {vert['status']}, {len(vert['committed_steps'])} committed steps")
    print(f"Live Load: {live['status']}, {len(live['committed_steps'])} committed steps")
    print(f"Output: {args.output_dir.resolve()}")
    return 0 if live["status"].startswith("completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
