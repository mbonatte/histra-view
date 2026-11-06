"""Fresh wall inputs for native P-Delta update and save-cache validation."""
from tools.benchmarks.build_secant_reference_model import build_secant_reference_model


def build_pdelta_reference_model(mode: str, step_save: int = 1):
    if mode not in ("EachStep", "EachIteration") or step_save < 1:
        raise ValueError("Expected a supported P-Delta mode and positive StepSave")
    tree = build_secant_reference_model(0.4)
    analysis = next(item for item in tree.getroot() if item.tag == "Analysis" and item.get("Key") == "2")
    analysis.attrib.update(PdeltaEffect=mode, CheckSecantStiffness="false", StepSave=str(step_save))
    return tree
