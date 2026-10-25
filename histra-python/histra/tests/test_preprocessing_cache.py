"""Unit tests for the prepared model preprocessing disk caching subsystem."""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from histra.io import load_model
from histra.preprocessing.cache import (
    _PREPROCESSING_CACHE_VERSION,
    compute_hrx_fingerprint,
    get_model_cache_path,
    is_cache_enabled,
    load_prepared_cache,
    save_prepared_cache,
)
from histra.preprocessing.prepare_model import prepare_model
from histra.solver import ModelManager


@pytest.fixture
def small_model_path() -> Path:
    candidates = [
        Path(__file__).resolve().parents[1] / "model-benchmark" / "model.hrx",
        Path("my_model/benchmark_1/benchmark.hrx"),
        Path(__file__).resolve().parents[1] / "model-live" / "model.hrx",
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    pytest.skip("No benchmark model found for cache test")


def test_compute_hrx_fingerprint(small_model_path: Path):
    fp1 = compute_hrx_fingerprint(small_model_path)
    fp2 = compute_hrx_fingerprint(small_model_path)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex string


def test_get_model_cache_path(small_model_path: Path, tmp_path: Path, monkeypatch):
    # Explicit directory
    p1 = get_model_cache_path(small_model_path, cache_dir=tmp_path)
    assert p1.parent == tmp_path
    assert p1.name == f"{small_model_path.name}.prepared.cache"

    # Environment variable override
    monkeypatch.setenv("HISTRA_CACHE_DIR", str(tmp_path / "custom_cache"))
    p2 = get_model_cache_path(small_model_path)
    assert p2.parent == tmp_path / "custom_cache"


def test_is_cache_enabled(monkeypatch):
    assert is_cache_enabled(True) is True
    assert is_cache_enabled(False) is False

    monkeypatch.setenv("HISTRA_PREPARED_CACHE", "1")
    assert is_cache_enabled() is True

    monkeypatch.setenv("HISTRA_PREPARED_CACHE", "0")
    assert is_cache_enabled() is False


def test_save_and_load_prepared_cache(small_model_path: Path, tmp_path: Path):
    model = load_model(small_model_path)
    report = prepare_model(model, force=True)

    cache_file = tmp_path / "test.prepared.cache"
    saved_path = save_prepared_cache(model, report, small_model_path, cache_path=cache_file)
    assert saved_path == cache_file
    assert cache_file.exists()

    loaded = load_prepared_cache(small_model_path, cache_path=cache_file)
    assert loaded is not None
    loaded_model, loaded_report = loaded

    assert loaded_model.requires_python_preparation is False
    assert loaded_model.is_locked is True
    assert len(loaded_model.collections.quads) == len(model.collections.quads)
    assert len(loaded_model.collections.interfaces) == len(model.collections.interfaces)
    assert loaded_report.quads == report.quads
    assert loaded_report.interfaces == report.interfaces
    assert loaded_report.transverse_springs == report.transverse_springs


def test_cache_invalidation_on_corrupt_file(small_model_path: Path, tmp_path: Path):
    cache_file = tmp_path / "corrupt.prepared.cache"
    cache_file.write_bytes(b"garbage corrupt data not a pickle")

    loaded = load_prepared_cache(small_model_path, cache_path=cache_file)
    assert loaded is None


def test_prepare_model_transparent_cache(small_model_path: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HISTRA_CACHE_DIR", str(tmp_path))

    m1 = load_model(small_model_path)
    r1 = prepare_model(m1, force=True, use_cache=True)
    cache_file = get_model_cache_path(small_model_path, cache_dir=tmp_path)
    assert cache_file.exists()

    # Second load with use_cache=True should restore from cache
    m2 = load_model(small_model_path)
    r2 = prepare_model(m2, use_cache=True)
    assert r2.interfaces == r1.interfaces
    assert len(m2.collections.interfaces) == len(m1.collections.interfaces)
    assert m2.requires_python_preparation is False


def test_model_manager_prepare_model_use_cache(small_model_path: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HISTRA_CACHE_DIR", str(tmp_path))

    m1 = load_model(small_model_path)
    r1 = ModelManager.prepare_model(m1, force=True, use_cache=True)
    assert r1.interfaces > 0

    m2 = load_model(small_model_path)
    r2 = ModelManager.prepare_model(m2, use_cache=True)
    assert r2.interfaces == r1.interfaces
    assert len(m2.collections.interfaces) == len(m1.collections.interfaces)
