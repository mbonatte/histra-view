"""AdvancedOptionsDefault's two Single tolerances and Double InterfaceImax."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from histra import load_model
from histra.io.hr_loader import _parse_advanced_options
from histra.model.model import Model
from histra.solver.model_manager import ModelManager
from tools.benchmarks.build_masonry_reference_models import DEFAULT_TEMPLATE, build_reference_model


def test_native_geometry_settings_survive_parser_and_programmatic_preparation(tmp_path):
    fixture = Path(__file__).parent / "fixtures/csharp-geometry-settings-2026.1.1.json"
    cases = json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]
    path = tmp_path / "wall.hrx"
    build_reference_model(DEFAULT_TEMPLATE, "01_isotropic_reversal").write(path, encoding="utf-8")
    for case in cases:
        value = case["input"]
        model = Model()
        options = ET.Element("AdvancedOptionsDefault", ToleranceNode=str(value),
                             TolerancePlane=str(value), InterfaceImax=str(value))
        _parse_advanced_options(options, model)
        assert model.geometry_tolerance_node == case["node"]
        assert model.geometry_tolerance_plane == case["plane"]
        assert model.interface_imax == case["imax"]
        model = load_model(path)
        model.geometry_tolerance_node = value
        model.geometry_tolerance_plane = value
        ModelManager.prepare_model(model, force=True, use_cache=False)
        assert model.geometry_tolerance_node == case["node"]
        assert model.geometry_tolerance_plane == case["plane"]
