"""The compiled centroid calculation must preserve the C# Single boundaries."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from histra.postprocessing import _spring_area_centroid_local_xy
from histra.solver.hysteretic_kernels.resultant_geometry import resultant_moment_arms


@pytest.mark.parametrize("seed", range(5))
def test_compiled_moment_arms_match_scalar_float32_bits(seed):
    rng = np.random.default_rng(seed)
    interfaces = []
    counts = []
    for _ in range(12):
        nrow, ncol = rng.integers(1, 12, size=2)
        coordinates = rng.normal(size=(4, 2)) * 10.0 ** rng.uniform(-5, 5)
        interfaces.append(SimpleNamespace(
            nrow=int(nrow), ncol=int(ncol), length=float(10.0 ** rng.uniform(-5, 5)),
            vint2d=[SimpleNamespace(x=x, y=y) for x, y in coordinates],
        ))
        counts.append(int(nrow * ncol))
    expected = np.asarray([_spring_area_centroid_local_xy(i, index)
                           for i, count in zip(interfaces, counts)
                           for index in range(count)], dtype=np.float32)
    offsets = np.concatenate(([0], np.cumsum(counts))).astype(np.int64)
    x, y = resultant_moment_arms(
        np.asarray([[[v.x, v.y] for v in i.vint2d] for i in interfaces], np.float32),
        np.asarray([i.length for i in interfaces], np.float32),
        np.asarray([i.nrow for i in interfaces], np.int64),
        np.asarray([i.ncol for i in interfaces], np.int64),
        offsets[:-1], offsets[1:], int(offsets[-1]),
    )
    actual = np.column_stack((x, y))
    np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))


def test_prepared_model_moment_arms_match_scalar():
    from histra import load_model
    from histra.solver import ModelManager
    from histra.solver.hysteretic_runtime import build_hysteretic_batch

    path = Path(__file__).resolve().parents[1] / "model-live/model.hrx"
    model = load_model(path)
    ModelManager.prepare_model(model, force=True)
    runtime = build_hysteretic_batch(model)
    runtime._ensure_resultant_moment_arms()
    expected = [_spring_area_centroid_local_xy(record.interface, index)
                for record in runtime.records for index in range(record.stop - record.start)]
    actual = np.column_stack((runtime._resultant_vec_x, runtime._resultant_vec_y))
    np.testing.assert_array_equal(actual.view(np.uint32), np.asarray(expected, np.float32).view(np.uint32))
