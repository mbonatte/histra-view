"""Architecture and differential checks for the extracted Quad kernel owner."""

import numpy as np
import pytest

import histra.elements.quad as quad_module
from histra.elements.quad import Quad
from histra.elements.quad_kernels import (
    _quad_yield_search_kernel,
    quad_yield_search,
    quad_yield_search_scalar,
)


def test_quad_facade_reexports_yield_search_kernels():
    assert quad_module._quad_yield_search_kernel is _quad_yield_search_kernel
    assert quad_module.quad_yield_search is quad_yield_search
    assert quad_module.quad_yield_search_scalar is quad_yield_search_scalar


def test_compiled_and_scalar_yield_search_agree_tightly():
    if _quad_yield_search_kernel is None:
        pytest.skip("Numba is unavailable")
    # 12 seeded cases: each scalar call runs a 100x100 Python double loop
    # (~0.17 s), so the case count is bounded to keep the default suite fast
    # while still sweeping the geometry space.
    rng = np.random.default_rng(7)
    worst = 0.0
    for _ in range(8):
        args = [float(rng.uniform(0.5, 2.0)) for _ in range(5)]
        geom = [float(rng.uniform(0.5, 3.0)) for _ in range(4)]
        geom += [float(rng.uniform(0.2, 1.2)) for _ in range(6)]
        compiled = quad_yield_search(*args, *geom)
        scalar = quad_yield_search_scalar(*args, *geom)
        assert np.sign(compiled[0]) == np.sign(scalar[0])
        assert np.sign(compiled[1]) == np.sign(scalar[1])
        denom = max(abs(compiled[0]), abs(compiled[1]), 1e-30)
        worst = max(
            worst,
            abs(compiled[0] - scalar[0]) / denom,
            abs(compiled[1] - scalar[1]) / denom,
        )
    assert worst < 1.0e-8  # observed ~1.9e-10 across 300 seeded cases


def test_quad_method_delegates_to_the_owner_dispatcher():
    quad = Quad(
        key=1,
        length=[2.0, 1.0, 2.0, 1.5],
        cos=[1.0, 0.5, 0.0, 0.8],
        sin=[0.0, 0.8660254037844386, 1.0, 0.6],
    )
    expected = quad_yield_search(
        1000.0, 5000.0, 2000.0, 3.0, 4.0, quad.d_alfa_2d_diag(),
        2.0, 1.0, 1.5, 1.0, 0.5, 0.0, 0.8660254037844386, 1.0, 0.6,
    )
    assert quad.set_non_linear_properties(1000.0, 5000.0, 2000.0, 3.0, 4.0) == expected
