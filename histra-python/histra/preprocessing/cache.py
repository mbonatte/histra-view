"""Disk and memory caching for freshly prepared computational models.

Preparing large 3D macro-element meshes (e.g. 50k+ DOFs with tens of thousands
of interfaces and hundreds of thousands of springs) involves extensive geometric
polygon clipping, coordinate transformations, and constitutive spring generation.
Caching the resulting Python-prepared model against the SHA-256 fingerprint of the
source HRX file allows subsequent analysis sessions, parameter sweeps, and
benchmarks to bypass redundant preprocessing with bit-for-bit exact parity.
"""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

from histra.model import Model
from histra.preprocessing.errors import ModelPreparationError
from histra.preprocessing.prepare_model import PreparationReport

logger = logging.getLogger(__name__)

_PREPROCESSING_CACHE_VERSION = "1.1.0"


def is_cache_enabled(requested: bool | None = None) -> bool:
    """Check whether prepared model disk caching is enabled."""
    if requested is not None:
        return bool(requested)
    env_val = os.environ.get("HISTRA_PREPARED_CACHE", "").strip().lower()
    return env_val in ("1", "true", "yes", "on")


def compute_hrx_fingerprint(hrx_path: str | os.PathLike[str]) -> str:
    """Compute deterministic SHA-256 fingerprint of the source HRX file."""
    path = Path(hrx_path).resolve()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_model_cache_path(
    hrx_path: str | os.PathLike[str],
    cache_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Return the filesystem path for the prepared model cache."""
    path = Path(hrx_path).resolve()
    if cache_dir is not None:
        base_dir = Path(cache_dir).resolve()
    else:
        env_dir = os.environ.get("HISTRA_CACHE_DIR")
        if env_dir:
            base_dir = Path(env_dir).resolve()
        else:
            base_dir = path.parent / ".histra_cache"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{path.name}.prepared.cache"


def load_prepared_cache(
    hrx_path: str | os.PathLike[str],
    cache_path: str | os.PathLike[str] | None = None,
) -> tuple[Model, PreparationReport] | None:
    """Load a prepared model and report from disk cache if valid."""
    path = Path(hrx_path).resolve()
    target_cache = Path(cache_path).resolve() if cache_path else get_model_cache_path(path)
    if not target_cache.exists():
        return None

    try:
        current_fp = compute_hrx_fingerprint(path)
        with open(target_cache, "rb") as f:
            data = pickle.load(f)

        if not isinstance(data, dict):
            return None
        if data.get("version") != _PREPROCESSING_CACHE_VERSION:
            return None
        if data.get("fingerprint") != current_fp:
            return None

        model = data.get("model")
        report = data.get("report")
        if not isinstance(model, Model) or not isinstance(report, PreparationReport):
            return None

        model.source_path = str(path)
        model.requires_python_preparation = False
        return model, report
    except Exception as exc:
        logger.debug("Failed to load prepared cache from %s: %s", target_cache, exc)
        return None


def save_prepared_cache(
    model: Model,
    report: PreparationReport,
    hrx_path: str | os.PathLike[str],
    cache_path: str | os.PathLike[str] | None = None,
) -> Path | None:
    """Save freshly prepared model and report to disk cache atomically."""
    path = Path(hrx_path).resolve()
    target_cache = Path(cache_path).resolve() if cache_path else get_model_cache_path(path)
    try:
        fingerprint = compute_hrx_fingerprint(path)
        payload = {
            "version": _PREPROCESSING_CACHE_VERSION,
            "fingerprint": fingerprint,
            "model": model,
            "report": report,
        }
        target_cache.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically using a temporary file in the same directory
        temp_file = tempfile.NamedTemporaryFile(
            dir=target_cache.parent, prefix="prep_cache_", delete=False
        )
        try:
            with temp_file as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temp_file.name, target_cache)
        except Exception:
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise
        return target_cache
    except Exception as exc:
        logger.debug("Failed to save prepared cache to %s: %s", target_cache, exc)
        return None
