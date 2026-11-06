"""Plot-ready named-point summaries, stage snapshots and legacy reading."""
from dataclasses import replace
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from histra import AnalysisSession, SimulationResults, load_model
from histra.io.hr_loader import _parse_model_point
from histra.io.model_point_summary import build_model_point_summary
from histra.model.load import ModelPoint
from histra.solver.model_manager import ModelManager
from histra.solver.output_projection import model_point_displacement

ROOT = Path(__file__).parents[2]


def test_model_point_label_metadata_is_preserved_from_hrx():
    point = _parse_model_point(ET.fromstring('<ModelPoint Key="90" Name="Arch centre" Description="Crown monitoring point" ElementType="Quad" ElementKey="3" IdVertex="0" />'))
    assert point.name == 'Arch centre'
    assert point.description == 'Crown monitoring point'
    assert (point.key, point.element_key, point.id_vertex) == (90, 3, 0)


@pytest.fixture(scope='module')
def solved():
    model = load_model(ROOT / 'histra/model-output/model.hrx')
    ModelManager.prepare_model(model, force=True)
    quad = next(iter(model.collections.quads.values()))
    model.collections.model_points.update({
        90: ModelPoint(90, quad.key, 'Quad', 0, 'Arch centre', 'Crown monitoring point'),
        91: ModelPoint(91, quad.key, 'Quad', 2, 'Top pier', 'Second point on the same macro-element'),
        92: ModelPoint(92, quad.node_keys[1], 'Node', 0, 'Pier node'),
    })
    session = AnalysisSession(model)
    execution = session.run('Vert')
    return session, execution


@pytest.mark.parametrize('format,tier', [('json', 'all'), ('npz', 'summary'), ('npz', 'all'), ('histra', 'all')])
def test_all_named_point_histories_are_available_without_dense_fields(solved, tmp_path, format, tier):
    session, execution = solved
    files = session.export_analysis('Vert', tmp_path, format=format, tier=tier)
    path = files.get('bundle') or files['summary']
    with SimulationResults.load(path) as result:
        data = result.summary['model_points']
        assert data['step'] == result.summary['curve']['step']
        assert data['step'] == [step.step for step in execution.output_steps]
        assert {point['key'] for point in data['points']} == set(session.model.collections.model_points)
        records = {point['key']: point for point in result.model_points}
        assert records[90]['name'] == 'Arch centre'
        assert records[90]['description'] == 'Crown monitoring point'
        assert not records[90]['active']  # Inactive monitoring points remain exported.
        assert records[90]['element_key'] == records[91]['element_key']
        quad = session.model.collections.quads[records[90]['element_key']]
        assert records[90]['coordinates_cm'] == [quad.g.x, quad.g.y, quad.g.z]
        point = session.model.collections.nodes[quad.node_keys[1]].point
        assert records[91]['coordinates_cm'] == [point.x, point.y, point.z]
        for key, record in records.items():
            assert record['available']
            definition = session.model.collections.model_points[key]
            expected = np.asarray([model_point_displacement(session.model.collections, definition, step.u) for step in execution.output_steps])
            for axis, name in enumerate(('ux', 'uy', 'uz')):
                steps, displacement = result.get_model_point_curve(key, name, 'cm')
                np.testing.assert_array_equal(steps, data['step'])
                assert displacement.tobytes() == expected[:, axis].tobytes()
                _, mm = result.get_model_point_curve(key, name, 'mm')
                np.testing.assert_array_equal(mm, displacement * 10.0)
        with pytest.raises(KeyError):
            result.get_model_point_curve(-99)
        with pytest.raises(ValueError):
            result.get_model_point_curve(90, component='rotation')


def test_point_summary_is_independent_of_later_model_changes(solved, tmp_path, monkeypatch):
    session, execution = solved
    captured = json.dumps(execution.model_point_output, sort_keys=True)
    definitions = dict(session.model.collections.model_points)
    definitions[90] = replace(definitions[90], name='Changed later')
    monkeypatch.setattr(session.model.collections, 'model_points', definitions)
    quad = session.model.collections.quads[definitions[90].element_key]
    monkeypatch.setattr(quad.g, 'z', quad.g.z + 100.0)
    files = session.export_analysis('Vert', tmp_path, format='json')
    data = json.loads(files['summary'].read_text())
    assert json.dumps(data['model_points'], sort_keys=True) == captured


def test_unsupported_or_nonfinite_point_output_is_explicit(solved, monkeypatch):
    session, execution = solved
    points = {100: ModelPoint(100, 9999, 'Frame', name='Unsupported monitor')}
    monkeypatch.setattr(session.model.collections, 'model_points', points)
    summary = build_model_point_summary(session.model, execution.output_steps)
    record = summary['points'][0]
    assert not record['available']
    assert record['displacement_cm'] is None
    assert record['coordinates_cm'] is None
    assert 'Unsupported' in record['error']
    json.dumps(summary, allow_nan=False)


def test_older_summary_has_no_fabricated_point_curves(tmp_path):
    path = tmp_path / 'old.summary.json'
    path.write_text(json.dumps({'metadata': {'schema_version': '2.0.0'}, 'files': {'fields': None}, 'curve': {'step': [0]}}))
    with SimulationResults.load(path) as result:
        assert result.model_points == []
        with pytest.raises(KeyError):
            result.get_model_point_curve(1)
