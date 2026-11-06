"""Generate small, unrun masonry reference inputs for C# 2026.1.1 validation.

Only schema/material defaults are borrowed from the tracked HRX template.
Geometry, restraints, loading, analysis definitions and empty states are new.
No serialized interfaces, springs, afference matrices or committed histories
are copied. Existing reference inputs are never overwritten.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import subprocess
from pathlib import Path
import xml.etree.ElementTree as E

CASE_NAMES = (
    "01_isotropic_reversal",
    "02_orthotropic_reversal",
    "03_elastic_transverse_reversal",
    "04_zero_friction_reversal",
)
DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "histra/model-live/model.hrx"


def build_reference_model(template_path: Path, variant: str) -> E.ElementTree:
    if variant not in CASE_NAMES:
        raise ValueError(f"Unknown masonry reference case: {variant}")
    old = E.parse(template_path).getroot()
    r = E.Element("HiStrA", dict(old.attrib))
    r.set("IsLocked", "false")
    r.set("GDL", "28")
    r.set("version", "2026.1.1")
    for x in old:
        if x.tag in (
            "Plugins",
            "ModelProperty",
            "AdvancedOptionsDefault",
            "Layer",
            "GridCoordinate",
            "LoadCondition",
            "ActionTable",
            "CombinationCoefficient",
        ):
            r.append(copy.deepcopy(x))
    mat = copy.deepcopy(next(x for x in old if x.tag == "Template" and x.get("Key") == "18"))
    mat.attrib.update(
        Key="18",
        Name=variant,
        IsExistent="false",
        SimpleMode="false",
        Ehor="100",
        Ever="100",
        Gd="40",
        FmHor=".3",
        FmVer=".3",
        FtmHor=".0005",
        FtmVer=".0005",
        fvk0d=".01",
        FrictionRatioShear=".02",
        ShearPlasticStiffnessRatio=".05",
        ShearPlasticStiffnessRatio2=".05",
        DuctilityShear="100",
        ShearPlasticStrain="1",
        FrictionRatioSlidingHor=".3",
        FrictionRatioSlidingVert=".3",
        FrictionRatioSlidingDir3=".3",
        CohesionSlidingHor=".03",
        CohesionSlidingVert=".03",
        CohesionSlidingDir3=".03",
        ortpf="false",
        ortsc="false",
        orttagl="false",
    )
    if variant.startswith("02"):
        mat.attrib.update(
            ortpf="true",
            Ehor="80",
            Ever="160",
            FmHor=".25",
            FmVer=".4",
            FtmHor=".0005",
            FtmVer=".001",
            Gt=".0002",
            GtVer=".0003",
        )
    if variant.startswith("03"):
        for key in (
            "TensileCurveType",
            "CompressiveCurveType",
            "TensileCurveTypeVertical",
            "CompressiveCurveTypeVertical",
        ):
            mat.set(key, "Elastic")
    if variant.startswith("04"):
        mat.set("FrictionRatioShear", "0")
    r.append(mat)
    # Ten geometric nodes, four stacked masonry Quads; no serialized interfaces or histories.
    for row in range(5):
        for col in range(2):
            key = 2 * row + col + 1
            n = E.SubElement(
                r,
                "Node",
                IsModelPoint="true" if key == 10 else "false",
                Point=f"{100 * col};0;{50 * row}",
                MasterElementKey="0",
                MasterElementType="None",
                LayerKey="1",
                IsPropertyModified="false",
                Key=str(key),
                Name=str(key),
            )
    for row in range(4):
        q = E.SubElement(
            r,
            "Quad",
            Key=str(row + 1),
            Name=f"Wall_{row + 1}",
            ParentKey="1",
            ParentTypeElement="Bridge",
            MaterialKey="18",
            LayerKey="1",
            IsPropertyModified="false",
            MasterElementKey="0",
            MasterElementType="None",
            **{
                f"NodeKey{j}": str(k)
                for j, k in enumerate((2 * row + 1, 2 * row + 2, 2 * row + 4, 2 * row + 3), 1)
            },
            **{f"Thickness{j}": "20" for j in range(1, 5)},
            **{f"Normal{j}": "0;-1;0" for j in range(1, 5)},
        )
        E.SubElement(
            q,
            "ReferenceSystem",
            E1="1;0;0",
            E2="0;0;1",
            E3="0;-1;0",
            Origin=f"50;0;{25 + row * 50}",
        )
    br = E.SubElement(
        r,
        "Bridge",
        H="200",
        B="20",
        L="100",
        Key="1",
        Name="Four_Quad_Wall",
        MasterElementKey="0",
        MasterElementType="None",
        LayerKey="1",
        IsPropertyModified="false",
    )
    qks = E.SubElement(br, "QuadKeys")
    for k in range(1, 5):
        E.SubElement(qks, "QuadKey", Value=str(k))
    gks = E.SubElement(br, "GeometryLineRestraintKeys")
    E.SubElement(gks, "GeometryLineRestraintKey", Value="1")
    E.SubElement(br, "ReferenceSystem", E1="1;0;0", E2="0;1;0", E3="0;0;1", Origin="0;0;0")
    gl = copy.deepcopy(next(x for x in old if x.tag == "GeometryLineRestraint"))
    gl.set("NodeKey1", "1")
    gl.set("NodeKey2", "2")
    gl.set("B", "20")
    gl.set("Key", "1")
    for x in list(gl):
        gl.remove(x)
    E.SubElement(gl, "RestraintKeys")
    E.SubElement(gl.find("RestraintKeys"), "RestraintKey", Value="1")
    E.SubElement(gl, "ReferenceSystem", E1="1;0;0", E2="0;0;1", E3="0;-1;0", Origin="50;0;0")
    r.append(gl)
    re = copy.deepcopy(next(x for x in old if x.tag == "Restraint"))
    re.attrib.update(
        Key="1",
        NodeKey1="1",
        NodeKey2="2",
        NodeCKey1="1",
        NodeCKey2="2",
        ComputationalElementKey="1",
        ComputationalElementEdge="0",
        G="50;0;0",
        Point1="0;-10;0",
        Point2="100;-10;0",
        Point3="100;10;0",
        Point4="0;10;0",
    )
    for x in list(re):
        re.remove(x)
    E.SubElement(re, "ReferenceSystem", E1="1;0;0", E2="0;0;1", E3="0;-1;0", Origin="50;0;0")
    r.append(re)
    for k in (1, 2):
        nc = E.SubElement(
            r,
            "NodeC",
            NodeKey=str(k),
            IsIndipendent="true",
            Key=str(k),
            Name=str(k),
            MasterElementKey="0",
            MasterElementType="None",
            LayerKey="0",
            IsPropertyModified="false",
        )
        E.SubElement(E.SubElement(nc, "MasterElements"), "MasterElement", Key=str(k), Value="Node")
        E.SubElement(E.SubElement(nc, "SlaveElements"), "SlaveElement", Key="1", Value="Restraint")
    mp = copy.deepcopy(next(x for x in old if x.tag == "ModelPoint"))
    mp.attrib.update(
        IdElement="10",
        ElementKey="10",
        ParentKey="1",
        Key="1",
        Point="100;0;200",
        Description="Top right wall node",
    )
    for x in ("Ux", "Uy", "Uz", "Vx", "Vy", "Vz", "Ax", "Ay", "Az"):
        mp.set(x, "0")
    r.append(mp)
    # Compression 60 kN and cycling +/-8 kN along the 100-cm top edge.
    for key, condition, value, direction in [("3", "11", ".08", "1"), ("4", "2", ".6", "0")]:
        tpl = copy.deepcopy(next(x for x in old if x.tag == "Template" and x.get("Key") == "3"))
        tpl.set("Key", key)
        tpl.set("Name", "Horizontal_8kN" if key == "3" else "Compression_60kN")
        item = tpl.find("./LoadtemplateItemList/LoadTemplateItem")
        item.attrib.update(
            IdLoadTemplate=key,
            Key=key,
            IdLoadCondition=condition,
            LoadValue=value,
            IdLoadDirection=direction,
            DirX="1" if key == "3" else "0",
            DirY="0",
            DirZ="0" if key == "3" else "-1",
            IsProjected="false",
        )
        r.append(tpl)
        E.SubElement(
            r,
            "LoadElement",
            TypeOf="HiStrA.Objects.LineLoadElement",
            Key=key,
            ParentKey="0",
            ElementKey="4",
            ElementType="Quad",
            IdLoadTemplate=key,
            Point1="0;0;200",
            Point2="100;0;200",
        )
    for key, conds in [("6", ("1", "2")), ("1", ("11",))]:
        combo = copy.deepcopy(
            next(x for x in old if x.tag == "LoadCombination" and x.get("Key") == key)
        )
        for item in combo:
            item.attrib.update(
                TypeData="Number",
                SecondaryTypeData="Number",
                Val="1" if item.get("ColumnKey") in conds else "0",
            )
        r.append(combo)
    for key, name, parent, combo in [
        ("1", "Vert", "-100", "6"),
        ("2", "Reversal", "1", "1"),
        ("3", "Modal_virgin", "-100", "6"),
        ("4", "Modal_after_reversal", "2", "6"),
    ]:
        a = copy.deepcopy(next(x for x in old if x.tag == "Analysis" and x.get("Key") == "1"))
        a.attrib.update(
            Key=key,
            Name=name,
            InitialAnalysisKey=parent,
            InitialCombinationAnalysisKey="1",
            LoadCombinationKey=combo,
            LoadFunctionKey=key,
            Method="StandardNewtonRaphson",
            ConvergenceTolerance="1E-8",
            MaxIterations="1000",
            maxU="10",
            Mult="1",
            IntegrationMethod="LoadControl",
        )
        if key in ("3", "4"):
            a.attrib.update(
                AnalysisType="5",
                ModalProcedure="InverseIterations",
                NumberOfEigenModes="6",
                ModalConvergenceCriteria="Frquency",
                ConvergenceTolerance="1E-10",
            )
        for child in a:
            child.clear()
        E.SubElement(a.find("ActiveModelPoints"), "ActiveModelPoint", Key="1", Value="true")
        E.SubElement(a.find("DisplModelPoints"), "DisplModelPoint", Key="1", Value="0")
        r.append(a)
        E.SubElement(
            r, "LoadFunction", key=key, typeDiscr="false", DiscrVal=".1" if key == "1" else ".125"
        )
        pts = [(0, 0), (1, 1), (2, -1), (3, 1), (4, 0)] if key == "2" else [(0, 0), (1, 1)]
        for j, (t, m) in enumerate(pts):
            E.SubElement(
                r,
                "LoadFunctionItem",
                key=str(10 * int(key) + j + 1),
                loadFunctionKey=key,
                pseudoTime=str(t),
                multiplier=str(m),
            )
    E.indent(r, space="  ")
    return E.ElementTree(r)


def write_reference_models(template_path: Path, output_dir: Path) -> list[Path]:
    targets = [output_dir / name / (name + ".hrx") for name in CASE_NAMES]
    protected = targets + [output_dir / "manifest.json", output_dir / "README.md"]
    if any(path.exists() for path in protected):
        raise FileExistsError("Reference inputs already exist; use a new output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, path in zip(CASE_NAMES, targets):
        path.parent.mkdir(parents=True, exist_ok=True)
        (path.parent / "csharp").mkdir(exist_ok=True)
        build_reference_model(template_path, name).write(
            path, encoding="utf-8", xml_declaration=True
        )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=DEFAULT_TEMPLATE.parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "schema_version": 1,
        "generator": "tools/benchmarks/build_masonry_reference_models.py",
        "target_reference_version": "2026.1.1",
        "template_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
        "source_note": "Template supplies schema defaults only; generated models are not native result references yet.",
        "geometry": {"quads": 4, "interfaces_after_preparation": 4, "active_dofs": 28},
        "nominal_loads_kN": {"top_compression": 60, "horizontal_peak": 8},
        "run_order": ["Modal_virgin", "Vert", "Reversal", "Modal_after_reversal"],
        "static_steps": {"Vert": 10, "Reversal": 32},
        "initial_step_is_committed": False,
        "models": [
            {
                "case": name,
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in zip(CASE_NAMES, targets)
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "README.md").write_text(RUN_INSTRUCTIONS, encoding="utf-8")
    return targets


RUN_INSTRUCTIONS = """# Masonry reference models for HiStrA 2026.1.1

Each file is a new four-Quad wall (100 cm wide, 200 cm high, 20 cm thick),
with one fixed foundation, self weight, nominal 60 kN top compression and
nominal +/-8 kN horizontal cycling. Materials are already assigned. No
interface-material changes are required.

Cases: 01 isotropic; 02 different horizontal/vertical flexural properties;
03 elastic transverse springs with Coulomb shear; 04 zero-friction diagonal
shear (the original Hysteretic construction branch).

For each case:

1. Open the root HRX in HiStrA Bridges 2026.1.1. It is unlocked and has no
   saved interfaces/springs or analysis results.
2. Before solving, Save As into its empty `csharp` subfolder, using the same
   HRX filename. Keep the generated root input unchanged.
3. Allow analysis preparation to generate the computational model from the
   supplied four-Quad geometry. Run analyses in this order: `Modal_virgin`, `Vert`, `Reversal`, `Modal_after_reversal`.
4. Save in the same `csharp` location after running. Keep the matching HRX,
   .Results and any parity logs together. Do not change materials, combinations,
   load functions, step counts or tolerances for this first comparison.
5. If an analysis fails, keep its partial results and log; do not tune it to
   completion. Tell me which case/analysis stopped.

Expected Python baseline under original native UMFPACK controls: Vert has
10 commits and Reversal has 32 (step zero excluded). The horizontal multiplier
follows 0 -> +1 -> -1 -> +1 -> 0. These counts are comparison expectations,
not a claim that the C# run has already been validated. Modal analyses request
six modes each. Comparisons will rebuild Python geometry from the original
inputs, without importing the saved C# interfaces or committed histories.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in write_reference_models(args.template, args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
