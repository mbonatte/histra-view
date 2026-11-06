"""Native high-performance simulation output architecture (Tiered Scientific Array Storage).

Provides two-tier output for HiStrA simulations:
- Tier 1: Summary Manifest (<case_id>.summary.json, < 100 KB) for instant notebook
  plotting and table generation.
- Tier 2: Dense Array Dataset (<case_id>.fields.npz or .h5, ~12-25 MB) separating
  static mesh topology from dynamic step fields and constitutive arrays.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping
import warnings

import numpy as np

import histra
from histra.model.model import Model
from histra.io.displacement_fields import build_displacement_fields
from histra.io.results_snapshot import capture_export_snapshot
from histra.io.spring_response import SPRING_RESPONSE_METADATA
from histra.io.model_point_summary import build_model_point_summary
from histra.solver.outcomes import AnalysisExecution, AnalysisOutcome


NATIVE_RESULTS_SCHEMA = "2.1.0"

NATIVE_UNITS = {
    "length": "cm", "displacement": "cm", "force": "kN",
    "moment": "kN*cm", "stress": "MPa", "rotation": "rad",
}


def select_pushover_force(rx, ry, rz):
    """Select the largest baseline-subtracted reaction; ties prefer Z, then X."""
    components = {"X": rx, "Y": ry, "Z": rz}
    delta = {axis: [abs(v - values[0]) for v in values] if len(values) else []
             for axis, values in components.items()}
    axis = max(("Z", "X", "Y"), key=lambda key: max(delta[key], default=0.0))
    if max(delta[axis], default=0.0) > 1e-4:
        return axis, delta[axis]
    return "resultant", [math.sqrt(x*x + y*y + z*z) for x, y, z in zip(rx, ry, rz)]


class ResultsWriter:
    """Exports simulation results into the 2-tier storage layout."""

    @staticmethod
    def export(
        model: Model,
        execution: AnalysisExecution,
        filepath: str | Path,
        format: str = "npz",  # "npz" | "h5" | "json" | "histra"
        tier: str = "all",     # "summary" | "fields" | "all"
        include_node_displacements: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Path]:
        """Exports simulation results into the 2-tier storage layout.

        Parameters
        ----------
        model : Model
            The HiStrA Model instance.
        execution : AnalysisExecution
            The execution record returned by AnalysisSession.run.
        filepath : str or Path
            Target base filepath. Suffixes (.npz, .h5, .summary.json, etc.)
            are stripped to form the stem.
        format : {"npz", "h5", "json", "histra", "results"}, default="npz"
            Array storage format. "npz" uses compressed NumPy; "h5" uses HDF5
            (falls back to .npz if h5py is not installed). "json" writes Tier 1 only.
            "histra" writes both tiers into a single compressed bundle.
            "results" writes captured native C# SQLite records (tier="all" only).
        tier : {"all", "summary", "fields"}, default="all"
            Which tiers to export.
        include_node_displacements : bool, default=True
            Whether to project and store full 3D node translations across steps.
        metadata : dict, optional
            Additional metadata merged into the summary manifest.

        Returns
        -------
        dict[str, Path]
            Created paths: {'summary': path, 'fields': path}, or {'bundle': path}.
        """
        format = str(format).lower().strip()
        tier = str(tier).lower().strip()
        if format in {"results", "result", "csharp"}:
            from histra.io.csharp_results_writer import export_csharp_executions

            if tier != "all":
                raise ValueError("Native .Results export requires tier='all'")
            return {"results": export_csharp_executions([execution], filepath)}
        if format == "histra":
            name = _output_stem(Path(filepath).name)
            path = ResultsWriter.export_bundle(
                model, {name: execution}, Path(filepath).parent / f"{name}.histra",
                tier=tier, include_node_displacements=include_node_displacements, metadata=metadata,
            )
            return {"bundle": path}
        if format not in {"npz", "h5", "json"}:
            raise ValueError(f"Unsupported result format: {format}")
        if tier not in {"all", "summary", "fields"}:
            raise ValueError(f"Unsupported result tier: {tier}")
        p = Path(filepath)
        output_dir = p.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        name = p.name
        for suffix in (
            ".summary.json",
            ".fields.npz",
            ".fields.h5",
            ".npz",
            ".h5",
            ".json",
        ):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

        summary_path = output_dir / f"{name}.summary.json"

        # Determine target fields format and path
        fmt = str(format).lower().strip()
        use_h5 = False
        if fmt == "h5":
            try:
                import h5py  # noqa: F401
                use_h5 = True
                fields_path = output_dir / f"{name}.fields.h5"
            except ImportError:
                warnings.warn(
                    "h5py is not installed; falling back to compressed NumPy (.npz) format.",
                    UserWarning,
                    stacklevel=2,
                )
                fields_path = output_dir / f"{name}.fields.npz"
        else:
            fields_path = output_dir / f"{name}.fields.npz"

        created: dict[str, Path] = {}
        tier_mode = str(tier).lower().strip()

        # Build Tier 1 Summary Manifest
        if tier_mode in ("all", "summary") or fmt == "json":
            summary_dict = _build_summary_manifest(
                model=model,
                execution=execution,
                case_id=name,
                extra_metadata=metadata,
            )
            summary_dict["files"] = {
                "fields": fields_path.name if tier_mode == "all" and fmt != "json" else None,
            }
            summary_dict["curve_only"] = summary_dict["files"]["fields"] is None
            with open(summary_path, "w", encoding="utf-8") as fp:
                json.dump(summary_dict, fp, indent=2)
            created["summary"] = summary_path

        # Build Tier 2 Dense Arrays
        if tier_mode in ("all", "fields") and fmt != "json":
            arrays = _build_dense_field_arrays(
                model=model,
                execution=execution,
                include_node_displacements=include_node_displacements,
            )
            if use_h5:
                _write_hdf5(fields_path, arrays)
            else:
                np.savez_compressed(fields_path, **arrays)
            created["fields"] = fields_path

        return created


    @staticmethod
    def export_bundle(model, executions, filepath, *, tier="all", include_node_displacements=True, metadata=None):
        """Write every selected execution into one verified .histra file."""
        from histra.io.bundle import HistraBundleWriter

        tier = str(tier).lower().strip()
        if tier not in {"all", "summary", "fields"}:
            raise ValueError(f"Unsupported result tier: {tier}")
        if not executions:
            raise ValueError("No executions selected for the bundle")
        path = Path(filepath)
        if path.suffix.lower() != ".histra":
            path = path.with_name(path.name + ".histra")
        with HistraBundleWriter(path, metadata=metadata) as writer:
            source = getattr(model, "source_path", None)
            model_sha = writer.add_model(source) if source and Path(source).is_file() else None
            for case_id, execution in executions.items():
                summary = _build_summary_manifest(model, execution, case_id, metadata) if tier != "fields" else None
                arrays = _build_dense_field_arrays(model, execution, include_node_displacements) if tier != "summary" else {}
                writer.add_case(case_id, summary, arrays, model_sha256=model_sha)
        return path


def _output_stem(name):
    for suffix in (".summary.json", ".fields.npz", ".fields.h5", ".histra", ".npz", ".h5", ".json"):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def _compute_sha256(filepath: str | Path) -> str | None:
    p = Path(filepath)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _build_summary_manifest(
    model: Model,
    execution: AnalysisExecution,
    case_id: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    steps = execution.output_steps

    model_src = getattr(model, "source_path", getattr(model, "filepath", None))
    sha256 = _compute_sha256(model_src) if model_src else None
    model_name = Path(model_src).stem if model_src else str(getattr(model, "name", case_id))

    # Step scalar histories
    step_indices = [int(s.step) for s in steps]
    displacements = [float(s.get("displacement", 0.0)) for s in steps]
    load_factors = [float(s.get("load_factor", 0.0)) for s in steps]
    rx = [float(s.get("reaction_x", 0.0)) for s in steps]
    ry = [float(s.get("reaction_y", 0.0)) for s in steps]
    rz = [float(s.get("reaction_z", 0.0)) for s in steps]

    forces_total = [math.sqrt(x*x + y*y + z*z) for x, y, z in zip(rx, ry, rz)]
    pushover_axis, forces_curve = select_pushover_force(rx, ry, rz)
    # Absolute reaction on the selected axis is distinct from its baseline change.
    reference_force = {"X": rx, "Y": ry, "Z": rz}.get(pushover_axis, forces_total)
    reference_force = [abs(value) for value in reference_force]

    f_max = max(forces_curve, default=0.0)
    idx_max = forces_curve.index(f_max) if f_max in forces_curve else 0
    d_at_f_max = displacements[idx_max] if idx_max < len(displacements) else 0.0
    d_max = max((abs(d) for d in displacements), default=0.0)

    # Ductility estimate (ratio of peak/ultimate displacement to approximate yield)
    ductility: float | None = None
    if f_max > 1e-6 and len(forces_curve) > 3:
        # 70% secant stiffness approximation for yield displacement
        f_70 = 0.70 * f_max
        d_y = None
        for i in range(1, len(forces_curve)):
            if forces_curve[i] >= f_70:
                d_y = abs(displacements[i])
                break
        if d_y is not None and d_y > 1e-6:
            ductility = round(d_max / d_y, 3)

    # Failure classification
    outcome = execution.outcome
    if outcome == AnalysisOutcome.COMPLETED_AT_DISPLACEMENT_LIMIT:
        classification = "displacement_limit"
    elif execution.completed:
        classification = "target_reached"
    elif outcome == AnalysisOutcome.CANCELLED:
        classification = "cancelled"
    elif outcome == AnalysisOutcome.NONCONVERGED:
        classification = "divergence"
    else:
        classification = str(outcome.value if outcome else "unknown")

    meta: dict[str, Any] = {
        "case_id": case_id,
        "schema_version": NATIVE_RESULTS_SCHEMA,
        "title": str(getattr(model, "title", model_name)),
        "model_name": model_name,
        "model_file": Path(model_src).name if model_src else "",
        "model_sha256": sha256,
        "analysis_key": int(execution.analysis_key),
        "analysis_name": str(execution.analysis_name),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": f"histra-python {getattr(histra, '__version__', '1.6.4')}",
        "units": NATIVE_UNITS.copy(),
        "spring_response": copy.deepcopy(SPRING_RESPONSE_METADATA),
    }
    if extra_metadata:
        meta.update(extra_metadata)
        meta["schema_version"] = NATIVE_RESULTS_SCHEMA
        meta["units"] = NATIVE_UNITS.copy()
        meta["spring_response"] = copy.deepcopy(SPRING_RESPONSE_METADATA)
        if meta.get("model_file"):
            meta["model_file"] = Path(meta["model_file"]).name

    manifest = {
        "metadata": meta,
        "pushover_axis": pushover_axis,
        "metrics": {
            "f_max_kN": float(f_max),
            "d_max_cm": float(d_max),
            "d_max_mm": float(d_max * 10.0),
            "d_at_f_max_cm": float(d_at_f_max),
            "d_at_f_max_mm": float(d_at_f_max * 10.0),
            "ductility": ductility,
            "total_steps": len(execution.steps),
            "committed_steps": len(execution.committed_steps),
            "runtime_seconds": float(execution.runtime_seconds),
            "exit_code": int(execution.code),
            "outcome": str(outcome.value if outcome else execution.code),
            "completed": bool(execution.completed),
            "failure_classification": classification,
        },
        "curve": {
            "step": step_indices,
            "displacement_cm": displacements,
            "displacement_mm": [d * 10.0 for d in displacements],
            "reference_force_kN": reference_force,
            "total_force_kN": forces_curve,
            "force_kN": forces_curve,
            "load_factor": load_factors,
            "elastic_energy": [s.get("elastic_energy") for s in steps],
            "dissipated_energy": [s.get("dissipated_energy") for s in steps],
        },
        "model_points": _model_point_output(model, execution),
        "reactions": {
            "reaction_x": rx,
            "reaction_y": ry,
            "reaction_z": rz,
            "reaction_mag": forces_total,
        },
    }
    if getattr(execution, "modal_result", None) is not None:
        manifest["modal"] = {
            "modal_values": execution.modal_result.modal_values_rows()
        }
    return manifest



def _model_point_output(model, execution):
    captured = getattr(execution, "model_point_output", None)
    if captured is not None:
        return copy.deepcopy(captured)
    definitions = getattr(model.collections, "analyses", {}) or {}
    return build_model_point_summary(model, execution.output_steps, definitions.get(execution.analysis_key))


def _build_dense_field_arrays(
    model: Model,
    execution: AnalysisExecution,
    include_node_displacements: bool = True,
) -> dict[str, np.ndarray]:
    """Extract and build all dense NumPy arrays for Tier 2 storage."""
    arrays: dict[str, np.ndarray] = {
        "metadata/schema_version": np.asarray(NATIVE_RESULTS_SCHEMA),
        "metadata/units": np.asarray(json.dumps(NATIVE_UNITS)),
        "metadata/spring_response": np.asarray(json.dumps(SPRING_RESPONSE_METADATA)),
    }

    snapshot = execution.export_snapshot
    arrays.update(snapshot if snapshot is not None else capture_export_snapshot(model))
    record_order = arrays.pop("_export/interface_record_order", None)
    sorted_interfaces = arrays["mesh/interface_keys"]

    # 2. Step Fields
    steps = execution.output_steps

    n_steps = len(steps)
    gdl = int(model.gdl)
    n_intf = len(sorted_interfaces)

    step_index = np.array([int(s.step) for s in steps], dtype=np.int32)
    load_factor = np.array([float(s.get("load_factor", 0.0)) for s in steps], dtype=np.float32)
    displacement = np.array([float(s.get("displacement", 0.0)) for s in steps], dtype=np.float32)
    reactions = np.array(
        [
            [
                float(s.get("reaction_x", 0.0)),
                float(s.get("reaction_y", 0.0)),
                float(s.get("reaction_z", 0.0)),
                0.0,
                0.0,
                0.0,
            ]
            for s in steps
        ],
        dtype=np.float32,
    )

    reactions = reactions.reshape(n_steps, 6)

    u_field = np.zeros((n_steps, gdl), dtype=np.float32)
    intf_res = np.zeros((n_steps, n_intf, 3), dtype=np.float32)
    intf_mom = np.zeros((n_steps, n_intf, 3), dtype=np.float32)

    for i, s in enumerate(steps):
        u_arr = s.get("u")
        if u_arr is not None:
            u_field[i, : len(u_arr)] = np.asarray(u_arr, dtype=np.float32)

        forces = s.get("interface_resultants")
        if forces is not None:
            intf_res[i] = np.asarray(forces, dtype=np.float32)[record_order] if record_order is not None else forces

        moments = s.get("interface_moments")
        if moments is not None:
            intf_mom[i] = np.asarray(moments, dtype=np.float32)[record_order] if record_order is not None else moments

    arrays["steps/step_index"] = step_index
    arrays["steps/load_factor"] = load_factor
    arrays["steps/displacement"] = displacement
    arrays["steps/reactions"] = reactions
    for name in ("elastic_energy", "dissipated_energy"):
        if steps and all(s.get(name) is not None for s in steps):
            arrays[f"steps/{name}"] = np.array([s[name] for s in steps], dtype=np.float64)
    arrays["fields/U"] = u_field
    arrays["fields/interface_resultants"] = intf_res
    arrays["fields/interface_moments"] = intf_mom

    quad_disps, node_disps = build_displacement_fields(
        model, steps, include_node_displacements=include_node_displacements,
        node_count=len(arrays["mesh/node_keys"]),
    )
    arrays["fields/quad_displacements"] = quad_disps
    if node_disps is not None and n_steps > 0:
        arrays["fields/node_displacements"] = node_disps

    if getattr(execution, "modal_result", None) is not None:
        arrays["modal_mode_shapes"] = np.asarray(execution.modal_result.mode_shapes.T, dtype=np.float32)
        arrays["modal_frequencies"] = np.asarray(execution.modal_result.frequencies, dtype=np.float32)
        arrays["modal_periods"] = np.asarray(execution.modal_result.periods, dtype=np.float32)

    return arrays


def _write_hdf5(filepath: Path, arrays: Mapping[str, np.ndarray]) -> None:
    import h5py

    with h5py.File(filepath, "w") as f:
        for key, arr in arrays.items():
            if arr.dtype.kind == "U":
                f.create_dataset(key, data=str(arr), dtype=h5py.string_dtype("utf-8"))
            else:
                f.create_dataset(key, data=arr, compression="gzip", compression_opts=4)


def write_session_manifest(model, results, filepath: Path):
    """Index every exported stage using paths relative to the bundle manifest."""
    cases = []
    for name, files in results.items():
        cases.append({
            "id": name,
            "analysis_name": name,
            "summary": files["summary"].name if "summary" in files else None,
            "fields": files["fields"].name if "fields" in files else None,
            "curve_only": "fields" not in files,
        })
    source = getattr(model, "source_path", None)
    if source and Path(source).is_file():
        import shutil

        target = filepath.parent / Path(source).name
        if target.resolve() != Path(source).resolve():
            if target.exists() and _compute_sha256(target) != _compute_sha256(source):
                raise FileExistsError(f"Bundle model path contains a different model: {target}")
            shutil.copyfile(source, target)
    manifest = {
        "schema_version": NATIVE_RESULTS_SCHEMA,
        "units": NATIVE_UNITS.copy(),
        "model": {"file": Path(source).name if source else None,
                  "sha256": _compute_sha256(source) if source else None},
        "cases": cases,
    }
    filepath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
