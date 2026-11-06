"""Native HiStrA SQLite serialization, with zero-tolerance record verification."""
from __future__ import annotations

from contextlib import closing
import math
import os
from pathlib import Path
import sqlite3
import struct
import tempfile

from histra.io.csharp_results_schema import CREATE_SQL
from histra.io.results_reader import ResultsStateError


def _schema(connection):
    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name: connection.execute(f'PRAGMA table_info("{name}")').fetchall() for name in names}


def _encoded(value):
    if value is None:
        return b'n'
    if isinstance(value, float):
        return b'f' + struct.pack('>d', value)
    if isinstance(value, int):
        return b'i' + str(value).encode()
    return b's' + str(value).encode('utf-8')


def compare_csharp_results(actual, reference, *, include_row_ids=False):
    """Require identical schemas and stored records, including every floating bit.

    Native parallel interface insertion gives unstable surrogate Id values.
    Those are excluded by default; all physical identities remain compared.
    This compares SQLite contents, not database page bytes or solver tolerances.
    """
    with closing(sqlite3.connect(f'{Path(actual).resolve().as_uri()}?mode=ro', uri=True)) as a, closing(sqlite3.connect(f'{Path(reference).resolve().as_uri()}?mode=ro', uri=True)) as b:
        schema = _schema(a)
        if schema != _schema(b):
            raise ResultsStateError('C# .Results schema mismatch')
        counts = {}
        for table, columns in schema.items():
            names = [column[1] for column in columns if include_row_ids or column[1] != 'Id']
            query = 'SELECT ' + ','.join(f'"{name}"' for name in names) + f' FROM "{table}"'
            rows_a = sorted(tuple(_encoded(v) for v in row) for row in a.execute(query))
            rows_b = sorted(tuple(_encoded(v) for v in row) for row in b.execute(query))
            if rows_a != rows_b:
                raise ResultsStateError(f'C# .Results stored-value mismatch in {table}: {len(rows_a)} versus {len(rows_b)} records (zero tolerance)')
            counts[table] = len(rows_a)
        return counts


def _bind(value):
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        raise ResultsStateError('Nonfinite value cannot be exported losslessly to native SQLite REAL')
    if value is not None and not isinstance(value, (str, int, float, bytes)):
        raise ResultsStateError(f'Unsupported SQLite value type: {type(value).__name__}')
    return value


def write_csharp_records(filepath, records, *, reference_path=None):
    """Atomically write captured native rows; no approximated or inferred fields."""
    path = Path(filepath)
    if path.suffix.lower() not in {'.result', '.results'}:
        path = path.with_name(path.name + '.Results')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.executescript(CREATE_SQL)
            columns = _schema(connection)
            for table, rows in records.items():
                if table not in columns:
                    raise ResultsStateError(f'Unknown C# results table: {table}')
                _insert_rows(connection, table, columns[table], rows)
            if connection.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ResultsStateError('SQLite integrity verification failed')
        if reference_path is not None:
            compare_csharp_results(temporary, reference_path)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def _insert_rows(connection, table, columns, rows):
    allowed = {column[1] for column in columns}
    for row in rows:
        if not row or set(row) - allowed:
            raise ResultsStateError(f'Invalid columns for C# {table}: {set(row) - allowed}')
        names = list(row)
        query = f'INSERT INTO "{table}" (' + ','.join(f'"{name}"' for name in names) + ') VALUES (' + ','.join('?' for _ in names) + ')'
        connection.execute(query, tuple(_bind(row[name]) for name in names))


def export_csharp_executions(executions, filepath, *, reference_path=None):
    records = {}
    latest = {execution.analysis_key: execution for execution in executions}
    if not latest:
        raise ResultsStateError('No executions selected for native export')
    for execution in latest.values():
        captured = getattr(execution, 'csharp_records', None)
        if captured is None:
            raise ResultsStateError('Complete native state capture is required: create AnalysisSession(..., capture_csharp_results=True) before solving')
        for table, rows in captured.items():
            records.setdefault(table, []).extend(rows)
    return write_csharp_records(filepath, records, reference_path=reference_path)
