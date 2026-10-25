"""Deterministic, opt-in nonlinear solver diagnostics.

Diagnostics are intentionally disabled by default.  When enabled they write a
JSON Lines event stream plus optional NPZ vector snapshots.  Stable database
identities are used for springs so the output can be joined directly to C#
``SpringStatesTmp`` rows.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np
import scipy.sparse as sp

from histra.solver.restart import _spring_targets
from histra.types.phase_enum import PhaseEnum


@dataclass(frozen=True)
class DiagnosticOptions:
    output_dir: Path | str
    capture_vectors: bool = False
    capture_matrices: bool = False
    capture_element_states: bool = False
    spring_details: bool = True
    flush_each_event: bool = True


class SolverDiagnostics:
    """Write deterministic analysis/step/iteration events."""

    def __init__(self, options: DiagnosticOptions, model: Any) -> None:
        self.options = options
        self.output_dir = Path(options.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.vector_dir = self.output_dir / "vectors"
        if options.capture_vectors or options.capture_matrices or options.capture_element_states:
            self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.output_dir / "events.jsonl"
        self._handle = self.events_path.open("w", encoding="utf-8", newline="\n")
        self._sequence = 0
        self._started = time.perf_counter()
        self._identity_by_object = {
            id(spring): tuple(int(v) for v in identity)
            for identity, spring in _spring_targets(model)
            if spring is not None
        }
        self._previous_spring_state: dict[tuple[int, int, int, int], tuple[float, float, int, float]] = {}
        self.timings: dict[str, float] = {}
        self.counts: dict[str, int] = {}

    def close(self) -> None:
        if self._handle.closed:
            return
        self.emit("diagnostics_closed", timings=self.timings, timing_counts=self.counts)
        self._handle.close()

    def __enter__(self) -> "SolverDiagnostics":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, dict):
            return {str(k): SolverDiagnostics._json_value(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [SolverDiagnostics._json_value(v) for v in value]
        return value

    def emit(self, event: str, **fields: Any) -> None:
        self._sequence += 1
        payload = {
            "sequence": self._sequence,
            "event": event,
            "elapsed_seconds": time.perf_counter() - self._started,
            **fields,
        }
        self._handle.write(
            json.dumps(self._json_value(payload), sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        if self.options.flush_each_event:
            self._handle.flush()

    def add_timing(self, name: str, seconds: float) -> None:
        self.timings[name] = self.timings.get(name, 0.0) + float(seconds)
        self.counts[name] = self.counts.get(name, 0) + 1

    @contextmanager
    def timed(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.add_timing(name, time.perf_counter() - started)

    @staticmethod
    def integrator_metrics(integrator: Any) -> dict[str, Any]:
        radius2 = getattr(integrator, "_arc_length2", None)
        radius = None
        if radius2 is not None:
            radius = math.sqrt(max(0.0, float(radius2)))
        delta_lambda = getattr(integrator, "_delta_lambda_step", None)
        incremental_load = float(getattr(integrator, "incr_mult", 0.0))
        step_increment = (
            float(delta_lambda) if delta_lambda is not None else incremental_load
        )
        predictor = step_increment
        current_load_factor = float(getattr(integrator, "mult", 0.0))
        return {
            "current_load_factor": current_load_factor,
            "previous_load_factor": current_load_factor - step_increment,
            "load_factor_increment": step_increment,
            "last_applied_load_correction": incremental_load,
            "arc_length_radius": radius,
            "arc_length_radius_squared": None if radius2 is None else float(radius2),
            "predictor_sign": 0 if predictor is None or float(predictor) == 0.0 else (1 if float(predictor) > 0.0 else -1),
            "delta_lambda_step": None if delta_lambda is None else float(delta_lambda),
        }

    @staticmethod
    def result_reason(result: int, test: Any, program: Any) -> str:
        if result >= 0:
            return "converged"
        if result == -1:
            return "continue_newton"
        if result == -2:
            return "maximum_iterations"
        if result == -3:
            if float(getattr(program, "max_u", 0.0)) >= float(getattr(test, "max_u", math.inf)):
                return "maximum_element_displacement"
            return "linear_system_failure"
        if result == -4:
            return "cancelled_or_nonfinite_or_external_stop"
        if result == -10:
            return "line_search_or_arc_length_failure"
        return f"solver_code_{result}"

    @staticmethod
    def _max_entry(values: np.ndarray) -> tuple[float, int]:
        if values.size == 0:
            return 0.0, -1
        index = int(np.argmax(np.abs(values)))
        return float(values[index]), index

    def vector_metrics(self, ls: Any) -> dict[str, Any]:
        max_r, max_r_i = self._max_entry(np.asarray(ls.b))
        max_x, max_x_i = self._max_entry(np.asarray(ls.x))
        return {
            "residual_norm": float(np.linalg.norm(ls.b)),
            "increment_norm": float(np.linalg.norm(ls.x)),
            "energy_norm": 0.5 * abs(float(np.dot(ls.x, ls.b))),
            "max_residual_value": max_r,
            "max_residual_dof": max_r_i,
            "max_correction_value": max_x,
            "max_correction_dof": max_x_i,
        }

    def _runtime_spring_rows(self, model: Any):
        from histra.solver.model_manager import ModelManager
        from histra.solver.hysteretic_runtime import (
            CKTANG, CTPHASE, CTSTRAIN, CTSTRESS,
            QKTANG, QTPHASE, QTSTRAIN, QTSTRESS,
        )

        runtime = ModelManager.hysteretic_batch_for(model)
        rows_by_identity: dict[
            tuple[int, int, int, int], tuple[tuple[int, int, int, int], float, float, int, float]
        ] = {}
        if runtime is not None:
            for index, spring in enumerate(runtime.springs):
                identity = self._identity_by_object.get(id(spring))
                if identity is None:
                    continue
                rows_by_identity[identity] = (
                    identity,
                    float(runtime.trial[index, 6]),
                    float(runtime.trial[index, 7]),
                    int(runtime.trial[index, 8]),
                    float(runtime.trial[index, 9]),
                )
            for index, spring in enumerate(runtime.coulomb_springs):
                identity = self._identity_by_object.get(id(spring))
                if identity is None:
                    continue
                row = runtime.coulomb_state[index]
                rows_by_identity[identity] = (
                    identity, float(row[CTSTRESS]), float(row[CTSTRAIN]),
                    int(row[CTPHASE]), float(row[CKTANG]),
                )
            for index, quad in enumerate(runtime.quad_records):
                identity = self._identity_by_object.get(id(quad.spring))
                if identity is None:
                    continue
                row = runtime.quad_state[index]
                rows_by_identity[identity] = (
                    identity, float(row[QTSTRESS]), float(row[QTSTRAIN]),
                    int(row[QTPHASE]), float(row[QKTANG]),
                )

        # Unsupported/unmanaged spring variants remain authoritative on their
        # Python objects. Include them so the diagnostic identity set exactly
        # matches the C# SpringStatesTmp key space rather than reporting only
        # the compiled subset.
        for identity, spring in _spring_targets(model):
            identity = tuple(int(value) for value in identity)
            if spring is None or identity in rows_by_identity:
                continue
            rows_by_identity[identity] = (
                identity,
                float(getattr(spring, "_tstress", getattr(spring, "f", 0.0))),
                float(getattr(spring, "_tstrain", getattr(spring, "u", 0.0))),
                int(getattr(spring, "t_phase", getattr(spring, "phase", 0))),
                float(getattr(spring, "k_tang", getattr(spring, "k", 0.0))),
            )
        return [rows_by_identity[key] for key in sorted(rows_by_identity)]

    def spring_metrics(self, model: Any) -> dict[str, Any]:
        if not self.options.spring_details:
            return {}
        rows = self._runtime_spring_rows(model)
        if not rows:
            return {"spring_count": 0}

        rupture = {
            int(PhaseEnum.Rupture), int(PhaseEnum.RuptureTraz),
            int(PhaseEnum.RuptureComp), int(PhaseEnum.Slip),
        }
        unloading = {
            int(PhaseEnum.Unload_t), int(PhaseEnum.Unload_c),
            int(PhaseEnum.Reload_t), int(PhaseEnum.Reload_c),
        }
        active = failed = unloaded = 0
        max_stress = max_tangent = max_state_change = -1.0
        max_stress_row = max_tangent_row = max_change_row = rows[0]
        phase_counts: dict[int, int] = {}
        for row in rows:
            identity, stress, strain, phase, tangent = row
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            if phase in rupture:
                failed += 1
            elif phase in unloading:
                unloaded += 1
            else:
                active += 1
            if abs(stress) > max_stress:
                max_stress, max_stress_row = abs(stress), row
            if abs(tangent) > max_tangent:
                max_tangent, max_tangent_row = abs(tangent), row
            previous = self._previous_spring_state.get(identity)
            if previous is None:
                change = 0.0
            else:
                change = max(
                    abs(stress - previous[0]),
                    abs(strain - previous[1]),
                    abs(float(phase - previous[2])),
                    abs(tangent - previous[3]),
                )
            if change > max_state_change:
                max_state_change, max_change_row = change, row
            self._previous_spring_state[identity] = (stress, strain, phase, tangent)

        def describe(row):
            identity, stress, strain, phase, tangent = row
            return {
                "identity": identity,
                "stress": stress,
                "strain": strain,
                "phase": phase,
                "tangent": tangent,
            }

        return {
            "spring_count": len(rows),
            "active_springs": active,
            "failed_springs": failed,
            "unloaded_springs": unloaded,
            "phase_counts": phase_counts,
            "max_abs_spring_stress": describe(max_stress_row),
            "max_abs_spring_tangent": describe(max_tangent_row),
            "max_spring_state_change": {**describe(max_change_row), "change": max_state_change},
        }

    def capture_state(
        self,
        *,
        label: str,
        step: int,
        iteration: int,
        program: Any,
        model: Any,
    ) -> str | None:
        if not (
            self.options.capture_vectors
            or self.options.capture_matrices
            or self.options.capture_element_states
        ):
            return None
        # A failed ArcLength step can retry the same ``step``/``iteration``
        # coordinates after an initial-tangent retry and several cutbacks.
        # The prior filename silently overwrote those decisive trial vectors.
        # ``emit`` will use the next sequence number, so include it here to
        # make the artifact identity stable and unique without changing the
        # event schema that references this path.
        event_sequence = self._sequence + 1
        path = self.vector_dir / (
            f"event_{event_sequence:06d}_step_{step:05d}_iter_{iteration:05d}_{label}.npz"
        )
        values: dict[str, Any] = {}
        if self.options.capture_vectors:
            values.update({
                "u": np.asarray(program.u, dtype=np.float64),
                "du": np.asarray(program.ls.x, dtype=np.float64),
                "residual": np.asarray(program.ls.b, dtype=np.float64),
            })
            from histra.solver.model_manager import ModelManager
            if ModelManager._fext is not None:
                values["external_load"] = np.asarray(ModelManager._fext, dtype=np.float64)
            if ModelManager._ptarget is not None:
                values["target_load"] = np.asarray(ModelManager._ptarget, dtype=np.float64)
            runtime = ModelManager.hysteretic_batch_for(model)
            if runtime is not None:
                values["internal_force"] = np.asarray(runtime._global_resisting_force, dtype=np.float64)
        if self.options.capture_matrices:
            k = sp.csc_matrix(program.ls.k)
            values.update({
                "k_data": k.data,
                "k_indices": k.indices,
                "k_indptr": k.indptr,
                "k_shape": np.asarray(k.shape, dtype=np.int64),
            })
        if self.options.capture_element_states:
            spring_rows = sorted(self._runtime_spring_rows(model), key=lambda row: row[0])
            if spring_rows:
                values.update({
                    "spring_identities": np.asarray([row[0] for row in spring_rows], dtype=np.int64),
                    "spring_stress": np.asarray([row[1] for row in spring_rows], dtype=np.float64),
                    "spring_strain": np.asarray([row[2] for row in spring_rows], dtype=np.float64),
                    "spring_phase": np.asarray([row[3] for row in spring_rows], dtype=np.int32),
                    "spring_tangent": np.asarray([row[4] for row in spring_rows], dtype=np.float64),
                })
            from histra.solver.model_manager import ModelManager
            runtime = ModelManager.hysteretic_batch_for(model)
            managed_interfaces = {} if runtime is None else {
                int(record.interface.key): np.asarray(runtime._local_u[index], dtype=np.float64)
                for index, record in enumerate(runtime.records)
            }
            managed_quads = {} if runtime is None else {
                int(quad.key): np.asarray(runtime._quad_local_u[index], dtype=np.float64)
                for index, quad in enumerate(runtime.quad_records)
            }
            interface_rows = []
            for key, interface in sorted(model.collections.interfaces.items()):
                local = managed_interfaces.get(int(key))
                if local is None:
                    local = np.asarray(interface.status.u, dtype=np.float64)
                interface_rows.append((int(key), local[:12]))
            quad_rows = []
            for key, quad in sorted(model.collections.quads.items()):
                local = managed_quads.get(int(key))
                if local is None:
                    local = np.asarray(quad.status.u, dtype=np.float64)
                quad_rows.append((int(key), local[:7]))
            if interface_rows:
                values["interface_keys"] = np.asarray([row[0] for row in interface_rows], dtype=np.int64)
                values["interface_u"] = np.stack([row[1] for row in interface_rows]).astype(np.float64)
            if quad_rows:
                values["quad_keys"] = np.asarray([row[0] for row in quad_rows], dtype=np.int64)
                values["quad_u"] = np.stack([row[1] for row in quad_rows]).astype(np.float64)
        np.savez_compressed(path, **values)
        # Diagnostic references are persisted in JSONL and may be compared or
        # consumed on a different operating system.  Always serialize them as
        # POSIX-style relative paths rather than leaking the host platform's
        # separator (for example, ``\\`` on Windows).
        return path.relative_to(self.output_dir).as_posix()


def create_diagnostics(
    diagnostics: DiagnosticOptions | str | Path | None,
    model: Any,
) -> SolverDiagnostics | None:
    if diagnostics is None:
        return None
    options = diagnostics if isinstance(diagnostics, DiagnosticOptions) else DiagnosticOptions(diagnostics)
    return SolverDiagnostics(options, model)
