"""Deliberately inject known faults in a separate process and require detection.

Run each scenario with a new ``python -m`` invocation. The ordinary tests still
compare against native output; this tool checks that they reject broken code.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import pytest


class Failures:
    count = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.failed:
            self.count += 1


def inject_fault(scenario):
    if scenario == "backbone":
        from histra.springs.hysteretic import SpringHysteretic

        def broken(*args, **kwargs):
            raise AssertionError("Deliberately broken production constitutive update")
        SpringHysteretic.set_trial_strain = broken
        return "histra/tests/test_csharp_multilinear_live.py", ["-k", "native_masonry_multilinear_backbone"], 3
    if scenario == "transfer":
        from histra.springs.transverse_fiber_group import TransverseFiberGroup
        original = TransverseFiberGroup.copy_committed_state_from

        def broken(self, source):
            original(self, source)
            self._trial[:, 9] = self._k  # Reintroduce the wrong target tangent.
        TransverseFiberGroup.copy_committed_state_from = broken
        return "histra/tests/test_native_material_state_transfer.py", ["-k", "not scalar"], 6
    from histra.solver.hysteretic_runtime import HystereticBatchRuntime
    original = HystereticBatchRuntime._read_transverse_objects_bulk

    def broken(self, springs, **kwargs):
        if not springs:
            return  # Reintroduce the all-numeric early return.
        return original(self, springs, **kwargs)
    HystereticBatchRuntime._read_transverse_objects_bulk = broken
    return "histra/tests/test_numeric_fibre_runtime_import.py", [], 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("backbone", "transfer", "numeric-import"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    test, filters, expected = inject_fault(args.scenario)
    counts = Failures()
    result = int(pytest.main(["-q", "--tb=no", test, *filters], plugins=[counts]))
    if result != 1 or counts.count != expected:
        raise RuntimeError(f"Fault not detected as expected: exit={result}, failures={counts.count}/{expected}")
    root = Path(__file__).resolve().parents[2]
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "generator": "tools/benchmarks/probe_native_test_sensitivity.py",
        "benchmark_id": "native-test-sensitivity-" + args.scenario,
        "scenario": args.scenario, "outcome": "known_fault_detected",
        "failed_as_expected": counts.count, "test": test,
        "test_lf_sha256": hashlib.sha256((root / test).read_text().encode()).hexdigest(),
        "limitation": "Detects the specified injected fault; not a proof of exhaustive fault coverage.",
    }
    args.output.write_bytes((json.dumps(report, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
