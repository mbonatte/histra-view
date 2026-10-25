from __future__ import annotations

from pathlib import Path

import pytest

from histra.elements.quad import Quad
from histra.io.hr_loader import load_model
from histra.model.model import Collections, Model
from histra.preprocessing import (
    ModelPreprocessingRequiredError,
    inspect_solver_readiness,
    require_solver_ready,
)


ROOT = Path(__file__).resolve().parents[1]
READY_HRX = ROOT / "model-live" / "model.hrx"


def test_quad_has_explicit_optional_spring_field() -> None:
    quad = Quad()
    assert quad.spring is None
    assert quad.springs == []


def test_solver_ready_locked_reference_model_passes() -> None:
    model = load_model(READY_HRX)
    report = inspect_solver_readiness(model)
    assert report.is_ready
    assert report.gdl > 0
    assert report.quad_spring_count == report.quad_count
    assert report.interface_spring_count == report.interface_count
    require_solver_ready(model)


def test_geometry_only_model_reports_all_required_preprocessing_outputs() -> None:
    model = Model(
        source_path="raw.hrx",
        is_locked=False,
        gdl=0,
        collections=Collections(quads={1: Quad(key=1), 2: Quad(key=2)}),
    )
    report = inspect_solver_readiness(model)
    assert not report.is_ready
    text = report.format(model.source_path)
    assert "GDL=0" in text
    assert "Quad diagonal springs (2 missing)" in text
    assert "Quad afference matrices (2 incomplete)" in text
    assert "interfaces (none present)" in text

    with pytest.raises(ModelPreprocessingRequiredError, match="requires HiStrA preprocessing"):
        require_solver_ready(model)
