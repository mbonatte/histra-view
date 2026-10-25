from __future__ import annotations

from types import SimpleNamespace
import warnings

import pytest

from histra import (
    SuboptimalSolverStrategyWarning,
    inspect_solver_strategy,
)
from histra.solver.session import AnalysisSession


def _analysis(
    *,
    key: int = 1,
    name: str = "Live",
    integration: str = "ArcLength",
    method: str = "ModifiedRegulaFalsiLineSearch",
    criterion: str = "Work",
    analysis_type: int = 2,
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        name=name,
        initial_analysis_key=-100,
        integration_method=integration,
        method=method,
        adaptive_convergence_criteria=criterion,
        analysis_type=analysis_type,
        pdelta_effect="None",
        max_u=1.0,
    )


def _model(*analyses: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        collections=SimpleNamespace(analyses={item.key: item for item in analyses}),
        gdl=1,
    )


def test_strategy_inspection_is_read_only_and_structured() -> None:
    analysis = _analysis()
    model = _model(analysis)

    report = inspect_solver_strategy(model, ["Live"])

    assert not report.recommended
    assert [item.code for item in report.advisories] == [
        "HISTRA-STRATEGY-001",
        "HISTRA-STRATEGY-002",
        "HISTRA-STRATEGY-004",
    ]
    assert analysis.method == "ModifiedRegulaFalsiLineSearch"
    assert analysis.adaptive_convergence_criteria == "Work"


def test_unqualified_force_moment_arc_length_method_has_advisory() -> None:
    analysis = _analysis(
        method="StandardRegulaFalsiLineSearch",
        criterion="ForceMoment",
    )

    report = inspect_solver_strategy(_model(analysis), [1])

    assert [item.code for item in report.advisories] == [
        "HISTRA-STRATEGY-003",
        "HISTRA-STRATEGY-004",
    ]


def test_force_moment_bisection_is_explicitly_unqualified_without_model_evidence() -> None:
    analysis = _analysis(
        method="StandardBisectionLineSearch",
        criterion="ForceMoment",
    )

    report = inspect_solver_strategy(_model(analysis), [1])
    assert not report.recommended
    assert [item.code for item in report.advisories] == ["HISTRA-STRATEGY-004"]


def test_session_emits_warning_and_log_once(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _analysis()
    model = _model(analysis)
    logs: list[str] = []
    monkeypatch.setattr(
        "histra.solver.session.solve_static_nonlinear",
        lambda *args, **kwargs: (
            0,
            [
                {
                    "step": 1,
                    "status": "OK",
                    "exit_code": 0,
                    "u": [0.0],
                    "reaction_x": 0.0,
                    "reaction_y": 0.0,
                    "reaction_z": 0.0,
                }
            ],
        ),
    )
    session = AnalysisSession(model, on_log=logs.append)

    with pytest.warns(SuboptimalSolverStrategyWarning) as captured:
        session.run("Live")

    assert len(captured) == 3
    assert sum("HISTRA-STRATEGY-001" in item for item in logs) == 1
    assert sum("HISTRA-STRATEGY-002" in item for item in logs) == 1
    assert sum("HISTRA-STRATEGY-004" in item for item in logs) == 1


def test_strategy_policy_off_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _analysis()
    model = _model(analysis)
    monkeypatch.setattr(
        "histra.solver.session.solve_static_nonlinear",
        lambda *args, **kwargs: (0, []),
    )
    session = AnalysisSession(model, strategy_policy="off")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        session.run("Live")

    assert not captured


@pytest.mark.parametrize("policy", ["", "error", "ignore"])
def test_strategy_policy_rejects_unknown_values(policy: str) -> None:
    with pytest.raises(ValueError, match="strategy_policy"):
        AnalysisSession(_model(_analysis()), strategy_policy=policy)


def test_certified_evidence_clears_strategy_004() -> None:
    from histra import CertifiedCandidateEvidence, ModelStrategyEvidence

    analysis = _analysis(
        name="Vert",
        integration="LoadControl",
        method="ModifiedRegulaFalsiLineSearch",
        criterion="ForceMoment",
    )
    evidence = ModelStrategyEvidence(
        candidates=(
            CertifiedCandidateEvidence(
                id="test-evidence",
                target="Vert",
                integration_method="LoadControl",
                nonlinear_method="ModifiedRegulaFalsiLineSearch",
                convergence_criterion="ForceMoment",
                qualifies=True,
                unsafe_steps=0,
                completed=True,
                range_covered=True,
                reference_evidence_accepted=True,
            ),
        )
    )
    model = _model(analysis)
    report = inspect_solver_strategy(model, ["Vert"], strategy_evidence=evidence)

    assert report.recommended
    assert report.advisories == ()
    assert report.certified_analyses == ("Vert",)
    assert report.is_certified("Vert")


def test_certified_evidence_retains_unsafe_warnings_when_configuration_is_unsafe() -> None:
    from histra import CertifiedCandidateEvidence, ModelStrategyEvidence

    # Analysis uses Work criterion (unsafe)
    analysis = _analysis(
        name="Vert",
        integration="LoadControl",
        method="ModifiedRegulaFalsiLineSearch",
        criterion="Work",
    )
    # Evidence only certified ForceMoment
    evidence = ModelStrategyEvidence(
        candidates=(
            CertifiedCandidateEvidence(
                id="safe-candidate",
                target="Vert",
                integration_method="LoadControl",
                nonlinear_method="ModifiedRegulaFalsiLineSearch",
                convergence_criterion="ForceMoment",
                qualifies=True,
                unsafe_steps=0,
                completed=True,
                range_covered=True,
                reference_evidence_accepted=True,
            ),
        )
    )
    model = _model(analysis)
    report = inspect_solver_strategy(model, ["Vert"], strategy_evidence=evidence)

    assert not report.recommended
    codes = [item.code for item in report.advisories]
    assert "HISTRA-STRATEGY-001" in codes
    assert "HISTRA-STRATEGY-004" in codes
    assert report.certified_analyses == ()


def test_session_with_certified_evidence_emits_zero_strategy_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from histra import CertifiedCandidateEvidence, ModelStrategyEvidence

    analysis = _analysis(
        name="Vert",
        integration="LoadControl",
        method="ModifiedRegulaFalsiLineSearch",
        criterion="ForceMoment",
    )
    evidence = ModelStrategyEvidence(
        candidates=(
            CertifiedCandidateEvidence(
                id="safe-evidence",
                target="Vert",
                integration_method="LoadControl",
                nonlinear_method="ModifiedRegulaFalsiLineSearch",
                convergence_criterion="ForceMoment",
                qualifies=True,
                unsafe_steps=0,
                completed=True,
                range_covered=True,
                reference_evidence_accepted=True,
            ),
        )
    )
    model = _model(analysis)
    monkeypatch.setattr(
        "histra.solver.session.solve_static_nonlinear",
        lambda *args, **kwargs: (
            0,
            [
                {
                    "step": 1,
                    "status": "OK",
                    "exit_code": 0,
                    "u": [0.0],
                    "reaction_x": 0.0,
                    "reaction_y": 0.0,
                    "reaction_z": 0.0,
                }
            ],
        ),
    )
    session = AnalysisSession(model, strategy_evidence=evidence)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        session.run("Vert")

    strategy_warnings = [
        w for w in captured if issubclass(w.category, SuboptimalSolverStrategyWarning)
    ]
    assert len(strategy_warnings) == 0


def test_benchmark_models_vert_and_live_load_certified_via_release_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path
    from histra import load_model

    hrx_path = Path(__file__).resolve().parents[1] / "model-live" / "model.hrx"
    if not hrx_path.exists():
        pytest.skip("model-live/model.hrx not present")

    model = load_model(hrx_path)
    # Configure Vert and LiveLoad_1 with the qualified ForceMoment strategies
    model.collections.analyses[1].adaptive_convergence_criteria = "ForceMoment"
    model.collections.analyses[22].adaptive_convergence_criteria = "ForceMoment"
    model.collections.analyses[22].method = "StandardBisectionLineSearch"

    report = inspect_solver_strategy(model, ["Vert", "LiveLoad_1"])
    assert report.recommended
    assert report.advisories == ()
    assert "Vert" in report.certified_analyses
    assert "LiveLoad_1" in report.certified_analyses
    assert report.is_certified("Vert")
    assert report.is_certified("LiveLoad_1")

    # Run in AnalysisSession to confirm end-to-end zero warnings
    monkeypatch.setattr(
        "histra.solver.session.solve_static_nonlinear",
        lambda *args, **kwargs: (
            0,
            [
                {
                    "step": 1,
                    "status": "OK",
                    "exit_code": 0,
                    "u": [0.0],
                    "reaction_x": 0.0,
                    "reaction_y": 0.0,
                    "reaction_z": 0.0,
                }
            ],
        ),
    )
    session = AnalysisSession(model)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        session.run("Vert")
        session.run("LiveLoad_1")

    strategy_warnings = [
        w for w in captured if issubclass(w.category, SuboptimalSolverStrategyWarning)
    ]
    assert len(strategy_warnings) == 0

