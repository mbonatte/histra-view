"""Lossless, atomic .histra storage and legacy conversion regressions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

import histra
from histra.io.bundle import HistraBundleWriter, BundleStore
from histra.io.bundle_codec import array_descriptor, encode_array, decode_array


@pytest.mark.parametrize("array", [
    np.array(2.5, np.float64),
    np.zeros((0, 3), np.float32),
    np.arange(24, dtype='>f8').reshape(4, 6)[:, ::2],
    np.array([0x7fc00001, 0x80000000, 0x7f800000], np.uint32).view(np.float32),
    np.array('cm / μm', dtype='U12'),
    np.array([b'abc', b'\0z'], dtype='S4'),
    np.array([True, False]),
    np.array(['2026-10-25'], dtype='datetime64[D]'),
])
def test_codec_preserves_shape_dtype_and_every_bit(array):
    digest, descriptor, raw = array_descriptor(array)
    restored = decode_array(encode_array(raw, array.dtype.itemsize), descriptor, digest)
    assert restored.shape == array.shape
    assert restored.dtype == array.dtype
    assert restored.tobytes() == array.tobytes(order='C')


def _summary(model_hash=None):
    return {"metadata": {"schema_version": "2.0.0", "model_sha256": model_hash},
            "curve": {"displacement_mm": [0, 2.5], "total_force_kN": [0, 234]}}


def test_multiple_cases_deduplicate_and_share_lazy_reader(tmp_path, monkeypatch):
    model = tmp_path / 'bridge.hrx'
    model.write_bytes(b'<Model>source geometry</Model>')
    attachment = tmp_path / 'curves.json'
    attachment.write_bytes(b'{"original_control":1.23456789012345}')
    path = tmp_path / 'study.histra'
    array = np.arange(30, dtype=np.float32).reshape(10, 3)
    with HistraBundleWriter(path, metadata={'study': 'bridge'}) as writer:
        model_hash = writer.add_model(model)
        writer.add_attachment(attachment)
        for case_id in ('Vert', 'Live'):
            writer.add_case(case_id, _summary(model_hash), {'mesh/nodes_xyz': array}, model_sha256=model_hash)
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read('manifest.json'))
        assert len(manifest['objects']) == 1
        assert all(i.compress_type == zipfile.ZIP_LZMA for i in z.infolist())
    # Listing and opening cases must not decode large numerical arrays.
    monkeypatch.setattr(BundleStore, 'array', lambda *args: pytest.fail('eager array read'))
    assert histra.SimulationResults.list_cases(path) == ['Vert', 'Live']
    with pytest.raises(ValueError, match='case_id'):
        histra.SimulationResults.load(path)
    with pytest.raises(KeyError, match='Unknown'):
        histra.SimulationResults.load(path, case_id='missing')
    readers = histra.SimulationResults.load_session(path)
    assert readers['Vert']._data.store is readers['Live']._data.store
    assert readers['Live'].get_model_source() == model.read_bytes()
    assert readers['Live'].get_attachment('curves.json') == attachment.read_bytes()
    assert readers['Live'].bundle_metadata['study'] == 'bridge'
    assert readers['Live'].keys() == ['mesh/nodes_xyz']
    assert 'mesh/nodes_xyz' in readers['Live']
    store = readers['Vert']._data.store
    readers['Vert'].close()
    assert store._zip.fp is not None
    readers['Live'].close()
    assert store._zip.fp is None


def test_single_case_read_and_atomic_failure_preserves_previous_file(tmp_path):
    path = tmp_path / 'case.histra'
    with HistraBundleWriter(path) as writer:
        writer.add_case('case', _summary(), {'mesh/nodes_xyz': np.arange(9).reshape(3, 3)})
    before = path.read_bytes()
    with pytest.raises(ValueError, match='dtype'):
        with HistraBundleWriter(path) as writer:
            writer.add_case('bad', {}, {'objects': np.array([object()], dtype=object)})
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.*.tmp'))
    with pytest.raises(FileExistsError):
        with HistraBundleWriter(path, overwrite=False):
            pass
    with histra.SimulationResults.load(path) as result:
        np.testing.assert_array_equal(result.mesh_nodes_xyz, np.arange(9).reshape(3, 3))
        assert result.summary['files'] == {'bundle': 'case.histra', 'case_id': 'case'}
    histra.verify_bundle(path)


def _rewrite_archive(path, mutate):
    with zipfile.ZipFile(path) as z:
        members = {name: z.read(name) for name in z.namelist()}
    mutate(members)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_LZMA) as z:
        for name, payload in members.items():
            z.writestr(name, payload)


@pytest.mark.parametrize('fault', ['version', 'missing', 'length', 'object_dtype', 'checksum'])
def test_corrupt_or_unsupported_bundles_fail_closed(tmp_path, fault):
    path = tmp_path / 'bad.histra'
    with HistraBundleWriter(path) as writer:
        writer.add_case('case', {}, {'values': np.arange(6, dtype=np.float32)})
    def mutate(members):
        manifest = json.loads(members['manifest.json'])
        digest = next(iter(manifest['objects']))
        member = f'objects/{digest}.bin'
        if fault == 'version':
            manifest['schema_version'] = '99.0.0'
        elif fault == 'missing':
            del members[member]
        elif fault == 'length':
            manifest['objects'][digest]['shape'] = [7]
        elif fault == 'object_dtype':
            manifest['objects'][digest]['dtype'] = '|O'
        else:
            members[member] = b'\xff' + members[member][1:]
        members['manifest.json'] = json.dumps(manifest).encode()
    _rewrite_archive(path, mutate)
    with pytest.raises(ValueError):
        histra.verify_bundle(path)


@pytest.fixture(scope='module')
def solved_session():
    model_path = Path(__file__).parents[1] / 'model-output/model.hrx'
    session = histra.AnalysisSession(histra.load_model(model_path))
    session.run('Vert')
    session.run('LiveLoad_1', max_committed_steps=1)
    return session


def test_session_single_file_exports_all_stages(solved_session, tmp_path):
    path = solved_session.export_bundle(tmp_path / 'bridge')
    assert path.name == 'bridge.histra'
    assert list(tmp_path.iterdir()) == [path]
    readers = histra.SimulationResults.load_session(path)
    try:
        assert set(readers) == {'Vert', 'LiveLoad_1'}
        for case_id, result in readers.items():
            execution = next(e for e in solved_session.executions if e.analysis_name == case_id)
            np.testing.assert_array_equal(result.steps, [s.step for s in execution.output_steps])
            assert result.quad_displacements.shape[0] == len(execution.output_steps)
            assert hashlib.sha256(result.get_model_source()).hexdigest() == result.summary['metadata']['model_sha256']
    finally:
        for result in readers.values():
            result.close()
    files = solved_session.export_session(tmp_path / 'session', 'study', format='histra')
    assert files['Vert']['bundle'] == files['LiveLoad_1']['bundle']
    assert len(list((tmp_path / 'session').iterdir())) == 1


@pytest.mark.parametrize('tier', ['all', 'summary', 'fields'])
def test_analysis_bundle_tier_filtering(solved_session, tmp_path, tier):
    files = solved_session.export_analysis('Vert', tmp_path, format='histra', tier=tier)
    assert set(files) == {'bundle'}
    with histra.SimulationResults.load(files['bundle']) as result:
        assert bool(result.summary) == (tier != 'fields')
        assert ('fields/U' in result) == (tier != 'summary')
        displacement, force = result.get_pushover_curve()
        assert displacement.size == force.size > 0


def test_convert_split_results_preserves_all_arrays_and_attachments(solved_session, tmp_path):
    source = tmp_path / 'source'
    split = solved_session.export_session(source, 'bridge')
    extra = tmp_path / 'aggregate.json'
    extra.write_bytes(b'{"measurement":1.2345678901234567}')
    target = tmp_path / 'bridge.histra'
    histra.pack_results_directory(source, target, attachments=[extra], remove_source=True)
    assert sorted(p.name for p in source.iterdir()) == ['model.hrx']
    assert extra.exists()
    readers = histra.SimulationResults.load_session(target)
    try:
        for name, result in readers.items():
            assert result.get_attachment(extra.name) == extra.read_bytes()
            assert 'bridge.session.json' in result.attachment_names
            execution = next(e for e in solved_session.executions if e.analysis_name == name.removeprefix('bridge_'))
            for key, value in execution.export_snapshot.items():
                if not key.startswith('_export/'):
                    assert result[key].tobytes() == value.tobytes()
    finally:
        for result in readers.values():
            result.close()
    assert not any(files['fields'].exists() for files in split.values())


def test_conversion_never_deletes_sources_when_model_or_array_invalid(solved_session, tmp_path):
    files = solved_session.export_analysis('Vert', tmp_path / 'source')
    wrong_model = tmp_path / 'wrong.hrx'
    wrong_model.write_bytes(b'wrong model')
    with pytest.raises(ValueError, match='SHA-256'):
        histra.pack_results_directory(tmp_path / 'source', tmp_path / 'bad.histra', model_path=wrong_model, remove_source=True)
    assert all(p.exists() for p in files.values())
    assert not (tmp_path / 'bad.histra').exists()


def test_pack_cli(solved_session, tmp_path):
    from histra.tools.pack_results import main

    solved_session.export_analysis('Vert', tmp_path / 'source')
    target = tmp_path / 'cli.histra'
    assert main([str(tmp_path / 'source'), '--output', str(target)]) == 0
    assert histra.SimulationResults.list_cases(target)


def test_cleanup_rejects_references_outside_input_directory(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    fields = tmp_path / 'external.fields.npz'
    np.savez_compressed(fields, values=np.arange(5))
    summary = _summary()
    summary['files'] = {'fields': '../external.fields.npz'}
    (source / 'case.summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError, match='input directory'):
        histra.pack_results_directory(source, tmp_path / 'bad.histra', remove_source=True)
    assert fields.exists()
    assert not (tmp_path / 'bad.histra').exists()


def test_changed_source_aborts_publication_and_cleanup(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    summary = source / 'case.summary.json'
    summary.write_text(json.dumps(_summary()))
    original = HistraBundleWriter.add_case
    def change_after_read(self, *args, **kwargs):
        original(self, *args, **kwargs)
        summary.write_text(summary.read_text() + ' ')
    monkeypatch.setattr(HistraBundleWriter, 'add_case', change_after_read)
    target = tmp_path / 'changed.histra'
    with pytest.raises(RuntimeError, match='changed during packing'):
        histra.pack_results_directory(source, target, remove_source=True)
    assert summary.exists()
    assert not target.exists()
