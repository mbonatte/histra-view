"""Evidence-based advisories for nonlinear solver configuration.

The advisor is deliberately read-only: it explains potentially unsafe or
inefficient choices but never rewrites the HRX analysis definition.  Stable
codes make the messages suitable for backend logs and automated filtering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import warnings

from histra.solver.strategy_evidence import (
    CertifiedCandidateEvidence,
    ModelStrategyEvidence,
    clear_registered_strategy_evidence,
    find_model_strategy_evidence,
    is_analysis_certified,
    load_strategy_evidence,
    register_strategy_evidence,
)


STRATEGY_GUIDE = "docs/nonlinear_convergence_safety.md"


class SuboptimalSolverStrategyWarning(UserWarning):
    """A supported analysis uses a strategy that is not recommended."""


@dataclass(frozen=True)
class SolverStrategyAdvisory:
    code: str
    analysis_key: int
    analysis_name: str
    integration_method: str
    nonlinear_method: str
    convergence_criterion: str
    reason: str
    recommendation: str
    documentation: str = STRATEGY_GUIDE

    def format_message(self) -> str:
        return (
            f"{self.code}: analysis={self.analysis_name!r} "
            f"(key={self.analysis_key}), integration={self.integration_method}, "
            f"method={self.nonlinear_method}, criterion={self.convergence_criterion}. "
            f"{self.reason} Recommendation: {self.recommendation}. "
            f"See {self.documentation}."
        )

    @property
    def identity(self) -> tuple[str, int, str, str, str]:
        return (
            self.code,
            self.analysis_key,
            self.integration_method,
            self.nonlinear_method,
            self.convergence_criterion,
        )


@dataclass(frozen=True)
class SolverStrategyReport:
    advisories: tuple[SolverStrategyAdvisory, ...]
    certified_analyses: tuple[str, ...] = ()

    @property
    def recommended(self) -> bool:
        return not self.advisories

    def is_certified(self, analysis_name_or_key: str | int) -> bool:
        target = str(analysis_name_or_key).casefold()
        return any(item.casefold() == target for item in self.certified_analyses)


def normalize_strategy_policy(value: str) -> str:
    normalized = str(value).strip().casefold()
    if normalized not in {"warn", "off"}:
        raise ValueError("strategy_policy must be 'warn' or 'off'.")
    return normalized


def _analysis_advisories(
    analysis: Any,
    model: Any | None = None,
    strategy_evidence: Any | None = None,
) -> tuple[SolverStrategyAdvisory, ...]:
    if int(getattr(analysis, "analysis_type", 2)) == 5:
        return ()

    key = int(getattr(analysis, "key", -1))
    name = str(getattr(analysis, "name", key))
    integration = str(getattr(analysis, "integration_method", "LoadControl"))
    method = str(getattr(analysis, "method", "StandardNewtonRaphson"))
    criterion = str(
        getattr(analysis, "adaptive_convergence_criteria", "ForceMoment")
    )
    result: list[SolverStrategyAdvisory] = []

    if criterion in {"Work", "DispRotation"}:
        result.append(
            SolverStrategyAdvisory(
                code="HISTRA-STRATEGY-001",
                analysis_key=key,
                analysis_name=name,
                integration_method=integration,
                nonlinear_method=method,
                convergence_criterion=criterion,
                reason=(
                    f"{criterion} can satisfy its incremental test while the active-DOF "
                    "force residual remains above the independent equilibrium limit"
                ),
                recommendation=(
                    "use ForceMoment for production equilibrium, or retain the authored "
                    "criterion only with equilibrium_policy='error'"
                ),
            )
        )

    if integration in {"ArcLength", "ArcLengthLinear"} and method.startswith("Modified"):
        result.append(
            SolverStrategyAdvisory(
                code="HISTRA-STRATEGY-002",
                analysis_key=key,
                analysis_name=name,
                integration_method=integration,
                nonlinear_method=method,
                convergence_criterion=criterion,
                reason=(
                    "the modified method retains an earlier tangent and has shown slower "
                    "or stalled convergence on strongly nonlinear live-load stages"
                ),
                recommendation=(
                    "benchmark StandardBisectionLineSearch for this ArcLength stage "
                    "and keep the independently audited response"
                ),
            )
        )

    if (
        integration in {"ArcLength", "ArcLengthLinear"}
        and criterion == "ForceMoment"
        and method != "StandardBisectionLineSearch"
    ):
        result.append(
            SolverStrategyAdvisory(
                code="HISTRA-STRATEGY-003",
                analysis_key=key,
                analysis_name=name,
                integration_method=integration,
                nonlinear_method=method,
                convergence_criterion=criterion,
                reason=(
                    "the current coarse Article live-load matrix qualifies only "
                    "StandardBisectionLineSearch over its measured five-step range"
                ),
                recommendation=(
                    "benchmark StandardBisectionLineSearch for this model and retain "
                    "the selected method only if the full safe response qualifies"
                ),
            )
        )

    # Check if a model-qualified certified benchmark evidence record exists
    # that qualifies this analysis configuration.
    certified = is_analysis_certified(
        analysis, model=model, evidence=strategy_evidence
    )
    if certified is None:
        result.append(
            SolverStrategyAdvisory(
                code="HISTRA-STRATEGY-004",
                analysis_key=key,
                analysis_name=name,
                integration_method=integration,
                nonlinear_method=method,
                convergence_criterion=criterion,
                reason=(
                    "no signed full-range, model-qualified strategy evidence is attached "
                    "to this analysis configuration"
                ),
                recommendation=(
                    "run the strict strategy matrix against a traceable accepted response "
                    "before treating this configuration as recommended"
                ),
            )
        )

    return tuple(result)


def inspect_solver_strategy(
    model: Any,
    analysis_names: Iterable[int | str | Any],
    *,
    strategy_evidence: Any | None = None,
) -> SolverStrategyReport:
    """Inspect named analyses without mutating the model.

    Evaluates the solver configurations (integration method, nonlinear algorithm,
    and convergence criterion) against safety and convergence heuristics. The advisor
    is read-only: it warns about potentially unsafe or non-convergent settings (such
    as unverified line-search or deceptive work-norm convergence) and certifies models
    with signed strategy evidence.

    Parameters
    ----------
    model : Model
        Structural model containing configured analyses in its collection.
    analysis_names : Iterable[int | str | Any]
        One or more analysis identifiers (keys, names, or Analysis instances) to inspect.
    strategy_evidence : ModelStrategyEvidence | None, optional
        Optional model strategy evidence container. If omitted, checks registered
        or bundled evidence.

    Returns
    -------
    SolverStrategyReport
        Summary report containing advisories and certified analysis names.

    Raises
    ------
    ValueError
        If an analysis key or name cannot be found or resolves ambiguously.

    Examples
    --------
    >>> from histra import load_model, inspect_solver_strategy
    >>> model = load_model("path/to/model.hrx")  # doctest: +SKIP
    >>> report = inspect_solver_strategy(model, ["Vert", "Live"])  # doctest: +SKIP
    >>> report.has_advisories  # doctest: +SKIP
    False
    """
    collections = getattr(model, "collections", None)
    if collections is None:
        raise ValueError("Model.collections is not initialized.")
    analyses = getattr(collections, "analyses", {})
    by_name: dict[str, list[Any]] = {}
    for analysis in analyses.values():
        by_name.setdefault(str(getattr(analysis, "name", "")).casefold(), []).append(
            analysis
        )

    selected: list[Any] = []
    for requested in analysis_names:
        if hasattr(requested, "key") and hasattr(requested, "name"):
            selected.append(requested)
        elif isinstance(requested, int) or str(requested).lstrip("-").isdigit():
            key = int(requested)
            if key not in analyses:
                raise ValueError(f"Analysis key {key} is absent from the model.")
            selected.append(analyses[key])
        else:
            name = str(requested)
            matches = by_name.get(name.casefold(), [])
            if len(matches) != 1:
                raise ValueError(
                    f"Expected exactly one analysis named {name!r}, found {len(matches)}."
                )
            selected.append(matches[0])

    advisories: list[SolverStrategyAdvisory] = []
    certified_list: list[str] = []
    for analysis in selected:
        adv = _analysis_advisories(
            analysis, model=model, strategy_evidence=strategy_evidence
        )
        advisories.extend(adv)
        if is_analysis_certified(analysis, model=model, evidence=strategy_evidence) is not None:
            a_name = str(getattr(analysis, "name", getattr(analysis, "key", "")))
            if a_name and a_name not in certified_list:
                certified_list.append(a_name)

    return SolverStrategyReport(
        advisories=tuple(advisories),
        certified_analyses=tuple(certified_list),
    )


def emit_strategy_advisories(
    analysis: Any,
    *,
    policy: str,
    on_log: Any | None,
    emitted: set[tuple[str, int, str, str, str]] | None = None,
    model: Any | None = None,
    strategy_evidence: Any | None = None,
) -> tuple[SolverStrategyAdvisory, ...]:
    """Emit each advisory once through warnings and the solver log."""
    if normalize_strategy_policy(policy) == "off":
        return ()
    emitted_keys = emitted if emitted is not None else set()
    delivered: list[SolverStrategyAdvisory] = []
    for advisory in _analysis_advisories(
        analysis, model=model, strategy_evidence=strategy_evidence
    ):
        if advisory.identity in emitted_keys:
            continue
        emitted_keys.add(advisory.identity)
        message = advisory.format_message()
        warnings.warn(message, SuboptimalSolverStrategyWarning, stacklevel=3)
        if on_log is not None:
            on_log(f"WARNING {message}")
        delivered.append(advisory)
    return tuple(delivered)


__all__ = [
    "CertifiedCandidateEvidence",
    "ModelStrategyEvidence",
    "SolverStrategyAdvisory",
    "SolverStrategyReport",
    "SuboptimalSolverStrategyWarning",
    "clear_registered_strategy_evidence",
    "emit_strategy_advisories",
    "find_model_strategy_evidence",
    "inspect_solver_strategy",
    "is_analysis_certified",
    "load_strategy_evidence",
    "normalize_strategy_policy",
    "register_strategy_evidence",
]
