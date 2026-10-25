from __future__ import annotations

import pytest

from histra.solver.hysteretic_batch import _phase_from_code
from histra.types.phase_enum import PhaseEnum


def test_phase_code_cache_returns_canonical_enum_singletons() -> None:
    for phase in PhaseEnum:
        assert _phase_from_code(int(phase)) is phase
        assert _phase_from_code(float(phase)) is phase


def test_phase_code_cache_preserves_invalid_code_failure() -> None:
    with pytest.raises(ValueError):
        _phase_from_code(99)
