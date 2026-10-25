"""Run a reproducible, correctness-first nonlinear strategy matrix."""
from __future__ import annotations

import argparse
import copy
from importlib import metadata
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
from typing import Any, Mapping

import numpy as np

from histra.io import load_model
from histra.solver import AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.solver.output_projection import compute_model_point_displacements
from histra.tools.article_models_benchmark import _file_sha256


_STRATEGY_FIELDS = (
    "integration_method", "method", "adaptive_convergence_criteria",
    "pdelta_effect", "convergence_tolerance",
    "csharp_line_search_compatibility", "arc_length_procedure", "dr2",
    "is_max_arc_length_ray", "max_arc_length_ray", "update_dr2",
    "arc_length_max_cutbacks", "arc_length_cutback_factor",
    "arc_length_min_radius", "max_iterations", "line_search_max_iterations",
)
_STRATEGY_DEFAULTS: dict[str, Any] = {
    "csharp_line_search_compatibility": True,
    "arc_length_max_cutbacks": 0,
    "arc_length_cutback_factor": 0.5,
    "arc_length_min_radius": 0.0,
}


def _apply_candidate_overrides(
    chain: list[Any], candidate: Mapping[str, Any]
) -> None:
    target = chain[-1]
    per_analysis = candidate.get("analysis_overrides", {})
    if not isinstance(per_analysis, Mapping):
        raise ValueError("analysis_overrides must be a mapping by analysis name")
    for definition in chain:
        overrides: dict[str, Any] = {}
        if definition is target:
            overrides.update(
                (field, candidate[field])
                for field in _STRATEGY_FIELDS
                if field in candidate
            )
        named = per_analysis.get(str(definition.name), {})
        if not isinstance(named, Mapping):
            raise ValueError(
                f"analysis_overrides[{definition.name!r}] must be a mapping"
            )
        unknown = sorted(set(named) - set(_STRATEGY_FIELDS))
        if unknown:
            raise ValueError(
                f"Unsupported strategy override field(s) for {definition.name}: "
                f"{', '.join(unknown)}"
            )
        overrides.update(named)
        for field, value in overrides.items():
            setattr(definition, field, value)


def _peak_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


def _response_component(analysis: Any) -> int:
    direction = (
        float(getattr(analysis, "dir_x", 0.0)),
        float(getattr(analysis, "dir_y", 0.0)),
        float(getattr(analysis, "dir_z", 0.0)),
    )
    if not any(direction):
        raise ValueError(f"Analysis {analysis.name!r} has no output direction")
    return int(np.argmax(np.abs(np.asarray(direction, dtype=np.float64))))


def _model_point_component(
    model: Any, displacement: np.ndarray, step: int, master_point: int, component: int
) -> float:
    points = compute_model_point_displacements(model, displacement, step=step)
    point = next((item for item in points if int(item.parent_key) == master_point), None)
    if point is None:
        raise ValueError(
            f"model point {master_point} is unavailable for physical strategy response"
        )
    return float((point.ux, point.uy, point.uz)[component])


def _candidate_curve(
    model: Any, executions: list[Any], analysis: Any
) -> tuple[list[float], list[float]]:
    """Project the strategy response at the analysis master point.

    The internal integrator displacement is not a physical response field and
    can differ between LoadControl and ArcLength.  Preserve predecessor
    baselines exactly as the Article live-load comparison does.
    """

    execution = executions[-1]
    master_point = int(getattr(analysis, "master_point", -1))
    if master_point < 0:
        raise ValueError(f"Analysis {analysis.name!r} has no model-point response")
    component = _response_component(analysis)
    initial = execution.initial_step
    reaction0 = float((initial.reaction_x, initial.reaction_y, initial.reaction_z)[component] or 0.0)
    displacement0 = _model_point_component(
        model, initial.u, int(initial.step), master_point, component
    )
    if len(executions) > 1:
        predecessor = executions[-2]
        predecessor_step = predecessor.committed_steps[-1]
        reaction0 = float(
            (predecessor_step.reaction_x, predecessor_step.reaction_y, predecessor_step.reaction_z)[component]
            or 0.0
        )
        displacement0 = _model_point_component(
            model,
            predecessor_step.u,
            int(predecessor_step.step),
            master_point,
            component,
        )
    x: list[float] = [0.0]
    y: list[float] = [0.0]
    for step in execution.committed_steps:
        x.append(
            (_model_point_component(model, step.u, int(step.step), master_point, component) - displacement0)
            * 10.0
        )
        y.append(float((step.reaction_x, step.reaction_y, step.reaction_z)[component] or 0.0) - reaction0)
    return x, y


def read_csharp_reference_curve(
    results_path: Path, chain: list[Any]
) -> dict[str, list[float]]:
    """Read the same physical response from C# Results for one chain target."""

    analysis = chain[-1]
    analysis_key = int(analysis.key)
    master_point = int(getattr(analysis, "master_point", -1))
    if master_point < 0:
        raise ValueError(f"Analysis {analysis.name!r} has no model-point response")
    component = _response_component(analysis)
    reactions: dict[tuple[int, int], tuple[float, float, float]] = {}
    displacements: dict[tuple[int, int], tuple[float, float, float]] = {}
    with sqlite3.connect(results_path) as db:
        for key, step, r1, r2, r3 in db.execute(
            "SELECT AnalysisKey,Step,R1,R2,R3 FROM ReactionSumStates WHERE Combination=1"
        ):
            reactions[(int(key), int(step))] = (float(r1), float(r2), float(r3))
        for key, step, ux, uy, uz in db.execute(
            "SELECT AnalysisKey,Step,Ux,Uy,Uz FROM DisplModelPoints "
            "WHERE Combination=1 AND ParentKey=?",
            (master_point,),
        ):
            displacements[(int(key), int(step))] = (float(ux), float(uy), float(uz))
    reaction0 = 0.0
    displacement0 = 0.0
    if len(chain) > 1:
        predecessor_key = int(chain[-2].key)
        keys = [key for key in reactions if key[0] == predecessor_key and key in displacements]
        if not keys:
            raise ValueError("C# predecessor response is unavailable for baseline subtraction")
        baseline_key = max(keys, key=lambda item: item[1])
        reaction0 = reactions[baseline_key][component]
        displacement0 = displacements[baseline_key][component]
    target_keys = sorted(
        (key for key in reactions if key[0] == analysis_key and key[1] > 0 and key in displacements),
        key=lambda item: item[1],
    )
    if not target_keys:
        raise ValueError("C# target reaction/model-point response is unavailable")
    return {
        "displacement_mm": [0.0] + [
            (displacements[key][component] - displacement0) * 10.0 for key in target_keys
        ],
        "load_kn": [0.0] + [reactions[key][component] - reaction0 for key in target_keys],
    }


def run_candidate(
    hrx_path: Path,
    target: str,
    candidate: Mapping[str, Any],
    *,
    max_steps: int | None,
    setup_mutations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    model = load_model(hrx_path)
    preparation_started = time.perf_counter()
    ModelManager.prepare_model(model, force=True)
    preparation_seconds = time.perf_counter() - preparation_started
    session = AnalysisSession(
        model,
        equilibrium_policy="error",
        strategy_policy="off",
    )
    if setup_mutations:
        for mut in setup_mutations:
            selector = mut.get("selector")
            material_key = int(mut.get("material_key"))
            if selector == "pier_foundation":
                from histra.tools.run_six_soil_vert_comparison import pier_foundation_interface_keys

                keys = pier_foundation_interface_keys(model)
                session.change_interface_materials(keys, material_key, preserve_committed_state=False)
    chain = session.dependency_chain(target)
    _apply_candidate_overrides(chain, candidate)
    target_definition = chain[-1]
    started = time.perf_counter()
    executions = []
    for definition in chain:
        execution = session.run(
            definition,
            max_committed_steps=max_steps if definition is target_definition else None,
        )
        executions.append(execution)
        if not execution.completed:
            break
    runtime_seconds = time.perf_counter() - started
    target_execution = executions[-1]
    target_reached = int(target_execution.analysis_key) == int(target_definition.key)
    x, y = (
        _candidate_curve(model, executions, target_definition)
        if target_reached else ([], [])
    )
    steps = [step for execution in executions for step in execution.steps]
    terminal_step = next(
        (execution.steps[-1] for execution in reversed(executions) if execution.steps),
        None,
    )
    return {
        "id": str(candidate["id"]),
        "configuration": {
            "target": {
                field: getattr(
                    target_definition, field, _STRATEGY_DEFAULTS.get(field)
                )
                for field in _STRATEGY_FIELDS
            },
            "analysis_overrides": candidate.get("analysis_overrides", {}),
        },
        "completed": len(executions) == len(chain) and all(item.completed for item in executions),
        "range_covered": bool(
            target_reached
            and all(item.completed for item in executions[:-1])
            and (
                len(target_execution.committed_steps) >= max_steps
                if max_steps is not None else target_execution.completed
            )
        ),
        "outcomes": [
            {
                "analysis_key": int(execution.analysis_key),
                "analysis_name": execution.analysis_name,
                "outcome": execution.outcome.value,
                "committed_steps": len(execution.committed_steps),
            }
            for execution in executions
        ],
        "unsafe_steps": sum(step.equilibrium_ok is False for step in steps),
        "committed_steps": sum(len(item.committed_steps) for item in executions),
        "iterations": sum(int(step.get("iterations", 0)) for step in steps),
        # These counters are cumulative on the session's LinearSystem. Reading
        # only the last available step avoids double-counting dependency stages.
        "linear_solves": int(terminal_step.get("linear_solve_count", 0)) if terminal_step else 0,
        "factorizations": int(terminal_step.get("factorization_count", 0)) if terminal_step else 0,
        "preparation_seconds": preparation_seconds,
        "runtime_seconds": runtime_seconds,
        "peak_rss_bytes": _peak_rss_bytes(),
        "curve": {"displacement_mm": x, "load_kn": y},
    }


def aggregate_candidate_runs(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize repeated fresh-model observations without hiding a bad run.

    A median is useful for timing noise, but it must never convert an unsafe,
    incomplete, or response-drifting observation into a qualified strategy.
    The individual observations remain in the release artifact for audit.
    """

    if not runs:
        raise ValueError("at least one candidate observation is required")
    identifiers = {str(item["id"]) for item in runs}
    if len(identifiers) != 1:
        raise ValueError("all repeated observations must have the same candidate id")

    result = copy.deepcopy(runs[0])
    result["observations"] = copy.deepcopy(runs)
    result["repetitions"] = len(runs)
    result["completed"] = all(bool(item["completed"]) for item in runs)
    result["range_covered"] = all(
        bool(item.get("range_covered", item["completed"])) for item in runs
    )
    # Summing makes a single unsafe commit visible even where another
    # observation happened to be safe.
    result["unsafe_steps"] = sum(int(item["unsafe_steps"]) for item in runs)
    for field in (
        "committed_steps",
        "iterations",
        "linear_solves",
        "factorizations",
        "preparation_seconds",
        "runtime_seconds",
    ):
        result[field] = float(np.median([float(item[field]) for item in runs]))
    rss = [int(item["peak_rss_bytes"]) for item in runs if item["peak_rss_bytes"] is not None]
    result["peak_rss_bytes"] = max(rss) if rss else None
    return result


def _path_response_metrics(
    reference_displacement_mm: list[float],
    reference_load_kn: list[float],
    actual_displacement_mm: list[float],
    actual_load_kn: list[float],
) -> dict[str, Any]:
    """Compare signed load-displacement paths without discarding reversals.

    Article envelope checks intentionally normalize a known-sign monotonic
    live-load curve.  Solver-strategy qualification also covers cyclic and
    descending paths, where sorting absolute displacements destroys the
    physical branch identity.  This comparison retains signed coordinates and
    traversal order, then samples both paths on normalized cumulative path
    length.  It is independent of adaptive step counts while still rejecting
    reversed sign, wrong unloading branches, and incomplete displacement range.
    """
    ref_x = np.asarray(reference_displacement_mm, dtype=np.float64)
    ref_y = np.asarray(reference_load_kn, dtype=np.float64)
    act_x = np.asarray(actual_displacement_mm, dtype=np.float64)
    act_y = np.asarray(actual_load_kn, dtype=np.float64)
    if (
        len(ref_x) < 2
        or len(act_x) < 2
        or len(ref_x) != len(ref_y)
        or len(act_x) != len(act_y)
        or not np.all(np.isfinite(np.concatenate((ref_x, ref_y, act_x, act_y))))
    ):
        return {
            "available": False,
            "within_curve_tolerance": False,
            "reason": "each finite signed response path requires at least two rows",
        }

    x_scale = max(float(np.max(np.abs(ref_x))), float(np.ptp(ref_x)), 1.0e-12)
    y_scale = max(float(np.max(np.abs(ref_y))), 1.0e-12)

    def parameterize(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
        dx = np.diff(x) / x_scale
        dy = np.diff(y) / y_scale
        length = np.sqrt(dx * dx + dy * dy)
        s = np.concatenate((np.zeros(1, dtype=np.float64), np.cumsum(length)))
        return s, float(s[-1])

    ref_s, ref_length = parameterize(ref_x, ref_y)
    act_s, act_length = parameterize(act_x, act_y)
    if ref_length <= 1.0e-14 or act_length <= 1.0e-14:
        return {
            "available": False,
            "within_curve_tolerance": False,
            "reason": "response path has zero normalized length",
        }

    sample = np.linspace(0.0, 1.0, 401)
    ref_xs = np.interp(sample * ref_length, ref_s, ref_x)
    ref_ys = np.interp(sample * ref_length, ref_s, ref_y)
    act_xs = np.interp(sample * act_length, act_s, act_x)
    act_ys = np.interp(sample * act_length, act_s, act_y)

    ref_peak_index = int(np.argmax(np.abs(ref_ys)))
    act_peak_index = int(np.argmax(np.abs(act_ys)))
    ref_peak = float(ref_ys[ref_peak_index])
    act_peak = float(act_ys[act_peak_index])
    sign_match = (
        abs(ref_peak) <= 1.0e-12
        or abs(act_peak) > 1.0e-12 and np.sign(ref_peak) == np.sign(act_peak)
    )
    displacement_epsilon = max(1.0e-9, 1.0e-8 * x_scale)
    range_covered = bool(
        np.min(act_x) <= np.min(ref_x) + displacement_epsilon
        and np.max(act_x) >= np.max(ref_x) - displacement_epsilon
    )

    load_rmse = float(np.sqrt(np.mean((act_ys - ref_ys) ** 2)) / y_scale)
    displacement_rmse = float(np.sqrt(np.mean((act_xs - ref_xs) ** 2)) / x_scale)
    peak_error = abs(act_peak - ref_peak) / y_scale
    path_area_reference = float(np.trapezoid(ref_y, ref_x))
    path_area_actual = float(np.trapezoid(act_y, act_x))
    path_area_error = abs(path_area_actual - path_area_reference) / max(
        abs(path_area_reference), y_scale * x_scale, np.finfo(float).tiny
    )
    endpoint_displacement_error = abs(float(act_x[-1] - ref_x[-1])) / x_scale
    endpoint_load_error = abs(float(act_y[-1] - ref_y[-1])) / y_scale
    metrics = {
        "available": True,
        "comparison": "signed_path_arclength_v1",
        "range_covered": range_covered,
        "peak_sign_match": bool(sign_match),
        "normalized_load_path_rmse": load_rmse,
        "normalized_displacement_path_rmse": displacement_rmse,
        "peak_load_relative_error": peak_error,
        "path_area_relative_error": path_area_error,
        "endpoint_displacement_relative_error": endpoint_displacement_error,
        "endpoint_load_relative_error": endpoint_load_error,
        "reference_displacement_range_mm": [float(np.min(ref_x)), float(np.max(ref_x))],
        "actual_displacement_range_mm": [float(np.min(act_x)), float(np.max(act_x))],
    }
    metrics["within_curve_tolerance"] = bool(
        range_covered
        and sign_match
        and load_rmse <= 0.01
        and displacement_rmse <= 0.02
        and peak_error <= 0.01
        and path_area_error <= 0.02
        and endpoint_displacement_error <= 0.02
        and endpoint_load_error <= 0.01
    )
    return metrics


def _accepted_reference_evidence(value: Mapping[str, Any] | None) -> bool:
    """Require a traceable external acceptance record before ranking methods."""
    return bool(
        isinstance(value, Mapping)
        and value.get("accepted") is True
        and str(value.get("source", "")).strip()
        and str(value.get("source_sha256", "")).strip()
    )


def qualify_candidates(
    results: list[dict[str, Any]],
    baseline_id: str,
    *,
    reference_curve: Mapping[str, Any] | None = None,
    reference_evidence: Mapping[str, Any] | None = None,
) -> None:
    """Mark only safe candidates that match a traceable accepted response.

    The baseline candidate remains useful for configuration bookkeeping, but it
    is never silently promoted to an engineering reference.  A release matrix
    supplies the C#/accepted signed path and its provenance explicitly.
    """
    baseline = next((item for item in results if item["id"] == baseline_id), None)
    if baseline is None:
        raise ValueError(f"Baseline candidate {baseline_id!r} is absent from results.")
    if reference_curve is None:
        reference_curve = baseline["curve"]
    ref_x = list(reference_curve.get("displacement_mm", ()))
    ref_y = list(reference_curve.get("load_kn", ()))
    baseline_safe = bool(
        baseline.get("completed", False)
        and baseline.get("range_covered", baseline.get("completed", False))
        and int(baseline.get("unsafe_steps", 0)) == 0
    )
    evidence_accepted = _accepted_reference_evidence(reference_evidence)
    for result in results:
        observations = result.get("observations", [result])
        response_observations = [
            _path_response_metrics(
                ref_x,
                ref_y,
                list(observation["curve"].get("displacement_mm", ())),
                list(observation["curve"].get("load_kn", ())),
            )
            for observation in observations
        ]
        response = response_observations[0]
        result["response_vs_baseline"] = response
        result["response_observations"] = response_observations
        result["all_repetitions_response_accepted"] = all(
            item.get("within_curve_tolerance", False)
            for item in response_observations
        )
        result["baseline_safe"] = baseline_safe
        result["reference_evidence_accepted"] = evidence_accepted
        result["qualifies"] = bool(
            baseline_safe
            and evidence_accepted
            and result.get("range_covered", result["completed"])
            and result["unsafe_steps"] == 0
            and result["all_repetitions_response_accepted"]
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path, help="JSON matrix definition")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    definition = json.loads(args.matrix.read_text(encoding="utf-8"))
    hrx_path = Path(definition["hrx"]).resolve()
    candidates = list(definition["candidates"])
    if not candidates or len({item["id"] for item in candidates}) != len(candidates):
        parser.error("candidates must contain unique ids")
    repetitions = int(definition.get("repetitions", 1))
    if repetitions < 1:
        parser.error("repetitions must be at least one")
    setup_mutations = definition.get("setup_mutations")
    results = [
        aggregate_candidate_runs(
            [
                run_candidate(
                    hrx_path,
                    str(definition["target"]),
                    copy.deepcopy(candidate),
                    max_steps=definition.get("max_steps"),
                    setup_mutations=setup_mutations,
                )
                for _ in range(repetitions)
            ]
        )
        for candidate in candidates
    ]
    baseline_id = str(definition.get("baseline_id", candidates[0]["id"]))
    reference_curve = definition.get("reference_curve")
    reference_results_path = definition.get("reference_results")
    if reference_results_path is not None:
        reference_file = Path(reference_results_path).resolve()
        if not reference_file.is_file():
            parser.error(f"reference_results is not a file: {reference_file}")
        reference_model = load_model(hrx_path)
        reference_chain = AnalysisSession(
            reference_model, strategy_policy="off"
        ).dependency_chain(str(definition["target"]))
        reference_curve = read_csharp_reference_curve(reference_file, reference_chain)
    qualify_candidates(
        results,
        baseline_id,
        reference_curve=reference_curve,
        reference_evidence=definition.get("reference_evidence"),
    )
    qualifying = [item for item in results if item["qualifies"]]
    recommended = min(qualifying, key=lambda item: item["runtime_seconds"])["id"] if qualifying else None
    packages: dict[str, str] = {}
    for package in ("histra-python", "numpy", "scipy", "numba"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = "not-installed"
    payload = {
        "schema_version": 1,
        "scenario": definition.get("scenario"),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "packages": packages,
            "warmup_policy": definition.get("warmup_policy", "fresh model per candidate; no unrecorded warm-up"),
            "cache_state": definition.get("cache_state", "process-warm; JIT cache state not independently measured"),
            "repetitions": repetitions,
        },
        "hrx": {"path": str(hrx_path), "sha256": _file_sha256(hrx_path)},
        "target": definition["target"],
        "baseline_id": baseline_id,
        "reference_evidence": definition.get("reference_evidence"),
        "reference_results": (
            {"path": str(reference_file), "sha256": _file_sha256(reference_file)}
            if reference_results_path is not None
            else None
        ),
        "recommended_id": recommended,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if recommended is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
