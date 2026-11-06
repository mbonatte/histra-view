"""In-process HiStrA-Python analysis runner and .histra bundle exporter for Model View."""
from __future__ import annotations

import base64
from dataclasses import replace
from enum import StrEnum
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from typing import Any, Callable
import uuid
import warnings

BASE = Path(__file__).resolve().parent
RUNS_DIR = BASE.parent / "results" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_JOB_ID: str | None = None
# Keep executed analyses and HRX <State> attributes per model SHA-256 so running
# several analyses on the same model accumulates them into a single multi-case
# .histra bundle (which embeds the updated .hrx inside the .histra archive).
_MODEL_EXECUTIONS: dict[str, dict[str, Any]] = {}
_MODEL_STATES: dict[str, dict[str, dict[str, str]]] = {}


class _RunOutcome(StrEnum):
    STOPPED = 'stopped'


def _stopped_execution(execution):
    """Mark an intentionally stopped committed snapshot as incomplete."""
    return replace(execution, code=-5, outcome=_RunOutcome.STOPPED,
                   message='Stopped by user after a committed step; analysis is incomplete.')


class _LambdaCrossing:
    """Find the first committed crossing after departing an initial target."""
    def __init__(self, target, initial=0.0):
        self.target = target
        self.previous = initial
        self.departed = initial != target
        self.achieved = None

    def observe(self, value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('The arc-length load factor is not finite.')
        if not self.departed:
            if value != self.target:
                self.departed = True
                self.previous = value
            return False
        crossed = (self.previous - self.target) * (value - self.target) <= 0
        self.previous = value
        if crossed:
            self.achieved = value
        return crossed


def _write_hrx_with_states(
    hrx_bytes: bytes,
    analysis_states: dict[str, dict[str, str]],
    target_path: Path,
) -> None:
    if not analysis_states:
        target_path.write_bytes(hrx_bytes)
        return
    try:
        from lxml import etree

        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(hrx_bytes, parser=parser)
        for analysis_el in root.findall("Analysis"):
            key = str(analysis_el.get("Key", "")).strip()
            st = analysis_states.get(key)
            if not st:
                continue
            states_el = analysis_el.find("States")
            if states_el is None:
                states_el = etree.SubElement(analysis_el, "States")
            state_el = states_el.find("State")
            if state_el is None:
                state_el = etree.SubElement(states_el, "State")
            for attr_key, attr_val in st.items():
                state_el.set(str(attr_key), str(attr_val))
        target_path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=True))
    except Exception:
        target_path.write_bytes(hrx_bytes)


def _safe_stem(name: str) -> str:
    stem = Path(name or "model.hrx").stem
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")
    return cleaned or "model"


def _execution_to_hrx_state(execution: Any) -> dict[str, str]:
    from histra.solver.outcomes import AnalysisOutcome

    committed = execution.committed_steps
    modal = execution.modal_result
    if modal is not None and execution.completed:
        state_name = "ExecutedCompleted"
        step_count = len(modal.modes)
        fo = 0.0
    elif execution.completed:
        state_name = "ExecutedCompleted"
        step_count = len(committed)
        fo = float(committed[-1].get("load_factor", 0.0)) if committed else 0.0
    elif committed:
        state_name = "ExecutedNotCompleted"
        step_count = len(committed)
        fo = float(committed[-1].get("load_factor", 0.0))
    elif execution.outcome is AnalysisOutcome.CANCELLED:
        state_name = "NotExecuted"
        step_count = 0
        fo = 0.0
    else:
        state_name = "ExecutedNotCompleted"
        step_count = 0
        fo = 0.0
    return {
        "Key": "1",
        "Combination": "0",
        "State": state_name,
        "Step": str(step_count),
        "Fo": f"{fo:g}",
        "Exit": str(int(execution.code)),
        "ExitDescription": str(execution.message or ""),
    }


def _expected_static_steps(definition: Any) -> int:
    method = str(getattr(definition, "integration_method", "LoadControl"))
    if method == "LoadControl":
        mult = abs(float(getattr(definition, "mult", 1.0) or 1.0))
        inc_mult = abs(float(getattr(definition, "inc_mult", 0.0) or 0.0))
        if inc_mult > 1e-9 and mult > 1e-9:
            return max(1, int(round(mult / inc_mult)))
        return 5
    max_steps = int(getattr(definition, "max_step", 0) or getattr(definition, "nstep", 0) or 50)
    return max(1, max_steps)


def _estimate_static_step_progress(definition: Any, step_dict: dict[str, Any]) -> float:
    step_num = int(step_dict.get("step", 0) or 0)
    expected = _expected_static_steps(definition)
    method = str(getattr(definition, "integration_method", "LoadControl"))
    if method == "LoadControl":
        lf = abs(float(step_dict.get("load_factor", 0.0) or 0.0))
        target = abs(float(getattr(definition, "mult", 1.0) or 1.0))
        if target > 1e-9 and lf > 0:
            return min(99.0, max(0.0, (lf / target) * 100.0))
    max_u = abs(float(getattr(definition, "max_u", 0.0) or 0.0))
    disp = abs(float(step_dict.get("displacement", 0.0) or 0.0))
    if max_u > 1e-9 and disp > 0:
        return min(99.0, max(0.0, (disp / max_u) * 100.0))
    if expected > 0:
        return min(99.0, max(0.0, (step_num / expected) * 100.0))
    return min(95.0, float(step_num))


def decode_source_bytes(source: str | bytes | None, fallback_bytes: bytes | None = None) -> bytes:
    if isinstance(source, bytes) and source:
        return source
    if isinstance(source, str) and source.strip():
        return base64.b64decode(source)
    if fallback_bytes:
        return fallback_bytes
    raise ValueError("No HRX model is loaded. Open or build an HRX model first.")


def _apply_pdelta_effect(hrx_bytes, chain, effect):
    """Apply a run-only setting to static stages and record it in the embedded HRX."""
    from lxml import etree
    root = etree.fromstring(hrx_bytes, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    for analysis in chain:
        if int(analysis.analysis_type) == 5:
            continue
        element = root.find(f"Analysis[@Key='{int(analysis.key)}']")
        if element is None:
            raise ValueError('Analysis definition missing from source HRX.')
        analysis.pdelta_effect = effect
        element.set('PdeltaEffect', effect)
    return etree.tostring(root, encoding='utf-8', xml_declaration=True)


def start_job(
    hrx_bytes: bytes,
    model_name: str,
    analysis_key: int | str,
    *,
    combination_row: int = 1,
    lateral_subgrade: dict[str, Any] | None = None,
    scour_workflow: dict[str, Any] | None = None,
    pdelta_effect: str | None = None,
    arc_lambda_target: float | None = None,
    on_complete: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    global _ACTIVE_JOB_ID
    if not hrx_bytes:
        raise ValueError("HRX model is empty.")
    if analysis_key in (None, ""):
        raise ValueError("Select an analysis to run.")

    if arc_lambda_target is not None:
        if isinstance(arc_lambda_target, bool):
            raise ValueError("Enter a finite arc-length λ target.")
        try:
            arc_lambda_target = float(arc_lambda_target)
        except (TypeError, ValueError):
            raise ValueError("Enter a finite arc-length λ target.") from None
        if not math.isfinite(arc_lambda_target):
            raise ValueError("Enter a finite arc-length λ target.")

    if pdelta_effect not in (None, "None", "EachStep", "EachIteration"):
        raise ValueError("Invalid P-Delta setting.")

    if lateral_subgrade is not None:
        if not isinstance(lateral_subgrade, dict):
            raise ValueError("Lateral subgrade settings must be an object.")
        keys = lateral_subgrade.get("restraintKeys")
        if not isinstance(keys, list) or not keys or any(type(k) is not int or k <= 0 for k in keys) or len(set(keys)) != len(keys):
            raise ValueError("Enter distinct positive integer lateral restraint keys.")
        try:
            kx = float(lateral_subgrade["kx"])
            ky = float(lateral_subgrade["ky"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Enter Kx and Ky in kN/m³.") from None
        if not all(math.isfinite(v) and v >= 0 for v in (kx, ky)):
            raise ValueError("Kx and Ky must be finite and non-negative.")
        lateral_subgrade = {"restraintKeys": sorted(keys), "kx": kx, "ky": ky}

    if scour_workflow is not None:
        from scour_workflow import normalize_workflow
        scour_workflow = normalize_workflow(scour_workflow)

    with _LOCK:
        if _ACTIVE_JOB_ID is not None:
            active = _JOBS.get(_ACTIVE_JOB_ID)
            if active and active["status"] == "running":
                raise ValueError(
                    f"Analysis '{active['targetName']}' is already running. Wait for it to finish or cancel it."
                )

        job_id = uuid.uuid4().hex[:12]
        stem = _safe_stem(model_name)
        identity = hrx_bytes
        if lateral_subgrade is not None:
            identity += b"\0lateral-subgrade:" + json.dumps(lateral_subgrade, sort_keys=True).encode()
        if scour_workflow is not None:
            identity += b"\0scour-workflow:" + json.dumps(scour_workflow, sort_keys=True).encode()
        if pdelta_effect is not None:
            identity += b"\0pdelta:" + pdelta_effect.encode()
        if arc_lambda_target is not None:
            identity += b"\0arc-lambda-target:" + repr(arc_lambda_target).encode()
        model_sha = hashlib.sha256(identity).hexdigest()
        if lateral_subgrade is not None or scour_workflow is not None or pdelta_effect is not None or arc_lambda_target is not None:
            stem = f"{stem}-soil-{model_sha[:8]}"
        bundle_path = RUNS_DIR / f"{stem}.histra"

        job: dict[str, Any] = {
            "jobId": job_id,
            "status": "running",
            "modelName": model_name or f"{stem}.hrx",
            "modelStem": stem,
            "modelSha256": model_sha,
            "_hrxBytes": hrx_bytes,
            "_lateralSubgrade": lateral_subgrade,
            "_scourWorkflow": scour_workflow,
            "_pdeltaEffect": pdelta_effect,
            "_arcLambdaTarget": arc_lambda_target,
            "lambdaTargetResult": None,
            "bundlePath": str(bundle_path),
            "bundleName": bundle_path.name,
            "bundleReady": False,
            "bundleSize": 0,
            "sourceId": f"run_{stem}",
            "targetKey": str(analysis_key),
            "targetName": str(analysis_key),
            "combinationRow": int(combination_row),
            "progress": 0.0,
            "startedAt": time.time(),
            "finishedAt": None,
            "runtimeSeconds": 0.0,
            "cancelRequested": False,
            "stopRequested": False,
            "_acceptStop": True,
            "error": None,
            "outcome": None,
            "message": "Preparing model and dependency chain…",
            "currentStage": None,
            "stages": [],
            "logs": [],
            "analysisStates": {},
            "resultSummary": None,
        }
        _JOBS[job_id] = job
        _ACTIVE_JOB_ID = job_id
        while len(_JOBS) > 24:
            oldest = next(iter(_JOBS))
            if oldest != _ACTIVE_JOB_ID:
                _JOBS.pop(oldest, None)
            else:
                break

    thread = threading.Thread(
        target=_run_job_worker,
        args=(job, on_complete),
        name=f"histra-solver-{job_id}",
        daemon=True,
    )
    thread.start()
    return job_status(job_id)


def _append_log(job: dict[str, Any], message: str) -> None:
    elapsed = time.time() - job["startedAt"]
    for line in str(message).splitlines():
        text = line.strip()
        if text:
            job["logs"].append(f"[{elapsed:6.2f}s] {text}")


def _run_job_worker(
    job: dict[str, Any],
    on_complete: Callable[[dict[str, Any]], dict[str, Any] | None] | None,
) -> None:
    global _ACTIVE_JOB_ID
    temp_dir = Path(tempfile.mkdtemp(prefix=f"histra-run-{job['jobId']}-"))
    try:
        from histra import AnalysisSession, load_solver_model
        from histra.io.results_writer import ResultsWriter
        from histra.solver.model_manager import ModelManager
        from histra.solver.outcomes import AnalysisOutcome

        _STEP_SOLVING_RE = re.compile(
            r"Step\s+(\d+)\s+solving:\s+Mult=([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
        )

        temp_hrx_path = temp_dir / f"{job['modelStem']}.hrx"
        temp_hrx_path.write_bytes(job["_hrxBytes"])

        _append_log(job, f"Loading HRX model '{job['modelName']}'…")
        model = load_solver_model(temp_hrx_path)
        effective_hrx = job["_hrxBytes"]
        if job["_lateralSubgrade"] is not None:
            from histra import set_lateral_subgrade_moduli
            from lxml import etree
            settings = job["_lateralSubgrade"]
            stiffnesses = set_lateral_subgrade_moduli(
                model, settings["restraintKeys"], kx_kn_m3=settings["kx"], ky_kn_m3=settings["ky"]
            )
            root = etree.fromstring(effective_hrx, parser=etree.XMLParser(resolve_entities=False, no_network=True))
            for restraint in root.findall("Restraint"):
                key = int(restraint.get("Key", "0"))
                if key in stiffnesses:
                    restraint.set("K2", repr(stiffnesses[key]))
            effective_hrx = etree.tostring(root, encoding="utf-8", xml_declaration=True)
            _append_log(job, f"Linear lateral subgrade: Kx={settings['kx']:g}, Ky={settings['ky']:g} kN/m³ on {len(stiffnesses)} restraints; effective K2 values are saved in the result bundle.")
        stage_index = 0
        total_stages = 1

        def on_log(msg: str) -> None:
            _append_log(job, msg)
            text = str(msg).strip()
            if not text:
                return
            last_line = text.splitlines()[-1][:200]
            cs = job.get("currentStage")
            m = _STEP_SOLVING_RE.search(last_line)
            if m and cs is not None:
                solving_step = int(m.group(1))
                target_lf = float(m.group(2))
                cs["solvingStep"] = solving_step
                cs["targetLoadFactor"] = target_lf
                job["message"] = (
                    f"Stage {cs['index']}/{cs['total']} ({cs['name']}) · "
                    f"Solving step {solving_step}/{cs.get('expectedSteps', cs.get('maxSteps', '?'))} (λ={target_lf:.3f})…"
                )
            else:
                job["message"] = last_line
            time.sleep(0)

        def on_progress(val: float) -> None:
            current = job.get("currentStage")
            if not current:
                return
            is_modal = current.get("analysisType") == 5
            if is_modal:
                stage_pct = (val * 100.0) if val <= 1.0 else float(val)
            else:
                expected = max(1, int(current.get("expectedSteps") or current.get("maxSteps") or 5))
                solving_step = max(1, int(current.get("solvingStep") or (int(current.get("step", 0)) + 1)))
                base = max(float(current.get("stageProgress", 0.0)), ((solving_step - 1) / expected) * 100.0)
                within_step = (min(95.0, max(0.0, float(val))) / 100.0) * (100.0 / expected)
                stage_pct = min(99.0, base + within_step)
            overall = 10.0 + ((stage_index + min(100.0, max(0.0, stage_pct)) / 100.0) / max(1, total_stages)) * 88.0
            job["progress"] = round(min(99.0, max(job["progress"], overall)), 1)
            time.sleep(0)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            session = AnalysisSession(
                model,
                combination_row=job["combinationRow"],
                on_log=on_log,
                on_progress=on_progress,
                equilibrium_policy=("off" if job["_scourWorkflow"]["skipEquilibriumAudit"] else "error") if job["_scourWorkflow"] else "off",
                preserve_predecessor_load=bool(job["_scourWorkflow"]),
                strategy_policy="off",
                performance_policy="compiled",
            )
            target_def = session.resolve_analysis(job["targetKey"])
            job["targetKey"] = str(target_def.key)
            job["targetName"] = str(target_def.name)
            if job['_arcLambdaTarget'] is not None and str(getattr(target_def, 'integration_method', '')) not in ('ArcLength', 'ArcLengthLinear'):
                raise ValueError('The λ target requires ArcLength on the selected analysis.')
            workflow = job["_scourWorkflow"]
            if workflow and workflow['skipEquilibriumAudit']:
                _append_log(job, 'Independent equilibrium audit disabled for this run; authored convergence criterion is used. Results are unaudited.')
            if workflow:
                from scour_workflow import configure_sequence
                chain = configure_sequence(model, target_def, workflow)
                from lxml import etree
                root = etree.fromstring(effective_hrx, parser=etree.XMLParser(resolve_entities=False, no_network=True))
                for definition in chain:
                    element = root.find(f"Analysis[@Key='{int(definition.key)}']")
                    if element is None: raise ValueError('Analysis definition missing from source HRX.')
                    element.set('InitialAnalysisKey', str(definition.initial_analysis_key))
                effective_hrx = etree.tostring(root, encoding='utf-8', xml_declaration=True)
            else:
                chain = session.dependency_chain(target_def.key)
            if job["_pdeltaEffect"] is not None:
                effective_hrx = _apply_pdelta_effect(effective_hrx, chain, job["_pdeltaEffect"])
                _append_log(job, f"P-Delta for static stages: {job['_pdeltaEffect']}; modal geometric stiffness is not supported.")
            total_stages = len(chain)
            job["stages"] = [
                {
                    "index": idx + 1,
                    "key": str(a.key),
                    "name": str(a.name),
                    "analysisType": int(a.analysis_type),
                    "status": "pending",
                    "steps": 0,
                    "expectedSteps": 0 if int(a.analysis_type) == 5 else _expected_static_steps(a),
                    "loadFactor": None,
                    "runtimeSeconds": 0.0,
                    "outcome": None,
                    "stepHistory": [],
                }
                for idx, a in enumerate(chain)
            ]
            chain_names = " → ".join(f"{a.name} (#{a.key})" for a in chain)
            _append_log(job, f"Resolved execution chain ({total_stages} stage{'s' if total_stages != 1 else ''}): {chain_names}")

            # Ensure C# native Work convergence criterion for ModifiedRegulaFalsiLineSearch
            for a in chain:
                if (
                    int(getattr(a, "analysis_type", 0)) != 5
                    and str(getattr(a, "method", "")) == "ModifiedRegulaFalsiLineSearch"
                    and str(getattr(a, "adaptive_convergence_criteria", "")) == "ForceMoment"
                ):
                    a.adaptive_convergence_criteria = "Work"
                    if model.collections and int(a.key) in model.collections.analyses:
                        model.collections.analyses[int(a.key)].adaptive_convergence_criteria = "Work"
                    _append_log(
                        job,
                        f"Stage '{a.name}': using C# native Work convergence criterion for ModifiedRegulaFalsiLineSearch",
                    )

            if workflow or bool(getattr(model, "requires_python_preparation", False)):
                job["message"] = "Preparing 3D mesh and fibre interface springs…"
                job["progress"] = 5.0
                _append_log(job, "Preparing 3D mesh and fibre interface springs…")
                time.sleep(0)
                t_prep = time.perf_counter()
                ModelManager.prepare_model(model, force=True)
                prep_s = time.perf_counter() - t_prep
                n_quads = len(getattr(model.collections, "quads", {}) or {})
                n_itf = len(getattr(model.collections, "interfaces", {}) or {})
                _append_log(job, f"Prepared {n_quads} quads and {n_itf} interfaces in {prep_s:.2f}s")
                job["progress"] = 10.0
                time.sleep(0)

            stage_selections = {}
            changed_scour_interfaces = set()
            if workflow:
                from lxml import etree
                from scour_workflow import pier_foundation_groups, select_ratio, selected_scour_extent, apply_scour_stage
                root = etree.fromstring(effective_hrx, parser=etree.XMLParser(resolve_entities=False, no_network=True))
                wizard = root.find('WizardData')
                if wizard is None:
                    raise ValueError('The scour workflow requires bridge WizardData.')
                groups = pier_foundation_groups(model, wizard)
                if workflow['pier'] > len(groups):
                    raise ValueError(f"Pier {workflow['pier']} not found; found {len(groups)} foundation footprints.")
                templates = model.collections.materials
                for material in (workflow['intactMaterial'], workflow['scouredMaterial']):
                    if material not in templates:
                        raise ValueError(f'Masonry soil material {material} is not available to the solver.')
                bottom_keys = sorted({e[5] for group in groups for e in group['entries']})
                report = session.change_interface_materials(bottom_keys, workflow['intactMaterial'], preserve_committed_state=False)
                _append_log(job, f"Assigned intact soil material {workflow['intactMaterial']} to {len(bottom_keys)} foundation interfaces before Vert.")
                group = groups[workflow['pier']-1]
                stage_selections = {item['analysisKey']: select_ratio(group, item['ratio'], workflow['direction']) for item in workflow['stages']}
                _append_log(job, f"Scour pier {workflow['pier']} from {workflow['direction']}; foundation width {group['ymax']-group['ymin']:.4g} cm.")
                for item in workflow['stages']:
                    extent = selected_scour_extent(group, stage_selections[item['analysisKey']], workflow['direction'])
                    stage = next((s for s in job['stages'] if s['key'] == str(item['analysisKey'])), None)
                    if stage is not None:
                        stage['scourExtent'] = {**extent, 'requestedRatio': item['ratio']}
                    _append_log(job, f"Scour analysis #{item['analysisKey']}: requested {item['ratio'] * 100:.2f}%; selected patch extent {extent['widthCm']:.4g} cm of {extent['foundationWidthCm']:.4g} cm ({extent['ratio'] * 100:.2f}%), {extent['interfaceCount']} interfaces.")
            executed_any = False
            stopped_run = False
            cancelled_run = False
            last_executed_name = str(target_def.name)

            for idx, definition in enumerate(chain):
                if job.get("stopRequested"):
                    stopped_run = True
                    job["message"] = "Stopped before the next stage; saving committed results…"
                    _append_log(job, job["message"])
                    break
                stage_index = idx
                stage_entry = job["stages"][idx]
                stage_entry["status"] = "running"
                max_steps = int(getattr(definition, "max_step", 0) or getattr(definition, "nstep", 0) or 50)
                expected_steps = _expected_static_steps(definition)
                job["currentStage"] = {
                    "index": idx + 1,
                    "total": total_stages,
                    "key": str(definition.key),
                    "name": str(definition.name),
                    "analysisType": int(definition.analysis_type),
                    "step": 0,
                    "solvingStep": 1,
                    "maxSteps": max_steps,
                    "expectedSteps": expected_steps,
                    "loadFactor": 0.0,
                    "targetLoadFactor": 0.0,
                    "displacement": 0.0,
                    "stageProgress": 0.0,
                    "stepHistory": [],
                }
                base_overall = 10.0 + (idx / max(1, total_stages)) * 88.0
                job["progress"] = round(max(job["progress"], base_overall), 1)
                _append_log(job, f"--- Starting stage {idx + 1}/{total_stages}: {definition.name} (#{definition.key}) ---")
                time.sleep(0)

                def on_step_committed(step_dict: dict[str, Any], _m: Any) -> None:
                    stage_pct = _estimate_static_step_progress(definition, step_dict)
                    step_num = int(step_dict.get("step", 0) or 0)
                    lf = float(step_dict.get("load_factor", 0.0) or 0.0)
                    disp = float(step_dict.get("displacement", 0.0) or 0.0)
                    iters = int(step_dict.get("iterations", 0) or 0)
                    err = float(step_dict.get("convergence_error", 0.0) or 0.0)
                    step_rec = {
                        "step": step_num,
                        "loadFactor": round(lf, 6),
                        "displacement": disp,
                        "iterations": iters,
                        "error": err,
                    }
                    cs = job["currentStage"]
                    if cs is not None:
                        cs["step"] = step_num
                        cs["solvingStep"] = step_num + 1
                        cs["loadFactor"] = lf
                        cs["displacement"] = disp
                        cs["stageProgress"] = stage_pct
                        cs["stepHistory"].append(step_rec)
                    stage_entry["steps"] = step_num
                    stage_entry["loadFactor"] = lf
                    stage_entry["stepHistory"].append(step_rec)
                    _append_log(
                        job,
                        f"  ✓ Step {step_num} converged: λ={lf:.4f}, |U|={disp:.4e} cm ({iters} iter, err={err:.2e})",
                    )
                    job["message"] = (
                        f"Stage {idx + 1}/{total_stages} ({definition.name}) · "
                        f"Step {step_num}/{expected_steps} converged (λ={lf:.3f}, |U|={disp:.3e} cm)"
                    )
                    overall = 10.0 + ((idx + stage_pct / 100.0) / max(1, total_stages)) * 88.0
                    job["progress"] = round(min(99.0, max(job["progress"], overall)), 1)
                    time.sleep(0)

                if workflow and int(definition.key) in stage_selections:
                    selected = set(stage_selections[int(definition.key)])
                    newly_selected = apply_scour_stage(session, selected, changed_scour_interfaces, workflow['scouredMaterial'])
                    _append_log(job, f"Scour stage {definition.name}: {newly_selected} newly scoured interfaces, {len(selected)} total; material {workflow['scouredMaterial']}, preserving committed state.")
                stop_observed = False
                crossing = (_LambdaCrossing(job['_arcLambdaTarget'])
                            if job['_arcLambdaTarget'] is not None and str(definition.key) == job['targetKey'] else None)
                def stop_after_commit(step):
                    nonlocal stop_observed
                    if job.get("stopRequested"):
                        stop_observed = True
                        return True
                    if crossing and crossing.observe(step.get('load_factor')):
                        job['lambdaTargetResult'] = {'target': crossing.target, 'achieved': crossing.achieved,
                                                     'step': int(step['step']), 'analysisKey': int(definition.key)}
                        _append_log(job, f"Arc-length λ target {crossing.target:g} crossed at committed step {step['step']}: λ={crossing.achieved:.9g}. No interpolation was applied.")
                        return True
                    return False

                execution = session.run(
                    definition,
                    on_step_committed=on_step_committed,
                    should_stop_after_commit=stop_after_commit,
                    should_cancel=lambda: bool(job.get("cancelRequested")),
                )
                if stop_observed and execution.completed:
                    execution = _stopped_execution(execution)
                elif crossing and crossing.achieved is None and execution.completed:
                    execution = replace(execution, code=-5, outcome=_RunOutcome.STOPPED,
                                        message='Arc-length target not reached before the analysis ended.')
                    _append_log(job, f"Arc-length λ target {crossing.target:g} was not reached; stopping the chain.")

                committed = execution.committed_steps
                stage_entry["steps"] = (
                    len(execution.modal_result.modes)
                    if execution.modal_result is not None
                    else len(committed)
                )
                stage_entry["loadFactor"] = (
                    float(committed[-1].get("load_factor", 0.0)) if committed else 0.0
                )
                stage_entry["runtimeSeconds"] = round(float(execution.runtime_seconds), 3)
                stage_entry["outcome"] = str(execution.outcome.value if execution.outcome else execution.code)
                stage_entry["status"] = (
                    "completed"
                    if execution.completed
                    else "stopped"
                    if execution.outcome == _RunOutcome.STOPPED
                    else "cancelled"
                    if execution.outcome is AnalysisOutcome.CANCELLED
                    else "nonconverged"
                    if committed
                    else "failed"
                )

                if workflow and not stop_observed:
                    valid_stage = (execution.outcome is AnalysisOutcome.COMPLETED and
                                   (bool(committed) or execution.modal_result is not None))
                    if str(definition.name).lower() == 'vert' and committed:
                        valid_stage = valid_stage and math.isclose(float(committed[-1].get('load_factor', 0)), 1.0, rel_tol=0, abs_tol=1e-6)
                    if not valid_stage:
                        stage_entry['status'] = 'failed'
                        stage_entry['outcome'] = 'incomplete'
                hrx_state = _execution_to_hrx_state(execution)
                if workflow and stage_entry['status'] == 'failed':
                    hrx_state['State'] = 'ExecutedNotCompleted'
                job["analysisStates"][str(definition.key)] = hrx_state
                with _LOCK:
                    state_bucket = _MODEL_STATES.setdefault(job["modelSha256"], {})
                    state_bucket[str(definition.key)] = hrx_state

                if committed or execution.modal_result is not None:
                    with _LOCK:
                        bucket = _MODEL_EXECUTIONS.setdefault(job["modelSha256"], {})
                        bucket[str(definition.name)] = execution
                    executed_any = True
                    last_executed_name = str(definition.name)

                _append_log(
                    job,
                    f"Stage '{definition.name}' finished: outcome={stage_entry['outcome']}, "
                    f"steps={stage_entry['steps']}, runtime={stage_entry['runtimeSeconds']:.2f}s",
                )

                if stop_observed:
                    stopped_run = True
                    job["message"] = f"Stopped after a committed step in '{definition.name}'; saving results…"
                    _append_log(job, job["message"])
                    break

                if job.get("cancelRequested") or execution.outcome is AnalysisOutcome.CANCELLED:
                    cancelled_run = True
                    job["message"] = f"Cancelled during '{definition.name}'; saving committed results…"
                    break

                if ((workflow and stage_entry['status'] == 'failed') or not execution.completed or (not committed and execution.modal_result is None)) and idx < total_stages - 1:
                    _append_log(
                        job,
                        f"Stopping chain because predecessor '{definition.name}' ended as {stage_entry['outcome']} with {stage_entry['steps']} committed steps.",
                    )
                    break

            job["_acceptStop"] = False
            if executed_any:
                _append_log(job, f"Exporting self-contained .histra bundle to {job['bundlePath']}…")
                with _LOCK:
                    all_execs = dict(_MODEL_EXECUTIONS.get(job["modelSha256"], {}))
                    all_states = dict(_MODEL_STATES.get(job["modelSha256"], {}))
                    job["analysisStates"].update(all_states)
                _write_hrx_with_states(effective_hrx, all_states, temp_hrx_path)
                bundle_path = ResultsWriter.export_bundle(
                    model,
                    all_execs,
                    job["bundlePath"],
                    tier="all",
                    include_node_displacements=True,
                    metadata={"default_case": last_executed_name, **({"arc_lambda_target": {
                        "target": job['_arcLambdaTarget'], "analysisKey": int(job['targetKey']),
                        "analysisName": job['targetName'],
                        "reached": job['lambdaTargetResult'] is not None,
                        **(job['lambdaTargetResult'] or {}),
                    }} if job['_arcLambdaTarget'] is not None else {}), **({
                        "scour_workflow": workflow,
                        "scour_interface_keys": {str(k): v for k, v in stage_selections.items()},
                        "scour_selected_extents": {str(k): selected_scour_extent(group, v, workflow['direction']) for k, v in stage_selections.items()},
                        "intact_foundation_interface_keys": bottom_keys,
                    } if workflow else {})},
                )
                job["bundleReady"] = True
                job["bundleSize"] = bundle_path.stat().st_size if bundle_path.is_file() else 0
                _append_log(
                    job,
                    f"Saved .histra bundle: {bundle_path} ({job['bundleSize']:,} bytes, "
                    f"cases: {', '.join(all_execs.keys())})",
                )
                if on_complete is not None:
                    summary = on_complete(job)
                    if summary is not None:
                        job["resultSummary"] = summary

            last_stage = next(
                (s for s in reversed(job["stages"]) if s["status"] != "pending"),
                job["stages"][-1] if job["stages"] else None,
            )
            if stopped_run:
                job["status"] = job["outcome"] = "stopped"
                job["message"] = (f"Stopped; committed results saved to {job['bundleName']}." if job['bundleReady']
                                  else "Stopped before any results were available to save.")
            elif cancelled_run:
                job["status"] = job["outcome"] = "cancelled"
                job["message"] = (f"Cancelled; committed results saved to {job['bundleName']}." if job['bundleReady']
                                  else "Cancelled before any results were available to save.")
            else:
                job["progress"] = 100.0
                job["outcome"] = last_stage["outcome"] if last_stage else "completed"
                job["status"] = (
                    "completed"
                    if last_stage and last_stage["status"] in ("completed", "nonconverged") and
                       (not workflow or (last_stage["key"] == job["targetKey"] and last_stage["status"] == "completed"))
                    else "failed"
                )
                job["message"] = (
                    f"Completed '{last_executed_name}' ({last_stage['steps']} steps) · saved to {job['bundleName']}"
                    if job["status"] == "completed"
                    else f"Analysis '{last_executed_name}' ended as {job['outcome']}"
                )
                if job['lambdaTargetResult'] and job['status'] == 'completed':
                    result = job['lambdaTargetResult']
                    job['message'] += f" · λ target {result['target']:g} crossed at step {result['step']} (λ={result['achieved']:.9g})"
                elif job['_arcLambdaTarget'] is not None and not job['lambdaTargetResult'] and job['status'] == 'failed':
                    job['message'] += f" · λ target {job['_arcLambdaTarget']:g} was not reached"
    except Exception as exc:
        _append_log(job, f"ERROR: {type(exc).__name__}: {exc}")
        job["status"] = "failed"
        job["outcome"] = "failed"
        job["error"] = str(exc)
        job["message"] = f"Error: {exc}"
    finally:
        job.pop("_hrxBytes", None)
        shutil.rmtree(temp_dir, ignore_errors=True)
        job["finishedAt"] = time.time()
        job["runtimeSeconds"] = round(job["finishedAt"] - job["startedAt"], 3)
        with _LOCK:
            if _ACTIVE_JOB_ID == job["jobId"]:
                _ACTIVE_JOB_ID = None


def job_status(job_id: str | None = None, log_offset: int = 0) -> dict[str, Any]:
    with _LOCK:
        target_id = job_id or _ACTIVE_JOB_ID
        if not target_id or target_id not in _JOBS:
            if not job_id and _JOBS:
                target_id = next(reversed(_JOBS))
            else:
                raise ValueError("Solver job not found.")
        job = _JOBS[target_id]
        logs = job["logs"]
        offset = max(0, min(int(log_offset), len(logs)))
        runtime = (
            job["runtimeSeconds"]
            if job["finishedAt"] is not None
            else round(time.time() - job["startedAt"], 2)
        )
        return {
            "jobId": job["jobId"],
            "status": job["status"],
            "modelName": job["modelName"],
            "bundlePath": job["bundlePath"],
            "bundleName": job["bundleName"],
            "bundleReady": job["bundleReady"],
            "bundleSize": job["bundleSize"],
            "sourceId": job["sourceId"],
            "targetKey": job["targetKey"],
            "targetName": job["targetName"],
            "combinationRow": job["combinationRow"],
            "progress": job["progress"],
            "runtimeSeconds": runtime,
            "lambdaTargetResult": job["lambdaTargetResult"],
            "cancelRequested": job["cancelRequested"],
            "stopRequested": job["stopRequested"],
            "error": job["error"],
            "outcome": job["outcome"],
            "message": job["message"],
            "currentStage": dict(job["currentStage"]) if job["currentStage"] else None,
            "stages": [dict(s) for s in job["stages"]],
            "logs": logs[offset:],
            "logCount": len(logs),
            "analysisStates": dict(job["analysisStates"]),
            "resultSummary": job["resultSummary"],
        }


def stop_job(job_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        target_id = job_id or _ACTIVE_JOB_ID
        if not target_id or target_id not in _JOBS:
            raise ValueError("No active solver job found.")
        job = _JOBS[target_id]
        if job['status'] == 'running' and job.get('_acceptStop') and not job['stopRequested']:
            job['stopRequested'] = True
            job['message'] = 'Stop requested; waiting for the next committed step or stage boundary…'
            _append_log(job, job['message'])
    return job_status(target_id)


def cancel_job(job_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        target_id = job_id or _ACTIVE_JOB_ID
        if not target_id or target_id not in _JOBS:
            raise ValueError("No active solver job found.")
        job = _JOBS[target_id]
        if job["status"] == "running":
            job["cancelRequested"] = True
            _append_log(job, "Cancellation requested by user; stopping at next checkpoint…")
    return job_status(target_id)


def bundle_path_for_job(job_id: str | None = None) -> Path:
    with _LOCK:
        target_id = job_id or (_ACTIVE_JOB_ID if _ACTIVE_JOB_ID else (next(reversed(_JOBS)) if _JOBS else None))
        if not target_id or target_id not in _JOBS:
            raise ValueError("Solver job not found.")
        job = _JOBS[target_id]
        path = Path(job["bundlePath"])
        if not job.get("bundleReady") or not path.is_file():
            raise ValueError("The .histra result bundle is not ready yet.")
        return path
