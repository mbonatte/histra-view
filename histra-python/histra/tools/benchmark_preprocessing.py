"""Benchmark Python PrepareModel against a C#-preprocessed HRX.

The reference HRX is loaded twice. One copy preserves the C# serialized
computational model; the second is force-regenerated from its geometry and
materials by Python. The command compares topology, afference, virgin spring
properties, and the assembled initial stiffness matrix.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import numpy as np

from histra.io.hr_loader import load_model
from histra.preprocessing import inspect_solver_readiness
from histra.solver.assembler import assemble_global_k
from histra.solver.model_manager import ModelManager
from histra.solver.solve import solve_static_nonlinear


def _interface_signature(model) -> list[tuple[Any, ...]]:
    return [
        (
            intf.parent_type_element1,
            intf.parent_element_key1,
            intf.parent_type_element2,
            intf.parent_element_key2,
            intf.face1,
            intf.face2,
            intf.nrow,
            intf.ncol,
        )
        for intf in model.collections.interfaces.values()
    ]


def _flatten(objects: Iterable[Any], field: str) -> np.ndarray:
    values: list[float] = []
    for obj in objects:
        value = getattr(obj, field)
        if isinstance(value, (list, tuple, np.ndarray)):
            values.extend(float(item) for item in value)
        else:
            values.append(float(value))
    return np.asarray(values, dtype=float)


def _error(reference: np.ndarray, generated: np.ndarray) -> dict[str, float]:
    reference = np.asarray(reference, dtype=float)
    generated = np.asarray(generated, dtype=float)
    delta = generated - reference
    if not delta.size:
        return {
            "max_absolute": 0.0,
            "max_relative_nonzero": 0.0,
            "relative_l2": 0.0,
        }

    # A raw element-wise relative error is meaningless for sparse matrices and
    # coefficient arrays containing structural zeros. Report the maximum only
    # where the reference is numerically significant relative to its own scale.
    reference_scale = float(np.max(np.abs(reference)))
    significant = np.abs(reference) > max(reference_scale * 1.0e-8, 1.0e-30)
    max_relative_nonzero = (
        float(np.max(np.abs(delta[significant]) / np.abs(reference[significant])))
        if np.any(significant)
        else 0.0
    )
    return {
        "max_absolute": float(np.max(np.abs(delta))),
        "max_relative_nonzero": max_relative_nonzero,
        "relative_l2": float(np.linalg.norm(delta) / max(np.linalg.norm(reference), 1.0e-30)),
    }


def _reset_initial(model) -> None:
    ModelManager.clear_hysteretic_batch()
    for quad in model.collections.quads.values():
        if quad.spring is not None:
            quad.spring.revert_to_start()
            quad.spring.revert_to_last_commit()
    for intf in model.collections.interfaces.values():
        for spring in (*intf.trasv_1, *intf.slid, *intf.slid_out_plan):
            spring.revert_to_start()
            spring.revert_to_last_commit()
        intf.status.init_from_interface(intf)
    ModelManager.compute_k(model, 0.0)


def compare_reference(path: Path) -> dict[str, Any]:
    reference = load_model(path)
    generated = load_model(path)
    signature = _interface_signature(reference)

    started = perf_counter()
    report = ModelManager.prepare_model(generated, force=True)
    elapsed = perf_counter() - started

    ref_aff = [
        (entry.gdl, entry.alfa)
        for intf in reference.collections.interfaces.values()
        for row in intf.aff
        for entry in row
    ]
    gen_aff = [
        (entry.gdl, entry.alfa)
        for intf in generated.collections.interfaces.values()
        for row in intf.aff
        for entry in row
    ]

    ref_h = [spring for intf in reference.collections.interfaces.values() for spring in intf.trasv_1]
    gen_h = [spring for intf in generated.collections.interfaces.values() for spring in intf.trasv_1]
    ref_s = [spring for intf in reference.collections.interfaces.values() for spring in intf.slid]
    gen_s = [spring for intf in generated.collections.interfaces.values() for spring in intf.slid]
    ref_o = [spring for intf in reference.collections.interfaces.values() for spring in intf.slid_out_plan]
    gen_o = [spring for intf in generated.collections.interfaces.values() for spring in intf.slid_out_plan]
    ref_q = [quad.spring for quad in reference.collections.quads.values()]
    gen_q = [quad.spring for quad in generated.collections.quads.values()]

    spring_errors: dict[str, dict[str, dict[str, float]]] = {}
    for name, left, right, fields in (
        ("transverse", ref_h, gen_h, ("k", "area", "fy", "kt", "ur", "alfau")),
        ("sliding", ref_s, gen_s, ("k", "area", "cohesion", "mu", "ur")),
        ("out_of_plane", ref_o, gen_o, ("k", "area", "cohesion", "mu", "ur")),
        # Cohesion and friction are deliberately excluded here: the supplied
        # locked HRX stores a post-analysis, normal-force-mutated Quad envelope.
        ("quad_diagonal", ref_q, gen_q, ("k", "area", "ur")),
    ):
        spring_errors[name] = {
            field: _error(_flatten(left, field), _flatten(right, field))
            for field in fields
        }

    _reset_initial(reference)
    k_reference = assemble_global_k(reference, alfa=0.0).toarray()
    _reset_initial(generated)
    k_generated = assemble_global_k(generated, alfa=0.0).toarray()
    k_error = _error(k_reference.ravel(), k_generated.ravel())
    ModelManager.clear_hysteretic_batch()

    return {
        "path": str(path.resolve()),
        "preparation_seconds": elapsed,
        "report": report.__dict__,
        "topology_exact": _interface_signature(generated) == signature,
        "afference": {
            "reference_entries": len(ref_aff),
            "generated_entries": len(gen_aff),
            "global_dof_sequence_exact": [item[0] for item in ref_aff] == [item[0] for item in gen_aff],
            "coefficient_error": _error(
                np.asarray([item[1] for item in ref_aff]),
                np.asarray([item[1] for item in gen_aff]),
            ),
        },
        "spring_errors": spring_errors,
        "initial_global_stiffness_error": k_error,
    }


def prepare_raw(path: Path, *, run_vert: bool) -> dict[str, Any]:
    model = load_model(path)
    before = inspect_solver_readiness(model)
    started = perf_counter()
    report = ModelManager.prepare_model(model)
    elapsed = perf_counter() - started
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "before_ready": before.is_ready,
        "preparation_seconds": elapsed,
        "report": report.__dict__,
        "after_ready": inspect_solver_readiness(model).is_ready,
    }
    if run_vert:
        analyses = [analysis for analysis in model.collections.analyses.values() if analysis.name == "Vert"]
        if len(analyses) != 1:
            raise RuntimeError(f"Expected one analysis named Vert, found {len(analyses)}.")
        started = perf_counter()
        code, rows = solve_static_nonlinear(
            model,
            copy.deepcopy(analyses[0]),
            1,
            auto_prepare=False,
        )
        result["vert"] = {
            "seconds": perf_counter() - started,
            "exit_code": code,
            "committed_steps": sum(row["status"] == "OK" for row in rows),
            "steps": [
                {
                    "step": row["step"],
                    "status": row["status"],
                    "iterations": row["iterations"],
                    "load_factor": row["load_factor"],
                    "reaction_x": row.get("reaction_x"),
                    "reaction_y": row.get("reaction_y"),
                    "reaction_z": row.get("reaction_z"),
                }
                for row in rows
            ],
        }
    ModelManager.clear_hysteretic_batch()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--reference",
        type=Path,
        default=root / "model-output" / "model.hrx",
        help="C#-preprocessed HRX used as the numerical oracle",
    )
    parser.add_argument("--raw", type=Path, help="Optional unlocked HRX to prepare")
    parser.add_argument("--run-vert", action="store_true", help="Run Vert after preparing --raw")
    parser.add_argument("--output", type=Path, default=Path("preprocessing_metrics.json"))
    args = parser.parse_args()

    metrics: dict[str, Any] = {"reference": compare_reference(args.reference)}
    if args.raw is not None:
        metrics["raw_model"] = prepare_raw(args.raw, run_vert=args.run_vert)
    args.output.write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
