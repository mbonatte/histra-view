"""Validate fresh experiment inputs without treating Python results as C# truth."""

import hashlib
import json

import pytest

from histra import AnalysisSession, load_model
from histra.solver.backend_coverage import inspect_solver_backend
from histra.solver.model_manager import ModelManager
from histra.springs.elastic import SpringElastic
from tools.benchmarks.build_material_modal_reference_models import (
    ANALYSES, CASES, DEFAULT_TEMPLATE, build_material_modal_model, write_models,
)


@pytest.mark.parametrize("case", CASES)
def test_fresh_foundation_target_and_loaded_restart_graph(tmp_path, case):
    path = tmp_path / f"{case}.hrx"
    tree = build_material_modal_model(DEFAULT_TEMPLATE, case)
    root = tree.getroot()
    assert root.get("IsLocked") == "false"
    for tag in ("Interface", ".//Spring", ".//State", ".//AfferenceMatrices"):
        assert not root.findall(tag)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    session = AnalysisSession(model)
    model = session.model
    targets = [i for i in model.collections.interfaces.values() if i.interfaccia_vincolata]
    assert len(targets) == 1
    assert model.gdl == 28
    inspect_solver_backend(model).require_compiled()
    for key, name, parent, _ in ANALYSES:
        analysis = root.find(f"Analysis[@Key='{key}']")
        assert analysis.get("Name") == name
        assert analysis.get("InitialAnalysisKey") == str(parent)
    # Both cycles retain a static predecessor, and have a complete signed cycle.
    for key in (2, 6):
        items = root.findall(f"LoadFunctionItem[@loadFunctionKey='{key}']")
        assert [float(i.get("multiplier")) for i in items] == [0, 1, -1, 1, 0]
    # This is an unloaded input-construction check. Loaded cross-law history
    # transfer is precisely the missing native reference, not asserted here.
    session.change_interface_materials([targets[0].key], 19, preserve_committed_state=False)
    fibers = model.collections.interfaces[targets[0].key].trasv_1
    assert all(isinstance(s, SpringElastic) for s in fibers) == (case == CASES[1])
    session.change_interface_materials([targets[0].key], 18, preserve_committed_state=False)
    inspect_solver_backend(model).require_compiled()


def test_pack_provenance_and_no_overwrite(tmp_path):
    output = tmp_path / "pack"
    paths = write_models(DEFAULT_TEMPLATE, output)
    manifest = json.loads((output / "manifest.json").read_text())
    for path, entry in zip(paths, manifest["models"], strict=True):
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert list((path.parent / "csharp").iterdir()) == []
    assert manifest["step_zero_is_commit"] is False
    with pytest.raises(FileExistsError):
        write_models(DEFAULT_TEMPLATE, output)
    with pytest.raises(ValueError):
        build_material_modal_model(DEFAULT_TEMPLATE, "unknown")
