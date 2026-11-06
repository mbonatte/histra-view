"""Inventory Python definitions and a bounded set of real native contracts.

An AST census is not a numerical verification. Native contracts below identify
source declarations and concrete evidence, never certification of whole files.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


PACKAGES = ("model", "elements", "springs", "preprocessing", "solver")
CONTRACTS = (
    ("masonry-backbone", ("histra/springs/hysteretic.py", "histra/solver/hysteretic_kernels/transverse.py"),
     "ModelLibrary/Objects/SpringHysteretic.cs", ("SetInitial", "setTrialStrain", "Commit"),
     "histra/tests/fixtures/csharp-masonry-backbone-state-transfer-2026.1.1.json"),
    ("material-history", ("histra/solver/restart.py", "histra/springs/transverse_fiber_group.py"),
     "ModelLibrary/Objects/ElementStates/SpringStateDBclass.cs", ("SetFromSpring", "SetSpring"),
     "histra/tests/fixtures/csharp-masonry-backbone-state-transfer-2026.1.1.json"),
    ("pdelta-load", ("histra/solver/model_manager.py", "histra/solver/hysteretic_runtime.py"),
     "ModelLibrary/ModelManagement/Load/ModelLoadOperations.cs", ("ComputePDeltaLoads",),
     "histra/tests/fixtures/csharp-pdelta-2026.1.1.json"),
    ("pdelta-save-timing", ("histra/solver/model_manager.py", "histra/solver/nonlinear_step.py"),
     "SolverRuntime/CommonOperations.cs", ("AddStateElements",),
     "histra/tests/fixtures/csharp-pdelta-execution-2026.1.1.json"),
    ("secant-switch", ("histra/solver/secant_stiffness.py",),
     "SolverRuntime/AnalysisProcedure/StaticNonLinearAnalysis.cs", ("Execute",),
     "histra/tests/fixtures/csharp-secant-execution-2026.1.1.json"),
    ("arc-corrector", ("histra/solver/arc_length.py",),
     "SolverRuntime/Integrator/ArcLength.cs", ("Update",),
     "histra/tests/fixtures/csharp_arc_length_update_2026_1_1.json"),
    ("contact-intersection", ("histra/preprocessing/contact_geometry.py",),
     "UtilityLibrary/Matematics/Operations.cs", ("FindIntersectionBetweenQuadrilaters",),
     "histra/tests/fixtures/csharp_quad_contact_intersection_2026_1_1.json"),
    ("restraint-cell-area", ("histra/preprocessing/csharp_fibre_geometry.py",),
     "UtilityLibrary/Matematics/Operations.cs", ("Area",),
     "histra/tests/fixtures/csharp-polygon-area-2026.1.1.json"),
)


class DefinitionInventory(ast.NodeVisitor):
    def __init__(self):
        self.stack = []
        self.classes = []
        self.functions = []

    def _visit(self, node, collection):
        collection.append({"name": ".".join([*self.stack, node.name]), "line": node.lineno})
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ClassDef(self, node):
        self._visit(node, self.classes)

    def visit_FunctionDef(self, node):
        self._visit(node, self.functions)

    visit_AsyncFunctionDef = visit_FunctionDef


def inventory_python(root):
    rows = []
    for package in PACKAGES:
        for path in sorted((root / "histra" / package).rglob("*.py")):
            text = path.read_text(encoding="utf-8-sig")
            visitor = DefinitionInventory()
            visitor.visit(ast.parse(text, filename=str(path)))
            rows.append({"path": path.relative_to(root).as_posix(), "status": "inventory_only",
                         "lf_sha256": hashlib.sha256(text.replace("\r\n", "\n").encode()).hexdigest(),
                         "classes": visitor.classes, "functions": visitor.functions})
    return rows


def native_contracts(root, source_root):
    rows = []
    for name, consumers, source, members, evidence in CONTRACTS:
        for relative in (*consumers, evidence):
            if not (root / relative).is_file():
                raise ValueError(f"Missing consumer/evidence: {relative}")
        path = source_root / source
        text = path.read_text(encoding="utf-8-sig")
        declarations = {}
        for member in members:
            pattern = r"(?m)^\s*(?:public|private|internal|protected) [^\n]*\b" + re.escape(member) + r"\s*\("
            matches = list(re.finditer(pattern, text))
            if not matches:
                raise ValueError(f"No declaration for {member} in {source}")
            declarations[member] = [text.count("\n", 0, match.end()) + 1 for match in matches]
        rows.append({"name": name, "status": "native_fixture_cases_only", "consumers": list(consumers),
                     "source": source, "source_lf_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "declarations": declarations, "evidence": evidence,
                     "evidence_lf_sha256": hashlib.sha256(
                         (root / evidence).read_text(encoding="utf-8-sig").encode()).hexdigest()})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    files = inventory_python(root)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "generator": "tools/benchmarks/build_source_audit_inventory.py",
        "benchmark_id": "masonry-source-inventory-not-parity-certification",
        "definition_scope": "AST class/function definitions including nested helpers; excludes lambdas and aliases.",
        "counts": {"files": len(files), "classes": sum(len(r["classes"]) for r in files),
                   "function_definitions": sum(len(r["functions"]) for r in files)},
        "files": files, "native_contracts": native_contracts(root, args.source_root),
        "limitations": ["Inventory coverage is not numerical coverage.",
                        "Native fixtures qualify their inputs and checked fields only.",
                        "This registry is a selected set of source bindings, not an exhaustive mapping."],
    }
    args.output.write_bytes((json.dumps(report, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
