"""Every available committed spring field on four independently run C# walls."""
import hashlib
import json
from pathlib import Path

import pytest

from histra import load_model, AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.types.umfpack import find_umfpack_library
from tools.benchmarks.build_masonry_reference_models import CASE_NAMES, DEFAULT_TEMPLATE, build_reference_model
from tools.benchmarks.masonry_spring_fingerprint import fingerprint, python_spring_rows


@pytest.mark.parametrize("case", CASE_NAMES)
def test_every_committed_native_spring_history(tmp_path, monkeypatch, case):
    if find_umfpack_library() is None:
        pytest.skip("Original native UMFPACK configuration required")
    monkeypatch.setenv("HISTRA_UMFPACK_ORDERING", "amd")
    fixture = Path(__file__).parent / "fixtures/masonry-wall-static-spring-history-2026.1.1.json"
    reference = json.loads(fixture.read_text())["cases"][case]
    path = tmp_path / (case + ".hrx")
    build_reference_model(DEFAULT_TEMPLATE, case).write(path, encoding="utf-8", xml_declaration=True)
    assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == reference["input_lf_sha256"]
    expected = {(row["analysis"], row["combination"], row["step"]): row["tables"] for row in reference["states"]}
    checked = set()
    try:
        for combination in (1, 2):
            model = load_model(path)
            ModelManager.prepare_model(model, force=True, use_cache=False)
            session = AnalysisSession(model, linear_solver_backend="umfpack", linear_solver_precision="accurate",
                                      umfpack_irstep=2, equilibrium_policy="warn", strategy_policy="off")

            def committed(row, analysis):
                key = (analysis.key, 1 if analysis.key == 1 else combination, row["step"])
                rows = python_spring_rows(model)
                for table, native in expected[key].items():
                    actual = fingerprint([item[0] for item in rows],
                                         [[item[1][field] for field in native["fields"]] for item in rows])
                    assert actual == {field: native[field] for field in ("rows", "identities", "values")}, (key, table)
                checked.add(key)

            assert session.run(1, on_step_committed=committed).code == 0
            session.combination_row = combination
            assert session.run(2, on_step_committed=committed).code == 0
        assert checked == set(expected)
    finally:
        ModelManager.clear_hysteretic_batch()
