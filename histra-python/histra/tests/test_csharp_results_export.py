"""Native database schema, exact serialization, and capture lifecycle regressions."""
from pathlib import Path
import hashlib
import sqlite3
import struct

import numpy as np
import pytest

from histra import AnalysisSession, load_model
from histra.io.csharp_results_schema import CREATE_SQL, SOURCE_SHA256
from histra.io.csharp_results_writer import write_csharp_records, compare_csharp_results, _schema
from histra.io.results_reader import ResultsStateError, read_analysis_metadata, read_spring_states

ROOT = Path(__file__).parents[2]
REFERENCE = ROOT / 'histra/model-output/model.Results'


def test_schema_matches_native_source_and_all_reference_databases():
    with sqlite3.connect(':memory:') as generated:
        generated.executescript(CREATE_SQL)
        expected = _schema(generated)
    for folder in ('model-output', 'model-live', 'model-chain', 'model-benchmark'):
        with sqlite3.connect(ROOT / 'histra' / folder / 'model.Results') as native:
            schema = _schema(native)
            assert all(expected[name] == columns for name, columns in schema.items())
            assert set(expected) - set(schema) <= {"SpringStatesTmp"}
    source = ROOT / 'C#_Original/source/ModelLibrary/SQLite/Create.sql'
    if source.exists():
        assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256


def test_every_native_fixture_record_round_trips_bit_exactly(tmp_path):
    records = {}
    with sqlite3.connect(REFERENCE) as source:
        source.row_factory = sqlite3.Row
        for table in _schema(source):
            records[table] = [dict(row) for row in source.execute(f'SELECT * FROM "{table}"')]
    path = write_csharp_records(tmp_path / 'roundtrip.Results', records, reference_path=REFERENCE)
    counts = compare_csharp_results(path, REFERENCE, include_row_ids=True)
    assert counts['SpringStatesTmp'] == 14724
    assert counts['SpringStates'] == 2454
    assert read_analysis_metadata(path, 1) == read_analysis_metadata(REFERENCE, 1)
    assert read_spring_states(path, 1, require_complete=True) == read_spring_states(REFERENCE, 1, require_complete=True)


def test_comparison_detects_one_bit_and_distinguishes_null_from_zero(tmp_path):
    base = {'AnalysisKey': 1, 'Combination': 1, 'Step': 0, 'R1': 1.0, 'Eel': None}
    a = write_csharp_records(tmp_path / 'a', {'ReactionSumStates': [base]})
    b = write_csharp_records(tmp_path / 'b', {'ReactionSumStates': [{**base, 'R1': np.nextafter(1.0, 2.0)}]})
    with pytest.raises(ResultsStateError, match='zero tolerance'):
        compare_csharp_results(a, b)
    with sqlite3.connect(b) as connection:
        connection.execute('UPDATE ReactionSumStates SET R1=1.0,Eel=0.0')
    with pytest.raises(ResultsStateError, match='stored-value'):
        compare_csharp_results(a, b)
    with sqlite3.connect(b) as connection:
        connection.execute('UPDATE ReactionSumStates SET Eel=NULL,Id=100')
    assert compare_csharp_results(a, b)['ReactionSumStates'] == 1
    with pytest.raises(ResultsStateError):
        compare_csharp_results(a, b, include_row_ids=True)


def test_verification_failure_preserves_old_destination(tmp_path):
    path = tmp_path / 'existing.Results'
    path.write_bytes(b'previous result')
    with pytest.raises(ResultsStateError):
        write_csharp_records(path, {}, reference_path=REFERENCE)
    assert path.read_bytes() == b'previous result'
    assert not list(tmp_path.glob('.*.tmp'))
    with pytest.raises(ResultsStateError, match='Nonfinite'):
        write_csharp_records(path, {'ReactionSumStates': [{'R1': float('nan')}]})
    assert path.read_bytes() == b'previous result'


@pytest.fixture(scope='module')
def captured_session():
    session = AnalysisSession(load_model(ROOT / 'histra/model-output/model.hrx'), capture_csharp_results=True)
    session.run('Vert')
    session.run('LiveLoad_1', max_committed_steps=1)
    return session


def test_capture_export_and_stage_snapshots(captured_session, tmp_path):
    path = captured_session.export_csharp_results(tmp_path / 'study')
    assert list(tmp_path.iterdir()) == [path]
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert connection.execute('SELECT DISTINCT AnalysisKey FROM QuadStates ORDER BY AnalysisKey').fetchall() == [(1,), (22,)]
        assert connection.execute('SELECT DISTINCT Step FROM QuadStates ORDER BY Step').fetchall() == [(0,), (1,), (2,), (3,), (4,), (5,)]
        finals = dict(connection.execute('SELECT DISTINCT AnalysisKey,Step FROM SpringStates'))
        assert finals == {e.analysis_key: e.output_steps[-1].step for e in captured_session.executions}
        assert connection.execute('SELECT COUNT(*) FROM SpringStates WHERE E IS NOT NULL OR Ed IS NOT NULL OR Eel IS NOT NULL').fetchone() == (0,)
        u = connection.execute('SELECT U FROM DynamicVectorsState WHERE AnalysisKey=1 ORDER BY Dof').fetchall()
    expected = captured_session.executions[0].committed_steps[-1].u
    assert b''.join(struct.pack('d', row[0]) for row in u) == expected.tobytes()
    assert read_spring_states(path, 1, require_complete=True)
    files = captured_session.export_analysis('Vert', tmp_path / 'single', format='results')
    assert set(files) == {'results'}
    assert read_analysis_metadata(files['results'], 1).steps_by_combination == {1: (0, 1, 2, 3, 4, 5)}
    files = captured_session.export_session(tmp_path / 'all', 'study', format='results')
    assert files['Vert']['results'] == files['LiveLoad_1']['results']


def test_capture_does_not_change_solver_history(captured_session):
    control = AnalysisSession(load_model(ROOT / 'histra/model-output/model.hrx'))
    control.run('Vert')
    control.run('LiveLoad_1', max_committed_steps=1)
    for expected, actual in zip(control.executions, captured_session.executions):
        for a, b in zip(expected.committed_steps, actual.committed_steps):
            assert a.u.tobytes() == b.u.tobytes()
            for key in ('reaction_x', 'reaction_y', 'reaction_z', 'elastic_energy', 'dissipated_energy'):
                assert struct.pack('d', a[key]) == struct.pack('d', b[key]), key
        assert all(expected.export_snapshot[k].tobytes() == actual.export_snapshot[k].tobytes() for k in expected.export_snapshot)


def test_uncaptured_export_fails_instead_of_filling_missing_history(tmp_path):
    session = AnalysisSession(load_model(ROOT / 'histra/model-output/model.hrx'))
    session.run('Vert')
    with pytest.raises(ResultsStateError, match='capture_csharp_results'):
        session.export_csharp_results(tmp_path / 'missing.Results')
    assert not list(tmp_path.iterdir())


def test_native_spring_mapping_preserves_reference_constitutive_fields(tmp_path):
    from histra.io.csharp_results_capture import native_spring_record
    from histra.solver.restart import _restore_hysteretic, _restore_coulomb, _restore_elastic
    from histra.springs.hysteretic import SpringHysteretic
    from histra.springs.coulomb03 import SpringCoulomb03
    from histra.springs.elastic import SpringElastic

    kinds = {8: (SpringHysteretic, _restore_hysteretic), 12: (SpringCoulomb03, _restore_coulomb), 1: (SpringElastic, _restore_elastic)}
    purposes = {1: 'Transversal1', 11: 'Slid', 21: 'SlidOutOfPlan', 30: 'Diagonal'}
    expected = []
    generated = []
    with sqlite3.connect(REFERENCE) as connection:
        connection.row_factory = sqlite3.Row
        for record in connection.execute('SELECT * FROM SpringStates'):
            row = dict(record)
            factory, restore = kinds[row['SpringType']]
            spring = factory()
            spring.area = row['ContactArea']
            spring.spring_purpose = purposes[row['SpringPurpose']]
            restore(spring, row)
            native = native_spring_record(spring, row['ParentKey'], row['ParentType'], row['IdLocal'])
            native.update({key: row[key] for key in ('Id', 'AnalysisKey', 'Combination', 'Step')})
            generated.append(native)
            expected.append(row)
    a = write_csharp_records(tmp_path / 'mapped.Results', {'SpringStates': generated})
    b = write_csharp_records(tmp_path / 'expected.Results', {'SpringStates': expected})
    assert compare_csharp_results(a, b, include_row_ids=True)['SpringStates'] == len(expected)


def test_native_capture_honors_public_save_interval(tmp_path):
    session = AnalysisSession(load_model(ROOT / 'histra/model-output/model.hrx'), capture_csharp_results=True)
    session.model.collections.analyses[1].step_save = 2
    session.run('Vert')
    path = session.export_csharp_results(tmp_path / 'interval.Results')
    with sqlite3.connect(path) as connection:
        for table in ('QuadStates', 'InterfaceStates', 'SpringStatesTmp', 'ReactionSumStates'):
            assert connection.execute(f'SELECT DISTINCT Step FROM {table} ORDER BY Step').fetchall() == [(0,), (2,), (4,)]
        assert connection.execute('SELECT DISTINCT Step FROM SpringStates').fetchall() == [(5,)]
        assert connection.execute('SELECT DISTINCT Step FROM DynamicVectorsState').fetchall() == [(5,)]


def test_capture_cancellation_before_initial_state_remains_cancelled():
    session = AnalysisSession(load_model(ROOT / 'histra/model-output/model.hrx'), capture_csharp_results=True)
    execution = session.run('Vert', should_cancel=lambda: True)
    from histra.solver.cancellation import CANCELLED_EXIT_CODE
    assert execution.code == CANCELLED_EXIT_CODE
    assert execution.csharp_records is None
