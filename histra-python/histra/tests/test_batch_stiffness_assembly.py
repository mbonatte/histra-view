from pathlib import Path
import time
import numpy as np
import pytest

from histra import load_model
from histra.solver.assembler import _assemble_global_k_legacy
from histra.solver.model_manager import ModelManager
from histra.types.linear_system import LinearSystem

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "model-benchmark" / "model.hrx"
ARTICLE_DIR = ROOT.parent / "my_model" / "Article_Models_Benchmark"


def _candidate_models() -> list[Path]:
    models = [DEFAULT_MODEL]
    chain_model = ROOT / "model-chain" / "model.hrx"
    if chain_model.exists():
        models.append(chain_model)
    live_model = ROOT / "model-live" / "model.hrx"
    if live_model.exists():
        models.append(live_model)
    if ARTICLE_DIR.exists():
        for name in ["Bridge_1.hrx", "Bridge_2.hrx", "Bridge_3.1_Coarse.hrx"]:
            p = ARTICLE_DIR / name
            if p.exists() and p not in models:
                models.append(p)
    return models


def test_batch_stiffness_matches_legacy_assembly_exact() -> None:
    test_model_paths = [DEFAULT_MODEL]
    if ARTICLE_DIR.exists() and (ARTICLE_DIR / "Bridge_1.hrx").exists():
        test_model_paths.append(ARTICLE_DIR / "Bridge_1.hrx")

    for path in test_model_paths:
        model = load_model(path)
        ModelManager.prepare_model(model, force=True)
        ModelManager.prepare_hysteretic_batch(model)

        ls = LinearSystem(model.gdl)

        for alfa in [0.0, 0.5, 1.0]:
            k_legacy = _assemble_global_k_legacy(model, alfa=alfa, recompute_elements=True)
            ModelManager.compute_ktang(model, ls, alfa)
            k_batch = ls.k

            diff_mat = k_batch - k_legacy
            max_diff = np.max(np.abs(diff_mat.data)) if diff_mat.nnz > 0 else 0.0
            rel_diff = max_diff / np.max(np.abs(k_legacy.data))
            assert rel_diff < 1e-13, f"{path.name} alfa={alfa} relative diff {rel_diff} exceeds 1e-13"


def test_batch_stiffness_preserves_non_uniform_plastic_tangents() -> None:
    test_model_paths = [DEFAULT_MODEL]
    if ARTICLE_DIR.exists() and (ARTICLE_DIR / "Bridge_1.hrx").exists():
        test_model_paths.append(ARTICLE_DIR / "Bridge_1.hrx")

    for path in test_model_paths:
        model = load_model(path)
        ModelManager.prepare_model(model, force=True)
        runtime = ModelManager.prepare_hysteretic_batch(model)
        assert runtime is not None

        # Mutate tangent stiffnesses of the first 50 springs in runtime.trial to simulate plasticity
        count = min(50, runtime.trial.shape[0])
        runtime.trial[:count, 9] = runtime.trial[:count, 9] * 0.12345
        runtime.sync_tangents_to_objects()

        ls = LinearSystem(model.gdl)

        k_legacy = _assemble_global_k_legacy(model, alfa=1.0, recompute_elements=True)
        ModelManager.compute_ktang(model, ls, 1.0)
        k_batch = ls.k

        diff_mat = k_batch - k_legacy
        max_diff = np.max(np.abs(diff_mat.data)) if diff_mat.nnz > 0 else 0.0
        rel_diff = max_diff / np.max(np.abs(k_legacy.data))
        assert rel_diff < 1e-13, f"{path.name} plastic tangent relative diff {rel_diff} exceeds 1e-13"


def test_batch_stiffness_across_multiple_article_models() -> None:
    models = _candidate_models()
    assert len(models) >= 1, "At least one model must be tested"

    for path in models:
        model = load_model(path)
        ModelManager.prepare_model(model, force=True)
        ModelManager.prepare_hysteretic_batch(model)
        ls = LinearSystem(model.gdl)

        for alfa in [0.0, 1.0]:
            k_legacy = _assemble_global_k_legacy(model, alfa=alfa, recompute_elements=True)
            ModelManager.compute_ktang(model, ls, alfa)
            k_batch = ls.k

            diff_mat = k_batch - k_legacy
            max_diff = np.max(np.abs(diff_mat.data)) if diff_mat.nnz > 0 else 0.0
            rel_diff = max_diff / np.max(np.abs(k_legacy.data))
            assert rel_diff < 1e-13, f"{path.name} alfa={alfa} rel_diff {rel_diff} exceeds 1e-13"


def test_batch_stiffness_performance_gain() -> None:
    path = ARTICLE_DIR / "Bridge_1.hrx" if (ARTICLE_DIR / "Bridge_1.hrx").exists() else DEFAULT_MODEL
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    ModelManager.prepare_hysteretic_batch(model)
    ls = LinearSystem(model.gdl)

    # Warmup
    ModelManager.compute_ktang(model, ls, 1.0)

    # Measure batch compute_ktang
    t0 = time.perf_counter()
    reps = 50
    for _ in range(reps):
        ModelManager.compute_ktang(model, ls, 1.0)
    dt_batch = (time.perf_counter() - t0) / reps

    # Batch compute_ktang must be under 5 ms
    assert dt_batch < 0.005, f"{path.name} batch stiffness time {dt_batch*1000:.2f} ms exceeds 5 ms threshold"
