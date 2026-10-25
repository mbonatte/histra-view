"""Interface mutation and in-memory analysis chaining benchmark for V1 release evidence (Gate C).

Runs the Vert -> change four interfaces -> scour_1 -> LiveLoad_1 chain in both
authored and strict modes, recording backend coverage, displacement and reaction parity,
committed-state history transfer, and equilibrium audit metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any

import numpy as np

from histra.io.hr_loader import load_model
from histra.solver.interface_material import change_interface_materials
from histra.solver.session import AnalysisSession
from histra.solver.backend_coverage import inspect_solver_backend
from histra.solver.outcomes import AnalysisExecution, AnalysisOutcome
from histra.tools.article_models_benchmark import (
    PARITY_DISPLACEMENT_ABSOLUTE_TOLERANCE_MM,
    PARITY_REACTION_ABSOLUTE_TOLERANCE,
    _apply_strict_strategy,
    _file_sha256,
    _live_load_curve_metrics,
    _python_phase_distribution,
    _project_python_history,
    _read_csharp_reference,
    compare_phase_checkpoint_at_physical_displacement,
    compute_parity_metrics,
)
from histra.solver.output_projection import compute_model_point_displacements

DEFAULT_CHAIN_DIR = Path(__file__).resolve().parents[1] / "model-chain"
DEFAULT_OUTPUT_DIR = Path("release-evidence/interface-chain-v1-rc")
AFFECTED_INTERFACES = (359, 360, 361, 362)


def _blocked_execution(analysis: Any, reason: str) -> AnalysisExecution:
    """Represent an unrun dependent stage without attempting an unsafe solve."""

    return AnalysisExecution(
        analysis_key=int(analysis.key),
        analysis_name=str(analysis.name),
        code=-10,
        steps=(),
        runtime_seconds=0.0,
        outcome=AnalysisOutcome.FAILED,
        message=f"blocked by incomplete predecessor: {reason}",
    )


def _analysis_configuration(analysis: Any) -> dict[str, Any]:
    """Serialize the numerical choices needed to reproduce a stage result."""

    return {
        "integration_method": str(getattr(analysis, "integration_method", "")),
        "method": str(getattr(analysis, "method", "")),
        "convergence_criterion": str(
            getattr(analysis, "adaptive_convergence_criteria", "")
        ),
        "convergence_tolerance": float(
            getattr(analysis, "convergence_tolerance", 0.0)
        ),
        "max_iterations": int(getattr(analysis, "max_iterations", 0)),
        "line_search_tolerance": float(
            getattr(analysis, "line_search_tolerance", 0.0)
        ),
        "line_search_max_iterations": int(
            getattr(analysis, "line_search_max_iterations", 0)
        ),
        "csharp_line_search_compatibility": bool(
            getattr(analysis, "csharp_line_search_compatibility", True)
        ),
        "arc_length_radius_squared": float(getattr(analysis, "dr2", 0.0)),
        "arc_length_max_cutbacks": int(
            getattr(analysis, "arc_length_max_cutbacks", 0)
        ),
    }


def _direction_index(analysis: Any) -> int:
    """Return the selected physical output direction for an analysis."""

    direction = np.asarray(
        (
            float(getattr(analysis, "dir_x", 0.0)),
            float(getattr(analysis, "dir_y", 0.0)),
            float(getattr(analysis, "dir_z", 0.0)),
        ),
        dtype=float,
    )
    if not np.any(direction):
        raise ValueError(
            f"Analysis {getattr(analysis, 'name', '')!r} has no physical output direction."
        )
    return int(np.argmax(np.abs(direction)))


def _terminal_response_metrics(
    model: Any,
    execution: Any,
    analysis: Any,
    csharp_reactions: dict[tuple[int, int], np.ndarray],
    csharp_displacements: dict[tuple[int, int, int], np.ndarray],
) -> dict[str, Any]:
    """Compare one terminal stage by its selected reaction and model point.

    Global generalized displacement vectors are not physical output fields and
    are especially branch-sensitive after a material mutation.  The V1 gate
    instead compares the reaction and the analysis master point in the
    configured direction, using the same units and limits as the Article
    harness.  Missing C# output is a failed comparison, never a silent pass.
    """

    committed = tuple(execution.committed_steps)
    analysis_key = int(getattr(analysis, "key"))
    master_point = int(getattr(analysis, "master_point", -10))
    component = _direction_index(analysis)
    if not committed or master_point < 0:
        return {
            "available": False,
            "within_tolerance": False,
            "reason": "analysis has no committed step or valid master point",
        }
    actual_step = committed[-1]
    reference_step = int(actual_step.step)
    if (
        (analysis_key, reference_step) not in csharp_reactions
        or (analysis_key, reference_step, master_point) not in csharp_displacements
    ):
        return {
            "available": False,
            "within_tolerance": False,
            "reason": (
                "C# reaction/model-point output is unavailable for the "
                f"committed terminal step {reference_step}"
            ),
        }
    actual_points = {
        int(point.parent_key): point
        for point in compute_model_point_displacements(
            model, actual_step.u, step=int(actual_step.step)
        )
    }
    point = actual_points.get(master_point)
    if point is None or actual_step.reaction_x is None or actual_step.reaction_y is None or actual_step.reaction_z is None:
        return {
            "available": False,
            "within_tolerance": False,
            "reason": "Python reaction/model-point output is unavailable for this stage",
        }
    reaction_reference = float(csharp_reactions[(analysis_key, reference_step)][component])
    displacement_reference_mm = float(
        csharp_displacements[(analysis_key, reference_step, master_point)][component] * 10.0
    )
    reaction_actual = (actual_step.reaction_x, actual_step.reaction_y, actual_step.reaction_z)[component]
    displacement_actual_mm = (point.ux, point.uy, point.uz)[component] * 10.0
    reaction_error = abs(float(reaction_actual) - reaction_reference)
    displacement_error = abs(float(displacement_actual_mm) - displacement_reference_mm)
    return {
        "available": True,
        "reference_step": int(reference_step),
        "actual_step": int(actual_step.step),
        "master_point": master_point,
        "direction": ("Ux", "Uy", "Uz")[component],
        "reaction_reference_kn": reaction_reference,
        "reaction_actual_kn": float(reaction_actual),
        "reaction_absolute_error_kn": reaction_error,
        "reaction_allowed_kn": PARITY_REACTION_ABSOLUTE_TOLERANCE,
        "displacement_reference_mm": displacement_reference_mm,
        "displacement_actual_mm": float(displacement_actual_mm),
        "displacement_absolute_error_mm": displacement_error,
        "displacement_allowed_mm": PARITY_DISPLACEMENT_ABSOLUTE_TOLERANCE_MM,
        "within_tolerance": bool(
            reaction_error <= PARITY_REACTION_ABSOLUTE_TOLERANCE
            and displacement_error <= PARITY_DISPLACEMENT_ABSOLUTE_TOLERANCE_MM
        ),
    }


def run_chain_benchmark(
    hrx_path: Path,
    results_path: Path | None,
    output_dir: Path,
    run_mode: str = "both",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    modes = ["authored", "strict"] if run_mode == "both" else [run_mode]

    report: dict[str, Any] = {
        "schema_version": 1,
        "harness_revision": 6,
        "hrx": {
            "path": str(hrx_path),
            "sha256": _file_sha256(hrx_path),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "affected_interfaces": list(AFFECTED_INTERFACES),
        "modes": {},
        "gate_c_pass": True,
    }

    for mode in modes:
        mode_result = _run_single_mode(hrx_path, results_path, mode)
        report["modes"][mode] = mode_result
        if not mode_result.get("passed", False):
            report["gate_c_pass"] = False

    output_file = output_dir / "chain_benchmark.json"
    with open(output_file, "w") as fp:
        json.dump(report, fp, indent=2)

    summary_file = output_dir / "chain_benchmark_summary.md"
    _write_markdown_summary(report, summary_file)

    return report


def _run_single_mode(
    hrx_path: Path,
    results_path: Path | None,
    mode: str,
) -> dict[str, Any]:
    t0 = time.time()
    model = load_model(hrx_path)
    from histra.solver.model_manager import ModelManager

    ModelManager.prepare_model(model, force=True)
    session = AnalysisSession(model, performance_policy="compiled")

    coverage_initial = inspect_solver_backend(model, ["Vert", "scour_1", "LiveLoad_1"])
    unmanaged_initial = coverage_initial.unmanaged_interfaces + coverage_initial.unmanaged_quads

    # Pre-Vert: mutate interfaces to 0 (soil)
    mutation_1_report = session.change_interface_materials(
        AFFECTED_INTERFACES, 0, preserve_committed_state=False
    )
    coverage_mut1 = inspect_solver_backend(model, ["Vert", "scour_1", "LiveLoad_1"])

    vert_def = model.collections.analyses[1]
    scour_def = model.collections.analyses[23]
    live_def = model.collections.analyses[22]

    if mode == "strict":
        _apply_strict_strategy(vert_def)
        _apply_strict_strategy(scour_def)
        # This is a diagnostic candidate: it is the only local ForceMoment
        # variant so far that reaches relaxation step 1.  The strategy warning
        # remains active because it has not preserved the reference response.
        scour_def.method = "ModifiedRegulaFalsiLineSearch"
        scour_def.max_iterations = 3000
        scour_def.als = False
        _apply_strict_strategy(live_def)
        live_def.max_iterations = 60

    # Execute Vert
    vert_res = session.run(vert_def)
    python_phase_counts = {int(vert_def.key): _python_phase_distribution(model)}

    mutation_2_report = None
    coverage_mut2 = None
    if not vert_res.completed:
        reason = f"{vert_res.analysis_key}:{vert_res.analysis_name} {vert_res.outcome}"
        scour_res = _blocked_execution(scour_def, reason)
        live_res = _blocked_execution(live_def, reason)
    else:
        # Post-Vert: mutate to 147 (scour) preserving committed history.
        mutation_2_report = session.change_interface_materials(
            AFFECTED_INTERFACES, 147, preserve_committed_state=True
        )
        coverage_mut2 = inspect_solver_backend(model, ["scour_1", "LiveLoad_1"])

        # Strict evidence must exercise the complete authored dependency chain.
        # A bounded one-step probe is useful while debugging but cannot establish
        # the release gate and must never be mistaken for a qualified run.
        scour_res = session.run(scour_def)
        python_phase_counts[int(scour_def.key)] = _python_phase_distribution(model)

        # Never attempt LiveLoad_1 after a failed predecessor: AnalysisSession
        # intentionally taints that state.  Record the blocked terminal state
        # in the release artifact instead of crashing the harness.
        if scour_res.completed:
            live_res = session.run(live_def)
            python_phase_counts[int(live_def.key)] = _python_phase_distribution(model)
        else:
            reason = f"{scour_res.analysis_key}:{scour_res.analysis_name} {scour_res.outcome}"
            live_res = _blocked_execution(live_def, reason)

    total_time = time.time() - t0
    expected_scour_steps = 5
    expected_live_steps = 38

    csharp_reactions: dict[tuple[int, int], np.ndarray] = {}
    csharp_displacements: dict[tuple[int, int, int], np.ndarray] = {}
    if results_path is not None and results_path.exists():
        csharp_reactions, csharp_displacements = _read_csharp_reference(
            results_path, (1, 23, 22)
        )
    executions = (vert_res, scour_res, live_res)
    python_reactions, python_displacements = _project_python_history(model, executions)
    exact_parity = compute_parity_metrics(
        csharp_reactions,
        python_reactions,
        csharp_displacements,
        python_displacements,
        expected_steps=[
            (analysis_key, step)
            for analysis_key, expected in ((1, 5), (23, expected_scour_steps), (22, expected_live_steps))
            for step in range(1, expected + 1)
        ],
        actual_steps=[
            (int(execution.analysis_key), int(step.step))
            for execution in executions
            for step in execution.committed_steps
        ],
    )
    live_curve = _live_load_curve_metrics(
        {
            "live_load_analyses": ("LiveLoad_1",),
            "master_point": int(live_def.master_point),
            "direction": ("Ux", "Uy", "Uz")[_direction_index(live_def)],
        },
        (vert_def, scour_def, live_def),
        csharp_reactions,
        python_reactions,
        csharp_displacements,
        python_displacements,
    )
    definitions = {int(item.key): item for item in (vert_def, scour_def, live_def)}
    strict_phase_checkpoints = (
        {
            int(execution.analysis_key): compare_phase_checkpoint_at_physical_displacement(
                results_path,
                execution,
                definitions[int(execution.analysis_key)],
                csharp_displacements,
                python_displacements,
                python_phase_counts.get(int(execution.analysis_key), {}),
            )
            for execution in executions
        }
        if mode == "strict" and results_path is not None and results_path.exists()
        else None
    )

    stage_results = []
    total_unsafe = 0
    all_passed = True

    for name, definition, exec_res, expected_steps in [
        ("Vert", vert_def, vert_res, 5),
        ("scour_1", scour_def, scour_res, expected_scour_steps),
        ("LiveLoad_1", live_def, live_res, expected_live_steps),
    ]:
        committed = len(exec_res.committed_steps)
        unsafe = sum(1 for s in exec_res.committed_steps if not s.equilibrium_ok)
        total_unsafe += unsafe

        authored_stepwise_diagnostic = _terminal_response_metrics(
            model,
            exec_res,
            definition,
            csharp_reactions,
            csharp_displacements,
        )
        if mode == "authored":
            response = live_curve if name == "LiveLoad_1" else authored_stepwise_diagnostic
            error_ok = bool(
                response.get("within_curve_tolerance", response.get("within_tolerance", False))
            )
            response_comparison = (
                "authored_curve" if name == "LiveLoad_1" else "authored_stepwise_parity"
            )
        elif name == "LiveLoad_1":
            # Strict runs may take a different sequence of equilibria.  The
            # physically comparable object is the load--displacement curve,
            # not the C# authored row with the same ordinal step.
            response = live_curve
            error_ok = bool(response.get("within_curve_tolerance", False))
            response_comparison = "strict_curve_response"
        else:
            response = {
                "available": False,
                "within_tolerance": None,
                "reason": (
                    "strict predecessor stages are checked for completion and safe "
                    "equilibrium; C# authored rows are not a comparable response path"
                ),
            }
            error_ok = True
            response_comparison = "not_applicable"
        stage_passed = (
            exec_res.completed
            and committed >= expected_steps
            and unsafe == 0
            and error_ok
        )
        if not stage_passed:
            all_passed = False

        terminal = exec_res.steps[-1] if exec_res.steps else None
        terminal_diagnostics = (
            {
                field: terminal.get(field)
                for field in (
                    "step",
                    "status",
                    "exit_code",
                    "iterations",
                    "convergence_criterion",
                    "convergence_tolerance",
                    "convergence_error",
                    "residual_norm",
                    "increment_norm",
                    "max_element_displacement",
                )
                if field in terminal
            }
            if terminal is not None
            else {"blocked_reason": exec_res.message}
        )

        stage_info = {
            "analysis_name": name,
            "analysis_key": int(definition.key),
            "configuration": _analysis_configuration(definition),
            "outcome": exec_res.outcome,
            "code": exec_res.code,
            "completed": exec_res.completed,
            "committed_steps": committed,
            "expected_steps": expected_steps,
            "unsafe_steps": unsafe,
            "response": response,
            "response_acceptable": error_ok,
            "response_comparison": response_comparison,
            "authored_stepwise_diagnostic": (
                authored_stepwise_diagnostic if mode == "strict" else None
            ),
            "strict_phase_checkpoint": (
                strict_phase_checkpoints.get(int(definition.key))
                if strict_phase_checkpoints is not None
                else None
            ),
            "terminal_diagnostics": terminal_diagnostics,
            "passed": stage_passed,
        }
        stage_results.append(stage_info)

    # Strict phase distributions are qualified only by physical-displacement
    # checkpoints.  C# authored solver-step ordinals are never used here.
    strict_phase_checkpoints_accepted = mode != "strict" or bool(
        strict_phase_checkpoints
    ) and all(item.get("accepted", False) for item in strict_phase_checkpoints.values())
    if not strict_phase_checkpoints_accepted:
        all_passed = False

    return {
        "mode": mode,
        "passed": all_passed,
        "total_time_seconds": total_time,
        "unmanaged_initial": unmanaged_initial,
        "unmanaged_after_mut1": coverage_mut1.unmanaged_interfaces + coverage_mut1.unmanaged_quads,
        "unmanaged_after_mut2": (
            coverage_mut2.unmanaged_interfaces + coverage_mut2.unmanaged_quads
            if coverage_mut2 is not None
            else None
        ),
        "total_unsafe_steps": total_unsafe,
        "exact_output_parity": exact_parity,
        "stepwise_parity_applicable": mode == "authored",
        "strict_phase_checkpoint_comparison": (
            strict_phase_checkpoints
        ),
        "live_load_curve": live_curve,
        "stages": stage_results,
    }


def _write_markdown_summary(report: dict[str, Any], path: Path) -> None:
    gate_status = "PASS" if report.get("gate_c_pass") else "FAIL (NOT RELEASE-READY)"
    lines = [
        "# Interface Material Chain Benchmark (Gate C)",
        "",
        f"**Gate C Release Status**: {gate_status}",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        "",
        "## Summary by Mode",
        "",
        "| Mode | Status | Time (s) | Vert Steps | Scour Steps | Live Steps | Unsafe Steps | Unmanaged Objects |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, data in report.get("modes", {}).items():
        stages = {s["analysis_name"]: s for s in data.get("stages", [])}
        v_steps = stages.get("Vert", {}).get("committed_steps", 0)
        s_steps = stages.get("scour_1", {}).get("committed_steps", 0)
        l_steps = stages.get("LiveLoad_1", {}).get("committed_steps", 0)
        status_str = "**PASS**" if data.get("passed") else "**FAIL**"
        unmanaged = max(
            value
            for value in (
                data.get("unmanaged_initial"),
                data.get("unmanaged_after_mut1"),
                data.get("unmanaged_after_mut2"),
            )
            if value is not None
        )
        lines.append(
            f"| {mode} | {status_str} | {data.get('total_time_seconds', 0.0):.2f} | "
            f"{v_steps} | {s_steps} | {l_steps} | {data.get('total_unsafe_steps', 0)} | {unmanaged} |"
        )

    lines.extend([
        "",
        "## Stage Details",
        "",
        "| Mode | Stage | Outcome | Committed / Expected | Unsafe | Response | Stage Status |",
        "|---|---|---|---:|---:|---|---|",
    ])
    for mode, data in report.get("modes", {}).items():
        for s in data.get("stages", []):
            response = s.get("response", {})
            if "normalized_curve_rmse" in response:
                response_str = (
                    f"curve RMSE={response.get('normalized_curve_rmse', float('nan')):.3e}; "
                    f"pass={bool(response.get('within_curve_tolerance', False))}"
                )
            elif response.get("available"):
                response_str = (
                    f"dR={response.get('reaction_absolute_error_kn', float('nan')):.3e} kN; "
                    f"du={response.get('displacement_absolute_error_mm', float('nan')):.3e} mm; "
                    f"pass={bool(response.get('within_tolerance', False))}"
                )
            else:
                response_str = f"n/a ({response.get('reason', 'unavailable')})"
            stage_st = "PASS" if s.get("passed") else "FAIL"
            lines.append(
                f"| {mode} | {s['analysis_name']} | {s['outcome']} | "
                f"{s['committed_steps']}/{s['expected_steps']} | {s['unsafe_steps']} | "
                f"{response_str} | {stage_st} |"
            )

    lines.append("")
    with open(path, "w") as fp:
        fp.write("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gate C interface chain benchmark.")
    parser.add_argument("--hrx", type=Path, default=DEFAULT_CHAIN_DIR / "model.hrx")
    parser.add_argument("--results", type=Path, default=DEFAULT_CHAIN_DIR / "model.Results")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-mode", choices=["authored", "strict", "both"], default="both")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Return success while collecting diagnostic evidence from a failing gate.",
    )
    args = parser.parse_args()

    report = run_chain_benchmark(args.hrx, args.results, args.output_dir, args.run_mode)
    print(f"Gate C pass: {report.get('gate_c_pass')}")
    return 0 if (report.get("gate_c_pass") or args.allow_incomplete) else 1


if __name__ == "__main__":
    sys.exit(main())
