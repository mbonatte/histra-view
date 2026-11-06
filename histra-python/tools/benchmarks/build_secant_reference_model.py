"""Fresh wall inputs that exercise C# ArcLength secant tangent switching."""
from pathlib import Path
import xml.etree.ElementTree as ET

from tools.benchmarks.build_masonry_reference_models import DEFAULT_TEMPLATE, build_reference_model


def build_secant_reference_model(ratio: float) -> ET.ElementTree:
    tree = build_reference_model(DEFAULT_TEMPLATE, "01_isotropic_reversal")
    root = tree.getroot()
    analysis = next(item for item in root if item.tag == "Analysis" and item.get("Key") == "2")
    analysis.attrib.update(Name="Secant", IntegrationMethod="ArcLength", CheckSecantStiffness="true",
                          SecantStiffnessRatio=str(ratio), TargetDisplacement=".08", Dr2=".0001",
                          ArcLengthProcedure="OnlyControlPoint", MasterPoint="1", MaxIterations="100",
                          DirectionAzimut="0", DirectionZenit="0", DirX="1", DirY="0", DirZ="0",
                          DirXDisp="1", DirYDisp="0", DirZDisp="0", UpdateDr2="false",
                          IsMaxArcLengthRay="false", LoadReductionRatioToStop="false")
    items = [item for item in root if item.tag == "LoadFunctionItem" and item.get("loadFunctionKey") == "2"]
    for item in items[2:]:
        root.remove(item)
    ET.indent(root, space="  ")
    return tree


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratio", type=float)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    build_secant_reference_model(args.ratio).write(args.output, encoding="utf-8", xml_declaration=True)
