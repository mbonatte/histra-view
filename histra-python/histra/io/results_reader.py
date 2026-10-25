"""Typed reader for HiStrA C# ``.Results`` SQLite databases.

The supplied C# application stores committed element states at every public
step, a compact spring state in ``SpringStatesTmp`` for every public step, and
complete spring/restart history only in ``SpringStates`` for the last step.
``DynamicVectorsState.Dof`` is zero-based (see C# ``CommonOperations``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping, Optional

import numpy as np


@dataclass(frozen=True)
class AnalysisMetadata:
    analysis_key: int
    combinations: tuple[int, ...]
    steps_by_combination: Mapping[int, tuple[int, ...]]
    last_step_by_combination: Mapping[int, int]
    has_final_dynamic_vectors: bool
    has_complete_final_spring_state: bool


@dataclass(frozen=True)
class QuadStateRecord:
    parent_key: int
    analysis_key: int
    combination: int
    step: int
    u: tuple[float, ...]
    k: float


@dataclass(frozen=True)
class InterfaceStateRecord:
    parent_key: int
    analysis_key: int
    combination: int
    step: int
    u: tuple[float, ...]
    forces: tuple[float, float, float]
    bending_moments: tuple[float, float, float]


@dataclass(frozen=True)
class SpringStateRecord:
    parent_key: int
    parent_type: int
    spring_purpose: int
    spring_type: int
    id_local: int
    analysis_key: int
    combination: int
    step: int
    values: Mapping[str, Any]
    complete: bool

    @property
    def identity(self) -> tuple[int, int, int, int]:
        return (self.parent_type, self.parent_key, self.spring_purpose, self.id_local)


class ResultsStateError(RuntimeError):
    """Raised when a requested committed/restart state is absent or ambiguous."""


def _connect(results_path: str | Path) -> sqlite3.Connection:
    p = Path(results_path)
    if not p.exists():
        raise FileNotFoundError(f"Results database not found: {p}")
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _step_rows(
    conn: sqlite3.Connection, table: str, analysis_key: int, combination: int
) -> list[int]:
    if not _table_exists(conn, table):
        return []
    rows = conn.execute(
        f'SELECT DISTINCT Step FROM "{table}" '
        "WHERE AnalysisKey=? AND Combination=? ORDER BY Step",
        (analysis_key, combination),
    ).fetchall()
    return [int(r[0]) for r in rows if r[0] is not None]


def available_steps(
    conn_or_path: sqlite3.Connection | str | Path,
    analysis_key: int,
    combination: int = 1,
) -> List[int]:
    """Return committed public steps for an analysis/combination.

    ``QuadStates`` is authoritative for this model family.  A fallback union is
    used for databases containing other element types but no quads.
    """
    owns = not isinstance(conn_or_path, sqlite3.Connection)
    conn = _connect(conn_or_path) if owns else conn_or_path
    try:
        steps = _step_rows(conn, "QuadStates", analysis_key, combination)
        if steps:
            return steps
        union: set[int] = set()
        for table in (
            "InterfaceStates",
            "ReactionSumStates",
            "NodeCStates",
            "FrameStates",
            "TrussStates",
            "DynamicVectorsState",
        ):
            union.update(_step_rows(conn, table, analysis_key, combination))
        return sorted(union)
    finally:
        if owns:
            conn.close()


def read_analysis_metadata(results_path: str | Path, analysis_key: int) -> AnalysisMetadata:
    """Describe the analysis content actually present in a results database."""
    conn = _connect(results_path)
    try:
        combinations: set[int] = set()
        for table in ("QuadStates", "InterfaceStates", "ReactionSumStates", "DynamicVectorsState"):
            if not _table_exists(conn, table):
                continue
            combinations.update(
                int(r[0])
                for r in conn.execute(
                    f'SELECT DISTINCT Combination FROM "{table}" WHERE AnalysisKey=?',
                    (analysis_key,),
                )
                if r[0] is not None
            )
        if not combinations:
            raise ResultsStateError(
                f"Analysis {analysis_key} is not present in {Path(results_path)}"
            )
        ordered = tuple(sorted(combinations))
        steps = {c: tuple(available_steps(conn, analysis_key, c)) for c in ordered}
        last = {c: values[-1] for c, values in steps.items() if values}
        has_dv = any(
            conn.execute(
                "SELECT 1 FROM DynamicVectorsState WHERE AnalysisKey=? AND Combination=? LIMIT 1",
                (analysis_key, c),
            ).fetchone()
            for c in ordered
        ) if _table_exists(conn, "DynamicVectorsState") else False
        has_spr = any(
            conn.execute(
                "SELECT 1 FROM SpringStates WHERE AnalysisKey=? AND Combination=? LIMIT 1",
                (analysis_key, c),
            ).fetchone()
            for c in ordered
        ) if _table_exists(conn, "SpringStates") else False
        return AnalysisMetadata(
            analysis_key=int(analysis_key),
            combinations=ordered,
            steps_by_combination=steps,
            last_step_by_combination=last,
            has_final_dynamic_vectors=has_dv,
            has_complete_final_spring_state=has_spr,
        )
    finally:
        conn.close()


def read_last_committed_step(
    results_path: str | Path, analysis_key: int, combination: int = 1
) -> int:
    steps = available_steps(results_path, analysis_key, combination)
    if not steps:
        raise ResultsStateError(
            f"No committed steps for analysis {analysis_key}, combination {combination}"
        )
    return int(steps[-1])


def read_quad_states(
    results_path: str | Path,
    analysis_key: int,
    combination: int = 1,
    step: Optional[int] = None,
) -> Dict[int, QuadStateRecord]:
    conn = _connect(results_path)
    try:
        step = read_last_committed_step(results_path, analysis_key, combination) if step is None else int(step)
        rows = conn.execute(
            "SELECT ParentKey, AnalysisKey, Combination, Step, "
            "U1,U2,U3,U4,U5,U6,U7,K FROM QuadStates "
            "WHERE AnalysisKey=? AND Combination=? AND Step=? ORDER BY ParentKey",
            (analysis_key, combination, step),
        ).fetchall()
        if not rows:
            raise ResultsStateError(
                f"QuadStates missing for analysis {analysis_key}, combination {combination}, step {step}"
            )
        return {
            int(r["ParentKey"]): QuadStateRecord(
                parent_key=int(r["ParentKey"]),
                analysis_key=int(r["AnalysisKey"]),
                combination=int(r["Combination"]),
                step=int(r["Step"]),
                u=tuple(float(r[f"U{i}"] or 0.0) for i in range(1, 8)),
                k=float(r["K"] or 0.0),
            )
            for r in rows
        }
    finally:
        conn.close()


def read_interface_states(
    results_path: str | Path,
    analysis_key: int,
    combination: int = 1,
    step: Optional[int] = None,
) -> Dict[int, InterfaceStateRecord]:
    conn = _connect(results_path)
    try:
        step = read_last_committed_step(results_path, analysis_key, combination) if step is None else int(step)
        rows = conn.execute(
            "SELECT * FROM InterfaceStates WHERE AnalysisKey=? AND Combination=? AND Step=? ORDER BY ParentKey",
            (analysis_key, combination, step),
        ).fetchall()
        if not rows:
            raise ResultsStateError(
                f"InterfaceStates missing for analysis {analysis_key}, combination {combination}, step {step}"
            )
        return {
            int(r["ParentKey"]): InterfaceStateRecord(
                parent_key=int(r["ParentKey"]),
                analysis_key=int(r["AnalysisKey"]),
                combination=int(r["Combination"]),
                step=int(r["Step"]),
                u=tuple(float(r[f"U{i}"] or 0.0) for i in range(1, 13)),
                forces=tuple(float(r[n] or 0.0) for n in ("ForceX", "ForceY", "ForceZ")),
                bending_moments=tuple(
                    float(r[n] or 0.0)
                    for n in ("BendingMomentsX", "BendingMomentsY", "BendingMomentsZ")
                ),
            )
            for r in rows
        }
    finally:
        conn.close()


def read_spring_states(
    results_path: str | Path,
    analysis_key: int,
    combination: int = 1,
    step: Optional[int] = None,
    *,
    require_complete: bool = False,
) -> Dict[tuple[int, int, int, int], SpringStateRecord]:
    """Read spring states keyed by ``(parent_type,parent_key,purpose,id_local)``.

    Complete restart fields are available only in ``SpringStates`` and normally
    only at the final committed step.  ``SpringStatesTmp`` is sufficient for
    numerical per-step comparisons but not a lossless restart.
    """
    conn = _connect(results_path)
    try:
        last = read_last_committed_step(results_path, analysis_key, combination)
        step = last if step is None else int(step)
        # Row objects are keyed by column name below, but sqlite3.Row key
        # lookups are comparatively slow for tens of thousands of rows; the
        # positional value mapping built here (columns from cursor.description)
        # produces exactly the same per-row mapping, only faster.
        cur = conn.execute(
            "SELECT * FROM SpringStates WHERE AnalysisKey=? AND Combination=? AND Step=?",
            (analysis_key, combination, step),
        )
        names = [d[0] for d in cur.description]
        col = {name: idx for idx, name in enumerate(names)}
        complete_rows = cur.fetchall()
        if complete_rows:
            table, rows, complete = "SpringStates", complete_rows, True
        else:
            if require_complete:
                raise ResultsStateError(
                    "Complete spring restart state is unavailable for "
                    f"analysis {analysis_key}, combination {combination}, step {step}; "
                    "the C# database stores complete SpringStates only for the final step"
                )
            table = "SpringStatesTmp"
            cur = conn.execute(
                "SELECT * FROM SpringStatesTmp WHERE AnalysisKey=? AND Combination=? AND Step=?",
                (analysis_key, combination, step),
            )
            names = [d[0] for d in cur.description]
            col = {name: idx for idx, name in enumerate(names)}
            rows = cur.fetchall()
            complete = False
        if not rows:
            raise ResultsStateError(
                f"No spring state in {table} for analysis {analysis_key}, combination {combination}, step {step}"
            )
        # Large restart databases return tens of thousands of rows here.  Bind
        # the column names once and build each per-row value mapping with
        # zip instead of repeated sqlite3.Row key lookups; the produced
        # mapping is identical (same keys, same values, same order).
        columns = tuple(names)
        records: Dict[tuple[int, int, int, int], SpringStateRecord] = {}
        pk, pt, sp, st, il, ak, cb, stp = (
            col["ParentKey"], col["ParentType"], col["SpringPurpose"],
            col["SpringType"], col["IdLocal"], col["AnalysisKey"],
            col["Combination"], col["Step"],
        )
        for row in rows:
            values = dict(zip(columns, row))
            del values["Id"]
            rec = SpringStateRecord(
                parent_key=int(row[pk]),
                parent_type=int(row[pt]),
                spring_purpose=int(row[sp]),
                spring_type=int(row[st]),
                id_local=int(row[il]),
                analysis_key=int(row[ak]),
                combination=int(row[cb]),
                step=int(row[stp]),
                values=values,
                complete=complete,
            )
            if rec.identity in records:
                raise ResultsStateError(f"Duplicate spring identity {rec.identity} in {table}")
            records[rec.identity] = rec
        return records
    finally:
        conn.close()


def read_dynamic_vectors(
    results_path: str | Path,
    analysis_key: int,
    combination: int = 1,
    step: Optional[int] = None,
    *,
    size: Optional[int] = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Read final C# global displacement/velocity vectors.

    C# writes ``Dof = i`` in ``CommonOperations.AddStateNonLinearAnalysis``;
    therefore database indices are zero-based.  Missing/non-contiguous DOFs are
    rejected instead of silently shifting or zero-filling a restart state.
    """
    conn = _connect(results_path)
    try:
        if step is None:
            row = conn.execute(
                "SELECT MAX(Step) FROM DynamicVectorsState WHERE AnalysisKey=? AND Combination=?",
                (analysis_key, combination),
            ).fetchone()
            if row is None or row[0] is None:
                raise ResultsStateError(
                    f"DynamicVectorsState missing for analysis {analysis_key}, combination {combination}"
                )
            step = int(row[0])
        rows = conn.execute(
            "SELECT Dof,U,V FROM DynamicVectorsState WHERE AnalysisKey=? AND Combination=? AND Step=? ORDER BY Dof",
            (analysis_key, combination, int(step)),
        ).fetchall()
        if not rows:
            raise ResultsStateError(
                f"DynamicVectorsState missing for analysis {analysis_key}, combination {combination}, step {step}"
            )
        dofs = [int(r["Dof"]) for r in rows]
        expected = list(range(max(dofs) + 1))
        if dofs != expected:
            raise ResultsStateError(
                f"DynamicVectorsState DOFs are not contiguous zero-based indices: first={dofs[:5]}, last={dofs[-5:]}"
            )
        n = max(len(dofs), int(size or 0))
        if size is not None and len(dofs) != int(size):
            raise ResultsStateError(
                f"Dynamic vector has {len(dofs)} DOFs; model expects {int(size)}"
            )
        u = np.zeros(n, dtype=np.float64)
        v = np.zeros(n, dtype=np.float64)
        for r in rows:
            idx = int(r["Dof"])
            u[idx] = float(r["U"] or 0.0)
            v[idx] = float(r["V"] or 0.0)
        return u, v, int(step)
    finally:
        conn.close()


def _resolve_model(model_or_hrx: Any):
    if hasattr(model_or_hrx, "collections") and hasattr(model_or_hrx, "gdl"):
        return model_or_hrx
    from histra.io.hr_loader import load_model

    return load_model(model_or_hrx)


def reconstruct_global_displacements(
    results_path: str | Path,
    model_or_hrx: Any,
    analysis_key: int,
    combination: int = 1,
    step: Optional[int] = None,
) -> np.ndarray:
    """Least-squares reconstruction from all quad and interface afferences.

    Intermediate C# steps do not contain ``DynamicVectorsState``.  The complete
    set of local element displacement equations is overdetermined for this
    benchmark and reconstructs the 126 generalized DOFs to numerical precision.
    The residual of that reconstruction is validated explicitly.
    """
    model = _resolve_model(model_or_hrx)
    qstates = read_quad_states(results_path, analysis_key, combination, step)
    resolved_step = next(iter(qstates.values())).step
    istates = read_interface_states(results_path, analysis_key, combination, resolved_step)
    rows: list[np.ndarray] = []
    values: list[float] = []
    for key, state in qstates.items():
        element = model.collections.quads.get(key)
        if element is None:
            raise ResultsStateError(f"Quad {key} from database is absent from HRX model")
        for local, target in enumerate(state.u):
            row = np.zeros(model.gdl, dtype=np.float64)
            for aff in element.aff[local]:
                idx = int(aff.gdl) - 1
                if not 0 <= idx < model.gdl:
                    raise ResultsStateError(f"Quad {key} afference DOF {aff.gdl} is outside model range")
                row[idx] += float(aff.alfa)
            rows.append(row)
            values.append(target)
    for key, state in istates.items():
        element = model.collections.interfaces.get(key)
        if element is None:
            raise ResultsStateError(f"Interface {key} from database is absent from HRX model")
        for local, target in enumerate(state.u):
            row = np.zeros(model.gdl, dtype=np.float64)
            for aff in element.aff[local]:
                idx = int(aff.gdl) - 1
                if not 0 <= idx < model.gdl:
                    raise ResultsStateError(f"Interface {key} afference DOF {aff.gdl} is outside model range")
                row[idx] += float(aff.alfa)
            rows.append(row)
            values.append(target)
    matrix = np.asarray(rows)
    rhs = np.asarray(values)
    u, _residuals, rank, _singular = np.linalg.lstsq(matrix, rhs, rcond=None)
    if rank != model.gdl:
        raise ResultsStateError(
            f"Local states determine rank {rank}, but model has {model.gdl} generalized DOFs"
        )
    local_error = np.max(np.abs(matrix @ u - rhs)) if rhs.size else 0.0
    if local_error > 1.0e-9:
        raise ResultsStateError(
            f"Local states are internally inconsistent; maximum reconstruction error={local_error:.6e}"
        )
    return u


def read_global_displacements(
    results_path: str | Path,
    analysis_key: int,
    combination: int = 1,
    step: Optional[int] = None,
    *,
    model_or_hrx: Any | None = None,
    size: Optional[int] = None,
) -> np.ndarray:
    """Return authoritative final globals or validated intermediate reconstruction."""
    try:
        u, _v, found_step = read_dynamic_vectors(
            results_path, analysis_key, combination, step, size=size
        )
        if step is None or int(step) == found_step:
            return u
    except ResultsStateError:
        if model_or_hrx is None:
            raise ResultsStateError(
                "The requested step has no DynamicVectorsState. Supply model_or_hrx "
                "to reconstruct intermediate global displacements from local states."
            )
    return reconstruct_global_displacements(
        results_path, model_or_hrx, analysis_key, combination, step
    )


def read_load_multiplier(
    hrx_path: str | Path,
    analysis_key: int,
    step: int,
) -> float:
    """Reproduce LoadControl's public-step load multiplier from the HRX function."""
    from histra.io.hr_loader import load_model

    model = load_model(hrx_path)
    analysis = model.collections.analyses.get(int(analysis_key))
    if analysis is None:
        raise ResultsStateError(f"Analysis {analysis_key} is absent from {hrx_path}")
    if str(analysis.integration_method) != "LoadControl":
        raise ResultsStateError(
            f"Load multiplier reconstruction currently supports LoadControl, not {analysis.integration_method}"
        )
    items = sorted(
        [(float(i.pseudo_time), float(i.multiplier)) for i in (analysis.load_function.items if analysis.load_function else [])]
    )
    if not items:
        raise ResultsStateError(f"Analysis {analysis_key} has no load-function points")
    t = items[0][0]
    mult = items[0][1] * float(analysis.mult)
    for _ in range(int(step)):
        if t >= items[-1][0] - 1e-12:
            break
        pair = None
        for a, b in zip(items, items[1:]):
            if t < b[0] - 1e-12:
                pair = (a, b)
                break
        if pair is None:
            pair = (items[-2], items[-1])
        (t0, f0), (t1, f1) = pair
        discr = abs(float(analysis.load_function.discr_val))
        if discr <= 0.0:
            raise ResultsStateError("Load-function discretization must be positive")
        span = abs(f1 - f0) if bool(analysis.load_function.type_discr) else abs(t1 - t0)
        count = max(1, int(np.ceil(span / discr)))
        dt = (t1 - t0) / count
        dt = min(dt, t1 - t) if dt >= 0 else max(dt, t1 - t)
        df = (f1 - f0) * (dt / (t1 - t0)) * float(analysis.mult) if abs(t1 - t0) > 1e-30 else 0.0
        t += dt
        mult += df
    return float(mult)


def find_results_path(hrx_path: str | Path) -> Optional[Path]:
    """Return the sibling C# ``.Results`` database, when present."""
    p = Path(hrx_path)
    for cand in (p.with_suffix(".Results"), p.parent / (p.stem + ".Results")):
        if cand.exists():
            return cand
    return None
