from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from histra.solver.strategy_evidence import (
    CertifiedCandidateEvidence,
    ModelStrategyEvidence,
    clear_registered_strategy_evidence,
    find_model_strategy_evidence,
    get_registered_strategy_evidence,
    is_analysis_certified,
    load_strategy_evidence,
    register_strategy_evidence,
)


def _analysis(
    *,
    key: int = 1,
    name: str = "Vert",
    integration: str = "LoadControl",
    method: str = "ModifiedRegulaFalsiLineSearch",
    criterion: str = "ForceMoment",
    pdelta: str = "None",
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        name=name,
        integration_method=integration,
        method=method,
        adaptive_convergence_criteria=criterion,
        pdelta_effect=pdelta,
    )


def test_candidate_matches_exact_configuration() -> None:
    candidate = CertifiedCandidateEvidence(
        id="test-cand",
        target="Vert",
        integration_method="LoadControl",
        nonlinear_method="ModifiedRegulaFalsiLineSearch",
        convergence_criterion="ForceMoment",
        pdelta_effect="None",
        qualifies=True,
        unsafe_steps=0,
        completed=True,
        range_covered=True,
        reference_evidence_accepted=True,
    )
    analysis = _analysis()
    assert candidate.matches_analysis(analysis)


@pytest.mark.parametrize(
    ("qualifies", "unsafe_steps", "completed", "range_covered", "ref_accepted"),
    [
        (False, 0, True, True, True),
        (True, 1, True, True, True),  # strict equilibrium failure
        (True, 0, False, True, True),  # incomplete
        (True, 0, True, False, True),  # range not covered
        (True, 0, True, True, False),  # reference not accepted
    ],
)
def test_candidate_fails_closed_on_unverified_metrics(
    qualifies: bool,
    unsafe_steps: int,
    completed: bool,
    range_covered: bool,
    ref_accepted: bool,
) -> None:
    candidate = CertifiedCandidateEvidence(
        id="unverified",
        target="Vert",
        integration_method="LoadControl",
        nonlinear_method="ModifiedRegulaFalsiLineSearch",
        convergence_criterion="ForceMoment",
        qualifies=qualifies,
        unsafe_steps=unsafe_steps,
        completed=completed,
        range_covered=range_covered,
        reference_evidence_accepted=ref_accepted,
    )
    assert not candidate.matches_analysis(_analysis())


def test_candidate_rejects_mismatched_settings() -> None:
    candidate = CertifiedCandidateEvidence(
        id="test-cand",
        target="Vert",
        integration_method="LoadControl",
        nonlinear_method="ModifiedRegulaFalsiLineSearch",
        convergence_criterion="ForceMoment",
        qualifies=True,
        unsafe_steps=0,
        completed=True,
        range_covered=True,
        reference_evidence_accepted=True,
    )
    # Different integration
    assert not candidate.matches_analysis(_analysis(integration="ArcLength"))
    # Different method
    assert not candidate.matches_analysis(_analysis(method="StandardBisectionLineSearch"))
    # Different criterion
    assert not candidate.matches_analysis(_analysis(criterion="Work"))
    # Different target analysis name
    assert not candidate.matches_analysis(_analysis(name="OtherAnalysis"))


def test_candidate_matches_with_analysis_overrides() -> None:
    candidate = CertifiedCandidateEvidence(
        id="staged-cand",
        target="Second",
        integration_method="ArcLength",
        nonlinear_method="StandardBisectionLineSearch",
        convergence_criterion="ForceMoment",
        qualifies=True,
        unsafe_steps=0,
        completed=True,
        range_covered=True,
        reference_evidence_accepted=True,
        analysis_overrides={
            "Vert": {
                "method": "StandardBisectionLineSearch",
                "adaptive_convergence_criteria": "ForceMoment",
            }
        },
    )
    vert_analysis = _analysis(
        name="Vert",
        integration="LoadControl",
        method="StandardBisectionLineSearch",
        criterion="ForceMoment",
    )
    assert candidate.matches_analysis(vert_analysis)

    second_analysis = _analysis(
        name="Second",
        integration="ArcLength",
        method="StandardBisectionLineSearch",
        criterion="ForceMoment",
    )
    assert candidate.matches_analysis(second_analysis)


def test_model_strategy_evidence_sha_matching(tmp_path: Path) -> None:
    hrx_file = tmp_path / "test.hrx"
    hrx_file.write_text("<HiStrA></HiStrA>", encoding="utf-8")
    import hashlib

    real_sha = hashlib.sha256(hrx_file.read_bytes()).hexdigest()

    evidence = ModelStrategyEvidence(
        hrx_sha256=real_sha,
        hrx_path="test.hrx",
    )

    model = SimpleNamespace(source_path=str(hrx_file))
    assert evidence.matches_model(model)

    # Different SHA
    wrong_evidence = ModelStrategyEvidence(
        hrx_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        hrx_path="test.hrx",
    )
    assert not wrong_evidence.matches_model(model)


def test_direct_attachment_rejects_conflicting_model_sha(tmp_path: Path) -> None:
    hrx_file = tmp_path / "test.hrx"
    hrx_file.write_text("<HiStrA>Model A</HiStrA>", encoding="utf-8")
    import hashlib

    model = SimpleNamespace(
        source_path=str(hrx_file),
        _sha256=hashlib.sha256(hrx_file.read_bytes()).hexdigest(),
    )

    conflicting_evidence = ModelStrategyEvidence(
        hrx_sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        candidates=(
            CertifiedCandidateEvidence(
                id="conflicting",
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
        ),
    )

    # Even as explicit direct evidence, conflicting SHA must be rejected
    certified = is_analysis_certified(
        _analysis(), model=model, evidence=conflicting_evidence
    )
    assert certified is None


def test_load_strategy_evidence_from_mapping() -> None:
    data = {
        "scenario": "test scenario",
        "hrx": {
            "path": "test.hrx",
            "sha256": "abcdef123456",
        },
        "reference_evidence": {
            "accepted": True,
            "source": "C# Results",
            "source_sha256": "123456abcdef",
        },
        "results": [
            {
                "id": "cand1",
                "target": "Vert",
                "configuration": {
                    "target": {
                        "integration_method": "LoadControl",
                        "method": "ModifiedRegulaFalsiLineSearch",
                        "adaptive_convergence_criteria": "ForceMoment",
                    }
                },
                "qualifies": True,
                "unsafe_steps": 0,
                "completed": True,
                "range_covered": True,
                "reference_evidence_accepted": True,
            }
        ],
    }

    records = load_strategy_evidence(data)
    assert len(records) == 1
    rec = records[0]
    assert rec.scenario == "test scenario"
    assert rec.hrx_sha256 == "abcdef123456"
    assert len(rec.candidates) == 1
    assert rec.candidates[0].matches_analysis(_analysis())


def test_programmatic_registration() -> None:
    clear_registered_strategy_evidence()
    try:
        assert len(get_registered_strategy_evidence()) == 0
        evidence = ModelStrategyEvidence(
            hrx_sha256="test-sha",
            candidates=(
                CertifiedCandidateEvidence(
                    id="reg-cand",
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
            ),
        )
        register_strategy_evidence(evidence)
        assert len(get_registered_strategy_evidence()) == 1

        model = SimpleNamespace(_sha256="test-sha")
        candidate = is_analysis_certified(_analysis(), model=model)
        assert candidate is not None
        assert candidate.id == "reg-cand"
    finally:
        clear_registered_strategy_evidence()


def test_discovery_hierarchy_companion_file(tmp_path: Path) -> None:
    hrx_file = tmp_path / "sample.hrx"
    hrx_file.write_text("<HiStrA></HiStrA>", encoding="utf-8")
    import hashlib

    real_sha = hashlib.sha256(hrx_file.read_bytes()).hexdigest()

    companion = tmp_path / "sample.strategy_evidence.json"
    companion.write_text(
        json.dumps(
            {
                "hrx": {"sha256": real_sha, "path": str(hrx_file)},
                "reference_evidence": {"accepted": True, "source": "test", "source_sha256": "abc"},
                "results": [
                    {
                        "id": "companion-cand",
                        "target": "Vert",
                        "configuration": {
                            "target": {
                                "integration_method": "LoadControl",
                                "method": "ModifiedRegulaFalsiLineSearch",
                                "adaptive_convergence_criteria": "ForceMoment",
                            }
                        },
                        "qualifies": True,
                        "unsafe_steps": 0,
                        "completed": True,
                        "range_covered": True,
                        "reference_evidence_accepted": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    model = SimpleNamespace(source_path=str(hrx_file))
    candidate = is_analysis_certified(_analysis(), model=model)
    assert candidate is not None
    assert candidate.id == "companion-cand"
