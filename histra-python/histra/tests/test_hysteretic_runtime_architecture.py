"""Architecture checks for the extracted hysteretic runtime owner."""

import importlib
import importlib.util
import types


def test_batch_module_is_a_pure_compatibility_facade():
    batch = importlib.import_module("histra.solver.hysteretic_batch")
    runtime = importlib.import_module("histra.solver.hysteretic_runtime")

    # Every runtime name (except module aliases and dunders) must be
    # re-exported by identity.
    missing = [
        name
        for name in dir(runtime)
        if not name.startswith("__")
        and not isinstance(getattr(runtime, name), types.ModuleType)
        and getattr(batch, name, None) is not getattr(runtime, name)
    ]
    assert missing == []


def test_runtime_owner_has_no_reverse_dependency_on_hysteretic_batch():
    source = importlib.util.find_spec(
        "histra.solver.hysteretic_runtime"
    ).origin
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "hysteretic_batch import" not in text
