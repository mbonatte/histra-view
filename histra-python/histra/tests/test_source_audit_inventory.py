"""Keep the inventory current without confusing it with proof of parity."""
import json
import hashlib
from pathlib import Path

from tools.benchmarks.build_source_audit_inventory import CONTRACTS, inventory_python


ROOT = Path(__file__).parents[2]
INVENTORY = ROOT / "docs/audit/csharp-python-source-inventory.json"


def test_inventory_matches_actual_python_definitions_and_source_hashes():
    report = json.loads(INVENTORY.read_text())
    actual = inventory_python(ROOT)
    assert report["files"] == actual
    assert report["counts"] == {"files": len(actual),
        "classes": sum(len(row["classes"]) for row in actual),
        "function_definitions": sum(len(row["functions"]) for row in actual)}
    assert all(row["status"] == "inventory_only" for row in actual)


def test_native_contracts_have_real_local_evidence_and_bounded_status():
    contracts = json.loads(INVENTORY.read_text())["native_contracts"]
    assert len(contracts) == len(CONTRACTS)
    for row, definition in zip(contracts, CONTRACTS, strict=True):
        name, consumers, source, members, evidence = definition
        assert (row["name"], row["consumers"], row["source"], row["evidence"]) == (name, list(consumers), source, evidence)
        assert set(row["declarations"]) == set(members)
        assert all(lines and all(line > 0 for line in lines) for lines in row["declarations"].values())
        assert len(row["source_lf_sha256"]) == 64
        assert row["status"] == "native_fixture_cases_only"
        assert all((ROOT / path).is_file() for path in (*consumers, evidence))
        assert row["evidence_lf_sha256"] == hashlib.sha256(
            (ROOT / evidence).read_text(encoding="utf-8-sig").encode()).hexdigest()
