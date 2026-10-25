"""Small self-contained smoke tests for the current HRX loader."""
from pathlib import Path

from histra.io.hr_loader import load_model
from histra.model.model import Model


def test_load_supplied_model():
    path = Path(__file__).resolve().parents[1] / "model-output" / "model.hrx"
    model = load_model(path)
    assert isinstance(model, Model)
    assert model.gdl == 126
    assert model.source_path == str(path.resolve())
    assert len(model.collections.quads) == 18
    assert len(model.collections.interfaces) == 29
    assert model.collections.analyses[1].initial_analysis_key == -100
    assert model.collections.analyses[22].initial_analysis_key == 1
