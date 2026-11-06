"""Regression tests for TransverseFiberGroup zero-materialization memory safety.

Ensures that solver lifecycle routines (preparation, backend inspection, virgin
reset, batch clearing, stiffness assembly, state snapshots, reaction calculation,
and session deepcopy) never eagerly materialize SpringHysteretic proxy objects
or duplicate transient solver caches into cloned models.
"""
from __future__ import annotations

import copy
from pathlib import Path
import numpy as np
import pytest

from histra import load_model, AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.solver.state_snapshot import SolverStateSnapshot
from histra.postprocessing import compute_total_reaction
from histra.solver.assembler import assemble_global_k, _get_stiffness_assembly_plan
from histra.springs.transverse_fiber_group import TransverseFiberGroup
from histra.springs.hysteretic import SpringHysteretic


MODEL_3D_DISTRIBUTED = Path("/home/mauricio/coding/dmem_validation/3d_scour/models/Bridge_scour_3d_Distributed.hrx")


def _count_materialized_proxies(model) -> int:
    return sum(
        len(getattr(intf.trasv_1, "_cache", ()))
        for intf in model.collections.interfaces.values()
    )


def test_transverse_fiber_group_lifecycle_zero_materialization():
    """Verify that synthetic TransverseFiberGroup lifecycle does not materialize proxies."""
    n_fibers = 100
    params = np.ones((n_fibers, 20), dtype=np.float64)
    params[:, 13] = 250.0  # E1p
    k = np.full(n_fibers, 200.0, dtype=np.float64)
    area = np.full(n_fibers, 10.0, dtype=np.float64)
    group = TransverseFiberGroup(params=params, k=k, area=area, parent_key=1)

    assert len(group._cache) == 0
    assert group.is_batch_backed

    # revert_to_start and revert_to_last_commit should not allocate proxies
    group.revert_to_start()
    assert len(group._cache) == 0
    assert np.all(group._trial[:, 9] == 250.0)

    group.revert_to_last_commit()
    assert len(group._cache) == 0

    # deepcopy should share immutable _params and produce empty _cache
    group_copy = copy.deepcopy(group)
    assert len(group_copy._cache) == 0
    assert group_copy._params is group._params

    # on-demand access materializes strictly the requested proxy
    proxy = group[5]
    assert isinstance(proxy, SpringHysteretic)
    assert len(group._cache) == 1
    assert proxy.k == 200.0
    assert proxy.area == 10.0

    # Mutating proxy and calling flush_cache_to_arrays syncs back
    proxy.k = 300.0
    group.flush_cache_to_arrays()
    assert group._k[5] == 300.0


@pytest.mark.skipif(not MODEL_3D_DISTRIBUTED.exists(), reason="3D bridge benchmark model not present")
def test_3d_model_solver_stages_retain_zero_materialized_proxies():
    """Verify that a full 3D bridge model retains 0 materialized proxies across all solver stages."""
    model = load_model(MODEL_3D_DISTRIBUTED)
    ModelManager.prepare_model(model, force=True)
    assert _count_materialized_proxies(model) == 0

    # 1. Performance caches on interfaces and quads
    for intf in model.collections.interfaces.values():
        intf._ensure_performance_cache()
    for quad in model.collections.quads.values():
        quad._ensure_dn_cache(model.collections)
    assert _count_materialized_proxies(model) == 0

    # 2. Hysteretic runtime build and clear
    runtime = ModelManager.prepare_hysteretic_batch(model, rebuild=True)
    assert runtime is not None
    assert _count_materialized_proxies(model) == 0

    ModelManager.clear_hysteretic_batch()
    assert _count_materialized_proxies(model) == 0

    # 3. Stiffness assembly plan
    plan = _get_stiffness_assembly_plan(model)
    assert plan is not None
    assert _count_materialized_proxies(model) == 0

    # 4. Reaction computation
    compute_total_reaction(model)
    assert _count_materialized_proxies(model) == 0

    # 5. Deepcopy model and session
    session = AnalysisSession(model)
    assert _count_materialized_proxies(model) == 0

    session_copy = copy.deepcopy(session)
    assert _count_materialized_proxies(session.model) == 0
    assert _count_materialized_proxies(session_copy.model) == 0

    # Cloned model should not have transient runtime attachments
    for intf in session_copy.model.collections.interfaces.values():
        assert getattr(intf, "_perf_hysteretic_batch", None) is None
    assert getattr(session_copy.model, "_perf_stiffness_assembly_plan", None) is None
