from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from histra.io import load_model
from histra.solver.cancellation import CANCELLED_EXIT_CODE, SolverCancelled, raise_if_cancelled
from histra.solver.capabilities import inspect_solver_capabilities
from histra.solver.outcomes import (
    AnalysisExecution,
    AnalysisOutcome,
    AnalysisStep,
    classify_analysis_outcome,
)
from histra.solver.output_projection import (
    OutputProjectionError,
    UnsupportedOutputError,
    project_analysis_outputs,
    project_reactions,
)


@dataclass(frozen=True)
class StepRequest:
    enabled: bool = True
    all_steps: bool = True
    step: int | None = None


@dataclass(frozen=True)
class OutputRequest:
    reactions: StepRequest
    displacements: StepRequest
    modal_contributions: StepRequest


def _committed(step: int, reaction: tuple[float, float, float]) -> AnalysisStep:
    return AnalysisStep.from_mapping(
        {
            "step": step,
            "status": "OK",
            "exit_code": 0,
            "u": np.array([float(step)]),
            "reaction_x": reaction[0],
            "reaction_y": reaction[1],
            "reaction_z": reaction[2],
        }
    )


def test_analysis_step_preserves_legacy_mapping_access() -> None:
    step = _committed(2, (1.0, 2.0, 3.0))

    assert step["step"] == 2
    assert step.get("status") == "OK"
    assert np.array_equal(step["u"], np.array([2.0]))
    assert dict(step)["reaction_z"] == 3.0


def test_displacement_limit_is_a_completed_outcome() -> None:
    terminal = AnalysisStep.from_mapping(
        {
            "step": 7,
            "status": "FAILED",
            "exit_code": -3,
            "u": np.zeros(1),
            "max_element_displacement": 0.125,
        }
    )
    analysis = SimpleNamespace(max_u=0.1)

    outcome = classify_analysis_outcome(-3, (terminal,), analysis)

    assert outcome is AnalysisOutcome.COMPLETED_AT_DISPLACEMENT_LIMIT


def test_cancellation_has_a_distinct_outcome() -> None:
    cancelled = AnalysisStep.from_mapping(
        {
            "step": 1,
            "status": "CANCELLED",
            "exit_code": CANCELLED_EXIT_CODE,
            "u": np.zeros(1),
        }
    )

    assert classify_analysis_outcome(
        CANCELLED_EXIT_CODE, (cancelled,), SimpleNamespace(max_u=1.0)
    ) is AnalysisOutcome.CANCELLED
    with pytest.raises(SolverCancelled):
        raise_if_cancelled(lambda: True)


def test_reaction_projection_includes_step_zero_and_committed_steps() -> None:
    execution = AnalysisExecution(
        analysis_key=3,
        analysis_name="Live",
        code=0,
        steps=(_committed(1, (10.0, 20.0, 30.0)), _committed(2, (11.0, 21.0, 31.0))),
        runtime_seconds=0.1,
        outcome=AnalysisOutcome.COMPLETED,
        initial_step=AnalysisStep.initial(np.zeros(1), reaction_x=1.0, reaction_y=2.0, reaction_z=3.0),
    )

    assert project_reactions(execution, StepRequest(all_steps=True)) == [
        {"Step": 0, "R1": 1.0, "R2": 2.0, "R3": 3.0},
        {"Step": 1, "R1": 10.0, "R2": 20.0, "R3": 30.0},
        {"Step": 2, "R1": 11.0, "R2": 21.0, "R3": 31.0},
    ]
    assert project_reactions(execution, StepRequest(all_steps=False, step=None)) == [
        {"Step": 2, "R1": 11.0, "R2": 21.0, "R3": 31.0}
    ]
    assert project_reactions(execution, StepRequest(all_steps=False, step=0)) == [
        {"Step": 0, "R1": 1.0, "R2": 2.0, "R3": 3.0}
    ]


def test_reaction_projection_rejects_missing_step() -> None:
    execution = AnalysisExecution(
        analysis_key=1,
        analysis_name="A",
        code=0,
        steps=(_committed(1, (1.0, 2.0, 3.0)),),
        runtime_seconds=0.0,
        outcome=AnalysisOutcome.COMPLETED,
        initial_step=AnalysisStep.initial(np.zeros(1)),
    )
    with pytest.raises(OutputProjectionError, match="Requested step 99"):
        project_reactions(execution, StepRequest(all_steps=False, step=99))


def test_output_projection_rejects_uninitialized_model() -> None:
    execution = AnalysisExecution(
        analysis_key=1, analysis_name="A", code=0,
        steps=(_committed(1, (1.0, 2.0, 3.0)),), runtime_seconds=0.0,
        outcome=AnalysisOutcome.COMPLETED,
        initial_step=AnalysisStep.initial(np.zeros(1)),
    )
    request = OutputRequest(
        reactions=StepRequest(enabled=False),
        displacements=StepRequest(enabled=True),
        modal_contributions=StepRequest(enabled=False),
    )
    with pytest.raises(OutputProjectionError, match="Model.collections"):
        project_analysis_outputs(object(), execution, request)


def test_output_projection_includes_modal_summary() -> None:
    modal_result = SimpleNamespace(
        as_dict=lambda include_shapes=False: {
            "converged_modes": 2,
            "include_shapes": include_shapes,
        }
    )
    execution = AnalysisExecution(
        analysis_key=30,
        analysis_name="Modal",
        code=0,
        steps=(),
        runtime_seconds=0.1,
        outcome=AnalysisOutcome.COMPLETED,
        initial_step=AnalysisStep.initial(np.zeros(3)),
        modal_result=modal_result,
    )
    request = SimpleNamespace(
        include_modal_shapes=True,
        reactions=StepRequest(enabled=False),
        displacements=StepRequest(enabled=False),
        modal_contributions=StepRequest(enabled=False),
    )

    assert project_analysis_outputs(SimpleNamespace(collections=object()), execution, request) == {
        "modal_analysis": {"converged_modes": 2, "include_shapes": True}
    }


def test_capability_preflight_resolves_dependencies_and_outputs() -> None:
    root = SimpleNamespace(key=1, name="Root", initial_analysis_key=-100, pdelta_effect=False)
    child = SimpleNamespace(key=2, name="Child", initial_analysis_key=1, pdelta_effect=False)
    model = SimpleNamespace(collections=SimpleNamespace(analyses={1: root, 2: child}))
    request = OutputRequest(
        reactions=StepRequest(enabled=True),
        displacements=StepRequest(enabled=False),
        modal_contributions=StepRequest(enabled=False),
    )

    report = inspect_solver_capabilities(
        model,
        ["Child"],
        output_requests={"Child": request},
    )

    assert report.supported
    assert report.issues == ()


@pytest.mark.parametrize("pdelta", ["EachStep", "EachIteration", 1, 2])
def test_capability_preflight_supports_static_pdelta(pdelta: object) -> None:
    analysis = SimpleNamespace(
        key=1,
        name="PDelta",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="ArcLength",
        method="StandardRegulaFalsiLineSearch",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect=pdelta,
    )
    model = SimpleNamespace(collections=SimpleNamespace(analyses={1: analysis}))

    assert inspect_solver_capabilities(model, ["PDelta"]).supported


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("analysis_type", 4, "DYNAMIC_ANALYSIS_UNSUPPORTED"),
        ("integration_method", "NewmarkMethod", "STATIC_INTEGRATOR_UNSUPPORTED"),
        ("method", "BFGS", "NONLINEAR_METHOD_UNSUPPORTED"),
        ("adaptive_convergence_criteria", "RelativeWork", "CONVERGENCE_CRITERION_UNSUPPORTED"),
        ("pdelta_effect", "FutureMode", "PDELTA_EFFECT_UNSUPPORTED"),
        ("type_load_distribution", "FutureDistribution", "LOAD_DISTRIBUTION_UNSUPPORTED"),
    ],
)
def test_capability_preflight_rejects_unsupported_solver_enums(
    field: str,
    value: object,
    code: str,
) -> None:
    analysis = SimpleNamespace(
        key=1,
        name="Unsupported",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="LoadControl",
        method="ModifiedNewtonRaphson",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect="None",
    )
    setattr(analysis, field, value)
    model = SimpleNamespace(collections=SimpleNamespace(analyses={1: analysis}))

    report = inspect_solver_capabilities(model, ["Unsupported"])

    assert not report.supported
    assert code in {issue.code for issue in report.issues}


@pytest.mark.parametrize("distribution", ["Modal", "Triangular", "Adaptive", "ShearFloor"])
def test_capability_preflight_rejects_unimplemented_static_load_distributions(
    distribution: str,
) -> None:
    analysis = SimpleNamespace(
        key=1,
        name="Static",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="LoadControl",
        method="StandardNewtonRaphson",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect="None",
        type_load_distribution=distribution,
    )
    model = SimpleNamespace(collections=SimpleNamespace(analyses={1: analysis}))

    report = inspect_solver_capabilities(model, ["Static"])

    assert not report.supported
    assert {issue.code for issue in report.issues} == {
        "STATIC_LOAD_DISTRIBUTION_UNSUPPORTED"
    }


def test_capability_preflight_accepts_explicit_static_force_and_combination_distributions() -> None:
    analyses = {
        key: SimpleNamespace(
            key=key,
            name=distribution,
            initial_analysis_key=-100,
            analysis_type=2,
            integration_method="LoadControl",
            method="StandardNewtonRaphson",
            adaptive_convergence_criteria="ForceMoment",
            pdelta_effect="None",
            type_load_distribution=distribution,
        )
        for key, distribution in enumerate(("Force", "LoadCombination"), start=1)
    }
    model = SimpleNamespace(collections=SimpleNamespace(analyses=analyses))

    assert inspect_solver_capabilities(model, ["Force", "LoadCombination"]).supported


def test_loader_preserves_csharp_force_control_metadata(tmp_path) -> None:
    hrx = tmp_path / "analysis-controls.hrx"
    hrx.write_text(
        '<HiStrA version="1" GDL="1" IsLocked="true">'
        '<Analysis Key="1" Name="Static" AnalysisType="2" '
        'InitialAnalysisKey="-100" TypeLoadDistribution="Force" '
        'ForceImposed="false" ForceControl="false" '
        'IntegrationMethod="LoadControl" Method="StandardNewtonRaphson" '
        'AdapticConvergenceCriteria="ForceMoment" />'
        '</HiStrA>',
        encoding="utf-8",
    )

    analysis = load_model(hrx).collections.analyses[1]

    assert analysis.type_load_distribution == "Force"
    assert not analysis.force_imposed
    assert not analysis.force_control


def test_capability_preflight_inspects_supplied_definition_not_same_name_model_copy() -> None:
    stored = SimpleNamespace(
        key=1,
        name="Static",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="LoadControl",
        method="StandardNewtonRaphson",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect="None",
    )
    supplied = SimpleNamespace(**vars(stored))
    supplied.method = "BFGS"
    model = SimpleNamespace(collections=SimpleNamespace(analyses={1: stored}))

    report = inspect_solver_capabilities(model, [supplied])

    assert not report.supported
    assert {issue.code for issue in report.issues} == {
        "NONLINEAR_METHOD_UNSUPPORTED"
    }


def test_capability_preflight_rejects_unknown_arc_length_procedure() -> None:
    analysis = SimpleNamespace(
        key=1,
        name="Arc",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="ArcLength",
        arc_length_procedure="FutureConstraint",
        method="StandardBisectionLineSearch",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect="None",
    )
    model = SimpleNamespace(collections=SimpleNamespace(analyses={1: analysis}))

    report = inspect_solver_capabilities(model, ["Arc"])

    assert not report.supported
    assert {issue.code for issue in report.issues} == {
        "ARC_LENGTH_PROCEDURE_UNSUPPORTED"
    }


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("modal_procedure", "FutureModes", "MODAL_PROCEDURE_UNSUPPORTED"),
        (
            "modal_convergence_criteria",
            "FutureCriterion",
            "MODAL_CONVERGENCE_CRITERION_UNSUPPORTED",
        ),
        ("mass_matrix_type", "FutureMass", "MASS_MATRIX_TYPE_UNSUPPORTED"),
    ],
)
def test_capability_preflight_rejects_unknown_modal_enums(
    field: str, value: str, code: str
) -> None:
    analysis = SimpleNamespace(
        key=30,
        name="Modal",
        initial_analysis_key=-100,
        analysis_type=5,
        modal_procedure="SubspaceIterations",
        modal_convergence_criteria="Frquency",
        pdelta_effect="None",
    )
    model = SimpleNamespace(
        mass_matrix_type="Consistent",
        collections=SimpleNamespace(analyses={30: analysis}),
    )
    if field == "mass_matrix_type":
        setattr(model, field, value)
    else:
        setattr(analysis, field, value)

    report = inspect_solver_capabilities(model, ["Modal"])

    assert not report.supported
    assert code in {issue.code for issue in report.issues}


def test_capability_preflight_rejects_unknown_masonry_constitutive_enum():
    analysis = SimpleNamespace(
        key=1,
        name="Vert",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="LoadControl",
        method="ModifiedNewtonRaphson",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect="None",
    )
    material = SimpleNamespace(
        key=9,
        properties={"CriterioSnervamento": "FutureDomain"},
    )
    material.value = lambda name, default: material.properties.get(name, default)
    model = SimpleNamespace(
        collections=SimpleNamespace(analyses={1: analysis}, materials={9: material})
    )

    report = inspect_solver_capabilities(model, ["Vert"])

    assert not report.supported
    assert report.issues[-1].code == "MASONRY_CONSTITUTIVE_ENUM_UNSUPPORTED"


def test_capability_preflight_rejects_out_of_v1_hrx_domains(tmp_path) -> None:
    hrx = tmp_path / "unsupported.hrx"
    hrx.write_text(
        '<HiStrA version="1" GDL="1" IsLocked="true">'
        '<Frame Key="1" />'
        '<Vertex Key="2" />'
        '<InterfaceMF Key="3" />'
        '<NodeBC Key="4" />'
        '<Template Key="2" PurposeType="ConcreteMaterial" />'
        '<Analysis Key="1" Name="Static" AnalysisType="2" '
        'InitialAnalysisKey="-100" IntegrationMethod="LoadControl" '
        'Method="StandardNewtonRaphson" AdapticConvergenceCriteria="ForceMoment" />'
        '</HiStrA>',
        encoding="utf-8",
    )
    model = load_model(hrx)

    report = inspect_solver_capabilities(model, ["Static"])

    assert not report.supported
    assert {issue.code for issue in report.issues} == {
        "V1_ELEMENT_DOMAIN_UNSUPPORTED",
    }
    assert model.unsupported_v1_features == {
        "element:Frame": 1,
        "element:InterfaceMF": 1,
        "element:NodeBC": 1,
        "element:Vertex": 1,
    }
    assert model.unsupported_material_templates == {2: "ConcreteMaterial"}


def test_capability_preflight_rejects_referenced_non_masonry_material() -> None:
    analysis = SimpleNamespace(
        key=1,
        name="Static",
        initial_analysis_key=-100,
        analysis_type=2,
        integration_method="LoadControl",
        method="StandardNewtonRaphson",
        adaptive_convergence_criteria="ForceMoment",
        pdelta_effect="None",
    )
    collections = SimpleNamespace(
        analyses={1: analysis},
        materials={},
        quads={1: SimpleNamespace(material_key=7)},
        interfaces={},
    )
    model = SimpleNamespace(
        collections=collections,
        unsupported_v1_features={},
        unsupported_material_templates={7: "SteelMaterial"},
    )

    report = inspect_solver_capabilities(model, ["Static"])

    assert not report.supported
    assert report.issues[-1].code == "V1_MATERIAL_DOMAIN_UNSUPPORTED"
