from __future__ import annotations

import importlib

import numpy as np
import pytest


aff = importlib.import_module("histra.preprocessing.afference")


def _float32_bits(values: tuple[np.float32, np.float32]) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).view(np.uint32)


@pytest.mark.skipif(aff._inverse_bilinear_f32_nb is None, reason="Numba is unavailable")
def test_compiled_inverse_bilinear_matches_scalar_float32_reference_bit_exactly() -> None:
    rng = np.random.default_rng(20260820)
    base = np.asarray(
        [
            [-2.0, -1.0, 0.0],
            [2.2, -0.8, 0.0],
            [1.8, 1.4, 0.0],
            [-2.1, 1.1, 0.0],
        ],
        dtype=np.float32,
    )

    # Exercise every dropped-coordinate branch used for arbitrarily oriented
    # Quad faces. Points are generated through the production float32 forward
    # map so the comparison isolates arithmetic/reduction ordering.
    orientations = ((0, 1, 2), (0, 2, 1), (2, 1, 0))
    for orientation in orientations:
        for _ in range(128):
            vertices = base.copy()
            vertices[:, :2] += rng.normal(0.0, 0.03, (4, 2)).astype(np.float32)
            vertices = np.ascontiguousarray(vertices[:, orientation])
            u = np.float32(rng.uniform(-0.95, 0.95))
            v = np.float32(rng.uniform(-0.95, 0.95))
            point = aff._bilinear_f32(vertices, u, v)

            expected = aff._inverse_bilinear_f32_python(vertices, point)
            compiled = aff._inverse_bilinear_f32_nb(vertices, point)
            dispatched = aff._inverse_bilinear_f32(vertices, point)

            np.testing.assert_array_equal(
                _float32_bits(compiled), _float32_bits(expected)
            )
            np.testing.assert_array_equal(
                _float32_bits(dispatched), _float32_bits(expected)
            )
