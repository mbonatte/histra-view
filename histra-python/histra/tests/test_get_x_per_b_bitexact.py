"""Bit-exactness lock for the C# ``operator ^`` energy reduction.

``LinearSystem.get_x_per_b`` must reproduce C#
``MatrixManager.Vector.operator ^`` — a strictly left-associated scalar loop —
bit for bit. The production implementation uses ``np.add.accumulate`` (a
sequential C loop with identical order and rounding). This test pins the
production implementation to the literal scalar loop on adversarial
magnitude mixes, because a different reduction (pairwise ``np.sum``, Neumaier
``builtin sum``, BLAS ``np.dot``) changes the last ulps and can flip marginal
energy-convergence decisions, which is a path-dependent behavior change.
"""

from __future__ import annotations

import struct

import numpy as np

from histra.types.linear_system import LinearSystem


def _bits(value: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _scalar_reference(x: np.ndarray, b: np.ndarray) -> float:
    value = 0.0
    for index in range(len(x)):
        value += float(x[index]) * float(b[index])
    return value


def test_get_x_per_b_is_bit_identical_to_the_csharp_reduction_order():
    rng = np.random.default_rng(20260828)
    for _ in range(500):
        n = int(rng.integers(1, 600))
        x = rng.normal(0.0, 10.0 ** rng.integers(-8, 9), n)
        b = rng.normal(0.0, 10.0 ** rng.integers(-8, 9), n)
        ls = LinearSystem(n)
        ls.set_x_vector(x)
        ls.set_b_vector(b)
        assert _bits(ls.get_x_per_b()) == _bits(_scalar_reference(x, b))


def test_get_x_per_b_empty_system_returns_zero():
    ls = LinearSystem(0)
    assert ls.get_x_per_b() == 0.0
