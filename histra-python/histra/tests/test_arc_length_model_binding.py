from __future__ import annotations

import ast
import inspect
import textwrap

from histra.solver.arc_length import ArcLength


def test_domain_changed_keeps_model_parameter_bound() -> None:
    """Regression: domain_changed must retain model for automatic DOF selection."""
    source = textwrap.dedent(inspect.getsource(ArcLength.domain_changed))
    tree = ast.parse(source)

    deleted_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Delete)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert "model" not in deleted_names
