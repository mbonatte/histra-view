"""Create fresh GUI references for loaded foundation material changes.

These are experiments to run in the original application, not golden results.
The foundation changes are deliberately manual: their GUI preparation/restart
path is the boundary we need to measure independently of our native drivers.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as E

from tools.benchmarks.build_masonry_reference_models import DEFAULT_TEMPLATE, build_reference_model


CASES = ("01_foundation_stiffness_return", "02_foundation_elastic_return")
ANALYSES = (
    (3, "Modal_virgin", -100, 3),
    (1, "Vert", -100, 1),
    (4, "Modal_loaded_A", 1, 4),
    (2, "Cycle_B", 1, 2),
    (5, "Modal_loaded_B", 2, 4),
    (6, "Cycle_return_A", 2, 2),
    (7, "Modal_return_A", 6, 4),
)


def build_material_modal_model(template: Path, case: str) -> E.ElementTree:
    if case not in CASES:
        raise ValueError(f"Unknown material/modal reference case: {case}")
    tree = build_reference_model(template, "01_isotropic_reversal")
    root = tree.getroot()
    original = root.find("Template[@Key='18']")
    assert original is not None
    original.set("Name", "A_Original_Masonry")
    replacement = copy.deepcopy(original)
    replacement.set("Key", "19")
    if case == CASES[0]:
        replacement.attrib.update(Name="B_Half_Stiffness_Masonry", Ehor="50", Ever="50", Gd="20")
    else:
        replacement.set("Name", "B_Elastic_Transverse_Masonry")
        for field in (
            "TensileCurveType", "CompressiveCurveType",
            "TensileCurveTypeVertical", "CompressiveCurveTypeVertical",
        ):
            replacement.set(field, "Elastic")
    root.append(replacement)
    _replace_analyses(root)
    E.indent(tree, space="  ")
    return tree


def _replace_analyses(root: E.Element) -> None:
    originals = {int(a.get("Key")): a for a in root.findall("Analysis")}
    functions = {int(a.get("key")): a for a in root.findall("LoadFunction")}
    items = root.findall("LoadFunctionItem")
    for tag in ("Analysis", "LoadFunction", "LoadFunctionItem"):
        for element in root.findall(tag):
            root.remove(element)
    for key, name, parent, source in ANALYSES:
        analysis = copy.deepcopy(originals[source])
        analysis.attrib.update(
            Key=str(key), Name=name, InitialAnalysisKey=str(parent), LoadFunctionKey=str(key),
        )
        root.append(analysis)
        function = copy.deepcopy(functions[source])
        function.set("key", str(key))
        root.append(function)
        for offset, original in enumerate(i for i in items if i.get("loadFunctionKey") == str(source)):
            item = copy.deepcopy(original)
            item.attrib.update(key=str(key * 10 + offset + 1), loadFunctionKey=str(key))
            root.append(item)


def write_models(template: Path, output: Path) -> list[Path]:
    # The entire directory is reserved before writing: old native evidence must
    # never be mixed with inputs from a regenerated experiment.
    output.mkdir(parents=True, exist_ok=False)
    paths = []
    for case in CASES:
        folder = output / case
        (folder / "csharp").mkdir(parents=True)
        path = folder / f"{case}.hrx"
        build_material_modal_model(template, case).write(path, encoding="utf-8", xml_declaration=True)
        paths.append(path)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=DEFAULT_TEMPLATE.parents[2],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": revision,
        "generator": "tools/benchmarks/build_material_modal_reference_models.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
        "benchmark_id": "gui-loaded-foundation-material-return-2026.1.1",
        "target_version": "2026.1.1",
        "status": "unrun_inputs_not_native_reference_results",
        "run_order": [name for _, name, _, _ in ANALYSES],
        "manual_changes": [
            {"before": "Cycle_B", "foundation_material_key": 19},
            {"before": "Cycle_return_A", "foundation_material_key": 18},
        ],
        "target": "Only the bottom Quad 1 / Restraint 1 foundation joint, z=0 cm",
        "expected_python_commits": {"Vert": 10, "Cycle_B": 32, "Cycle_return_A": 32},
        "step_zero_is_commit": False,
        "requested_modes_per_modal_analysis": 6,
        "models": [
            {"path": p.relative_to(output).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in paths
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text(RUN_INSTRUCTIONS, encoding="utf-8")
    return paths


RUN_INSTRUCTIONS = """# Loaded foundation material and modal references - C# 2026.1.1

Two independent four-Quad walls: 100 cm wide, 200 cm high, 20 cm thick.
All Quads use A_Original_Masonry (material 18). Only the ONE foundation
interface at z=0 cm will change. It joins bottom Quad 1 to Restraint 1;
do not select the three internal horizontal wall joints at z=50/100/150 cm.
The initial HRXs contain fresh geometry, with no saved computational model.

Case 01: B_Half_Stiffness_Masonry (19) halves Ehor, Ever and Gd.
Case 02: B_Elastic_Transverse_Masonry (19) uses elastic transverse curves;
its sliding/friction properties are unchanged. It is still a masonry material.

## Run each case separately, using the ORIGINAL HiStrA Bridges 2026.1.1

1. Open the case root HRX. Save As the SAME filename inside its empty `csharp`
   folder before running. Keep the generated root file unchanged.
2. Generate the computational model from the supplied geometry by running
   `Modal_virgin`. Then run `Vert`, then `Modal_loaded_A`, individually.
   Save. Copy the saved HRX and matching Results together into a new
   `csharp/snapshots/01_loaded_A` folder, keeping their matching base names.
3. Change ONLY the foundation interface material to B (19), ONCE. Do not edit
   the material definition or the Quad material. Run `Cycle_B`, then
   `Modal_loaded_B`. Save. Copy the HRX and matching Results into
   `csharp/snapshots/02_loaded_B`.
4. Change that SAME foundation interface to A_Original_Masonry (18), ONCE.
   Run `Cycle_return_A`, then `Modal_return_A`. Save. Leave the final HRX and
   matching Results at `csharp/`, and copy them into `snapshots/03_return_A`.
5. Copy the parity logs created during this case into `csharp/logs`. Include
   normal successful-run logs, not just errors. The installed diagnostic
   runtime normally writes them under the original installation's parity-logs.
   Record the application version and any warnings/failures in `csharp/notes.txt`.

Run ONLY the next named analysis, not the whole tree or its predecessors again.
Do not unlock/regenerate after starting, rerun earlier analyses, or adjust load
combinations, steps, tolerances, materials or modal settings. A repeated reset
can change C# parent-interface registration, so the exact edit count matters.
Keep the application open for the complete case. Save after each phase.

If changing the material requires deleting earlier analyses, or the application
automatically reruns/invalidates them, STOP and record what happened. Preserve
the current files and logs; do not unlock it to force the next stage. The GUI
restart behavior is part of this experiment, not an assumed solver result.

Vert applies selfweight plus 60 kN top compression. Each subsequent cycle adds
a nominal +/-8 kN horizontal load: 0 -> +1 -> -1 -> +1 -> 0, retaining its
specified static predecessor. The second cycle starts from Cycle_B, not from
Vert and not from a modal analysis. Modal analyses request six modes each;
keep partial modal results and warnings if fewer modes converge.

The nominal static discretizations are 10/32/32 committed steps, EXCLUDING
step zero. These are input expectations, not acceptance criteria or claims
of successful native execution. Preserve failures and adaptive retries too.

These cases target loaded material resets, restoration, two constitutive-law
paths and loaded-state modal results. They do not close the entire validation
register (clustered/rigid modes, general geometry and damage sweeps remain).
Some private histories are absent from standard Results/parity logs; further
original-runtime instrumentation may still be needed after inspecting this run.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in write_models(args.template, args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
