from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import histra.solver.model_manager as model_manager_module
from histra.solver.incremental_integrator import IncrementalIntegrator
from histra.solver.model_manager import ModelManager


class _LinearSystemStub:
    def __init__(self) -> None:
        self.zero_load_calls = 0

    def set_zero_load(self) -> None:
        self.zero_load_calls += 1


class _IntegratorStub(IncrementalIntegrator):
    def update(self, model, p, an):
        return 0

    def new_step(self, p, model, ls, an, combination, step, dof):
        return None

    def commit(self, model, an, disp, dof_max, has_domain_changed):
        return True


def test_static_target_load_is_reused_only_for_matching_analysis_signature(monkeypatch):
    calls: list[tuple[object, int | None, int]] = []

    def fake_assemble(model, analysis_key=None, combination=1):
        calls.append((model, analysis_key, combination))
        return np.asarray([float(len(calls)), 2.0], dtype=np.float64)

    monkeypatch.setattr(model_manager_module, "assemble_load_vector", fake_assemble)
    monkeypatch.setattr(ModelManager, "_ptarget", None)
    monkeypatch.setattr(ModelManager, "_ptarget_signature", None)

    model = object()
    other_model = object()
    ls = _LinearSystemStub()

    ModelManager.assemble_load(model, ls, 7, 1)
    first = ModelManager._ptarget
    np.testing.assert_array_equal(first, [1.0, 2.0])

    ModelManager.assemble_load(model, ls, 7, 1, reuse_current=True)
    assert ModelManager._ptarget is first
    assert len(calls) == 1

    ModelManager.assemble_load(model, ls, 7, 2, reuse_current=True)
    np.testing.assert_array_equal(ModelManager._ptarget, [2.0, 2.0])
    ModelManager.assemble_load(model, ls, 8, 2, reuse_current=True)
    np.testing.assert_array_equal(ModelManager._ptarget, [3.0, 2.0])
    ModelManager.assemble_load(other_model, ls, 8, 2, reuse_current=True)
    np.testing.assert_array_equal(ModelManager._ptarget, [4.0, 2.0])

    # A mandatory fresh assembly must never reuse even a matching signature.
    ModelManager.assemble_load(other_model, ls, 8, 2)
    np.testing.assert_array_equal(ModelManager._ptarget, [5.0, 2.0])
    assert len(calls) == 5
    assert ls.zero_load_calls == 6


def test_incremental_target_refresh_requests_same_analysis_reuse(monkeypatch):
    calls: list[tuple[object, object, int, int, bool]] = []

    def fake_assemble(cls, model, ls, analysis_key, combination, *, reuse_current=False):
        calls.append((model, ls, analysis_key, combination, reuse_current))

    monkeypatch.setattr(
        ModelManager,
        "assemble_load",
        classmethod(fake_assemble),
    )

    model = object()
    ls = object()
    program = SimpleNamespace(ls=ls)
    analysis = SimpleNamespace(key=17, pdelta_effect=False)

    assert _IntegratorStub().update_ptarget(program, model, analysis, 3, 4)
    assert calls == [(model, ls, 17, 3, True)]
