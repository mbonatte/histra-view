from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest

from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession
from histra.solver.model_manager import ModelManager
from histra.solver.output_projection import compute_model_point_displacements

pytestmark = pytest.mark.filterwarnings(
    "ignore::histra.solver.strategy.SuboptimalSolverStrategyWarning"
)


def test_run_model_notebook_is_valid_json():
    nb_path = Path(__file__).parents[2] / "run_model.ipynb"
    assert nb_path.exists(), f"Notebook file {nb_path} does not exist"
    
    with open(nb_path, encoding="utf-8") as f:
        nb = json.load(f)
        
    assert nb.get("nbformat") == 4
    assert len(nb.get("cells", [])) >= 10
    
    markdown_text = "\n".join("".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type") == "markdown")
    assert "Benchmark 1" in markdown_text
    assert "Benchmark 2" in markdown_text
    assert "Random Bridge Models" in markdown_text


def test_aligned_step_history_on_benchmark_1():
    benchmark_dir = Path(__file__).parents[2] / "my_model" / "benchmark_1"
    hrx_file = benchmark_dir / "benchmark_virgin.hrx"
    results_file = benchmark_dir / "benchmark.Results"
    
    if not hrx_file.exists() or not results_file.exists():
        pytest.skip("Benchmark 1 model files not available in this environment.")
        
    model = load_model(hrx_file)
    ModelManager.prepare_model(model)
    session = AnalysisSession(model)
    
    # Run Vert
    exec_vert = session.run("Vert")
    assert exec_vert.completed
    
    with sqlite3.connect(results_file) as db:
        cs_reactions = {
            (r[0], r[1]): r[5]
            for r in db.execute("SELECT AnalysisKey, Step, Combination, R1, R2, R3 FROM ReactionSumStates WHERE AnalysisKey=1").fetchall()
        }
        
    # Step 0 match
    assert (1, 0) in cs_reactions
    assert cs_reactions[(1, 0)] == pytest.approx(0.0)
    
    # Step final reaction match (R3)
    last_step = exec_vert.committed_steps[-1]
    assert (1, last_step.step) in cs_reactions
    assert last_step.reaction_z == pytest.approx(cs_reactions[(1, last_step.step)], rel=1e-3)


def test_pier_tilt_kinematics_calculation():
    uz_up = -0.020
    uz_down = -0.010
    dy = 252.0
    theta_x_mrad = (uz_down - uz_up) / dy * 1000.0
    
    assert theta_x_mrad == pytest.approx(10.0 / 252.0, rel=1e-4)
    
    ux_top = 0.005
    ux_base = 0.001
    dz = 225.0
    theta_y_mrad = (ux_top - ux_base) / dz * 1000.0
    
    assert theta_y_mrad == pytest.approx(4.0 / 225.0, rel=1e-4)
