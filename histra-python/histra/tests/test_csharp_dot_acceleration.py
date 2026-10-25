from __future__ import annotations

import numpy as np
import pytest

from histra.solver import line_search, newton_line_search


@pytest.mark.parametrize("module", [line_search, newton_line_search])
def test_compiled_csharp_dot_is_bit_exact(module) -> None:
    rng = np.random.default_rng(20260819)
    for size in (0, 1, 2, 3, 31, 257, 4096):
        left = rng.standard_normal(size)
        right = rng.standard_normal(size)
        expected = module._csharp_dot_python(left, right)
        actual = module._csharp_dot(left, right)
        assert np.float64(actual).view(np.uint64) == np.float64(expected).view(np.uint64)


@pytest.mark.parametrize("module", [line_search, newton_line_search])
def test_compiled_csharp_dot_keeps_shape_validation(module) -> None:
    with pytest.raises(ValueError, match="dot shape mismatch"):
        module._csharp_dot(np.zeros(3), np.zeros(4))
