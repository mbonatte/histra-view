"""Fresh, reproducible inputs for native masonry validation, not golden results."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from histra import AnalysisSession, load_model
from histra.solver.backend_coverage import inspect_solver_backend
from histra.solver.load_assembly import assemble_load_vector
from histra.solver.model_manager import ModelManager
from histra.solver.equilibrium import UnsafeEquilibriumWarning
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.types.umfpack import find_umfpack_library
from tools.benchmarks.build_masonry_reference_models import (
    CASE_NAMES,
    DEFAULT_TEMPLATE,
    build_reference_model,
    write_reference_models,
)


@pytest.mark.parametrize("case", CASE_NAMES)
def test_new_geometry_and_intended_material_branches(tmp_path, case):
    tree = build_reference_model(DEFAULT_TEMPLATE, case)
    root = tree.getroot()
    assert root.get("IsLocked") == "false"
    assert root.findall("Interface") == []
    assert root.findall(".//Spring") == []
    assert root.findall(".//AfferenceMatrices") == []
    assert root.findall(".//State") == []
    path = tmp_path / (case + ".hrx")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    assert (len(model.collections.quads), len(model.collections.interfaces), model.gdl) == (
        4,
        4,
        28,
    )
    inspect_solver_backend(model).require_compiled()
    material = model.collections.materials[18]
    if case.startswith("02"):
        assert float(material.properties["Ehor"]) == 80.0
        assert float(material.properties["Ever"]) == 160.0
    if case.startswith("03"):
        assert all(
            isinstance(s, SpringElastic)
            for i in model.collections.interfaces.values()
            for s in i.trasv_1
        )
    if case.startswith("04"):
        assert all(isinstance(q.spring, SpringHysteretic) for q in model.collections.quads.values())
    items = root.findall("LoadFunctionItem[@loadFunctionKey='2']")
    assert [(float(i.get("pseudoTime")), float(i.get("multiplier"))) for i in items] == [
        (0, 0),
        (1, 1),
        (2, -1),
        (3, 1),
        (4, 0),
    ]
    assert all(np.isfinite(assemble_load_vector(model, key)).all() for key in (1, 2))


def test_writer_preserves_existing_reference_inputs(tmp_path):
    paths = write_reference_models(DEFAULT_TEMPLATE, tmp_path)
    before = {p: p.read_bytes() for p in paths}
    with pytest.raises(FileExistsError):
        write_reference_models(DEFAULT_TEMPLATE, tmp_path)
    assert before == {p: p.read_bytes() for p in paths}


@pytest.mark.parametrize("is_seismic", [False, True])
@pytest.mark.parametrize("factors", [(1.0, 1.0, 1.0), (0.25, 0.5, 0.0)])
def test_modal_line_load_uses_three_mass_directions(tmp_path, is_seismic, factors):
    path = tmp_path / "modal.hrx"
    build_reference_model(DEFAULT_TEMPLATE, CASE_NAMES[0]).write(path, encoding="utf-8")
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    analysis = model.collections.analyses[3]
    analysis.is_seismic = is_seismic
    analysis.dir_x, analysis.dir_y, analysis.dir_z = (0.0, 0.0, -1.0)
    for condition in model.collections.load_conditions.values():
        condition.mass_in_dir_x, condition.mass_in_dir_y, condition.mass_in_dir_z = factors
    assemble_load_vector(model, 3)
    total = sum((np.asarray(q.status.p[:3]) for q in model.collections.quads.values()))
    np.testing.assert_array_equal(total, 60.0 * np.asarray(factors))


@pytest.mark.parametrize("case", CASE_NAMES)
def test_native_control_python_reference_chain(tmp_path, monkeypatch, case):
    if find_umfpack_library() is None:
        pytest.skip("Original native UMFPACK configuration required")
    monkeypatch.setenv("HISTRA_UMFPACK_ORDERING", "amd")
    path = tmp_path / (case + ".hrx")
    build_reference_model(DEFAULT_TEMPLATE, case).write(
        path, encoding="utf-8", xml_declaration=True
    )
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    session = AnalysisSession(
        model,
        linear_solver_backend="umfpack",
        linear_solver_precision="accurate",
        umfpack_irstep=2,
        equilibrium_policy="warn",
        strategy_policy="off",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UnsafeEquilibriumWarning)
        vert = session.run("Vert")
        reversal = session.run("Reversal")
    assert vert.code == reversal.code == 0
    assert len(vert.committed_steps) == 10
    assert len(reversal.committed_steps) == 32
    factors = [step["load_factor"] for step in reversal.steps if step.committed]
    assert [factors[j] for j in (7, 15, 23, 31)] == [1.0, -1.0, 1.0, 0.0]


def _precision_model_tree(mass_factors, fractional_direction):
    tree = build_reference_model(DEFAULT_TEMPLATE, CASE_NAMES[0])
    if fractional_direction:
        for analysis in tree.getroot().findall("Analysis"):
            analysis.set("IsSeismic", "true")
            analysis.set("DirX", "0.123456789")
            analysis.set("DirY", "0.234567891")
            analysis.set("DirZ", "-0.345678912")
        changed = 0
        for item in tree.getroot().findall("LoadCombination/Item"):
            if float(item.get("Val", "0")) != 0.0:
                item.set("Val", "1.23456789")
                changed += 1
        assert changed > 0
    for condition in tree.getroot().findall("LoadCondition"):
        for axis, factor in zip("XYZ", mass_factors):
            condition.set(f"MassInDir{axis}", str(factor))
    return tree


def test_fresh_load_vectors_match_native_precision_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures/csharp-fresh-load-precision-2026.1.1.json"
    for index, case in enumerate(json.loads(fixture.read_text())["cases"]):
        path = tmp_path / f"precision-{index}.hrx"
        tree = _precision_model_tree(case["mass_factors"], case["fractional_direction"])
        tree.write(path, encoding="utf-8", xml_declaration=True)
        assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == case["input_lf_sha256"]
        model = load_model(path)
        ModelManager.prepare_model(model, force=True)
        for key, native in case["vectors"].items():
            np.testing.assert_array_equal(assemble_load_vector(model, int(key)), native)


@pytest.mark.parametrize("mass_factors", [(1.0, 1.0, 1.0), (0.25, 0.5, 0.0)])
@pytest.mark.parametrize("fractional_direction", [False, True])
def test_original_oracle_initializes_unrun_analysis_load_state(tmp_path, mass_factors, fractional_direction):
    install = Path(r"C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1")
    if sys.platform != "win32" or not (install / "SolverRuntime.dll").exists():
        pytest.skip("Installed original C# 2026.1.1 runtime required")
    model_path = tmp_path / "unrun.hrx"
    tree = _precision_model_tree(mass_factors, fractional_direction)
    tree.write(
        model_path,
        encoding="utf-8",
        xml_declaration=True,
    )
    assert not ET.parse(model_path).findall(".//State")
    oracle = (
        DEFAULT_TEMPLATE.parents[2] / "tools/csharp-diagnostics/Invoke-FreshConstructionOracle.ps1"
    )
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    for key in (1, 2, 3, 4):
        out = tmp_path / str(key)
        result = subprocess.run(
            [
                str(shell),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(oracle),
                "-ModelPath",
                str(model_path),
                "-OutputDirectory",
                str(out),
                "-ExportAssembly",
                "-AnalysisKey",
                str(key),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        native = np.fromfile(out / "native-Vert-Ptarget.bin", dtype=np.float64)
        model = load_model(model_path)
        ModelManager.prepare_model(model, force=True)
        expected = assemble_load_vector(model, key)
        assert np.any(native)
        np.testing.assert_array_equal(native, expected)


@pytest.mark.parametrize("case", CASE_NAMES)
def test_wall_modal_native_reference(tmp_path, monkeypatch, case):
    if find_umfpack_library() is None:
        pytest.skip("Original native UMFPACK configuration required")
    monkeypatch.setenv("HISTRA_LINEAR_SOLVER", "umfpack")
    monkeypatch.setenv("HISTRA_LINEAR_SOLVER_PRECISION", "accurate")
    monkeypatch.setenv("HISTRA_UMFPACK_ORDERING", "amd")
    fixture = json.loads((Path(__file__).parent / "fixtures/masonry-wall-modal-2026.1.1.json").read_text())
    reference = fixture["cases"][case]
    path = tmp_path / (case + ".hrx")
    build_reference_model(DEFAULT_TEMPLATE, case).write(path, encoding="utf-8", xml_declaration=True)
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(raw)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == reference["input_sha256"]
    for key in (3, 4):
        model = load_model(path)
        ModelManager.prepare_model(model, force=True)
        session = AnalysisSession(
            model, linear_solver_backend="umfpack", linear_solver_precision="accurate",
            umfpack_irstep=2, equilibrium_policy="warn", strategy_policy="off",
        )
        if key == 4:
            for predecessor in (1, 2):
                assert session.run(predecessor).code == 0
        result = session.run(key).modal_result
        modes = reference["analyses"][str(key)]["modes"]
        assert result.converged_modes == len(modes) < result.requested_modes
        for mode, native in zip(result.modes, modes):
            actual = mode.as_modal_values_row(analysis_key=key)
            assert set(native["values"]) - {"Id"} <= set(actual)
            for field, value in actual.items():
                if field in native["values"] and field != "ResidualNorm":
                    np.testing.assert_allclose(value, native["values"][field], rtol=1e-11, atol=1e-12, err_msg=field)
            np.testing.assert_allclose(mode.shape, native["shape"], rtol=1e-10, atol=1e-10)
