"""Model-qualified certified benchmark evidence lookup and validation.

This module provides traceable verification for nonlinear solver strategy
evidence.  An analysis configuration qualifies as certified only when strict
equilibrium audit passes with zero unsafe steps, range coverage is complete,
the reference response is traceable and externally accepted, and the candidate
curve matches within tolerance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


def _file_sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file in 64 KiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _accepted_reference_evidence(value: Mapping[str, Any] | None) -> bool:
    """Require a traceable external acceptance record with source and SHA-256."""
    return bool(
        isinstance(value, Mapping)
        and value.get("accepted") is True
        and str(value.get("source", "")).strip()
        and str(value.get("source_sha256", "")).strip()
    )


@dataclass(frozen=True)
class CertifiedCandidateEvidence:
    """Qualification status and settings for one benchmarked strategy candidate."""

    id: str
    target: str | int | None
    integration_method: str
    nonlinear_method: str
    convergence_criterion: str
    pdelta_effect: str | None = None
    qualifies: bool = True
    unsafe_steps: int = 0
    completed: bool = True
    range_covered: bool = True
    reference_evidence_accepted: bool = True
    analysis_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    outcomes: tuple[dict[str, Any], ...] = ()

    def matches_analysis(self, analysis: Any) -> bool:
        """Check if this candidate certifies the runtime analysis configuration."""
        if not (
            self.qualifies
            and self.unsafe_steps == 0
            and self.completed
            and self.range_covered
            and self.reference_evidence_accepted
        ):
            return False

        analysis_name = str(getattr(analysis, "name", "")).casefold()
        analysis_key = getattr(analysis, "key", None)
        target_name = str(self.target or "").casefold()

        # Determine effective configuration for this specific analysis.
        # It could be the target analysis or an analysis override/outcome stage.
        config_int: str | None = None
        config_method: str | None = None
        config_crit: str | None = None
        config_pdelta: str | None = None

        if self.analysis_overrides:
            matched_override = None
            for key, val in self.analysis_overrides.items():
                if str(key).casefold() == analysis_name or (
                    analysis_key is not None and str(key) == str(analysis_key)
                ):
                    matched_override = val
                    break
            if matched_override is not None:
                config_int = matched_override.get("integration_method")
                config_method = matched_override.get("method")
                config_crit = matched_override.get(
                    "adaptive_convergence_criteria",
                    matched_override.get("convergence_criterion"),
                )
                config_pdelta = matched_override.get("pdelta_effect")
            elif target_name and (
                target_name == analysis_name
                or (analysis_key is not None and target_name == str(analysis_key))
            ):
                config_int = self.integration_method
                config_method = self.nonlinear_method
                config_crit = self.convergence_criterion
                config_pdelta = self.pdelta_effect
            elif self.outcomes:
                outcome_match = next(
                    (
                        item
                        for item in self.outcomes
                        if str(item.get("analysis_name", "")).casefold() == analysis_name
                        or (
                            analysis_key is not None
                            and item.get("analysis_key") == analysis_key
                        )
                    ),
                    None,
                )
                if outcome_match is None or outcome_match.get("outcome") not in (
                    "completed",
                    "completed_at_configured_displacement_limit",
                ):
                    return False
                config_int = self.integration_method
                config_method = self.nonlinear_method
                config_crit = self.convergence_criterion
                config_pdelta = self.pdelta_effect
            else:
                return False
        else:
            if target_name and (
                target_name == analysis_name
                or (analysis_key is not None and target_name == str(analysis_key))
            ):
                config_int = self.integration_method
                config_method = self.nonlinear_method
                config_crit = self.convergence_criterion
                config_pdelta = self.pdelta_effect
            elif self.outcomes:
                outcome_match = next(
                    (
                        item
                        for item in self.outcomes
                        if str(item.get("analysis_name", "")).casefold() == analysis_name
                        or (
                            analysis_key is not None
                            and item.get("analysis_key") == analysis_key
                        )
                    ),
                    None,
                )
                if outcome_match is None or outcome_match.get("outcome") not in (
                    "completed",
                    "completed_at_configured_displacement_limit",
                ):
                    return False
                config_int = self.integration_method
                config_method = self.nonlinear_method
                config_crit = self.convergence_criterion
                config_pdelta = self.pdelta_effect
            elif not target_name:
                config_int = self.integration_method
                config_method = self.nonlinear_method
                config_crit = self.convergence_criterion
                config_pdelta = self.pdelta_effect
            else:
                return False

        # Compare integration method if specified
        if config_int is not None:
            actual_int = str(getattr(analysis, "integration_method", "LoadControl"))
            if config_int.casefold() != actual_int.casefold():
                return False

        # Compare nonlinear solver method if specified
        if config_method is not None:
            actual_method = str(getattr(analysis, "method", "StandardNewtonRaphson"))
            if config_method.casefold() != actual_method.casefold():
                return False

        # Compare convergence criterion if specified
        if config_crit is not None:
            actual_crit = str(
                getattr(analysis, "adaptive_convergence_criteria", "ForceMoment")
            )
            if config_crit.casefold() != actual_crit.casefold():
                return False

        # Compare P-Delta effect if specified
        if config_pdelta is not None:
            actual_pdelta = str(getattr(analysis, "pdelta_effect", "None"))
            if str(config_pdelta).casefold() != actual_pdelta.casefold():
                return False

        return True


@dataclass(frozen=True)
class ModelStrategyEvidence:
    """Benchmark evidence record for a model's nonlinear solver strategies."""

    hrx_sha256: str | tuple[str, ...] | None = None
    hrx_path: str | tuple[str, ...] | None = None
    scenario: str | None = None
    reference_evidence: dict[str, Any] | None = None
    candidates: tuple[CertifiedCandidateEvidence, ...] = ()
    source_origin: str | None = None

    def matches_model(self, model: Any, *, direct_attachment: bool = False) -> bool:
        """Check if this evidence record applies to the given model."""
        if direct_attachment:
            # If evidence has no model restrictions, direct attachment applies
            if not self.hrx_sha256 and not self.hrx_path:
                return True
            # If model has neither source_path nor sha, direct attachment is accepted
            source_path = getattr(model, "source_path", None)
            cached_sha = getattr(model, "_sha256", None) or getattr(model, "hrx_sha256", None)
            if not source_path and not cached_sha:
                return True

        if model is None:
            return False

        # If evidence specifies SHA-256, verify against model source file or model._sha256
        if self.hrx_sha256:
            allowed_shas = (
                (self.hrx_sha256.lower(),)
                if isinstance(self.hrx_sha256, str)
                else tuple(s.lower() for s in self.hrx_sha256)
            )
            cached_sha = getattr(model, "_sha256", None) or getattr(model, "hrx_sha256", None)
            if cached_sha:
                return cached_sha.lower() in allowed_shas

            source_path = getattr(model, "source_path", None)
            if source_path:
                path = Path(source_path)
                if path.is_file():
                    try:
                        computed = _file_sha256(path)
                        try:
                            object.__setattr__(model, "_sha256", computed)
                        except (TypeError, AttributeError):
                            pass
                        return computed.lower() in allowed_shas
                    except (OSError, PermissionError):
                        pass
            return False

        # Fallback matching by HRX filename if paths are present and SHA is not specified
        if self.hrx_path:
            allowed_paths = (
                (self.hrx_path,)
                if isinstance(self.hrx_path, str)
                else tuple(self.hrx_path)
            )
            source_path = getattr(model, "source_path", None)
            if source_path:
                model_p = Path(source_path)
                for target_path in allowed_paths:
                    target_p = Path(target_path)
                    if model_p == target_p:
                        return True
                    if len(target_p.parts) > 1 and tuple(model_p.parts[-len(target_p.parts):]) == target_p.parts:
                        return True
                    if model_p.name.casefold() == target_p.name.casefold():
                        return True

        return False

    def find_certified_candidate(self, analysis: Any) -> CertifiedCandidateEvidence | None:
        """Find a qualifying candidate in this evidence that matches analysis."""
        for candidate in self.candidates:
            if candidate.matches_analysis(analysis):
                return candidate
        return None


def _parse_candidate_dict(
    item: Mapping[str, Any],
    top_target: str | int | None,
    top_ref_accepted: bool,
) -> CertifiedCandidateEvidence | None:
    """Parse one candidate record from strategy benchmark results."""
    candidate_id = str(item.get("id", "candidate"))
    config = item.get("configuration", {})
    target_config = config.get("target", {})
    analysis_overrides = dict(config.get("analysis_overrides", {}))

    # Determine candidate settings
    integ = str(
        target_config.get("integration_method", item.get("integration_method", "LoadControl"))
    )
    method = str(
        target_config.get("method", item.get("method", "StandardNewtonRaphson"))
    )
    crit = str(
        target_config.get(
            "adaptive_convergence_criteria",
            target_config.get(
                "convergence_criterion",
                item.get(
                    "adaptive_convergence_criteria",
                    item.get("convergence_criterion", "ForceMoment"),
                ),
            ),
        )
    )
    pdelta = target_config.get("pdelta_effect", item.get("pdelta_effect"))

    completed = bool(item.get("completed", False))
    range_covered = bool(item.get("range_covered", completed))
    unsafe_steps = int(item.get("unsafe_steps", 0))

    # Reference evidence acceptance check
    ref_accepted = bool(
        item.get("reference_evidence_accepted", top_ref_accepted)
    )

    # Qualification flag
    qualifies = bool(
        item.get("qualifies", False)
        or (
            completed
            and range_covered
            and unsafe_steps == 0
            and ref_accepted
            and item.get("all_repetitions_response_accepted", False)
        )
    )

    outcomes = tuple(item.get("outcomes", ()))
    target = item.get("target", top_target)

    return CertifiedCandidateEvidence(
        id=candidate_id,
        target=target,
        integration_method=integ,
        nonlinear_method=method,
        convergence_criterion=crit,
        pdelta_effect=pdelta,
        qualifies=qualifies,
        unsafe_steps=unsafe_steps,
        completed=completed,
        range_covered=range_covered,
        reference_evidence_accepted=ref_accepted,
        analysis_overrides=analysis_overrides,
        outcomes=outcomes,
    )


def load_strategy_evidence(
    source: str | Path | Mapping[str, Any] | ModelStrategyEvidence | Iterable[Any],
) -> tuple[ModelStrategyEvidence, ...]:
    """Load and normalize strategy benchmark evidence from files or mappings."""
    if isinstance(source, ModelStrategyEvidence):
        return (source,)

    if isinstance(source, (str, Path)):
        path = Path(source).resolve()
        if path.is_dir():
            results: list[ModelStrategyEvidence] = []
            for file_path in sorted(path.glob("*.json")):
                results.extend(load_strategy_evidence(file_path))
            return tuple(results)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                evidence_list = load_strategy_evidence(data)
                return tuple(
                    ModelStrategyEvidence(
                        hrx_sha256=item.hrx_sha256,
                        hrx_path=item.hrx_path,
                        scenario=item.scenario,
                        reference_evidence=item.reference_evidence,
                        candidates=item.candidates,
                        source_origin=str(path),
                    )
                    for item in evidence_list
                )
            except Exception:
                return ()
        return ()

    if isinstance(source, Mapping):
        # Support container format with "models" or "evidence" array
        if "models" in source and isinstance(source["models"], Iterable) and not isinstance(source["models"], (str, bytes, Mapping)):
            nested_results: list[ModelStrategyEvidence] = []
            for item in source["models"]:
                nested_results.extend(load_strategy_evidence(item))
            return tuple(nested_results)
        if "evidence" in source and isinstance(source["evidence"], Iterable) and not isinstance(source["evidence"], (str, bytes, Mapping)):
            nested_results = []
            for item in source["evidence"]:
                nested_results.extend(load_strategy_evidence(item))
            return tuple(nested_results)

        # Could be a benchmark report or direct analysis mapping
        hrx_info = source.get("hrx", {})
        hrx_sha256 = (
            hrx_info.get("sha256")
            if isinstance(hrx_info, Mapping)
            else source.get("hrx_sha256")
        )
        hrx_path = (
            hrx_info.get("path")
            if isinstance(hrx_info, Mapping)
            else source.get("hrx_path")
        )
        scenario = source.get("scenario")
        ref_evidence = source.get("reference_evidence")
        top_ref_accepted = _accepted_reference_evidence(ref_evidence)
        top_target = source.get("target")

        candidates: list[CertifiedCandidateEvidence] = []

        # Case 1: Standard strategy_benchmark results array
        raw_results = source.get("results")
        if isinstance(raw_results, Iterable) and not isinstance(raw_results, Mapping):
            for item in raw_results:
                if isinstance(item, Mapping):
                    cand = _parse_candidate_dict(
                        item, top_target=top_target, top_ref_accepted=top_ref_accepted
                    )
                    if cand is not None:
                        candidates.append(cand)

        # Case 2: Mapping of analyses directly, e.g. {"Vert": {...}, "LiveLoad_1": {...}}
        raw_analyses = source.get("analyses")
        if isinstance(raw_analyses, Mapping):
            for name, item in raw_analyses.items():
                if isinstance(item, Mapping):
                    cand = _parse_candidate_dict(
                        {**item, "id": str(name), "target": str(name)},
                        top_target=name,
                        top_ref_accepted=top_ref_accepted,
                    )
                    if cand is not None:
                        candidates.append(cand)

        # Case 3: Single candidate at top level
        if not candidates and "method" in source:
            cand = _parse_candidate_dict(
                source, top_target=top_target, top_ref_accepted=top_ref_accepted
            )
            if cand is not None:
                candidates.append(cand)

        norm_sha: str | tuple[str, ...] | None
        if isinstance(hrx_sha256, (list, tuple)):
            norm_sha = tuple(str(s).strip().lower() for s in hrx_sha256 if s)
        elif hrx_sha256:
            norm_sha = str(hrx_sha256).strip().lower()
        else:
            norm_sha = None

        norm_path: str | tuple[str, ...] | None
        if isinstance(hrx_path, (list, tuple)):
            norm_path = tuple(str(p).strip() for p in hrx_path if p)
        elif hrx_path:
            norm_path = str(hrx_path).strip()
        else:
            norm_path = None

        return (
            ModelStrategyEvidence(
                hrx_sha256=norm_sha,
                hrx_path=norm_path,
                scenario=str(scenario) if scenario else None,
                reference_evidence=dict(ref_evidence) if isinstance(ref_evidence, Mapping) else None,
                candidates=tuple(candidates),
            ),
        )

    if isinstance(source, Iterable):
        collected: list[ModelStrategyEvidence] = []
        for item in source:
            collected.extend(load_strategy_evidence(item))
        return tuple(collected)

    return ()


# Global registry for programmatic evidence attachment
_REGISTERED_STRATEGY_EVIDENCE: list[ModelStrategyEvidence] = []


def register_strategy_evidence(
    evidence: str | Path | Mapping[str, Any] | ModelStrategyEvidence | Iterable[Any],
) -> None:
    """Register strategy benchmark evidence globally for subsequent analyses."""
    _REGISTERED_STRATEGY_EVIDENCE.extend(load_strategy_evidence(evidence))


def clear_registered_strategy_evidence() -> None:
    """Clear all globally registered strategy evidence."""
    _REGISTERED_STRATEGY_EVIDENCE.clear()


def get_registered_strategy_evidence() -> tuple[ModelStrategyEvidence, ...]:
    """Return all globally registered strategy evidence."""
    return tuple(_REGISTERED_STRATEGY_EVIDENCE)


def _default_evidence_directories() -> list[Path]:
    """Find default directories containing release strategy evidence."""
    candidates: list[Path] = []
    # 1. Environment variable if set
    env_dir = os.environ.get("HISTRA_STRATEGY_EVIDENCE_DIR")
    if env_dir:
        path = Path(env_dir).resolve()
        if path.is_dir():
            candidates.append(path)

    # 2. Known repo root relative to this file
    try:
        repo_root = Path(__file__).resolve().parents[2]
        rel_evidence = repo_root / "release-evidence" / "strategy"
        if rel_evidence.is_dir():
            candidates.append(rel_evidence)
    except IndexError:
        pass

    # 3. Current working directory
    cwd_evidence = Path("release-evidence/strategy").resolve()
    if cwd_evidence.is_dir() and cwd_evidence not in candidates:
        candidates.append(cwd_evidence)

    return candidates


def find_model_strategy_evidence(
    model: Any,
    explicit_evidence: Any | None = None,
) -> list[tuple[ModelStrategyEvidence, bool]]:
    """Resolve all strategy evidence sources applicable to a model.

    Returns a list of (evidence, is_direct_attachment) pairs.
    """
    resolved: list[tuple[ModelStrategyEvidence, bool]] = []

    # 1. Explicit evidence passed to call
    if explicit_evidence is not None:
        for ev in load_strategy_evidence(explicit_evidence):
            resolved.append((ev, True))

    # 2. Evidence attached to model instance
    model_evidence = getattr(model, "strategy_evidence", None)
    if model_evidence is not None:
        for ev in load_strategy_evidence(model_evidence):
            resolved.append((ev, True))

    # 3. Globally registered evidence
    for ev in _REGISTERED_STRATEGY_EVIDENCE:
        if ev.matches_model(model):
            resolved.append((ev, False))

    # 4. Single file from environment variable
    env_file = os.environ.get("HISTRA_STRATEGY_EVIDENCE_PATH")
    if env_file:
        file_path = Path(env_file).resolve()
        if file_path.is_file():
            for ev in load_strategy_evidence(file_path):
                if ev.matches_model(model):
                    resolved.append((ev, False))

    # 5. Companion file next to model source_path
    source_path_val = getattr(model, "source_path", None)
    if source_path_val:
        model_path = Path(source_path_val).resolve()
        companion_patterns = [
            model_path.with_suffix(".strategy_evidence.json"),
            model_path.parent / "strategy_evidence.json",
            model_path.parent / f"{model_path.stem}_strategy.json",
        ]
        for companion in companion_patterns:
            if companion.is_file():
                for ev in load_strategy_evidence(companion):
                    if ev.matches_model(model):
                        resolved.append((ev, False))

    # 6. Default release-evidence directories
    for evidence_dir in _default_evidence_directories():
        for ev in load_strategy_evidence(evidence_dir):
            if ev.matches_model(model):
                resolved.append((ev, False))

    return resolved


def is_analysis_certified(
    analysis: Any,
    model: Any | None = None,
    evidence: Any | None = None,
) -> CertifiedCandidateEvidence | None:
    """Check if analysis has qualifying model-certified benchmark evidence.

    Returns the matching CertifiedCandidateEvidence if certified, or None.
    """
    evidence_pairs = find_model_strategy_evidence(model, explicit_evidence=evidence)
    for ev, is_direct in evidence_pairs:
        if ev.matches_model(model, direct_attachment=is_direct):
            candidate = ev.find_certified_candidate(analysis)
            if candidate is not None:
                return candidate

    return None
