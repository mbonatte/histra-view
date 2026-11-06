"""A support change must be able to retain the actually applied gravity load."""
import numpy as np

from histra import AnalysisSession, load_model
from histra.model.load import LoadFunction, LoadFunctionItem
from histra.solver.model_manager import ModelManager
from tools.benchmarks.build_material_modal_reference_models import (
    CASES, DEFAULT_TEMPLATE, build_material_modal_model,
)


def test_material_change_reequilibrates_under_committed_external_load(tmp_path):
    path = tmp_path / "bridge.hrx"
    build_material_modal_model(DEFAULT_TEMPLATE, CASES[0]).write(path, encoding="utf-8", xml_declaration=True)
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    session = AnalysisSession(model, equilibrium_policy="error", strategy_policy="off",
                              preserve_predecessor_load=True)
    gravity = session.run("Vert")
    assert gravity.completed
    applied = ModelManager._fext.copy()
    reaction = gravity.committed_steps[-1]
    session.change_interface_materials([4], 19)
    analysis = model.collections.analyses[2]
    analysis.mult = 0.0
    analysis.adaptive_convergence_criteria = "ForceMoment"
    model.collections.load_functions[2] = LoadFunction(
        key=2, discr_val=1.0,
        items=[LoadFunctionItem(key=1, load_function_key=2, pseudo_time=0.0, multiplier=0.0),
               LoadFunctionItem(key=2, load_function_key=2, pseudo_time=1.0, multiplier=1.0)],
    )
    result = session.run(2)
    assert result.completed and len(result.committed_steps) == 1, {k: v for k, v in result.steps[-1].items() if k.startswith("equilibrium_")}
    assert np.array_equal(ModelManager._fext, applied)
    endpoint = result.committed_steps[-1]
    assert endpoint.equilibrium_ok
    assert np.allclose([endpoint.reaction_x, endpoint.reaction_y, endpoint.reaction_z],
                       [reaction.reaction_x, reaction.reaction_y, reaction.reaction_z],
                       rtol=1e-5, atol=1e-3)


def test_preserved_load_does_not_accept_false_work_convergence(tmp_path):
    path = tmp_path / "bridge.hrx"
    build_material_modal_model(DEFAULT_TEMPLATE, CASES[0]).write(path, encoding="utf-8", xml_declaration=True)
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    session = AnalysisSession(model, equilibrium_policy="error", strategy_policy="off",
                              preserve_predecessor_load=True)
    assert session.run("Vert").completed
    session.change_interface_materials([4], 19)
    model.collections.analyses[2].mult = 0.0
    model.collections.load_functions[2] = LoadFunction(
        key=2, discr_val=1.0,
        items=[LoadFunctionItem(key=1, load_function_key=2, pseudo_time=0.0, multiplier=0.0),
               LoadFunctionItem(key=2, load_function_key=2, pseudo_time=1.0, multiplier=1.0)],
    )
    result = session.run(2)
    assert not result.completed and not result.committed_steps
    assert not result.steps[-1]["equilibrium_ok"]
    assert result.steps[-1]["equilibrium_residual_norm"] > 1.0
