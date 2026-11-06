from pathlib import Path
import tempfile
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import histra
from histra.postprocessing import compute_node_displacements
from histra.solver.model_manager import ModelManager

HRX_PATH = Path(__file__).resolve().parent.parent / "model-output" / "model.hrx"


@pytest.fixture(scope="module")
def vert_execution():
    model = histra.load_model(HRX_PATH)
    session = histra.AnalysisSession(model)
    execution = session.run("Vert")
    return model, session, execution


def test_results_export_two_tier_files(vert_execution):
    model, session, execution = vert_execution
    with tempfile.TemporaryDirectory() as td:
        created = session.export_analysis("Vert", td)
        assert "summary" in created
        assert "fields" in created

        summary_path = created["summary"]
        fields_path = created["fields"]
        assert summary_path.is_file()
        assert fields_path.is_file()

        # Size requirements: summary < 100 KB, fields < 20 MB
        summary_size = summary_path.stat().st_size
        fields_size = fields_path.stat().st_size
        assert summary_size <= 100 * 1024, f"Summary size {summary_size} exceeds 100 KB"
        assert fields_size <= 20 * 1024 * 1024, f"Fields size {fields_size} exceeds 20 MB"

        # Check SimulationResults can load from fields path or summary path
        sr = histra.SimulationResults.load(fields_path)
        assert sr.summary is not None
        assert "metadata" in sr.summary
        assert "metrics" in sr.summary
        assert sr.summary["metrics"]["completed"] is True
        assert sr.summary["metrics"]["total_steps"] > 0

        # Load from summary path
        sr_summary = histra.SimulationResults.load(summary_path)
        assert sr_summary.fields_path == fields_path


def test_results_export_round_trip_parity(vert_execution):
    model, session, execution = vert_execution
    last_u = execution.committed_steps[-1].u

    with tempfile.TemporaryDirectory() as td:
        created = session.export_analysis("Vert", td)
        sr = histra.SimulationResults.load(created["fields"])

        # 1. Displacement field parity
        disp_field = sr.get_displacement_field(step=-1)
        expected_rows = compute_node_displacements(model, last_u, only_quad_nodes=True)
        expected_arr = np.array(
            [[r.ux, r.uy, r.uz] for r in expected_rows], dtype=np.float32
        )
        l_inf_disp = np.max(np.abs(disp_field - expected_arr))
        assert l_inf_disp < 1.0e-6, f"Displacement L_inf mismatch: {l_inf_disp}"

        # 2. Interface resultants parity
        rt = ModelManager.hysteretic_batch_for(model)
        assert rt is not None
        expected_forces = rt.all_resultant_forces()
        actual_forces = sr.get_interface_resultants(step=-1)
        l_inf_forces = np.max(np.abs(actual_forces - expected_forces))
        assert l_inf_forces < 1.0e-6, f"Interface resultants L_inf mismatch: {l_inf_forces}"

        # 3. Filtered interface keys
        keys = list(sr.mesh_interface_keys)
        subset_keys = keys[:5]
        sub_forces = sr.get_interface_resultants(step=-1, interface_keys=subset_keys)
        assert sub_forces.shape == (5, 3)
        np.testing.assert_array_equal(sub_forces, actual_forces[:5])

        # 4. Pushover curve
        disp_curve, force_curve = sr.get_pushover_curve()
        assert len(disp_curve) == len(force_curve)
        assert len(disp_curve) == len(execution.output_steps)


def test_results_export_session_bundle(vert_execution):
    model, session, _ = vert_execution
    with tempfile.TemporaryDirectory() as td:
        bundle = session.export_session(td, "test_bundle")
        assert "Vert" in bundle
        assert bundle["Vert"]["summary"].is_file()
        assert bundle["Vert"]["fields"].is_file()


def test_results_export_tier_filtering(vert_execution):
    _, session, _ = vert_execution
    with tempfile.TemporaryDirectory() as td:
        # Tier summary only
        res_sum = session.export_analysis("Vert", td, base_name="sum_only", tier="summary")
        assert "summary" in res_sum
        assert "fields" not in res_sum
        assert res_sum["summary"].is_file()

        # Tier fields only
        res_fld = session.export_analysis("Vert", td, base_name="fld_only", tier="fields")
        assert "fields" in res_fld
        assert "summary" not in res_fld
        assert res_fld["fields"].is_file()


def test_results_export_h5_fallback_when_unavailable(vert_execution):
    _, session, _ = vert_execution
    with tempfile.TemporaryDirectory() as td:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            created = session.export_analysis("Vert", td, base_name="h5_test", format="h5")

        # Either created h5 or gracefully fell back to npz with warning
        fields_path = created["fields"]
        assert fields_path.is_file()
        if fields_path.suffix == ".npz":
            assert any("h5py is not installed" in str(w.message) for w in caught)


def test_simulation_results_to_vtk(vert_execution):
    _, session, _ = vert_execution
    with tempfile.TemporaryDirectory() as td:
        created = session.export_analysis("Vert", td)
        sr = histra.SimulationResults.load(created["fields"])

        vtu_path = Path(td) / "deformed_bridge.vtu"
        sr.to_vtk(vtu_path, step=-1)
        assert vtu_path.is_file()

        # Validate VTU is well-formed XML
        tree = ET.parse(vtu_path)
        root = tree.getroot()
        assert root.tag == "VTKFile"
        assert root.attrib.get("type") == "UnstructuredGrid"

        piece = root.find(".//Piece")
        assert piece is not None
        assert int(piece.attrib["NumberOfPoints"]) == len(sr.mesh_nodes_xyz)
        assert int(piece.attrib["NumberOfCells"]) == len(sr.mesh_quad_conn)


def test_step_resultant_hooks_numpy_arrays(vert_execution):
    _, _, execution = vert_execution
    # Verify every committed step has contiguous NumPy arrays without proxy objects
    for step in execution.committed_steps:
        forces = step.interface_resultants
        moments = step.interface_moments
        assert forces is not None
        assert moments is not None
        assert isinstance(forces, np.ndarray)
        assert isinstance(moments, np.ndarray)
        assert forces.dtype == np.float32
        assert moments.dtype == np.float32


@pytest.mark.parametrize(
    "reactions, axis, forces",
    [
        ([(0, 4, 1000), (0.1, 4.1, 1234)], "Z", [0, 234]),
        ([(50, 80, 1000), (250, 81, 1001)], "X", [0, 200]),
        ([(50, 80, 1000), (51, -120, 1001)], "Y", [0, 200]),
        ([(0, 0, 0), (10, 10, 10)], "Z", [0, 10]),
        ([(0, 0, 0), (10, 10, 0)], "X", [0, 10]),
        ([(0, 0, 3), (0, 0, 3)], "resultant", [3, 3]),
        ([], "resultant", []),
    ],
)
def test_summary_units_force_selection_and_metrics(vert_execution, reactions, axis, forces):
    from dataclasses import replace
    from histra.io.results_writer import _build_summary_manifest, NATIVE_UNITS
    from histra.solver.outcomes import AnalysisStep

    model, _, execution = vert_execution
    steps = tuple(AnalysisStep.from_mapping(dict(
        step=index, status="OK", displacement=-0.25 * index, load_factor=0.5 * index,
        reaction_x=rx, reaction_y=ry, reaction_z=rz,
    )) for index, (rx, ry, rz) in enumerate(reactions))
    execution = replace(execution, initial_step=None, steps=steps)
    summary = _build_summary_manifest(model, execution, "synthetic")
    assert summary["metadata"]["units"] == NATIVE_UNITS == {
        "length": "cm", "displacement": "cm", "force": "kN",
        "moment": "kN*cm", "stress": "MPa", "rotation": "rad",
    }
    assert summary["pushover_axis"] == axis
    np.testing.assert_allclose(summary["curve"]["total_force_kN"], forces)
    np.testing.assert_allclose(summary["curve"]["force_kN"], forces)
    np.testing.assert_allclose(summary["curve"]["displacement_mm"],
                               np.array(summary["curve"]["displacement_cm"]) * 10)
    assert summary["metrics"]["d_max_mm"] == summary["metrics"]["d_max_cm"] * 10
    assert summary["metrics"]["d_at_f_max_mm"] == summary["metrics"]["d_at_f_max_cm"] * 10
    assert not Path(summary["metadata"]["model_file"]).is_absolute()
    if axis == "Z" and len(reactions) == 2 and reactions[0][2] == 1000:
        assert summary["curve"]["reference_force_kN"] == [1000, 1234]
        assert summary["curve"]["load_factor"] == [0, 0.5]


def test_complete_topology_and_disconnected_kinematics(vert_execution, tmp_path):
    from histra.postprocessing import quad_node_displacement

    model, session, execution = vert_execution
    created = session.export_analysis("Vert", tmp_path)
    with histra.SimulationResults.load(created["summary"]) as result:
        quads = [q for _, q in sorted(model.collections.quads.items())]
        interfaces = [i for _, i in sorted(model.collections.interfaces.items())]
        specs = {
            "quad_material_keys": (np.uint32, [q.material_key for q in quads]),
            "quad_thickness": (np.float32, [q.thickness for q in quads]),
            "quad_interface_keys": (np.int32, [[face[0] if face else -1 for face in q.interface_keys] for q in quads]),
            "interface_node_keys": (np.uint32, [i.node_keys for i in interfaces]),
            "interface_length": (np.float32, [i.length for i in interfaces]),
            "interface_material_keys": (np.uint32, [i.material_key for i in interfaces]),
            "interface_e1": (np.float32, [i.reference_e1 for i in interfaces]),
            "interface_e3": (np.float32, [i.reference_e3 for i in interfaces]),
            "interface_origin": (np.float32, [[i.reference_origin.x, i.reference_origin.y, i.reference_origin.z] for i in interfaces]),
            "interface_nrow": (np.uint16, [i.nrow for i in interfaces]),
            "interface_ncol": (np.uint16, [i.ncol for i in interfaces]),
            "interface_nspring": (np.uint16, [len(i.trasv_1) for i in interfaces]),
            "interface_restrained": (np.uint8, [i.interfaccia_vincolata for i in interfaces]),
        }
        for name, (dtype, expected) in specs.items():
            actual = getattr(result, f"mesh_{name}")
            assert actual.dtype == dtype
            np.testing.assert_array_equal(actual, np.array(expected, dtype))
        assert result.quad_displacements.shape == (len(execution.output_steps), len(quads), 4, 3)
        assert result.quad_displacements.dtype == np.float32
        expected = [[quad_node_displacement(q, model.collections.nodes[key].point, corner,
                                           execution.output_steps[-1].u)
                     for corner, key in enumerate(q.node_keys)] for q in quads]
        np.testing.assert_array_equal(result.get_quad_displacement_field(), np.array(expected, np.float32))
        # Preserve the actual face order used by C# DrawCurvaPressioni, including
        # partial-edge faces with multiple contact interfaces.
        offsets = result.mesh_quad_face_interface_offsets
        keys = result.mesh_quad_face_interface_keys
        for q_index, quad in enumerate(quads):
            for face_index, face in enumerate(quad.interface_keys):
                index = q_index * 6 + face_index
                np.testing.assert_array_equal(keys[offsets[index]:offsets[index+1]], face)
        opposite_faces = ((0, 2), (1, 3), (4, 5))
        expected_pairs = [(a, b) for q in quads for f1, f2 in opposite_faces
                          if len(q.interface_keys[f1]) == len(q.interface_keys[f2]) == 1
                          for a in q.interface_keys[f1] for b in q.interface_keys[f2]]
        actual_pairs = [(a, b) for qi in range(len(quads)) for f1, f2 in opposite_faces
                        if offsets[qi*6+f1+1] - offsets[qi*6+f1] == offsets[qi*6+f2+1] - offsets[qi*6+f2] == 1
                        for a in keys[offsets[qi*6+f1]:offsets[qi*6+f1+1]]
                        for b in keys[offsets[qi*6+f2]:offsets[qi*6+f2+1]]]
        assert actual_pairs == expected_pairs
        assert all(a in result.mesh_interface_keys and b in result.mesh_interface_keys for a, b in actual_pairs)


def test_spring_offsets_stress_phase_and_snapshot_isolation(vert_execution, tmp_path, monkeypatch):
    from histra.solver.hysteretic_kernels.interface_coulomb import CCSTRESS, CCPHASE

    model, session, execution = vert_execution
    runtime = ModelManager.hysteretic_batch_for(model)
    interfaces = [i for _, i in sorted(model.collections.interfaces.items())]
    records = {id(r.interface): (idx, r) for idx, r in enumerate(runtime.records)}
    expected = {}
    for interface in interfaces:
        index, record = records[id(interface)]
        sliding = [int(a[index]) for a in (runtime._slid_index, runtime._oop0_index, runtime._oop1_index) if a[index] >= 0]
        expected[interface.key] = (
            runtime.committed[record.start:record.stop, 6].copy(),
            runtime.committed[record.start:record.stop, 8].astype(np.int8),
            np.array([spring.area for spring in interface.trasv_1]),
            runtime.coulomb_state[sliding, CCSTRESS].copy(),
            runtime.coulomb_state[sliding, CCPHASE].astype(np.int8),
            runtime.coulomb_params[sliding, 4].copy(),
        )
    # A later stage can replace all live arrays; exports must remain stage-bound.
    monkeypatch.setattr(runtime, "committed", runtime.committed + 99)
    monkeypatch.setattr(runtime, "coulomb_state", runtime.coulomb_state + 99)
    files = session.export_analysis("Vert", tmp_path)
    with histra.SimulationResults.load(files["fields"]) as result:
        for kind in ("transverse", "sliding"):
            offsets = result[f"springs/{kind}_offsets"]
            assert offsets.dtype == np.uint32
            assert offsets.shape == (len(interfaces) + 1,)
            assert offsets[0] == 0
            assert offsets[-1] == len(result[f"springs/{kind}_stress"]) == len(result[f"springs/{kind}_phase"])
        np.testing.assert_array_equal(np.diff(result["springs/transverse_offsets"]), result.mesh_interface_nspring)
        for key, (tf, tp, ta, sf, sp, sa) in expected.items():
            for kind, force, phase, area in (("transverse", tf, tp, ta), ("sliding", sf, sp, sa)):
                springs = result.get_interface_springs(key, kind)
                np.testing.assert_allclose(springs["force"], force, rtol=1e-6)
                np.testing.assert_array_equal(springs["phase"], phase)
                np.testing.assert_allclose(springs["stress"], 10 * force / area, rtol=1e-6, atol=1e-6)


def test_bundle_manifest_relative_references_and_curve_only(vert_execution, tmp_path):
    import json
    import shutil

    _, session, _ = vert_execution
    session.export_session(tmp_path / "original", "bundle")
    shutil.move(tmp_path / "original", tmp_path / "moved")
    base = tmp_path / "moved"
    manifest = json.loads((base / "bundle.session.json").read_text())
    assert manifest["schema_version"] == "2.1.0"
    assert len(manifest["cases"]) == len(session.executions)
    for case in manifest["cases"]:
        assert not case["curve_only"]
        for tier in ("summary", "fields"):
            assert not Path(case[tier]).is_absolute()
            assert (base / case[tier]).is_file()
        with histra.SimulationResults.load(base / case["summary"]) as result:
            assert result.mesh_quad_conn.shape[1] == 4
    session.export_session(tmp_path / "curves", "curves", format="json")
    manifest = json.loads((tmp_path / "curves/curves.session.json").read_text())
    assert all(case["curve_only"] and case["fields"] is None for case in manifest["cases"])


def test_legacy_reader_and_dense_curve_fallback(tmp_path):
    import json

    summary = {"metadata": {"schema_version": "1.0.0"}, "curve": {
        "displacement_mm": [0.0, 1.5], "force_kN": [0.0, 20.0],
    }}
    path = tmp_path / "legacy.summary.json"
    path.write_text(json.dumps(summary))
    with histra.SimulationResults.load(path) as result:
        disp, force = result.get_pushover_curve()
        np.testing.assert_array_equal(disp, [0, 1.5])
        np.testing.assert_array_equal(force, [0, 20])
        with pytest.raises(KeyError):
            result.get_quad_displacement_field()
    fields = tmp_path / "dense.fields.npz"
    np.savez(fields, **{"steps/displacement": [0, 0.25],
                        "steps/reactions": [[0, 4, 1000, 0, 0, 0], [0.1, 4.1, 1234, 0, 0, 0]]})
    with histra.SimulationResults.load(fields) as result:
        disp, force = result.get_pushover_curve()
        np.testing.assert_array_equal(disp, [0, 2.5])
        np.testing.assert_array_equal(force, [0, 234])


def test_session_stage_exports_survive_next_analysis(tmp_path):
    model = histra.load_model(HRX_PATH)
    session = histra.AnalysisSession(model)
    vert = session.run("Vert")
    original = {key: arr.copy() for key, arr in vert.export_snapshot.items()}
    session.run("LiveLoad_1", max_committed_steps=1)
    session.export_session(tmp_path, "chain")
    readers = histra.SimulationResults.load_session(tmp_path / "chain.session.json")
    try:
        assert set(readers) == {"Vert", "LiveLoad_1"}
        for key, value in original.items():
            if not key.startswith("_export/"):
                np.testing.assert_array_equal(readers["Vert"][key], value)
    finally:
        for reader in readers.values():
            reader.close()


def test_no_failed_trial_steps_exported(vert_execution):
    from dataclasses import replace
    from histra.io.results_writer import _build_summary_manifest
    from histra.solver.outcomes import AnalysisStep, AnalysisOutcome

    model, _, execution = vert_execution
    failed = AnalysisStep.from_mapping(dict(step=1, status="FAILED", displacement=99))
    execution = replace(execution, initial_step=None, steps=(failed,), outcome=AnalysisOutcome.NONCONVERGED)
    summary = _build_summary_manifest(model, execution, "failed")
    assert summary["curve"]["step"] == []
    assert summary["metrics"]["d_max_cm"] == 0
    assert summary["metrics"]["failure_classification"] == "divergence"


def test_empty_fields_and_invalid_options(tmp_path):
    from histra.io.results_writer import ResultsWriter
    from histra.model.model import Model, Collections
    from histra.solver.outcomes import AnalysisExecution

    execution = AnalysisExecution(1, "empty", 0, (), 0)
    for kwargs in ({"format": "bad"}, {"tier": "bad"}):
        with pytest.raises(ValueError):
            ResultsWriter.export(Model(), execution, tmp_path / "bad", **kwargs)
    files = ResultsWriter.export(Model(collections=Collections()), execution, tmp_path / "empty")
    with histra.SimulationResults.load(files["fields"]) as result:
        assert result.mesh_nodes_xyz.shape == (0, 3)
        assert result.mesh_quad_conn.shape == (0, 4)
        assert result.mesh_interface_node_keys.shape == (0, 2)
        assert result.quad_displacements.shape == (0, 0, 4, 3)
        assert result.reactions.shape == (0, 6)


def test_schema_gate_and_missing_declared_fields(tmp_path):
    import json

    path = tmp_path / "case.summary.json"
    path.write_text(json.dumps({"metadata": {"schema_version": "99.0.0"}}))
    with pytest.raises(ValueError, match="Unsupported"):
        histra.SimulationResults.load(path)
    path.write_text(json.dumps({"metadata": {"schema_version": "2.0.0"}, "files": {"fields": "missing.npz"}}))
    with pytest.raises(FileNotFoundError, match="missing"):
        histra.SimulationResults.load(path)


def test_sorted_interface_fields_with_different_runtime_order(tmp_path, monkeypatch):
    from dataclasses import replace
    from histra.io.results_snapshot import capture_export_snapshot
    from histra.io.results_writer import ResultsWriter
    from histra.solver.outcomes import AnalysisStep

    model = histra.load_model(HRX_PATH)
    execution = histra.AnalysisSession(model).run("Vert")
    runtime = ModelManager.hysteretic_batch_for(model)
    expected = runtime.all_resultant_forces().copy()
    moments = runtime.all_bending_moments().copy()
    # Simulate a runtime built in reverse key order without altering integration.
    monkeypatch.setattr(runtime, "records", list(reversed(runtime.records)))
    for attr in ("_slid_index", "_oop0_index", "_oop1_index"):
        monkeypatch.setattr(runtime, attr, getattr(runtime, attr)[::-1].copy())
    monkeypatch.setattr(runtime, "all_resultant_forces", lambda: expected[::-1])
    monkeypatch.setattr(runtime, "all_bending_moments", lambda: moments[::-1])
    monkeypatch.setattr(model.collections, "interfaces", dict(reversed(list(model.collections.interfaces.items()))))

    def reversed_step(step):
        values = dict(step)
        for field in ("interface_resultants", "interface_moments"):
            values[field] = values[field][::-1].copy()
        return AnalysisStep.from_mapping(values)

    latest = replace(execution, export_snapshot=capture_export_snapshot(model),
                     initial_step=reversed_step(execution.initial_step),
                     steps=tuple(reversed_step(step) for step in execution.steps))
    files = ResultsWriter.export(model, latest, tmp_path / "ordered", include_node_displacements=False)
    with histra.SimulationResults.load(files["fields"]) as result:
        assert "fields/node_displacements" not in result
        np.testing.assert_array_equal(result.get_interface_resultants(), expected)
        np.testing.assert_array_equal(result["springs/runtime_arrays/all_resultant_forces"], expected)
        assert result.quad_displacements.shape[2:] == (4, 3)
        for key in result.keys():
            array = result[key]
            if np.issubdtype(array.dtype, np.number):
                assert np.isfinite(array).all(), key


def test_hdf5_dense_round_trip_if_available(vert_execution, tmp_path):
    pytest.importorskip("h5py")
    _, session, _ = vert_execution
    files = session.export_analysis("Vert", tmp_path, format="h5")
    with histra.SimulationResults.load(files["summary"]) as result:
        assert "fields/quad_displacements" in result.keys()
        assert result.quad_displacements.shape[2:] == (4, 3)
        assert result.mesh_interface_nspring.dtype == np.uint16
        assert result.get_interface_springs(int(result.mesh_interface_keys[0]))["stress"].size > 0


def test_zero_area_sliding_snapshot_preserves_force_and_masks_stress(tmp_path, monkeypatch):
    from histra.io.results_snapshot import capture_export_snapshot

    model = histra.load_model(HRX_PATH)
    histra.AnalysisSession(model).run("Vert")
    runtime = ModelManager.hysteretic_batch_for(model)
    parameters = runtime.coulomb_params.copy()
    parameters[:, 4] = 0.0
    monkeypatch.setattr(runtime, "coulomb_params", parameters)
    snapshot = capture_export_snapshot(model)
    assert snapshot["springs/sliding_force"].size > 0
    assert not snapshot["springs/sliding_stress_valid"].any()
    assert np.isfinite(snapshot["springs/sliding_stress"]).all()
    np.testing.assert_array_equal(snapshot["springs/sliding_stress"], 0)
