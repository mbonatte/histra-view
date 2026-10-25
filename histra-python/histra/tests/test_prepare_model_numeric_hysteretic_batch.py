from __future__ import annotations

from dataclasses import fields
import importlib
import struct

import numpy as np
import pytest

pm = importlib.import_module("histra.preprocessing.prepare_model")
from histra.preprocessing.constitutive_laws import HystereticLaw as _HystereticLaw
from histra.preprocessing.spring_factory import (
    _configure_combined_hysteretic,
    _configure_combined_hysteretic_batch,
)
from histra.springs.hysteretic import SpringHysteretic


def _law(tension: str, compression: str, scale: float) -> _HystereticLaw:
    return _HystereticLaw(
        E=11.0 * scale,
        fy_t=1.7 * scale,
        fy_c=8.3 * scale,
        tensile_curve=tension,
        compressive_curve=compression,
        ratio_et_t=0.13,
        ratio_et_c=0.07,
        alfa_r_t=1.2,
        alfa_r_c=1.3,
        alfa_u_t=2.4,
        alfa_u_c=2.7,
        G_t=0.045 * scale,
        G_c=0.31 * scale,
        eps_u_t=0.012,
        eps_u_c=-0.028,
        law_type="Masonry",
    )


def _assert_exact(left, right) -> None:
    if isinstance(left, float) or isinstance(right, float):
        assert struct.pack("=d", float(left)) == struct.pack("=d", float(right))
        return
    if isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right):
            _assert_exact(a, b)
        return
    assert left == right


def _assert_spring_exact(left: SpringHysteretic, right: SpringHysteretic) -> None:
    for field in fields(SpringHysteretic):
        _assert_exact(getattr(left, field.name), getattr(right, field.name))


@pytest.mark.parametrize(
    ("law1", "law2"),
    [
        (_law("LinearSoftening", "LinearSoftening", 1.0), _law("LinearHardening", "LinearHardening", 1.4)),
        (_law("Elastic", "Elastic", 0.9), _law("LinearSoftening", "Parabolic", 1.6)),
        (_law("Exponential", "Parabolic", 1.2), _law("LinearSoftening", "LinearSoftening", 0.8)),
        (_law("LinearHardening", "Parabolic", 1.7), _law("Exponential", "Elastic", 1.1)),
    ],
)
def test_numeric_combined_hysteretic_batch_matches_scalar_bit_exactly(law1, law2) -> None:
    rng = np.random.default_rng(73421)
    count = 17
    props1 = np.column_stack(
        (
            rng.uniform(4.0, 60.0, count),
            rng.uniform(0.02, 2.0, count),
            rng.uniform(0.05, 1.5, count),
        )
    )
    props2 = np.column_stack(
        (
            rng.uniform(5.0, 75.0, count),
            rng.uniform(0.03, 2.4, count),
            rng.uniform(0.06, 1.7, count),
        )
    )

    batch = _configure_combined_hysteretic_batch(
        props1, law1, props2, law2, interface_key=37
    )
    assert len(batch) == count

    for index in range(count):
        scalar = _configure_combined_hysteretic(
            *map(float, props1[index]), law1,
            *map(float, props2[index]), law2,
        )
        scalar.key = index
        scalar.parent_key = 37
        scalar.parent_type = "Interface"
        scalar.spring_purpose = "Transversal1"
        scalar.length = 0.0
        _assert_spring_exact(batch[index], scalar)


def test_f32_direct_binding_preserves_system_single_bits_exactly():
    values = (
        0.0,
        -0.0,
        1.0,
        -1.0,
        1.0 / 3.0,
        np.nextafter(1.0, 2.0),
        np.nextafter(1.0, 0.0),
        np.finfo(np.float32).tiny,
        np.finfo(np.float32).max,
    )
    for value in values:
        actual = pm._f32(value)
        expected = np.float32(value)
        assert isinstance(actual, np.float32)
        assert actual.view(np.uint32) == expected.view(np.uint32)
