"""In-memory execution of HRX-defined chained nonlinear analyses."""
from __future__ import annotations

import copy
from pathlib import Path
import time
from typing import Any, Callable, Iterable

import numpy as np

from histra.postprocessing import ReactionResult, compute_total_reaction
from histra.solver.cancellation import CancelCheck
from histra.solver.interface_material import (
    InterfaceMaterialMutationReport,
    change_interface_materials,
    normalize_interface_registration,
    normalize_spring_type_change,
    _backup_quad_links,
    _restore_quad_links,
)
from histra.solver.outcomes import (
    AnalysisExecution,
    AnalysisOutcome,
    AnalysisStep,
    classify_analysis_outcome,
)
from histra.solver.modal import modal_linear_solver_backend, solve_modal_analysis
from histra.solver.solve import solve_static_nonlinear
from histra.solver.equilibrium import UNSAFE_EQUILIBRIUM_EXIT_CODE
from histra.solver.capabilities import inspect_solver_capabilities
from histra.solver.strategy import (
    emit_strategy_advisories,
    normalize_strategy_policy,
)


class AnalysisSessionError(RuntimeError):
    """Raised when an HRX analysis chain is inconsistent with session state."""


class AnalysisSession:
    """Stateful multi-analysis execution manager with in-memory state preservation.

    Manages chained HRX analyses (e.g. Gravity -> Scour -> Lateral Pushover)
    without reloading the model or serializing intermediate state to disk.
    Preserves committed element deformations and constitutive histories across
    analysis boundaries, and supports boundary material mutations via
    ``change_interface_materials``.

    Parameters
    ----------
    model : Model
        The freshly prepared or loaded HiStrA Model.
    combination_row : int, default=1
        1-based index of the load combination to evaluate.
    on_log : Callable[[str], None], optional
        Callback receiving solver progress and diagnostic log messages.
    on_progress : Callable[[float], None], optional
        Callback receiving numerical step progress (0.0 to 100.0).
    equilibrium_policy : {"warn", "strict", "off"}, default="warn"
        Policy for independent equilibrium force residual balance auditing.
    performance_policy : {"compiled", "diagnostic-scalar"}, default="compiled"
        Policy enforcing compiled Numba backend execution.
    preserve_predecessor_load : bool, default=False
        Carry the committed applied load into chained static analyses. This is
        useful when a material change must re-equilibrate under the same load;
        the default retains the C# restart's resisting-force baseline.

    Examples
    --------
    >>> from histra import load_model, AnalysisSession
    >>> model = load_model("path/to/model.hrx")
    >>> session = AnalysisSession(model)
    >>> execution = session.run_analysis("Vert")
    >>> execution.outcome.name
    'CONVERGED'
    """

    def __init__(
        self,
        model: Any,
        *,
        combination_row: int = 1,
        on_log: Callable[[str], None] | None = None,
        on_progress: Callable[[float], None] | None = None,
        equilibrium_policy: str = "warn",
        equilibrium_force_absolute_tolerance: float = 1.0e-3,
        equilibrium_force_relative_tolerance: float = 1.0e-5,
        equilibrium_residual_tolerance: float | None = None,
        strategy_policy: str = "warn",
        strategy_evidence: Any | None = None,
        performance_policy: str = "compiled",
        linear_solver_backend: str | None = None,
        linear_solver_precision: str = "fast",
        umfpack_irstep: int | None = None,
        adaptive_tangent_refresh: bool | int | None = None,
        tangent_refresh_cadence: int | None = None,
        allow_experimental_methods: bool = False,
        interface_registration: str = "csharp",
        capture_csharp_results: bool = False,
        preserve_predecessor_load: bool = False,
    ) -> None:
        if model.collections is None:
            raise AnalysisSessionError("Model.collections is not initialized.")
        self.model = model
        self.capture_csharp_results = bool(capture_csharp_results)
        self.preserve_predecessor_load = bool(preserve_predecessor_load)
        self._committed_external_load: np.ndarray | None = None
        self._committed_reaction: ReactionResult | None = None
        self.interface_registration = normalize_interface_registration(interface_registration)
        self.combination_row = int(combination_row)
        self.on_log = on_log
        self.on_progress = on_progress
        self.equilibrium_policy = equilibrium_policy
        self.equilibrium_force_absolute_tolerance = float(
            equilibrium_force_absolute_tolerance
        )
        self.equilibrium_force_relative_tolerance = float(
            equilibrium_force_relative_tolerance
        )
        self.equilibrium_residual_tolerance = equilibrium_residual_tolerance
        self.strategy_policy = normalize_strategy_policy(strategy_policy)
        self.strategy_evidence = strategy_evidence
        policy = str(performance_policy).strip().lower()
        if policy not in {"compiled", "diagnostic-scalar"}:
            raise ValueError(
                f"Unknown performance_policy {performance_policy!r}; "
                "expected 'compiled' or 'diagnostic-scalar'."
            )
        self.performance_policy = policy
        self.linear_solver_backend = linear_solver_backend
        self.linear_solver_precision = linear_solver_precision
        self.umfpack_irstep = umfpack_irstep
        self.adaptive_tangent_refresh = adaptive_tangent_refresh
        self.tangent_refresh_cadence = tangent_refresh_cadence
        self.allow_experimental_methods = bool(allow_experimental_methods)
        self.backend_coverage: Any | None = None
        if policy == "diagnostic-scalar" and self.on_log is not None:
            self.on_log(
                "PERFORMANCE POLICY NOTICE: Running in 'diagnostic-scalar' mode. "
                "This unmanaged/scalar execution is for diagnostics only and cannot support production release acceptance."
            )
        self._emitted_strategy_advisories: set[
            tuple[str, int, str, str, str]
        ] = set()
        self.current_analysis_key: int | None = None
        self.current_displacement: np.ndarray | None = None
        self.executions: list[AnalysisExecution] = []
        self.mutations: list[InterfaceMaterialMutationReport] = []
        self._tainted_reason: str | None = None

    @property
    def usable(self) -> bool:
        """Whether the session can safely start another analysis."""
        return self._tainted_reason is None

    def _require_usable(self) -> None:
        if self._tainted_reason is not None:
            raise AnalysisSessionError(
                "This analysis session cannot be reused after an incomplete solve: "
                f"{self._tainted_reason}. Reload the HRX and create a new session."
            )

    def resolve_analysis(self, analysis: int | str | Any) -> Any:
        if hasattr(analysis, "key") and hasattr(analysis, "name"):
            return analysis
        if isinstance(analysis, int) or str(analysis).lstrip("-").isdigit():
            key = int(analysis)
            try:
                return self.model.collections.analyses[key]
            except KeyError as exc:
                raise AnalysisSessionError(f"Analysis key {key} is absent from the HRX.") from exc
        name = str(analysis)
        matches = [
            item for item in self.model.collections.analyses.values()
            if item.name.casefold() == name.casefold()
        ]
        if len(matches) != 1:
            raise AnalysisSessionError(
                f"Expected one HRX analysis named {name!r}, found {len(matches)}."
            )
        return matches[0]

    def change_interface_materials(
        self,
        interface_keys: Iterable[int],
        material_key: int,
        *,
        preserve_committed_state: bool = True,
        spring_type_change: str = "reject",
    ) -> InterfaceMaterialMutationReport:
        self._require_usable()
        policy = normalize_spring_type_change(spring_type_change)
        keys = tuple(dict.fromkeys(int(key) for key in interface_keys))
        if not keys:
            return InterfaceMaterialMutationReport(
                int(material_key), (), self.interface_registration,
                spring_type_change=policy, preserve_committed_state=preserve_committed_state,
            )

        if self.model.collections is None:
            from histra.solver.interface_material import InterfaceMaterialMutationError

            raise InterfaceMaterialMutationError("Model.collections is not initialized.")

        missing = [key for key in keys if key not in self.model.collections.interfaces]
        if missing:
            from histra.solver.interface_material import InterfaceMaterialMutationError

            raise InterfaceMaterialMutationError(f"Unknown interface keys: {missing}.")

        from histra.solver.interface_material import _backup_interface

        quad_links = _backup_quad_links(self.model, keys)
        if quad_links:
            from histra.solver.model_manager import ModelManager

            runtime = ModelManager.hysteretic_batch_for(self.model)
            if runtime is not None:
                runtime.sync_all_to_objects()
        backups = {
            key: _backup_interface(self.model.collections.interfaces[key])
            for key in keys
        }

        try:
            report = change_interface_materials(
                self.model,
                keys,
                material_key,
                preserve_committed_state=preserve_committed_state,
                interface_registration=self.interface_registration,
                spring_type_change=policy,
            )
            if self.performance_policy == "compiled":
                from histra.solver.backend_coverage import inspect_solver_backend

                coverage = inspect_solver_backend(self.model)
                self.backend_coverage = coverage
                coverage.require_compiled()
        except Exception:
            try:
                _restore_quad_links(self.model, quad_links)
                for key, backup in backups.items():
                    self.model.collections.interfaces[key] = backup
                from histra.solver.model_manager import ModelManager

                ModelManager.clear_hysteretic_batch()
            except Exception as rollback_exc:
                self._tainted_reason = (
                    f"change_interface_materials rollback failed: {rollback_exc}"
                )
            raise

        self.mutations.append(report)
        if self.on_log is not None:
            self.on_log(
                f"Changed {report.interface_count} interfaces to material "
                f"{report.material_key}; rebuilt {report.spring_count} springs; "
                f"registration={report.interface_registration}, "
                f"added Quad links={report.added_quad_links}; "
                f"spring_type_change={report.spring_type_change}, "
                f"reset spring histories={report.reset_spring_count}"
            )
        return report

    def run(
        self,
        analysis: int | str | Any,
        *,
        max_committed_steps: int | None = None,
        should_stop_after_commit: Callable[[dict[str, Any]], bool] | None = None,
        on_step_committed: Callable[[dict[str, Any], Any], None] | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> AnalysisExecution:
        self._require_usable()
        # A locked HRX carries C# serialized interfaces/springs for reference
        # comparison only.  Regenerate the Python model before any capability,
        # backend, or solver operation can observe those objects.
        if bool(getattr(self.model, "requires_python_preparation", False)):
            from histra.solver.model_manager import ModelManager

            ModelManager.prepare_model(self.model, force=True)
        definition = copy.deepcopy(self.resolve_analysis(analysis))
        if self.allow_experimental_methods:
            definition.allow_experimental_methods = True
        inspect_solver_capabilities(self.model, [definition]).require_supported()
        is_modal = int(getattr(definition, "analysis_type", 0)) == 5
        execution_backend = modal_linear_solver_backend(definition) if is_modal else getattr(
            definition, "linear_solver_backend", self.linear_solver_backend
        )
        if self.performance_policy == "compiled":
            from histra.solver.backend_coverage import require_compiled_dependencies

            require_compiled_dependencies(
                self.model, [definition],
                linear_solver_backend=execution_backend,
            )
        # Restart resultants are numerical work too: audit their live runtime
        # before capturing predecessor reactions. Virgin state is built in setup.
        if self.performance_policy == "compiled" and int(definition.initial_analysis_key) >= 0:
            from histra.solver.backend_coverage import inspect_solver_backend

            self.backend_coverage = inspect_solver_backend(
                self.model, [definition],
                linear_solver_backend=execution_backend,
            )
            self.backend_coverage.require_compiled()
        emit_strategy_advisories(
            definition,
            policy=self.strategy_policy,
            on_log=self.on_log,
            emitted=self._emitted_strategy_advisories,
            model=self.model,
            strategy_evidence=self.strategy_evidence,
        )
        initial_key = int(getattr(definition, "initial_analysis_key", -100))
        kwargs: dict[str, Any] = {}
        if initial_key < 0:
            if self.current_analysis_key is not None:
                raise AnalysisSessionError(
                    f"Analysis {definition.key}:{definition.name} is virgin but session "
                    f"already contains committed analysis {self.current_analysis_key}."
                )
            interfaces = getattr(self.model.collections, "interfaces", None)
            num_intf = len(interfaces) if interfaces is not None else 0
            init_f = np.zeros((num_intf, 3), dtype=np.float32) if num_intf > 0 else None
            init_m = np.zeros((num_intf, 3), dtype=np.float32) if num_intf > 0 else None
            initial_step = AnalysisStep.initial(
                np.zeros(int(self.model.gdl), dtype=float),
                interface_resultants=init_f,
                interface_moments=init_m,
            )
        else:
            if self.current_analysis_key != initial_key or self.current_displacement is None:
                raise AnalysisSessionError(
                    f"Analysis {definition.key}:{definition.name} requires predecessor "
                    f"{initial_key}, but current session predecessor is "
                    f"{self.current_analysis_key}."
                )
            predecessor_reaction = compute_total_reaction(self.model)
            from histra.solver.model_manager import ModelManager

            pred_rt = ModelManager.hysteretic_batch_for(self.model)
            pred_f = (
                pred_rt.all_resultant_forces().copy()
                if pred_rt is not None and getattr(pred_rt, "active", False)
                else None
            )
            pred_m = (
                pred_rt.all_bending_moments().copy()
                if pred_rt is not None and getattr(pred_rt, "active", False)
                else None
            )
            initial_step = AnalysisStep.initial(
                self.current_displacement,
                reaction_x=predecessor_reaction.x,
                reaction_y=predecessor_reaction.y,
                reaction_z=predecessor_reaction.z,
                interface_resultants=pred_f,
                interface_moments=pred_m,
            )
            kwargs.update(
                initial_displacement=self.current_displacement,
                restart_from_current_state=True,
            )
            if self.preserve_predecessor_load and not is_modal:
                if self._committed_external_load is None or self._committed_reaction is None:
                    raise AnalysisSessionError("No committed predecessor load is available")
                kwargs.update(
                    initial_external_load=self._committed_external_load.copy(),
                    equilibrium_reference_reaction=self._committed_reaction,
                )

        capture = None
        if self.capture_csharp_results:
            from histra.io.csharp_results_capture import CSharpResultsCapture

            if int(definition.analysis_type) == 5:
                raise AnalysisSessionError("Native .Results capture currently supports static Quad/Interface analyses only")
            capture = CSharpResultsCapture(self.model, self.combination_row)
        started = time.perf_counter()
        try:
            if is_modal:
                modal_result = solve_modal_analysis(
                    self.model,
                    definition,
                    self.combination_row,
                    on_log=self.on_log,
                    on_progress=self.on_progress,
                    should_cancel=should_cancel,
                    performance_policy=self.performance_policy,
                    **kwargs,
                )
                code = 0
                raw_steps: list[dict[str, Any]] = []
            else:
                modal_result = None
                code, raw_steps = solve_static_nonlinear(
                    self.model,
                    definition,
                    self.combination_row,
                    on_log=self.on_log,
                    on_progress=self.on_progress,
                    max_committed_steps=max_committed_steps,
                    should_stop_after_commit=should_stop_after_commit,
                    on_step_committed=on_step_committed,
                    on_state_saved=capture.capture if capture is not None else None,
                    should_cancel=should_cancel,
                    linear_solver_backend=execution_backend,
                    linear_solver_precision=getattr(
                        definition, "linear_solver_precision", self.linear_solver_precision
                    ),
                    umfpack_irstep=getattr(
                        definition, "umfpack_irstep", self.umfpack_irstep
                    ),
                    adaptive_tangent_refresh=getattr(
                        definition, "adaptive_tangent_refresh", self.adaptive_tangent_refresh
                    ),
                    tangent_refresh_cadence=getattr(
                        definition, "tangent_refresh_cadence", self.tangent_refresh_cadence
                    ),
                    equilibrium_policy=self.equilibrium_policy,
                    equilibrium_force_absolute_tolerance=(
                        self.equilibrium_force_absolute_tolerance
                    ),
                    equilibrium_force_relative_tolerance=(
                        self.equilibrium_force_relative_tolerance
                    ),
                    equilibrium_residual_tolerance=(
                        self.equilibrium_residual_tolerance
                    ),
                    performance_policy=self.performance_policy,
                    **kwargs,
                )
            if self.performance_policy == "compiled":
                from histra.solver.backend_coverage import inspect_solver_backend

                self.backend_coverage = inspect_solver_backend(
                    self.model, [definition],
                    linear_solver_backend=execution_backend,
                )
                self.backend_coverage.require_compiled()
        except Exception as exc:
            self._tainted_reason = f"{type(exc).__name__}: {exc}"
            raise
        runtime = time.perf_counter() - started
        steps = tuple(AnalysisStep.from_mapping(step) for step in raw_steps)
        outcome = classify_analysis_outcome(int(code), steps, definition)
        from histra.io.results_snapshot import capture_export_snapshot
        from histra.io.model_point_summary import build_model_point_summary

        execution = AnalysisExecution(
            analysis_key=int(definition.key),
            analysis_name=str(definition.name),
            code=int(code),
            steps=steps,
            runtime_seconds=float(runtime),
            outcome=outcome,
            message=(
                "Analysis candidate failed the independent equilibrium safety "
                "audit and was rolled back before commit."
                if int(code) == UNSAFE_EQUILIBRIUM_EXIT_CODE
                else _outcome_message(outcome)
            ),
            initial_step=initial_step,
            modal_result=modal_result,
            export_snapshot=capture_export_snapshot(self.model) if modal_result is None else None,
            csharp_records=capture.finish(definition.key) if capture is not None and capture.last_row is not None else None,
            model_point_output=build_model_point_summary(
                self.model, ((initial_step,) if initial_step is not None else ()) + tuple(s for s in steps if s.committed), definition,
            ) if modal_result is None else None,
        )
        committed = execution.committed_steps
        if execution.completed and execution.modal_result is not None:
            self.current_analysis_key = int(definition.key)
            self.current_displacement = initial_step.u.copy()
        elif execution.completed and committed:
            self.current_analysis_key = int(definition.key)
            self.current_displacement = committed[-1].u.copy()
            if self.preserve_predecessor_load:
                from histra.solver.model_manager import ModelManager

                if ModelManager._fext is None:
                    raise AnalysisSessionError("Completed analysis has no external load vector")
                self._committed_external_load = ModelManager._fext.copy()
                last = committed[-1]
                reaction_x, reaction_y, reaction_z = last.reaction_x, last.reaction_y, last.reaction_z
                if reaction_x is None or reaction_y is None or reaction_z is None:
                    raise AnalysisSessionError("Completed analysis has no reaction reference")
                self._committed_reaction = ReactionResult(
                    reaction_x, reaction_y, reaction_z,
                )
        elif not execution.completed:
            self._tainted_reason = (
                f"analysis {definition.key}:{definition.name} ended as {outcome.value}"
            )
        self.executions.append(execution)
        return execution

    def dependency_chain(self, target: int | str | Any) -> tuple[Any, ...]:
        """Return the HRX-defined predecessor chain ending at ``target``."""
        chain: list[Any] = []
        seen: set[int] = set()
        current = self.resolve_analysis(target)
        while True:
            key = int(current.key)
            if key in seen:
                raise AnalysisSessionError(
                    f"Cycle detected in HRX analysis dependencies at key {key}."
                )
            seen.add(key)
            chain.append(current)
            predecessor = int(getattr(current, "initial_analysis_key", -100))
            if predecessor < 0:
                break
            try:
                current = self.model.collections.analyses[predecessor]
            except KeyError as exc:
                raise AnalysisSessionError(
                    f"Analysis {key}:{current.name} requires missing predecessor "
                    f"{predecessor}."
                ) from exc
        chain.reverse()
        return tuple(chain)

    def run_to(
        self,
        target: int | str | Any,
        *,
        before_analysis: Callable[["AnalysisSession", Any], None] | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> tuple[AnalysisExecution, ...]:
        """Run the HRX dependency chain, optionally mutating at boundaries."""
        results: list[AnalysisExecution] = []
        for analysis in self.dependency_chain(target):
            if before_analysis is not None:
                before_analysis(self, analysis)
            results.append(self.run(analysis, should_cancel=should_cancel))
        return tuple(results)

    def run_sequence(
        self,
        analyses: Iterable[int | str | Any],
        *,
        should_cancel: CancelCheck | None = None,
    ) -> tuple[AnalysisExecution, ...]:
        return tuple(
            self.run(analysis, should_cancel=should_cancel) for analysis in analyses
        )

    # Alias matching session documentation and user intuition
    run_analysis = run

    def export_analysis(
        self,
        analysis_key_or_name: int | str,
        output_dir: str | Path,
        base_name: str | None = None,
        format: str = "npz",
        tier: str = "all",
        include_node_displacements: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Path]:
        """Export simulation results of a single executed analysis.

        Parameters
        ----------
        analysis_key_or_name : int or str
            Key or name of an already executed analysis in this session.
        output_dir : str or Path
            Target directory for export.
        base_name : str, optional
            Base filename prefix (defaults to '{model_name}_{analysis_name}').
        format : {"npz", "h5", "json", "histra", "results"}, default="npz"
            Array format for dense fields.
        tier : {"all", "summary", "fields"}, default="all"
            Which tiers to export.
        include_node_displacements : bool, default=True
            Whether to project and store full 3D node translations across steps.
        metadata : dict, optional
            Additional metadata merged into the summary manifest.

        Returns
        -------
        dict[str, Path]
            Dictionary of created files: {'summary': path, 'fields': path}.
        """
        target_analysis = self.resolve_analysis(analysis_key_or_name)
        target_key = int(target_analysis.key)
        execution = next(
            (e for e in reversed(self.executions) if int(e.analysis_key) == target_key),
            None,
        )
        if execution is None:
            raise AnalysisSessionError(
                f"No execution found in session for analysis {target_key}:{target_analysis.name}. "
                "Execute the analysis first using session.run(...) before exporting."
            )

        if base_name is None:
            model_stem = getattr(self.model, "name", None) or (
                Path(self.model.source_path).stem if getattr(self.model, "source_path", None) else "model"
            )
            base_name = f"{model_stem}_{execution.analysis_name}"

        filepath = Path(output_dir) / base_name
        from histra.io.results_writer import ResultsWriter

        return ResultsWriter.export(
            model=self.model,
            execution=execution,
            filepath=filepath,
            format=format,
            tier=tier,
            include_node_displacements=include_node_displacements,
            metadata=metadata,
        )

    def export_session(
        self,
        output_dir: str | Path,
        bundle_name: str,
        format: str = "npz",
        tier: str = "all",
        include_node_displacements: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Path]]:
        """Export all executed analyses in this session.

        Parameters
        ----------
        output_dir : str or Path
            Target directory.
        bundle_name : str
            Prefix for all exported analyses.
        format : {"npz", "h5", "json", "histra", "results"}, default="npz"
            Array format for dense fields.
        tier : {"all", "summary", "fields"}, default="all"
            Which tiers to export.
        include_node_displacements : bool, default=True
            Whether to project and store full 3D node translations across steps.
        metadata : dict, optional
            Additional metadata merged into the summary manifests.

        Returns
        -------
        dict[str, dict[str, Path]]
            Mapping of analysis_name -> dict of created file paths.
        """
        if not self.executions:
            raise AnalysisSessionError("Session contains no completed or executed analyses to export.")

        if str(format).lower().strip() in {"results", "result", "csharp"}:
            if str(tier).lower().strip() != "all":
                raise ValueError("Native .Results export requires tier='all'")
            path = self.export_csharp_results(Path(output_dir) / bundle_name)
            return {execution.analysis_name: {"results": path} for execution in self.executions}
        if str(format).lower().strip() == "histra":
            path = self.export_bundle(
                Path(output_dir) / bundle_name, tier=tier,
                include_node_displacements=include_node_displacements, metadata=metadata,
            )
            return {execution.analysis_name: {"bundle": path} for execution in self.executions}

        results: dict[str, dict[str, Path]] = {}
        from histra.io.results_writer import ResultsWriter

        # Match export_analysis: the most recent execution wins on reruns.
        latest = {execution.analysis_name: execution for execution in self.executions}
        for execution in latest.values():
            base_name = f"{bundle_name}_{execution.analysis_name}"
            filepath = Path(output_dir) / base_name
            meta = dict(metadata or {})
            meta["bundle_name"] = bundle_name
            exported = ResultsWriter.export(
                model=self.model,
                execution=execution,
                filepath=filepath,
                format=format,
                tier=tier,
                include_node_displacements=include_node_displacements,
                metadata=meta,
            )
            results[execution.analysis_name] = exported
        from histra.io.results_writer import write_session_manifest

        write_session_manifest(self.model, results, Path(output_dir) / f"{bundle_name}.session.json")
        return results

    def export_csharp_results(self, filepath, *, reference_path=None) -> Path:
        """Export captured native static records; optionally demand exact reference values."""
        from histra.io.csharp_results_writer import export_csharp_executions

        return export_csharp_executions(self.executions, filepath, reference_path=reference_path)

    def export_bundle(self, filepath, *, tier="all", include_node_displacements=True, metadata=None) -> Path:
        """Export the latest execution of every analysis in one .histra file."""
        from histra.io.results_writer import ResultsWriter

        if not self.executions:
            raise AnalysisSessionError("Session contains no executed analyses to export.")
        latest = {execution.analysis_name: execution for execution in self.executions}
        return ResultsWriter.export_bundle(
            self.model, latest, filepath, tier=tier,
            include_node_displacements=include_node_displacements, metadata=metadata,
        )


def _outcome_message(outcome: AnalysisOutcome) -> str:
    if outcome is AnalysisOutcome.COMPLETED:
        return "Analysis completed."
    if outcome is AnalysisOutcome.COMPLETED_AT_DISPLACEMENT_LIMIT:
        return "Analysis reached its configured element displacement limit."
    if outcome is AnalysisOutcome.CANCELLED:
        return "Analysis was cancelled and its active trial step was rolled back."
    if outcome is AnalysisOutcome.NONCONVERGED:
        return "Analysis did not converge."
    return f"Analysis ended as {outcome.value}."
